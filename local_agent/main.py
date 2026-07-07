"""用户本机 Agent 入口。

该进程运行在用户电脑上，负责持有 PyTorch 训练环境，并主动连接云端
服务器。服务器端不应直接执行 local_agent.runtime 下的训练代码。
"""

from typing import Any

from fastapi import FastAPI

from .agent_client import connect_to_cloud_server
from .runtime.device import get_device_summary
from .runtime.schemas import ModelRequest
from .runtime.validator import validate_model_graph


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
    agent_id: str | None = None,
    runtime_version: str | None = None,
) -> None:
    """启动本机 Agent，并主动连接云端服务器。

    TODO：实现进程启动、日志初始化、运行时检查、异常处理和优雅退出。

    参数：
        server_url：云端 WebSocket 地址，例如
            "wss://example.com/agents/ws"。
        auth_token：用于证明当前 Agent 属于某个用户或设备的身份令牌。
        agent_id：本机 Agent 的稳定 id。为空时应从本地配置读取或自动
            生成。
        runtime_version：期望使用的 trainer-runtime 版本。为空时应向
            云端查询最新兼容版本。

    返回：
        None。正式实现中该函数应保持运行，直到用户关闭 Agent 或进程
        收到退出信号。
    """
    connect_to_cloud_server(
        server_url=server_url,
        auth_token=auth_token,
        agent_id=agent_id,
        runtime_version=runtime_version,
    )
