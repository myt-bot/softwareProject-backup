"""支持 DAG 前向传播的 PyTorch 图模型。"""

import torch
import torch.nn as nn

from .graph_utils import (
    build_predecessor_map,
    build_successor_map,
)


class ExecutableGraphModel(nn.Module):
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

            #将所有前置节点的输出合并成该节点的输入
            node_input = self._collect_node_input(layer_id, outputs)

            if layer_type == "Output":
                outputs[layer_id] = node_input
                continue

            # 执行该层定义的计算
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
