"""M5 教学辅助知识核心。

本模块只保存和查询面向初学者的教学知识，不包含代码导出、Notebook 生成、
FastAPI 接口、PyTorch 逻辑、数据库逻辑，也不调用现有 validator。
"""

from __future__ import annotations

import copy
from typing import Any


LayerTeaching = dict[str, Any]
ParameterTeaching = dict[str, Any]
ErrorSuggestion = dict[str, Any]


_LAYER_REGISTRY: dict[str, dict[str, Any]] = {
    "Input": {"canonical_name": "Input", "aliases": (), "has_teaching": True},
    "Output": {"canonical_name": "Output", "aliases": (), "has_teaching": True},
    "Add": {
        "canonical_name": "Add",
        "aliases": (),
        "has_teaching": True,
        "compatibility_note": "前端教学节点；提交给 M3 时折叠为目标节点的 params.merge=add。",
    },
    "Conv2D": {"canonical_name": "Conv2D", "aliases": ("Convolution2D",), "has_teaching": True},
    "Pooling": {
        "canonical_name": "Pooling",
        "aliases": ("Pool", "MaxPooling", "MaxPool"),
        "has_teaching": True,
        "compatibility_note": "前端显示 MaxPooling，序列化后的规范类型为 Pooling。",
    },
    "ReLU": {"canonical_name": "ReLU", "aliases": (), "has_teaching": True},
    "Flatten": {"canonical_name": "Flatten", "aliases": (), "has_teaching": True},
    "Linear": {"canonical_name": "Linear", "aliases": ("Dense",), "has_teaching": True},
    "Dropout": {"canonical_name": "Dropout", "aliases": (), "has_teaching": True},
    "LSTM": {"canonical_name": "LSTM", "aliases": (), "has_teaching": True},
    "Seq2Seq": {"canonical_name": "Seq2Seq", "aliases": (), "has_teaching": True},
    "TransformerEncoder": {
        "canonical_name": "TransformerEncoder",
        "aliases": (),
        "has_teaching": True,
    },
    "SelfAttention": {"canonical_name": "SelfAttention", "aliases": (), "has_teaching": True},
    "VAE": {"canonical_name": "VAE", "aliases": (), "has_teaching": True},
    "GraphConv": {"canonical_name": "GraphConv", "aliases": ("GCN",), "has_teaching": True},
    "Identity": {
        "canonical_name": "Identity",
        "aliases": (),
        "has_teaching": False,
        "compatibility_note": "M3 用于自定义容器展开后的直通端口，M5 暂无独立教学内容。",
    },
}


_LAYER_NAME_INDEX: dict[str, str] = {
    alias.strip().lower().replace(" ", "").replace("_", "").replace("-", ""): canonical_name
    for canonical_name, metadata in _LAYER_REGISTRY.items()
    for alias in (canonical_name, *metadata["aliases"])
}


_LAYER_TEACHING: dict[str, LayerTeaching] = {
    "Input": {
        "known": True,
        "layer_type": "Input",
        "display_name": "Input 输入层",
        "purpose": "声明模型接收的数据形状，是整张网络的数据入口。",
        "input_requirement": "通常不接收前置层输入，需要在参数中写清楚输入 shape。",
        "output_effect": "输出一个符合 shape 的张量，供后续层继续处理。",
        "common_position": "放在模型最开头；一个简单模型通常只需要一个 Input。",
        "beginner_tip": "图像任务常用 [通道数, 高, 宽]，例如 MNIST 是 [1, 28, 28]。",
        "common_mistakes": [
            "把高、宽、通道顺序写反。",
            "shape 里出现 0、负数或非整数。",
            "忘记添加 Input，导致后续层没有数据来源。",
        ],
    },
    "Output": {
        "known": True,
        "layer_type": "Output",
        "display_name": "Output 输出节点",
        "purpose": "标记模型最终结果从哪里输出。",
        "input_requirement": "需要连接到模型最后一个有效计算层。",
        "output_effect": "通常不改变数据，只把前一层结果作为模型输出。",
        "common_position": "放在模型末尾；分类模型一般接在最后一个 Linear 后面。",
        "beginner_tip": "Output 本身不决定类别数，类别数通常由前一个 Linear 的 out_features 决定。",
        "common_mistakes": [
            "忘记添加 Output。",
            "Output 后面又连接其它层。",
            "多个分支没有汇合就直接结束，导致有些路径到不了 Output。",
        ],
    },
    "Add": {
        "known": True,
        "layer_type": "Add",
        "display_name": "Add 相加合并",
        "purpose": "把多条分支在相同位置逐元素相加，常用于残差连接。",
        "input_requirement": "所有输入分支的 shape 必须完全一致。",
        "output_effect": "输出 shape 与每个输入 shape 相同。",
        "common_position": "常放在两条或多条分支重新汇合的位置。",
        "beginner_tip": "如果两个分支尺寸不同，先用卷积、池化或 Linear 调整到一致再相加。",
        "common_mistakes": [
            "把通道数或空间尺寸不同的分支直接相加。",
            "误以为 Add 会自动拼接通道。",
            "只连接了一条输入分支，Add 就失去合并意义。",
        ],
    },
    "Conv2D": {
        "known": True,
        "layer_type": "Conv2D",
        "display_name": "Conv2D 二维卷积层",
        "purpose": "用可学习的小窗口在图像或特征图上滑动，提取局部特征。",
        "input_requirement": "通常需要三维输入 [通道数, 高, 宽]。",
        "output_effect": "改变通道数，并可能因 kernel_size、stride、padding 改变高和宽。",
        "common_position": "常放在图像模型前半段，后面接 ReLU 和 Pooling。",
        "beginner_tip": "先用小卷积核，例如 3，通常更稳定也更容易理解。",
        "common_mistakes": [
            "忘记设置 out_channels。",
            "kernel_size 太大，导致输出尺寸变成 0 或负数。",
            "padding 和 stride 设置不合适，使特征图缩小过快。",
        ],
    },
    "Pooling": {
        "known": True,
        "layer_type": "Pooling",
        "display_name": "Pooling 池化层",
        "purpose": "对局部区域做下采样，保留显著特征并减少计算量。",
        "input_requirement": "通常需要三维输入 [通道数, 高, 宽]。",
        "output_effect": "一般保持通道数不变，缩小高和宽。",
        "common_position": "常跟在 Conv2D 和 ReLU 后面，用于逐步压缩空间尺寸。",
        "beginner_tip": "最常见设置是 kernel_size=2、stride=2，相当于把高和宽大约减半。",
        "common_mistakes": [
            "kernel_size 大于输入特征图尺寸。",
            "stride 没设或设得过大，导致尺寸缩得太快。",
            "以为池化会改变通道数；它通常只改变高和宽。",
        ],
    },
    "ReLU": {
        "known": True,
        "layer_type": "ReLU",
        "display_name": "ReLU 激活函数",
        "purpose": "为网络加入非线性，让多层模型能表达更复杂的关系。",
        "input_requirement": "可接收多数张量 shape，通常接在 Conv2D 或 Linear 后面。",
        "output_effect": "把小于 0 的值变成 0，shape 不变。",
        "common_position": "常放在 Conv2D 或 Linear 之后。",
        "beginner_tip": "没有激活函数，多层线性层叠起来仍接近一层线性变换。",
        "common_mistakes": [
            "在所有层后都机械添加，忽略最后分类输出是否需要原始 logits。",
            "误以为 ReLU 会改变维度。",
            "把 ReLU 当成可学习层；它没有需要训练的参数。",
        ],
    },
    "Flatten": {
        "known": True,
        "layer_type": "Flatten",
        "display_name": "Flatten 展平层",
        "purpose": "把多维特征图摊平成一维向量，方便接入全连接层。",
        "input_requirement": "通常接收卷积或池化后的多维特征。",
        "output_effect": "把 [C, H, W] 变成 [C*H*W]，不改变具体数值。",
        "common_position": "常放在卷积部分结束、Linear 层开始之前。",
        "beginner_tip": "如果从 Conv2D/Pooling 直接接 Linear，通常需要先 Flatten。",
        "common_mistakes": [
            "忘记在卷积部分和全连接部分之间添加 Flatten。",
            "以为 Flatten 会减少特征数量；它只是改变排列形状。",
            "在已经是一维向量的地方重复展平，虽然通常可行但没有必要。",
        ],
    },
    "Linear": {
        "known": True,
        "layer_type": "Linear",
        "display_name": "Linear 全连接层",
        "purpose": "把输入特征映射到指定数量的输出特征，常用于分类或特征组合。",
        "input_requirement": "通常需要一维特征向量；多维特征一般先经过 Flatten。",
        "output_effect": "输出长度由 out_features 决定。",
        "common_position": "常放在模型后半段，最后一层 Linear 的输出数通常等于类别数。",
        "beginner_tip": "做 10 类分类时，最后一个 Linear 的 out_features 通常设为 10。",
        "common_mistakes": [
            "手写 in_features 与上一层实际展平维度不一致。",
            "最后分类层 out_features 与数据集类别数不一致。",
            "把卷积输出直接接 Linear，却忘记 Flatten。",
        ],
    },
    "Dropout": {
        "known": True,
        "layer_type": "Dropout",
        "display_name": "Dropout 随机失活",
        "purpose": "训练时随机屏蔽一部分神经元，降低模型过拟合风险。",
        "input_requirement": "可接在多数特征层之后，常用于 Linear 或激活函数之后。",
        "output_effect": "训练时按概率 p 置零部分值；推理时通常自动关闭，shape 不变。",
        "common_position": "常放在全连接层附近，也可用于较大的网络中做正则化。",
        "beginner_tip": "p=0.2 到 0.5 是常见起点；模型太小或数据很简单时不一定需要。",
        "common_mistakes": [
            "把 p 设成大于 1 或小于 0。",
            "p 设置过大，导致模型学不到足够信息。",
            "以为 Dropout 会减少输出维度；它不会改变 shape。",
        ],
    },
    "LSTM": {
        "known": True,
        "layer_type": "LSTM",
        "display_name": "LSTM 长短期记忆网络",
        "purpose": "按顺序读取序列数据，用隐藏状态保留上下文信息，适合序列分类等任务。",
        "input_requirement": "当前项目约定输入为 [seq_len, input_size]，分别表示序列长度和每步特征数。",
        "output_effect": "默认输出最后一步的特征 [hidden_size]；双向时为 [hidden_size*2]；返回完整序列时保留 seq_len 维度。",
        "common_position": "常放在序列输入后面，后续可接 Linear 做分类或回归。",
        "beginner_tip": "hidden_size 控制记忆容量；先从 32 这类较小值开始更容易训练和理解。",
        "common_mistakes": [
            "把图像的 [C, H, W] 直接当作 LSTM 输入。",
            "开启 bidirectional 后忘记输出特征数会变成 hidden_size 的两倍。",
            "return_sequences=True 后输出仍是序列，后续层需要能处理二维序列形状。",
        ],
    },
    "Seq2Seq": {
        "known": True,
        "layer_type": "Seq2Seq",
        "display_name": "Seq2Seq 序列到序列",
        "purpose": "用编码器-解码器结构把一个序列转换成另一个序列，适合输入和输出都是序列的任务。",
        "input_requirement": "当前项目约定输入为 [source_length, input_size]。",
        "output_effect": "输出形状为 [target_length, output_size]，表示目标序列长度和每步输出维度。",
        "common_position": "常作为序列转换模型的主体，前接序列 Input，后接 Output。",
        "beginner_tip": "target_length 决定生成多少步，output_size 决定每一步输出多少个特征。",
        "common_mistakes": [
            "把 output_size 误认为类别总数，忽略它是每个目标时间步的输出维度。",
            "target_length 设置与任务需要的目标序列长度不一致。",
            "输入不是二维序列形状，导致维度推导失败。",
        ],
    },
    "TransformerEncoder": {
        "known": True,
        "layer_type": "TransformerEncoder",
        "display_name": "TransformerEncoder 自注意力编码器",
        "purpose": "用多头自注意力和前馈网络处理序列，让每个位置参考序列中其它位置的信息。",
        "input_requirement": "当前项目约定输入最后一维必须等于 d_model，例如 [seq_len, d_model]。",
        "output_effect": "输出 shape 与输入保持一致，便于后续 Flatten 或 Linear 继续处理。",
        "common_position": "常放在序列或 token embedding 输入之后，用于注意力类模型的编码部分。",
        "beginner_tip": "d_model 必须能被 num_heads 整除；这是多头注意力拆分特征维度的要求。",
        "common_mistakes": [
            "d_model 与输入最后一维不一致。",
            "d_model 不能被 num_heads 整除。",
            "堆叠层数和前馈维度一开始设得过大，导致训练变慢。",
        ],
    },
    "SelfAttention": {
        "known": True,
        "layer_type": "SelfAttention",
        "display_name": "SelfAttention 自注意力",
        "purpose": "让序列中每个位置根据其它位置的信息更新自身表示，适合捕捉长距离依赖。",
        "input_requirement": "当前项目要求输入至少二维，且最后一维必须等于 embed_dim。",
        "output_effect": "输出 shape 与输入保持一致，只更新每个位置的表示。",
        "common_position": "常放在序列输入或特征序列中间，后续可接 Flatten、Linear 或其它序列层。",
        "beginner_tip": "embed_dim 必须能被 num_heads 整除；先用 embed_dim=32、num_heads=4 这类小配置。",
        "common_mistakes": [
            "embed_dim 与输入最后一维不一致。",
            "num_heads 不能整除 embed_dim。",
            "误以为自注意力会自动改变序列长度；当前实现保持 shape 不变。",
        ],
    },
    "VAE": {
        "known": True,
        "layer_type": "VAE",
        "display_name": "VAE 变分自编码器",
        "purpose": "把输入压缩到隐空间再重建输出，适合理解生成模型和重建任务。",
        "input_requirement": "可接收可展平的输入形状，例如图像 [C, H, W]。",
        "output_effect": "输出为一维重建向量，长度默认为输入展平长度，也可由 output_features 指定。",
        "common_position": "常作为重建模型主体，前接 Input，后接 Output。",
        "beginner_tip": "latent_dim 是隐空间大小；太小会难以重建，太大则压缩约束变弱。",
        "common_mistakes": [
            "output_features 与希望重建的展平长度不一致。",
            "把 VAE 当作普通分类层使用，却没有接适合分类的输出头。",
            "latent_dim 设置过小，导致重建信息不足。",
        ],
    },
    "GraphConv": {
        "known": True,
        "layer_type": "GraphConv",
        "display_name": "GraphConv 图卷积层",
        "purpose": "沿图结构的邻接关系聚合节点特征，适合节点分类等图数据任务。",
        "input_requirement": "当前项目约定输入为 [num_nodes, in_features]，表示节点数和每个节点的特征数。",
        "output_effect": "输出为 [num_nodes, out_features]，节点数不变，每个节点的特征维度改变。",
        "common_position": "常在图输入后堆叠一到多层，中间可接 ReLU，最后接 Output。",
        "beginner_tip": "out_features 控制每个节点的新特征维度；节点数量不会被 GraphConv 改变。",
        "common_mistakes": [
            "把普通图像 shape 直接接到 GraphConv。",
            "误以为 out_features 会改变节点数量。",
            "没有准备符合图任务含义的节点特征输入。",
        ],
    },
}


_PARAMETER_ALIASES: dict[str, str] = {
    "shape": "shape",
    "out_channels": "out_channels",
    "outchannels": "out_channels",
    "kernel_size": "kernel_size",
    "kernelsize": "kernel_size",
    "stride": "stride",
    "padding": "padding",
    "in_features": "in_features",
    "infeatures": "in_features",
    "out_features": "out_features",
    "outfeatures": "out_features",
    "p": "p",
    "dropout": "p",
    "dropout_rate": "p",
    "dropoutrate": "p",
    "hidden_size": "hidden_size",
    "hiddensize": "hidden_size",
    "num_layers": "num_layers",
    "numlayers": "num_layers",
    "bidirectional": "bidirectional",
    "return_sequences": "return_sequences",
    "returnsequences": "return_sequences",
    "output_size": "output_size",
    "outputsize": "output_size",
    "target_length": "target_length",
    "targetlength": "target_length",
    "d_model": "d_model",
    "dmodel": "d_model",
    "num_heads": "num_heads",
    "numheads": "num_heads",
    "dim_feedforward": "dim_feedforward",
    "dimfeedforward": "dim_feedforward",
    "embed_dim": "embed_dim",
    "embeddim": "embed_dim",
    "latent_dim": "latent_dim",
    "latentdim": "latent_dim",
    "output_features": "output_features",
    "outputfeatures": "output_features",
}


_PARAMETER_TEACHING: dict[str, dict[str, ParameterTeaching]] = {
    "Input": {
        "shape": {
            "known": True,
            "layer_type": "Input",
            "parameter": "shape",
            "display_name": "shape 输入形状",
            "explanation": "描述单个样本进入模型时的张量形状。",
            "recommendation": "图像任务常用 [通道数, 高, 宽]，例如 MNIST 为 [1, 28, 28]。",
            "increase_effect": "不适用。shape 描述数据本身，不能为了增强模型随意调大。",
            "decrease_effect": "不适用。shape 应与真实输入数据一致，随意调小会丢失或错配数据。",
            "constraint": "必须是非空正整数列表。",
            "common_mistakes": [
                "把 [C, H, W] 写成 [H, W, C]。",
                "shape 中包含 0、负数或字符串。",
                "数据集已经固定，却手动填了不匹配的输入形状。",
            ],
        },
    },
    "Conv2D": {
        "out_channels": {
            "known": True,
            "layer_type": "Conv2D",
            "parameter": "out_channels",
            "display_name": "out_channels 输出通道数",
            "explanation": "决定卷积层输出多少张特征图。",
            "recommendation": "入门模型可从 8、16、32、64 这类值开始。",
            "increase_effect": "能表达更多特征，但计算更慢、参数更多，也更容易过拟合。",
            "decrease_effect": "计算更轻，但可能限制模型提取特征的能力。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "漏填 out_channels。",
                "把它理解成输入通道数；输入通道通常由上一层 shape 决定。",
                "一开始设置得非常大，导致训练慢且容易过拟合。",
            ],
        },
        "kernel_size": {
            "known": True,
            "layer_type": "Conv2D",
            "parameter": "kernel_size",
            "display_name": "kernel_size 卷积核大小",
            "explanation": "决定卷积窗口一次覆盖多大的局部区域。",
            "recommendation": "常用 3 或 5；入门时优先尝试 3。",
            "increase_effect": "单次能看见更大区域，但输出尺寸更容易缩小，计算量也更大。",
            "decrease_effect": "计算更轻、局部性更强，但单层看到的范围更小。",
            "constraint": "必须是正整数，且不能大到让输出高宽无效。",
            "common_mistakes": [
                "kernel_size 大于输入高宽。",
                "忽略 padding，导致输出尺寸缩得过快。",
                "误以为 kernel_size 越大一定越好。",
            ],
        },
        "stride": {
            "known": True,
            "layer_type": "Conv2D",
            "parameter": "stride",
            "display_name": "stride 步长",
            "explanation": "决定卷积窗口每次移动多少格。",
            "recommendation": "常用 1；需要下采样时再考虑 2。",
            "increase_effect": "输出高宽会变小，计算减少，但细节可能丢失更多。",
            "decrease_effect": "输出保留更多空间细节，但计算量更大。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "把 stride 设得过大，导致特征图很快变小。",
                "忘记 stride 会影响后续 Linear 的输入维度。",
                "用 stride 下采样时又接过多 Pooling，尺寸压缩过度。",
            ],
        },
        "padding": {
            "known": True,
            "layer_type": "Conv2D",
            "parameter": "padding",
            "display_name": "padding 填充",
            "explanation": "在输入边缘补零，控制卷积后空间尺寸的变化。",
            "recommendation": "kernel_size=3 时常用 0 或 1；想尽量保持尺寸可用 1。",
            "increase_effect": "输出高宽更不容易缩小，但过大可能引入过多边缘填充。",
            "decrease_effect": "输出尺寸会更快缩小，边缘信息保留更少。",
            "constraint": "必须是非负整数。",
            "common_mistakes": [
                "把 padding 填成负数。",
                "不知道 padding 会改变输出尺寸。",
                "为了保持尺寸随意填很大，导致边缘补零过多。",
            ],
        },
    },
    "Pooling": {
        "kernel_size": {
            "known": True,
            "layer_type": "Pooling",
            "parameter": "kernel_size",
            "display_name": "kernel_size 池化窗口大小",
            "explanation": "决定每次从多大的局部区域中取代表值。",
            "recommendation": "最常见是 2。",
            "increase_effect": "压缩更强，计算更少，但空间细节损失更多。",
            "decrease_effect": "保留更多细节，但下采样效果变弱。",
            "constraint": "必须是正整数，且不能大到让输出高宽无效。",
            "common_mistakes": [
                "窗口大于输入特征图尺寸。",
                "连续多次池化让空间尺寸很快归零。",
                "误以为池化窗口会改变通道数。",
            ],
        },
        "stride": {
            "known": True,
            "layer_type": "Pooling",
            "parameter": "stride",
            "display_name": "stride 池化步长",
            "explanation": "决定池化窗口每次移动多少格。",
            "recommendation": "常用与 kernel_size 相同，例如 kernel_size=2 时 stride=2。",
            "increase_effect": "输出尺寸更小，计算更少，但细节损失更多。",
            "decrease_effect": "输出尺寸更大，保留更多局部信息，但下采样较弱。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "stride 过大导致输出尺寸异常小。",
                "忘记 stride 会影响 Flatten 后的特征数量。",
                "把 stride 留空时不清楚默认值通常与窗口大小相关。",
            ],
        },
        "padding": {
            "known": True,
            "layer_type": "Pooling",
            "parameter": "padding",
            "display_name": "padding 池化填充",
            "explanation": "在池化前对边缘补零，用来影响输出空间尺寸。",
            "recommendation": "池化层通常用 0。",
            "increase_effect": "输出尺寸可能变大一些，但池化边缘会受补零影响。",
            "decrease_effect": "更符合常规池化习惯；为 0 时不额外填充。",
            "constraint": "必须是非负整数。",
            "common_mistakes": [
                "无特殊原因给池化设置很大的 padding。",
                "填成负数。",
                "把池化 padding 和卷积 padding 的作用完全混为一谈。",
            ],
        },
    },
    "Linear": {
        "in_features": {
            "known": True,
            "layer_type": "Linear",
            "parameter": "in_features",
            "display_name": "in_features 输入特征数",
            "explanation": "表示进入全连接层的一维特征长度。",
            "recommendation": "优先由上一层输出自动推导；手动填写时必须与上一层展平后的长度一致。",
            "increase_effect": "不适用。它应匹配上一层输出，不应作为调参项随意增大。",
            "decrease_effect": "不适用。随意调小会与真实输入维度不匹配。",
            "constraint": "如果显式提供，必须是正整数且等于实际输入特征数。",
            "common_mistakes": [
                "把 in_features 猜成类别数。",
                "上一层尺寸变化后忘记同步更新。",
                "卷积输出未 Flatten 就直接估算 in_features。",
            ],
        },
        "out_features": {
            "known": True,
            "layer_type": "Linear",
            "parameter": "out_features",
            "display_name": "out_features 输出特征数",
            "explanation": "决定这一层输出多少个数。",
            "recommendation": "中间层可用 64、128、256；最后分类层通常等于类别数。",
            "increase_effect": "表达能力更强，但参数更多、训练更慢，也可能更容易过拟合。",
            "decrease_effect": "模型更轻，但可能表达能力不足。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "最后分类层输出数与类别数不一致。",
                "中间层设置过大，导致参数量暴涨。",
                "以为 out_features 会自动根据数据集类别数变化。",
            ],
        },
    },
    "Dropout": {
        "p": {
            "known": True,
            "layer_type": "Dropout",
            "parameter": "p",
            "display_name": "p 随机失活比例",
            "explanation": "训练时每个特征被随机置零的概率。",
            "recommendation": "常用 0.2 到 0.5；入门可先试 0.5 或 0.2。",
            "increase_effect": "正则化更强，可能缓解过拟合，但太大会让模型学不动。",
            "decrease_effect": "保留更多信息，训练更稳定，但防过拟合效果更弱。",
            "constraint": "必须是 0 到 1 之间的数值。",
            "common_mistakes": [
                "把 p 写成 50 而不是 0.5。",
                "p 设置过大导致训练准确率也上不去。",
                "误以为 Dropout 在推理时仍会随机丢弃同样比例的神经元。",
            ],
        },
    },
    "LSTM": {
        "hidden_size": {
            "known": True,
            "layer_type": "LSTM",
            "parameter": "hidden_size",
            "display_name": "hidden_size 隐藏维度",
            "explanation": "决定 LSTM 每个方向输出的隐藏状态维度，也就是它保留上下文信息的容量。",
            "recommendation": "入门可从 32 或 64 开始；序列任务简单时不必一开始设很大。",
            "increase_effect": "记忆容量和表达能力更强，但参数更多、训练更慢，也更容易过拟合。",
            "decrease_effect": "模型更轻、训练更快，但可能记不住足够的序列信息。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "开启 bidirectional 后忘记实际输出特征数会翻倍。",
                "把 hidden_size 当作输入特征数。",
                "一开始设置过大，导致小数据集上过拟合。",
            ],
        },
        "num_layers": {
            "known": True,
            "layer_type": "LSTM",
            "parameter": "num_layers",
            "display_name": "num_layers 堆叠层数",
            "explanation": "决定堆叠多少层 LSTM，后一层会继续处理前一层的序列表示。",
            "recommendation": "入门通常先用 1；需要更强表达能力时再尝试 2。",
            "increase_effect": "模型更深，可能表达更复杂序列关系，但训练更慢、更难调。",
            "decrease_effect": "模型更简单稳定，但表达能力可能不足。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "在简单任务上一开始堆很多层。",
                "增加层数后没有同步关注过拟合和训练速度。",
                "误以为 num_layers 会改变输入序列长度。",
            ],
        },
        "bidirectional": {
            "known": True,
            "layer_type": "LSTM",
            "parameter": "bidirectional",
            "display_name": "bidirectional 双向",
            "explanation": "控制 LSTM 是否同时从前往后、从后往前读取序列。",
            "recommendation": "需要同时利用前后文时可开启；实时预测或只应看历史信息的任务通常关闭。",
            "increase_effect": "不适用。它是布尔开关；开启后输出特征数变为 hidden_size 的两倍。",
            "decrease_effect": "不适用。关闭后只按正向读取序列，输出特征数为 hidden_size。",
            "constraint": "必须是布尔值 true 或 false。",
            "common_mistakes": [
                "开启后忘记后续 Linear 的输入维度会变大。",
                "在只能使用过去信息的任务中使用双向读取。",
                "把字符串 yes/no 当作布尔值。",
            ],
        },
        "return_sequences": {
            "known": True,
            "layer_type": "LSTM",
            "parameter": "return_sequences",
            "display_name": "return_sequences 返回完整序列",
            "explanation": "控制 LSTM 返回每个时间步的输出，还是只返回最后一个时间步的输出。",
            "recommendation": "序列分类通常关闭；后续还要逐步处理整个序列时开启。",
            "increase_effect": "不适用。它是布尔开关；开启后输出保留 seq_len 维度。",
            "decrease_effect": "不适用。关闭后只返回最后一步特征，更适合直接接 Linear 做分类。",
            "constraint": "必须是布尔值 true 或 false。",
            "common_mistakes": [
                "开启后直接接只期望一维输入的层。",
                "序列标注任务关闭该选项，导致丢失每步输出。",
                "把字符串 true/false 当作布尔值。",
            ],
        },
    },
    "Seq2Seq": {
        "hidden_size": {
            "known": True,
            "layer_type": "Seq2Seq",
            "parameter": "hidden_size",
            "display_name": "hidden_size 编码隐藏维度",
            "explanation": "决定编码器和解码器内部隐藏状态的维度。",
            "recommendation": "入门可从 32 或 64 开始。",
            "increase_effect": "模型容量更大，能保存更多序列信息，但训练更慢。",
            "decrease_effect": "模型更轻，但可能无法充分表示输入序列。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "把 hidden_size 当成最终输出维度。",
                "设置过大导致小样本任务过拟合。",
                "忽略它会影响模型参数量。",
            ],
        },
        "output_size": {
            "known": True,
            "layer_type": "Seq2Seq",
            "parameter": "output_size",
            "display_name": "output_size 每步输出维度",
            "explanation": "决定目标序列中每个时间步输出多少个特征。",
            "recommendation": "应与任务中每个目标时间步需要表示的特征数一致。",
            "increase_effect": "每个时间步能输出更多特征，但后续处理和损失计算更重。",
            "decrease_effect": "输出更紧凑，但可能不足以表达目标。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "把 output_size 和 target_length 混淆。",
                "输出维度与训练标签每步维度不一致。",
                "误以为它表示整个序列的总长度。",
            ],
        },
        "target_length": {
            "known": True,
            "layer_type": "Seq2Seq",
            "parameter": "target_length",
            "display_name": "target_length 目标序列长度",
            "explanation": "决定解码器要生成多少个时间步。",
            "recommendation": "应根据任务目标序列长度设置，例如模板中使用 6。",
            "increase_effect": "生成序列更长，计算更多，也更容易累积误差。",
            "decrease_effect": "生成序列更短，计算更少，但可能截断目标。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "把 target_length 当作每步输出维度。",
                "目标序列长度与训练标签长度不一致。",
                "为分类任务误用很长的 target_length。",
            ],
        },
        "num_layers": {
            "known": True,
            "layer_type": "Seq2Seq",
            "parameter": "num_layers",
            "display_name": "num_layers 编码器/解码器层数",
            "explanation": "决定编码器和解码器 LSTM 堆叠层数。",
            "recommendation": "入门先用 1；复杂任务再尝试增加。",
            "increase_effect": "序列建模能力可能更强，但训练更慢、调参更难。",
            "decrease_effect": "结构更简单稳定，但表达能力可能较弱。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "层数过多导致训练不稳定。",
                "增加层数后没有关注过拟合。",
                "误以为 num_layers 会改变 target_length。",
            ],
        },
    },
    "TransformerEncoder": {
        "d_model": {
            "known": True,
            "layer_type": "TransformerEncoder",
            "parameter": "d_model",
            "display_name": "d_model 特征维度",
            "explanation": "表示序列中每个位置的特征维度，也是 Transformer 编码器的主维度。",
            "recommendation": "应与输入最后一维一致，并且能被 num_heads 整除；模板中常用 32。",
            "increase_effect": "表示能力更强，但计算量和参数量增加。",
            "decrease_effect": "计算更轻，但可表达的信息减少。",
            "constraint": "必须是正整数，且输入最后一维必须等于 d_model。",
            "common_mistakes": [
                "d_model 与输入最后一维不一致。",
                "d_model 不能被 num_heads 整除。",
                "把 d_model 当成序列长度。",
            ],
        },
        "num_heads": {
            "known": True,
            "layer_type": "TransformerEncoder",
            "parameter": "num_heads",
            "display_name": "num_heads 注意力头数",
            "explanation": "决定把特征维度拆成多少个注意力头并行观察不同关系。",
            "recommendation": "常用 2、4、8；必须能整除 d_model。",
            "increase_effect": "可从更多子空间观察关系，但每个头分到的维度更小，计算也更复杂。",
            "decrease_effect": "结构更简单，但捕捉不同关系的能力可能下降。",
            "constraint": "必须是正整数，且 d_model 必须能被 num_heads 整除。",
            "common_mistakes": [
                "num_heads 不能整除 d_model。",
                "头数设置过多导致每个头维度太小。",
                "把头数当成输出类别数。",
            ],
        },
        "num_layers": {
            "known": True,
            "layer_type": "TransformerEncoder",
            "parameter": "num_layers",
            "display_name": "num_layers 编码器层数",
            "explanation": "决定堆叠多少个 Transformer Encoder 层。",
            "recommendation": "入门先用 1；结构稳定后再尝试增加。",
            "increase_effect": "模型更深，可能捕捉更复杂关系，但训练更慢、更容易过拟合。",
            "decrease_effect": "模型更轻，训练更快，但表达能力可能不足。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "在小任务上一开始堆很多层。",
                "增加层数后没有增加数据或正则化。",
                "误以为层数会改变输出 shape；当前实现保持 shape 不变。",
            ],
        },
        "dim_feedforward": {
            "known": True,
            "layer_type": "TransformerEncoder",
            "parameter": "dim_feedforward",
            "display_name": "dim_feedforward 前馈网络维度",
            "explanation": "决定每个编码器层内部前馈网络的隐藏维度。",
            "recommendation": "通常大于 d_model；模板中 d_model=32 时使用 64。",
            "increase_effect": "前馈部分表达能力增强，但参数和计算增加。",
            "decrease_effect": "计算更轻，但可能限制编码器表达能力。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "设置为 0 或负数。",
                "与 d_model 混淆。",
                "设置过大导致模型变慢。",
            ],
        },
        "dropout": {
            "known": True,
            "layer_type": "TransformerEncoder",
            "parameter": "dropout",
            "display_name": "dropout 随机失活比例",
            "explanation": "控制 Transformer 编码器内部训练时随机失活的比例。",
            "recommendation": "模板中使用 0.1；入门通常在 0 到 0.3 之间尝试。",
            "increase_effect": "正则化更强，可能缓解过拟合，但太大会降低学习效果。",
            "decrease_effect": "保留更多信息，训练更直接，但防过拟合效果减弱。",
            "constraint": "应为 0 到 1 之间的数值。",
            "common_mistakes": [
                "把 10% 写成 10 而不是 0.1。",
                "在小模型中过大设置导致训练困难。",
                "以为 dropout 会改变输出 shape；它不会。",
            ],
        },
    },
    "SelfAttention": {
        "embed_dim": {
            "known": True,
            "layer_type": "SelfAttention",
            "parameter": "embed_dim",
            "display_name": "embed_dim 嵌入维度",
            "explanation": "表示序列中每个位置的特征维度，自注意力输入最后一维需要等于它。",
            "recommendation": "应与输入最后一维一致，并能被 num_heads 整除；模板中常用 32。",
            "increase_effect": "每个位置的表示更丰富，但计算和参数更多。",
            "decrease_effect": "计算更轻，但单个位置能表达的信息减少。",
            "constraint": "必须是正整数，且输入最后一维必须等于 embed_dim。",
            "common_mistakes": [
                "embed_dim 与输入最后一维不一致。",
                "embed_dim 不能被 num_heads 整除。",
                "把 embed_dim 当成序列长度。",
            ],
        },
        "num_heads": {
            "known": True,
            "layer_type": "SelfAttention",
            "parameter": "num_heads",
            "display_name": "num_heads 注意力头数",
            "explanation": "决定自注意力分成多少个头并行计算不同关系。",
            "recommendation": "常用 2、4、8；必须能整除 embed_dim。",
            "increase_effect": "能并行观察更多关系，但每个头分到的特征维度更小。",
            "decrease_effect": "结构更简单，但关系建模的多样性可能下降。",
            "constraint": "必须是正整数，且 embed_dim 必须能被 num_heads 整除。",
            "common_mistakes": [
                "num_heads 不能整除 embed_dim。",
                "头数过多导致每个头太窄。",
                "把头数理解为输出类别数。",
            ],
        },
        "dropout": {
            "known": True,
            "layer_type": "SelfAttention",
            "parameter": "dropout",
            "display_name": "dropout 注意力失活比例",
            "explanation": "控制自注意力训练时随机失活的比例。",
            "recommendation": "模板中使用 0.0；需要正则化时可尝试 0.1。",
            "increase_effect": "正则化更强，但过大可能削弱注意力学习。",
            "decrease_effect": "保留更多注意力信息，但防过拟合效果更弱。",
            "constraint": "应为 0 到 1 之间的数值。",
            "common_mistakes": [
                "把 0.1 写成 10。",
                "在很小模型上设置过高。",
                "误以为 dropout 会改变输出 shape。",
            ],
        },
    },
    "VAE": {
        "latent_dim": {
            "known": True,
            "layer_type": "VAE",
            "parameter": "latent_dim",
            "display_name": "latent_dim 隐空间维度",
            "explanation": "决定 VAE 压缩后隐变量空间的大小。",
            "recommendation": "模板中使用 32；入门可从 16、32、64 尝试。",
            "increase_effect": "隐空间容量更大，重建可能更容易，但压缩约束变弱。",
            "decrease_effect": "压缩更强，但过小会丢失关键信息，重建质量下降。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "设置过小导致重建效果差。",
                "设置过大后隐空间约束不明显。",
                "把 latent_dim 当成最终重建长度。",
            ],
        },
        "output_features": {
            "known": True,
            "layer_type": "VAE",
            "parameter": "output_features",
            "display_name": "output_features 重建输出维度",
            "explanation": "决定 VAE 解码后的重建向量长度。",
            "recommendation": "应与希望重建的数据展平长度一致，例如 MNIST 图像常用 784。",
            "increase_effect": "输出向量更长，可重建更多数值，但需要匹配真实目标。",
            "decrease_effect": "输出更短，但可能无法覆盖完整重建目标。",
            "constraint": "如果提供，必须是正整数。",
            "common_mistakes": [
                "与输入展平长度不一致。",
                "把它当成类别数。",
                "忘记当前 VAE 输出是一维重建向量。",
            ],
        },
    },
    "GraphConv": {
        "out_features": {
            "known": True,
            "layer_type": "GraphConv",
            "parameter": "out_features",
            "display_name": "out_features 输出节点特征数",
            "explanation": "决定每个节点经过图卷积后拥有多少个特征。",
            "recommendation": "中间层可用 16、32、64；节点分类末层通常等于类别数。",
            "increase_effect": "每个节点表示更丰富，但参数和计算增加。",
            "decrease_effect": "模型更轻，但节点表示能力可能不足。",
            "constraint": "必须是正整数。",
            "common_mistakes": [
                "误以为 out_features 会改变节点数量。",
                "末层 out_features 与节点类别数不一致。",
                "把图像通道数当作图节点特征数。",
            ],
        },
    },
}


_ERROR_SUGGESTION_RULES: tuple[dict[str, Any], ...] = (
    {
        "category": "missing_input",
        "title": "缺少 Input 输入节点",
        "match_any": (
            ("缺少必要节点", "Input"),
            ("缺少输入节点",),
        ),
        "reason": "模型没有明确的数据入口，后续层不知道从哪里接收输入张量。",
        "suggestions": [
            "从组件库添加一个 Input 层，并把它连接到第一层可计算层。",
            "检查模型图中是否误删了 Input，或模板加载后连接是否丢失。",
            "确认 Input 的 shape 与当前数据集样本形状一致。",
        ],
        "related_layers": ["Input"],
        "related_parameters": ["shape"],
    },
    {
        "category": "missing_output",
        "title": "缺少 Output 输出节点",
        "match_any": (
            ("缺少必要节点", "Output"),
            ("缺少输出节点",),
        ),
        "reason": "模型没有标记最终输出位置，系统无法确定哪一层结果作为模型输出。",
        "suggestions": [
            "在模型末尾添加 Output 节点。",
            "把最后一个有效计算层连接到 Output。",
            "如果有多条分支，先用 add 或 concat 等方式汇合，再连接到 Output。",
        ],
        "related_layers": ["Output"],
        "related_parameters": [],
    },
    {
        "category": "missing_input_connection",
        "title": "某一层没有输入连接",
        "match_any": (
            ("没有输入连接",),
            ("不在任何 Input 出发的路径上",),
        ),
        "reason": "该层没有接到来自 Input 或前一层的数据，因此无法参与前向传播。",
        "suggestions": [
            "检查报错层左侧是否有连线接入。",
            "从 Input 开始沿数据流逐层检查，确保每个中间层都有前驱节点。",
            "如果该层不需要使用，请从画布中删除，避免形成无效分支。",
        ],
        "related_layers": [],
        "related_parameters": [],
    },
    {
        "category": "missing_output_connection",
        "title": "某一层没有输出连接",
        "match_any": (
            ("没有输出连接",),
            ("无法到达任何 Output",),
        ),
        "reason": "该层的结果没有继续传到后续层或 Output，模型输出不会使用它。",
        "suggestions": [
            "检查报错层右侧是否有连线连到下一层。",
            "确保所有有效分支最终都能到达 Output。",
            "如果这是多余层，请删除它；如果是有效分支，请把它接回主路径。",
        ],
        "related_layers": ["Output"],
        "related_parameters": [],
    },
    {
        "category": "isolated_node",
        "title": "存在孤立节点或异常连接",
        "match_any": (
            ("孤立节点",),
            ("连接异常",),
        ),
        "reason": "模型中存在没有正确接入数据流的节点，可能既没有有效输入，也没有有效输出。",
        "suggestions": [
            "检查被标出的节点是否应该连接到主路径。",
            "从 Input 到 Output 顺着连线走一遍，找出断开的节点。",
            "删除临时拖入但没有使用的层，保持图结构清晰。",
        ],
        "related_layers": [],
        "related_parameters": [],
    },
    {
        "category": "cycle_detected",
        "title": "模型连接中存在环",
        "match_any": (
            ("存在环",),
            ("无法排序",),
        ),
        "reason": "当前模型图需要是从 Input 到 Output 的有向无环图，环形连接会让执行顺序无法确定。",
        "suggestions": [
            "检查报错中列出的节点，找到从后面层又连回前面层的边。",
            "删除造成回路的连线，让数据只沿一个方向流动。",
            "如果想表达残差结构，请使用分支后再合并，而不是把输出连回前面的层。",
        ],
        "related_layers": [],
        "related_parameters": [],
    },
    {
        "category": "missing_merge",
        "title": "多输入节点没有声明合并方式",
        "match_any": (
            ("多个输入", "没有声明合并方式"),
            ("多输入节点", "params.merge"),
            ("请设置 merge 参数",),
        ),
        "reason": "一个节点接收多条分支时，系统需要知道是逐元素相加还是按维度拼接。",
        "suggestions": [
            "如果多条分支 shape 完全一致，可设置 params.merge 为 add 或 sum。",
            "如果想把特征接在一起，可设置 params.merge 为 concat，并检查 dim 参数。",
            "如果并不需要多输入，删除多余连线，只保留一条输入路径。",
        ],
        "related_layers": ["Add"],
        "related_parameters": ["merge", "dim"],
    },
    {
        "category": "add_shape_mismatch",
        "title": "Add 合并的输入 shape 不一致",
        "match_any": (
            ("add 合并要求所有输入 shape 完全一致",),
        ),
        "reason": "逐元素相加要求每个位置都有一一对应的数值，因此所有输入 shape 必须完全相同。",
        "suggestions": [
            "检查参与 add 的每条分支输出 shape 是否完全一致。",
            "调整 Conv2D 的 out_channels、kernel_size、stride 或 padding，让分支输出尺寸对齐。",
            "如果本意是拼接特征，请改用 concat 合并，而不是 add。",
        ],
        "related_layers": ["Add", "Conv2D", "Pooling", "Linear"],
        "related_parameters": ["merge", "out_channels", "kernel_size", "stride", "padding"],
    },
    {
        "category": "concat_shape_mismatch",
        "title": "Concat 合并的非拼接维度不一致",
        "match_any": (
            ("concat 合并要求除拼接维度外其它维度一致",),
            ("concat 合并要求所有输入 shape 维度数量一致",),
        ),
        "reason": "拼接只允许在指定维度上长度不同，其它维度必须完全一致。",
        "suggestions": [
            "确认 concat 的 dim 是否设置为你真正想拼接的维度。",
            "检查各分支除拼接维度外的 shape 是否一致。",
            "通过调整 Conv2D、Pooling 或 Linear 参数，让非拼接维度对齐后再 concat。",
        ],
        "related_layers": ["Conv2D", "Pooling", "Linear"],
        "related_parameters": ["merge", "dim", "kernel_size", "stride", "padding", "out_features"],
    },
    {
        "category": "linear_in_features_mismatch",
        "title": "Linear 输入特征数不匹配",
        "match_any": (
            ("Linear 输入维度与 in_features 不匹配",),
            ("全连接层输入维度对不上",),
        ),
        "reason": "Linear 的 in_features 必须等于上一层实际输出展平后的特征数。",
        "suggestions": [
            "先检查 Linear 前一层的输出 shape，尤其是 Flatten 后的长度。",
            "把 Linear 的 in_features 改成上一层实际输出的特征数，或让系统自动推导。",
            "如果前面改过 Conv2D 或 Pooling 参数，需要重新检查 Flatten 后的维度。",
        ],
        "related_layers": ["Linear", "Flatten", "Conv2D", "Pooling"],
        "related_parameters": ["in_features", "out_features", "kernel_size", "stride", "padding"],
    },
    {
        "category": "pooling_output_shape_invalid",
        "title": "Pooling 输出尺寸无效",
        "match_any": (
            ("Pooling 输出尺寸无效",),
            ("Pooling", "输出尺寸"),
            ("Pooling", "无法推导输出维度"),
        ),
        "reason": "池化窗口、步长或填充与输入 shape 组合后，得到的高或宽不是有效正数。",
        "suggestions": [
            "减小 Pooling 的 kernel_size，确保窗口不大于输入特征图。",
            "检查 stride 是否过大，导致输出尺寸被压缩到 0 或负数。",
            "通常先尝试 kernel_size=2、stride=2、padding=0。",
        ],
        "related_layers": ["Pooling"],
        "related_parameters": ["kernel_size", "stride", "padding"],
    },
    {
        "category": "conv2d_output_shape_invalid",
        "title": "Conv2D 输出尺寸无效",
        "match_any": (
            ("Conv2D 输出尺寸无效",),
            ("Conv2D", "输出尺寸"),
            ("Conv2D", "无法推导输出维度"),
            ("Conv2D", "kernel_size 过大"),
        ),
        "reason": "卷积核、步长或填充与输入高宽组合后，输出高或宽无法成为有效正数。",
        "suggestions": [
            "减小 Conv2D 的 kernel_size，确保卷积核不大于输入高宽。",
            "适当增大 padding，或减小 stride，避免特征图缩小过快。",
            "检查输入 shape 是否为 [通道数, 高, 宽]，并确认高宽是正整数。",
        ],
        "related_layers": ["Conv2D"],
        "related_parameters": ["kernel_size", "stride", "padding", "out_channels"],
    },
    {
        "category": "dropout_p_invalid",
        "title": "Dropout p 取值非法",
        "match_any": (
            ("p 必须是 0 到 1 之间的数值",),
            ("Dropout", "0 到 1"),
        ),
        "reason": "Dropout 的 p 表示随机置零概率，只能写 0 到 1 之间的小数。",
        "suggestions": [
            "把百分比写成小数，例如 50% 应写成 0.5。",
            "常见起点是 0.2 到 0.5，先不要设置得过大。",
            "如果不想使用 Dropout，可将 p 设为 0 或删除 Dropout 层。",
        ],
        "related_layers": ["Dropout"],
        "related_parameters": ["p"],
    },
    {
        "category": "attention_heads_mismatch",
        "title": "注意力维度不能被 num_heads 整除",
        "match_any": (
            ("注意力维度必须能被 num_heads 整除",),
            ("d_model", "num_heads", "整除"),
            ("embed_dim", "num_heads", "整除"),
        ),
        "reason": "多头注意力会把特征维度平均分给多个头，因此 d_model 或 embed_dim 必须能整除 num_heads。",
        "suggestions": [
            "调整 num_heads，让它能整除 d_model 或 embed_dim。",
            "或者调整 d_model/embed_dim，例如 32 搭配 4 个头是常见组合。",
            "检查输入最后一维是否与 d_model 或 embed_dim 一致。",
        ],
        "related_layers": ["TransformerEncoder", "SelfAttention"],
        "related_parameters": ["d_model", "embed_dim", "num_heads"],
    },
    {
        "category": "invalid_integer_parameter",
        "title": "参数整数约束不满足",
        "match_any": (
            ("必须是正整数",),
            ("必须是非负整数",),
        ),
        "reason": "该参数需要整数且有取值范围限制，当前填写的值不符合要求。",
        "suggestions": [
            "检查报错里点名的参数，例如 out_channels、kernel_size、stride、padding 或 out_features。",
            "正整数参数应填写 1、2、3 这类大于 0 的整数。",
            "非负整数参数可以为 0，但不能为负数，例如 padding 常用 0 或 1。",
        ],
        "related_layers": ["Input", "Conv2D", "Pooling", "Linear", "LSTM", "Seq2Seq", "TransformerEncoder", "SelfAttention", "VAE", "GraphConv"],
        "related_parameters": ["shape", "out_channels", "kernel_size", "stride", "padding", "out_features", "hidden_size", "num_layers", "d_model", "embed_dim", "num_heads"],
    },
    {
        "category": "unsupported_layer_type",
        "title": "未知或暂不支持的层类型",
        "match_any": (
            ("暂不支持该层类型",),
            ("UNSUPPORTED_LAYER_TYPE",),
        ),
        "reason": "当前项目只支持内置层类型，不能直接使用未收录的自定义层名。",
        "suggestions": [
            "检查层名拼写是否与组件库中的规范层名一致。",
            "优先使用当前支持的层：Input、Conv2D、Pooling、Linear、LSTM、SelfAttention 等。",
            "如果需要新层，应先在项目的模型构建、校验和教学知识中统一增加支持。",
        ],
        "related_layers": [],
        "related_parameters": [],
    },
)


def list_supported_layers() -> list[str]:
    """返回当前知识库支持的规范层名，不包含别名。"""
    return [
        canonical_name
        for canonical_name, metadata in _LAYER_REGISTRY.items()
        if metadata["has_teaching"]
    ]


def get_layer_teaching(layer_type: str) -> dict[str, Any]:
    """查询层级教学说明。

    层名支持大小写和常见别名兼容。未知层、空值或非字符串输入不会抛异常，
    而是返回 known=False 的统一兜底结构。
    """
    canonical_layer = _normalize_layer_type(layer_type, require_teaching=True)
    if canonical_layer is None:
        return copy.deepcopy(_unknown_layer_teaching(layer_type))
    return copy.deepcopy(_LAYER_TEACHING[canonical_layer])


def get_parameter_teaching(layer_type: str, param_name: str) -> dict[str, Any]:
    """查询参数教学说明。

    层名支持常见别名和大小写兼容，参数名支持合理的大小写兼容。
    未知层或未知参数不会抛异常，而是返回 known=False 的统一兜底结构。
    """
    canonical_layer = _normalize_layer_type(layer_type, require_teaching=True)
    canonical_param = _canonical_parameter_name(param_name, canonical_layer)
    if canonical_layer is None or canonical_param is None:
        return copy.deepcopy(_unknown_parameter_teaching(layer_type, param_name, canonical_layer))

    parameter_info = _PARAMETER_TEACHING.get(canonical_layer, {}).get(canonical_param)
    if parameter_info is None:
        return copy.deepcopy(_unknown_parameter_teaching(layer_type, param_name, canonical_layer))
    return copy.deepcopy(parameter_info)


def get_teaching_catalog() -> dict[str, Any]:
    """返回当前全部层说明和参数说明的结构化目录。"""
    return copy.deepcopy({
        "layers": {
            layer_type: _LAYER_TEACHING[layer_type]
            for layer_type in list_supported_layers()
        },
        "parameters": {
            layer_type: parameters
            for layer_type, parameters in _PARAMETER_TEACHING.items()
            if _normalize_layer_type(layer_type, require_teaching=True) is not None
        },
        "supported_layers": list_supported_layers(),
    })


def get_error_suggestion(error_message: str, context: dict | None = None) -> dict[str, Any]:
    """根据真实校验错误文本返回独立的教学排查建议。

    本函数不调用 validator，也不修改原始错误文本。context 仅作为未来扩展预留；
    当前实现即使没有 context，也会仅根据错误文本给出建议。
    """
    _ = context
    normalized_message = _normalize_error_message(error_message)
    if not normalized_message:
        return copy.deepcopy(_unknown_error_suggestion(error_message))

    for rule in _ERROR_SUGGESTION_RULES:
        if _error_rule_matches(normalized_message, rule):
            return copy.deepcopy(_build_error_suggestion(rule, error_message))

    return copy.deepcopy(_unknown_error_suggestion(error_message))


def explain_model_graph(model_graph: dict) -> dict[str, Any]:
    """生成整张模型图的教学性概览。

    该函数只解释模型组成和大致数据流，不进行合法性校验，也不调用 validator。
    """
    if not isinstance(model_graph, dict):
        return copy.deepcopy(_unknown_model_graph_explanation("模型图必须是字典结构。"))

    raw_layers = model_graph.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        return copy.deepcopy(_unknown_model_graph_explanation("模型图缺少可解释的 layers 列表。"))

    raw_connections = model_graph.get("connections", [])
    if not isinstance(raw_connections, list):
        return copy.deepcopy(_unknown_model_graph_explanation("模型图的 connections 字段不是列表。"))

    layers, extraction_warnings = _extract_model_layers(raw_layers)
    if not layers:
        explanation = _unknown_model_graph_explanation("layers 中没有可解释的层配置。")
        explanation["beginner_warnings"].extend(extraction_warnings)
        return copy.deepcopy(explanation)

    connections, connection_warnings = _extract_model_connections(raw_connections)
    ordered_layers, flow_warnings = _order_layers_for_flow(layers, connections)
    layer_types = [layer["layer_type"] for layer in layers]
    model_family = _detect_model_family(layer_types)
    layer_type_counts = _count_layer_types(layer_types)
    flow = [_flow_item(layer) for layer in ordered_layers]
    key_layers = _key_layers(layers)
    warnings = (
        extraction_warnings
        + connection_warnings
        + flow_warnings
        + _beginner_warnings(layers, connections)
    )

    result = {
        "understood": True,
        "model_family": model_family,
        "title": _model_title(model_family),
        "summary": _model_summary(model_family, len(layers), len(connections)),
        "layer_count": len(layers),
        "connection_count": len(connections),
        "layer_type_counts": layer_type_counts,
        "flow": flow,
        "key_layers": key_layers,
        "learning_points": _learning_points(model_family),
        "beginner_warnings": warnings,
    }
    return copy.deepcopy(result)


def _normalize_layer_type(layer_type: Any, require_teaching: bool = False) -> str | None:
    if not isinstance(layer_type, str):
        return None
    key = _compact_key(layer_type)
    if not key:
        return None
    canonical_layer = _LAYER_NAME_INDEX.get(key)
    if canonical_layer is None:
        return None
    if require_teaching and not _LAYER_REGISTRY[canonical_layer]["has_teaching"]:
        return None
    return canonical_layer


def _canonical_parameter_name(param_name: Any, canonical_layer: str | None = None) -> str | None:
    if not isinstance(param_name, str):
        return None
    stripped = param_name.strip()
    if not stripped:
        return None

    underscore_key = stripped.lower().replace("-", "_").replace(" ", "_")
    while "__" in underscore_key:
        underscore_key = underscore_key.replace("__", "_")
    compact_key = _compact_key(stripped)

    if canonical_layer in ("SelfAttention", "TransformerEncoder"):
        if underscore_key in ("dropout", "dropout_rate") or compact_key in ("dropout", "dropoutrate"):
            return "dropout"

    return _PARAMETER_ALIASES.get(underscore_key) or _PARAMETER_ALIASES.get(compact_key)


def _compact_key(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _safe_text(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _normalize_error_message(error_message: Any) -> str:
    if not isinstance(error_message, str):
        return ""
    return error_message.strip()


def _error_rule_matches(error_text: str, rule: dict[str, Any]) -> bool:
    lowered_text = error_text.lower()
    return any(
        all(str(keyword).lower() in lowered_text for keyword in keyword_group)
        for keyword_group in rule["match_any"]
    )


def _build_error_suggestion(rule: dict[str, Any], original_error: Any) -> ErrorSuggestion:
    return {
        "matched": True,
        "category": rule["category"],
        "title": rule["title"],
        "original_error": original_error,
        "reason": rule["reason"],
        "suggestions": list(rule["suggestions"]),
        "related_layers": list(rule["related_layers"]),
        "related_parameters": list(rule["related_parameters"]),
    }


def _unknown_error_suggestion(original_error: Any) -> ErrorSuggestion:
    return {
        "matched": False,
        "category": "unknown_error",
        "title": "暂未识别的错误",
        "original_error": original_error,
        "reason": "当前教学知识库还没有匹配到明确的错误类型。",
        "suggestions": [
            "先查看模型是否从 Input 连到 Output，且中间没有断开的节点。",
            "再检查出错层附近的参数是否符合要求，例如正整数、非负整数或 0 到 1 的概率。",
            "如果错误来自某个具体层，请结合层说明和参数说明逐项排查。",
        ],
        "related_layers": [],
        "related_parameters": [],
    }


def _unknown_model_graph_explanation(reason: str) -> dict[str, Any]:
    return {
        "understood": False,
        "model_family": "Unknown",
        "title": "暂无法解释模型结构",
        "summary": "当前输入还不是一个可解释的模型图。请确认它包含 layers 列表和 connections 列表。",
        "layer_count": 0,
        "connection_count": 0,
        "layer_type_counts": {},
        "flow": [],
        "key_layers": [],
        "learning_points": [
            "一个可解释的模型图通常需要包含层列表 layers。",
            "每个层建议包含 id、type、name 和 params 等字段。",
            "connections 用 source 和 target 描述层之间的数据流。",
        ],
        "beginner_warnings": [reason],
    }


def _extract_model_layers(raw_layers: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    layers = []
    warnings = []
    for index, layer in enumerate(raw_layers, start=1):
        if not isinstance(layer, dict):
            warnings.append(f"第 {index} 个 layer 不是字典，已在教学概览中跳过。")
            continue

        raw_id = layer.get("id")
        raw_type = layer.get("type")
        layer_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f"layer_{index}"
        requested_type = raw_type.strip() if isinstance(raw_type, str) and raw_type.strip() else "Unknown"
        teaching_info = get_layer_teaching(requested_type)
        layer_type = teaching_info["layer_type"] if teaching_info.get("known") else requested_type
        params = layer.get("params") if isinstance(layer.get("params"), dict) else {}

        if not teaching_info.get("known"):
            warnings.append(f"层 {layer_id} 的类型 {requested_type} 当前教学知识库未收录。")

        layers.append({
            "layer_id": layer_id,
            "layer_type": layer_type,
            "display_name": teaching_info.get("display_name", requested_type),
            "name": layer.get("name") if isinstance(layer.get("name"), str) else None,
            "params": params,
        })
    return layers, warnings


def _extract_model_connections(raw_connections: list[Any]) -> tuple[list[dict[str, str]], list[str]]:
    connections = []
    warnings = []
    for index, connection in enumerate(raw_connections, start=1):
        if not isinstance(connection, dict):
            warnings.append(f"第 {index} 条 connection 不是字典，已在教学概览中跳过。")
            continue
        source = connection.get("source")
        target = connection.get("target")
        if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
            warnings.append(f"第 {index} 条 connection 缺少有效 source 或 target，已跳过。")
            continue
        connections.append({"source": source.strip(), "target": target.strip()})
    return connections, warnings


def _order_layers_for_flow(
    layers: list[dict[str, Any]],
    connections: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if len(layers) <= 1:
        return list(layers), []
    if not connections:
        return list(layers), ["当前模型没有 connections，教学概览按 layers 原顺序展示数据流。"]

    layer_by_id = {layer["layer_id"]: layer for layer in layers}
    layer_ids = [layer["layer_id"] for layer in layers]
    adjacency = {layer_id: [] for layer_id in layer_ids}
    in_degree = {layer_id: 0 for layer_id in layer_ids}

    for connection in connections:
        source = connection["source"]
        target = connection["target"]
        if source not in layer_by_id or target not in layer_by_id:
            continue
        adjacency[source].append(target)
        in_degree[target] += 1

    ready = [layer_id for layer_id in layer_ids if in_degree[layer_id] == 0]
    ordered_ids = []
    while ready:
        current = ready.pop(0)
        ordered_ids.append(current)
        for target in adjacency[current]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                ready.append(target)

    if len(ordered_ids) != len(layer_ids):
        return list(layers), ["当前连接关系无法确定完整顺序，教学概览按 layers 原顺序展示。"]

    return [layer_by_id[layer_id] for layer_id in ordered_ids], []


def _detect_model_family(layer_types: list[str]) -> str:
    type_set = set(layer_types)
    major_families = []
    if {"Conv2D", "Pooling"} & type_set:
        major_families.append("CNN")
    if "LSTM" in type_set:
        major_families.append("LSTM")
    if "Seq2Seq" in type_set:
        major_families.append("Seq2Seq")
    if {"TransformerEncoder", "SelfAttention"} & type_set:
        major_families.append("Transformer")
    if "VAE" in type_set:
        major_families.append("VAE")
    if "GraphConv" in type_set:
        major_families.append("GNN")

    if len(major_families) >= 2:
        return "Hybrid"
    if major_families:
        return major_families[0]
    if type_set & {"Flatten", "Linear", "ReLU", "Dropout"} and type_set <= {"Input", "Output", "Flatten", "Linear", "ReLU", "Dropout"}:
        return "MLP"
    return "Unknown"


def _count_layer_types(layer_types: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for layer_type in layer_types:
        counts[layer_type] = counts.get(layer_type, 0) + 1
    return counts


def _flow_item(layer: dict[str, Any]) -> dict[str, Any]:
    return {
        "layer_id": layer["layer_id"],
        "layer_type": layer["layer_type"],
        "display_name": layer["display_name"],
    }


_KEY_LAYER_ROLES: dict[str, str] = {
    "Conv2D": "提取图像或特征图中的局部特征。",
    "Pooling": "压缩空间尺寸，减少计算量并保留显著响应。",
    "Flatten": "把多维特征展平成一维向量，方便接入 Linear。",
    "Linear": "组合特征并映射到指定输出维度。",
    "Dropout": "训练时随机失活，帮助缓解过拟合。",
    "Add": "合并多条 shape 一致的分支，常用于残差连接。",
    "LSTM": "按时间顺序处理序列并保留上下文。",
    "Seq2Seq": "把输入序列编码后生成目标序列。",
    "TransformerEncoder": "用自注意力编码序列中各位置的关系。",
    "SelfAttention": "让序列每个位置参考其它位置更新表示。",
    "VAE": "把输入压缩到隐空间并重建输出。",
    "GraphConv": "沿图结构聚合节点邻居特征。",
}


def _key_layers(layers: list[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    for layer in layers:
        role = _KEY_LAYER_ROLES.get(layer["layer_type"])
        if role:
            result.append({
                "layer_id": layer["layer_id"],
                "layer_type": layer["layer_type"],
                "role": role,
            })
    return result


def _learning_points(model_family: str) -> list[str]:
    points = {
        "CNN": [
            "关注 Conv2D 的 out_channels 如何改变通道数。",
            "观察 kernel_size、stride、padding 如何影响特征图高宽。",
            "在进入 Linear 前，通常需要用 Flatten 展平特征。",
        ],
        "MLP": [
            "关注 Flatten 如何把输入变成一维特征。",
            "Linear 的输入维度应与上一层输出长度一致。",
            "ReLU 提供非线性，Dropout 可帮助缓解过拟合。",
        ],
        "LSTM": [
            "关注输入 shape 中的序列长度和每步特征数。",
            "hidden_size 决定 LSTM 输出特征容量。",
            "bidirectional=True 时输出维度可能翻倍。",
        ],
        "Seq2Seq": [
            "关注 source_length 和 target_length 的区别。",
            "output_size 决定目标序列每一步的输出维度。",
            "hidden_size 控制编码器和解码器内部表示能力。",
        ],
        "Transformer": [
            "关注输入最后一维是否等于 d_model 或 embed_dim。",
            "num_heads 必须与特征维度整除配合。",
            "Transformer/SelfAttention 通常保持输入输出 shape 一致。",
        ],
        "VAE": [
            "关注 latent_dim 如何控制隐空间压缩程度。",
            "output_features 应与希望重建的展平长度匹配。",
            "VAE 更适合理解重建与生成任务，而不是直接分类。",
        ],
        "GNN": [
            "关注输入 shape 中的节点数和每个节点的特征维度。",
            "GraphConv 改变节点特征维度，但不改变节点数量。",
            "节点分类末层的 out_features 通常对应类别数。",
        ],
        "Hybrid": [
            "模型混合了多类结构，建议分段理解每一部分的输入输出。",
            "先确认不同结构交界处的 shape 是否能衔接。",
            "复杂模型更需要关注关键层参数对数据流的影响。",
        ],
        "Unknown": [
            "先确认模型使用的层类型是否在当前知识库中。",
            "从 Input 到 Output 顺着连接理解数据流。",
        ],
    }
    return list(points.get(model_family, points["Unknown"]))


def _beginner_warnings(layers: list[dict[str, Any]], connections: list[dict[str, str]]) -> list[str]:
    warnings = []
    layer_types = [layer["layer_type"] for layer in layers]
    layer_by_id = {layer["layer_id"]: layer for layer in layers}

    if "Input" not in layer_types:
        warnings.append("建议先确认模型入口：当前图中没有 Input 层。")
    if "Output" not in layer_types:
        warnings.append("建议先确认模型出口：当前图中没有 Output 层。")

    for connection in connections:
        source = layer_by_id.get(connection["source"])
        target = layer_by_id.get(connection["target"])
        if source and target and source["layer_type"] == "Conv2D" and target["layer_type"] == "Linear":
            warnings.append("Conv2D 后直接连接 Linear 时，请特别关注是否需要先经过 Flatten。")

    for layer in layers:
        if layer["layer_type"] == "LSTM" and layer["params"].get("bidirectional") is True:
            warnings.append(f"层 {layer['layer_id']} 开启了双向 LSTM，输出维度通常会变为 hidden_size 的两倍。")
        if layer["layer_type"] in ("TransformerEncoder", "SelfAttention"):
            warnings.append(f"层 {layer['layer_id']} 使用注意力结构，请确认特征维度能被 num_heads 合理整除。")
        if get_layer_teaching(layer["layer_type"]).get("known") is False:
            warnings.append(f"层 {layer['layer_id']} 的类型 {layer['layer_type']} 当前知识库未收录。")

    return _unique_strings(warnings)


def _model_title(model_family: str) -> str:
    titles = {
        "CNN": "卷积神经网络概览",
        "MLP": "多层感知机概览",
        "LSTM": "LSTM 序列模型概览",
        "Seq2Seq": "Seq2Seq 序列转换模型概览",
        "Transformer": "注意力模型概览",
        "VAE": "变分自编码器概览",
        "GNN": "图神经网络概览",
        "Hybrid": "混合结构模型概览",
        "Unknown": "模型结构概览",
    }
    return titles.get(model_family, titles["Unknown"])


def _model_summary(model_family: str, layer_count: int, connection_count: int) -> str:
    descriptions = {
        "CNN": "这个模型包含卷积或池化结构，重点在于图像/特征图的通道数和空间尺寸变化。",
        "MLP": "这个模型主要由展平、全连接、激活和正则化层组成，适合理解基础分类流程。",
        "LSTM": "这个模型包含 LSTM，重点在于序列长度、每步特征和隐藏状态维度。",
        "Seq2Seq": "这个模型包含编码器-解码器序列结构，重点在输入序列到目标序列的转换。",
        "Transformer": "这个模型包含自注意力结构，重点在特征维度、注意力头数和序列关系建模。",
        "VAE": "这个模型包含 VAE，重点在隐空间压缩和重建输出。",
        "GNN": "这个模型包含图卷积，重点在节点数和节点特征维度。",
        "Hybrid": "这个模型混合了多类结构，建议按模块分段理解数据流。",
        "Unknown": "这个模型的主要类型暂不明确，可先从层列表和连接关系理解数据流。",
    }
    return f"{descriptions.get(model_family, descriptions['Unknown'])} 当前共有 {layer_count} 个层和 {connection_count} 条连接。"


def _unique_strings(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _unknown_layer_teaching(layer_type: Any) -> LayerTeaching:
    requested = _safe_text(layer_type, "<unknown>")
    return {
        "known": False,
        "layer_type": requested,
        "display_name": requested,
        "purpose": "当前教学知识库还没有收录这一层。",
        "input_requirement": "暂无该层的输入要求说明。",
        "output_effect": "暂无该层的输出变化说明。",
        "common_position": "暂无该层的常见位置说明。",
        "beginner_tip": "请先确认层名是否拼写正确，或查看当前支持的层类型列表。",
        "common_mistakes": [
            "层名拼写或大小写不符合当前项目约定。",
            "使用了当前版本尚未收录的自定义层。",
        ],
    }


def _unknown_parameter_teaching(
    layer_type: Any,
    param_name: Any,
    canonical_layer: str | None,
) -> ParameterTeaching:
    requested_layer = canonical_layer or _safe_text(layer_type, "<unknown>")
    requested_param = _safe_text(param_name, "<unknown>")
    return {
        "known": False,
        "layer_type": requested_layer,
        "parameter": requested_param,
        "display_name": requested_param,
        "explanation": "当前教学知识库还没有收录这个参数。",
        "recommendation": "请先确认层名和参数名是否拼写正确。",
        "increase_effect": "暂无调大影响说明。",
        "decrease_effect": "暂无调小影响说明。",
        "constraint": "暂无约束说明。",
        "common_mistakes": [
            "参数名拼写不符合当前项目约定。",
            "该参数属于尚未收录的层或下一阶段功能。",
        ],
    }
