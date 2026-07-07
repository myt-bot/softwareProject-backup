"""模型图结构工具函数。"""

import json


def normalize_model_graph(model_graph):
    """将 JSON 字符串或字典形式的模型图统一成字典。"""
    if isinstance(model_graph, str):
        return json.loads(model_graph)

    return model_graph


def topological_sort_layers(model_graph):
    """根据 connections 返回拓扑排序后的 layer_config 列表。"""
    # DAG拓扑排序
    model_graph = normalize_model_graph(model_graph)
    layers = model_graph.get("layers", [])
    connections = model_graph.get("connections", [])

    if not connections:
        return layers

    layer_map = {
        layer["id"]: layer
        for layer in layers
    }
    successors = build_successor_map(model_graph)
    in_degree = {
        layer_id: 0
        for layer_id in layer_map
    }

    for connection in connections:
        target = connection["target"]
        in_degree[target] += 1

    ready_nodes = [
        layer_id
        for layer_id in layer_map
        if in_degree[layer_id] == 0
    ]
    ordered_ids = []

    while ready_nodes:
        current_id = ready_nodes.pop(0)
        ordered_ids.append(current_id)

        for target_id in successors[current_id]:
            in_degree[target_id] -= 1
            if in_degree[target_id] == 0:
                ready_nodes.append(target_id)

    return [
        layer_map[layer_id]
        for layer_id in ordered_ids
    ]


def build_predecessor_map(model_graph):
    """根据 connections 生成每个节点的前驱节点列表。用于知道该节点的输入节点，后续可进行输入合并"""
    model_graph = normalize_model_graph(model_graph)
    layers = model_graph.get("layers", [])
    predecessors = {
        layer["id"]: []
        for layer in layers
    }

    for connection in model_graph.get("connections", []):
        source = connection["source"]
        target = connection["target"]
        predecessors[target].append(source)

    return predecessors


def build_successor_map(model_graph):
    """根据 connections 生成每个节点的后继节点列表。用于拓扑排序"""
    model_graph = normalize_model_graph(model_graph)
    layers = model_graph.get("layers", [])
    successors = {
        layer["id"]: []
        for layer in layers
    }

    for connection in model_graph.get("connections", []):
        source = connection["source"]
        target = connection["target"]
        successors[source].append(target)

    return successors
