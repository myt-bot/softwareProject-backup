import unittest

from fastapi.testclient import TestClient

from local_agent.main import app

try:
    from backend.main import app as backend_app
except Exception as exc:  # pragma: no cover - depends on optional backend environment.
    backend_app = None
    backend_import_error = exc
else:
    backend_import_error = None


def layer(layer_id, layer_type, params=None):
    return {
        "id": layer_id,
        "type": layer_type,
        "params": params or {},
    }


def connection(source, target):
    return {
        "source": source,
        "target": target,
    }


def valid_cnn_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
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


class ValidateApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_validate_endpoint_accepts_valid_model(self):
        response = self.client.post("/validate", json={"model": valid_cnn_graph()})

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertTrue(body["valid"])
        self.assertEqual([], body["errors"])
        self.assertEqual("结构校验通过", body["message"])
        self.assertEqual([8, 28, 28], body["shapes"]["conv"]["output_shape"])
        self.assertEqual([8, 14, 14], body["shapes"]["pool"]["output_shape"])
        self.assertEqual([1568], body["shapes"]["flatten"]["output_shape"])
        self.assertEqual([10], body["shapes"]["linear"]["output_shape"])

    def test_validate_endpoint_returns_business_validation_error(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("flatten", "Flatten"),
            ],
            "connections": [connection("input", "flatten")],
        }

        response = self.client.post("/validate", json={"model": graph})

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertFalse(body["valid"])
        self.assertIn("模型缺少必要节点: Output", body["errors"])

    def test_validate_endpoint_rejects_invalid_request_schema(self):
        response = self.client.post("/validate", json={"model": {"layers": "bad", "connections": []}})

        self.assertEqual(422, response.status_code)


class BackendValidateApiTests(unittest.TestCase):
    def setUp(self):
        if backend_app is None:
            self.skipTest(f"backend.main import unavailable: {backend_import_error}")
        self.client = TestClient(backend_app)

    def test_backend_validate_endpoint_handles_valid_and_business_invalid_models(self):
        valid_response = self.client.post("/validate", json={"model": valid_cnn_graph()})

        self.assertEqual(200, valid_response.status_code)
        valid_body = valid_response.json()
        self.assertTrue(valid_body["valid"])
        self.assertEqual([], valid_body["errors"])

        invalid_graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("flatten", "Flatten"),
            ],
            "connections": [connection("input", "flatten")],
        }
        invalid_response = self.client.post("/validate", json={"model": invalid_graph})

        self.assertEqual(200, invalid_response.status_code)
        invalid_body = invalid_response.json()
        self.assertFalse(invalid_body["valid"])
        self.assertIn("模型缺少必要节点: Output", invalid_body["errors"])


if __name__ == "__main__":
    unittest.main()

