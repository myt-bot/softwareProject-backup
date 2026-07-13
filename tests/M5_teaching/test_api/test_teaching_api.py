from fastapi.testclient import TestClient

from backend.main import app
from backend.teaching import list_supported_layers


client = TestClient(app)


def layer(layer_id, layer_type, params=None):
    return {"id": layer_id, "type": layer_type, "params": params or {}}


def connection(source, target):
    return {"source": source, "target": target}


def simple_cnn_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3}),
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2}),
            layer("flatten", "Flatten"),
            layer("linear", "Linear", {"out_features": 10}),
            layer("output", "Output"),
        ],
        "connections": [
            connection("input", "conv"),
            connection("conv", "pool"),
            connection("pool", "flatten"),
            connection("flatten", "linear"),
            connection("linear", "output"),
        ],
    }


def test_layers_returns_unique_canonical_core_list():
    response = client.get("/teaching/layers")

    assert response.status_code == 200
    layers = response.json()["layers"]
    assert layers == list_supported_layers()
    assert len(layers) == len(set(layers))
    assert "MaxPooling" not in layers


def test_layer_explanation_supports_canonical_name_and_alias():
    conv = client.get("/teaching/layers/Conv2D")
    pooling = client.get("/teaching/layers/MaxPooling")

    assert conv.status_code == 200
    assert conv.json()["known"] is True
    assert conv.json()["layer_type"] == "Conv2D"
    assert pooling.status_code == 200
    assert pooling.json()["known"] is True
    assert pooling.json()["layer_type"] == "Pooling"


def test_unknown_layer_uses_core_fallback():
    response = client.get("/teaching/layers/UnknownLayer")

    assert response.status_code == 200
    assert response.json()["known"] is False


def test_parameter_explanation_supports_canonical_name_and_aliases():
    canonical = client.get("/teaching/layers/Conv2D/parameters/kernel_size")
    aliases = client.get("/teaching/layers/conv2d/parameters/kernel-size")

    assert canonical.status_code == 200
    assert canonical.json()["known"] is True
    assert canonical.json()["parameter"] == "kernel_size"
    assert aliases.status_code == 200
    assert aliases.json()["known"] is True
    assert aliases.json()["layer_type"] == "Conv2D"
    assert aliases.json()["parameter"] == "kernel_size"


def test_unknown_parameter_uses_core_fallback():
    response = client.get("/teaching/layers/Conv2D/parameters/unknown")

    assert response.status_code == 200
    assert response.json()["known"] is False


def test_catalog_exposes_core_sections():
    response = client.get("/teaching/catalog")

    assert response.status_code == 200
    assert set(response.json()) == {"layers", "parameters", "supported_layers"}


def test_known_error_explanation_matches_category():
    response = client.post(
        "/teaching/errors/explain",
        json={"error_message": "模型缺少必要节点: Input"},
    )

    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert response.json()["category"] == "missing_input"


def test_error_context_is_forwarded_to_core_for_location():
    response = client.post(
        "/teaching/errors/explain",
        json={
            "error_message": "层 fc_2(Linear): Linear 输入维度与 in_features 不匹配",
            "context": {
                "layer_id": "fc_2",
                "layer_type": "Linear",
                "parameter": "in_features",
                "current_value": 64,
                "expected_value": 128,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["layer_id"] == "fc_2"
    assert body["layer_type"] == "Linear"
    assert body["can_locate"] is True


def test_unknown_and_non_string_errors_use_core_fallback():
    for error_message in ["unrecognized error", None, 123]:
        response = client.post(
            "/teaching/errors/explain",
            json={"error_message": error_message, "context": "bad-context"},
        )

        assert response.status_code == 200
        assert response.json()["matched"] is False
        assert response.json()["category"] == "unknown_error"


def test_model_explanation_identifies_simple_cnn():
    response = client.post(
        "/teaching/models/explain",
        json={"model_graph": simple_cnn_graph()},
    )

    assert response.status_code == 200
    assert response.json()["understood"] is True
    assert response.json()["model_family"] == "CNN"


def test_empty_or_incomplete_model_graph_uses_core_fallback():
    for model_graph in [{}, {"layers": [], "connections": []}, {"layers": "bad"}]:
        response = client.post(
            "/teaching/models/explain",
            json={"model_graph": model_graph},
        )

        assert response.status_code == 200
        assert response.json()["understood"] is False


def test_existing_health_and_validate_routes_remain_registered():
    health = client.get("/health")
    validation = client.post("/validate", json={"layers": [], "connections": []})

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert validation.status_code == 200
    assert "valid" in validation.json()
