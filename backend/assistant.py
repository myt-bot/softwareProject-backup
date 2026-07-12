"""AI 助手（大模型对话 + 命令行工具调用）后端模块。

目标
====
让用户在网页里用自然语言与大模型对话，大模型能像用户一样「登录后」操作本系统：
- 建模型：用户说「给我建一个 LeNet」，模型自主调用命令（template / add / connect /
  validate …）在用户的**实时画布**上把模型搭出来，并用自然语言解释；
- 答疑：用户问「我这个模型有什么问题」，模型先调**只读命令**（get_model_graph /
  validate / get_shapes …）摸清当前项目，再据此回答。

架构（与本机 Agent 的反向 WebSocket 同构）
==========================================
    浏览器聊天面板 <--(/assistant/ws)--> 云端后端 <--(OpenAI API 工具调用循环)--> 大模型

关键点：大模型跑在**后端**，但「命令」要在**浏览器的实时画布**上执行。因此每次工具调用
是一次往返：
  1. 模型发起工具调用（tool_calls）
  2. 后端经 WebSocket 把「执行这条命令」的请求推给浏览器
  3. 浏览器用页内命令分发器在当前画布上执行，把结果回传
  4. 后端把结果喂回模型；模型继续调用或给出最终回答

WebSocket 消息协议（JSON）
==========================
浏览器 → 后端：
  {"type": "user_message", "text": "帮我建一个 LeNet"}                    # 用户提问
  {"type": "tool_result", "call_id": "...", "ok": true, "result": {...}} # 命令执行结果回传
后端 → 浏览器：
  {"type": "tool_request", "call_id": "...", "command": "template",
   "args": {"key": "lenet"}}                                            # 请浏览器执行一条命令
  {"type": "assistant_message", "text": "...", "final": true}           # 助手（流式/最终）回复

"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


router = APIRouter(tags=["assistant"])

# 模型名与 API Key 一律由前端在「模型设置」里提供，随每条消息上送；后端不做任何默认配置。
# 前端未填写时，run_assistant_turn 会直接提示用户去填写，不发起调用。

# 单次工具调用等待浏览器回传结果的超时秒数（超时视为该命令执行失败）
TOOL_CALL_TIMEOUT_SECONDS = 30

# 一轮对话内允许的最大工具调用轮数（防止模型陷入死循环，超出即中止并给出提示）。
# 复杂建模/多画布/反复校验修正会消耗不少轮次，故给得宽松些，适配更“深”的模型。
MAX_TOOL_ITERATIONS = 80


# —————————————————————————————————————————————
# 客户端连接与工具调用桥接（后端 ↔ 浏览器）
# —————————————————————————————————————————————

class AssistantConnection:
    """一个浏览器聊天面板与后端之间的 WebSocket 会话。

    每个已登录用户的一个浏览器标签页对应一个连接；它既用于接收用户消息，也用于把
    模型发起的「命令执行请求」下发给浏览器、并等待其回传结果。
    """

    def __init__(self, user_id: str, websocket: WebSocket) -> None:
        """初始化一个助手会话。

        参数：
            user_id：该连接所属用户的 id（用于把对话与项目权限绑定到具体账号）。
            websocket：已握手成功的 FastAPI WebSocket 对象，用于双向收发 JSON 消息。
        """
        self.user_id = user_id
        self.websocket = websocket
        self._pending_calls: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._send_lock = asyncio.Lock()

    async def send_json(self, message: dict[str, Any]) -> None:
        """向浏览器发送一条 JSON 消息（助手回复 / 命令执行请求 / 状态提示）。

        参数：
            message：要下发的消息体，需符合模块顶部约定的「后端 → 浏览器」协议，
                例如 {"type": "assistant_message", "text": "...", "final": true} 或
                {"type": "tool_request", "call_id": "...", "command": "...", "args": {...}}。

        返回：无。发送失败（连接已断开）时应向上抛出异常，由调用方决定是否结束本轮对话。
        """
        async with self._send_lock:
            await self.websocket.send_json(message)

    def make_pending_call(self, call_id: str) -> "asyncio.Future[dict[str, Any]]":
        """为一次即将下发到浏览器的命令登记一个「待兑现」的 Future。

        用途：模型发起工具调用后，后端先创建一个 Future 并记录到本连接的挂起表里，然后把
        命令下发给浏览器；浏览器把结果回传时，通过 call_id 找到并兑现这个 Future，从而让
        等待中的协程拿到执行结果。

        参数：
            call_id：本次命令调用的唯一标识（后端生成），用于把「下发」与「回传」配对。

        返回：一个未完成的 asyncio.Future；等待它 await 完成即可拿到浏览器回传的结果字典
            （形如 {"ok": bool, "result": Any, "error": Optional[str]}）。
        """
        previous = self._pending_calls.pop(call_id, None)
        if previous is not None and not previous.done():
            previous.cancel()
        future = asyncio.get_running_loop().create_future()
        self._pending_calls[call_id] = future
        return future

    def resolve_pending_call(self, call_id: str, payload: dict[str, Any]) -> None:
        """用浏览器回传的结果兑现之前登记的 Future，唤醒等待该结果的协程。

        参数：
            call_id：与下发时一致的调用标识；据此在挂起表里定位对应的 Future。
            payload：浏览器回传的执行结果，形如 {"ok": bool, "result": Any, "error": str}。

        返回：无。若 call_id 不存在（重复回传或已超时清理），应安全忽略。
        """
        future = self._pending_calls.pop(call_id, None)
        if future is not None and not future.done():
            future.set_result(payload)


class AssistantHub:
    """进程内的助手连接注册表 + 工具调用桥接中枢。

    维护「用户 id → 在线聊天连接」的映射，并对外提供「让浏览器执行一条命令并取回结果」
    的统一入口，供大模型的工具调用循环使用。单进程部署（与训练调度一致）。
    """

    def __init__(self) -> None:
        """初始化空的连接注册表。"""
        self._connections: dict[str, AssistantConnection] = {}

    def register(self, user_id: str, connection: AssistantConnection) -> None:
        """登记一个用户的在线聊天连接。

        参数：
            user_id：用户 id。
            connection：该用户新建立的 AssistantConnection。
        """
        old = self._connections.get(user_id)
        if old is not None and old is not connection:
            self._cancel_pending(old, "连接已被新的浏览器会话替换")
        self._connections[user_id] = connection

    def unregister(self, user_id: str, connection: AssistantConnection) -> None:
        """注销一个已断开的聊天连接（并清理其尚未兑现的挂起调用）。

        参数：
            user_id：用户 id。
            connection：要移除的连接对象。
        """
        if self._connections.get(user_id) is connection:
            self._connections.pop(user_id, None)
        self._cancel_pending(connection, "浏览器连接已断开")

    def connection_for(self, user_id: str) -> Optional[AssistantConnection]:
        """取某用户当前在线的聊天连接。

        参数：
            user_id：用户 id。

        返回：该用户的 AssistantConnection；若其当前没有在线聊天连接则返回 None
            （此时工具调用无法执行，应让模型据此告知用户「请在网页里操作」）。
        """
        return self._connections.get(user_id)

    @staticmethod
    def _cancel_pending(connection: AssistantConnection, reason: str) -> None:
        pending = list(connection._pending_calls.values())
        connection._pending_calls.clear()
        for future in pending:
            if not future.done():
                future.set_result({"ok": False, "result": None, "error": reason})

    async def execute_command_in_browser(
        self,
        user_id: str,
        command: str,
        args: dict[str, Any],
        timeout: float = TOOL_CALL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """把一条命令下发到该用户的浏览器执行，并等待其回传结果（工具调用的核心桥接）。

        这是「模型工具调用 → 浏览器实际操作画布 → 取回结果」这条往返链路的后端侧实现入口：
        生成 call_id → 登记 Future → 经 WebSocket 下发 tool_request → await 结果。

        参数：
            user_id：目标用户 id（决定命令在谁的画布上执行）。
            command：命令名，对应页内命令分发器里的动词，如 "template" / "add" /
                "connect" / "set" / "validate" / "get_model_graph" 等。
            args：该命令的参数字典，如 {"key": "lenet"} 或 {"type": "Conv2D"}。
            timeout：等待浏览器回传结果的最长秒数；超时按失败处理。

        返回：浏览器回传的结果字典，形如 {"ok": bool, "result": Any, "error": Optional[str]}；
            result 是命令的产物（如新建节点 id、校验结论、当前模型图 JSON 等），会被喂回模型。
        """
        connection = self.connection_for(user_id)
        if connection is None:
            return {"ok": False, "result": None, "error": "浏览器助手未连接"}

        call_id = uuid4().hex
        future = connection.make_pending_call(call_id)
        try:
            await connection.send_json({
                "type": "tool_request",
                "call_id": call_id,
                "command": command,
                "args": args,
            })
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"ok": False, "result": None, "error": f"命令执行超时（{timeout:g} 秒）"}
        except Exception as exc:
            return {"ok": False, "result": None, "error": f"命令下发失败：{exc}"}
        finally:
            connection._pending_calls.pop(call_id, None)
            if not future.done():
                future.cancel()


# 进程内单例：全局共享的助手连接与工具桥接中枢。
hub = AssistantHub()


# —————————————————————————————————————————————
# 大模型客户端、工具定义与系统提示词
# —————————————————————————————————————————————

def create_openai_client(api_key: str, base_url: Optional[str] = None) -> Any:
    """用**前端提供的** API Key / 地址构造 OpenAI 客户端（后端不读环境变量、不做默认）。

    参数：
        api_key：前端「模型设置」里填写的 API Key（每条消息上送，仅用于本次调用）。
        base_url：可选，兼容 OpenAI 的自定义 API 地址；留空则用 SDK 默认地址。

    返回：一个可用于发起对话 / 工具调用循环的 OpenAI 客户端实例。
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 OpenAI SDK，请先安装 openai 包") from exc
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def command_specs() -> list[dict[str, Any]]:
    """返回全部命令的规格清单——「命令」的唯一事实来源（single source of truth）。

    build_command_tools（给大模型的工具定义）与 build_help_text（给用户看的帮助文本）都从
    这里派生，确保新增/修改命令时两处自动同步、不会漂移。

    每个元素描述一条命令，建议字段：
        name       命令名（动词），如 "add_node" / "connect_nodes" / "help"
        category   分类，如 "read"（只读，用于答疑）/ "write"（操作画布）/ "meta"（元命令）
        summary    一句话说明该命令做什么
        params     参数列表，每项含 name（参数名）、type（类型）、required（是否必填）、
                   desc（含义），可选 default（默认值）
        usage      用法示例字符串，如 "add Conv2D --out_channels 16"
        runs_on    执行位置："browser"（需在浏览器实时画布上执行）或
                   "backend"（后端本地直接应答，如 help）

    返回：命令规格字典的列表。
    """
    def p(name: str, type_: str, desc: str, required: bool = True, default: Any = None) -> dict[str, Any]:
        item = {"name": name, "type": type_, "required": required, "desc": desc}
        if default is not None:
            item["default"] = default
        return item

    return [
        {"name": "get_model_graph", "category": "read", "summary": "获取当前画布的完整模型图。", "params": [], "usage": "get_model_graph", "runs_on": "browser"},
        {"name": "list_nodes", "category": "read", "summary": "列出画布中的全部节点。", "params": [], "usage": "list_nodes", "runs_on": "browser"},
        {"name": "list_canvases", "category": "read", "summary": "列出全部画布（第几个 index / 名称 name / 节点数 / 是否当前焦点），用于定位某个画布。", "params": [], "usage": "list_canvases", "runs_on": "browser"},
        {"name": "get_canvas_graph", "category": "read", "summary": "读取指定画布的模型图与各层维度（不改变用户当前焦点）。用 index / name / id 之一定位。", "params": [p("index", "integer", "第几个画布（从 1 开始）", False), p("name", "string", "画布名称", False), p("id", "integer", "画布 id", False)], "usage": "get_canvas_graph --index 2", "runs_on": "browser"},
        {"name": "get_shapes", "category": "read", "summary": "获取各层推导出的输入和输出维度。", "params": [], "usage": "get_shapes", "runs_on": "browser"},
        {"name": "validate_model", "category": "read", "summary": "校验当前模型结构并返回错误和警告。", "params": [], "usage": "validate_model", "runs_on": "browser"},
        {"name": "list_templates", "category": "read", "summary": "列出可用的内置模型模板。", "params": [], "usage": "list_templates", "runs_on": "browser"},
        {"name": "get_train_config", "category": "read", "summary": "获取当前训练配置（数据集/轮次/批大小/学习率/优化器/损失/设备）。", "params": [], "usage": "get_train_config", "runs_on": "browser"},
        {"name": "get_training_result", "category": "read", "summary": "获取当前/最近一次训练的结果与逐轮指标（准确率、损失、进度、报错等），用于就训练结果答疑。", "params": [], "usage": "get_training_result", "runs_on": "browser"},
        {"name": "get_system_status", "category": "read", "summary": "查看系统实时状态：本机 Agent 是否连接、设备(CPU/GPU)与 CUDA、存储目录、当前画布等。", "params": [], "usage": "get_system_status", "runs_on": "browser"},
        {"name": "load_template", "category": "write", "summary": "将内置模板载入当前画布（会替换当前模型）。", "params": [p("key", "string", "模板键，如 lenet")], "usage": "load_template --key lenet", "runs_on": "browser"},
        {"name": "add_node", "category": "write", "summary": "新增一个层节点。", "params": [p("type", "string", "层类型，如 Conv2D"), p("params", "object", "层参数", False, {})], "usage": "add_node --type Conv2D --params '{\"out_channels\":16}'", "runs_on": "browser"},
        {"name": "connect_nodes", "category": "write", "summary": "连接两个节点。", "params": [p("source", "string", "源节点 id"), p("target", "string", "目标节点 id")], "usage": "connect_nodes --source node_1 --target node_2", "runs_on": "browser"},
        {"name": "set_param", "category": "write", "summary": "修改节点的一个参数。", "params": [p("node_id", "string", "节点 id"), p("name", "string", "参数名"), p("value", "any", "参数值")], "usage": "set_param --node_id node_1 --name out_channels --value 32", "runs_on": "browser"},
        {"name": "delete_node", "category": "write", "summary": "删除节点及其相关连线。", "params": [p("node_id", "string", "节点 id")], "usage": "delete_node --node_id node_1", "runs_on": "browser"},
        {"name": "set_dataset", "category": "write", "summary": "切换训练数据集（会自动把 Input 层维度同步为该数据集的形状）。", "params": [p("name", "string", "数据集名，如 MNIST / FashionMNIST / CIFAR10")], "usage": "set_dataset --name FashionMNIST", "runs_on": "browser"},
        {"name": "set_train_config", "category": "write", "summary": "修改训练超参数（可设 epochs/batch_size/rate/optimizer/loss_fn/device 中任意项）。", "params": [p("epochs", "integer", "训练轮次 1~100", False), p("batch_size", "integer", "批大小，正整数", False), p("rate", "number", "学习率，正数", False), p("optimizer", "string", "优化器：sgd/adam/adamw/rmsprop/adagrad/adadelta", False), p("loss_fn", "string", "损失：cross_entropy/nll/mse/l1/smooth_l1", False), p("device", "string", "设备：cpu 或 cuda", False)], "usage": "set_train_config --epochs 10 --optimizer adam", "runs_on": "browser"},
        {"name": "stop_training", "category": "write", "summary": "停止当前正在进行的训练任务。", "params": [], "usage": "stop_training", "runs_on": "browser"},
        {"name": "auto_layout", "category": "write", "summary": "自动整理画布节点布局。", "params": [], "usage": "auto_layout", "runs_on": "browser"},
        {"name": "export_code", "category": "read", "summary": "把当前模型导出为 PyTorch 代码。", "params": [], "usage": "export_code", "runs_on": "browser"},
        {"name": "start_training", "category": "write", "summary": "使用当前配置发起训练，需要本机 Agent 在线。", "params": [p("config", "object", "可选的训练配置覆盖项", False, {})], "usage": "start_training --config '{\"epochs\":10}'", "runs_on": "browser"},
        {"name": "help", "category": "meta", "summary": "显示全部命令、参数和用法。", "params": [], "usage": "help", "runs_on": "backend"},
    ]


def build_command_tools() -> list[dict[str, Any]]:
    """构造并返回提供给大模型的「命令工具」清单（工具即页内命令，读写皆有）。

    实现时应遍历 command_specs() 的每条命令，把它转换成大模型可用的工具定义
    （OpenAI 的 type/function/parameters 格式，其中 parameters 由 params 生成）。
    下面的分组列表只是示意其覆盖范围，真正的清单以 command_specs() 为准。

    每个工具的 function 包含 name / description / parameters，让模型知道有哪些命令、
    分别做什么、需要哪些参数。模型据此自主决定调用哪个命令。建议至少包含：

      读（了解当前项目，用于答疑）：
        - get_model_graph   取当前画布的模型图（层与连接）
        - list_nodes        列出当前所有节点及其类型/标题/id
        - get_shapes        获取各层推导出的输出维度
        - validate_model    对当前模型做结构校验，返回 valid/errors/warnings
        - list_templates    列出可用的内置模板
      写（像用户一样操作，用于建模/改模）：
        - load_template     一键载入某个模板（如 lenet）
        - add_node          新增一个层节点（type、可选参数）
        - connect_nodes     连接两个节点（source、target）
        - set_param         修改某节点的某个参数
        - delete_node       删除某节点（及其相关连线）
        - auto_layout       自动排版
        - export_code       导出为 PyTorch 代码
        - start_training    发起训练（需本机 Agent 在线）
      辅助 / 元命令：
        - help              显示所有命令及其用法（见 build_help_text）；无参数，
                            供用户在命令栏查阅，也便于模型向用户说明「能做什么」

    返回：工具定义列表，直接作为大模型请求里的 tools 传入。
    """
    type_map: dict[str, dict[str, Any]] = {
        "string": {"type": "string"}, "integer": {"type": "integer"},
        "number": {"type": "number"}, "boolean": {"type": "boolean"},
        "object": {"type": "object"}, "array": {"type": "array"},
        "any": {},
    }
    tools = []
    for spec in command_specs():
        properties: dict[str, Any] = {}
        required = []
        for param in spec["params"]:
            schema = dict(type_map.get(param["type"], {}))
            schema["description"] = param["desc"]
            if "default" in param:
                schema["default"] = param["default"]
            properties[param["name"]] = schema
            if param.get("required", False):
                required.append(param["name"])
        tools.append({"type": "function", "function": {
            "name": spec["name"],
            "description": f"[{spec['category']}] {spec['summary']} 用法：{spec['usage']}",
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        }})
    return tools


def build_help_text() -> str:
    """生成「所有命令及其用法」的帮助文本，供 help 命令展示。

    实现时应遍历 command_specs()（与 build_command_tools 同一份唯一源），逐条列出：命令名、
    参数（名称 / 含义 / 是否必填）、一句话说明，以及用法示例（如 `add Conv2D --out_channels 16`）。
    人类用户在命令栏输入 help 时展示它；也可放进系统提示，让模型准确地向用户介绍可用能力。

    返回：格式化好的多行帮助字符串（命令栏 / 聊天面板可直接展示）。
    """
    category_names = {"read": "只读命令", "write": "画布操作", "meta": "帮助"}
    lines = ["模型工坊可用命令"]
    specs = command_specs()
    for category in ("read", "write", "meta"):
        lines.extend(["", f"【{category_names[category]}】"])
        for spec in (s for s in specs if s["category"] == category):
            lines.append(f"- {spec['name']}：{spec['summary']}")
            for param in spec["params"]:
                flag = "必填" if param.get("required") else f"可选，默认 {param.get('default')!r}"
                lines.append(f"  {param['name']} ({param['type']}，{flag})：{param['desc']}")
            lines.append(f"  用法：{spec['usage']}")
    return "\n".join(lines)


def build_system_prompt(project_summary: Optional[str] = None) -> str:
    """构造系统提示词，设定助手身份、可用命令与行为准则。

    应说明：你是「模型工坊」平台内的 AI 助手；可以通过给定的命令工具，在用户的实时画布上
    查看和搭建模型；回答建模概念时用通俗、面向初学者的语言；执行写操作前后简要说明你做了
    什么；只在需要时才调用命令；破坏性操作（删除等）要谨慎。

    参数：
        project_summary：可选，当前项目状态的简要文字（见 summarize_project_snapshot）。
            若提供，则一并放进系统提示，减少模型为「摸清现状」而反复调用只读命令的往返。

    返回：拼装好的系统提示词字符串。
    """
    template = _load_prompt_template()
    prompt = template.replace("{{COMMAND_LIST}}", build_help_text()).rstrip()
    if project_summary:
        prompt += f"\n\n# 当前项目概况\n{project_summary.strip()}"
    return prompt


# 系统提示词模板文件（静态部分抽离到此，便于维护、无需改代码）。
_PROMPT_TEMPLATE_FILE = Path(__file__).resolve().parent / "prompts" / "system_prompt.md"
# 读文件失败时的兜底提示（极简，保证服务不崩）。
_FALLBACK_PROMPT = (
    "你是“模型工坊”平台内的 AI 助手，可调用命令工具在用户实时画布上查看/搭建/校验模型，"
    "用通俗中文向初学者解释。一切以工具返回结果为准，绝不臆造；只在需要时调用工具。\n\n"
    "# 可用命令清单\n{{COMMAND_LIST}}"
)


def _load_prompt_template() -> str:
    """读取系统提示词模板（含 {{COMMAND_LIST}} 占位符）；读不到时回退到内置兜底文本。

    每次调用都重新读文件，便于直接改 system_prompt.md 后即时生效、无需重启服务。
    """
    try:
        return _PROMPT_TEMPLATE_FILE.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_PROMPT


def summarize_project_snapshot(snapshot: dict[str, Any]) -> str:
    """把当前项目的结构化快照压成简短、可放进上下文的自然语言描述。

    参数：
        snapshot：前端随对话一起上送的当前项目快照，通常含模型图（layers/connections）、
            最近一次校验结果、数据集/设备/轮次等训练配置。

    返回：对该项目的一段精简描述（如「当前是一个 6 层 CNN：Input→Conv2D→…→Output，
        结构校验通过」），用于喂给模型做背景，降低工具往返次数。
    """
    if not snapshot:
        return "当前项目没有可用快照。"
    graph = snapshot.get("model_graph") or snapshot.get("model") or snapshot.get("graph") or snapshot
    layers = graph.get("layers") or graph.get("nodes") or [] if isinstance(graph, Mapping) else []
    connections = graph.get("connections") or graph.get("edges") or [] if isinstance(graph, Mapping) else []
    names = []
    for layer in layers:
        if isinstance(layer, Mapping):
            names.append(str(layer.get("type") or layer.get("title") or layer.get("name") or layer.get("id") or "未知层"))
    chain = " → ".join(names[:12])
    if len(names) > 12:
        chain += f" → …（另 {len(names) - 12} 层）"
    validation = snapshot.get("validation") or snapshot.get("validation_result")
    status_text = ""
    if isinstance(validation, Mapping):
        valid = validation.get("valid")
        errors = validation.get("errors") or []
        warnings = validation.get("warnings") or []
        status_text = f"；结构校验{'通过' if valid else '未通过' if valid is False else '状态未知'}，{len(errors)} 个错误、{len(warnings)} 个警告"
    training = snapshot.get("training") or snapshot.get("training_config") or {}
    training_bits = []
    if isinstance(training, Mapping):
        for key, label in (("dataset", "数据集"), ("device", "设备"), ("epochs", "轮次")):
            if training.get(key) is not None:
                training_bits.append(f"{label}={training[key]}")
    training_text = f"；训练配置：{', '.join(training_bits)}" if training_bits else ""
    structure = f"：{chain}" if chain else ""
    return f"当前模型有 {len(layers)} 个层、{len(connections)} 条连接{structure}{status_text}{training_text}。"


# —————————————————————————————————————————————
# 对话主循环（工具调用编排）
# —————————————————————————————————————————————

async def handle_tool_use(
    user_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """处理大模型的一次工具调用：把它翻译成命令、交浏览器执行、取回结果。

    这是 Tool Runner / 工具循环里每个工具的统一执行函数——多数命令要在浏览器的实时画布上
    执行，所以主要是「工具名/参数 → command/args」的映射 + 调用 hub.execute_command_in_browser。
    少数「元命令 / 纯静态」命令（如 help，直接返回 build_help_text() 的结果）可在**后端本地**
    直接应答，无需浏览器往返——在此按命令名分流即可。

    参数：
        user_id：当前对话所属用户 id。
        tool_name：模型请求调用的工具名（来自 build_command_tools 中的 name）。
        tool_input：模型给出的工具参数（已按 parameters schema 校验）。

    返回：该命令的执行结果字典（含 ok / result / error），将作为 tool_result 回传给模型。
    """
    spec = next((item for item in command_specs() if item["name"] == tool_name), None)
    if spec is None:
        return {"ok": False, "result": None, "error": f"未知命令：{tool_name}"}
    if spec["runs_on"] == "backend":
        if tool_name == "help":
            return {"ok": True, "result": build_help_text(), "error": None}
        return {"ok": False, "result": None, "error": f"后端命令未实现：{tool_name}"}
    return await hub.execute_command_in_browser(user_id, tool_name, dict(tool_input or {}))


async def _stream_model_round(
    connection: "AssistantConnection",
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """跑一轮大模型（流式），边收边把正文增量经 WebSocket 推给浏览器。

    返回 (完整正文, 工具调用列表)；工具调用形如 {"id","name","arguments"}。正文通过
    多条 {"type":"assistant_delta","text": 片段} 实时下发，前端逐段追加显示。
    若流式在**尚未产出任何内容前**就失败，则自动退回非流式调用，保证可用。
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    def produce() -> None:
        try:
            stream = client.chat.completions.create(
                model=model, messages=messages, tools=tools,
                tool_choice="auto", stream=True,
            )
            for chunk in stream:
                loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
        except Exception as exc:  # 交由主协程决定：退回非流式或抛出
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    loop.run_in_executor(None, produce)

    content_parts: list[str] = []
    tool_slots: dict[int, dict[str, Any]] = {}
    streamed_any = False
    error: Optional[BaseException] = None

    while True:
        kind, payload = await queue.get()
        if kind == "done":
            break
        if kind == "error":
            error = payload
            continue
        choices = getattr(payload, "choices", None) or []
        if not choices:
            continue
        delta = choices[0].delta
        piece = getattr(delta, "content", None)
        if piece:
            content_parts.append(piece)
            streamed_any = True
            await connection.send_json({"type": "assistant_delta", "text": piece})
        for tc in (getattr(delta, "tool_calls", None) or []):
            slot = tool_slots.setdefault(tc.index, {"id": None, "name": None, "arguments": ""})
            if tc.id:
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if fn.name:
                    slot["name"] = fn.name
                if fn.arguments:
                    slot["arguments"] += fn.arguments

    if error is not None and not streamed_any and not tool_slots:
        # 流式在产出任何内容前失败：退回一次非流式调用（兼容不支持 stream 的接口）
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model, messages=messages, tools=tools, tool_choice="auto",
        )
        msg = response.choices[0].message
        content = msg.content or ""
        if content:
            await connection.send_json({"type": "assistant_delta", "text": content})
        calls = [
            {"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
            for c in (msg.tool_calls or [])
        ]
        return content, calls

    if error is not None:
        raise error

    calls = []
    for idx in sorted(tool_slots):
        slot = tool_slots[idx]
        calls.append({"id": slot["id"], "name": slot["name"], "arguments": slot["arguments"] or "{}"})
    return "".join(content_parts), calls


async def run_assistant_turn(
    connection: AssistantConnection,
    user_message: str,
    history: list[dict[str, Any]],
    project_summary: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    """跑完一轮对话：用户提问 →（模型多次调用命令并取回结果）→ 模型给出最终回答。

    内部驱动大模型的工具调用循环：把系统提示 + 历史 + 本次用户消息 + 工具清单发给模型；
    每当模型请求调用命令，就用 handle_tool_use 执行并把结果回传模型；循环直到模型不再调用
    命令、产出最终自然语言回答（可在过程中通过 connection 向浏览器流式推送中间/最终文本）。

    参数：
        connection：当前用户的聊天连接（用于下发命令与推送助手回复）。
        user_message：用户本轮输入的自然语言。
        history：既往对话消息列表（用户/助手轮次），用于给模型上下文；本轮结束后应把
            本次问答追加进去以维持多轮记忆。
        project_summary：可选的当前项目简述（见 build_system_prompt 的同名参数）。
        model：**前端**提供的模型名（必填，来自「模型设置」）。为空时直接提示用户去填写。
        api_key：**前端**提供的 API Key（必填）。为空时直接提示用户去填写。
        base_url：可选，前端提供的自定义 API 地址；留空用默认。

    返回：模型本轮的最终自然语言回答文本（也已经/将要通过 connection 推送给前端）。
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("用户消息不能为空")

    # 模型名 / 密钥 / API 地址一律来自前端，均必填；缺任一则提示用户去填写，不发起调用
    model = (model or "").strip()
    api_key = (api_key or "").strip()
    base_url = (base_url or "").strip()
    if not model or not api_key or not base_url:
        hint = "还没配置模型。请点开 AI 助手右上角的齿轮，填写「模型名」「模型 API Key」和「API 地址」后再试。"
        await connection.send_json({"type": "assistant_message", "text": hint, "final": True})
        return hint

    client = create_openai_client(api_key, base_url)
    messages = [{"role": "system", "content": build_system_prompt(project_summary)}]
    messages.extend(dict(item) for item in history)
    messages.append({"role": "user", "content": user_message.strip()})
    final_text = ""

    tools = build_command_tools()
    for _ in range(MAX_TOOL_ITERATIONS + 1):
        content, tool_calls = await _stream_model_round(connection, client, model, messages, tools)

        serialized_calls = [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
            for c in tool_calls
        ]
        assistant_entry: dict[str, Any] = {"role": "assistant", "content": content}
        if serialized_calls:
            assistant_entry["tool_calls"] = serialized_calls
        messages.append(assistant_entry)

        if not tool_calls:
            final_text = content or "抱歉，我没有生成有效回复。"
            # 正文已通过 assistant_delta 流式送达；这里只发结束信号（无正文时补发兜底文本）
            await connection.send_json({
                "type": "assistant_message",
                "text": "" if content else final_text,
                "final": True,
            })
            break

        if _ >= MAX_TOOL_ITERATIONS:
            final_text = f"本轮已达到最多 {MAX_TOOL_ITERATIONS} 次工具调用，为避免循环已停止。"
            await connection.send_json({"type": "assistant_message", "text": final_text, "final": True})
            break

        for call in tool_calls:
            try:
                parsed = json.loads(call["arguments"] or "{}")
                if not isinstance(parsed, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
                result = await handle_tool_use(connection.user_id, call["name"], parsed)
            except (json.JSONDecodeError, ValueError) as exc:
                result = {"ok": False, "result": None, "error": f"工具参数无效：{exc}"}
            except Exception as exc:
                result = {"ok": False, "result": None, "error": f"工具执行异常：{exc}"}
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    history.extend([
        {"role": "user", "content": user_message.strip()},
        {"role": "assistant", "content": final_text},
    ])

    # 回答完毕后，再生成 3 个用户可能想继续问的问题，供前端点选。
    # 始终下发一条 suggestions（哪怕为空），以便前端清掉「生成中…」占位。
    suggestions: list[str] = []
    try:
        convo = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str) and m["content"].strip()
        ]
        suggestions = await generate_followups(client, model, convo[-4:])
    except Exception:
        suggestions = []
    try:
        await connection.send_json({"type": "suggestions", "items": suggestions})
    except Exception:
        pass

    return final_text


async def generate_followups(client: Any, model: str, convo: list[dict[str, Any]]) -> list[str]:
    """根据对话，站在用户角度生成 3 个可能的后续追问（供前端展示为可点选项）。

    参数：
        client / model：与主对话相同的大模型客户端与模型名（前端 BYO-key）。
        convo：最近若干轮 user/assistant 文本消息，用作生成上下文。

    返回：至多 3 条简短中文追问；无法生成或解析失败时返回空列表（不影响主流程）。
    """
    if not convo:
        return []
    system = (
        "你是“追问建议器”。根据下面的对话，站在用户角度，给出 3 个用户接下来最可能想问的问题。"
        "要求：中文；每个不超过 20 字；具体、可直接发送；紧扣当前模型/训练场景；不要重复已经问过的。"
        "只输出一个 JSON 字符串数组，例如 [\"问题一\",\"问题二\",\"问题三\"]，不要输出任何多余文字、解释或代码块以外的内容。"
    )
    chat_messages = [{"role": "system", "content": system}, *convo]
    # 先带 temperature/max_tokens；若模型拒绝这些参数（常见于推理模型）或返回空，
    # 再退回“极简调用”（只给 model+messages，与主回答一致）重试一遍。
    variants = [{"temperature": 0.8, "max_tokens": 200}, {}]
    for extra in variants:
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=chat_messages,
                **extra,
            )
            text = response.choices[0].message.content or ""
            parsed = _parse_followups(text)
            print(f"[followups] extra={extra} raw={text[:120]!r} parsed={parsed}", flush=True)
            if parsed:
                return parsed
        except Exception as exc:
            print(f"[followups] extra={extra} error={exc!r}", flush=True)
            continue
    return []


def _parse_followups(text: str) -> list[str]:
    """从模型回复中尽量稳健地解析出最多 3 条追问。

    容忍多种非严格输出：代码块包裹、数组前后夹带说明文字、被截断的 JSON、
    以及“1. …/ - …/ 、…”这类编号或项目符号列表（含中文标点）。解析不出则返回空列表。
    """
    if not text or not text.strip():
        return []
    cleaned = text.replace("```", " ").strip()

    # 1) 优先抓取一个 JSON 字符串数组（允许前后有多余文字）
    match = re.search(r"\[[^\[\]]*\]", cleaned, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                items = [str(x).strip().strip("\"'“”‘’") for x in data]
                items = [x for x in items if x]
                if items:
                    return items[:3]
        except Exception:
            pass

    # 2) 退回按行拆：去掉编号/项目符号/引号，取非空行
    lines: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip()
        line = re.sub(r'^[\s\-*·•\d\.\)、,，。："“”‘’\'\[\]]+', "", line).strip()
        line = line.strip("\"'“”‘’，。").strip()
        if len(line) >= 2:
            lines.append(line)
    return lines[:3]


# —————————————————————————————————————————————
# 认证与 WebSocket 入口
# —————————————————————————————————————————————

def verify_assistant_token(token: str) -> str:
    """校验聊天连接携带的 JWT 令牌，返回其对应的用户 id。

    参数：
        token：前端建立 WebSocket 时带上的登录令牌（查询参数或首帧消息）。

    返回：令牌有效时返回 user_id（后续所有命令都在该用户名下、在其画布上执行）；
        无效时应抛出异常，由入口据此拒绝连接（关闭 WebSocket）。
    """
    if not token or not isinstance(token, str):
        raise ValueError("缺少登录令牌")
    from .auth import get_user
    from .security import verify_access_token

    payload = verify_access_token(token)
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id or get_user(user_id) is None:
        raise ValueError("令牌对应的用户不存在")
    return user_id


@router.websocket("/assistant/ws")
async def assistant_ws(websocket: WebSocket, token: str) -> None:
    """浏览器聊天面板的 WebSocket 入口：接入连接、路由消息、驱动对话。

    职责：
      1. 用 token 校验登录（verify_assistant_token），通过则 accept、注册到 hub；
      2. 循环收前端消息：
         - user_message → 调 run_assistant_turn 跑一轮对话（其间会下发 tool_request）；
         - tool_result  → 调 connection.resolve_pending_call 兑现对应命令的结果；
      3. 断开时从 hub 注销并清理挂起调用。

    参数：
        websocket：FastAPI 注入的 WebSocket 连接。
        token：查询参数里的登录令牌（浏览器下载/连接无法带请求头，故用查询参数传递）。

    返回：无（长连接，直到客户端断开或校验失败）。
    """
    try:
        user_id = verify_assistant_token(token)
    except Exception:
        await websocket.close(code=1008, reason="登录令牌无效或已过期")
        return

    await websocket.accept()
    connection = AssistantConnection(user_id, websocket)
    hub.register(user_id, connection)
    history: list[dict[str, Any]] = []
    turn_task: Optional[asyncio.Task[str]] = None

    async def run_turn(text: str, summary: Optional[str], cfg: dict[str, Any]) -> str:
        try:
            return await run_assistant_turn(
                connection, text, history, summary,
                model=cfg.get("model"),
                api_key=cfg.get("api_key"),
                base_url=cfg.get("base_url"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            message = f"助手处理失败：{exc}"
            await connection.send_json({"type": "assistant_message", "text": message, "final": True})
            return message

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "tool_result":
                call_id = message.get("call_id")
                if isinstance(call_id, str):
                    connection.resolve_pending_call(call_id, {
                        "ok": bool(message.get("ok", False)),
                        "result": message.get("result"),
                        "error": message.get("error"),
                    })
            elif message_type == "user_message":
                text = message.get("text")
                if not isinstance(text, str) or not text.strip():
                    await connection.send_json({"type": "assistant_message", "text": "消息不能为空。", "final": True})
                    continue
                if turn_task is not None and not turn_task.done():
                    await connection.send_json({"type": "assistant_message", "text": "上一条消息仍在处理中，请稍候。", "final": True})
                    continue
                summary = message.get("project_summary")
                if summary is None and isinstance(message.get("snapshot"), dict):
                    summary = summarize_project_snapshot(message["snapshot"])
                cfg = {
                    "model": message.get("model"),
                    "api_key": message.get("api_key"),
                    "base_url": message.get("base_url"),
                }
                turn_task = asyncio.create_task(
                    run_turn(text, summary if isinstance(summary, str) else None, cfg)
                )
            else:
                await connection.send_json({"type": "assistant_message", "text": f"不支持的消息类型：{message_type}", "final": True})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.unregister(user_id, connection)
        if turn_task is not None and not turn_task.done():
            turn_task.cancel()
            await asyncio.gather(turn_task, return_exceptions=True)
