"""FastAPI 后端入口。

本文件只声明课设项目需要的接口结构，具体业务逻辑后续在对应模块中实现。
"""

from fastapi import FastAPI

from .schemas import (
    CodeExportRequest,
    ModelRequest,
    TrainRequest,
)


app = FastAPI(title="Visual Deep Learning Model Builder")


@app.get("/health")
def health_check():
    """检查后端服务是否正常运行。"""
    pass


@app.get("/devices")
def list_devices():
    """返回当前本机可用的计算设备，例如 CPU 和 CUDA GPU。"""
    pass


@app.post("/validate")
def validate_model(request: ModelRequest):
    """校验模型结构，并推导每一层的张量维度变化。"""
    pass


@app.post("/train")
def start_training(request: TrainRequest):
    """根据用户选择的 CPU 或 GPU 启动本地训练任务。"""
    pass


@app.get("/train/{job_id}/status")
def get_training_status(job_id: str):
    """返回指定训练任务的当前状态、日志和进度。"""
    pass


@app.get("/train/{job_id}/result")
def get_training_result(job_id: str):
    """返回训练完成后的最终指标和相关产物信息。"""
    pass


@app.post("/export/pytorch")
def export_pytorch_code(request: CodeExportRequest):
    """根据可视化模型结构生成 PyTorch 源代码。"""
    pass
