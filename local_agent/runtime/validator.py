"""模型结构校验与张量维度推导。"""

import json

from .graph_utils import build_predecessor_map, topological_sort_layers


def validate_model_graph(model_graph):
    """执行完整模型校验，并返回错误、警告和维度信息。

    参数：
        model_graph：前端画布生成的模型图结构，包含层节点和连接关系。传入的model_graph已经从json中提取出来了

    返回：
        后续应返回校验结果字典，包括 valid、errors、warnings 和 shapes 等字段。
    """
    errors = []
    warnings = []
    shapes = {}

    if not isinstance(model_graph, dict):
        errors.append(build_error_message("INVALID_MODEL_GRAPH"))
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "shapes": shapes,
            "message": errors[0],
        }

    layers = model_graph.get("layers")
    connections = model_graph.get("connections", [])

    if not isinstance(layers, list):
        errors.append(build_error_message("INVALID_MODEL_LAYERS"))
    if not isinstance(connections, list):
        errors.append(build_error_message("INVALID_MODEL_CONNECTIONS"))

    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "shapes": shapes,
            "message": errors[0],
        }

    for node_type in validate_required_nodes(model_graph):
        errors.append(build_error_message(
            "MISSING_REQUIRED_NODE",
            {"node_type": node_type},
        ))

    errors.extend(validate_connections(model_graph))

    for layer_config in layers:
        errors.extend(validate_layer_params(layer_config))

    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "shapes": shapes,
            "message": errors[0],
        }

    try:
        shape_info = infer_all_shapes(model_graph)
    except Exception as exc:
        errors.append(build_error_message(
            "SHAPE_INFERENCE_FAILED",
            {"reason": str(exc)},
        ))
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "shapes": shapes,
            "message": errors[0],
        }

    shapes = shape_info.get("layers", {})
    for layer_id, layer_shape in shapes.items():
        if layer_shape.get("status") != "ok":
            if layer_shape.get("error"):
                errors.append(layer_shape["error"])
                continue

            layer_type = layer_shape.get("layer_type")
            if layer_type == "Linear":
                errors.append(build_error_message(
                    "LINEAR_IN_FEATURES_MISMATCH",
                    {
                        "layer_id": layer_id,
                        "layer_type": layer_type,
                        "input_shape": layer_shape.get("input_shape"),
                        "expected_in_features": layer_shape.get("expected_in_features"),
                        "actual_in_features": layer_shape.get("actual_in_features"),
                    },
                ))
                continue

            errors.append(build_error_message(
                "UNKNOWN_LAYER_SHAPE",
                {
                    "layer_id": layer_id,
                    "layer_type": layer_type,
                },
            ))

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "shapes": shapes,
        "message": "结构校验通过" if not errors else errors[0],
    }


def validate_required_nodes(model_graph):
    """检查模型图中是否包含 Input、Output 等必要节点。

    参数：
        model_graph：需要检查的模型图结构。

    返回：
        后续应返回缺失节点错误列表；没有错误时返回空列表。
    """
    required_node_types = ["Input", "Output"]
    layers = model_graph.get("layers", [])
    existing_node_types = {
        layer.get("type")
        for layer in layers
        if isinstance(layer, dict)
    }

    return [
        node_type
        for node_type in required_node_types
        if node_type not in existing_node_types
    ]
    

def validate_connections(model_graph):
    """检查是否存在缺失、重复、非法或暂不支持的连接关系。

    参数：
        model_graph：需要检查连接关系的模型图结构。

    返回：
        后续应返回连接错误列表；没有错误时返回空列表。
    """
    # DAG拓扑排序
    if isinstance(model_graph, str):
        model_graph = json.loads(model_graph)

    errors = []
    layers = model_graph.get("layers", [])
    connections = model_graph.get("connections", [])

    if not layers:
        return ["模型图中没有任何层节点"]

    layer_map = {}
    duplicate_layer_ids = set()
    for layer in layers:
        layer_id = layer["id"]
        if layer_id in layer_map:
            duplicate_layer_ids.add(layer_id)
            continue
        layer_map[layer_id] = layer

    for layer_id in sorted(duplicate_layer_ids):
        errors.append(f"存在重复的层节点 id: {layer_id}")

    if not connections:
        if len(layers) > 1:
            errors.append("模型包含多个层节点时必须提供 connections 连接关系")
        return errors

    adjacency = {layer_id: [] for layer_id in layer_map}
    predecessors = {layer_id: [] for layer_id in layer_map}
    in_degree = {layer_id: 0 for layer_id in layer_map}
    seen_connections = set()

    for connection in connections:
        source = connection["source"]
        target = connection["target"]

        if source not in layer_map:
            errors.append(f"连接起点不存在: {source}")
            continue
        if target not in layer_map:
            errors.append(f"连接终点不存在: {target}")
            continue
        if source == target:
            errors.append(f"节点 {source} 不能连接到自身")
            continue

        edge = (source, target)
        if edge in seen_connections:
            errors.append(f"存在重复连接: {source} -> {target}")
            continue

        seen_connections.add(edge)
        adjacency[source].append(target)
        predecessors[target].append(source)
        in_degree[target] += 1

    if errors:
        return errors

    input_ids = [
        layer_id
        for layer_id, layer in layer_map.items()
        if layer.get("type") == "Input"
    ]
    output_ids = [
        layer_id
        for layer_id, layer in layer_map.items()
        if layer.get("type") == "Output"
    ]

    for layer_id in input_ids:
        if predecessors[layer_id]:
            errors.append(f"Input 节点不能有输入连接: {layer_id}")

    for layer_id in output_ids:
        if adjacency[layer_id]:
            errors.append(f"Output 节点不能有输出连接: {layer_id}")

    for layer_id, layer in layer_map.items():
        layer_type = layer.get("type")
        if layer_type != "Input" and not predecessors[layer_id]:
            errors.append(f"层 {layer_id} 没有输入连接，必须连接到 Input 或前一层之后")
        if layer_type != "Output" and not adjacency[layer_id]:
            errors.append(f"层 {layer_id} 没有输出连接，必须最终连接到 Output")
        if len(predecessors[layer_id]) > 1 and not _has_explicit_merge(layer):
            errors.append(f"层 {layer_id} 收到了多个输入，但没有声明合并方式，请设置 merge 参数")
    
    isolated_nodes = [
        layer_id
        for layer_id in layer_map
        if not adjacency[layer_id] and in_degree[layer_id] == 0
    ]

    for layer_id in isolated_nodes:
        errors.append(f"存在孤立节点或连接异常: {layer_id}")

    ready_nodes = [
        layer_id
        for layer_id in layer_map
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

    if len(ordered_ids) != len(layer_map):
        cycle_ids = [
            layer_id
            for layer_id in layer_map
            if in_degree[layer_id] > 0
        ]
        errors.append(f"模型连接中存在环，无法排序: {cycle_ids}")

    if input_ids and output_ids:
        reachable_from_inputs = _collect_reachable(input_ids, adjacency)
        can_reach_outputs = _collect_reachable(output_ids, predecessors)

        for layer_id in layer_map:
            if layer_id not in reachable_from_inputs:
                errors.append(f"层 {layer_id} 不在任何 Input 出发的路径上")
            if layer_id not in can_reach_outputs:
                errors.append(f"层 {layer_id} 无法到达任何 Output，请连接到输出节点或删除该分支")

    return errors


def _has_explicit_merge(layer_config):
    """多输入节点必须显式声明合并方式，避免误把错误连接当 concat。"""
    params = layer_config.get("params", {})
    return params.get("merge") in ("concat", "add", "sum")


def _collect_reachable(start_ids, adjacency):
    """从一组起点出发收集所有可达节点。"""
    reachable = set()
    pending = list(start_ids)

    while pending:
        current_id = pending.pop(0)
        if current_id in reachable:
            continue
        reachable.add(current_id)
        pending.extend(adjacency.get(current_id, []))

    return reachable


def validate_layer_params(layer_config):
    """检查某一层的可编辑参数是否合法。

    参数：
        layer_config：单个层节点配置，包含层类型和用户填写的参数。

    返回：
        后续应返回该层的参数错误列表；没有错误时返回空列表。
    """
    errors = []

    if not isinstance(layer_config, dict):
        return [build_error_message("INVALID_LAYER_CONFIG")]

    layer_id = layer_config.get("id", "<unknown>")
    layer_type = layer_config.get("type")
    params = layer_config.get("params", {})

    if not layer_type:
        return [build_error_message("MISSING_LAYER_TYPE", {"layer_id": layer_id})]

    if not isinstance(params, dict):
        return [build_error_message("INVALID_PARAMS", {
            "layer_id": layer_id,
            "layer_type": layer_type,
        })]

    def add_error(error_code, extra_context=None):
        context = {
            "layer_id": layer_id,
            "layer_type": layer_type,
        }
        if extra_context:
            context.update(extra_context)
        errors.append(build_error_message(error_code, context))

    def is_positive_int(value):
        return isinstance(value, int) and value > 0

    def is_non_negative_int(value):
        return isinstance(value, int) and value >= 0

    def is_bool(value):
        return isinstance(value, bool)

    if layer_type == "Input":
        shape = params.get("shape")
        if not isinstance(shape, list) or not shape:
            add_error("INVALID_INPUT_SHAPE")
        elif not all(is_positive_int(dimension) for dimension in shape):
            add_error("INVALID_INPUT_SHAPE_DIMENSION")

    elif layer_type == "Conv2D":
        if not is_positive_int(params.get("out_channels")):
            add_error("INVALID_POSITIVE_INT", {"param": "out_channels"})
        if "kernel_size" in params and not is_positive_int(params.get("kernel_size")):
            add_error("INVALID_POSITIVE_INT", {"param": "kernel_size"})
        if "stride" in params and not is_positive_int(params.get("stride")):
            add_error("INVALID_POSITIVE_INT", {"param": "stride"})
        if "padding" in params and not is_non_negative_int(params.get("padding")):
            add_error("INVALID_NON_NEGATIVE_INT", {"param": "padding"})

    elif layer_type == "Pooling":
        if "kernel_size" in params and not is_positive_int(params.get("kernel_size")):
            add_error("INVALID_POSITIVE_INT", {"param": "kernel_size"})
        if "stride" in params and not is_positive_int(params.get("stride")):
            add_error("INVALID_POSITIVE_INT", {"param": "stride"})
        if "padding" in params and not is_non_negative_int(params.get("padding")):
            add_error("INVALID_NON_NEGATIVE_INT", {"param": "padding"})

    elif layer_type == "Linear":
        if not is_positive_int(params.get("out_features")):
            add_error("INVALID_POSITIVE_INT", {"param": "out_features"})

    elif layer_type == "Dropout":
        p = params.get("p", 0.5)
        if not isinstance(p, (int, float)) or not 0 <= p <= 1:
            add_error("INVALID_DROPOUT_P")

    elif layer_type in ("SelfAttention", "TransformerEncoder"):
        embed_param = "embed_dim" if layer_type == "SelfAttention" else "d_model"
        if not is_positive_int(params.get(embed_param)):
            add_error("INVALID_POSITIVE_INT", {"param": embed_param})
        if not is_positive_int(params.get("num_heads")):
            add_error("INVALID_POSITIVE_INT", {"param": "num_heads"})
        elif is_positive_int(params.get(embed_param)) and params.get(embed_param) % params.get("num_heads") != 0:
            add_error("INVALID_ATTENTION_HEADS", {"param": "num_heads"})
        if layer_type == "TransformerEncoder":
            if not is_positive_int(params.get("num_layers", 1)):
                add_error("INVALID_POSITIVE_INT", {"param": "num_layers"})
            if not is_positive_int(params.get("dim_feedforward", params.get("d_model", 1) * 4)):
                add_error("INVALID_POSITIVE_INT", {"param": "dim_feedforward"})

    elif layer_type == "LSTM":
        if not is_positive_int(params.get("hidden_size")):
            add_error("INVALID_POSITIVE_INT", {"param": "hidden_size"})
        if not is_positive_int(params.get("num_layers", 1)):
            add_error("INVALID_POSITIVE_INT", {"param": "num_layers"})
        if "bidirectional" in params and not is_bool(params.get("bidirectional")):
            add_error("INVALID_BOOL", {"param": "bidirectional"})
        if "return_sequences" in params and not is_bool(params.get("return_sequences")):
            add_error("INVALID_BOOL", {"param": "return_sequences"})

    elif layer_type == "Seq2Seq":
        if not is_positive_int(params.get("hidden_size")):
            add_error("INVALID_POSITIVE_INT", {"param": "hidden_size"})
        if not is_positive_int(params.get("output_size")):
            add_error("INVALID_POSITIVE_INT", {"param": "output_size"})
        if not is_positive_int(params.get("target_length")):
            add_error("INVALID_POSITIVE_INT", {"param": "target_length"})
        if not is_positive_int(params.get("num_layers", 1)):
            add_error("INVALID_POSITIVE_INT", {"param": "num_layers"})

    elif layer_type == "VAE":
        if not is_positive_int(params.get("latent_dim")):
            add_error("INVALID_POSITIVE_INT", {"param": "latent_dim"})
        if "output_features" in params and not is_positive_int(params.get("output_features")):
            add_error("INVALID_POSITIVE_INT", {"param": "output_features"})

    elif layer_type == "GraphConv":
        if not is_positive_int(params.get("out_features")):
            add_error("INVALID_POSITIVE_INT", {"param": "out_features"})

    elif layer_type in ("ReLU", "Flatten", "Output"):
        pass

    else:
        add_error("UNSUPPORTED_LAYER_TYPE")

    return errors


def infer_all_shapes(model_graph):
    """按执行顺序推导每一层的输入维度和输出维度。

    参数：
        model_graph：已经按规则连接的模型图结构。传入的model_graph已经从json中提取出来了

    返回：
        后续应返回每一层的 input_shape、output_shape 和推导状态。
    """

    ordered_layers = topological_sort_layers(model_graph)
    predecessors = build_predecessor_map(model_graph)
    shape_by_layer = {}

    for layer_config in ordered_layers:
        layer_id = layer_config["id"]
        # 逐层容错：任何一层推导失败都只把该层标为 unknown，不让整体崩溃，
        # 这样前端才能把"算不出尺寸"的层定位并标红。
        try:
            predecessor_shapes = [
                shape_by_layer[predecessor_id]["output_shape"]
                for predecessor_id in predecessors[layer_id]
            ]

            if not predecessor_shapes:
                input_shape = None
            elif len(predecessor_shapes) == 1:
                input_shape = predecessor_shapes[0]
            else:
                input_shape = _merge_shapes(layer_config, predecessor_shapes)

            output_shape = infer_layer_shape(layer_config, input_shape)
            inference_error = None
        except Exception as exc:
            input_shape = None
            output_shape = None
            inference_error = str(exc)

        shape_by_layer[layer_id] = {
            "layer_type": layer_config.get("type"),
            "input_shape": input_shape,
            "output_shape": output_shape,
            "status": "ok" if output_shape is not None else "unknown",
        }
        if inference_error:
            shape_by_layer[layer_id]["error"] = inference_error

        if layer_config.get("type") == "Linear":
            actual_in_features = _flattened_size(input_shape)
            if actual_in_features is not None:
                shape_by_layer[layer_id]["actual_in_features"] = actual_in_features
            if layer_config.get("params", {}).get("in_features") is not None:
                shape_by_layer[layer_id]["expected_in_features"] = layer_config.get("params", {}).get("in_features")

    return {
        "layers": shape_by_layer
    }


def _merge_shapes(layer_config, shapes):
    """根据节点合并方式推导多个前驱 shape 合并后的 shape。"""
    params = layer_config.get("params", {})
    merge_mode = params.get("merge")

    if merge_mode not in ("concat", "add", "sum"):
        raise ValueError(
            f"层 {layer_config.get('id')}: 多输入节点必须通过 params.merge 声明 concat、add 或 sum 合并方式"
        )

    if merge_mode in ("add", "sum"):
        normalized_shapes = [
            list(shape) if isinstance(shape, (list, tuple)) else shape
            for shape in shapes
        ]
        first_shape = normalized_shapes[0]
        if any(shape != first_shape for shape in normalized_shapes[1:]):
            raise ValueError(
                f"层 {layer_config.get('id')}: add 合并要求所有输入 shape 完全一致，"
                f"当前输入 shapes 为 {normalized_shapes}"
            )
        return first_shape

    concat_dim = params.get("dim", params.get("concat_dim", 1))
    shape_index = concat_dim - 1 if concat_dim > 0 else concat_dim
    merged_shape = list(shapes[0])

    if shape_index < 0:
        shape_index += len(merged_shape)

    for shape in shapes:
        if len(shape) != len(merged_shape):
            raise ValueError(
                f"层 {layer_config.get('id')}: concat 合并要求所有输入 shape 维度数量一致，"
                f"当前输入 shapes 为 {shapes}"
            )

        for dimension_index, dimension in enumerate(shape):
            if dimension_index == shape_index:
                continue
            if dimension != merged_shape[dimension_index]:
                raise ValueError(
                    f"层 {layer_config.get('id')}: concat 合并要求除拼接维度外其它维度一致，"
                    f"当前输入 shapes 为 {shapes}"
                )

    merged_shape[shape_index] = sum(shape[shape_index] for shape in shapes)

    return merged_shape


def infer_layer_shape(layer_config, input_shape):
    """根据输入维度和层参数推导某一层的输出维度。

    参数：
        layer_config：需要推导的单个层节点配置。
        input_shape：该层收到的输入张量形状。

    返回：
        后续应返回该层的输出张量形状。
    """
    if layer_config is None:
        return None

    layer_type = layer_config.get("type")
    params = layer_config.get("params", {})

    if layer_type == "Input":
        return params.get("shape", input_shape)

    if input_shape is None:
        return None

    if layer_type == "Conv2D":
        return infer_conv2d_shape(input_shape, params)

    if layer_type == "Pooling":
        return infer_pooling_shape(input_shape, params)

    if layer_type == "Flatten":
        return infer_flatten_shape(input_shape)

    if layer_type in ("ReLU", "Dropout", "Output"):
        return input_shape

    if layer_type == "Linear":
        return infer_linear_shape(input_shape, params)

    if layer_type == "SelfAttention":
        return infer_self_attention_shape(input_shape, params)

    if layer_type == "TransformerEncoder":
        return infer_transformer_encoder_shape(input_shape, params)

    if layer_type == "LSTM":
        return infer_lstm_shape(input_shape, params)

    if layer_type == "Seq2Seq":
        return infer_seq2seq_shape(input_shape, params)

    if layer_type == "VAE":
        return infer_vae_shape(input_shape, params)

    if layer_type == "GraphConv":
        return infer_graph_conv_shape(input_shape, params)

    return None


def infer_linear_shape(input_shape, params):
    """根据输入维度和 Linear 参数推导输出维度。"""
    params = params or {}
    out_features = params.get("out_features")
    in_features = params.get("in_features")

    actual_in_features = _flattened_size(input_shape)
    if actual_in_features is None:
        return None

    if in_features is not None and in_features != actual_in_features:
        return None

    return [out_features]


def infer_self_attention_shape(input_shape, params):
    """推导自注意力层输出维度，输出 shape 与输入保持一致。"""
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) < 2:
        return None

    embed_dim = params.get("embed_dim")
    if input_shape[-1] != embed_dim:
        return None

    return list(input_shape)


def infer_transformer_encoder_shape(input_shape, params):
    """推导 Transformer Encoder 输出维度，输出 shape 与输入保持一致。"""
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) < 2:
        return None

    d_model = params.get("d_model")
    if input_shape[-1] != d_model:
        return None

    return list(input_shape)


def infer_lstm_shape(input_shape, params):
    """推导 LSTM 输出维度。输入约定为 [seq_len, input_size]。"""
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) != 2:
        return None

    seq_len, _ = input_shape
    hidden_size = params.get("hidden_size")
    directions = 2 if params.get("bidirectional", False) else 1
    output_features = hidden_size * directions

    if params.get("return_sequences", False):
        return [seq_len, output_features]

    return [output_features]


def infer_seq2seq_shape(input_shape, params):
    """推导 Seq2Seq 输出维度。输入约定为 [source_length, input_size]。"""
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) != 2:
        return None

    return [params.get("target_length"), params.get("output_size")]


def infer_vae_shape(input_shape, params):
    """推导 VAE 重建输出维度，默认重建为展平后的输入长度。"""
    flattened_size = _flattened_size(input_shape)
    if flattened_size is None:
        return None

    return [params.get("output_features", flattened_size)]


def infer_graph_conv_shape(input_shape, params):
    """推导图卷积输出维度。输入约定为 [num_nodes, in_features]。"""
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) != 2:
        return None

    num_nodes, _ = input_shape
    return [num_nodes, params.get("out_features")]


def _flattened_size(input_shape):
    """返回输入 shape 展平后的元素数量；无法计算时返回 None。"""
    if not isinstance(input_shape, (list, tuple)):
        return None
    flattened_size = 1
    for dimension in input_shape:
        if not isinstance(dimension, int) or dimension <= 0:
            return None
        flattened_size *= dimension

    return flattened_size


def infer_conv2d_shape(input_shape, params):
    """根据通道数、卷积核、步长和填充推导 Conv2D 输出维度。

    参数：
        input_shape：Conv2D 层输入形状，通常为 [C, H, W]。
        params：Conv2D 参数字典，包含 out_channels、kernel_size、stride 和 padding。

    返回：
        后续应返回 Conv2D 输出形状 [out_channels, H_out, W_out]。
    """
    if not isinstance(input_shape, (list, tuple)) or len(input_shape) != 3:
        return None

    params = params or {}
    _, height, width = input_shape
    kernel_size = params.get("kernel_size", 3)
    stride = params.get("stride", 1)
    padding = params.get("padding", 0)
    out_channels = params.get("out_channels")

    values = [height, width, kernel_size, stride, padding, out_channels]
    if not all(isinstance(value, int) for value in values):
        return None
    if height <= 0 or width <= 0 or kernel_size <= 0 or stride <= 0 or padding < 0 or out_channels <= 0:
        return None

    H_out = (height + 2 * padding - kernel_size) // stride + 1
    W_out = (width + 2 * padding - kernel_size) // stride + 1

    if H_out <= 0 or W_out <= 0:
        return None

    return [out_channels, H_out, W_out]


def infer_pooling_shape(input_shape, params):
    """根据池化核、步长和填充推导池化层输出维度。

    参数：
        input_shape：池化层输入形状，通常为 [C, H, W]。
        params：池化层参数字典，包含 kernel_size、stride 和 padding。

    返回：
        后续应返回池化层输出形状 [C, H_out, W_out]。
    """
    if input_shape is None:
        return None

    channels, height, width = input_shape
    kernel_size = params.get("kernel_size", 2)
    stride = params.get("stride", kernel_size)
    padding = params.get("padding", 0)

    output_height = (height + 2 * padding - kernel_size) // stride + 1
    output_width = (width + 2 * padding - kernel_size) // stride + 1

    return [channels, output_height, output_width]


def infer_flatten_shape(input_shape):
    """根据多维张量输入推导 Flatten 后的一维向量长度。

    参数：
        input_shape：Flatten 前的输入张量形状，例如 [C, H, W]。

    返回：
        后续应返回展平后的一维形状，例如 [C * H * W]。
    """
    if input_shape is None:
        return None

    flattened_size = 1
    for dimension in input_shape:
        flattened_size *= dimension

    return [flattened_size]


def build_error_message(error_code, context=None):
    """将校验错误转换成适合初学者阅读的解释文本。

    参数：
        error_code：错误类型标识，用于决定生成哪一种错误说明。
        context：错误上下文信息，例如节点名称、参数名或当前维度；默认为 None。

    返回：
        后续应返回面向用户的中文错误解释和修改建议。
    """
    context = context or {}
    layer_id = context.get("layer_id", "<unknown>")
    layer_type = context.get("layer_type")
    param = context.get("param")

    if layer_type:
        prefix = f"层 {layer_id}({layer_type})"
    else:
        prefix = f"层 {layer_id}"

    messages = {
        "INVALID_MODEL_GRAPH": "模型图必须是字典结构",
        "INVALID_MODEL_LAYERS": "模型图的 layers 字段必须是列表",
        "INVALID_MODEL_CONNECTIONS": "模型图的 connections 字段必须是列表",
        "MISSING_REQUIRED_NODE": f"模型缺少必要节点: {context.get('node_type')}",
        "SHAPE_INFERENCE_FAILED": f"模型维度推导失败: {context.get('reason')}",
        "UNKNOWN_LAYER_SHAPE": f"层 {layer_id}: 无法推导输出维度",
        "INVALID_LAYER_CONFIG": "层配置必须是字典结构",
        "MISSING_LAYER_TYPE": f"{prefix}: 缺少 type 字段",
        "INVALID_PARAMS": f"{prefix}: params 必须是字典结构",
        "INVALID_INPUT_SHAPE": f"{prefix}: shape 必须是非空列表，例如 [1, 28, 28]",
        "INVALID_INPUT_SHAPE_DIMENSION": f"{prefix}: shape 中的每个维度都必须是正整数",
        "INVALID_POSITIVE_INT": f"{prefix}: {param} 必须是正整数",
        "INVALID_NON_NEGATIVE_INT": f"{prefix}: {param} 必须是非负整数",
        "INVALID_DROPOUT_P": f"{prefix}: p 必须是 0 到 1 之间的数值",
        "INVALID_BOOL": f"{prefix}: {param} 必须是布尔值 true 或 false",
        "INVALID_ATTENTION_HEADS": f"{prefix}: 注意力维度必须能被 num_heads 整除",
        "UNSUPPORTED_LAYER_TYPE": f"{prefix}: 暂不支持该层类型",
        "LINEAR_IN_FEATURES_MISMATCH": (
            f"{prefix}: Linear 输入维度与 in_features 不匹配，"
            f"当前输入 shape 为 {context.get('input_shape')}，"
            f"展平后维度为 {context.get('actual_in_features')}，"
            f"in_features 为 {context.get('expected_in_features')}"
        ),
    }

    return messages.get(error_code, f"{prefix}: 未知校验错误 {error_code}")
