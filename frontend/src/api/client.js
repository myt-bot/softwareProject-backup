const API_BASE_URL = "http://127.0.0.1:8000";


export async function fetchHealth() {
  // 调用后端健康检查接口，确认服务是否可访问。
}


export async function fetchDevices() {
  // 向后端请求当前可用的 CPU/GPU 设备。
}


export async function validateModel(modelGraph) {
  // 将可视化模型图发送给后端，用于结构校验和维度推导。
}


export async function startTraining(modelGraph, trainConfig) {
  // 根据选择的数据集、超参数和设备启动本地训练任务。
}


export async function fetchTrainingStatus(jobId) {
  // 查询训练任务的当前状态和进度。
}


export async function fetchTrainingResult(jobId) {
  // 查询已完成训练任务的最终指标和产物信息。
}


export async function exportPytorchCode(modelGraph) {
  // 向后端请求根据模型图生成的 PyTorch 模型代码。
}
