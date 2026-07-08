"""本地 PyTorch 训练流程。"""

import json
import os

import torch
import torch.nn as nn
import torchvision
import torch.utils.data

from datetime import datetime
from uuid import uuid4

from .device import resolve_device
from .model_builder import build_model

TRANING_JOBS = {} #后续改为数据库存储

# 训练产物（模型权重、指标）默认保存目录。
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ARTIFACTS_ROOT = os.path.join(PROJECT_ROOT, "training_artifacts")

# 训练任务状态对应的中文提示，用于前端状态可见性（NFR4）。
STATUS_MESSAGES = {
    "pending": "训练任务已创建，等待开始",
    "running": "正在训练",
    "cancelling": "正在停止，等待当前轮结束",
    "completed": "训练完成",
    "failed": "训练失败",
    "cancelled": "训练已取消",
}

DATASET_SPECS = {
    "MNIST": {
        "class": torchvision.datasets.MNIST,
        "root": "./MNIST",
        "aliases": ("mnist",),
    },
    "FashionMNIST": {
        "class": torchvision.datasets.FashionMNIST,
        "root": "./FashionMNIST",
        "aliases": ("fashionmnist", "fashion_mnist", "fashion-mnist"),
    },
    "KMNIST": {
        "class": torchvision.datasets.KMNIST,
        "root": "./KMNIST",
        "aliases": ("kmnist",),
    },
    "CIFAR10": {
        "class": torchvision.datasets.CIFAR10,
        "root": "./CIFAR10",
        "aliases": ("cifar10", "cifar-10", "cifar_10"),
    },
    "CIFAR100": {
        "class": torchvision.datasets.CIFAR100,
        "root": "./CIFAR100",
        "aliases": ("cifar100", "cifar-100", "cifar_100"),
    },
}


def create_training_job(model_graph, train_config):
    """在训练开始前创建并登记一个训练任务。

    参数：
        model_graph：前端传入的模型图结构，用于后续构建 PyTorch 模型。
        train_config：训练配置，包含数据集、轮数、批大小、学习率和设备选择。
        train_config 包含字段：dataset_name、epochs、batch_size、rate、device、loss_fn、optimizer。
    返回：
        dict：训练任务编号和初始任务状态。
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
        "total_epochs": train_config["epochs"],
        "metrics": [],
        "error": None,
        "cancel_requested": False
    }

    return {
        "job_id": job_id,
        "status": "pending",
        "current_epoch": 0,
        "total_epochs": train_config["epochs"],
    }



def run_training_job(job_id):
    """执行一个已登记训练任务的完整训练流程。

    参数：
        job_id：训练任务编号，用于读取任务配置、更新进度并保存结果。

    返回：
        后续应返回训练结果摘要，或将结果写入任务状态存储中。
    """
    if job_id not in TRANING_JOBS:
        raise ValueError(f"训练任务不存在: {job_id}")

    job = TRANING_JOBS[job_id]
    train_config = job["train_config"]

    # 连通性测试用的演示模式：设置环境变量 TRAINER_DEMO=1 时，跳过真实
    # PyTorch 训练，改为逐轮生成合成指标（每轮之间 sleep 让出 GIL），
    # 使前端轮询 /status 能观察到曲线逐轮增长。不设置时走真实训练流程。
    if os.environ.get("TRAINER_DEMO") == "1":
        return _run_demo_job(job_id)

    try:
        job["status"] = "running"
        job["error"] = None

        dataset_name = train_config.get("dataset_name", "MNIST")
        batch_size = train_config.get("batch_size", 64)
        epochs = train_config.get("epochs", 1)
        rate = train_config.get("rate", 0.001)
        requested_device = train_config.get("device", "cpu")
        loss_fn_config = train_config.get("loss_fn", None)
        optimizer_config = train_config.get("optimizer", None)

        device = resolve_device(requested_device)
        job["device"] = str(device)
        model = build_model(job["model_graph"]).to(device)
        loss_fn = _build_loss_fn(loss_fn_config)
        optimizer = _build_optimizer(
            optimizer_config=optimizer_config,
            model=model,
            rate=rate,
        )

        train_loader, test_loader = prepare_dataset(
            dataset_name=dataset_name,
            batch_size=batch_size,
            data_dir=train_config.get("data_dir") or None,
        )

        metrics = []
        job["total_steps"] = len(train_loader)
        for epoch in range(1, epochs + 1):
            if job.get("cancel_requested"):
                break

            job["current_step"] = 0
            train_metrics = train_one_epoch(
                model=model,
                train_loader=train_loader,
                optimizer=optimizer,
                loss_fn=loss_fn,
                device=device,
                progress_callback=lambda step: job.__setitem__("current_step", step),
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
            # 该轮已计入 current_epoch，清零 step 避免整体进度短暂超前
            job["current_step"] = 0
            job["metrics"] = metrics

            if job.get("cancel_requested"):
                break

        if job.get("cancel_requested"):
            job["status"] = "cancelled"
            cancelled_result = {
                "job_id": job_id,
                "status": "cancelled",
                "metrics": metrics,
            }
            job["result"] = cancelled_result
            return cancelled_result

        artifacts = save_training_artifacts(
            job_id, model, metrics,
            artifacts_dir=train_config.get("artifacts_dir") or None,
        )
        job["status"] = "completed"
        completed_result = {
            "job_id": job_id,
            "status": "completed",
            "device": str(device),
            "metrics": metrics,
            "artifacts": artifacts,
        }
        job["result"] = completed_result
        return completed_result

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["result"] = {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
            "metrics": job.get("metrics", []),
        }
        raise


def _run_demo_job(job_id):
    """连通性测试用的演示训练（不依赖真实数据集和 PyTorch 训练）。

    逐轮生成趋势合理的合成指标（loss 下降、accuracy 上升，val 略低于
    train），每轮之间 sleep 一秒并更新 job 状态，使前端轮询 /status 能
    观察到 current_epoch、metrics 逐轮增长，曲线一条条长出来。

    产出的数据结构与真实训练完全一致，因此 /status、/result 接口和前端
    无需任何改动即可复用。
    """
    import time

    job = TRANING_JOBS[job_id]
    train_config = job["train_config"]
    epochs = train_config.get("epochs", 1)

    job["status"] = "running"
    job["error"] = None
    job["device"] = "cpu (demo)"

    metrics = []
    for epoch in range(1, epochs + 1):
        if job.get("cancel_requested"):
            break

        # 模拟每轮训练耗时，给前端留出观察逐轮进度的时间窗口。
        time.sleep(1.0)

        progress = epoch / epochs if epochs else 1.0
        train_loss = round(1.2 * (1.0 - 0.7 * progress), 4)
        train_acc = round(0.35 + 0.6 * progress, 4)
        val_loss = round(train_loss + 0.08, 4)
        val_acc = round(train_acc - 0.03, 4)

        metrics.append({
            "epoch": epoch,
            "train": {"loss": train_loss, "accuracy": train_acc},
            "eval": {"loss": val_loss, "accuracy": val_acc},
        })

        job["current_epoch"] = epoch
        job["metrics"] = metrics

        if job.get("cancel_requested"):
            break

    if job.get("cancel_requested"):
        job["status"] = "cancelled"
        cancelled_result = {
            "job_id": job_id,
            "status": "cancelled",
            "metrics": metrics,
        }
        job["result"] = cancelled_result
        return cancelled_result

    job["status"] = "completed"
    completed_result = {
        "job_id": job_id,
        "status": "completed",
        "device": "cpu (demo)",
        "metrics": metrics,
        "artifacts": None,
    }
    job["result"] = completed_result
    return completed_result


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


def _build_optimizer(optimizer_config, model, rate):
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
                lr=rate,
                momentum=0.9,
            )
        if optimizer_name == "adam":
            return torch.optim.Adam(
                model.parameters(),
                lr=rate,
            )

    raise ValueError(f"暂不支持的优化器配置: {optimizer_config}")


def prepare_dataset(dataset_name, batch_size, data_dir=None):
    """加载并预处理用户选择的内置数据集。

    参数：
        dataset_name：数据集名称，例如 "MNIST"、"FashionMNIST" 或 "CIFAR10"。
        batch_size：每个训练批次的数据量，用于构造 DataLoader。
        data_dir：数据集下载/缓存目录；为空时使用各数据集的默认位置。

    返回：
        训练集 DataLoader 和测试集 DataLoader。
    """
    dataset_key = _resolve_dataset_key(dataset_name)
    dataset_spec = DATASET_SPECS[dataset_key]
    dataset_class = dataset_spec["class"]
    transform = _build_dataset_transform(dataset_key)

    if data_dir:
        dataset_root = os.path.join(os.path.expanduser(data_dir), dataset_key)
    else:
        dataset_root = dataset_spec["root"]

    train_data = dataset_class(
        root=dataset_root,
        train=True,
        transform=transform,
        download=True
    )

    test_data = dataset_class(
        root=dataset_root,
        train=False,
        transform=transform
    )

    train_dataloader = torch.utils.data.DataLoader(
        dataset=train_data,
        batch_size=batch_size,
        shuffle=True
    )

    test_dataloader = torch.utils.data.DataLoader(
        dataset=test_data,
        batch_size=batch_size
    )

    return train_dataloader, test_dataloader


def _resolve_dataset_key(dataset_name):
    """将用户传入的数据集名称或别名解析为 DATASET_SPECS 中的标准 key。"""
    if not isinstance(dataset_name, str) or not dataset_name.strip():
        raise ValueError("dataset_name 必须是非空字符串")

    normalized_name = dataset_name.strip().lower()
    for dataset_key, dataset_spec in DATASET_SPECS.items():
        aliases = (dataset_key.lower(), *dataset_spec.get("aliases", ()))
        if normalized_name in aliases:
            return dataset_key

    supported = ", ".join(DATASET_SPECS.keys())
    raise ValueError(f"暂不支持的数据集: {dataset_name}，当前支持: {supported}")


def _build_dataset_transform(dataset_key):
    """返回指定数据集的默认输入转换。"""
    if dataset_key in ("CIFAR10", "CIFAR100"):
        return torchvision.transforms.Compose([
            torchvision.transforms.ToTensor(),
            torchvision.transforms.Normalize(
                mean=(0.4914, 0.4822, 0.4465),
                std=(0.2470, 0.2435, 0.2616),
            ),
        ])

    return torchvision.transforms.ToTensor()


def train_one_epoch(model, train_loader, optimizer, loss_fn, device, progress_callback=None):
    """训练一个 epoch，并返回该轮训练指标。

    参数：
        model：需要训练的 PyTorch 模型。
        train_loader：训练数据加载器，按 batch 提供输入和标签。
        optimizer：优化器，用于根据梯度更新模型参数。
        loss_fn：损失函数，用于计算预测值与真实标签之间的误差。
        device：实际训练设备，例如 CPU 或 CUDA GPU。
        progress_callback：可选回调，每完成一个 batch 以 step 序号（从 1 开始）
            调用一次，用于向状态接口汇报轮次内进度。

    返回：
        后续应返回该 epoch 的平均 loss、accuracy 和样本数量等指标。
    """
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for step, (inputs, labels) in enumerate(train_loader, start=1):
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

        if progress_callback is not None:
            progress_callback(step)

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


def save_training_artifacts(job_id, model, metrics, artifacts_dir=None):
    """保存训练产生的模型权重、指标和日志。

    参数：
        job_id：训练任务编号，用于生成保存目录或文件名。
        model：训练完成后的 PyTorch 模型对象。
        metrics：训练过程产生的指标数据，例如每轮 loss 和 accuracy。
        artifacts_dir：产物保存根目录；为空时使用默认的 training_artifacts。

    返回：
        dict：保存产物信息，包含模型权重文件路径和指标文件路径。
    """
    artifacts_root = os.path.expanduser(artifacts_dir) if artifacts_dir else ARTIFACTS_ROOT
    artifact_dir = os.path.join(artifacts_root, job_id)
    os.makedirs(artifact_dir, exist_ok=True)

    model_path = os.path.join(artifact_dir, "model.pt")
    metrics_path = os.path.join(artifact_dir, "metrics.json")

    torch.save(model.state_dict(), model_path)
    with open(metrics_path, "w", encoding="utf-8") as metrics_file:
        json.dump(metrics, metrics_file, ensure_ascii=False, indent=2)

    return {
        "model_path": model_path,
        "metrics_path": metrics_path,
    }


def get_job_status(job_id):
    """返回训练任务的当前状态和进度。

    参数：
        job_id：训练任务编号，用于查询对应任务的运行状态。

    返回：
        dict：任务状态、当前 epoch、总轮数、进度百分比和已产生的指标。

    异常：
        当 job_id 不存在时抛出 ValueError。
    """
    if job_id not in TRANING_JOBS:
        raise ValueError(f"训练任务不存在: {job_id}")

    job = TRANING_JOBS[job_id]
    total_epochs = job.get("total_epochs") or 0
    current_epoch = job.get("current_epoch", 0)
    total_steps = job.get("total_steps") or 0
    current_step = job.get("current_step", 0)

    if total_epochs > 0:
        # current_epoch 为已完成的轮数，再叠加进行中轮次的 step 进度
        step_fraction = (current_step / total_steps) if total_steps > 0 else 0.0
        progress = round(min(1.0, (current_epoch + step_fraction) / total_epochs), 4)
    else:
        progress = 0.0

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "current_epoch": current_epoch,
        "total_epochs": total_epochs,
        "current_step": current_step,
        "total_steps": total_steps,
        "progress": progress,
        "metrics": job.get("metrics", []),
        "error": job.get("error"),
    }


def get_job_result(job_id):
    """返回已完成训练任务的最终指标和保存文件路径。

    参数：
        job_id：训练任务编号，用于查询对应任务的最终结果。

    返回：
        dict：任务状态、最终 loss、accuracy、逐轮指标、设备和模型保存路径。
        当任务尚未完成时，loss/accuracy 为 None。

    异常：
        当 job_id 不存在时抛出 ValueError。
    """
    if job_id not in TRANING_JOBS:
        raise ValueError(f"训练任务不存在: {job_id}")

    job = TRANING_JOBS[job_id]
    metrics = job.get("metrics", [])

    final_loss = None
    final_accuracy = None
    if metrics:
        last_epoch = metrics[-1]
        eval_metrics = last_epoch.get("eval", {})
        final_loss = eval_metrics.get("loss")
        final_accuracy = eval_metrics.get("accuracy")

    result = job.get("result", {})

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "loss": final_loss,
        "accuracy": final_accuracy,
        "metrics": metrics,
        "device": job.get("device"),
        "artifacts": result.get("artifacts"),
        "error": job.get("error"),
    }


def stop_training_job(job_id):
    """请求取消一个正在运行的训练任务。

    参数：
        job_id：训练任务编号，用于定位需要取消的训练任务。

    返回：
        dict：取消请求是否被接受以及任务的新状态。

    异常：
        当 job_id 不存在时抛出 ValueError。
    """
    if job_id not in TRANING_JOBS:
        raise ValueError(f"训练任务不存在: {job_id}")

    job = TRANING_JOBS[job_id]
    current_status = job.get("status")

    if current_status in ("completed", "failed", "cancelled"):
        return {
            "job_id": job_id,
            "cancelled": False,
            "status": current_status,
        }

    job["cancel_requested"] = True
    job["status"] = "cancelling"
    return {
        "job_id": job_id,
        "cancelled": True,
        "status": "cancelling",
    }
