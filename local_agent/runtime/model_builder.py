"""根据可视化模型 JSON 构建 PyTorch 模型。"""

import json

import torch
import torch.nn as nn

from .graph_model import ExecutableGraphModel
from .graph_utils import flatten_graph, topological_sort_layers
from .validator import infer_all_shapes


def build_model(model_graph):
    """将模型图转换成支持非顺序结构的 PyTorch 图模型。

    参数：
        model_graph：前端画布生成的模型图结构，包含层节点列表和节点连接关系。

    返回：
        ExecutableGraphModel：支持 DAG 前向传播的 PyTorch 模型。
    """
    normalized_graph = json.loads(model_graph) if isinstance(model_graph, str) else model_graph
    # 自定义容器：展平成纯层扁平图后再构建，内部层以层级 id 进入 ModuleDict。
    normalized_graph = flatten_graph(normalized_graph)
    ordered_layers = order_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph)

    # 根据拓扑排序后的模型层配置，逐层创建对应的PyTorch层对象，并收集到modules中
    modules = {}
    layer_shapes = shape_info["layers"]
    for layer_config in ordered_layers:
        layer_id = layer_config["id"]
        layer_type = layer_config["type"]
        input_shape = None
        if layer_type not in ("Input", "Output"):
            input_shape = layer_shapes[layer_id]["input_shape"]

        layer = create_layer(layer_config, input_shape)
        if layer is not None:
            modules[layer_id] = layer

    return ExecutableGraphModel(
        model_graph=normalized_graph,
        ordered_layers=ordered_layers,
        modules=modules,
    )


def create_layer(layer_config, input_shape=None):
    """根据一个可视化层配置创建对应的 PyTorch 层。

    参数：
        layer_config：单个层节点配置，包含层类型、层名称和参数。
        input_shape：validator 已推导出的该层输入张量形状；默认为 None。

    返回：
        后续应返回对应的 PyTorch 层对象。
    """
    layer_type = layer_config["type"]
    layer_params = layer_config.get("params", {})

    if layer_type == "Input":
        return None

    if layer_type == "Output":
        return None

    if layer_type == 'Conv2D':
        return nn.Conv2d(
            in_channels=input_shape[0],
            out_channels=layer_params['out_channels'],
            kernel_size=layer_params.get("kernel_size", 3),
            stride=layer_params.get("stride", 1),
            padding=layer_params.get("padding", 0),
            padding_mode=layer_params.get("padding_mode", "zeros")
        )
    
    if layer_type == 'ReLU':
        return nn.ReLU()

    if layer_type == 'Identity':
        # 容器输入/输出端口展平后的直通层
        return nn.Identity()
    
    if layer_type == 'Flatten':
        return nn.Flatten()
    
    if layer_type == 'Linear':
        return nn.Linear(
            in_features=input_shape[0],
            out_features=layer_params["out_features"]
        )
    
    if layer_type == 'Pooling':
        return nn.MaxPool2d(
            kernel_size=layer_params.get("kernel_size", 2),
            stride=layer_params.get("stride", layer_params.get("kernel_size", 2)),
            padding=layer_params.get("padding", 0)
        )
    
    if layer_type == "Dropout":
        return nn.Dropout(
            p=layer_params.get("p", 0.5)
        )

    if layer_type == "SelfAttention":
        return SelfAttentionBlock(
            embed_dim=layer_params["embed_dim"],
            num_heads=layer_params["num_heads"],
            dropout=layer_params.get("dropout", 0.0),
        )

    if layer_type == "TransformerEncoder":
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=layer_params["d_model"],
            nhead=layer_params["num_heads"],
            dim_feedforward=layer_params.get("dim_feedforward", layer_params["d_model"] * 4),
            dropout=layer_params.get("dropout", 0.1),
            batch_first=True,
        )
        return nn.TransformerEncoder(
            encoder_layer=encoder_layer,
            num_layers=layer_params.get("num_layers", 1),
        )

    if layer_type == "LSTM":
        return LSTMLayer(
            input_size=input_shape[-1],
            hidden_size=layer_params["hidden_size"],
            num_layers=layer_params.get("num_layers", 1),
            bidirectional=layer_params.get("bidirectional", False),
            return_sequences=layer_params.get("return_sequences", False),
        )

    if layer_type == "Seq2Seq":
        return Seq2SeqLayer(
            input_size=input_shape[-1],
            hidden_size=layer_params["hidden_size"],
            output_size=layer_params["output_size"],
            target_length=layer_params["target_length"],
            num_layers=layer_params.get("num_layers", 1),
        )

    if layer_type == "VAE":
        return VAELayer(
            input_features=_flattened_size(input_shape),
            latent_dim=layer_params["latent_dim"],
            output_features=layer_params.get("output_features", _flattened_size(input_shape)),
        )

    if layer_type == "GraphConv":
        return GraphConvLayer(
            in_features=input_shape[-1],
            out_features=layer_params["out_features"],
        )


def order_layers(model_graph):
    """将画布中的模型节点排序为拓扑执行顺序。

    参数：
        model_graph：前端画布生成的模型图结构，包含节点和连接关系。

    返回：
        返回按依赖关系排序后的层配置列表。该排序支持分支和汇合结构，
        但要求模型图必须是有向无环图。
    """
    return topological_sort_layers(model_graph)


def _flattened_size(shape):
    """计算不含 batch 维度的展平特征数。"""
    flattened_size = 1
    for dimension in shape:
        flattened_size *= dimension
    return flattened_size


class SelfAttentionBlock(nn.Module):
    """面向教学的单层多头自注意力模块。"""

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
    """包装 PyTorch LSTM，默认返回最后一个时间步。"""

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
    """简化版编码器-解码器层，用于展示 Seq2Seq 的数据流。"""

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
    """简化版 VAE 层，返回重建结果。"""

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
    """简化 GCN 层，支持直接传节点特征或 {"x": features, "adj": adjacency}。"""

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


def extract_model_summary(model):
    """生成便于展示或调试的模型结构摘要。

    参数：
        model：已经构建好的 ExecutableGraphModel 模型对象。

    返回：
        dict：模型摘要，包含逐层信息（id、类型、名称、参数量）、
        总参数量和可训练参数量。
    """
    layers = []
    total_params = 0
    trainable_params = 0

    for layer_config in getattr(model, "ordered_layers", []):
        layer_id = layer_config["id"]
        layer_type = layer_config.get("type")
        modules_by_id = getattr(model, "modules_by_id", None)
        module = modules_by_id[layer_id] if modules_by_id is not None and layer_id in modules_by_id else None

        layer_param_count = 0
        if module is not None:
            layer_param_count = sum(
                parameter.numel()
                for parameter in module.parameters()
            )

        layers.append({
            "id": layer_id,
            "type": layer_type,
            "name": layer_config.get("name"),
            "params": layer_config.get("params", {}),
            "num_parameters": layer_param_count,
        })

    for parameter in model.parameters():
        total_params += parameter.numel()
        if parameter.requires_grad:
            trainable_params += parameter.numel()

    return {
        "layers": layers,
        "total_parameters": total_params,
        "trainable_parameters": trainable_params,
    }
