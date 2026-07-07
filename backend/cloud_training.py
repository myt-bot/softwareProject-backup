"""云端训练任务调度与中转接口。

该模块只属于服务器部署。它负责创建训练任务、匹配用户在线的本机
Agent、通过 WebSocket 下发训练指令，并接收 Agent 回传的训练进度。
真正的 PyTorch 训练逻辑必须在用户本机 Agent 中执行。

拓扑：
    浏览器 <--(客户端 WebSocket /client/ws)--> 云端服务器
    云端服务器 <--(Agent WebSocket /agents/ws)--> 用户本机 Agent

云端只做「任务登记 + 指令转发 + 进度中转」，不执行任何 PyTorch 代码。
状态为进程内内存态（课设单进程部署），进程重启后训练任务不保留。
"""

import asyncio
import hashlib
import io
import json
import os
import py_compile
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from .schemas import CloudTrainRequest
from .security import verify_access_token


router = APIRouter(tags=["cloud-training"])

# 当前云端提供的训练运行时版本；Agent 据此判断是否需要下载/更新本机训练代码
RUNTIME_VERSION = "1.0.0"
MIN_AGENT_VERSION = "1.0.0"

# 本机训练运行时源码目录（打包后供 Agent 首次下载）
_RUNTIME_SOURCE_DIR = Path(__file__).resolve().parent.parent / "local_agent" / "runtime"
# 本机 Agent 完整源码目录（首次使用的用户可从云端下载整个 Agent 程序）
_AGENT_SOURCE_DIR = Path(__file__).resolve().parent.parent / "local_agent"

# 编译 .pyc 时使用的 Python 版本（打包成单文件应用时内置的独立 Python 应与之一致）
_PYC_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"

# 下载版应用的使用说明（随包附带）
_AGENT_README = """\
VisualDL 本机训练应用
======================

这是运行在你自己电脑上的训练程序。系统的训练在本机进行（可用 GPU 加速），
云端只负责界面、登录和任务中转。

首次打开会自动准备训练环境（创建一个专属虚拟环境并安装 PyTorch 等依赖，
首次较慢、只需一次），之后每次打开都会直接连接云端。已连接后，网页顶部会
显示「本机训练已连接」，即可进行结构校验、训练与代码导出。

—— 已打包为单文件应用（推荐）——
直接双击可执行文件（Windows 为 .exe、macOS 为 .app、Linux 为可执行文件）即可，
无需安装 Python。应用内已内置令牌，会自动绑定到你的账号并连接云端。

—— 用源码直接运行（开发/进阶）——
本包已内置令牌（config.json）。在含 launcher.py 的目录下执行：

       python launcher.py

即会自动创建虚拟环境、安装依赖并启动。（此方式需要本机已装 Python {py}。）

如何打包成单文件应用：见 build_app.md。

提示：本应用已绑定你的账号（config.json 内含登录令牌），请勿分享给他人。
"""

# 打包成单文件应用的构建说明（随包附带）
_BUILD_GUIDE = """\
把本应用打包成「用户双击即用、无需预装 Python」的单文件应用
=========================================================

思路：用一份「独立 Python」作为内置解释器，用 PyInstaller 把 launcher.py 冻结成
单文件可执行程序，并把 local_agent/（.pyc）与 config.json 一并打包进去。运行时
launcher 用内置的独立 Python 创建虚拟环境并安装依赖。

前提：本包内的 local_agent/*.pyc 是用 Python {py} 编译的，内置的独立 Python 必须
是同一小版本（{py}.x），否则 .pyc 无法被加载。

步骤（在与目标平台相同的系统上执行）：

1. 获取独立 Python {py}（例如 python-build-standalone 项目的发行版），解压到
   本目录下的 pybundle/。

2. 安装 PyInstaller：pip install pyinstaller

3. 打包（Windows 为例）：

       pyinstaller --onefile --name VisualDL-Agent \\
         --add-data "local_agent;local_agent" \\
         --add-data "config.json;." \\
         --add-binary "pybundle;pybundle" \\
         launcher.py

   （macOS/Linux 把 --add-data 的分隔符 ; 换成 :）

4. 产物在 dist/ 下。把它作为「本机训练应用」提供给用户下载即可。

注：不同平台需各自构建一次（Windows/macOS/Linux）。torch 不打进可执行文件，
而是首次运行时装进虚拟环境，因此可执行文件体积很小。
"""


# —————————————————————————————————————————————
# 进程内注册表：在线 Agent、浏览器客户端、训练任务
# —————————————————————————————————————————————

class AgentSession:
    """一个用户本机 Agent 的在线会话。"""

    def __init__(self, user_id: str, websocket: WebSocket):
        self.user_id = user_id
        self.websocket = websocket
        self.agent_id: str = ""
        self.runtime_version: str = ""
        self.platform: str = ""
        self.device_summary: dict[str, Any] = {}
        self.connected_at = time.time()
        self.last_heartbeat_at = time.time()
        self._send_lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self.websocket.send_json(message)

    def meta(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "runtime_version": self.runtime_version,
            "platform": self.platform,
            "device_summary": self.device_summary,
            "connected_at": self.connected_at,
            "last_heartbeat_at": self.last_heartbeat_at,
        }


class Registry:
    """在线 Agent、浏览器客户端与训练任务的进程内注册表。"""

    def __init__(self):
        # 每个用户同一时间只保留一个在线 Agent（后连接覆盖旧连接）
        self.agents: dict[str, AgentSession] = {}
        # 每个用户可有多个浏览器标签页同时在线
        self.clients: dict[str, set[WebSocket]] = {}
        # 训练任务记录（job_id -> record）
        self.jobs: dict[str, dict[str, Any]] = {}

    def add_client(self, user_id: str, websocket: WebSocket) -> None:
        self.clients.setdefault(user_id, set()).add(websocket)

    def remove_client(self, user_id: str, websocket: WebSocket) -> None:
        conns = self.clients.get(user_id)
        if conns:
            conns.discard(websocket)
            if not conns:
                self.clients.pop(user_id, None)

    async def broadcast_to_clients(self, user_id: str, message: dict[str, Any]) -> None:
        """把一条消息推送给该用户所有在线浏览器标签页。"""
        for websocket in list(self.clients.get(user_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:
                self.remove_client(user_id, websocket)


registry = Registry()


# —————————————————————————————————————————————
# WebSocket 鉴权工具
# —————————————————————————————————————————————

def _authenticate_ws_token(token: Optional[str]) -> Optional[str]:
    """校验 WebSocket 握手令牌，返回 user_id；失败返回 None。"""
    if not token:
        return None
    try:
        payload = verify_access_token(token)
        return payload.get("sub")
    except Exception:
        return None


def _agent_status_payload(user_id: str) -> dict[str, Any]:
    """构造给浏览器的 Agent 在线状态消息。"""
    agent = registry.agents.get(user_id)
    if agent is None:
        return {"type": "agent_status", "online": False}
    return {
        "type": "agent_status",
        "online": True,
        "agent_id": agent.agent_id,
        "runtime_version": agent.runtime_version,
        "platform": agent.platform,
        "device_summary": agent.device_summary,
    }


# —————————————————————————————————————————————
# REST：训练任务中转
# —————————————————————————————————————————————

@router.post("/train")
async def create_cloud_training_job(request: CloudTrainRequest, user_id: str = Query(...)) -> dict[str, Any]:
    """创建云端训练任务，并下发给用户本机 Agent。

    云端只保存和转发该请求，不能在服务器本机执行 PyTorch 训练。

    参数：
        request：前端提交的训练请求，包含模型图 model 和训练配置 train_config。
        user_id：任务所属用户 id（当前作为查询参数占位，后续应从 JWT 获取）。

    返回：
        status / job_id / job_status / agent_status / message。
    """
    agent = registry.agents.get(user_id)
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    train_config = dict(request.train_config or {})

    record = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "pending_agent",
        "model": request.model.model_dump(),
        "train_config": train_config,
        "current_epoch": 0,
        "total_epochs": train_config.get("epochs", 1),
        "current_step": 0,
        "total_steps": 0,
        "progress": 0.0,
        "metrics": [],
        "result": None,
        "error": None,
        "created_at": time.time(),
    }
    registry.jobs[job_id] = record

    if agent is None:
        record["status"] = "no_agent"
        return {
            "status": "ok",
            "job_id": job_id,
            "job_status": "no_agent",
            "agent_status": "offline",
            "message": "未检测到在线的本机训练 Agent，请先在本地启动训练 Agent。",
        }

    dispatch = await dispatch_training_job_to_agent(job_id, user_id, {
        "job_id": job_id,
        "model": record["model"],
        "train_config": train_config,
        "runtime_version": RUNTIME_VERSION,
    })

    record["status"] = "dispatched"
    return {
        "status": "ok",
        "job_id": job_id,
        "job_status": "dispatched",
        "agent_status": "online",
        "agent_id": dispatch.get("agent_id"),
        "message": "训练任务已下发到本机 Agent。",
    }


@router.get("/train/{job_id}/status")
def get_cloud_training_status(job_id: str, user_id: str = Query(...)) -> dict[str, Any]:
    """查询云端记录的训练任务状态。"""
    record = registry.jobs.get(job_id)
    if record is None or record["user_id"] != user_id:
        return JSONResponse(status_code=404, content={"status": "error", "message": "训练任务不存在"})

    return {
        "job_id": job_id,
        "status": record["status"],
        "current_epoch": record["current_epoch"],
        "total_epochs": record["total_epochs"],
        "current_step": record["current_step"],
        "total_steps": record["total_steps"],
        "progress": record["progress"],
        "metrics": record["metrics"],
        "error": record["error"],
    }


@router.post("/train/{job_id}/cancel")
async def cancel_cloud_training_job(job_id: str, user_id: str = Query(...)) -> dict[str, Any]:
    """请求取消一个正在执行或等待执行的训练任务。"""
    record = registry.jobs.get(job_id)
    if record is None or record["user_id"] != user_id:
        return JSONResponse(status_code=404, content={"status": "error", "message": "训练任务不存在"})

    if record["status"] in ("completed", "failed", "cancelled"):
        return {"job_id": job_id, "cancelled": False, "status": record["status"], "message": "任务已结束，无需取消。"}

    agent = registry.agents.get(user_id)
    if agent is None:
        record["status"] = "cancelled"
        return {"job_id": job_id, "cancelled": True, "status": "cancelled", "message": "本机 Agent 已离线，任务已在云端标记为取消。"}

    await agent.send({"type": "cancel_training", "job_id": job_id})
    return {"job_id": job_id, "cancelled": True, "status": record["status"], "message": "已向本机 Agent 转发取消请求。"}


@router.get("/train/{job_id}/result")
def get_cloud_training_result(job_id: str, user_id: str = Query(...)) -> dict[str, Any]:
    """查询本机 Agent 回传的最终训练结果。"""
    record = registry.jobs.get(job_id)
    if record is None or record["user_id"] != user_id:
        return JSONResponse(status_code=404, content={"status": "error", "message": "训练任务不存在"})

    result = record.get("result") or {}
    return {
        "job_id": job_id,
        "status": record["status"],
        "loss": result.get("loss"),
        "accuracy": result.get("accuracy"),
        "metrics": record["metrics"],
        "device": result.get("device"),
        "artifacts": result.get("artifacts"),
        "error": record["error"],
    }


@router.get("/agents/status")
def get_agent_status(user_id: str = Query(...)) -> dict[str, Any]:
    """查询某用户当前本机 Agent 的在线状态（供前端首次加载查询）。"""
    return _agent_status_payload(user_id)


# —————————————————————————————————————————————
# WebSocket：本机 Agent 连接
# —————————————————————————————————————————————

@router.websocket("/agents/ws")
async def agent_websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    """接收用户本机 Agent 主动建立的 WebSocket 连接。

    Agent 在握手时通过查询参数 token 携带用户 JWT，认证成功后注册为该
    用户的在线 Agent，随后循环接收 Agent 上报的进度/结果消息并中转给
    对应用户的浏览器。
    """
    user_id = _authenticate_ws_token(token)
    if user_id is None:
        await websocket.close(code=1008, reason="Agent 令牌无效")
        return

    await websocket.accept()
    session = AgentSession(user_id, websocket)
    registry.agents[user_id] = session
    await websocket.send_json({"type": "welcome", "runtime_version": RUNTIME_VERSION})

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_agent_message(session, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # 仅在当前会话仍是该用户注册的 Agent 时移除（避免误删新连接）
        if registry.agents.get(user_id) is session:
            registry.agents.pop(user_id, None)
            await registry.broadcast_to_clients(user_id, {"type": "agent_status", "online": False})


async def _handle_agent_message(session: AgentSession, message: dict[str, Any]) -> None:
    """处理本机 Agent 上报的一条消息。"""
    msg_type = message.get("type")
    user_id = session.user_id

    if msg_type == "hello":
        session.agent_id = message.get("agent_id") or f"agent_{uuid.uuid4().hex[:8]}"
        session.runtime_version = message.get("runtime_version", "")
        session.platform = message.get("platform", "")
        session.device_summary = message.get("device_summary", {}) or {}
        # 通知该用户所有浏览器：本机 Agent 已上线
        await registry.broadcast_to_clients(user_id, _agent_status_payload(user_id))
        return

    if msg_type == "heartbeat":
        session.last_heartbeat_at = time.time()
        return

    if msg_type in ("training_update", "training_result"):
        handle_agent_training_update(session.agent_id, message)
        # 原样中转给浏览器
        await registry.broadcast_to_clients(user_id, message)
        return

    if msg_type == "command_ack":
        # 命令回执：记录到任务上，也转发给前端便于提示
        job = registry.jobs.get(message.get("job_id", ""))
        if job is not None and not message.get("accepted", True):
            job["status"] = "failed"
            job["error"] = message.get("message", "本机 Agent 拒绝了训练指令")
        await registry.broadcast_to_clients(user_id, message)
        return

    if msg_type == "agent_response":
        # 校验/设备/导出等请求-响应的回执，原样中转给浏览器
        await registry.broadcast_to_clients(user_id, message)
        return


# —————————————————————————————————————————————
# WebSocket：浏览器客户端连接
# —————————————————————————————————————————————

@router.websocket("/client/ws")
async def client_websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    """接收浏览器建立的持久化 WebSocket 连接。

    连接建立后立即推送当前 Agent 在线状态；之后由服务器把 Agent 回传的
    训练进度/结果实时推送给浏览器。浏览器侧通常只接收，无需上行。
    """
    user_id = _authenticate_ws_token(token)
    if user_id is None:
        await websocket.close(code=1008, reason="令牌无效")
        return

    await websocket.accept()
    registry.add_client(user_id, websocket)
    await websocket.send_json(_agent_status_payload(user_id))

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_client_message(user_id, message)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        registry.remove_client(user_id, websocket)


async def _handle_client_message(user_id: str, message: dict[str, Any]) -> None:
    """处理浏览器上行消息（校验/设备/导出等需要 Agent 执行的请求）。"""
    if message.get("type") != "agent_request":
        return

    request_id = message.get("request_id", "")
    agent = registry.agents.get(user_id)
    if agent is None:
        # 无在线 Agent，直接回错误响应给浏览器
        await registry.broadcast_to_clients(user_id, {
            "type": "agent_response",
            "request_id": request_id,
            "ok": False,
            "error": "未检测到在线的本机训练 Agent，请先在本地启动训练 Agent。",
        })
        return

    # 转发给该用户的本机 Agent 执行
    await agent.send({
        "type": "agent_request",
        "request_id": request_id,
        "action": message.get("action"),
        "payload": message.get("payload", {}),
    })


# —————————————————————————————————————————————
# 运行时下载（首次使用需下载本机训练代码）
# —————————————————————————————————————————————

def _build_runtime_package() -> tuple[bytes, str]:
    """把本机训练运行时源码打包为 zip，返回 (数据, sha256)。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(_RUNTIME_SOURCE_DIR.rglob("*.py")):
            archive.write(path, arcname=f"runtime/{path.relative_to(_RUNTIME_SOURCE_DIR)}")
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


@router.get("/runtime/manifest")
def get_runtime_manifest() -> dict[str, Any]:
    """返回最新训练运行时的元信息，供 Agent 判断是否需要下载。"""
    data, sha256 = _build_runtime_package()
    return {
        "version": RUNTIME_VERSION,
        "download_url": "/runtime/download",
        "sha256": sha256,
        "size_bytes": len(data),
        "min_agent_version": MIN_AGENT_VERSION,
        "release_notes": "可视化深度学习训练运行时",
    }


@router.get("/runtime/download")
def download_runtime() -> Response:
    """下载训练运行时 zip 包。"""
    data, _ = _build_runtime_package()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="trainer-runtime-{RUNTIME_VERSION}.zip"'},
    )


# —————————————————————————————————————————————
# 本机 Agent 下载（首次使用的用户从这里获取整个 Agent 程序）
# —————————————————————————————————————————————

def _compile_to_pyc(source_path: Path) -> bytes:
    """把一个 .py 文件编译为「无源码」的 .pyc 字节，用于代码保护。"""
    with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        py_compile.compile(str(source_path), cfile=tmp_path, doraise=True, optimize=2)
        return Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/agent/download")
def download_agent(request: Request, token: str = Query(...)) -> Response:
    """打包并下载本机训练应用（自举启动器 + 编译后的 Agent 代码 + 内置令牌）。

    首次使用、本机还没有训练程序的用户，从网页「本机训练 Agent」弹窗点击下载
    即可获取。包内：
      - launcher.py：自举启动器（检测/创建专属虚拟环境、装依赖、启动 Agent）；
      - local_agent/*.pyc：编译后的 Agent 与训练代码（不含明文源码）；
      - config.json：云端地址与当前用户令牌（下载已按登录态注入，双击即连）；
      - README.txt / build_app.md：使用说明与「打包成单文件应用」的构建指引。

    参数：
        token：当前用户的 JWT 令牌（查询参数，浏览器下载链接无法带请求头，
            故用查询参数）。校验通过后注入 config.json。
    """
    try:
        verify_access_token(token)
    except Exception:
        return JSONResponse(status_code=401, content={"status": "error", "message": "令牌无效，无法下载应用"})

    server_url = str(request.base_url).rstrip("/")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # 启动器以源码形式放在顶层（它是打包单文件应用的入口，且只用标准库）
        launcher_src = _AGENT_SOURCE_DIR / "launcher.py"
        archive.writestr("visualdl-agent/launcher.py", launcher_src.read_text(encoding="utf-8"))

        # local_agent 其余代码编译为 .pyc（无源码分发，保护系统代码）
        for path in sorted(_AGENT_SOURCE_DIR.rglob("*.py")):
            if path.name == "launcher.py":
                continue
            rel = path.relative_to(_AGENT_SOURCE_DIR.parent)  # 保留 local_agent/ 前缀
            pyc_name = f"visualdl-agent/{rel.with_suffix('.pyc')}"
            archive.writestr(pyc_name, _compile_to_pyc(path))

        # 内置令牌与云端地址：双击即自动连接、绑定账号
        archive.writestr("visualdl-agent/config.json", json.dumps({"server_url": server_url, "token": token}, ensure_ascii=False))
        archive.writestr("visualdl-agent/README.txt", _AGENT_README.format(py=_PYC_PYTHON))
        archive.writestr("visualdl-agent/build_app.md", _BUILD_GUIDE.format(py=_PYC_PYTHON))

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="visualdl-agent-{RUNTIME_VERSION}.zip"'},
    )


# —————————————————————————————————————————————
# 内部辅助
# —————————————————————————————————————————————

async def dispatch_training_job_to_agent(job_id: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """将训练任务下发给用户在线的本机 Agent。"""
    agent = registry.agents.get(user_id)
    if agent is None:
        return {"dispatch_status": "no_agent", "agent_id": None, "sent_at": time.time(), "message": "无在线 Agent"}

    await agent.send({"type": "start_training", **payload})
    return {
        "dispatch_status": "sent",
        "agent_id": agent.agent_id,
        "sent_at": time.time(),
        "message": "训练指令已发送",
    }


def handle_agent_training_update(agent_id: str, message: dict[str, Any]) -> dict[str, Any]:
    """处理本机 Agent 回传的训练进度或最终结果，更新云端任务状态。"""
    job_id = message.get("job_id")
    record = registry.jobs.get(job_id or "")
    if record is None:
        return {"status": "ignored", "job_id": job_id, "accepted": False, "message": "未知任务"}

    msg_type = message.get("type")
    record["status"] = message.get("status", record["status"])
    if "current_epoch" in message:
        record["current_epoch"] = message["current_epoch"]
    if "total_epochs" in message:
        record["total_epochs"] = message["total_epochs"]
    if "current_step" in message:
        record["current_step"] = message["current_step"]
    if "total_steps" in message:
        record["total_steps"] = message["total_steps"]
    if "progress" in message:
        record["progress"] = message["progress"]
    if message.get("metrics") is not None:
        record["metrics"] = message["metrics"]
    if message.get("error") is not None:
        record["error"] = message["error"]

    if msg_type == "training_result":
        record["result"] = {
            "loss": message.get("loss"),
            "accuracy": message.get("accuracy"),
            "device": message.get("device"),
            "artifacts": message.get("artifacts"),
        }

    return {"status": "ok", "job_id": job_id, "accepted": True, "message": "已更新"}


def get_online_agent_for_user(user_id: str) -> Optional[dict[str, Any]]:
    """查询某个用户当前在线的本机 Agent 元信息。"""
    agent = registry.agents.get(user_id)
    return agent.meta() if agent is not None else None


# 供 Docker/环境变量覆盖：训练产物默认目录（仅当 Agent 未指定时使用）
DEFAULT_ARTIFACTS_ROOT = os.getenv("ARTIFACTS_ROOT", "training_artifacts")
