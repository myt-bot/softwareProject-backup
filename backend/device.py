"""CPU/GPU 设备检测与选择工具。"""


def get_available_devices():
    """检测当前可用的计算设备，并返回给前端用于展示。"""
    pass


def is_cuda_available():
    """检查当前本机的 PyTorch 是否可以使用 CUDA GPU。"""
    pass


def resolve_device(requested_device):
    """根据用户选择决定训练实际使用的设备。"""
    pass


def get_device_summary():
    """返回适合在设置面板中展示的 CPU/GPU 信息。"""
    pass
