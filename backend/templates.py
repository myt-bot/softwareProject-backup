"""内置入门模型模板。

模板返回统一的 ModelGraph 字典，便于后续接入 API、前端画布或测试。
"""


def _layer(layer_id, layer_type, name=None, params=None):
    """创建一个模型层配置。"""
    return {
        "id": layer_id,
        "type": layer_type,
        "name": name or layer_type,
        "params": params or {},
    }


def _connection(source, target):
    """创建一条模型图连接。"""
    return {
        "source": source,
        "target": target,
    }


def _graph(layers, connections):
    """创建标准 ModelGraph 字典。"""
    return {
        "layers": layers,
        "connections": connections,
    }


def _meta(key, name, description, family, input_shape, output_shape):
    """创建模板元信息。"""
    return {
        "key": key,
        "name": name,
        "description": description,
        "family": family,
        "input_shape": input_shape,
        "output_shape": output_shape,
    }


def get_available_templates():
    """返回前端可选择的模型模板，例如 MLP 和 CNN。"""
    return [
        _meta("linear_classifier", "Linear Classifier", "最小线性分类基线。", "feedforward", [1, 28, 28], [10]),
        _meta("mlp", "MLP", "经典多层感知机。", "feedforward", [1, 28, 28], [10]),
        _meta("perceptron", "Perceptron", "单隐藏层感知机。", "feedforward", [1, 28, 28], [10]),
        _meta("lenet", "LeNet", "经典早期卷积网络。", "cnn", [1, 28, 28], [10]),
        _meta("resnet_tiny", "ResNet Tiny", "简化残差网络，用于理解跳连思想。", "cnn", [1, 28, 28], [10]),
        _meta("lstm", "LSTM", "基础序列分类模板。", "sequence", [12, 8], [4]),
        _meta("seq2seq", "Seq2Seq", "简化编码器-解码器序列转换模板。", "sequence", [10, 16], [6, 12]),
        _meta("transformer_encoder_tiny", "Transformer Encoder Tiny", "迷你 Transformer 编码器分类模板。", "attention", [16, 32], [5]),
        _meta("self_attention_demo", "Self-Attention Demo", "单层多头自注意力演示模板。", "attention", [8, 32], [3]),
        _meta("vae", "VAE", "变分自编码器重建模板。", "generative", [1, 28, 28], [784]),
        _meta("gcn_tiny", "GCN Tiny", "简化图卷积节点分类模板。", "graph", [20, 16], [20, 7]),
    ]


def create_linear_classifier_template():
    """创建线性分类器模板。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("flatten", "Flatten", "Flatten Image"),
        _layer("classifier", "Linear", "Linear Classifier", {"out_features": 10}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "flatten"),
        _connection("flatten", "classifier"),
        _connection("classifier", "output"),
    ])


def create_mlp_template():
    """创建适合初学者使用的 MLP 模板图。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("flatten", "Flatten", "Flatten Image"),
        _layer("fc1", "Linear", "Hidden Layer 1", {"out_features": 256}),
        _layer("relu1", "ReLU", "Activation 1"),
        _layer("dropout", "Dropout", "Dropout", {"p": 0.2}),
        _layer("fc2", "Linear", "Hidden Layer 2", {"out_features": 64}),
        _layer("relu2", "ReLU", "Activation 2"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 10}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "flatten"),
        _connection("flatten", "fc1"),
        _connection("fc1", "relu1"),
        _connection("relu1", "dropout"),
        _connection("dropout", "fc2"),
        _connection("fc2", "relu2"),
        _connection("relu2", "classifier"),
        _connection("classifier", "output"),
    ])


def create_perceptron_template():
    """创建单隐藏层感知机模板。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("flatten", "Flatten", "Flatten Image"),
        _layer("hidden", "Linear", "Hidden Layer", {"out_features": 64}),
        _layer("relu", "ReLU", "Activation"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 10}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "flatten"),
        _connection("flatten", "hidden"),
        _connection("hidden", "relu"),
        _connection("relu", "classifier"),
        _connection("classifier", "output"),
    ])


def create_lenet_template():
    """创建经典 LeNet 风格模板。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("conv1", "Conv2D", "Conv 1", {"out_channels": 6, "kernel_size": 5, "stride": 1, "padding": 2}),
        _layer("relu1", "ReLU", "Activation 1"),
        _layer("pool1", "Pooling", "Pooling 1", {"kernel_size": 2, "stride": 2, "padding": 0}),
        _layer("conv2", "Conv2D", "Conv 2", {"out_channels": 16, "kernel_size": 5, "stride": 1, "padding": 0}),
        _layer("relu2", "ReLU", "Activation 2"),
        _layer("pool2", "Pooling", "Pooling 2", {"kernel_size": 2, "stride": 2, "padding": 0}),
        _layer("flatten", "Flatten", "Flatten Features"),
        _layer("fc1", "Linear", "Dense Layer", {"out_features": 120}),
        _layer("relu3", "ReLU", "Activation 3"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 10}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "conv1"),
        _connection("conv1", "relu1"),
        _connection("relu1", "pool1"),
        _connection("pool1", "conv2"),
        _connection("conv2", "relu2"),
        _connection("relu2", "pool2"),
        _connection("pool2", "flatten"),
        _connection("flatten", "fc1"),
        _connection("fc1", "relu3"),
        _connection("relu3", "classifier"),
        _connection("classifier", "output"),
    ])


def create_resnet_tiny_template():
    """创建简化 ResNet 模板，使用 add 合并表示残差连接。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("stem", "Conv2D", "Stem Conv", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
        _layer("relu1", "ReLU", "Stem Activation"),
        _layer("res_conv", "Conv2D", "Residual Conv", {"out_channels": 8, "kernel_size": 3, "stride": 1, "padding": 1}),
        _layer("res_relu", "ReLU", "Residual Activation"),
        _layer("merge", "ReLU", "Residual Add", {"merge": "add"}),
        _layer("pool", "Pooling", "Pooling", {"kernel_size": 2, "stride": 2, "padding": 0}),
        _layer("flatten", "Flatten", "Flatten Features"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 10}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "stem"),
        _connection("stem", "relu1"),
        _connection("relu1", "res_conv"),
        _connection("res_conv", "res_relu"),
        _connection("relu1", "merge"),
        _connection("res_relu", "merge"),
        _connection("merge", "pool"),
        _connection("pool", "flatten"),
        _connection("flatten", "classifier"),
        _connection("classifier", "output"),
    ])


def create_lstm_template():
    """创建 LSTM 序列分类模板。"""
    layers = [
        _layer("input", "Input", "Sequence Input", {"shape": [12, 8]}),
        _layer("lstm", "LSTM", "LSTM Encoder", {"hidden_size": 32, "num_layers": 1, "return_sequences": False}),
        _layer("classifier", "Linear", "Sequence Classifier", {"out_features": 4}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "lstm"),
        _connection("lstm", "classifier"),
        _connection("classifier", "output"),
    ])


def create_seq2seq_template():
    """创建 Seq2Seq 序列转换模板。"""
    layers = [
        _layer("input", "Input", "Source Sequence", {"shape": [10, 16]}),
        _layer("seq2seq", "Seq2Seq", "Encoder Decoder", {
            "hidden_size": 32,
            "output_size": 12,
            "target_length": 6,
            "num_layers": 1,
        }),
        _layer("output", "Output", "Target Sequence"),
    ]
    return _graph(layers, [
        _connection("input", "seq2seq"),
        _connection("seq2seq", "output"),
    ])


def create_transformer_encoder_tiny_template():
    """创建迷你 Transformer Encoder 分类模板。"""
    layers = [
        _layer("input", "Input", "Token Embeddings", {"shape": [16, 32]}),
        _layer("encoder", "TransformerEncoder", "Transformer Encoder", {
            "d_model": 32,
            "num_heads": 4,
            "num_layers": 1,
            "dim_feedforward": 64,
            "dropout": 0.1,
        }),
        _layer("flatten", "Flatten", "Flatten Tokens"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 5}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "encoder"),
        _connection("encoder", "flatten"),
        _connection("flatten", "classifier"),
        _connection("classifier", "output"),
    ])


def create_self_attention_demo_template():
    """创建单层自注意力演示模板。"""
    layers = [
        _layer("input", "Input", "Token Embeddings", {"shape": [8, 32]}),
        _layer("attention", "SelfAttention", "Self Attention", {"embed_dim": 32, "num_heads": 4, "dropout": 0.0}),
        _layer("flatten", "Flatten", "Flatten Tokens"),
        _layer("classifier", "Linear", "Classifier", {"out_features": 3}),
        _layer("output", "Output", "Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "attention"),
        _connection("attention", "flatten"),
        _connection("flatten", "classifier"),
        _connection("classifier", "output"),
    ])


def create_vae_template():
    """创建 VAE 重建模板。"""
    layers = [
        _layer("input", "Input", "Image Input", {"shape": [1, 28, 28]}),
        _layer("vae", "VAE", "Variational AutoEncoder", {"latent_dim": 32, "output_features": 784}),
        _layer("output", "Output", "Reconstruction Output"),
    ]
    return _graph(layers, [
        _connection("input", "vae"),
        _connection("vae", "output"),
    ])


def create_gcn_tiny_template():
    """创建简化 GCN 节点分类模板。"""
    layers = [
        _layer("input", "Input", "Graph Node Features", {"shape": [20, 16]}),
        _layer("gcn1", "GraphConv", "Graph Conv 1", {"out_features": 32}),
        _layer("relu", "ReLU", "Activation"),
        _layer("gcn2", "GraphConv", "Graph Conv 2", {"out_features": 7}),
        _layer("output", "Output", "Node Class Output"),
    ]
    return _graph(layers, [
        _connection("input", "gcn1"),
        _connection("gcn1", "relu"),
        _connection("relu", "gcn2"),
        _connection("gcn2", "output"),
    ])


def create_cnn_template():
    """保留兼容入口：当前 CNN 默认返回 LeNet 模板。"""
    return create_lenet_template()


def apply_template(template_name):
    """返回用户选择的模板图，供前端加载到画布中。"""
    if not isinstance(template_name, str) or not template_name.strip():
        return {
            "status": "error",
            "message": "template_name 必须是非空字符串",
        }

    normalized_name = template_name.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "linear": create_linear_classifier_template,
        "linear_classifier": create_linear_classifier_template,
        "mlp": create_mlp_template,
        "perceptron": create_perceptron_template,
        "cnn": create_cnn_template,
        "lenet": create_lenet_template,
        "resnet_tiny": create_resnet_tiny_template,
        "lstm": create_lstm_template,
        "seq2seq": create_seq2seq_template,
        "transformer": create_transformer_encoder_tiny_template,
        "transformer_encoder": create_transformer_encoder_tiny_template,
        "transformer_encoder_tiny": create_transformer_encoder_tiny_template,
        "self_attention": create_self_attention_demo_template,
        "self_attention_demo": create_self_attention_demo_template,
        "vae": create_vae_template,
        "gcn": create_gcn_tiny_template,
        "gcn_tiny": create_gcn_tiny_template,
    }

    factory = aliases.get(normalized_name)
    if factory is None:
        return {
            "status": "error",
            "message": f"模板不存在: {template_name}",
            "available_templates": [template["key"] for template in get_available_templates()],
        }

    return {
        "status": "ok",
        "template": normalized_name,
        "model": factory(),
    }
