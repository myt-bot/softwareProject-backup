import unittest

from local_agent.runtime.validator import (
    infer_flatten_shape,
    infer_layer_shape,
    validate_model_graph,
)


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
    layers = [
        layer("input", "Input", {"shape": [1, 28, 28]}),
        layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
        layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
        layer("flatten", "Flatten"),
        layer("linear", "Linear", {"out_features": 10}),
        layer("output", "Output"),
    ]
    connections = [
        connection("input", "conv"),
        connection("conv", "pool"),
        connection("pool", "flatten"),
        connection("flatten", "linear"),
        connection("linear", "output"),
    ]
    return {"layers": layers, "connections": connections}


class ValidatorShapeUnitTests(unittest.TestCase):
    def assert_error_contains_any(self, errors, keywords):
        self.assertTrue(
            any(any(keyword in error for keyword in keywords) for error in errors),
            f"errors={errors} did not contain any of {keywords}",
        )

    def test_validate_model_graph_accepts_valid_cnn_and_infers_shapes(self):
        result = validate_model_graph(valid_cnn_graph())

        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual([8, 28, 28], result["shapes"]["conv"]["output_shape"])
        self.assertEqual([8, 14, 14], result["shapes"]["pool"]["output_shape"])
        self.assertEqual([1568], result["shapes"]["flatten"]["output_shape"])
        self.assertEqual([10], result["shapes"]["linear"]["output_shape"])

    def test_validate_model_graph_accepts_valid_mlp_and_infers_shapes(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("flatten", "Flatten"),
                layer("fc1", "Linear", {"out_features": 64}),
                layer("relu", "ReLU"),
                layer("fc2", "Linear", {"out_features": 10}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input", "flatten"),
                connection("flatten", "fc1"),
                connection("fc1", "relu"),
                connection("relu", "fc2"),
                connection("fc2", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual([784], result["shapes"]["flatten"]["output_shape"])
        self.assertEqual([64], result["shapes"]["fc1"]["output_shape"])
        self.assertEqual([10], result["shapes"]["fc2"]["output_shape"])

    def test_concat_merge_valid_graph_infers_merged_shape(self):
        graph = {
            "layers": [
                layer("input_a", "Input", {"shape": [8, 28, 28]}),
                layer("input_b", "Input", {"shape": [8, 28, 28]}),
                layer("merge", "ReLU", {"merge": "concat", "dim": 0}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input_a", "merge"),
                connection("input_b", "merge"),
                connection("merge", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual([16, 28, 28], result["shapes"]["merge"]["output_shape"])

    def test_missing_input_node_is_invalid(self):
        graph = {
            "layers": [
                layer("linear", "Linear", {"out_features": 10}),
                layer("output", "Output"),
            ],
            "connections": [connection("linear", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertIn("模型缺少必要节点: Input", result["errors"])

    def test_missing_output_node_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("flatten", "Flatten"),
            ],
            "connections": [connection("input", "flatten")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertIn("模型缺少必要节点: Output", result["errors"])

    def test_isolated_node_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("relu", "ReLU"),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("孤立" in error or "连接" in error for error in result["errors"]))

    def test_broken_connection_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "missing_output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertIn("连接终点不存在: missing_output", result["errors"])

    def test_cycle_connection_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("relu", "ReLU"),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input", "relu"),
                connection("relu", "output"),
                connection("output", "relu"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("存在环" in error for error in result["errors"]))

    def test_missing_conv2d_required_parameter_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("conv", "Conv2D", {"kernel_size": 3}),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "conv"), connection("conv", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("out_channels 必须是正整数" in error for error in result["errors"]))

    def test_invalid_conv2d_out_channels_values_are_rejected(self):
        for out_channels in (0, -1, "8"):
            with self.subTest(out_channels=out_channels):
                graph = {
                    "layers": [
                        layer("input", "Input", {"shape": [1, 28, 28]}),
                        layer("conv", "Conv2D", {"out_channels": out_channels, "kernel_size": 3}),
                        layer("output", "Output"),
                    ],
                    "connections": [connection("input", "conv"), connection("conv", "output")],
                }

                result = validate_model_graph(graph)

                self.assertFalse(result["valid"])
                self.assert_error_contains_any(result["errors"], ["out_channels", "正整数"])

    def test_conv2d_kernel_size_too_large_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 4, 4]}),
                layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 5, "stride": 1, "padding": 0}),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "conv"), connection("conv", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assert_error_contains_any(result["errors"], ["shape", "维度", "输出尺寸", "Conv2D"])

    def test_conv2d_shape_inference(self):
        output_shape = infer_layer_shape(
            layer("conv", "Conv2D", {"out_channels": 16, "kernel_size": 5, "stride": 1, "padding": 0}),
            [3, 32, 32],
        )

        self.assertEqual([16, 28, 28], output_shape)

    def test_pooling_shape_inference(self):
        output_shape = infer_layer_shape(
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
            [16, 28, 28],
        )

        self.assertEqual([16, 14, 14], output_shape)

    def test_pooling_kernel_size_too_large_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [8, 2, 2]}),
                layer("pool", "Pooling", {"kernel_size": 3, "stride": 1, "padding": 0}),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "pool"), connection("pool", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assert_error_contains_any(result["errors"], ["shape", "维度", "输出尺寸", "Pooling"])

    def test_flatten_shape_inference(self):
        self.assertEqual([1568], infer_flatten_shape([8, 14, 14]))

    def test_invalid_linear_out_features_values_are_rejected(self):
        for params in ({}, {"out_features": 0}, {"out_features": -1}, {"out_features": "10"}):
            with self.subTest(params=params):
                graph = {
                    "layers": [
                        layer("input", "Input", {"shape": [784]}),
                        layer("linear", "Linear", params),
                        layer("output", "Output"),
                    ],
                    "connections": [connection("input", "linear"), connection("linear", "output")],
                }

                result = validate_model_graph(graph)

                self.assertFalse(result["valid"])
                self.assert_error_contains_any(result["errors"], ["out_features", "正整数"])

    def test_linear_input_dimension_mismatch_is_invalid(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [1, 28, 28]}),
                layer("linear", "Linear", {"in_features": 10, "out_features": 3}),
                layer("output", "Output"),
            ],
            "connections": [connection("input", "linear"), connection("linear", "output")],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("Linear" in error and ("维度" in error or "in_features" in error) for error in result["errors"]))

    def test_invalid_dropout_p_values_are_rejected(self):
        for p in (-0.1, 1.1, "0.5"):
            with self.subTest(p=p):
                graph = {
                    "layers": [
                        layer("input", "Input", {"shape": [4]}),
                        layer("dropout", "Dropout", {"p": p}),
                        layer("output", "Output"),
                    ],
                    "connections": [connection("input", "dropout"), connection("dropout", "output")],
                }

                result = validate_model_graph(graph)

                self.assertFalse(result["valid"])
                self.assert_error_contains_any(result["errors"], ["Dropout", "p", "概率", "0 到 1"])

    def test_dangling_branch_not_reaching_output_is_invalid(self):
        graph = {
            "layers": [
                layer("input_left", "Input", {"shape": [1, 28, 28]}),
                layer("linear_left", "Linear", {"out_features": 128}),
                layer("input_right", "Input", {"shape": [1, 28, 28]}),
                layer("flatten", "Flatten"),
                layer("classifier", "Linear", {"out_features": 10}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input_left", "linear_left"),
                connection("input_right", "flatten"),
                connection("flatten", "classifier"),
                connection("classifier", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("无法到达任何 Output" in error for error in result["errors"]))

    def test_multi_input_multi_output_complete_graph_is_valid(self):
        graph = {
            "layers": [
                layer("input_a", "Input", {"shape": [4]}),
                layer("input_b", "Input", {"shape": [4]}),
                layer("merge", "ReLU", {"merge": "add"}),
                layer("hidden", "Linear", {"out_features": 8}),
                layer("matrix", "Linear", {"out_features": 4}),
                layer("mean", "Linear", {"out_features": 1}),
                layer("variance", "Linear", {"out_features": 1}),
                layer("output_matrix", "Output"),
                layer("output_mean", "Output"),
                layer("output_variance", "Output"),
            ],
            "connections": [
                connection("input_a", "merge"),
                connection("input_b", "merge"),
                connection("merge", "hidden"),
                connection("hidden", "matrix"),
                connection("hidden", "mean"),
                connection("hidden", "variance"),
                connection("matrix", "output_matrix"),
                connection("mean", "output_mean"),
                connection("variance", "output_variance"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertTrue(result["valid"])
        self.assertEqual([], result["errors"])
        self.assertEqual([4], result["shapes"]["matrix"]["output_shape"])
        self.assertEqual([1], result["shapes"]["mean"]["output_shape"])
        self.assertEqual([1], result["shapes"]["variance"]["output_shape"])

    def test_input_node_cannot_have_predecessor(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [4]}),
                layer("linear", "Linear", {"out_features": 4}),
                layer("bad_input", "Input", {"shape": [4]}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input", "linear"),
                connection("linear", "bad_input"),
                connection("bad_input", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("Input 节点不能有输入连接" in error for error in result["errors"]))

    def test_output_node_cannot_have_successor(self):
        graph = {
            "layers": [
                layer("input", "Input", {"shape": [4]}),
                layer("output", "Output"),
                layer("linear", "Linear", {"out_features": 2}),
                layer("final_output", "Output"),
            ],
            "connections": [
                connection("input", "output"),
                connection("output", "linear"),
                connection("linear", "final_output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("Output 节点不能有输出连接" in error for error in result["errors"]))

    def test_multi_input_node_requires_explicit_merge(self):
        graph = {
            "layers": [
                layer("input_a", "Input", {"shape": [4]}),
                layer("input_b", "Input", {"shape": [4]}),
                layer("relu", "ReLU"),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input_a", "relu"),
                connection("input_b", "relu"),
                connection("relu", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("没有声明合并方式" in error for error in result["errors"]))

    def test_add_merge_requires_same_input_shapes(self):
        graph = {
            "layers": [
                layer("input_a", "Input", {"shape": [8, 28, 28]}),
                layer("input_b", "Input", {"shape": [16, 28, 28]}),
                layer("merge", "ReLU", {"merge": "add"}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input_a", "merge"),
                connection("input_b", "merge"),
                connection("merge", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("add 合并要求所有输入 shape 完全一致" in error for error in result["errors"]))

    def test_concat_merge_requires_matching_non_concat_dimensions(self):
        graph = {
            "layers": [
                layer("input_a", "Input", {"shape": [8, 28, 28]}),
                layer("input_b", "Input", {"shape": [8, 32, 28]}),
                layer("merge", "ReLU", {"merge": "concat", "dim": 1}),
                layer("output", "Output"),
            ],
            "connections": [
                connection("input_a", "merge"),
                connection("input_b", "merge"),
                connection("merge", "output"),
            ],
        }

        result = validate_model_graph(graph)

        self.assertFalse(result["valid"])
        self.assertTrue(any("concat 合并要求除拼接维度外其它维度一致" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()

