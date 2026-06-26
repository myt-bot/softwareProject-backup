"""本地 PyTorch 训练流程。"""

import torch
import torch.nn as nn
import torchvision 
import torch.utils.data

from datetime import datetime
from uuid import uuid4

from .device import resolve_device
from .model_builder import build_model

TRANING_JOBS = {} #后续改为数据库存储

def create_training_job(model_graph, train_config):
    """在训练开始前创建并登记一个训练任务。

    参数：
        model_graph：前端传入的模型图结构，用于后续构建 PyTorch 模型。
        train_config：训练配置，包含数据集、轮数、批大小、学习率和设备选择。
        train_config为字典，包含字段：dataset_name、epochs、batch_size、rate、device、loss_fn、optimizer
    返回：
        后续应返回训练任务编号和初始任务状态。
    """
    def generate_job_id():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid4().hex[:6]
        return f"train_{timestamp}_{short_uuid}"
    
    job_id = generate_job_id()

    TRANING_JOBS[job_id] = {
        "status": "pending", #pending为已创建，等待开始；running为正在训练；completed为训练完成；failed为训练失败；cancelled为已取消
        "model_graph": model_graph,
        "train_config": train_config,
        "current_epoch": 0,
        "total_epochs": train_config.epochs,
        "metrics": [],
        "error": None
    }



def run_training_job(job_id):
    """执行一个已登记训练任务的完整训练流程。

    参数：
        job_id：训练任务编号，用于读取任务配置、更新进度并保存结果。

    返回：
        后续应返回训练结果摘要，或将结果写入任务状态存储中。
    """
    def _get_config_value(config, key, default=None):
        if isinstance(config, dict):
            return config.get(key, default)

        return getattr(config, key, default)

    if job_id not in TRANING_JOBS:
        raise ValueError(f"训练任务不存在: {job_id}")

    job = TRANING_JOBS[job_id]
    train_config = job["train_config"]

    try:
        job["status"] = "running"
        job["error"] = None

        dataset_name = _get_config_value(
            train_config,
            "dataset_name",
            "MNIST"
        )
        batch_size = _get_config_value(train_config, "batch_size", 64)
        epochs = _get_config_value(train_config, "epochs", 1)
        learning_rate = _get_config_value(
            train_config,
            "rate",
            0.001
        )
        requested_device = _get_config_value(train_config, "device", "cpu")
        loss_fn_config = _get_config_value(train_config, "loss_fn", None)
        optimizer_config = _get_config_value(train_config, "optimizer", None)

        device = resolve_device(requested_device)
        model = build_model(job["model_graph"]).to(device)
        loss_fn = _build_loss_fn(loss_fn_config)
        optimizer = _build_optimizer(
            optimizer_config=optimizer_config,
            model=model,
            learning_rate=learning_rate,
        )

        train_loader, test_loader = prepare_dataset(
            dataset_name=dataset_name,
            batch_size=batch_size,
        )

        metrics = []
        for epoch in range(1, epochs + 1):
            if job["status"] == "cancelled":
                break

            train_metrics = train_one_epoch(
                model=model,
                train_loader=train_loader,
                optimizer=optimizer,
                loss_fn=loss_fn,
                device=device,
            )
            eval_metrics = evaluate_model(
                model=model,
                test_loader=test_loader,
                loss_fn=loss_fn,
                device=device,
            )

            epoch_metrics = {
                "epoch": epoch,
                "train": train_metrics,
                "eval": eval_metrics,
            }
            metrics.append(epoch_metrics)

            job["current_epoch"] = epoch
            job["metrics"] = metrics

        if job["status"] == "cancelled":
            return {
                "job_id": job_id,
                "status": "cancelled",
                "metrics": metrics,
            }

        artifacts = save_training_artifacts(job_id, model, metrics)
        job["status"] = "completed"
        return {
            "job_id": job_id,
            "status": "completed",
            "device": str(device),
            "metrics": metrics,
            "artifacts": artifacts,
        }

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        raise


def _build_loss_fn(loss_fn_config):
    """根据训练配置创建损失函数。"""
    if loss_fn_config is None:
        return nn.CrossEntropyLoss()

    if isinstance(loss_fn_config, nn.Module):
        return loss_fn_config

    if isinstance(loss_fn_config, str):
        loss_fn_name = loss_fn_config.lower()
        if loss_fn_name in ("cross_entropy", "crossentropyloss", "ce"):
            return nn.CrossEntropyLoss()
        if loss_fn_name in ("mse", "mseloss"):
            return nn.MSELoss()

    raise ValueError(f"暂不支持的损失函数配置: {loss_fn_config}")


def _build_optimizer(optimizer_config, model, learning_rate):
    """根据训练配置创建优化器。"""
    if isinstance(optimizer_config, torch.optim.Optimizer):
        return optimizer_config

    if optimizer_config is None:
        optimizer_config = "sgd"

    if isinstance(optimizer_config, str):
        optimizer_name = optimizer_config.lower()
        if optimizer_name == "sgd":
            return torch.optim.SGD(
                model.parameters(),
                lr=learning_rate,
                momentum=0.9,
            )
        if optimizer_name == "adam":
            return torch.optim.Adam(
                model.parameters(),
                lr=learning_rate,
            )

    raise ValueError(f"暂不支持的优化器配置: {optimizer_config}")


def prepare_dataset(dataset_name, batch_size):
    """加载并预处理用户选择的内置数据集。

    参数：
        dataset_name：数据集名称，例如 "MNIST"，用于决定加载哪个内置数据集。
        batch_size：每个训练批次的数据量，用于构造 DataLoader。

    返回：
        后续应返回训练集 DataLoader 和测试集 DataLoader。
    """
    if dataset_name == 'MNIST':
        train_data = torchvision.datasets.MNIST(
            root='./MNIST',
            train=True,
            transform=torchvision.transforms.ToTensor(),
            download=True
        )

        test_data = torchvision.datasets.MNIST(
            root='./MNIST',
            train=False,
            transform=torchvision.transforms.ToTensor()
        )

    train_DataLoader = torch.utils.data.DataLoader(
            dataset=train_data,
            batch_size=batch_size,
            shuffle=True
    )

    test_DataLoader = torch.utils.data.DataLoader(dataset=test_data)

    return train_DataLoader, test_DataLoader


def train_one_epoch(model, train_loader, optimizer, loss_fn, device):
    """训练一个 epoch，并返回该轮训练指标。

    参数：
        model：需要训练的 PyTorch 模型。
        train_loader：训练数据加载器，按 batch 提供输入和标签。
        optimizer：优化器，用于根据梯度更新模型参数。
        loss_fn：损失函数，用于计算预测值与真实标签之间的误差。
        device：实际训练设备，例如 CPU 或 CUDA GPU。

    返回：
        后续应返回该 epoch 的平均 loss、accuracy 和样本数量等指标。
    """
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

        predicted = outputs.argmax(dim=1)
        correct += (predicted == labels).sum().item()
        total += batch_size

    if total == 0:
        return {
            "loss": 0.0,
            "accuracy": 0.0,
            "correct": 0,
            "total": 0,
        }

    return {
        "loss": total_loss / total,
        "accuracy": correct / total,
        "correct": correct,
        "total": total,
    }


def evaluate_model(model, test_loader, loss_fn, device):
    """评估模型，并返回验证损失和准确率。

    参数：
        model：需要评估的 PyTorch 模型。
        test_loader：测试或验证数据加载器。
        loss_fn：损失函数，用于计算验证损失。
        device：评估时使用的计算设备，例如 CPU 或 CUDA GPU。

    返回：
        后续应返回验证 loss、accuracy 和评估样本数量等指标。
    """
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

            predicted = outputs.argmax(dim=1)
            correct += (predicted == labels).sum().item()
            total += batch_size

    if total == 0:
        return {
            "loss": 0.0,
            "accuracy": 0.0,
            "correct": 0,
            "total": 0,
        }

    return {
        "loss": total_loss / total,
        "accuracy": correct / total,
        "correct": correct,
        "total": total,
    }


def save_training_artifacts(job_id, model, metrics):
    """保存训练产生的模型权重、指标和日志。

    参数：
        job_id：训练任务编号，用于生成保存目录或文件名。
        model：训练完成后的 PyTorch 模型对象。
        metrics：训练过程产生的指标数据，例如每轮 loss 和 accuracy。

    返回：
        后续应返回保存文件路径或产物信息字典。
    """
    pass


def get_job_status(job_id):
    """返回训练任务的当前状态和进度。

    参数：
        job_id：训练任务编号，用于查询对应任务的运行状态。

    返回：
        后续应返回任务状态、当前 epoch、进度和日志信息。
    """
    pass


def get_job_result(job_id):
    """返回已完成训练任务的最终指标和保存文件路径。

    参数：
        job_id：训练任务编号，用于查询对应任务的最终结果。

    返回：
        后续应返回最终 loss、accuracy、模型保存路径和训练摘要。
    """
    pass


def stop_training_job(job_id):
    """请求取消一个正在运行的训练任务。

    参数：
        job_id：训练任务编号，用于定位需要取消的训练任务。

    返回：
        后续应返回取消请求是否成功以及任务的新状态。
    """
    pass
