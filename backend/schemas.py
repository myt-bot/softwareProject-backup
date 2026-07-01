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

    def check_id(self) -> List[str]:
        """检查节点 id 是否为非空字符串。"""
        if not isinstance(self.id, str) or not self.id.strip():
            return ["层节点 id 必须是非空字符串"]
        return []

    def check_type(self) -> List[str]:
        """检查节点 type 是否为非空字符串。"""
        if not isinstance(self.type, str) or not self.type.strip():
            return [f"层 {self.id}: type 必须是非空字符串"]
        return []

    def check_name(self) -> List[str]:
        """检查节点 name 是否为空或字符串。"""
        if self.name is not None and not isinstance(self.name, str):
            return [f"层 {self.id}: name 必须是字符串或 None"]
        return []

    def check_params(self) -> List[str]:
        """检查节点 params 是否为字典。"""
        if not isinstance(self.params, dict):
            return [f"层 {self.id}: params 必须是字典"]
        return []

    def check_all(self) -> List[str]:
        """汇总检查当前层节点的基础字段。"""
        errors = []
        errors.extend(self.check_id())
        errors.extend(self.check_type())
        errors.extend(self.check_name())
        errors.extend(self.check_params())
        return errors


class ConnectionConfig(BaseModel):
    """描述画布中两个层节点之间的连接关系。

    字段：
        source：连接起点节点 id，表示数据从哪个层输出。
        target：连接终点节点 id，表示数据流入哪个层。
    """

    source: str
    target: str

    def check_source(self) -> List[str]:
        """检查连接起点是否为非空字符串。"""
        if not isinstance(self.source, str) or not self.source.strip():
            return ["连接 source 必须是非空字符串"]
        return []

    def check_target(self) -> List[str]:
        """检查连接终点是否为非空字符串。"""
        if not isinstance(self.target, str) or not self.target.strip():
            return ["连接 target 必须是非空字符串"]
        return []

    def check_all(self) -> List[str]:
        """汇总检查当前连接的基础字段。"""
        errors = []
        errors.extend(self.check_source())
        errors.extend(self.check_target())
        return errors


class ModelGraph(BaseModel):
    """描述前端传给后端的完整模型图结构。

    字段：
        layers：模型图中的所有层节点配置列表。
        connections：节点之间的连接关系列表，用于确定模型执行顺序。
    """

    layers: List[LayerConfig]
    connections: List[ConnectionConfig] = []

    def check_layers(self) -> List[str]:
        """检查 layers 是否为非空列表，并汇总每个层节点的基础字段错误。"""
        errors = []

        if not isinstance(self.layers, list):
            return ["model.layers 必须是列表"]

        if not self.layers:
            errors.append("model.layers 不能为空")

        for index, layer in enumerate(self.layers):
            if not isinstance(layer, LayerConfig):
                errors.append(f"model.layers[{index}] 必须是 LayerConfig")
                continue
            errors.extend(layer.check_all())

        return errors

    def check_connections(self) -> List[str]:
        """检查 connections 是否为列表，并汇总每条连接的基础字段错误。"""
        errors = []

        if not isinstance(self.connections, list):
            return ["model.connections 必须是列表"]

        for index, connection in enumerate(self.connections):
            if not isinstance(connection, ConnectionConfig):
                errors.append(f"model.connections[{index}] 必须是 ConnectionConfig")
                continue
            errors.extend(connection.check_all())

        return errors

    def check_all(self) -> List[str]:
        """汇总检查完整模型图的基础字段。"""
        errors = []
        errors.extend(self.check_layers())
        errors.extend(self.check_connections())
        return errors


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

    def check_dataset_name(self) -> List[str]:
        """检查数据集名称是否为非空字符串。"""
        if not isinstance(self.dataset_name, str) or not self.dataset_name.strip():
            return ["dataset_name 必须是非空字符串"]
        return []

    def check_epochs(self) -> List[str]:
        """检查训练轮数是否为正整数。"""
        if not isinstance(self.epochs, int) or self.epochs <= 0:
            return ["epochs 必须是正整数"]
        return []

    def check_batch_size(self) -> List[str]:
        """检查批大小是否为正整数。"""
        if not isinstance(self.batch_size, int) or self.batch_size <= 0:
            return ["batch_size 必须是正整数"]
        return []

    def check_rate(self) -> List[str]:
        """检查学习率是否为正数。"""
        if not isinstance(self.rate, (int, float)) or self.rate <= 0:
            return ["rate 必须是正数"]
        return []

    def check_device(self) -> List[str]:
        """检查设备名称是否为非空字符串。"""
        if not isinstance(self.device, str) or not self.device.strip():
            return ["device 必须是非空字符串"]
        return []

    def check_loss_fn(self) -> List[str]:
        """检查损失函数名称是否为非空字符串。"""
        if not isinstance(self.loss_fn, str) or not self.loss_fn.strip():
            return ["loss_fn 必须是非空字符串"]
        return []

    def check_optimizer(self) -> List[str]:
        """检查优化器名称是否为非空字符串。"""
        if not isinstance(self.optimizer, str) or not self.optimizer.strip():
            return ["optimizer 必须是非空字符串"]
        return []

    def check_all(self) -> List[str]:
        """汇总检查训练配置的基础字段。"""
        errors = []
        errors.extend(self.check_dataset_name())
        errors.extend(self.check_epochs())
        errors.extend(self.check_batch_size())
        errors.extend(self.check_rate())
        errors.extend(self.check_device())
        errors.extend(self.check_loss_fn())
        errors.extend(self.check_optimizer())
        return errors


class ModelRequest(BaseModel):
    """模型校验和维度推导接口的请求体。

    字段：
        model：需要校验和推导维度的模型图结构。
    """

    model: ModelGraph

    def check_model(self) -> List[str]:
        """检查模型请求中的模型图。"""
        if not isinstance(self.model, ModelGraph):
            return ["model 必须是 ModelGraph"]
        return self.model.check_all()

    def check_all(self) -> List[str]:
        """汇总检查模型请求。"""
        return self.check_model()


class TrainRequest(BaseModel):
    """启动本地训练任务接口的请求体。

    字段：
        model：用于训练的模型图结构。
        train_config：训练配置，包含数据集、轮数、批大小、学习率、设备、损失函数和优化器。
    """

    model: ModelGraph
    train_config: TrainConfig

    def check_model(self) -> List[str]:
        """检查训练请求中的模型图。"""
        if not isinstance(self.model, ModelGraph):
            return ["model 必须是 ModelGraph"]
        return self.model.check_all()

    def check_train_config(self) -> List[str]:
        """检查训练请求中的训练配置。"""
        if not isinstance(self.train_config, TrainConfig):
            return ["train_config 必须是 TrainConfig"]
        return self.train_config.check_all()

    def check_all(self) -> List[str]:
        """汇总检查训练请求。"""
        errors = []
        errors.extend(self.check_model())
        errors.extend(self.check_train_config())
        return errors


class CodeExportRequest(BaseModel):
    """导出 PyTorch 代码接口的请求体。

    字段：
        model：需要导出为 PyTorch 代码的模型图结构。
        class_name：导出的 PyTorch 模型类名，默认值为 GeneratedModel。
    """

    model: ModelGraph
    class_name: str = "GeneratedModel"

<<<<<<< HEAD

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
=======
    def check_model(self) -> List[str]:
        """检查代码导出请求中的模型图。"""
        if not isinstance(self.model, ModelGraph):
            return ["model 必须是 ModelGraph"]
        return self.model.check_all()

    def check_class_name(self) -> List[str]:
        """检查导出类名是否为非空字符串。"""
        if not isinstance(self.class_name, str) or not self.class_name.strip():
            return ["class_name 必须是非空字符串"]
        return []

    def check_all(self) -> List[str]:
        """汇总检查代码导出请求。"""
        errors = []
        errors.extend(self.check_model())
        errors.extend(self.check_class_name())
        return errors
>>>>>>> 778d884361f0ecefb0f0b9490eae6e24633b97f1
