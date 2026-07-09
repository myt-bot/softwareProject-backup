"""模型图结构工具函数。"""

import json

# 自定义容器（组合容器）节点的类型标识。容器把一整张内部子图打包成一个命名节点，
# 子图里的 Input / Output 节点即容器对外的输入 / 输出端口（支持多输入多输出）。
CONTAINER_TYPE = "Container"

# 展平后内部层 id 的层级分隔符。用双下划线而非 "/"，保证结果 id 仍是合法的
# Python 标识符与合法的 nn.ModuleDict 键（前端按同一规则拼接以回查 shape）。
CONTAINER_ID_SEP = "__"

# 主画布连线里"容器端口"端点的分隔符：容器id::内部端口层id。展平时映射到
# 前缀化后的内部端口层（容器id__内部端口层id）。
PORT_SEP = "::"

# 容器内部 Input / Output 端口层展平后统一变成的直通层类型（原样透传张量）。
IDENTITY_TYPE = "Identity"


def normalize_model_graph(model_graph):
    """将 JSON 字符串或字典形式的模型图统一成字典。"""
    if isinstance(model_graph, str):
        return json.loads(model_graph)

    return model_graph


def prefixed_layer_id(container_id, inner_id):
    """按统一规则拼接容器内部层的层级 id（前端 store 需保持同一规则以回查 shape）。"""
    return f"{container_id}{CONTAINER_ID_SEP}{inner_id}"


def graph_has_container(model_graph):
    """判断模型图顶层是否包含自定义容器节点。"""
    model_graph = normalize_model_graph(model_graph)
    return any(
        isinstance(layer, dict) and layer.get("type") == CONTAINER_TYPE
        for layer in model_graph.get("layers", [])
    )


def flatten_graph(model_graph):
    """把含自定义容器的模型图递归展平成纯层的扁平 DAG。

    容器被就地内联：内部层 id 加容器 id 前缀（保证全局唯一），暴露参数按
    param_bindings 写入对应内部层，跨容器边界的外部连线改接到内部入口/出口层。
    对不含容器的图是幂等的（原样返回），因此可安全地在每个入口重复调用。

    参数：
        model_graph：可能含 Container 节点的模型图（前端画布导出格式）。

    返回：
        不含任何 Container 节点的扁平模型图 {layers, connections}。
    """
    model_graph = normalize_model_graph(model_graph)
    layers = model_graph.get("layers", []) or []
    connections = model_graph.get("connections", []) or []

    # 幂等快路径：顶层没有容器就无需改写
    if not any(
        isinstance(layer, dict) and layer.get("type") == CONTAINER_TYPE
        for layer in layers
    ):
        return model_graph

    layer_by_id = {
        layer["id"]: layer
        for layer in layers
        if isinstance(layer, dict) and "id" in layer
    }
    container_ids = {
        layer_id
        for layer_id, layer in layer_by_id.items()
        if layer.get("type") == CONTAINER_TYPE
    }

    flat_layers = []
    flat_connections = []

    # 1) 逐个节点落地：普通层原样保留，容器就地内联（内部子图已递归展平）
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        if layer.get("type") == CONTAINER_TYPE:
            _inline_container(layer, flat_layers, flat_connections)
        else:
            flat_layers.append(layer)

    # 2) 改写外层连线：普通端点原样保留；容器端口端点（容器id::端口层id）映射到
    #    前缀化后的内部端口直通层
    for connection in connections:
        for real_source in _resolve_endpoint(connection["source"], container_ids, layer_by_id, "outputs"):
            for real_target in _resolve_endpoint(connection["target"], container_ids, layer_by_id, "inputs"):
                flat_connections.append({"source": real_source, "target": real_target})

    return {"layers": flat_layers, "connections": flat_connections}


def _resolve_endpoint(endpoint, container_ids, layer_by_id, boundary_key):
    """把一条外层连线的端点解析成展平后真实的内部层 id 列表。

    参数：
        endpoint：连线端点。可能是普通层 id、"容器id::端口层id"、或裸容器 id。
        boundary_key："outputs"（作为连线起点时）或 "inputs"（作为终点时），
            仅在端点是裸容器 id（未指定端口）时用于兜底分发到全部输入/输出端口。
    """
    if isinstance(endpoint, str) and PORT_SEP in endpoint:
        container_id, port_id = endpoint.split(PORT_SEP, 1)
        return [prefixed_layer_id(container_id, port_id)]

    if endpoint in container_ids:
        # 裸容器 id（无端口）：兜底分发到该容器全部输入/输出端口
        return _container_boundary(layer_by_id[endpoint], boundary_key)

    return [endpoint]


def _inline_container(container, flat_layers, flat_connections):
    """把单个容器的内部子图内联进扁平图（内部子图先递归展平以支持容器嵌套）。

    内部子图里的 Input / Output 端口层展平后变成 Identity 直通层：这样外部输入可以
    连到入口端口、出口端口可以接到外部后继，且不再受"Input 不能有前驱"等校验限制。
    """
    container_id = container["id"]
    subgraph = flatten_graph(container.get("subgraph") or {})

    # 暴露参数 → 内部层参数（可选，无绑定时不生效）：{内部层 id: {参数名: 值}}
    exposed_params = container.get("params") or {}
    binding_map = {}
    for binding in container.get("param_bindings") or []:
        value = exposed_params.get(binding.get("param"))
        if value is None:
            continue
        binding_map.setdefault(binding.get("target"), {})[binding.get("key")] = value

    for layer in subgraph.get("layers", []) or []:
        if not isinstance(layer, dict):
            continue
        new_layer = dict(layer)
        new_layer["id"] = prefixed_layer_id(container_id, layer["id"])
        if layer.get("type") in ("Input", "Output"):
            # 端口层：变成直通层，维度由外部实际连接决定（不写死内部 Input 的 shape）
            new_layer["type"] = IDENTITY_TYPE
            new_layer["params"] = {}
        else:
            merged_params = dict(layer.get("params") or {})
            if layer["id"] in binding_map:
                merged_params.update(binding_map[layer["id"]])
            new_layer["params"] = merged_params
        flat_layers.append(new_layer)

    for connection in subgraph.get("connections", []) or []:
        flat_connections.append({
            "source": prefixed_layer_id(container_id, connection["source"]),
            "target": prefixed_layer_id(container_id, connection["target"]),
        })


def _container_boundary(container, key):
    """裸容器端点（未指定端口）兜底：返回容器全部输入/输出端口层的前缀化 id。

    参数：
        key："inputs"（内部 Input 端口层）或 "outputs"（内部 Output 端口层）。
    """
    container_id = container["id"]
    subgraph = container.get("subgraph") or {}
    boundary_ids = subgraph.get(key)

    if not boundary_ids:
        boundary_ids = _infer_boundary_ids(subgraph, key)

    return [prefixed_layer_id(container_id, inner_id) for inner_id in boundary_ids]


def _infer_boundary_ids(subgraph, key):
    """未显式声明端口时的兜底：inputs=内部 Input 层，outputs=内部 Output 层。"""
    layers = subgraph.get("layers", []) or []
    wanted = "Input" if key == "inputs" else "Output"
    return [
        layer["id"]
        for layer in layers
        if isinstance(layer, dict) and layer.get("type") == wanted
    ]


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
