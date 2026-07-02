"""根据可视化模型 JSON 构建 PyTorch 模型。"""

import json

import torch
import torch.nn as nn

from .graph_utils import (
    build_predecessor_map,
    build_successor_map,
    topological_sort_layers,
)
from .validator import infer_all_shapes


def build_model(model_graph):
    """将模型图转换成支持非顺序结构的 PyTorch 图模型。

    参数：
        model_graph：前端画布生成的模型图结构，包含层节点列表和节点连接关系。

    返回：
        GraphModel：支持 DAG 前向传播的 PyTorch 模型。
    """
    normalized_graph = json.loads(model_graph) if isinstance(model_graph, str) else model_graph
    ordered_layers = order_layers(normalized_graph)
    shape_info = infer_all_shapes(normalized_graph)

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

    return GraphModel(
        model_graph=normalized_graph,
        ordered_layers=ordered_layers,
        modules=modules,
    )


class GraphModel(nn.Module):
    """支持有向无环图结构的 PyTorch 模型。

    参数：
        model_graph：模型图结构，包含 layers 和 connections。
        ordered_layers：经过拓扑排序后的层配置列表。
        modules：以 layer_id 为键、PyTorch 层对象为值的模块字典。
    """

    def __init__(self, model_graph, ordered_layers, modules):
        super().__init__()
        self.model_graph = model_graph
        self.ordered_layers = ordered_layers
        self.layer_map = {
            layer["id"]: layer
            for layer in model_graph.get("layers", [])
        }
        self.predecessors = build_predecessor_map(model_graph)
        self.modules_by_id = nn.ModuleDict(modules)

    def forward(self, x):
        """按拓扑顺序执行模型图。

        参数：
            x：模型输入张量；如果存在多个 Input 节点，也可以传入 {input_id: tensor} 字典。

        返回：
            最后一个拓扑节点的输出张量；如果存在多个输出节点，返回 {node_id: tensor} 字典。
        """
        outputs = {}

        for layer_config in self.ordered_layers:
            layer_id = layer_config["id"]
            layer_type = layer_config["type"]

            if layer_type == "Input":
                outputs[layer_id] = _resolve_input_tensor(x, layer_id)
                continue

            node_input = self._collect_node_input(layer_id, outputs)

            if layer_type == "Output":
                outputs[layer_id] = node_input
                continue

            module = self.modules_by_id[layer_id]
            outputs[layer_id] = module(node_input)

        output_ids = self._get_output_node_ids()
        if len(output_ids) == 1:
            return outputs[output_ids[0]]

        return {
            output_id: outputs[output_id]
            for output_id in output_ids
        }

    def _collect_node_input(self, layer_id, outputs):
        """收集并合并当前节点的所有前驱输出。"""
        predecessor_ids = self.predecessors[layer_id]

        tensors = [
            outputs[predecessor_id]
            for predecessor_id in predecessor_ids
        ]
        if len(tensors) == 1:
            return tensors[0]

        layer_config = self.layer_map[layer_id]
        return _merge_tensors(layer_config, tensors)

    def _get_output_node_ids(self):
        """获取模型输出节点 id。"""
        explicit_output_ids = [
            layer["id"]
            for layer in self.ordered_layers
            if layer["type"] == "Output"
        ]
        if explicit_output_ids:
            return explicit_output_ids

        successor_map = build_successor_map(self.model_graph)
        terminal_ids = [
            layer_id
            for layer_id, successors in successor_map.items()
            if not successors
        ]

        return terminal_ids


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


def _resolve_input_tensor(x, layer_id):
    """根据输入节点 id 获取输入张量。"""
    if isinstance(x, dict):
        if layer_id not in x:
            raise ValueError(f"缺少输入节点 {layer_id} 对应的输入张量")
        return x[layer_id]

    return x


def _merge_tensors(layer_config, tensors):
    """合并多个前驱节点输出。

    目标节点可通过 params.merge 指定合并方式：
        concat：按 params.dim 或 params.concat_dim 指定维度拼接，默认 dim=1；
        add/sum：逐元素相加。
    """
    params = layer_config.get("params", {})
    merge_mode = params.get("merge", "concat")

    if merge_mode == "concat":
        concat_dim = params.get("dim", params.get("concat_dim", 1))
        return torch.cat(tensors, dim=concat_dim)

    if merge_mode in ("add", "sum"):
        merged = tensors[0]
        for tensor in tensors[1:]:
            merged = merged + tensor
        return merged


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
        model：已经构建好的 PyTorch 模型对象。

    返回：
        后续应返回模型层级、参数数量和输入输出信息等摘要数据。
    """
    pass
