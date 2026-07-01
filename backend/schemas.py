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
        dataset_name：训练数据集名称，例如 MNIST。
        epochs：训练轮数，表示完整遍历训练集的次数。
        batch_size：批大小，表示每次参数更新使用多少条样本。
        rate：学习率，用于控制优化器每次更新参数的步长。
        device：用户选择的计算设备，例如 cpu、cuda 或 auto。
    """

    dataset_name: str = "MNIST"
    epochs: int = 1
    batch_size: int = 64
    rate: float = 0.001
    device: str = "cpu"
    loss_fn: str = "cross_entropy"
    optimizer: str = "sgd"


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
        train_config：训练配置，包含数据集、轮数、批大小、学习率、设备、损失函数和优化器。
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


# ============================================================
# M1 用户与项目管理模块 —— 数据结构
# 编写者：甘淞文
# ============================================================

class UserCreateRequest(BaseModel):
    """创建用户接口的请求体。

    字段：
        username：用户名，2-20 个字符，支持中英文、数字和下划线。
        email：用户邮箱，需符合基本邮箱格式。
    """

    username: str
    email: str


class UserUpdateRequest(BaseModel):
    """更新用户接口的请求体。所有字段可选，至少提供一个。

    字段：
        username：新的用户名（可选）。
        email：新的邮箱（可选）。
    """

    username: Optional[str] = None
    email: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    """创建项目（保存模型）接口的请求体。

    字段：
        user_id：所属用户 id。
        name：项目名称，不能超过 100 个字符。
        model_graph：模型图结构，包含 layers 和 connections。
        description：项目描述（可选），不能超过 500 个字符。
    """

    user_id: str
    name: str
    model_graph: ModelGraph
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    """更新项目接口的请求体。所有字段可选，至少提供一个。

    字段：
        name：新的项目名称（可选）。
        model_graph：新的模型图结构（可选）。
        description：新的项目描述（可选）。
    """

    name: Optional[str] = None
    model_graph: Optional[ModelGraph] = None
    description: Optional[str] = None

# ============================================================
# M1 用户与项目管理模块 —— 数据结构
# ============================================================