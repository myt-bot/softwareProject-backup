import argparse
import os
import torch
import torch.nn as nn
import torch.utils.data
import torchvision

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

class M6CifarAdapterModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.layer_conv = nn.Conv2d(in_channels=1, out_channels=4, kernel_size=3, stride=1, padding=1, padding_mode='zeros')
        self.layer_flat = nn.Flatten()
        self.layer_classifier = nn.Linear(in_features=3136, out_features=10)

    def forward(self, x):
        outputs = {}
        out_input = x
        outputs['input'] = out_input
        out_conv = self.layer_conv(outputs['input'])
        outputs['conv'] = out_conv
        out_flat = self.layer_flat(outputs['conv'])
        outputs['flat'] = out_flat
        out_classifier = self.layer_classifier(outputs['flat'])
        outputs['classifier'] = out_classifier
        out_out = outputs['classifier']
        outputs['out'] = out_out
        return outputs['out']

TRAIN_CONFIG = {'dataset_name': 'CIFAR10', 'epochs': 1, 'batch_size': 1, 'rate': 0.001, 'device': 'cpu', 'loss_fn': 'cross_entropy', 'optimizer': 'sgd', 'data_dir': '', 'artifacts_dir': ''}

DATASET_SPECS = {
    'MNIST': {'class': torchvision.datasets.MNIST, 'shape': [1, 28, 28], 'classes': 10},
    'FashionMNIST': {'class': torchvision.datasets.FashionMNIST, 'shape': [1, 28, 28], 'classes': 10},
    'KMNIST': {'class': torchvision.datasets.KMNIST, 'shape': [1, 28, 28], 'classes': 10},
    'CIFAR10': {'class': torchvision.datasets.CIFAR10, 'shape': [3, 32, 32], 'classes': 10},
    'CIFAR100': {'class': torchvision.datasets.CIFAR100, 'shape': [3, 32, 32], 'classes': 100},
}


MODEL_INPUTS = [{'id': 'input', 'shape': [1, 28, 28]}]
MODEL_INPUT_SHAPES = [item['shape'] for item in MODEL_INPUTS]


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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', action='store_true', help='Train the exported model with TRAIN_CONFIG dataset settings.')
    args = parser.parse_args()
    model = M6CifarAdapterModel()
    if args.train:
        run_training(model, TRAIN_CONFIG)
    else:
        sample_input = build_sample_input_from_dataset(TRAIN_CONFIG, MODEL_INPUTS)
        output = model(sample_input)
        print(model)
        print('dataset:', TRAIN_CONFIG.get('dataset_name', 'MNIST'))
        if isinstance(output, dict):
            print({key: tuple(value.shape) for key, value in output.items()})
        else:
            print(tuple(output.shape))
