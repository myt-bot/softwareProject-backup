"""本机 Agent 连接云端服务器的 WebSocket 客户端。

Agent 主动连接云端，注册为某用户的在线训练节点，接收云端下发的训练
指令，在本机用 PyTorch 执行训练，并把进度与最终结果实时回传给云端。
真正的训练循环运行在本机 runtime（local_agent.runtime.trainer）中。
"""

import asyncio
import json
import platform
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import websockets

from .runtime import trainer as runtime_trainer
from .runtime.device import get_device_summary


# —————————————————————————————————————————————
# Agent 运行态（单进程内单连接）
# —————————————————————————————————————————————

class AgentState:
    def __init__(self):
        self.websocket: Optional[Any] = None
        self.agent_id: str = ""
        self.runtime_version: str = ""
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.send_lock = asyncio.Lock()
        # 云端 job_id -> 本机 runtime job_id
        self.job_map: dict[str, str] = {}
        self.cancelled: set[str] = set()


state = AgentState()

# 与云端 backend.cloud_training.AGENT_REPLACED_CLOSE_CODE 保持一致。收到该关闭码
# 表示同账号已有更新的 Agent 会话，当前实例应停止重连，避免两个实例反复互相覆盖。
AGENT_REPLACED_CLOSE_CODE = 4001


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_agent_hello_message(
    agent_id: str,
    auth_token: str,
    runtime_version: str,
    device_summary: dict[str, Any],
) -> dict[str, Any]:
    """构造 Agent 连接云端后的首条注册消息。

    令牌通过 WebSocket 握手 URL 的查询参数传递，因此 hello 消息里不再
    重复携带敏感 token。
    """
    return {
        "type": "hello",
        "agent_id": agent_id,
        "runtime_version": runtime_version,
        "device_summary": device_summary,
        "platform": f"{platform.system()} {platform.release()}",
        "sent_at": _now_iso(),
    }


async def _send(message: dict[str, Any]) -> None:
    """通过当前活跃连接发送一条消息（串行化，避免并发写交错）。"""
    if state.websocket is None:
        return
    async with state.send_lock:
        await state.websocket.send(json.dumps(message))


def send_training_update(job_id: str, status: str, payload: dict[str, Any]) -> None:
    """向云端服务器发送训练进度或最终结果（线程安全，跨线程投递到事件循环）。

    训练循环运行在独立线程中，这里把发送协程调度回 Agent 的事件循环。
    """
    message = {"job_id": job_id, "status": status, **payload}
    loop = state.loop
    if loop is None:
        return
    asyncio.run_coroutine_threadsafe(_send(message), loop)


def handle_cloud_command(command: dict[str, Any]) -> dict[str, Any]:
    """处理云端服务器下发的指令，返回是否接受及回执数据。"""
    cmd_type = command.get("type")

    if cmd_type == "start_training":
        job_id = command.get("job_id", "")
        model_graph = command.get("model", {})
        train_config = command.get("train_config", {})
        return start_local_training_job(job_id, model_graph, train_config)

    if cmd_type == "cancel_training":
        job_id = command.get("job_id", "")
        local_job_id = state.job_map.get(job_id)
        state.cancelled.add(job_id)
        if local_job_id:
            try:
                runtime_trainer.stop_training_job(local_job_id)
            except Exception:
                pass
        return {"type": "command_ack", "job_id": job_id, "command": "cancel_training", "accepted": True, "message": "已请求停止本机训练"}

    if cmd_type == "agent_request":
        return _handle_agent_request(command)

    if cmd_type == "ping":
        return {"type": "pong"}

    return {"type": "command_ack", "command": cmd_type, "accepted": False, "message": f"未知指令：{cmd_type}"}


def _handle_agent_request(command: dict[str, Any]) -> dict[str, Any]:
    """处理云端转发的请求-响应类指令（结构校验 / 设备查询 / 代码导出）。"""
    request_id = command.get("request_id", "")
    action = command.get("action")
    payload = command.get("payload", {}) or {}

    def ok(data: Any) -> dict[str, Any]:
        return {"type": "agent_response", "request_id": request_id, "ok": True, "data": data}

    def fail(error: str) -> dict[str, Any]:
        return {"type": "agent_response", "request_id": request_id, "ok": False, "error": error}

    try:
        if action == "validate":
            from .runtime.validator import validate_model_graph
            return ok(validate_model_graph(payload.get("model", {})))

        if action == "devices":
            return ok(get_device_summary())

        if action == "export":
            from .runtime.code_exporter import export_model_code, generate_requirements
            export_format = (payload.get("format", "py") or "py").lower()
            class_name = payload.get("class_name", "GeneratedModel")
            code = export_model_code(
                payload.get("model", {}),
                class_name=class_name,
                export_format=export_format,
                train_config=payload.get("train_config"),
            )
            if not code:
                return fail("本机训练运行时暂未实现代码导出。")
            suffix = "ipynb" if export_format == "ipynb" else "py"
            # 依赖清单一并返回；由前端把代码与 requirements.txt 打包成 zip 下载，
            # 这样无需重新分发本机 Agent 即可生效。
            return ok({
                "code": code,
                "format": suffix,
                "filename": f"{class_name}.{suffix}",
                "requirements": generate_requirements(export_format),
            })

        if action == "list_dir":
            return ok(_list_directory(payload.get("path")))

        return fail(f"未知请求：{action}")
    except Exception as exc:
        return fail(str(exc))


_DRIVES_ROOT = "__drives__"   # “此电脑”视图的特殊路径：列出所有盘符


def _list_drives() -> list[dict[str, Any]]:
    """列出本机所有可用盘符（Windows）或根目录（*nix）。"""
    import os
    import string

    if os.name == "nt":
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append({"name": f"{letter}: 盘", "path": root, "kind": "drive"})
        return drives
    return [{"name": "/", "path": "/", "kind": "drive"}]


def _list_directory(path: Optional[str]) -> dict[str, Any]:
    """列出本机某目录下的子目录，供前端浏览选择存储位置。

    支持“此电脑”视图（path == "__drives__"）以在不同盘符间切换；从盘根再向上会
    回到该视图，从而可以选择 C 盘以外的其它盘。
    """
    import os

    # “此电脑”：列出所有盘符
    if path == _DRIVES_ROOT:
        return {
            "path": _DRIVES_ROOT,
            "display": "此电脑",
            "is_root": True,
            "parent": None,
            "entries": _list_drives(),
        }

    base = os.path.expanduser(path) if path else os.path.expanduser("~")
    base = os.path.abspath(base)
    if not os.path.isdir(base):
        base = os.path.expanduser("~")

    entries = []
    try:
        for name in sorted(os.listdir(base), key=str.lower):
            if name.startswith("."):
                continue  # 隐藏以点开头的目录，界面更清爽
            full = os.path.join(base, name)
            if os.path.isdir(full):
                entries.append({"name": name, "path": full, "kind": "dir"})
    except PermissionError:
        pass

    parent = os.path.dirname(base)
    if parent == base:
        # 已到盘根（Windows: C:\）或文件系统根：向上回到“此电脑”以便切换其它盘符
        parent = _DRIVES_ROOT if os.name == "nt" else None

    return {
        "path": base,
        "display": base,
        "is_root": False,
        "parent": parent,
        "entries": entries,
    }


def start_local_training_job(job_id: str, model_graph: dict[str, Any], train_config: dict[str, Any]) -> dict[str, Any]:
    """在用户本机启动 PyTorch 训练任务，并在后台线程流式上报进度。"""
    try:
        created = runtime_trainer.create_training_job(model_graph=model_graph, train_config=train_config)
    except Exception as exc:
        send_training_update(job_id, "failed", {"type": "training_result", "error": f"创建训练任务失败：{exc}"})
        return {"type": "command_ack", "job_id": job_id, "command": "start_training", "accepted": False, "message": str(exc)}

    local_job_id = created["job_id"]
    state.job_map[job_id] = local_job_id

    thread = threading.Thread(target=_run_and_stream, args=(job_id, local_job_id), daemon=True)
    thread.start()

    return {
        "type": "command_ack",
        "job_id": job_id,
        "command": "start_training",
        "accepted": True,
        "local_job_id": local_job_id,
        "status": "running",
        "message": "本机已开始训练",
    }


def _run_and_stream(job_id: str, local_job_id: str) -> None:
    """在后台线程运行训练，并周期性把状态流式回传给云端。"""
    # 轮询线程：训练在另一线程阻塞执行，这里定时读取 runtime 任务状态并上报
    def poll_loop():
        last_signature = None
        while True:
            try:
                status = runtime_trainer.get_job_status(local_job_id)
            except Exception:
                break
            dataset_progress = status.get("dataset_progress") or {}
            signature = (
                status.get("status"),
                status.get("current_epoch"),
                status.get("current_step"),
                len(status.get("metrics", [])),
                dataset_progress.get("status"),
                dataset_progress.get("percent"),
                dataset_progress.get("downloaded_bytes"),
                dataset_progress.get("file_name"),
            )
            if signature != last_signature:
                last_signature = signature
                send_training_update(job_id, status.get("status", "running"), {
                    "type": "training_update",
                    "current_epoch": status.get("current_epoch", 0),
                    "total_epochs": status.get("total_epochs", 0),
                    "current_step": status.get("current_step", 0),
                    "total_steps": status.get("total_steps", 0),
                    "progress": status.get("progress", 0.0),
                    "metrics": status.get("metrics", []),
                    "dataset_progress": dataset_progress,
                })
            if status.get("status") in ("completed", "failed", "cancelled"):
                break
            time.sleep(0.8)

    poller = threading.Thread(target=poll_loop, daemon=True)
    poller.start()

    # 层高亮已改为前端按拓扑顺序、可感知节奏地自行推进（见前端 startLayerSweep）。
    # Agent 不再对「每个 batch 的每一层」发送 layer_pulse——原先 forward 每层每批都发一条，
    # 微秒级、量极大，会刷爆 WebSocket 且前端也已不再消费，故直接不发。

    # 在当前线程阻塞执行真实训练（PyTorch）
    try:
        runtime_trainer.run_training_job(local_job_id)
    except Exception:
        pass  # 失败状态由 trainer 写入任务，poll_loop 会读取并上报

    poller.join(timeout=5)

    # 汇总最终结果并回传
    try:
        result = runtime_trainer.get_job_result(local_job_id)
    except Exception as exc:
        send_training_update(job_id, "failed", {"type": "training_result", "error": str(exc)})
        return

    metrics = result.get("metrics", [])
    final = _summarize_metrics(metrics)
    send_training_update(job_id, result.get("status", "completed"), {
        "type": "training_result",
        "loss": final.get("loss"),
        "accuracy": final.get("accuracy"),
        "device": result.get("device"),
        "metrics": metrics,
        "artifacts": result.get("artifacts"),
        "dataset_progress": result.get("dataset_progress"),
        "error": result.get("error"),
    })


def _summarize_metrics(metrics: list) -> dict[str, Any]:
    """从逐轮指标里取最后一轮的验证 loss/accuracy 作为最终结果摘要。"""
    if not metrics:
        return {"loss": None, "accuracy": None}
    last = metrics[-1] or {}
    eval_m = last.get("eval") or {}
    return {"loss": eval_m.get("loss"), "accuracy": eval_m.get("accuracy")}


async def connect_to_cloud_server(
    server_url: str,
    auth_token: str,
    agent_id: Optional[str] = None,
    runtime_version: Optional[str] = None,
) -> None:
    """连接云端 WebSocket 服务并持续运行（断线自动重连）。

    参数：
        server_url：云端 WebSocket 地址，例如 ws://127.0.0.1:8000。
        auth_token：绑定用户身份的 JWT 令牌。
        agent_id：本机 Agent 稳定 id，为空则自动生成。
        runtime_version：当前训练运行时版本。
    """
    state.agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
    state.runtime_version = runtime_version or ""
    state.loop = asyncio.get_running_loop()

    ws_base = server_url.rstrip("/")
    if ws_base.startswith("http://"):
        ws_base = "ws://" + ws_base[len("http://"):]
    elif ws_base.startswith("https://"):
        ws_base = "wss://" + ws_base[len("https://"):]
    ws_url = f"{ws_base}/agents/ws?token={auth_token}"

    device_summary = get_device_summary()

    while True:
        try:
            async with websockets.connect(ws_url, max_size=32 * 1024 * 1024) as websocket:
                state.websocket = websocket
                await _send(build_agent_hello_message(
                    agent_id=state.agent_id,
                    auth_token=auth_token,
                    runtime_version=state.runtime_version,
                    device_summary=device_summary,
                ))
                # 明确的连接成功标记（GUI 启动器据此显示"已连接"）
                print("[agent] CONNECTED 已成功连接云端。", flush=True)
                heartbeat = asyncio.create_task(_heartbeat_loop())
                try:
                    async for raw in websocket:
                        await _on_cloud_message(raw)
                finally:
                    heartbeat.cancel()
        except Exception as exc:
            if getattr(exc, "code", None) == AGENT_REPLACED_CLOSE_CODE:
                print("[agent] 当前连接已被同账号的新 Agent 会话替换，停止自动重连。", flush=True)
                return
            print(f"[agent] 与云端连接中断，将在 3 秒后重连：{exc}")
        finally:
            state.websocket = None
        await asyncio.sleep(3)


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(15)
        await _send({"type": "heartbeat", "sent_at": _now_iso()})


async def _on_cloud_message(raw: Any) -> None:
    """收到云端一条指令：分发处理并回传回执。"""
    try:
        command = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return
    if command.get("type") == "welcome":
        return
    response = handle_cloud_command(command)
    if response:
        await _send(response)
