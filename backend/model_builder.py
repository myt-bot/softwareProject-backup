"""根据可视化模型 JSON 构建 PyTorch 模型。"""

import json

import torch
import torch.nn as nn

from .validator import infer_all_shapes


def build_model(model_graph):
    """将模型图转换成支持非顺序结构的 PyTorch 图模型。

    参数：
        model_graph：前端画布生成的模型图结构，包含层节点列表和节点连接关系。

    返回：
        GraphModel：支持 DAG 前向传播的 PyTorch 模型。
    """
    normalized_graph = _normalize_model_graph(model_graph)
    ordered_layers = order_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph)

    if shape_info is None:
        raise ValueError("validator.infer_all_shapes() 尚未返回维度信息，无法构建模型")

    modules = {}
    for layer_config in ordered_layers:
        layer_id = _get_field(layer_config, "id")
        layer_type = _get_field(layer_config, "type")
        input_shape = None
        if layer_type not in ("Input", "Output"):
            input_shape = _get_layer_input_shape(shape_info, layer_id)

        layer = create_layer(layer_config, input_shape)
        if layer is not None:
            modules[layer_id] = layer

    if not modules:
        raise ValueError("模型中没有可执行的 PyTorch 层")

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
            _get_field(layer, "id"): layer
            for layer in _get_field(model_graph, "layers", [])
        }
        self.predecessors = _build_predecessor_map(model_graph)
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
            layer_id = _get_field(layer_config, "id")
            layer_type = _get_field(layer_config, "type")

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
        if not predecessor_ids:
            raise ValueError(f"非 Input 节点缺少输入: {layer_id}")

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
            _get_field(layer, "id")
            for layer in self.ordered_layers
            if _get_field(layer, "type") == "Output"
        ]
        if explicit_output_ids:
            return explicit_output_ids

        successor_map = _build_successor_map(self.model_graph)
        terminal_ids = [
            layer_id
            for layer_id, successors in successor_map.items()
            if not successors
        ]
        if not terminal_ids:
            raise ValueError("模型没有可识别的输出节点")

        return terminal_ids


def create_layer(layer_config, input_shape=None):
    """根据一个可视化层配置创建对应的 PyTorch 层。

    参数：
        layer_config：单个层节点配置，包含层类型、层名称和参数。
        input_shape：该层输入张量的形状，用于推导某些层的构造参数；默认为 None。

    返回：
        后续应返回对应的 PyTorch 层对象。
    """
    layer_type = _get_field(layer_config, "type")
    layer_params = _get_field(layer_config, "params", {})

    if layer_type == "Input":
        return None

    if layer_type == "Output":
        return None

    if layer_type == 'Conv2D':
        if input_shape is None:
            raise ValueError("Conv2D 层需要 input_shape 来确定 in_channels")
     
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
        if input_shape is None:
            raise ValueError("Linear 层需要 input_shape 来确定 in_features")
        if len(input_shape) != 1:
            raise ValueError("Linear 层前需要先使用 Flatten 将输入展平成一维向量")
        
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
    
    raise ValueError(f"暂不支持的层类型: {layer_type}")


def order_layers(model_graph):
    """将画布中的模型节点排序为拓扑执行顺序。

    参数：
        model_graph：前端画布生成的模型图结构，包含节点和连接关系。

    返回：
        返回按依赖关系排序后的层配置列表。该排序支持分支和汇合结构，
        但要求模型图必须是有向无环图。
    """
    # DAG拓扑排序
    if isinstance(model_graph, str):
        model_graph = json.loads(model_graph)

    layers = _get_field(model_graph, "layers", [])
    connections = _get_field(model_graph, "connections", [])

    if not layers:
        raise ValueError("模型图中没有任何层节点")

    layer_map = {}
    for layer in layers:
        layer_id = _get_field(layer, "id")
        if layer_id in layer_map:
            raise ValueError(f"存在重复的层节点 id: {layer_id}")
        layer_map[layer_id] = layer

    if not connections:
        if len(layers) == 1:
            return layers
        raise ValueError("模型包含多个层节点时必须提供 connections 连接关系")

    layer_ids = list(layer_map.keys())
    adjacency = {layer_id: [] for layer_id in layer_ids}
    in_degree = {layer_id: 0 for layer_id in layer_ids}
    seen_connections = set()

    for connection in connections:
        source = _get_field(connection, "source")
        target = _get_field(connection, "target")

        if source not in layer_map:
            raise ValueError(f"连接起点不存在: {source}")
        if target not in layer_map:
            raise ValueError(f"连接终点不存在: {target}")
        if source == target:
            raise ValueError(f"节点 {source} 不能连接到自身")

        edge = (source, target)
        if edge in seen_connections:
            raise ValueError(f"存在重复连接: {source} -> {target}")

        seen_connections.add(edge)
        adjacency[source].append(target)
        in_degree[target] += 1

    ready_nodes = [
        layer_id
        for layer_id in layer_ids
        if in_degree[layer_id] == 0
    ]
    ordered_ids = []

    while ready_nodes:
        current_id = ready_nodes.pop(0)
        ordered_ids.append(current_id)

        for target_id in adjacency[current_id]:
            in_degree[target_id] -= 1
            if in_degree[target_id] == 0:
                ready_nodes.append(target_id)

    if len(ordered_ids) != len(layer_ids):
        cycle_ids = [
            layer_id
            for layer_id in layer_ids
            if in_degree[layer_id] > 0
        ]
        raise ValueError(f"模型连接中存在环，无法排序: {cycle_ids}")

    return [layer_map[layer_id] for layer_id in ordered_ids]


def _get_field(obj, field_name, default=None):
    """从 Pydantic 对象或 dict 中读取字段。"""
    if isinstance(obj, dict):
        return obj.get(field_name, default)

    return getattr(obj, field_name, default)


def _normalize_model_graph(model_graph):
    """将 JSON 字符串、dict 或 Pydantic 对象统一为可读取的模型图对象。"""
    if isinstance(model_graph, str):
        return json.loads(model_graph)

    return model_graph


def _build_predecessor_map(model_graph):
    """根据 connections 生成每个节点的前驱节点列表。"""
    layers = _get_field(model_graph, "layers", [])
    predecessors = {
        _get_field(layer, "id"): []
        for layer in layers
    }

    for connection in _get_field(model_graph, "connections", []):
        source = _get_field(connection, "source")
        target = _get_field(connection, "target")
        predecessors[target].append(source)

    return predecessors


def _build_successor_map(model_graph):
    """根据 connections 生成每个节点的后继节点列表。"""
    layers = _get_field(model_graph, "layers", [])
    successors = {
        _get_field(layer, "id"): []
        for layer in layers
    }

    for connection in _get_field(model_graph, "connections", []):
        source = _get_field(connection, "source")
        target = _get_field(connection, "target")
        successors[source].append(target)

    return successors


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
    params = _get_field(layer_config, "params", {})
    merge_mode = params.get("merge", "concat")

    if merge_mode == "concat":
        concat_dim = params.get("dim", params.get("concat_dim", 1))
        return torch.cat(tensors, dim=concat_dim)

    if merge_mode in ("add", "sum"):
        merged = tensors[0]
        for tensor in tensors[1:]:
            merged = merged + tensor
        return merged

    raise ValueError(f"暂不支持的多输入合并方式: {merge_mode}")


def _get_layer_input_shape(shape_info, layer_id):
    """从 validator.infer_all_shapes() 的结果中读取某层输入维度。"""
    if isinstance(shape_info, dict):
        if layer_id in shape_info:
            return _extract_input_shape(shape_info[layer_id])

        layers_info = shape_info.get("layers")
        if isinstance(layers_info, dict) and layer_id in layers_info:
            return _extract_input_shape(layers_info[layer_id])

        if isinstance(layers_info, list):
            for item in layers_info:
                if _get_field(item, "id") == layer_id or _get_field(item, "layer_id") == layer_id:
                    return _extract_input_shape(item)

    raise ValueError(f"无法从 validator.infer_all_shapes() 结果中读取 {layer_id} 的输入维度")


def _extract_input_shape(layer_shape_info):
    """从单层维度信息中提取 input_shape。"""
    input_shape = _get_field(layer_shape_info, "input_shape")
    if input_shape is None:
        input_shape = _get_field(layer_shape_info, "input")

    if input_shape is None:
        raise ValueError(f"维度信息缺少 input_shape 字段: {layer_shape_info}")

    return input_shape


def extract_model_summary(model):
    """生成便于展示或调试的模型结构摘要。

    参数：
        model：已经构建好的 PyTorch 模型对象。

    返回：
        后续应返回模型层级、参数数量和输入输出信息等摘要数据。
    """
    pass
