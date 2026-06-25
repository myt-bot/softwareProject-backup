"""请求和响应数据结构。

这里维护前后端之间的数据约定。后续项目细化后，可以继续增加更严格的字段校验规则。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class LayerConfig(BaseModel):
    """描述画布中的一个模型层节点以及它的可编辑参数。"""

    id: str
    type: str
    name: Optional[str] = None
    params: Dict[str, Any] = {}


class ConnectionConfig(BaseModel):
    """描述画布中两个层节点之间的连接关系。"""

    source: str
    target: str


class ModelGraph(BaseModel):
    """描述前端传给后端的完整模型图结构。"""

    layers: List[LayerConfig]
    connections: List[ConnectionConfig] = []


class TrainConfig(BaseModel):
    """描述训练超参数以及用户选择的计算设备。"""

    dataset: str
    epochs: int
    batch_size: int
    learning_rate: float
    device: str


class ModelRequest(BaseModel):
    """模型校验和维度推导接口的请求体。"""

    model: ModelGraph


class TrainRequest(BaseModel):
    """启动本地训练任务接口的请求体。"""

    model: ModelGraph
    train_config: TrainConfig


class CodeExportRequest(BaseModel):
    """导出 PyTorch 代码接口的请求体。"""

    model: ModelGraph
    class_name: str = "GeneratedModel"
