"""CPU/GPU 设备检测与选择工具。"""

import torch


def get_available_devices():
    """检测当前可用的计算设备，并返回给前端用于展示。

    参数：
        无。

    返回：
        list[str]：可用设备标识列表，固定包含 "cpu"；如果 CUDA 可用则包含 "cuda"。
    """
    devices = ["cpu"]

    if is_cuda_available():
        devices.append("cuda")

    return devices


def is_cuda_available():
    """检查当前本机的 PyTorch 是否可以使用 CUDA GPU。

    参数：
        无。

    返回：
        bool：如果 PyTorch 能检测到可用 CUDA GPU，则返回 True，否则返回 False。
    """
    return torch.cuda.is_available()


def resolve_device(requested_device):
    """根据用户选择决定训练实际使用的设备。

    参数：
        requested_device：用户或前端传入的设备名称，可为 "cpu"、"cuda"、"gpu" 或 "auto"。
            "cpu" 表示强制使用 CPU；
            "cuda" 或 "gpu" 表示希望使用 CUDA GPU；
            "auto" 表示后端自动优先选择 GPU，否则回退到 CPU。

    返回：
        torch.device：训练时实际使用的 PyTorch 设备对象。
    """
    normalized_device = (requested_device or "cpu").lower()

    if normalized_device in ("cuda", "gpu") and is_cuda_available():
        return torch.device("cuda")

    if normalized_device == "auto":
        return torch.device("cuda" if is_cuda_available() else "cpu")

    return torch.device("cpu")


def get_device_summary():
    """返回适合在设置面板中展示的 CPU/GPU 信息。

    参数：
        无。

    返回：
        dict：设备摘要信息，包括可用设备列表、默认设备、CUDA 是否可用、
        CUDA 设备数量、每个 GPU 的索引和名称，以及用于排查「有 GPU 却检测
        不到」的诊断信息（PyTorch 版本、是否为 CUDA 构建、原因说明）。
    """
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
