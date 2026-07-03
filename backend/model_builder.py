"""根据可视化模型 JSON 构建 PyTorch 模型。"""

import json

import torch
import torch.nn as nn

from .graph_utils import (
    build_predecessor_map,
    build_successor_map,
    topological_sort_layers,
)
from .validator import infer_all_shapes


def build_model(model_graph):
    """将模型图转换成支持非顺序结构的 PyTorch 图模型。

    参数：
        model_graph：前端画布生成的模型图结构，包含层节点列表和节点连接关系。

    返回：
        GraphModel：支持 DAG 前向传播的 PyTorch 模型。
    """
    normalized_graph = json.loads(model_graph)
    ordered_layers = order_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph)

    modules = {}
    layer_shapes = shape_info["layers"]
    for layer_config in ordered_layers:
        layer_id = layer_config["id"]
        layer_type = layer_config["type"]
        input_shape = None
        if layer_type not in ("Input", "Output"):
            input_shape = layer_shapes[layer_id]["input_shape"]

        layer = create_layer(layer_config, input_shape)
        if layer is not None:
            modules[layer_id] = layer

    return GraphModel(
        model_graph=normalized_graph,
        ordered_layers=ordered_layers,
        modules=modules,
    )


class GraphModel(nn.Module):
    """支持有向无环图结构的 PyTorch 模型。

    参数：
        model_graph：模型图结构，包含 layers 和 connections。
        ordered_layers：经过拓扑排序后的层配置列表。
        modules：以 layer_id 为键、PyTorch 层对象为值的模块字典。
    """

    def __init__(self, model_graph, ordered_layers, modules):
        super().__init__()
        self.model_graph = model_graph
        self.ordered_layers = ordered_layers
        self.layer_map = {
            layer["id"]: layer
            for layer in model_graph.get("layers", [])
        }
        self.predecessors = build_predecessor_map(model_graph)
        self.modules_by_id = nn.ModuleDict(modules)

    def forward(self, x):
        """按拓扑顺序执行模型图。

        参数：
            x：模型输入张量；如果存在多个 Input 节点，也可以传入 {input_id: tensor} 字典。

        返回：
            最后一个拓扑节点的输出张量；如果存在多个输出节点，返回 {node_id: tensor} 字典。
        """
        outputs = {}

        for layer_config in self.ordered_layers:
            layer_id = layer_config["id"]
            layer_type = layer_config["type"]

            if layer_type == "Input":
                outputs[layer_id] = _resolve_input_tensor(x, layer_id)
                continue

            node_input = self._collect_node_input(layer_id, outputs)

            if layer_type == "Output":
                outputs[layer_id] = node_input
                continue

            module = self.modules_by_id[layer_id]
            outputs[layer_id] = module(node_input)

        output_ids = self._get_output_node_ids()
        if len(output_ids) == 1:
            return outputs[output_ids[0]]

        return {
            output_id: outputs[output_id]
            for output_id in output_ids
        }

    def _collect_node_input(self, layer_id, outputs):
        """收集并合并当前节点的所有前驱输出。"""
        predecessor_ids = self.predecessors[layer_id]

        tensors = [
            outputs[predecessor_id]
            for predecessor_id in predecessor_ids
        ]
        if len(tensors) == 1:
            return tensors[0]

        layer_config = self.layer_map[layer_id]
        return _merge_tensors(layer_config, tensors)

    def _get_output_node_ids(self):
        """获取模型输出节点 id。"""
        explicit_output_ids = [
            layer["id"]
            for layer in self.ordered_layers
            if layer["type"] == "Output"
        ]
        if explicit_output_ids:
            return explicit_output_ids

        successor_map = build_successor_map(self.model_graph)
        terminal_ids = [
            layer_id
            for layer_id, successors in successor_map.items()
            if not successors
        ]

        return terminal_ids


def create_layer(layer_config, input_shape=None):
    """根据一个可视化层配置创建对应的 PyTorch 层。

    参数：
        layer_config：单个层节点配置，包含层类型、层名称和参数。
        input_shape：validator 已推导出的该层输入张量形状；默认为 None。

    返回：
        后续应返回对应的 PyTorch 层对象。
    """
    layer_type = layer_config["type"]
    layer_params = layer_config.get("params", {})

    if layer_type == "Input":
        return None

    if layer_type == "Output":
        return None

    if layer_type == 'Conv2D':
        return nn.Conv2d(
            in_channels=input_shape[0],
            out_channels=layer_params['out_channels'],
            kernel_size=layer_params.get("kernel_size", 3),
            stride=layer_params.get("stride", 1),
            padding=layer_params.get("padding", 0),
            padding_mode=layer_params.get("padding_mode", "zeros")
        )
    
    if layer_type == 'ReLU':
        return nn.ReLU()
    
    if layer_type == 'Flatten':
        return nn.Flatten()
    
    if layer_type == 'Linear':
        return nn.Linear(
            in_features=input_shape[0],
            out_features=layer_params["out_features"]
        )
    
    if layer_type == 'Pooling':
        return nn.MaxPool2d(
            kernel_size=layer_params.get("kernel_size", 2),
            stride=layer_params.get("stride", layer_params.get("kernel_size", 2)),
            padding=layer_params.get("padding", 0)
        )
    
    if layer_type == "Dropout":
        return nn.Dropout(
            p=layer_params.get("p", 0.5)
        )


def order_layers(model_graph):
    """将画布中的模型节点排序为拓扑执行顺序。

    参数：
        model_graph：前端画布生成的模型图结构，包含节点和连接关系。

    返回：
        返回按依赖关系排序后的层配置列表。该排序支持分支和汇合结构，
        但要求模型图必须是有向无环图。
    """
    return topological_sort_layers(model_graph)


def _resolve_input_tensor(x, layer_id):
    """根据输入节点 id 获取输入张量。"""
    if isinstance(x, dict):
        if layer_id not in x:
            raise ValueError(f"缺少输入节点 {layer_id} 对应的输入张量")
        return x[layer_id]

    return x


def _merge_tensors(layer_config, tensors):
    """合并多个前驱节点输出。

    目标节点可通过 params.merge 指定合并方式：
        concat：按 params.dim 或 params.concat_dim 指定维度拼接，默认 dim=1；
        add/sum：逐元素相加。
    """
    params = layer_config.get("params", {})
    merge_mode = params.get("merge", "concat")

    if merge_mode == "concat":
        concat_dim = params.get("dim", params.get("concat_dim", 1))
        return torch.cat(tensors, dim=concat_dim)

    if merge_mode in ("add", "sum"):
        merged = tensors[0]
        for tensor in tensors[1:]:
            merged = merged + tensor
        return merged


def extract_model_summary(model):
    """生成便于展示或调试的模型结构摘要。

    参数：
        model：已经构建好的 GraphModel 模型对象。

    返回：
        dict：模型摘要，包含逐层信息（id、类型、名称、参数量）、
        总参数量和可训练参数量。
    """
    layers = []
    total_params = 0
    trainable_params = 0

    for layer_config in getattr(model, "ordered_layers", []):
        layer_id = layer_config["id"]
        layer_type = layer_config.get("type")
        module = model.modules_by_id.get(layer_id) if hasattr(model, "modules_by_id") else None

        layer_param_count = 0
        if module is not None:
            layer_param_count = sum(
                parameter.numel()
                for parameter in module.parameters()
            )

        layers.append({
            "id": layer_id,
            "type": layer_type,
            "name": layer_config.get("name"),
            "params": layer_config.get("params", {}),
            "num_parameters": layer_param_count,
        })

    for parameter in model.parameters():
        total_params += parameter.numel()
        if parameter.requires_grad:
            trainable_params += parameter.numel()

    return {
        "layers": layers,
        "total_parameters": total_params,
        "trainable_parameters": trainable_params,
    }
