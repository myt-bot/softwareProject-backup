"""用户本机 Agent 入口。

该进程运行在用户电脑上，负责持有 PyTorch 训练环境，并主动连接云端
服务器。服务器端不应直接执行 local_agent.runtime 下的训练代码。

命令行启动（连接云端并等待训练指令）：
    python -m local_agent.main --server http://127.0.0.1:8000 --token <JWT>
"""

import argparse
import asyncio
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI

from . import runtime_manager
from .agent_client import connect_to_cloud_server
from .runtime.device import get_device_summary
from .runtime.schemas import ModelRequest
from .runtime.validator import validate_model_graph

# 训练运行时下载/安装目录（各版本训练代码缓存于此）
RUNTIME_ROOT = Path.home() / ".visualdl_agent" / "runtime"


app = FastAPI(title="VisualDL Local Training Agent")


@app.get("/health")
def health_check() -> dict[str, Any]:
    """返回本机 Agent 的健康状态。

    返回：
        dict，包含 Agent 状态、服务名称和本机可用设备摘要。
    """
    return {
        "status": "ok",
        "service": "VisualDL Local Training Agent",
        "devices": get_device_summary(),
    }


@app.get("/devices")
def list_devices() -> dict[str, Any]:
    """返回用户本机可用的 CPU/GPU 训练设备。

    返回：
        dict，包含 status，以及 runtime.device.get_device_summary()
        生成的设备摘要。
    """
    return {
        "status": "ok",
        **get_device_summary(),
    }


@app.post("/validate")
def validate_model(request: ModelRequest) -> dict[str, Any]:
    """在用户本机校验模型结构。

    参数：
        request：模型校验请求体，包含前端或云端下发的模型图结构。

    返回：
        dict，包含 valid、errors、warnings 和维度推导结果等校验信息。
    """
    return validate_model_graph(request.model.model_dump())


def start_agent(
    server_url: str,
    auth_token: str,
    agent_id: Optional[str] = None,
    runtime_version: Optional[str] = None,
) -> None:
    """启动本机 Agent：确保训练运行时就绪后，主动连接云端服务器。

    参数：
        server_url：云端服务器地址，例如 "http://127.0.0.1:8000"。
        auth_token：证明当前 Agent 属于某个用户的 JWT 身份令牌。
        agent_id：本机 Agent 稳定 id，为空时自动生成。
        runtime_version：期望的训练运行时版本，为空时向云端查询最新版本。

    该函数保持运行，直到用户关闭 Agent（Ctrl+C）。
    """
    # 首次使用：确保本机已下载训练运行时代码
    ready = runtime_manager.ensure_runtime_ready(server_url, auth_token, RUNTIME_ROOT)
    print(f"[agent] 训练运行时：{ready.get('message')}")
    version = runtime_version or ready.get("version") or ""

    devices = get_device_summary()
    print(f"[agent] 本机可用设备：{devices.get('available_devices')}（默认 {devices.get('default_device')}）")
    print(f"[agent] 正在连接云端 {server_url} ...")

    try:
        asyncio.run(connect_to_cloud_server(
            server_url=server_url,
            auth_token=auth_token,
            agent_id=agent_id,
            runtime_version=version,
        ))
    except KeyboardInterrupt:
        print("\n[agent] 已停止。")


def _main() -> None:
    parser = argparse.ArgumentParser(description="VisualDL 本机训练 Agent")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="云端服务器地址")
    parser.add_argument("--token", required=True, help="登录后获得的 JWT 令牌（绑定用户身份）")
    parser.add_argument("--agent-id", default=None, help="本机 Agent 稳定 id（可选）")
    args = parser.parse_args()
    start_agent(server_url=args.server, auth_token=args.token, agent_id=args.agent_id)


if __name__ == "__main__":
    _main()
