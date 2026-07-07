import unittest

from backend.templates import (
    apply_template,
    create_gcn_tiny_template,
    create_lstm_template,
    create_self_attention_demo_template,
    create_seq2seq_template,
    create_transformer_encoder_tiny_template,
    create_vae_template,
    get_available_templates,
)
from local_agent.runtime.validator import infer_layer_shape, validate_model_graph


EXPECTED_TEMPLATE_KEYS = {
    "linear_classifier",
    "mlp",
    "perceptron",
    "lenet",
    "resnet_tiny",
    "lstm",
    "seq2seq",
    "transformer_encoder_tiny",
    "self_attention_demo",
    "vae",
    "gcn_tiny",
}


def layer(layer_id, layer_type, params=None):
    return {
        "id": layer_id,
        "type": layer_type,
        "params": params or {},
    }


def graph_with_single_layer(target_layer):
    return {
        "layers": [
            layer("input", "Input", {"shape": target_layer["input_shape"]}),
            layer("target", target_layer["type"], target_layer["params"]),
            layer("output", "Output"),
        ],
        "connections": [
            {"source": "input", "target": "target"},
            {"source": "target", "target": "output"},
        ],
    }


class TemplateUnitTests(unittest.TestCase):
    def test_get_available_templates_returns_expected_keys(self):
        templates = get_available_templates()
        keys = {template["key"] for template in templates}

        self.assertEqual(EXPECTED_TEMPLATE_KEYS, keys)
        self.assertEqual(11, len(templates))
        for template in templates:
            self.assertIn("name", template)
            self.assertIn("description", template)
            self.assertIn("family", template)
            self.assertIn("input_shape", template)
            self.assertIn("output_shape", template)

    def test_all_templates_can_be_applied_and_validated(self):
        for template_key in EXPECTED_TEMPLATE_KEYS:
            with self.subTest(template_key=template_key):
                result = apply_template(template_key)

                self.assertEqual("ok", result["status"])
                self.assertIn("model", result)

                validation = validate_model_graph(result["model"])
                self.assertTrue(validation["valid"], validation["errors"])
                self.assertEqual([], validation["errors"])

    def test_template_aliases_are_supported(self):
        aliases = {
            "linear": "linear_classifier",
            "cnn": "lenet",
            "transformer": "transformer_encoder_tiny",
            "self_attention": "self_attention_demo",
            "gcn": "gcn_tiny",
        }

        for alias, expected_key in aliases.items():
            with self.subTest(alias=alias):
                result = apply_template(alias)

                self.assertEqual("ok", result["status"])
                validation = validate_model_graph(result["model"])
                self.assertTrue(validation["valid"], validation["errors"])

                expected_result = apply_template(expected_key)
                self.assertEqual(expected_result["model"], result["model"])

    def test_unknown_template_returns_error_and_available_templates(self):
        result = apply_template("unknown_template")

        self.assertEqual("error", result["status"])
        self.assertIn("模板不存在", result["message"])
        self.assertEqual(EXPECTED_TEMPLATE_KEYS, set(result["available_templates"]))

    def test_lstm_template_shape_inference(self):
        graph = create_lstm_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([32], validation["shapes"]["lstm"]["output_shape"])
        self.assertEqual([4], validation["shapes"]["classifier"]["output_shape"])

    def test_seq2seq_template_shape_inference(self):
        graph = create_seq2seq_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([6, 12], validation["shapes"]["seq2seq"]["output_shape"])

    def test_transformer_encoder_template_shape_inference(self):
        graph = create_transformer_encoder_tiny_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([16, 32], validation["shapes"]["encoder"]["output_shape"])
        self.assertEqual([512], validation["shapes"]["flatten"]["output_shape"])

    def test_self_attention_template_shape_inference(self):
        graph = create_self_attention_demo_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([8, 32], validation["shapes"]["attention"]["output_shape"])
        self.assertEqual([256], validation["shapes"]["flatten"]["output_shape"])

    def test_vae_template_shape_inference(self):
        graph = create_vae_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([784], validation["shapes"]["vae"]["output_shape"])

    def test_gcn_template_shape_inference(self):
        graph = create_gcn_tiny_template()
        validation = validate_model_graph(graph)

        self.assertTrue(validation["valid"], validation["errors"])
        self.assertEqual([20, 32], validation["shapes"]["gcn1"]["output_shape"])
        self.assertEqual([20, 7], validation["shapes"]["gcn2"]["output_shape"])

    def test_new_layer_shape_helpers(self):
        cases = [
            (layer("attention", "SelfAttention", {"embed_dim": 32, "num_heads": 4}), [8, 32], [8, 32]),
            (layer("encoder", "TransformerEncoder", {"d_model": 32, "num_heads": 4}), [16, 32], [16, 32]),
            (layer("lstm", "LSTM", {"hidden_size": 32, "num_layers": 1}), [12, 8], [32]),
            (
                layer("lstm", "LSTM", {"hidden_size": 32, "num_layers": 1, "return_sequences": True}),
                [12, 8],
                [12, 32],
            ),
            (
                layer("seq2seq", "Seq2Seq", {"hidden_size": 32, "output_size": 12, "target_length": 6}),
                [10, 16],
                [6, 12],
            ),
            (layer("vae", "VAE", {"latent_dim": 32, "output_features": 784}), [1, 28, 28], [784]),
            (layer("gcn", "GraphConv", {"out_features": 7}), [20, 16], [20, 7]),
        ]

        for layer_config, input_shape, expected_shape in cases:
            with self.subTest(layer_type=layer_config["type"]):
                self.assertEqual(expected_shape, infer_layer_shape(layer_config, input_shape))

    def test_invalid_attention_head_count_is_rejected(self):
        graph = graph_with_single_layer({
            "type": "SelfAttention",
            "input_shape": [8, 30],
            "params": {"embed_dim": 30, "num_heads": 8},
        })

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("注意力维度" in error or "num_heads" in error for error in result["errors"]))

    def test_invalid_lstm_boolean_parameter_is_rejected(self):
        graph = graph_with_single_layer({
            "type": "LSTM",
            "input_shape": [12, 8],
            "params": {"hidden_size": 32, "return_sequences": "yes"},
        })

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("return_sequences" in error and "布尔值" in error for error in result["errors"]))

    def test_invalid_graph_conv_parameter_is_rejected(self):
        graph = graph_with_single_layer({
            "type": "GraphConv",
            "input_shape": [20, 16],
            "params": {},
        })

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("out_features 必须是正整数" in error for error in result["errors"]))


class TemplateModelBuilderUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import torch  # noqa: F401
            from local_agent.runtime.model_builder import create_layer
        except ModuleNotFoundError as exc:
            cls.skip_reason = f"缺少依赖，跳过 model_builder 构建测试: {exc}"
            cls.create_layer = None
        else:
            cls.skip_reason = None
            cls.create_layer = staticmethod(create_layer)

    def setUp(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)

    def test_create_layer_returns_modules_for_template_layers(self):
        cases = [
            ({"id": "attention", "type": "SelfAttention", "params": {"embed_dim": 32, "num_heads": 4}}, [8, 32]),
            (
                {
                    "id": "encoder",
                    "type": "TransformerEncoder",
                    "params": {"d_model": 32, "num_heads": 4, "num_layers": 1, "dim_feedforward": 64},
                },
                [16, 32],
            ),
            ({"id": "lstm", "type": "LSTM", "params": {"hidden_size": 32, "num_layers": 1}}, [12, 8]),
            (
                {
                    "id": "seq2seq",
                    "type": "Seq2Seq",
                    "params": {"hidden_size": 32, "output_size": 12, "target_length": 6},
                },
                [10, 16],
            ),
            ({"id": "vae", "type": "VAE", "params": {"latent_dim": 32, "output_features": 784}}, [1, 28, 28]),
            ({"id": "gcn", "type": "GraphConv", "params": {"out_features": 7}}, [20, 16]),
        ]

        for layer_config, input_shape in cases:
            with self.subTest(layer_type=layer_config["type"]):
                module = self.create_layer(layer_config, input_shape)
                self.assertIsNotNone(module)
                self.assertTrue(hasattr(module, "forward"))


if __name__ == "__main__":
    unittest.main()

