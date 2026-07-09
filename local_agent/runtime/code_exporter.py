"""根据可视化模型定义生成可运行的 PyTorch 代码。"""

import json
import keyword
import re
from typing import Any

from .graph_utils import build_predecessor_map, flatten_graph, topological_sort_layers
from .validator import infer_all_shapes, validate_model_graph


SUPPORTED_FORMATS = {"py", "ipynb"}


def export_to_pytorch(model_graph, class_name="GeneratedModel", train_config=None):
    """根据可视化模型图生成完整的 PyTorch 模型源代码。"""
    return export_model_code(model_graph, class_name=class_name, export_format="py", train_config=train_config)


def export_model_code(model_graph, class_name="GeneratedModel", export_format="py", train_config=None):
    """导出 PyTorch 模型代码。

    export_format 支持：
        py：返回 Python 源码字符串。
        ipynb：返回 Jupyter Notebook JSON 字符串。
    """
    export_format = (export_format or "py").lower()
    if export_format not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的导出格式: {export_format}")

    normalized_graph = _normalize_graph(model_graph)
    export_train_config = _extract_train_config(normalized_graph, train_config)

    source_code = format_python_code(
        "\n\n".join([
            generate_imports(),
            generate_helper_layers(),
            generate_model_class(normalized_graph, class_name),
            generate_training_config(export_train_config),
            generate_model_metadata(normalized_graph),
            generate_dataset_helpers(),
            generate_training_helpers(),
            generate_smoke_test(normalized_graph, class_name),
        ])
    )

    if export_format == "ipynb":
        return generate_notebook(source_code, normalized_graph, class_name, export_train_config)

    return source_code


def generate_imports():
    """生成导出代码所需的 import 语句。"""
    return "\n".join([
        "import argparse",
        "import os",
        "import torch",
        "import torch.nn as nn",
        "import torch.utils.data",
        "import torchvision",
    ])


def generate_helper_layers():
    """生成高级层所需的辅助 nn.Module。"""
    return r'''
class SelfAttentionBlock(nn.Module):
    def __init__(self, embed_dim, num_heads, dropout=0.0):
        super().__init__()
        self.attention = nn.MultiheadAttention(
            embed_dim=embed_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True,
        )

    def forward(self, x):
        output, _ = self.attention(x, x, x)
        return output


class LSTMLayer(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers=1, bidirectional=False, return_sequences=False):
        super().__init__()
        self.return_sequences = return_sequences
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            bidirectional=bidirectional,
            batch_first=True,
        )

    def forward(self, x):
        output, _ = self.lstm(x)
        if self.return_sequences:
            return output
        return output[:, -1, :]


class Seq2SeqLayer(nn.Module):
    def __init__(self, input_size, hidden_size, output_size, target_length, num_layers=1):
        super().__init__()
        self.target_length = target_length
        self.encoder = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
        )
        self.decoder_cell = nn.LSTM(
            input_size=output_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
        )
        self.initial_decoder_input = nn.Parameter(torch.zeros(1, 1, output_size))
        self.output_projection = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        batch_size = x.size(0)
        _, hidden = self.encoder(x)
        decoder_input = self.initial_decoder_input.expand(batch_size, self.target_length, -1)
        decoder_output, _ = self.decoder_cell(decoder_input, hidden)
        return self.output_projection(decoder_output)


class VAELayer(nn.Module):
    def __init__(self, input_features, latent_dim, output_features):
        super().__init__()
        self.encoder_mu = nn.Linear(input_features, latent_dim)
        self.encoder_logvar = nn.Linear(input_features, latent_dim)
        self.decoder = nn.Linear(latent_dim, output_features)

    def forward(self, x):
        x = torch.flatten(x, start_dim=1)
        mu = self.encoder_mu(x)
        logvar = self.encoder_logvar(x)
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std
        return self.decoder(z)


class GraphConvLayer(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.projection = nn.Linear(in_features, out_features)

    def forward(self, x):
        adjacency = None
        if isinstance(x, dict):
            adjacency = x.get("adj")
            x = x.get("x")

        support = self.projection(x)
        if adjacency is None:
            return support
        return torch.matmul(adjacency, support)
'''.strip()


def generate_model_class(model_graph, class_name):
    """生成导出模型对应的 nn.Module 类主体。"""
    normalized_graph = _normalize_graph(model_graph)
    _ensure_valid_graph(normalized_graph)

    class_name = _safe_class_name(class_name)
    ordered_layers = topological_sort_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph).get("layers", {})

    init_lines = [
        f"class {class_name}(nn.Module):",
        "    def __init__(self):",
        "        super().__init__()",
    ]

    module_lines = []
    for layer_config in ordered_layers:
        layer_type = layer_config.get("type")
        if layer_type in ("Input", "Output"):
            continue

        layer_id = layer_config["id"]
        input_shape = shape_info.get(layer_id, {}).get("input_shape")
        layer_code = generate_layer_code(layer_config, input_shape)
        if layer_code:
            module_lines.append(f"        self.{_module_name(layer_id)} = {layer_code}")

    init_lines.extend(module_lines or ["        pass"])

    return "\n".join(init_lines + ["", generate_forward_method(normalized_graph)])


def generate_layer_code(layer_config, input_shape=None):
    """生成某一个 PyTorch 层的构造表达式。"""
    layer_type = layer_config["type"]
    params = layer_config.get("params", {}) or {}

    if layer_type == "Conv2D":
        return (
            "nn.Conv2d("
            f"in_channels={input_shape[0]}, "
            f"out_channels={params['out_channels']}, "
            f"kernel_size={params.get('kernel_size', 3)}, "
            f"stride={params.get('stride', 1)}, "
            f"padding={params.get('padding', 0)}, "
            f"padding_mode={_repr(params.get('padding_mode', 'zeros'))}"
            ")"
        )

    if layer_type == "ReLU":
        return "nn.ReLU()"

    if layer_type == "Identity":
        return "nn.Identity()"

    if layer_type == "Flatten":
        return "nn.Flatten()"

    if layer_type == "Linear":
        return f"nn.Linear(in_features={input_shape[0]}, out_features={params['out_features']})"

    if layer_type == "Pooling":
        kernel_size = params.get("kernel_size", 2)
        return (
            "nn.MaxPool2d("
            f"kernel_size={kernel_size}, "
            f"stride={params.get('stride', kernel_size)}, "
            f"padding={params.get('padding', 0)}"
            ")"
        )

    if layer_type == "Dropout":
        return f"nn.Dropout(p={params.get('p', 0.5)})"

    if layer_type == "SelfAttention":
        return (
            "SelfAttentionBlock("
            f"embed_dim={params['embed_dim']}, "
            f"num_heads={params['num_heads']}, "
            f"dropout={params.get('dropout', 0.0)}"
            ")"
        )

    if layer_type == "TransformerEncoder":
        dim_feedforward = params.get("dim_feedforward", params["d_model"] * 4)
        return (
            "nn.TransformerEncoder("
            "encoder_layer=nn.TransformerEncoderLayer("
            f"d_model={params['d_model']}, "
            f"nhead={params['num_heads']}, "
            f"dim_feedforward={dim_feedforward}, "
            f"dropout={params.get('dropout', 0.1)}, "
            "batch_first=True"
            "), "
            f"num_layers={params.get('num_layers', 1)}"
            ")"
        )

    if layer_type == "LSTM":
        return (
            "LSTMLayer("
            f"input_size={input_shape[-1]}, "
            f"hidden_size={params['hidden_size']}, "
            f"num_layers={params.get('num_layers', 1)}, "
            f"bidirectional={params.get('bidirectional', False)}, "
            f"return_sequences={params.get('return_sequences', False)}"
            ")"
        )

    if layer_type == "Seq2Seq":
        return (
            "Seq2SeqLayer("
            f"input_size={input_shape[-1]}, "
            f"hidden_size={params['hidden_size']}, "
            f"output_size={params['output_size']}, "
            f"target_length={params['target_length']}, "
            f"num_layers={params.get('num_layers', 1)}"
            ")"
        )

    if layer_type == "VAE":
        input_features = _flattened_size(input_shape)
        return (
            "VAELayer("
            f"input_features={input_features}, "
            f"latent_dim={params['latent_dim']}, "
            f"output_features={params.get('output_features', input_features)}"
            ")"
        )

    if layer_type == "GraphConv":
        return f"GraphConvLayer(in_features={input_shape[-1]}, out_features={params['out_features']})"

    raise ValueError(f"暂不支持导出层类型: {layer_type}")


def generate_forward_method(model_graph):
    """生成导出 PyTorch 模型的 forward 方法。"""
    ordered_layers = topological_sort_layers(model_graph)
    predecessors = build_predecessor_map(model_graph)
    input_ids = [layer["id"] for layer in ordered_layers if layer.get("type") == "Input"]
    output_ids = [layer["id"] for layer in ordered_layers if layer.get("type") == "Output"]
    if not output_ids and ordered_layers:
        output_ids = [ordered_layers[-1]["id"]]

    lines = [
        "    def forward(self, x):",
        "        outputs = {}",
    ]

    for layer_config in ordered_layers:
        layer_id = layer_config["id"]
        layer_type = layer_config["type"]
        output_var = _tensor_name(layer_id)

        if layer_type == "Input":
            if len(input_ids) > 1:
                lines.append(f"        {output_var} = x[{_repr(layer_id)}]")
            else:
                lines.append(f"        {output_var} = x")
            lines.append(f"        outputs[{_repr(layer_id)}] = {output_var}")
            continue

        predecessor_ids = predecessors.get(layer_id, [])
        input_expr = _input_expression(layer_config, predecessor_ids)

        if layer_type == "Output":
            lines.append(f"        {output_var} = {input_expr}")
        else:
            lines.append(f"        {output_var} = self.{_module_name(layer_id)}({input_expr})")
        lines.append(f"        outputs[{_repr(layer_id)}] = {output_var}")

    if len(output_ids) == 1:
        lines.append(f"        return outputs[{_repr(output_ids[0])}]")
    else:
        items = ", ".join(f"{_repr(output_id)}: outputs[{_repr(output_id)}]" for output_id in output_ids)
        lines.append(f"        return {{{items}}}")

    return "\n".join(lines)


def generate_training_config(train_config):
    """生成导出文件中的训练配置常量。"""
    return (
        f"TRAIN_CONFIG = {_repr(train_config)}\n\n"
        "DATASET_SPECS = {\n"
        "    'MNIST': {'class': torchvision.datasets.MNIST, 'shape': [1, 28, 28], 'classes': 10},\n"
        "    'FashionMNIST': {'class': torchvision.datasets.FashionMNIST, 'shape': [1, 28, 28], 'classes': 10},\n"
        "    'KMNIST': {'class': torchvision.datasets.KMNIST, 'shape': [1, 28, 28], 'classes': 10},\n"
        "    'CIFAR10': {'class': torchvision.datasets.CIFAR10, 'shape': [3, 32, 32], 'classes': 10},\n"
        "    'CIFAR100': {'class': torchvision.datasets.CIFAR100, 'shape': [3, 32, 32], 'classes': 100},\n"
        "}\n"
    )


def generate_model_metadata(model_graph):
    """生成导出文件中的模型输入元数据。"""
    inputs = [
        {"id": layer.get("id"), "shape": layer.get("params", {}).get("shape", [])}
        for layer in model_graph.get("layers", [])
        if layer.get("type") == "Input"
    ]
    return (
        f"MODEL_INPUTS = {_repr(inputs)}\n"
        "MODEL_INPUT_SHAPES = [item['shape'] for item in MODEL_INPUTS]\n"
    )


def generate_dataset_helpers():
    """生成数据集加载与预处理代码。"""
    return r'''
def resolve_dataset_name(dataset_name):
    aliases = {
        "mnist": "MNIST",
        "fashionmnist": "FashionMNIST",
        "fashion_mnist": "FashionMNIST",
        "fashion-mnist": "FashionMNIST",
        "kmnist": "KMNIST",
        "cifar10": "CIFAR10",
        "cifar-10": "CIFAR10",
        "cifar_10": "CIFAR10",
        "cifar100": "CIFAR100",
        "cifar-100": "CIFAR100",
        "cifar_100": "CIFAR100",
    }
    normalized = str(dataset_name or "MNIST").strip()
    if normalized in DATASET_SPECS:
        return normalized
    key = aliases.get(normalized.lower())
    if key:
        return key
    supported = ", ".join(DATASET_SPECS)
    raise ValueError(f"Unsupported dataset: {dataset_name}. Supported datasets: {supported}")


def get_primary_model_input_shape(model_inputs=None):
    model_inputs = model_inputs or MODEL_INPUTS
    if not model_inputs:
        dataset_name = resolve_dataset_name(TRAIN_CONFIG.get("dataset_name", "MNIST"))
        return DATASET_SPECS[dataset_name]["shape"]
    return list(model_inputs[0].get("shape", []))


def _product(values):
    result = 1
    for value in values:
        result *= int(value)
    return result


def build_dataset_transform(dataset_name, model_inputs=None):
    dataset_shape = DATASET_SPECS[dataset_name]["shape"]
    target_shape = get_primary_model_input_shape(model_inputs)
    transforms = []

    if len(target_shape) == 3:
        target_channels, target_height, target_width = target_shape
        if target_channels not in (1, 3):
            raise ValueError(f"Image dataset export only supports 1 or 3 input channels, got {target_channels}")
        transforms.append(torchvision.transforms.Resize((target_height, target_width)))
        if target_channels != dataset_shape[0]:
            transforms.append(torchvision.transforms.Grayscale(num_output_channels=target_channels))
        transforms.append(torchvision.transforms.ToTensor())
        return torchvision.transforms.Compose(transforms)

    if len(target_shape) == 2:
        target_height, target_width = target_shape
        transforms.extend([
            torchvision.transforms.Grayscale(num_output_channels=1),
            torchvision.transforms.Resize((target_height, target_width)),
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Lambda(lambda tensor: tensor.squeeze(0)),
        ])
        return torchvision.transforms.Compose(transforms)

    if len(target_shape) == 1:
        target_features = int(target_shape[0])
        dataset_features = _product(dataset_shape)
        if target_features == dataset_features:
            transforms.extend([
                torchvision.transforms.ToTensor(),
                torchvision.transforms.Lambda(lambda tensor: torch.flatten(tensor)),
            ])
        else:
            transforms.extend([
                torchvision.transforms.Grayscale(num_output_channels=1),
                torchvision.transforms.Resize((1, target_features)),
                torchvision.transforms.ToTensor(),
                torchvision.transforms.Lambda(lambda tensor: torch.flatten(tensor)),
            ])
        return torchvision.transforms.Compose(transforms)

    raise ValueError(f"Unsupported model input shape for image dataset: {target_shape}")


def prepare_dataloaders(config):
    dataset_name = resolve_dataset_name(config.get("dataset_name", "MNIST"))
    dataset_class = DATASET_SPECS[dataset_name]["class"]
    batch_size = int(config.get("batch_size", 64))
    data_dir = os.path.expanduser(config.get("data_dir") or "./datasets")
    dataset_root = os.path.join(data_dir, dataset_name)
    transform = build_dataset_transform(dataset_name, MODEL_INPUTS)

    train_data = dataset_class(
        root=dataset_root,
        train=True,
        transform=transform,
        download=True,
    )
    test_data = dataset_class(
        root=dataset_root,
        train=False,
        transform=transform,
        download=True,
    )

    train_loader = torch.utils.data.DataLoader(
        train_data,
        batch_size=batch_size,
        shuffle=True,
    )
    test_loader = torch.utils.data.DataLoader(
        test_data,
        batch_size=batch_size,
        shuffle=False,
    )
    return train_loader, test_loader


def build_sample_input_from_dataset(config, model_inputs=None):
    dataset_name = resolve_dataset_name(config.get("dataset_name", "MNIST"))
    dataset_shape = DATASET_SPECS[dataset_name]["shape"]
    model_inputs = model_inputs or []
    input_shapes = [item.get("shape", []) for item in model_inputs]
    shape = input_shapes[0] if input_shapes else dataset_shape
    batch_size = int(config.get("batch_size", 64))
    if len(model_inputs) > 1:
        return {
            item["id"]: torch.randn(batch_size, *item.get("shape", []))
            for item in model_inputs
        }
    return torch.randn(batch_size, *shape)
'''.strip()


def generate_training_helpers():
    """生成训练、评估和命令行入口辅助代码。"""
    return r'''
def build_loss_fn(config):
    loss_name = str(config.get("loss_fn", "cross_entropy")).lower()
    if loss_name in ("cross_entropy", "crossentropyloss", "ce"):
        return nn.CrossEntropyLoss()
    if loss_name in ("mse", "mseloss"):
        return nn.MSELoss()
    raise ValueError(f"Unsupported loss function: {config.get('loss_fn')}")


def build_optimizer(model, config):
    optimizer_name = str(config.get("optimizer", "sgd")).lower()
    learning_rate = float(config.get("rate", 0.001))
    if optimizer_name == "sgd":
        return torch.optim.SGD(model.parameters(), lr=learning_rate, momentum=0.9)
    if optimizer_name == "adam":
        return torch.optim.Adam(model.parameters(), lr=learning_rate)
    raise ValueError(f"Unsupported optimizer: {config.get('optimizer')}")


def train_one_epoch(model, train_loader, optimizer, loss_fn, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for inputs, labels in train_loader:
        inputs = inputs.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(inputs)
        loss = loss_fn(outputs, labels)
        loss.backward()
        optimizer.step()

        batch_size = labels.size(0)
        total_loss += loss.item() * batch_size
        correct += (outputs.argmax(dim=1) == labels).sum().item()
        total += batch_size

    return {
        "loss": total_loss / total if total else 0.0,
        "accuracy": correct / total if total else 0.0,
    }


def evaluate(model, test_loader, loss_fn, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for inputs, labels in test_loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            outputs = model(inputs)
            loss = loss_fn(outputs, labels)

            batch_size = labels.size(0)
            total_loss += loss.item() * batch_size
            correct += (outputs.argmax(dim=1) == labels).sum().item()
            total += batch_size

    return {
        "loss": total_loss / total if total else 0.0,
        "accuracy": correct / total if total else 0.0,
    }


def run_training(model, config=None):
    config = dict(TRAIN_CONFIG if config is None else config)
    requested_device = config.get("device", "cpu")
    if requested_device == "cuda" and not torch.cuda.is_available():
        requested_device = "cpu"
    device = torch.device(requested_device)

    model = model.to(device)
    train_loader, test_loader = prepare_dataloaders(config)
    loss_fn = build_loss_fn(config)
    optimizer = build_optimizer(model, config)
    epochs = int(config.get("epochs", 1))

    history = []
    for epoch in range(1, epochs + 1):
        train_metrics = train_one_epoch(model, train_loader, optimizer, loss_fn, device)
        eval_metrics = evaluate(model, test_loader, loss_fn, device)
        item = {"epoch": epoch, "train": train_metrics, "eval": eval_metrics}
        history.append(item)
        print(
            f"epoch={epoch} "
            f"train_loss={train_metrics['loss']:.4f} "
            f"train_acc={train_metrics['accuracy']:.4f} "
            f"eval_loss={eval_metrics['loss']:.4f} "
            f"eval_acc={eval_metrics['accuracy']:.4f}"
        )
    return history
'''.strip()


def generate_smoke_test(model_graph, class_name):
    """生成可直接运行的最小示例。"""
    normalized_graph = _normalize_graph(model_graph)
    class_name = _safe_class_name(class_name)

    lines = [
        "if __name__ == \"__main__\":",
        "    parser = argparse.ArgumentParser()",
        "    parser.add_argument('--train', action='store_true', help='Train the exported model with TRAIN_CONFIG dataset settings.')",
        "    args = parser.parse_args()",
        f"    model = {class_name}()",
        "    if args.train:",
        "        run_training(model, TRAIN_CONFIG)",
        "    else:",
        "        sample_input = build_sample_input_from_dataset(TRAIN_CONFIG, MODEL_INPUTS)",
        "        output = model(sample_input)",
        "        print(model)",
        "        print('dataset:', TRAIN_CONFIG.get('dataset_name', 'MNIST'))",
        "        if isinstance(output, dict):",
        "            print({key: tuple(value.shape) for key, value in output.items()})",
        "        else:",
        "            print(tuple(output.shape))",
    ]
    return "\n".join(lines)


def generate_notebook(source_code, model_graph, class_name, train_config=None):
    """生成按教学模块分块的 Jupyter Notebook JSON。"""
    normalized_graph = _normalize_graph(model_graph)
    _ensure_valid_graph(normalized_graph)
    class_name = _safe_class_name(class_name)
    export_train_config = _extract_train_config(normalized_graph, train_config)
    ordered_layers = topological_sort_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph).get("layers", {})
    cells = []

    def add_markdown(text):
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": _to_notebook_lines(text),
        })

    def add_code(text):
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": _to_notebook_lines(format_python_code(text)),
        })

    add_markdown(generate_notebook_title(normalized_graph, class_name, shape_info))
    add_markdown(
        "## 1. 依赖导入\n\n"
        "##### 功能\n"
        "导入 PyTorch 和神经网络模块。后面的模型类、辅助层和运行示例都依赖这些包。\n"
    )
    add_code(generate_imports())

    add_markdown(
        "## 2. 数据集与训练配置\n\n"
        "##### 功能\n"
        "这里保存从模型 JSON 导出的训练配置，包括数据集、批大小、训练轮数、学习率、优化器和损失函数。"
        "后续 DataLoader 和训练循环会直接读取这些配置。\n"
    )
    add_code(generate_training_config(export_train_config))
    add_code(generate_model_metadata(normalized_graph))

    add_markdown(
        "## 3. 数据集加载\n\n"
        "##### 功能\n"
        "根据 `TRAIN_CONFIG['dataset_name']` 加载 torchvision 内置数据集，并按数据集类型选择输入转换。"
        "这一步把导出的模型和真实数据连接起来。\n"
    )
    add_code(generate_dataset_helpers())

    add_markdown(
        "## 4. 高级辅助层\n\n"
        "##### 功能\n"
        "这里放置序列、注意力、VAE、图卷积等高级模块的封装。当前模型未用到的辅助类也可以保留，方便继续扩展画布。\n"
    )
    add_code(generate_helper_layers())

    add_markdown(
        f"## 5. 模型主体：`{class_name}`\n\n"
        "##### 功能\n"
        "这一段是从画布连接关系生成的 `nn.Module`。`__init__` 定义每个可计算层，`forward` 按拓扑顺序执行数据流。\n"
    )
    add_code(generate_model_class(normalized_graph, class_name))

    add_markdown(
        "## 6. 结构与维度总览\n\n"
        "##### 功能\n"
        "用表格化数据查看每一层的类型、输入维度、输出维度和关键参数，帮助确认画布结构是否符合预期。\n"
    )
    add_code(generate_notebook_shape_overview(ordered_layers, shape_info))

    for index, layer_config in enumerate(ordered_layers, start=1):
        add_markdown(generate_layer_markdown(index, layer_config, shape_info))
        add_code(generate_layer_explanation_code(layer_config, shape_info))

    add_markdown(
        "## 7. 训练与评估函数\n\n"
        "##### 功能\n"
        "定义一个完整的训练轮次、评估函数和 `run_training` 入口。运行训练时会使用上面配置的数据集、损失函数和优化器。\n"
    )
    add_code(generate_training_helpers())

    add_markdown(
        "## 8. 前向传播试运行\n\n"
        "##### 功能\n"
        "根据当前数据集的输入形状构造一份样例输入，执行模型前向传播，并打印最终输出维度。它不会下载数据集或训练模型，只用于确认模型结构可以运行。\n"
    )
    add_code(generate_notebook_smoke_test(normalized_graph, class_name))

    add_markdown(
        "## 9. 使用真实数据集训练\n\n"
        "##### 功能\n"
        "取消下面代码的注释后，会根据 `TRAIN_CONFIG` 下载/读取数据集并训练模型。首次运行某个数据集时可能需要等待下载完成。\n"
    )
    add_code("# history = run_training(model, TRAIN_CONFIG)\n# history[-1] if history else None")

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, ensure_ascii=False, indent=2)


def generate_notebook_title(model_graph, class_name, shape_info):
    """生成 Notebook 顶部模型说明。"""
    input_shapes = [
        layer_shape.get("output_shape")
        for layer_id, layer_shape in shape_info.items()
        if layer_shape.get("layer_type") == "Input"
    ]
    output_shapes = [
        layer_shape.get("output_shape")
        for layer_id, layer_shape in shape_info.items()
        if layer_shape.get("layer_type") == "Output"
    ]
    return (
        f"# {class_name}\n\n"
        "这个 Notebook 由可视化模型图自动生成，按功能拆成多个小节，便于逐段阅读、运行和改写。\n\n"
        f"- 层数量：{len(model_graph.get('layers', []))}\n"
        f"- 连接数量：{len(model_graph.get('connections', []))}\n"
        f"- 输入维度：{input_shapes}\n"
        f"- 输出维度：{output_shapes}\n"
    )


def generate_notebook_shape_overview(ordered_layers, shape_info):
    """生成 Notebook 中的结构概览代码块。"""
    rows = []
    for layer_config in ordered_layers:
        layer_id = layer_config["id"]
        layer_shape = shape_info.get(layer_id, {})
        rows.append({
            "id": layer_id,
            "type": layer_config.get("type"),
            "input_shape": layer_shape.get("input_shape"),
            "output_shape": layer_shape.get("output_shape"),
            "params": layer_config.get("params", {}),
        })

    return (
        f"layer_summaries = {_repr(rows)}\n"
        "for index, item in enumerate(layer_summaries, start=1):\n"
        "    print(f\"{index}. {item['id']} ({item['type']})\")\n"
        "    print(f\"   input : {item['input_shape']}\")\n"
        "    print(f\"   output: {item['output_shape']}\")\n"
        "    print(f\"   params: {item['params']}\")\n"
    )


def generate_layer_markdown(index, layer_config, shape_info):
    """生成单层教学说明 Markdown。"""
    layer_id = layer_config["id"]
    layer_type = layer_config.get("type")
    layer_shape = shape_info.get(layer_id, {})
    return (
        f"### 模块 {index}: `{layer_id}` ({layer_type})\n\n"
        "##### 功能\n"
        f"{_layer_function_description(layer_config)}\n\n"
        "##### 维度\n"
        f"- 输入维度：`{layer_shape.get('input_shape')}`\n"
        f"- 输出维度：`{layer_shape.get('output_shape')}`\n"
    )


def generate_layer_explanation_code(layer_config, shape_info):
    """生成单层解释代码块，便于用户运行查看模块信息。"""
    layer_id = layer_config["id"]
    layer_shape = shape_info.get(layer_id, {})
    info = {
        "id": layer_id,
        "type": layer_config.get("type"),
        "params": layer_config.get("params", {}),
        "input_shape": layer_shape.get("input_shape"),
        "output_shape": layer_shape.get("output_shape"),
        "status": layer_shape.get("status"),
        "note": _layer_function_description(layer_config),
    }
    return (
        f"module_info = {_repr(info)}\n"
        "print(f\"模块: {module_info['id']} ({module_info['type']})\")\n"
        "print(f\"功能: {module_info['note']}\")\n"
        "print(f\"输入维度: {module_info['input_shape']}\")\n"
        "print(f\"输出维度: {module_info['output_shape']}\")\n"
        "print(f\"关键参数: {module_info['params']}\")\n"
    )


def generate_notebook_smoke_test(model_graph, class_name):
    """生成 Notebook 中的前向传播试运行代码块。"""
    lines = [
        f"model = {class_name}()",
        "sample_input = build_sample_input_from_dataset(TRAIN_CONFIG, MODEL_INPUTS)",
        "output = model(sample_input)",
        "print(model)",
        "print('dataset:', TRAIN_CONFIG.get('dataset_name', 'MNIST'))",
        "if isinstance(output, dict):",
        "    print({key: tuple(value.shape) for key, value in output.items()})",
        "else:",
        "    print(tuple(output.shape))",
    ]
    return "\n".join(lines)


def format_python_code(source_code):
    """格式化生成的 Python 源代码。"""
    lines = [line.rstrip() for line in source_code.strip().splitlines()]
    formatted = "\n".join(lines)
    while "\n\n\n\n" in formatted:
        formatted = formatted.replace("\n\n\n\n", "\n\n\n")
    return formatted + "\n"


def _layer_function_description(layer_config):
    """返回适合 Notebook 教学说明的层功能描述。"""
    layer_type = layer_config.get("type")
    params = layer_config.get("params", {}) or {}

    descriptions = {
        "Input": "声明模型接收的数据形状。运行时会把传入的张量作为后续层的数据源。",
        "Output": "标记模型的最终输出位置。该节点不改变张量，只把前一层结果作为模型返回值。",
        "Conv2D": (
            "二维卷积层，用可学习卷积核提取局部空间特征。"
            f"本层输出通道数为 {params.get('out_channels')}，卷积核大小为 {params.get('kernel_size', 3)}。"
        ),
        "Pooling": (
            "最大池化层，用局部窗口保留显著响应并压缩空间尺寸。"
            f"本层窗口大小为 {params.get('kernel_size', 2)}，步幅为 {params.get('stride', params.get('kernel_size', 2))}。"
        ),
        "Flatten": "展平层，把多维特征图摊平成一维特征向量，常用于连接卷积部分和全连接部分。",
        "Linear": f"全连接层，对输入特征做线性变换。本层输出特征数为 {params.get('out_features')}。",
        "ReLU": "ReLU 激活层，把负值截断为 0，引入非线性表达能力。",
        "Dropout": f"随机失活层，训练时按 p={params.get('p', 0.5)} 的概率屏蔽部分神经元以缓解过拟合。",
        "SelfAttention": "自注意力层，让序列中每个位置根据其它位置的信息更新自身表示。",
        "TransformerEncoder": "Transformer 编码器层，结合多头自注意力和前馈网络处理序列特征。",
        "LSTM": "长短期记忆网络层，按时间顺序读取序列并保留上下文信息。",
        "Seq2Seq": "编码器-解码器序列层，将输入序列转换成指定长度和特征维度的输出序列。",
        "VAE": "变分自编码器层，把输入编码到潜变量空间，再解码为重建结果。",
        "GraphConv": "图卷积层，根据邻接矩阵聚合邻居节点信息，并更新节点特征。",
    }

    merge_mode = params.get("merge")
    if merge_mode in ("add", "sum"):
        return descriptions.get(layer_type, "执行该模型层的张量变换。") + " 多个输入会先逐元素相加再进入本层。"
    if merge_mode == "concat":
        dim = params.get("dim", params.get("concat_dim", 1))
        return descriptions.get(layer_type, "执行该模型层的张量变换。") + f" 多个输入会先沿 dim={dim} 拼接再进入本层。"

    return descriptions.get(layer_type, "执行该模型层的张量变换。")


def _extract_train_config(model_graph, explicit_train_config=None):
    """从显式参数或模型 JSON 中提取训练配置。"""
    config = {}
    if isinstance(model_graph, dict):
        embedded = model_graph.get("train_config") or model_graph.get("training") or model_graph.get("dataset")
        if isinstance(embedded, dict):
            config.update(embedded)
    if isinstance(explicit_train_config, dict):
        config.update(explicit_train_config)

    return {
        "dataset_name": config.get("dataset_name", config.get("dataset", "MNIST")),
        "epochs": int(config.get("epochs", 1) or 1),
        "batch_size": int(config.get("batch_size", 64) or 64),
        "rate": float(config.get("rate", config.get("learning_rate", 0.001)) or 0.001),
        "device": config.get("device", "cpu"),
        "loss_fn": config.get("loss_fn", "cross_entropy"),
        "optimizer": config.get("optimizer", "sgd"),
        "data_dir": config.get("data_dir", ""),
        "artifacts_dir": config.get("artifacts_dir", ""),
    }


def _normalize_graph(model_graph):
    if isinstance(model_graph, str):
        model_graph = json.loads(model_graph)
    if not isinstance(model_graph, dict):
        raise ValueError("模型图必须是 JSON 对象")
    # 自定义容器：展平成纯层扁平图后再导出（幂等，不含容器时原样返回）。
    return flatten_graph(model_graph)


def _ensure_valid_graph(model_graph):
    result = validate_model_graph(model_graph)
    if not result.get("valid"):
        errors = result.get("errors") or [result.get("message") or "模型结构校验失败"]
        raise ValueError("无法导出代码：" + "；".join(str(error) for error in errors))


def _safe_class_name(value):
    name = re.sub(r"\W+", "_", str(value or "GeneratedModel")).strip("_")
    if not name:
        name = "GeneratedModel"
    if name[0].isdigit():
        name = "_" + name
    if keyword.iskeyword(name):
        name += "Model"
    return name


def _module_name(layer_id):
    name = re.sub(r"\W+", "_", str(layer_id)).strip("_")
    if not name:
        name = "layer"
    if name[0].isdigit():
        name = "layer_" + name
    if keyword.iskeyword(name):
        name += "_layer"
    return f"layer_{name}"


def _tensor_name(layer_id):
    name = re.sub(r"\W+", "_", str(layer_id)).strip("_")
    if not name:
        name = "value"
    if name[0].isdigit():
        name = "_" + name
    if keyword.iskeyword(name):
        name += "_value"
    return f"out_{name}"


def _input_expression(layer_config, predecessor_ids):
    if not predecessor_ids:
        raise ValueError(f"节点 {layer_config.get('id')} 缺少输入连接")
    if len(predecessor_ids) == 1:
        return f"outputs[{_repr(predecessor_ids[0])}]"

    tensors = ", ".join(f"outputs[{_repr(predecessor_id)}]" for predecessor_id in predecessor_ids)
    params = layer_config.get("params", {}) or {}
    merge_mode = params.get("merge", "concat")

    if merge_mode in ("add", "sum"):
        expression = f"[{tensors}]"
        return f"sum({expression}[1:], {expression}[0])"

    concat_dim = params.get("dim", params.get("concat_dim", 1))
    return f"torch.cat([{tensors}], dim={concat_dim})"


def _flattened_size(shape):
    size = 1
    for dimension in shape or []:
        size *= dimension
    return size


def _repr(value: Any):
    return repr(value)


def _to_notebook_lines(text):
    lines = text.splitlines(keepends=True)
    if text and not text.endswith("\n"):
        lines[-1] += "\n"
    return lines
