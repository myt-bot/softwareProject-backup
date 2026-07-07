"""本机 Agent 连接云端服务器的 WebSocket 客户端。"""

from typing import Any


def connect_to_cloud_server(
    server_url: str,
    auth_token: str,
    agent_id: str | None = None,
    runtime_version: str | None = None,
) -> None:
    """连接云端 WebSocket 服务。

    TODO：实现 WebSocket 建连、身份认证、心跳、断线重连、命令接收、
    训练进度上报和最终结果上报。

    参数：
        server_url：云端 WebSocket 地址，例如
            "wss://example.com/agents/ws"。
        auth_token：用于绑定用户或设备的身份令牌。
        agent_id：本机 Agent 的稳定 id。为空时应读取或生成本地 id。
        runtime_version：当前已安装的 trainer-runtime 版本。

    返回：
        None。正式实现中该函数应持续运行，直到用户停止 Agent 或进程
        收到关闭信号。
    """
    raise NotImplementedError("TODO：连接本机 Agent 到云端服务器")


def build_agent_hello_message(
    agent_id: str,
    auth_token: str,
    runtime_version: str,
    device_summary: dict[str, Any],
) -> dict[str, Any]:
    """构造 Agent 连接云端后的首条注册消息。

    TODO：实现 hello 消息构造。若协议改为在请求头中传递令牌，则首条
    消息中不应重复发送敏感 token。

    参数：
        agent_id：本机 Agent 的稳定 id。
        auth_token：用于绑定用户或设备的身份令牌。
        runtime_version：当前安装的训练运行时版本。
        device_summary：本机 CPU/GPU 能力摘要。

    返回：
        dict，包含消息类型、Agent id、身份信息或身份引用、运行时版本、
        设备摘要、平台信息和时间戳。
    """
    raise NotImplementedError("TODO：构造 Agent hello 消息")


def handle_cloud_command(command: dict[str, Any]) -> dict[str, Any]:
    """处理云端服务器下发的指令。

    TODO：实现命令分发。预期指令类型包括 start_training、
    cancel_training、check_runtime、download_runtime 和 ping。

    参数：
        command：云端服务器下发的消息，必须包含 type 字段，并根据指令
            类型携带 job_id、模型图、训练配置或运行时版本等数据。

    返回：
        dict，说明该指令是否被接受，以及需要立即回传给云端的响应数据。
    """
    raise NotImplementedError("TODO：处理云端下发指令")


def start_local_training_job(job_id: str, model_graph: dict[str, Any], train_config: dict[str, Any]) -> dict[str, Any]:
    """在用户本机启动 PyTorch 训练任务。

    TODO：对接 local_agent.runtime.trainer。训练循环必须在本机执行，并
    通过 WebSocket 将进度、指标和最终结果回传给云端。

    参数：
        job_id：云端训练任务 id，用于关联进度、结果和训练产物。
        model_graph：云端下发的可视化模型图结构。
        train_config：训练配置，例如 dataset_name、epochs、batch_size、
            学习率、device、data_dir 和 artifacts_dir。

    返回：
        dict，包含 job_id、accepted、local_job_id、status 和 message。
    """
    raise NotImplementedError("TODO：启动本机训练任务")


def send_training_update(job_id: str, status: str, payload: dict[str, Any]) -> None:
    """向云端服务器发送训练进度或最终结果。

    TODO：使用当前活跃的 WebSocket 连接发送消息，必要时加入本地队列以
    支持断线后的补发。

    参数：
        job_id：云端训练任务 id。
        status：当前任务状态，例如 running、completed、failed 或
            cancelled。
        payload：状态对应的数据。训练中通常包含 current_epoch、progress
            和 metrics；训练完成时通常包含最终指标和产物元信息。

    返回：
        None。正式实现中该函数应发送或排队一条 WebSocket 消息。
    """
    raise NotImplementedError("TODO：向云端发送训练状态")
