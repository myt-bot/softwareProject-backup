// 与后端交互的业务动作（校验 / 保存 / 导出 / 训练）。
// 所有操作在发起时捕获所属画布的引用，异步结果写回原画布——
// 各画布可以并行进行结构检查、保存模型、导出代码、训练与查看训练任务。

import {
  cancelTraining,
  createProject,
  exportPytorchCode,
  fetchDevices,
  fetchProjectTemplate,
  fetchProjectTemplates,
  fetchTrainingResult,
  fetchTrainingStatus,
  isBackendNotImplemented,
  isBackendUnavailable,
  startTraining,
  validateModel,
} from "./api/client";
import { auth, isLoggedIn } from "./auth";
import { applyTemplateGraph } from "./canvas";
import { openTrainingMonitor } from "./monitor";
import {
  activeCanvas,
  getCurrentModelGraph,
  getTrainConfig,
  getTrainingLayers,
  getTrainingStatusLabel,
  setTrainingJob,
  showToast,
  store,
  templateLibrary,
  ui,
  updateShapeHints,
} from "./store";
import type { WorkCanvas } from "./store";
import type { ValidationResult } from "./types";

// 每个画布独立的训练轮询定时器（画布 id → timer）
const trainingPollTimers = new Map<number, number>();


export function showBackendError(error: unknown, fallbackMessage: string) {
  if (isBackendNotImplemented(error)) {
    showToast("warning", fallbackMessage);
    return;
  }
  showToast("error", (error as Error)?.message || fallbackMessage);
}


function canvasExists(canvas: WorkCanvas) {
  return store.canvases.some(item => item.id === canvas.id);
}


// —————————————————————————————————————————————
// 初始化加载
// —————————————————————————————————————————————

export async function loadDevices() {
  try {
    const devices = await fetchDevices();
    // 同步设备可用性到顶栏设备选择器
    store.cudaAvailable = Boolean(devices?.cuda_available);
    if (devices?.default_device) {
      store.device = devices.default_device;
      showToast("success", `后端设备已连接: ${devices.default_device}`);
    }
    if (!store.cudaAvailable && store.device !== "cpu") {
      store.device = "cpu";
    }
  } catch (error) {
    showBackendError(error, "设备接口暂未实现。");
  }
}


export async function loadProjectTemplates() {
  try {
    const result = await fetchProjectTemplates();
    if (result?.data?.length) {
      templateLibrary.items = result.data;
    }
    if (result?.count) {
      showToast("info", `已连接模板库: ${result.count} 个模板`);
    }
  } catch (error) {
    showBackendError(error, "模板列表接口暂未实现。");
  }
}


export async function loadTemplateToCanvas(templateKey: string, templateName?: string) {
  try {
    const result = await fetchProjectTemplate(templateKey);
    const graph = result?.model;
    if (!graph) {
      showToast("error", "模板数据为空，无法加载。");
      return;
    }

    applyTemplateGraph(graph);
    ui.templateGalleryOpen = false;
    showToast("success", `已加载模板: ${templateName || templateKey}`);
  } catch (error) {
    showBackendError(error, "模板加载接口暂未实现。");
  }
}


// —————————————————————————————————————————————
// 结构校验（按画布并行）
// —————————————————————————————————————————————

export async function handleValidateModel() {
  const canvas = activeCanvas();
  if (canvas.validating) return;
  canvas.validating = true;

  try {
    const result = await validateModel(getCurrentModelGraph(canvas));
    applyValidationResult(canvas, result);
  } catch (error) {
    // 校验结果只通过 toast 提示
    if (isBackendUnavailable(error)) {
      showToast("error", "后端服务未启动，无法进行结构校验。");
    } else {
      showBackendError(error, "结构校验接口暂未实现。");
    }
    canvas.validationStatus = "unvalidated";
  } finally {
    canvas.validating = false;
  }
}


function applyValidationResult(canvas: WorkCanvas, result: ValidationResult) {
  const valid = result?.valid === true || result?.status === "ok";
  if (valid) {
    canvas.validationStatus = "passing";
    canvas.nodeBadge = "passed";
    updateShapeHints(canvas);
    showToast("success", `${canvas.name} 结构校验通过。`);
    return;
  }

  canvas.validationStatus = "failed";
  canvas.nodeBadge = "pending";
  showToast("error", `${canvas.name} ${result?.message || "结构校验失败"}`);
}


// —————————————————————————————————————————————
// 保存 / 导出
// —————————————————————————————————————————————

export async function handleSaveProject() {
  const canvas = activeCanvas();

  // 保存接口需要登录（正常情况下主界面只在登录后可见，此处为兜底）
  if (!isLoggedIn() || !auth.user?.id) {
    showToast("warning", "登录状态已失效，请重新登录。");
    return;
  }

  const name = window.prompt("请输入项目名称：", canvas.name || "Untitled Model");
  if (!name) {
    showToast("warning", "已取消保存。");
    return;
  }

  try {
    const result = await createProject({
      user_id: auth.user.id,
      name,
      model_graph: getCurrentModelGraph(canvas),
      description: "Created from visual model editor",
    });
    showToast("success", `项目已保存: ${result?.data?.name || name}`);
  } catch (error) {
    showBackendError(error, "保存项目失败。");
  }
}


export async function handleExportCode() {
  const canvas = activeCanvas();
  ui.exportModalOpen = true;
  canvas.exportCodeDisplay = "正在请求后端导出接口...";

  try {
    const result = await exportPytorchCode(getCurrentModelGraph(canvas));
    const code = typeof result === "string" ? result : result?.code || result?.source_code;
    canvas.lastExportCode = typeof code === "string" ? code : JSON.stringify(result, null, 2);
    canvas.exportCodeDisplay = canvas.lastExportCode;
    showToast("success", `${canvas.name} 的 PyTorch 代码已从后端导出。`);
  } catch (error) {
    showBackendError(error, "代码导出接口暂未实现。");
    canvas.lastExportCode = "";
    canvas.exportCodeDisplay = "代码导出接口暂未实现。";
  }
}


export function closeExportModal() {
  ui.exportModalOpen = false;
}


export async function copyExportCode() {
  const canvas = activeCanvas();
  if (!canvas.lastExportCode) {
    showToast("warning", "暂无可复制代码。");
    return;
  }

  try {
    await navigator.clipboard.writeText(canvas.lastExportCode);
    showToast("success", "代码已复制。");
  } catch {
    showToast("warning", "当前浏览器不支持自动复制。");
  }
}


export function downloadExportCode() {
  const canvas = activeCanvas();
  if (!canvas.lastExportCode) {
    showToast("warning", "暂无可下载代码。");
    return;
  }

  const blob = new Blob([canvas.lastExportCode], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "MNIST_CNN.py";
  link.click();
  URL.revokeObjectURL(url);
}


// —————————————————————————————————————————————
// 训练任务（按画布并行）
// —————————————————————————————————————————————

async function submitTrainingJob(canvas: WorkCanvas) {
  const trainConfig = getTrainConfig(canvas);
  const result = await startTraining(getCurrentModelGraph(canvas), trainConfig);
  return {
    result,
    trainConfig,
    jobId: result?.job_id,
  };
}


export async function handleStartTraining() {
  const canvas = activeCanvas();
  if (canvas.trainStarting) return;
  canvas.trainStarting = true;

  try {
    const { result, trainConfig, jobId } = await submitTrainingJob(canvas);
    setTrainingJob(canvas, {
      job_id: jobId,
      status: result?.job_status || result?.status || "pending",
      current_epoch: result?.current_epoch ?? 0,
      total_epochs: result?.total_epochs ?? trainConfig.epochs,
      progress: 0,
      trainConfig,
    });
    showToast("success", `训练任务已创建: ${canvas.jobId || "未知任务"}`);
    if (jobId) {
      openTrainingMonitorForCanvas(canvas);
      pollTrainingStatus(canvas, jobId);
    }
  } catch (error) {
    showBackendError(error, "训练接口暂未实现。");
  } finally {
    canvas.trainStarting = false;
  }
}


function stopTrainingPolling(canvas: WorkCanvas) {
  const timer = trainingPollTimers.get(canvas.id);
  if (timer) {
    clearTimeout(timer);
    trainingPollTimers.delete(canvas.id);
  }
}


function pollTrainingStatus(canvas: WorkCanvas, jobId: string) {
  stopTrainingPolling(canvas);
  void poll();

  async function poll() {
    // 画布被关闭后停止跟踪其训练任务
    if (!canvasExists(canvas)) return;

    try {
      const status = await fetchTrainingStatus(jobId);
      setTrainingJob(canvas, status);
      if (status?.status === "completed") {
        const result = await fetchTrainingResult(jobId);
        setTrainingJob(canvas, {
          ...result,
          progress: 1,
        });
        showToast("success", `${canvas.name} 训练完成，accuracy=${result?.accuracy ?? "未知"}`);
        return;
      }
      if (status?.status === "failed" || status?.status === "cancelled") {
        showToast(
          status.status === "failed" ? "error" : "warning",
          `${canvas.name} 训练${getTrainingStatusLabel(status.status)}。`
        );
        return;
      }
      trainingPollTimers.set(canvas.id, window.setTimeout(() => void poll(), 1000));
    } catch (error) {
      showBackendError(error, "训练状态接口暂未实现。");
    }
  }
}


// 打开指定画布的训练监控页（重新训练也会回写到该画布）
function openTrainingMonitorForCanvas(canvas: WorkCanvas) {
  if (!canvas.trainingJob?.job_id) {
    showToast("warning", "当前画布没有可查看的训练任务。");
    return;
  }

  openTrainingMonitor({
    live: true,
    jobId: canvas.trainingJob.job_id,
    fetchStatus: fetchTrainingStatus,
    fetchResult: fetchTrainingResult,
    cancelJob: cancelTraining,
    hyperparams: canvas.trainingJob.trainConfig || getTrainConfig(canvas),
    layers: getTrainingLayers(canvas),
    onRerun: async () => {
      const { jobId, trainConfig, result } = await submitTrainingJob(canvas);
      setTrainingJob(canvas, {
        job_id: jobId,
        status: result?.job_status || result?.status || "pending",
        current_epoch: result?.current_epoch ?? 0,
        total_epochs: result?.total_epochs ?? trainConfig.epochs,
        progress: 0,
        trainConfig,
      });
      if (jobId) {
        pollTrainingStatus(canvas, jobId);
      }
      return { jobId };
    },
  });
}


export function openCurrentTrainingMonitor() {
  openTrainingMonitorForCanvas(activeCanvas());
}
