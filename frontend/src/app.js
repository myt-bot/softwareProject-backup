import {
  exportPytorchCode,
  fetchDevices,
  fetchTrainingResult,
  fetchTrainingStatus,
  startTraining,
  validateModel,
} from "./api/client.js";


function initializeApp() {
  // 初始化页面状态，加载可用设备，并绑定界面事件。
}


function initializeLayerPalette() {
  // 渲染支持的层类型，例如 Input、Conv2D、ReLU、Pooling 和 Linear。
}


function initializeCanvas() {
  // 初始化可视化模型画布或图编辑器。
}


function initializePropertyPanel() {
  // 渲染当前选中层的可编辑参数。
}


function initializeTrainingPanel() {
  // 渲染训练设置、设备选择、指标展示和操作按钮。
}


function getCurrentModelGraph() {
  // 将当前画布状态转换为后端需要的模型 JSON。
}


function loadModelGraph(modelGraph) {
  // 将后端或模板提供的模型 JSON 加载到可视化画布中。
}


function handleValidateModel() {
  // 将当前模型图发送到后端，并展示结构校验结果。
}


function handleStartTraining() {
  // 将模型图和训练配置发送到后端，启动本地训练。
}


function pollTrainingStatus(jobId) {
  // 定时查询训练状态，并更新界面中的训练进度。
}


function renderTrainingCurves(metrics) {
  // 根据后端返回的训练指标绘制 loss 和 accuracy 曲线。
}


function handleExportCode() {
  // 向后端请求生成的 PyTorch 代码，并展示给用户。
}


initializeApp();
