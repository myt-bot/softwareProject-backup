"""CPU/GPU 设备检测与选择工具。"""

import torch


def get_available_devices():
    """检测当前可用的计算设备，并返回给前端用于展示。"""
    devices = ["cpu"]

    if is_cuda_available():
        devices.append("cuda")

    return devices


def is_cuda_available():
    """检查当前本机的 PyTorch 是否可以使用 CUDA GPU。"""
    return torch.cuda.is_available()


def resolve_device(requested_device):
    """根据用户选择决定训练实际使用的设备。"""
    normalized_device = (requested_device or "cpu").lower()

    if normalized_device in ("cuda", "gpu") and is_cuda_available():
        return torch.device("cuda")

    if normalized_device == "auto":
        return torch.device("cuda" if is_cuda_available() else "cpu")

    return torch.device("cpu")


def get_device_summary():
    """返回适合在设置面板中展示的 CPU/GPU 信息。"""
    cuda_available = is_cuda_available()
    cuda_device_count = torch.cuda.device_count() if cuda_available else 0
    cuda_devices = []

    for index in range(cuda_device_count):
        cuda_devices.append(
            {
                "index": index,
                "name": torch.cuda.get_device_name(index),
            }
        )

    return {
        "available_devices": get_available_devices(),
        "default_device": "cuda" if cuda_available else "cpu",
        "cuda_available": cuda_available,
        "cuda_device_count": cuda_device_count,
        "cuda_devices": cuda_devices,
    }
