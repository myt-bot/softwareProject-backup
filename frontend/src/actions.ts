// 与后端交互的业务动作（校验 / 保存 / 导出 / 训练）。

import { ref } from "vue";
import {
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
import { applyTemplateGraph } from "./canvas";
import { openTrainingMonitor } from "./monitor";
import {
  getCurrentModelGraph,
  getTrainConfig,
  getTrainingLayers,
  getTrainingStatusLabel,
  setTrainingJob,
  showToast,
  store,
  ui,
  updateShapeHints,
} from "./store";
import type { ValidationResult } from "./types";

// 按钮加载态
export const validating = ref(false);
export const trainStarting = ref(false);

let trainingPollTimer: number | null = null;


export function showBackendError(error: unknown, fallbackMessage: string) {
  if (isBackendNotImplemented(error)) {
    showToast("warning", fallbackMessage);
    return;
  }
  showToast("error", (error as Error)?.message || fallbackMessage);
}


// —————————————————————————————————————————————
// 初始化加载
// —————————————————————————————————————————————

export async function loadDevices() {
  try {
    const devices = await fetchDevices();
    if (devices?.default_device) {
      showToast("success", `后端设备已连接: ${devices.default_device}`);
    }
  } catch (error) {
    showBackendError(error, "设备接口暂未实现。");
  }
}


export async function loadProjectTemplates() {
  try {
    const result = await fetchProjectTemplates();
    if (result?.count) {
      showToast("info", `已连接模板库: ${result.count} 个模板`);
    }
  } catch (error) {
    showBackendError(error, "模板列表接口暂未实现。");
  }
}


export async function loadTemplateToCanvas(templateName: string) {
  try {
    const result = await fetchProjectTemplate(templateName);
    const graph = result?.model;
    if (!graph) {
      showToast("error", "模板数据为空，无法加载。");
      return;
    }

    applyTemplateGraph(graph);
    showToast("success", `已加载模板: ${templateName}`);
  } catch (error) {
    showBackendError(error, "模板加载接口暂未实现。");
  }
}


// —————————————————————————————————————————————
// 结构校验
// —————————————————————————————————————————————

export async function handleValidateModel() {
  validating.value = true;

  try {
    const result = await validateModel(getCurrentModelGraph());
    applyValidationResult(result);
    showToast("success", "结构校验完成。");
  } catch (error) {
    showBackendError(error, "结构校验接口暂未实现。");
    applyUnavailableValidation(
      isBackendUnavailable(error) ? "后端服务未启动" : "结构校验接口暂未实现"
    );
  } finally {
    validating.value = false;
  }
}


function applyValidationResult(result: ValidationResult) {
  const valid = result?.valid === true || result?.status === "ok";
  if (valid) {
    store.validationStatus = "passing";
    applyValidationUI(true, "结构校验通过");
    return;
  }

  store.validationStatus = "failed";
  applyValidationUI(false, result?.message || "结构校验失败");
}


function applyUnavailableValidation(message: string) {
  store.validationStatus = "unvalidated";
  store.validationSummary = {
    visible: true,
    kind: "warning",
    icon: "mdi:clock-alert-outline",
    text: message,
  };
}


function applyValidationUI(isPass: boolean, message: string) {
  store.validationSummary = {
    visible: true,
    kind: isPass ? "success" : "error",
    icon: isPass ? "mdi:check-circle" : "mdi:alert-circle",
    text: message,
  };
  store.nodeBadge = isPass ? "passed" : "pending";

  if (isPass) {
    updateShapeHints();
  }
}


// —————————————————————————————————————————————
// 保存 / 导出
// —————————————————————————————————————————————

export async function handleSaveProject() {
  const userId = window.prompt("请输入 user_id，用于保存到 /projects：");
  if (!userId) {
    showToast("warning", "已取消保存。");
    return;
  }

  const name = window.prompt("请输入项目名称：", "Untitled Model");
  if (!name) {
    showToast("warning", "已取消保存。");
    return;
  }

  try {
    const result = await createProject({
      user_id: userId,
      name,
      model_graph: getCurrentModelGraph(),
      description: "Created from visual model editor",
    });
    showToast("success", `项目已保存: ${result?.data?.name || name}`);
  } catch (error) {
    showBackendError(error, "保存项目失败，请确认用户已创建。");
  }
}


export async function handleExportCode() {
  ui.exportModalOpen = true;
  store.exportCodeDisplay = "正在请求后端导出接口...";

  try {
    const result = await exportPytorchCode(getCurrentModelGraph());
    const code = typeof result === "string" ? result : result?.code || result?.source_code;
    store.lastExportCode = typeof code === "string" ? code : JSON.stringify(result, null, 2);
    store.exportCodeDisplay = store.lastExportCode;
    showToast("success", "PyTorch 代码已从后端导出。");
  } catch (error) {
    showBackendError(error, "代码导出接口暂未实现。");
    store.lastExportCode = "";
    store.exportCodeDisplay = "代码导出接口暂未实现。";
  }
}


export function closeExportModal() {
  ui.exportModalOpen = false;
}


export async function copyExportCode() {
  if (!store.lastExportCode) {
    showToast("warning", "暂无可复制代码。");
    return;
  }

  try {
    await navigator.clipboard.writeText(store.lastExportCode);
    showToast("success", "代码已复制。");
  } catch {
    showToast("warning", "当前浏览器不支持自动复制。");
  }
}


export function downloadExportCode() {
  if (!store.lastExportCode) {
    showToast("warning", "暂无可下载代码。");
    return;
  }

  const blob = new Blob([store.lastExportCode], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "MNIST_CNN.py";
  link.click();
  URL.revokeObjectURL(url);
}


// —————————————————————————————————————————————
// 训练任务
// —————————————————————————————————————————————

async function submitTrainingJob() {
  const trainConfig = getTrainConfig();
  const result = await startTraining(getCurrentModelGraph(), trainConfig);
  return {
    result,
    trainConfig,
    jobId: result?.job_id,
  };
}


export async function handleStartTraining() {
  trainStarting.value = true;

  try {
    const { result, trainConfig, jobId } = await submitTrainingJob();
    setTrainingJob({
      job_id: jobId,
      status: result?.job_status || result?.status || "pending",
      current_epoch: result?.current_epoch ?? 0,
      total_epochs: result?.total_epochs ?? trainConfig.epochs,
      progress: 0,
      trainConfig,
    });
    showToast("success", `训练任务已创建: ${store.jobId || "未知任务"}`);
    if (jobId) {
      openCurrentTrainingMonitor();
      void pollTrainingStatus(jobId);
    }
  } catch (error) {
    showBackendError(error, "训练接口暂未实现。");
  } finally {
    trainStarting.value = false;
  }
}


function stopTrainingPanelPolling() {
  if (trainingPollTimer) {
    clearTimeout(trainingPollTimer);
    trainingPollTimer = null;
  }
}


async function pollTrainingStatus(jobId: string) {
  stopTrainingPanelPolling();

  try {
    const status = await fetchTrainingStatus(jobId);
    setTrainingJob(status);
    if (status?.status === "completed") {
      const result = await fetchTrainingResult(jobId);
      setTrainingJob({
        ...result,
        progress: 1,
      });
      showToast("success", `训练完成，accuracy=${result?.accuracy ?? "未知"}`);
      return;
    }
    if (status?.status === "failed" || status?.status === "cancelled") {
      showToast(status.status === "failed" ? "error" : "warning", `训练${getTrainingStatusLabel(status.status)}。`);
      return;
    }
    trainingPollTimer = window.setTimeout(() => pollTrainingStatus(jobId), 1000);
  } catch (error) {
    showBackendError(error, "训练状态接口暂未实现。");
  }
}


export function openCurrentTrainingMonitor() {
  if (!store.trainingJob?.job_id) {
    showToast("warning", "当前没有可查看的训练任务。");
    return;
  }

  openTrainingMonitor({
    live: true,
    jobId: store.trainingJob.job_id,
    fetchStatus: fetchTrainingStatus,
    fetchResult: fetchTrainingResult,
    hyperparams: store.trainingJob.trainConfig || getTrainConfig(),
    layers: getTrainingLayers(),
    onRerun: async () => {
      const { jobId, trainConfig, result } = await submitTrainingJob();
      setTrainingJob({
        job_id: jobId,
        status: result?.job_status || result?.status || "pending",
        current_epoch: result?.current_epoch ?? 0,
        total_epochs: result?.total_epochs ?? trainConfig.epochs,
        progress: 0,
        trainConfig,
      });
      if (jobId) {
        void pollTrainingStatus(jobId);
      }
      return { jobId };
    },
  });
}
