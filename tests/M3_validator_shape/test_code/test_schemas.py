"""backend.schemas 数据结构和基础检查方法测试。"""

import pytest
from pydantic import ValidationError

from backend.schemas import (
    CodeExportRequest,
    ConnectionConfig,
    LayerConfig,
    ModelGraph,
    ModelRequest,
    TrainConfig,
    TrainRequest,
)


def unsafe_model(model_class, **values):
    """绕过 Pydantic 自动校验，用于测试普通检查方法的异常分支。"""
    if hasattr(model_class, "model_construct"):
        return model_class.model_construct(**values)
    return model_class.construct(**values)


def build_valid_model_graph():
    return ModelGraph(
        layers=[
            LayerConfig(
                id="input_1",
                type="Input",
                name="输入层",
                params={"shape": [1, 28, 28]},
            ),
            LayerConfig(
                id="output_1",
                type="Output",
                params={},
            ),
        ],
        connections=[
            ConnectionConfig(source="input_1", target="output_1"),
        ],
    )


def test_layer_config_accepts_valid_layer_and_defaults():
    layer = LayerConfig(id="conv_1", type="Conv2D")

    assert layer.id == "conv_1"
    assert layer.type == "Conv2D"
    assert layer.name is None
    assert layer.params == {}
    assert layer.check_all() == []


def test_layer_config_keeps_params():
    layer = LayerConfig(
        id="conv_1",
        type="Conv2D",
        params={
            "out_channels": 16,
            "kernel_size": 3,
            "stride": 1,
            "padding": 0,
        },
    )

    assert layer.params["out_channels"] == 16
    assert layer.params["kernel_size"] == 3
    assert layer.check_params() == []


def test_layer_config_reports_blank_id_and_type():
    layer = LayerConfig(id=" ", type="")

    assert "层节点 id 必须是非空字符串" in layer.check_id()
    assert "层  : type 必须是非空字符串" in layer.check_type()
    assert len(layer.check_all()) == 2


def test_layer_config_reports_invalid_name_and_params_when_constructed_unsafely():
    layer = unsafe_model(
        LayerConfig,
        id="bad_layer",
        type="Input",
        name=123,
        params=["not", "dict"],
    )

    assert "层 bad_layer: name 必须是字符串或 None" in layer.check_name()
    assert "层 bad_layer: params 必须是字典" in layer.check_params()
    assert len(layer.check_all()) == 2


def test_layer_config_requires_id_and_type():
    with pytest.raises(ValidationError):
        LayerConfig(type="Input")

    with pytest.raises(ValidationError):
        LayerConfig(id="input_1")


def test_connection_config_accepts_valid_connection():
    connection = ConnectionConfig(source="input_1", target="conv_1")

    assert connection.source == "input_1"
    assert connection.target == "conv_1"
    assert connection.check_all() == []


def test_connection_config_reports_blank_source_and_target():
    connection = ConnectionConfig(source="", target=" ")

    assert "连接 source 必须是非空字符串" in connection.check_source()
    assert "连接 target 必须是非空字符串" in connection.check_target()
    assert len(connection.check_all()) == 2


def test_connection_config_requires_source_and_target():
    with pytest.raises(ValidationError):
        ConnectionConfig(target="conv_1")

    with pytest.raises(ValidationError):
        ConnectionConfig(source="input_1")


def test_model_graph_parses_nested_layers_and_connections():
    graph = ModelGraph(
        layers=[
            {"id": "input_1", "type": "Input", "params": {"shape": [1, 28, 28]}},
            {"id": "output_1", "type": "Output"},
        ],
        connections=[
            {"source": "input_1", "target": "output_1"},
        ],
    )

    assert isinstance(graph.layers[0], LayerConfig)
    assert isinstance(graph.connections[0], ConnectionConfig)
    assert graph.check_all() == []


def test_model_graph_uses_empty_connections_by_default():
    graph = ModelGraph(layers=[LayerConfig(id="input_1", type="Input")])

    assert graph.connections == []
    assert graph.check_connections() == []


def test_model_graph_reports_empty_layers():
    graph = ModelGraph(layers=[])

    assert "model.layers 不能为空" in graph.check_layers()
    assert graph.check_all() == ["model.layers 不能为空"]


def test_model_graph_reports_invalid_nested_items_when_constructed_unsafely():
    graph = unsafe_model(
        ModelGraph,
        layers=["not_layer"],
        connections=["not_connection"],
    )

    assert "model.layers[0] 必须是 LayerConfig" in graph.check_layers()
    assert "model.connections[0] 必须是 ConnectionConfig" in graph.check_connections()
    assert len(graph.check_all()) == 2


def test_model_graph_requires_layers_and_list_types():
    with pytest.raises(ValidationError):
        ModelGraph()

    with pytest.raises(ValidationError):
        ModelGraph(layers="not_list")

    with pytest.raises(ValidationError):
        ModelGraph(layers=[], connections="not_list")


def test_train_config_defaults_are_valid():
    config = TrainConfig()

    assert config.dataset_name == "MNIST"
    assert config.epochs == 1
    assert config.batch_size == 64
    assert config.rate == 0.001
    assert config.device == "cpu"
    assert config.loss_fn == "cross_entropy"
    assert config.optimizer == "sgd"
    assert config.check_all() == []


def test_train_config_accepts_custom_values():
    config = TrainConfig(
        dataset_name="MNIST",
        epochs=5,
        batch_size=128,
        rate=0.01,
        device="cuda",
        loss_fn="cross_entropy",
        optimizer="adam",
    )

    assert config.epochs == 5
    assert config.batch_size == 128
    assert config.rate == 0.01
    assert config.device == "cuda"
    assert config.optimizer == "adam"
    assert config.check_all() == []


def test_train_config_reports_invalid_values():
    config = TrainConfig(
        dataset_name="",
        epochs=0,
        batch_size=-1,
        rate=0,
        device=" ",
        loss_fn="",
        optimizer="",
    )

    assert config.check_all() == [
        "dataset_name 必须是非空字符串",
        "epochs 必须是正整数",
        "batch_size 必须是正整数",
        "rate 必须是正数",
        "device 必须是非空字符串",
        "loss_fn 必须是非空字符串",
        "optimizer 必须是非空字符串",
    ]


def test_train_config_rejects_unparseable_number_types():
    with pytest.raises(ValidationError):
        TrainConfig(epochs="abc")

    with pytest.raises(ValidationError):
        TrainConfig(rate="abc")


def test_model_request_wraps_model_graph():
    graph = build_valid_model_graph()
    request = ModelRequest(model=graph)

    assert request.model == graph
    assert request.check_all() == []


def test_model_request_requires_model():
    with pytest.raises(ValidationError):
        ModelRequest()


def test_train_request_wraps_model_and_train_config():
    graph = build_valid_model_graph()
    config = TrainConfig(epochs=2)
    request = TrainRequest(model=graph, train_config=config)

    assert request.model == graph
    assert request.train_config == config
    assert request.check_all() == []


def test_train_request_reports_nested_train_config_errors():
    graph = build_valid_model_graph()
    config = TrainConfig(epochs=0, batch_size=0)
    request = TrainRequest(model=graph, train_config=config)

    assert "epochs 必须是正整数" in request.check_train_config()
    assert "batch_size 必须是正整数" in request.check_all()


def test_train_request_requires_train_config():
    graph = build_valid_model_graph()

    with pytest.raises(ValidationError):
        TrainRequest(model=graph)


def test_code_export_request_uses_default_class_name():
    graph = build_valid_model_graph()
    request = CodeExportRequest(model=graph)

    assert request.class_name == "GeneratedModel"
    assert request.check_all() == []


def test_code_export_request_accepts_custom_class_name():
    graph = build_valid_model_graph()
    request = CodeExportRequest(model=graph, class_name="MNIST_CNN")

    assert request.class_name == "MNIST_CNN"
    assert request.check_class_name() == []


def test_code_export_request_reports_blank_class_name():
    graph = build_valid_model_graph()
    request = CodeExportRequest(model=graph, class_name=" ")

    assert request.check_class_name() == ["class_name 必须是非空字符串"]
    assert request.check_all() == ["class_name 必须是非空字符串"]


def test_code_export_request_requires_model():
    with pytest.raises(ValidationError):
        CodeExportRequest()
