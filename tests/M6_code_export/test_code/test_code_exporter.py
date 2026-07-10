import json
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[3]
RESULT_DIR = Path(__file__).resolve().parent / "test_result"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from local_agent.runtime.code_exporter import export_model_code, export_to_pytorch


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


def train_config(dataset_name="MNIST", batch_size=1, epochs=1):
    return {
        "dataset_name": dataset_name,
        "epochs": epochs,
        "batch_size": batch_size,
        "rate": 0.001,
        "device": "cpu",
        "loss_fn": "cross_entropy",
        "optimizer": "sgd",
        "data_dir": "",
        "artifacts_dir": "",
    }


def cnn_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
            layer("relu", "ReLU"),
            layer("pool", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
            layer("flat", "Flatten"),
            layer("fc", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "conv"),
            connection("conv", "relu"),
            connection("relu", "pool"),
            connection("pool", "flat"),
            connection("flat", "fc"),
            connection("fc", "out"),
        ],
        "train_config": train_config("MNIST"),
    }


def mlp_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [784]}),
            layer("fc1", "Linear", {"out_features": 64}),
            layer("relu", "ReLU"),
            layer("dropout", "Dropout", {"p": 0.25}),
            layer("fc2", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "fc1"),
            connection("fc1", "relu"),
            connection("relu", "dropout"),
            connection("dropout", "fc2"),
            connection("fc2", "out"),
        ],
        "train_config": train_config("MNIST"),
    }


def cifar_mlp_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [3072]}),
            layer("fc1", "Linear", {"out_features": 128}),
            layer("relu", "ReLU"),
            layer("classifier", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "fc1"),
            connection("fc1", "relu"),
            connection("relu", "classifier"),
            connection("classifier", "out"),
        ],
        "train_config": train_config("CIFAR10"),
    }


def cifar_to_grayscale_cnn_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("conv", "Conv2D", {"out_channels": 4, "kernel_size": 3, "stride": 1, "padding": 1}),
            layer("flat", "Flatten"),
            layer("classifier", "Linear", {"out_features": 10}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "conv"),
            connection("conv", "flat"),
            connection("flat", "classifier"),
            connection("classifier", "out"),
        ],
        "train_config": train_config("CIFAR10"),
    }


def lstm_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [12, 8]}),
            layer("lstm", "LSTM", {"hidden_size": 16, "num_layers": 1, "return_sequences": False, "bidirectional": True}),
            layer("fc", "Linear", {"out_features": 4}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "lstm"),
            connection("lstm", "fc"),
            connection("fc", "out"),
        ],
        "train_config": train_config("MNIST"),
    }


def add_branch_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [4]}),
            layer("left", "Linear", {"out_features": 4}),
            layer("right", "Linear", {"out_features": 4}),
            layer("merge_relu", "ReLU", {"merge": "add"}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "left"),
            connection("input", "right"),
            connection("left", "merge_relu"),
            connection("right", "merge_relu"),
            connection("merge_relu", "out"),
        ],
        "train_config": train_config("MNIST"),
    }


def concat_branch_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [4]}),
            layer("left", "Linear", {"out_features": 3}),
            layer("right", "Linear", {"out_features": 5}),
            layer("merge_relu", "ReLU", {"merge": "concat", "dim": 1}),
            layer("classifier", "Linear", {"out_features": 2}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "left"),
            connection("input", "right"),
            connection("left", "merge_relu"),
            connection("right", "merge_relu"),
            connection("merge_relu", "classifier"),
            connection("classifier", "out"),
        ],
        "train_config": train_config("MNIST"),
    }


def missing_output_graph():
    graph = cnn_graph()
    graph["layers"] = [item for item in graph["layers"] if item["type"] != "Output"]
    graph["connections"] = [item for item in graph["connections"] if item["target"] != "out"]
    return graph


def broken_connection_graph():
    graph = cnn_graph()
    graph["connections"][-1] = connection("fc", "missing_output")
    return graph


def linear_mismatch_graph():
    return {
        "layers": [
            layer("input", "Input", {"shape": [1, 28, 28]}),
            layer("fc", "Linear", {"in_features": 10, "out_features": 3}),
            layer("out", "Output"),
        ],
        "connections": [
            connection("input", "fc"),
            connection("fc", "out"),
        ],
    }


class CodeExporterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RESULT_DIR.mkdir(parents=True, exist_ok=True)

    def write_python_export(self, graph, class_name):
        source = export_to_pytorch(graph, class_name)
        path = RESULT_DIR / f"{class_name}.py"
        path.write_text(source, encoding="utf-8")
        return path, source

    def run_generated_python(self, path):
        return subprocess.run(
            [sys.executable, str(path)],
            cwd=str(RESULT_DIR),
            text=True,
            capture_output=True,
            check=True,
        )

    def test_exports_and_runs_cnn_python_code(self):
        path, source = self.write_python_export(cnn_graph(), "M6CnnModel")

        self.assertIn("class M6CnnModel(nn.Module):", source)
        self.assertIn("nn.Conv2d(in_channels=1", source)
        self.assertIn("nn.Linear(in_features=1568, out_features=10)", source)
        self.assertIn("'dataset_name': 'MNIST'", source)
        self.assertIn("def prepare_dataloaders(config):", source)
        self.assertIn("def run_training(model, config=None):", source)
        self.assertIn("parser.add_argument('--train'", source)

        completed = self.run_generated_python(path)
        self.assertIn("dataset: MNIST", completed.stdout)
        self.assertIn("(1, 10)", completed.stdout)

    def test_exports_and_runs_mlp_python_code(self):
        path, source = self.write_python_export(mlp_graph(), "M6MlpModel")

        self.assertIn("nn.Dropout(p=0.25)", source)
        self.assertIn("nn.Linear(in_features=784, out_features=64)", source)
        self.assertIn("TRAIN_CONFIG", source)

        completed = self.run_generated_python(path)
        self.assertIn("(1, 10)", completed.stdout)

    def test_exports_and_runs_lstm_python_code(self):
        path, source = self.write_python_export(lstm_graph(), "M6LstmModel")

        self.assertIn("LSTMLayer(input_size=8, hidden_size=16", source)
        self.assertIn("bidirectional=True", source)
        self.assertIn("nn.Linear(in_features=32, out_features=4)", source)
        self.assertIn("MODEL_INPUTS", source)

        completed = self.run_generated_python(path)
        self.assertIn("(1, 4)", completed.stdout)

    def test_exports_and_runs_add_branch_python_code(self):
        path, source = self.write_python_export(add_branch_graph(), "M6AddBranchModel")

        self.assertIn("sum([outputs['left'], outputs['right']][1:], [outputs['left'], outputs['right']][0])", source)

        completed = self.run_generated_python(path)
        self.assertIn("(1, 4)", completed.stdout)

    def test_exports_and_runs_concat_branch_python_code(self):
        path, source = self.write_python_export(concat_branch_graph(), "M6ConcatBranchModel")

        self.assertIn("torch.cat([outputs['left'], outputs['right']], dim=1)", source)
        self.assertIn("nn.Linear(in_features=8, out_features=2)", source)

        completed = self.run_generated_python(path)
        self.assertIn("(1, 2)", completed.stdout)

    def test_export_model_code_dispatches_python_format(self):
        source = export_model_code(cnn_graph(), "M6DispatchModel", "py")

        self.assertIn("class M6DispatchModel(nn.Module):", source)
        self.assertIn("TRAIN_CONFIG", source)
        self.assertNotIn('"nbformat"', source)

    def test_export_rejects_unsupported_format(self):
        with self.assertRaisesRegex(ValueError, "不支持的导出格式: markdown"):
            export_model_code(cnn_graph(), "M6UnsupportedFormat", "markdown")

    def test_explicit_train_config_overrides_embedded_graph_config(self):
        source = export_model_code(
            cnn_graph(),
            "M6TrainConfigModel",
            "py",
            train_config={
                "dataset_name": "CIFAR100",
                "epochs": 3,
                "batch_size": 16,
                "learning_rate": 0.02,
                "device": "cuda",
                "loss_fn": "mse",
                "optimizer": "adam",
                "data_dir": "datasets/custom",
                "artifacts_dir": "runs/custom",
            },
        )

        self.assertIn("'dataset_name': 'CIFAR100'", source)
        self.assertIn("'epochs': 3", source)
        self.assertIn("'batch_size': 16", source)
        self.assertIn("'rate': 0.02", source)
        self.assertIn("'device': 'cuda'", source)
        self.assertIn("'loss_fn': 'mse'", source)
        self.assertIn("'optimizer': 'adam'", source)
        self.assertIn("'data_dir': 'datasets/custom'", source)
        self.assertIn("'artifacts_dir': 'runs/custom'", source)

    def test_exports_valid_ipynb_file(self):
        notebook_json = export_model_code(cnn_graph(), "M6NotebookModel", "ipynb")
        path = RESULT_DIR / "M6NotebookModel.ipynb"
        path.write_text(notebook_json, encoding="utf-8")

        notebook = json.loads(path.read_text(encoding="utf-8"))
        markdown_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "markdown"]
        code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        markdown_text = "\n".join("".join(cell["source"]) for cell in markdown_cells)

        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual(notebook["cells"][0]["cell_type"], "markdown")
        self.assertGreaterEqual(len(markdown_cells), 10)
        self.assertGreaterEqual(len(code_cells), 10)
        self.assertIn("# M6NotebookModel", "".join(notebook["cells"][0]["source"]))
        self.assertIn("## 1. 依赖导入", markdown_text)
        self.assertIn("## 2. 数据集与训练配置", markdown_text)
        self.assertIn("## 3. 数据集加载", markdown_text)
        self.assertIn("## 5. 模型主体", markdown_text)
        self.assertIn("## 6. 结构与维度总览", markdown_text)
        self.assertIn("## 7. 训练与评估函数", markdown_text)
        self.assertIn("## 9. 使用真实数据集训练", markdown_text)
        self.assertIn("### 模块 2: `conv` (Conv2D)", markdown_text)
        self.assertIn("##### 功能", markdown_text)
        self.assertIn("##### 维度", markdown_text)
        self.assertTrue(any("class M6NotebookModel" in "".join(cell["source"]) for cell in code_cells))
        self.assertTrue(any("module_info" in "".join(cell["source"]) for cell in code_cells))
        self.assertTrue(any("def prepare_dataloaders" in "".join(cell["source"]) for cell in code_cells))
        self.assertTrue(any("'dataset_name': 'MNIST'" in "".join(cell["source"]) for cell in code_cells))

        namespace = {"__name__": "__notebook_test__"}
        with redirect_stdout(io.StringIO()):
            for cell in code_cells:
                exec(compile("".join(cell["source"]), str(path), "exec"), namespace)
        self.assertIn("model", namespace)
        self.assertIn("output", namespace)

    def test_exports_successful_mlp_ipynb_with_cifar_dataset_adapter(self):
        notebook_json = export_model_code(cifar_mlp_graph(), "M6CifarMlpNotebook", "ipynb")
        path = RESULT_DIR / "M6CifarMlpNotebook.ipynb"
        path.write_text(notebook_json, encoding="utf-8")

        notebook = json.loads(path.read_text(encoding="utf-8"))
        code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
        markdown_text = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "markdown"
        )

        self.assertIn("# M6CifarMlpNotebook", "".join(notebook["cells"][0]["source"]))
        self.assertIn("## 2. 数据集与训练配置", markdown_text)
        self.assertIn("## 3. 数据集加载", markdown_text)
        self.assertTrue(any("'dataset_name': 'CIFAR10'" in "".join(cell["source"]) for cell in code_cells))
        self.assertTrue(any("nn.Linear(in_features=3072, out_features=128)" in "".join(cell["source"]) for cell in code_cells))

        namespace = {"__name__": "__notebook_test__"}
        with redirect_stdout(io.StringIO()):
            for cell in code_cells:
                exec(compile("".join(cell["source"]), str(path), "exec"), namespace)

        sample = Image.new("RGB", (32, 32))
        transform = namespace["build_dataset_transform"]("CIFAR10", namespace["MODEL_INPUTS"])
        tensor = transform(sample)
        self.assertEqual((3072,), tuple(tensor.shape))
        self.assertEqual((1, 10), tuple(namespace["output"].shape))

    def test_dataset_transform_adapts_cifar_image_to_model_input_shape(self):
        source = export_to_pytorch(cifar_to_grayscale_cnn_graph(), "M6CifarAdapterModel")
        path = RESULT_DIR / "M6CifarAdapterModel.py"
        path.write_text(source, encoding="utf-8")

        namespace = {"__name__": "__adapter_test__"}
        with redirect_stdout(io.StringIO()):
            exec(compile(source, str(path), "exec"), namespace)

        sample = Image.new("RGB", (32, 32))
        transform = namespace["build_dataset_transform"]("CIFAR10", namespace["MODEL_INPUTS"])
        tensor = transform(sample)
        self.assertEqual((1, 28, 28), tuple(tensor.shape))

    def test_invalid_missing_output_model_cannot_export(self):
        with self.assertRaisesRegex(ValueError, "模型缺少必要节点: Output"):
            export_to_pytorch(missing_output_graph(), "InvalidMissingOutput")

    def test_invalid_broken_connection_model_cannot_export(self):
        with self.assertRaisesRegex(ValueError, "连接终点不存在: missing_output"):
            export_to_pytorch(broken_connection_graph(), "InvalidBrokenConnection")

    def test_invalid_linear_mismatch_model_cannot_export(self):
        with self.assertRaisesRegex(ValueError, "Linear 输入维度与 in_features 不匹配"):
            export_to_pytorch(linear_mismatch_graph(), "InvalidLinearMismatch")


class FrontendExportContractTests(unittest.TestCase):
    def test_export_modal_exposes_python_and_notebook_controls(self):
        modal_source = (ROOT_DIR / "frontend" / "src" / "components" / "ExportModal.vue").read_text(encoding="utf-8")

        self.assertIn("setExportFormat('py')", modal_source)
        self.assertIn("setExportFormat('ipynb')", modal_source)
        self.assertIn("mdi:language-python", modal_source)
        self.assertIn("mdi:notebook-outline", modal_source)
        self.assertIn('canvas.exportFormat === "ipynb" ? ".ipynb" : ".py"', modal_source)
        self.assertIn("canvas.exportCodeDisplay", modal_source)
        self.assertIn("downloadExportCode", modal_source)

    def test_export_action_sends_format_model_and_train_config_to_agent(self):
        actions_source = (ROOT_DIR / "frontend" / "src" / "actions.ts").read_text(encoding="utf-8")

        self.assertIn('requestAgent<ExportAgentResult>("export"', actions_source)
        self.assertIn("model: getCurrentModelGraph(canvas)", actions_source)
        self.assertIn('class_name: "GeneratedModel"', actions_source)
        self.assertIn("format: canvas.exportFormat", actions_source)
        self.assertIn("train_config: getTrainConfig(canvas)", actions_source)
        self.assertIn("canvas.exportFilename = result?.filename", actions_source)
        self.assertIn("application/x-ipynb+json;charset=utf-8", actions_source)
        self.assertIn("text/x-python;charset=utf-8", actions_source)


if __name__ == "__main__":
    unittest.main()
