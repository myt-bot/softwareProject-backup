import ast
from pathlib import Path

import pytest

from backend import teaching


SUPPORTED_LAYERS = [
    "Input",
    "Output",
    "Add",
    "Conv2D",
    "Pooling",
    "ReLU",
    "Flatten",
    "Linear",
    "Dropout",
    "LSTM",
    "Seq2Seq",
    "TransformerEncoder",
    "SelfAttention",
    "VAE",
    "GraphConv",
]

ADVANCED_LAYERS = [
    "LSTM",
    "Seq2Seq",
    "TransformerEncoder",
    "SelfAttention",
    "VAE",
    "GraphConv",
]

LAYER_REQUIRED_FIELDS = [
    "known",
    "layer_type",
    "display_name",
    "purpose",
    "input_requirement",
    "output_effect",
    "common_position",
    "beginner_tip",
    "common_mistakes",
]

LAYER_TEXT_FIELDS = [
    "layer_type",
    "display_name",
    "purpose",
    "input_requirement",
    "output_effect",
    "common_position",
    "beginner_tip",
]

PARAMETER_REQUIRED_FIELDS = [
    "known",
    "layer_type",
    "parameter",
    "display_name",
    "explanation",
    "recommendation",
    "increase_effect",
    "decrease_effect",
    "constraint",
    "common_mistakes",
]

PARAMETER_TEXT_FIELDS = [
    "layer_type",
    "parameter",
    "display_name",
    "explanation",
    "recommendation",
    "increase_effect",
    "decrease_effect",
    "constraint",
]

SUPPORTED_PARAMETERS = [
    ("Input", "shape"),
    ("Conv2D", "out_channels"),
    ("Conv2D", "kernel_size"),
    ("Conv2D", "stride"),
    ("Conv2D", "padding"),
    ("Pooling", "kernel_size"),
    ("Pooling", "stride"),
    ("Pooling", "padding"),
    ("Linear", "in_features"),
    ("Linear", "out_features"),
    ("Dropout", "p"),
    ("LSTM", "hidden_size"),
    ("LSTM", "num_layers"),
    ("LSTM", "bidirectional"),
    ("LSTM", "return_sequences"),
    ("Seq2Seq", "hidden_size"),
    ("Seq2Seq", "output_size"),
    ("Seq2Seq", "target_length"),
    ("Seq2Seq", "num_layers"),
    ("TransformerEncoder", "d_model"),
    ("TransformerEncoder", "num_heads"),
    ("TransformerEncoder", "num_layers"),
    ("TransformerEncoder", "dim_feedforward"),
    ("TransformerEncoder", "dropout"),
    ("SelfAttention", "embed_dim"),
    ("SelfAttention", "num_heads"),
    ("SelfAttention", "dropout"),
    ("VAE", "latent_dim"),
    ("VAE", "output_features"),
    ("GraphConv", "out_features"),
]

BOOLEAN_PARAMETERS = [
    ("LSTM", "bidirectional"),
    ("LSTM", "return_sequences"),
]

ERROR_REQUIRED_FIELDS = [
    "matched",
    "category",
    "title",
    "original_error",
    "reason",
    "suggestions",
    "related_layers",
    "related_parameters",
]

ERROR_TEXT_FIELDS = [
    "category",
    "title",
    "reason",
]

MODEL_GRAPH_REQUIRED_FIELDS = [
    "understood",
    "model_family",
    "title",
    "summary",
    "layer_count",
    "connection_count",
    "layer_type_counts",
    "flow",
    "key_layers",
    "learning_points",
    "beginner_warnings",
]

ERROR_CASES = [
    ("模型缺少必要节点: Input", "missing_input"),
    ("模型缺少必要节点: Output", "missing_output"),
    ("层 conv_1 没有输入连接，必须连接到 Input 或前一层之后", "missing_input_connection"),
    ("层 fc_2 没有输出连接，必须最终连接到 Output", "missing_output_connection"),
    ("存在孤立节点或连接异常: relu_3", "isolated_node"),
    ("模型连接中存在环，无法排序: ['relu', 'output']", "cycle_detected"),
    ("层 merge_1 收到了多个输入，但没有声明合并方式，请设置 merge 参数", "missing_merge"),
    ("层 merge_2: add 合并要求所有输入 shape 完全一致，当前收到 [[8, 28, 28], [16, 28, 28]]", "add_shape_mismatch"),
    ("层 merge_3: concat 合并要求除拼接维度外其它维度一致，当前 dim=1", "concat_shape_mismatch"),
    ("层 conv_4(Conv2D): Conv2D 输出尺寸无效，请检查 kernel_size、stride、padding 与输入 shape", "conv2d_output_shape_invalid"),
    ("Pooling 输出尺寸无效，请检查 kernel_size、stride、padding 与输入 shape", "pooling_output_shape_invalid"),
    ("层 fc_5(Linear): Linear 输入维度与 in_features 不匹配，当前输入 shape 为 [1, 28, 28]", "linear_in_features_mismatch"),
    ("层 dropout_1(Dropout): p 必须是 0 到 1 之间的数值", "dropout_p_invalid"),
    ("层 conv_6(Conv2D): out_channels 必须是正整数", "invalid_integer_parameter"),
    ("层 encoder_1(TransformerEncoder): 注意力维度必须能被 num_heads 整除", "attention_heads_mismatch"),
    ("层 custom_1(CustomLayer): 暂不支持该层类型", "unsupported_layer_type"),
]


def layer(layer_id, layer_type, params=None, name=None):
    payload = {"id": layer_id, "type": layer_type, "params": params or {}}
    if name is not None:
        payload["name"] = name
    return payload


def connection(source, target):
    return {"source": source, "target": target}


def graph(layers, connections=None):
    return {"layers": layers, "connections": connections or []}


def assert_layer_payload(payload, expected_layer_type):
    assert set(LAYER_REQUIRED_FIELDS).issubset(payload)
    assert payload["known"] is True
    assert payload["layer_type"] == expected_layer_type
    for field in LAYER_TEXT_FIELDS:
        assert isinstance(payload[field], str)
        assert payload[field].strip()
    assert isinstance(payload["common_mistakes"], list)
    assert payload["common_mistakes"]
    assert all(isinstance(item, str) and item.strip() for item in payload["common_mistakes"])


def assert_unknown_layer_payload(payload):
    assert set(LAYER_REQUIRED_FIELDS).issubset(payload)
    assert payload["known"] is False
    assert isinstance(payload["common_mistakes"], list)
    assert payload["common_mistakes"]
    for field in LAYER_TEXT_FIELDS:
        assert isinstance(payload[field], str)
        assert payload[field].strip()


def assert_parameter_payload(payload, expected_layer_type, expected_parameter):
    assert set(PARAMETER_REQUIRED_FIELDS).issubset(payload)
    assert payload["known"] is True
    assert payload["layer_type"] == expected_layer_type
    assert payload["parameter"] == expected_parameter
    for field in PARAMETER_TEXT_FIELDS:
        assert isinstance(payload[field], str)
        assert payload[field].strip()
    assert isinstance(payload["common_mistakes"], list)
    assert payload["common_mistakes"]
    assert all(isinstance(item, str) and item.strip() for item in payload["common_mistakes"])


def assert_unknown_parameter_payload(payload):
    assert set(PARAMETER_REQUIRED_FIELDS).issubset(payload)
    assert payload["known"] is False
    assert isinstance(payload["common_mistakes"], list)
    assert payload["common_mistakes"]
    for field in PARAMETER_TEXT_FIELDS:
        assert isinstance(payload[field], str)
        assert payload[field].strip()


def assert_error_payload(payload, expected_category, expected_original_error):
    assert set(ERROR_REQUIRED_FIELDS).issubset(payload)
    assert payload["matched"] is True
    assert payload["category"] == expected_category
    assert payload["original_error"] == expected_original_error
    for field in ERROR_TEXT_FIELDS:
        assert isinstance(payload[field], str)
        assert payload[field].strip()
    assert isinstance(payload["suggestions"], list)
    assert payload["suggestions"]
    assert all(isinstance(item, str) and item.strip() for item in payload["suggestions"])
    assert isinstance(payload["related_layers"], list)
    assert isinstance(payload["related_parameters"], list)


def assert_unknown_error_payload(payload, expected_original_error):
    assert set(ERROR_REQUIRED_FIELDS).issubset(payload)
    assert payload["matched"] is False
    assert payload["category"] == "unknown_error"
    assert payload["original_error"] == expected_original_error
    assert isinstance(payload["suggestions"], list)
    assert payload["suggestions"]
    assert all(isinstance(item, str) and item.strip() for item in payload["suggestions"])
    assert isinstance(payload["related_layers"], list)
    assert isinstance(payload["related_parameters"], list)


def assert_model_graph_payload(payload):
    assert set(MODEL_GRAPH_REQUIRED_FIELDS).issubset(payload)
    assert isinstance(payload["understood"], bool)
    assert isinstance(payload["model_family"], str)
    assert payload["model_family"].strip()
    assert isinstance(payload["title"], str)
    assert payload["title"].strip()
    assert isinstance(payload["summary"], str)
    assert payload["summary"].strip()
    assert isinstance(payload["layer_count"], int)
    assert payload["layer_count"] >= 0
    assert isinstance(payload["connection_count"], int)
    assert payload["connection_count"] >= 0
    assert isinstance(payload["layer_type_counts"], dict)
    assert isinstance(payload["flow"], list)
    assert isinstance(payload["key_layers"], list)
    assert isinstance(payload["learning_points"], list)
    assert isinstance(payload["beginner_warnings"], list)


def test_list_supported_layers_returns_only_unique_canonical_names():
    layers = teaching.list_supported_layers()

    assert layers == SUPPORTED_LAYERS
    assert len(layers) == 15
    assert len(layers) == len(set(layers))
    assert "MaxPooling" not in layers
    assert "maxpooling" not in layers
    assert "pooling" not in layers


def test_list_supported_layers_includes_all_advanced_layers():
    layers = teaching.list_supported_layers()

    for layer_type in ADVANCED_LAYERS:
        assert layer_type in layers


@pytest.mark.parametrize("layer_type", SUPPORTED_LAYERS)
def test_get_layer_teaching_returns_complete_payload_for_supported_layers(layer_type):
    assert_layer_payload(teaching.get_layer_teaching(layer_type), layer_type)


@pytest.mark.parametrize("layer_type", ADVANCED_LAYERS)
def test_get_layer_teaching_returns_complete_payload_for_advanced_layers(layer_type):
    payload = teaching.get_layer_teaching(layer_type)

    assert_layer_payload(payload, layer_type)
    assert any(word in payload["purpose"] + payload["input_requirement"] for word in ["序列", "图", "重建", "注意力"])


@pytest.mark.parametrize("layer_name", ["conv2d", "CONV2D", "CoNv2D"])
def test_get_layer_teaching_accepts_conv2d_case_variants(layer_name):
    assert_layer_payload(teaching.get_layer_teaching(layer_name), "Conv2D")


@pytest.mark.parametrize("alias", ["MaxPooling", "maxpooling", "pooling"])
def test_get_layer_teaching_maps_pooling_aliases(alias):
    assert_layer_payload(teaching.get_layer_teaching(alias), "Pooling")


@pytest.mark.parametrize(
    ("alias", "parameter", "canonical_layer"),
    [
        ("MaxPooling", "kernel_size", "Pooling"),
        ("MAX-POOLING", "stride", "Pooling"),
        ("dense", "out_features", "Linear"),
        ("gcn", "out_features", "GraphConv"),
    ],
)
def test_layer_and_parameter_queries_share_layer_normalization(alias, parameter, canonical_layer):
    layer_payload = teaching.get_layer_teaching(alias)
    parameter_payload = teaching.get_parameter_teaching(alias, parameter)

    assert layer_payload["known"] is True
    assert parameter_payload["known"] is True
    assert layer_payload["layer_type"] == canonical_layer
    assert parameter_payload["layer_type"] == canonical_layer


def test_registry_records_system_compatibility_without_listing_non_teaching_layer():
    assert teaching._LAYER_REGISTRY["Add"]["has_teaching"] is True
    assert "merge" in teaching._LAYER_REGISTRY["Add"]["compatibility_note"]
    assert teaching._LAYER_REGISTRY["Identity"]["has_teaching"] is False
    assert "Identity" not in teaching.list_supported_layers()
    assert_unknown_layer_payload(teaching.get_layer_teaching("Identity"))


@pytest.mark.parametrize("unknown_layer", [None, "", "   ", 123, object(), "UnknownLayer"])
def test_get_layer_teaching_returns_unknown_payload_for_invalid_or_unknown_layers(unknown_layer):
    assert_unknown_layer_payload(teaching.get_layer_teaching(unknown_layer))


@pytest.mark.parametrize(("layer_type", "parameter"), SUPPORTED_PARAMETERS)
def test_get_parameter_teaching_returns_complete_payload_for_supported_parameters(layer_type, parameter):
    assert_parameter_payload(
        teaching.get_parameter_teaching(layer_type, parameter),
        layer_type,
        parameter,
    )


@pytest.mark.parametrize(
    ("layer_type", "parameter", "expected_layer_type", "expected_parameter"),
    [
        ("conv2d", "KERNEL_SIZE", "Conv2D", "kernel_size"),
        ("CONV2D", "kernel-size", "Conv2D", "kernel_size"),
        ("Conv2D", "kernel size", "Conv2D", "kernel_size"),
        ("Conv2D", "OutChannels", "Conv2D", "out_channels"),
        ("MaxPooling", "kernel-size", "Pooling", "kernel_size"),
        ("pooling", "STRIDE", "Pooling", "stride"),
        ("Linear", "InFeatures", "Linear", "in_features"),
        ("Linear", "out-features", "Linear", "out_features"),
        ("Dropout", "dropout_rate", "Dropout", "p"),
        ("lstm", "HiddenSize", "LSTM", "hidden_size"),
        ("LSTM", "return-sequences", "LSTM", "return_sequences"),
        ("Seq2Seq", "target-length", "Seq2Seq", "target_length"),
        ("TransformerEncoder", "d-model", "TransformerEncoder", "d_model"),
        ("TransformerEncoder", "dropout", "TransformerEncoder", "dropout"),
        ("SelfAttention", "EmbedDim", "SelfAttention", "embed_dim"),
        ("SelfAttention", "dropout-rate", "SelfAttention", "dropout"),
        ("VAE", "latent-dim", "VAE", "latent_dim"),
        ("GraphConv", "OutFeatures", "GraphConv", "out_features"),
    ],
)
def test_get_parameter_teaching_accepts_case_hyphen_and_reasonable_aliases(
    layer_type,
    parameter,
    expected_layer_type,
    expected_parameter,
):
    assert_parameter_payload(
        teaching.get_parameter_teaching(layer_type, parameter),
        expected_layer_type,
        expected_parameter,
    )


@pytest.mark.parametrize(
    ("layer_type", "parameter"),
    [
        ("UnknownLayer", "shape"),
        ("Conv2D", "unknown_parameter"),
        (None, "shape"),
        ("Input", None),
        (123, "shape"),
        ("Input", 456),
        ("", ""),
        ("LSTM", "state_size"),
        ("TransformerEncoder", "attention_dim"),
        ("SelfAttention", "hidden_size"),
        ("VAE", "num_layers"),
    ],
)
def test_get_parameter_teaching_returns_unknown_payload_for_invalid_or_unknown_inputs(layer_type, parameter):
    assert_unknown_parameter_payload(teaching.get_parameter_teaching(layer_type, parameter))


@pytest.mark.parametrize(("error_message", "expected_category"), ERROR_CASES)
def test_get_error_suggestion_matches_real_error_categories(error_message, expected_category):
    payload = teaching.get_error_suggestion(error_message)

    assert_error_payload(payload, expected_category, error_message)


@pytest.mark.parametrize(
    ("error_message", "expected_parameters"),
    [
        ("Pooling 输出尺寸无效，请检查 kernel_size、stride、padding 与输入 shape", {"kernel_size", "stride", "padding"}),
        ("层 fc_5(Linear): Linear 输入维度与 in_features 不匹配", {"in_features"}),
        ("层 encoder_1(TransformerEncoder): 注意力维度必须能被 num_heads 整除", {"num_heads"}),
    ],
)
def test_error_suggestion_includes_related_parameters_for_key_errors(error_message, expected_parameters):
    payload = teaching.get_error_suggestion(error_message)

    assert payload["matched"] is True
    assert expected_parameters.issubset(set(payload["related_parameters"]))


def test_error_suggestion_recognizes_errors_with_node_ids_and_prefixes():
    error_message = "层 block_12__merge_3: concat 合并要求除拼接维度外其它维度一致，当前 shape 不匹配"

    payload = teaching.get_error_suggestion(error_message)

    assert_error_payload(payload, "concat_shape_mismatch", error_message)


@pytest.mark.parametrize("unknown_error", [None, "", "   ", 123, "这是一个陌生错误"])
def test_get_error_suggestion_returns_unknown_payload_for_invalid_or_unmatched_errors(unknown_error):
    assert_unknown_error_payload(teaching.get_error_suggestion(unknown_error), unknown_error)


def test_error_suggestion_returns_deep_copies():
    payload = teaching.get_error_suggestion("模型缺少必要节点: Input")
    original_suggestion = payload["suggestions"][0]
    original_layer = payload["related_layers"][0]

    payload["suggestions"][0] = "changed"
    payload["related_layers"][0] = "changed"

    fresh = teaching.get_error_suggestion("模型缺少必要节点: Input")
    assert fresh["suggestions"][0] == original_suggestion
    assert fresh["related_layers"][0] == original_layer


@pytest.mark.parametrize(("layer_type", "parameter"), BOOLEAN_PARAMETERS)
def test_boolean_parameter_teaching_describes_toggle_behavior(layer_type, parameter):
    payload = teaching.get_parameter_teaching(layer_type, parameter)

    assert_parameter_payload(payload, layer_type, parameter)
    assert "布尔" in payload["constraint"]
    assert "不适用" in payload["increase_effect"]
    assert "不适用" in payload["decrease_effect"]
    assert any(word in payload["increase_effect"] + payload["decrease_effect"] for word in ["开启", "关闭"])


def test_get_teaching_catalog_contains_expected_sections_and_matches_query_interfaces():
    catalog = teaching.get_teaching_catalog()

    assert set(catalog) == {"layers", "parameters", "supported_layers"}
    assert catalog["supported_layers"] == teaching.list_supported_layers()
    assert set(catalog["layers"]) == set(SUPPORTED_LAYERS)

    for layer_type in SUPPORTED_LAYERS:
        assert catalog["layers"][layer_type] == teaching.get_layer_teaching(layer_type)

    catalog_parameters = {
        (layer_type, parameter)
        for layer_type, params in catalog["parameters"].items()
        for parameter in params
    }
    assert catalog_parameters == set(SUPPORTED_PARAMETERS)

    for layer_type, parameter in SUPPORTED_PARAMETERS:
        assert catalog["parameters"][layer_type][parameter] == teaching.get_parameter_teaching(layer_type, parameter)


def test_layer_teaching_returns_deep_copies():
    payload = teaching.get_layer_teaching("Conv2D")
    original_purpose = payload["purpose"]
    original_mistake = payload["common_mistakes"][0]

    payload["purpose"] = "changed"
    payload["common_mistakes"][0] = "changed"

    fresh = teaching.get_layer_teaching("Conv2D")
    assert fresh["purpose"] == original_purpose
    assert fresh["common_mistakes"][0] == original_mistake


def test_parameter_teaching_returns_deep_copies():
    payload = teaching.get_parameter_teaching("Conv2D", "kernel_size")
    original_explanation = payload["explanation"]
    original_mistake = payload["common_mistakes"][0]

    payload["explanation"] = "changed"
    payload["common_mistakes"][0] = "changed"

    fresh = teaching.get_parameter_teaching("Conv2D", "kernel_size")
    assert fresh["explanation"] == original_explanation
    assert fresh["common_mistakes"][0] == original_mistake


def test_advanced_layer_teaching_returns_deep_copies():
    payload = teaching.get_layer_teaching("TransformerEncoder")
    original_tip = payload["beginner_tip"]
    original_mistake = payload["common_mistakes"][0]

    payload["beginner_tip"] = "changed"
    payload["common_mistakes"][0] = "changed"

    fresh = teaching.get_layer_teaching("TransformerEncoder")
    assert fresh["beginner_tip"] == original_tip
    assert fresh["common_mistakes"][0] == original_mistake


def test_advanced_parameter_teaching_returns_deep_copies():
    payload = teaching.get_parameter_teaching("LSTM", "return_sequences")
    original_recommendation = payload["recommendation"]
    original_mistake = payload["common_mistakes"][0]

    payload["recommendation"] = "changed"
    payload["common_mistakes"][0] = "changed"

    fresh = teaching.get_parameter_teaching("LSTM", "return_sequences")
    assert fresh["recommendation"] == original_recommendation
    assert fresh["common_mistakes"][0] == original_mistake


def test_teaching_catalog_returns_deep_copies():
    catalog = teaching.get_teaching_catalog()
    original_layer_purpose = catalog["layers"]["Conv2D"]["purpose"]
    original_param_explanation = catalog["parameters"]["Conv2D"]["kernel_size"]["explanation"]

    catalog["layers"]["Conv2D"]["purpose"] = "changed"
    catalog["parameters"]["Conv2D"]["kernel_size"]["explanation"] = "changed"

    fresh = teaching.get_teaching_catalog()
    assert fresh["layers"]["Conv2D"]["purpose"] == original_layer_purpose
    assert fresh["parameters"]["Conv2D"]["kernel_size"]["explanation"] == original_param_explanation


def test_catalog_mutation_does_not_pollute_registry_or_queries():
    catalog = teaching.get_teaching_catalog()
    catalog["supported_layers"].append("Identity")
    catalog["layers"]["Pooling"]["layer_type"] = "changed"

    assert "Identity" not in teaching.list_supported_layers()
    assert teaching.get_layer_teaching("MaxPooling")["layer_type"] == "Pooling"


def test_supported_layers_list_returns_independent_lists():
    layers = teaching.list_supported_layers()
    layers.append("MaxPooling")

    fresh = teaching.list_supported_layers()
    assert fresh == SUPPORTED_LAYERS
    assert "MaxPooling" not in fresh


def test_explain_model_graph_identifies_cnn_and_counts_graph_parts():
    model = graph(
        [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
            layer("relu", "ReLU"),
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
            layer("flat", "Flatten"),
            layer("fc", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        [
            connection("input", "conv"),
            connection("conv", "relu"),
            connection("relu", "pool"),
            connection("pool", "flat"),
            connection("flat", "fc"),
            connection("fc", "out"),
        ],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert overview["model_family"] == "CNN"
    assert overview["layer_count"] == 7
    assert overview["connection_count"] == 6
    assert overview["layer_type_counts"]["Conv2D"] == 1
    assert overview["layer_type_counts"]["Pooling"] == 1
    assert [item["layer_id"] for item in overview["flow"]] == ["input", "conv", "relu", "pool", "flat", "fc", "out"]
    assert overview["key_layers"]
    assert overview["learning_points"]


def test_explain_model_graph_identifies_mlp():
    model = graph(
        [
            layer("input", "Input", {"shape": [784]}),
            layer("flat", "Flatten"),
            layer("fc1", "Linear", {"out_features": 64}),
            layer("relu", "ReLU"),
            layer("dropout", "Dropout", {"p": 0.2}),
            layer("fc2", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        [
            connection("input", "flat"),
            connection("flat", "fc1"),
            connection("fc1", "relu"),
            connection("relu", "dropout"),
            connection("dropout", "fc2"),
            connection("fc2", "out"),
        ],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert overview["model_family"] == "MLP"
    assert overview["layer_type_counts"]["Linear"] == 2


@pytest.mark.parametrize(
    ("advanced_layer", "params", "expected_family"),
    [
        ("LSTM", {"hidden_size": 32, "num_layers": 1}, "LSTM"),
        ("TransformerEncoder", {"d_model": 32, "num_heads": 4}, "Transformer"),
        ("VAE", {"latent_dim": 32, "output_features": 784}, "VAE"),
        ("GraphConv", {"out_features": 16}, "GNN"),
    ],
)
def test_explain_model_graph_identifies_advanced_model_families(advanced_layer, params, expected_family):
    model = graph(
        [
            layer("input", "Input", {"shape": [8, 32]}),
            layer("main", advanced_layer, params),
            layer("out", "Output"),
        ],
        [connection("input", "main"), connection("main", "out")],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert overview["model_family"] == expected_family
    assert overview["key_layers"]
    assert overview["learning_points"]


def test_explain_model_graph_identifies_hybrid_when_cnn_and_transformer_are_combined():
    model = graph(
        [
            layer("input", "Input", {"shape": [3, 32, 32]}),
            layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3}),
            layer("attention", "SelfAttention", {"embed_dim": 32, "num_heads": 4}),
            layer("out", "Output"),
        ],
        [connection("input", "conv"), connection("conv", "attention"), connection("attention", "out")],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["model_family"] == "Hybrid"


def test_explain_model_graph_falls_back_to_layer_order_when_flow_cannot_be_sorted():
    model = graph(
        [
            layer("input", "Input"),
            layer("a", "Linear", {"out_features": 4}),
            layer("b", "Linear", {"out_features": 4}),
            layer("out", "Output"),
        ],
        [
            connection("input", "a"),
            connection("a", "b"),
            connection("b", "a"),
            connection("b", "out"),
        ],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert [item["layer_id"] for item in overview["flow"]] == ["input", "a", "b", "out"]
    assert any("原顺序" in warning or "无法确定" in warning for warning in overview["beginner_warnings"])


@pytest.mark.parametrize("invalid_graph", [None, {}, 123, {"layers": "bad"}, {"layers": [], "connections": []}, {"layers": [], "connections": "bad"}])
def test_explain_model_graph_returns_unknown_payload_for_invalid_inputs(invalid_graph):
    overview = teaching.explain_model_graph(invalid_graph)

    assert_model_graph_payload(overview)
    assert overview["understood"] is False
    assert overview["model_family"] == "Unknown"
    assert overview["beginner_warnings"]


def test_explain_model_graph_handles_unknown_layers_without_crashing():
    model = graph(
        [
            layer("input", "Input"),
            layer("custom", "CustomLayer", {"units": 8}),
            layer("out", "Output"),
        ],
        [connection("input", "custom"), connection("custom", "out")],
    )

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert overview["model_family"] == "Unknown"
    assert overview["layer_type_counts"]["CustomLayer"] == 1
    assert any("未收录" in warning for warning in overview["beginner_warnings"])


def test_explain_model_graph_tolerates_bad_layer_and_connection_items():
    model = {
        "layers": [
            "bad-layer",
            layer("input", "Input"),
            layer("fc", "Linear", {"out_features": 2}),
            layer("out", "Output"),
        ],
        "connections": [
            "bad-connection",
            {"source": "input"},
            connection("input", "fc"),
            connection("fc", "out"),
        ],
    }

    overview = teaching.explain_model_graph(model)

    assert_model_graph_payload(overview)
    assert overview["understood"] is True
    assert overview["layer_count"] == 3
    assert overview["connection_count"] == 2
    assert overview["beginner_warnings"]


def test_explain_model_graph_returns_independent_results():
    model = graph(
        [
            layer("input", "Input"),
            layer("fc", "Linear", {"out_features": 2}),
            layer("out", "Output"),
        ],
        [connection("input", "fc"), connection("fc", "out")],
    )
    overview = teaching.explain_model_graph(model)
    original_summary = overview["summary"]
    original_flow_type = overview["flow"][0]["layer_type"]
    original_count = overview["layer_type_counts"]["Input"]

    overview["summary"] = "changed"
    overview["flow"][0]["layer_type"] = "changed"
    overview["layer_type_counts"]["Input"] = 99

    fresh = teaching.explain_model_graph(model)
    assert fresh["summary"] == original_summary
    assert fresh["flow"][0]["layer_type"] == original_flow_type
    assert fresh["layer_type_counts"]["Input"] == original_count


def test_teaching_module_uses_only_lightweight_standard_library_imports():
    source_path = Path(teaching.__file__)
    source = source_path.read_text(encoding="utf-8")
    parsed = ast.parse(source)

    imported_roots = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_roots.add(node.module.split(".")[0])

    assert imported_roots <= {"__future__", "copy", "typing"}
    assert "torch" not in imported_roots
    assert "fastapi" not in imported_roots
    assert "sqlalchemy" not in imported_roots
    assert "code_exporter" not in imported_roots
