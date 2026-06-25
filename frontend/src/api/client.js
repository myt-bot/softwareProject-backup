const API_BASE_URL = "http://127.0.0.1:8000";


export async function fetchHealth() {
  // 参数：无。
  // 返回：后续应返回后端健康检查结果，用于判断服务是否可访问。
}


export async function fetchDevices() {
  // 参数：无。
  // 返回：后续应返回可用设备列表、默认设备和 GPU 摘要信息。
}


export async function validateModel(modelGraph) {
  // 参数：
  //   modelGraph：当前画布模型图，包含 layers 和 connections。
  // 返回：后续应返回结构校验结果、错误信息和维度推导信息。
}


export async function startTraining(modelGraph, trainConfig) {
  // 参数：
  //   modelGraph：当前画布模型图，用于后端构建训练模型。
  //   trainConfig：训练配置，包含 dataset、epochs、batch_size、learning_rate 和 device。
  // 返回：后续应返回训练任务编号和初始状态。
}


export async function fetchTrainingStatus(jobId) {
  // 参数：
  //   jobId：训练任务编号，用于查询对应任务的实时状态。
  // 返回：后续应返回任务状态、训练进度、日志和当前指标。
}


export async function fetchTrainingResult(jobId) {
  // 参数：
  //   jobId：训练任务编号，用于查询对应任务的最终结果。
  // 返回：后续应返回最终 loss、accuracy、模型文件路径和训练摘要。
}


export async function exportPytorchCode(modelGraph) {
  // 参数：
  //   modelGraph：当前画布模型图，用于生成 PyTorch 模型代码。
  // 返回：后续应返回生成的 PyTorch 源代码字符串。
}
