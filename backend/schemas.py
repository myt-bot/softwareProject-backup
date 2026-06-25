"""请求和响应数据结构。

这里维护前后端之间的数据约定。后续项目细化后，可以继续增加更严格的字段校验规则。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LayerConfig(BaseModel):
    """描述画布中的一个模型层节点以及它的可编辑参数。

    字段：
        id：节点唯一标识，用于连接关系和前端节点定位。
        type：层类型，例如 Input、Conv2D、ReLU、Flatten 或 Linear。
        name：用户可读的层名称，可用于界面展示；默认为 None。
        params：层参数字典，用于保存 kernel_size、stride、out_features 等配置。
    """

    id: str
    type: str
    name: Optional[str] = None
    params: Dict[str, Any] = {}


class ConnectionConfig(BaseModel):
    """描述画布中两个层节点之间的连接关系。

    字段：
        source：连接起点节点 id，表示数据从哪个层输出。
        target：连接终点节点 id，表示数据流入哪个层。
    """

    source: str
    target: str


class ModelGraph(BaseModel):
    """描述前端传给后端的完整模型图结构。

    字段：
        layers：模型图中的所有层节点配置列表。
        connections：节点之间的连接关系列表，用于确定模型执行顺序。
    """

    layers: List[LayerConfig]
    connections: List[ConnectionConfig] = []


class TrainConfig(BaseModel):
    """描述训练超参数以及用户选择的计算设备。

    字段：
        dataset：训练数据集名称，例如 MNIST。
        epochs：训练轮数，表示完整遍历训练集的次数。
        batch_size：批大小，表示每次参数更新使用多少条样本。
        learning_rate：学习率，用于控制优化器每次更新参数的步长。
        device：用户选择的计算设备，例如 cpu、cuda 或 auto。
    """

    dataset: str
    epochs: int
    batch_size: int
    learning_rate: float
    device: str


class ModelRequest(BaseModel):
    """模型校验和维度推导接口的请求体。

    字段：
        model：需要校验和推导维度的模型图结构。
    """

    model: ModelGraph


class TrainRequest(BaseModel):
    """启动本地训练任务接口的请求体。

    字段：
        model：用于训练的模型图结构。
        train_config：训练配置，包含数据集、轮数、批大小、学习率和设备。
    """

    model: ModelGraph
    train_config: TrainConfig


class CodeExportRequest(BaseModel):
    """导出 PyTorch 代码接口的请求体。

    字段：
        model：需要导出为 PyTorch 代码的模型图结构。
        class_name：导出的 PyTorch 模型类名，默认值为 GeneratedModel。
    """

    model: ModelGraph
    class_name: str = "GeneratedModel"
