// 与后端交互的业务动作（校验 / 保存 / 导出 / 训练）。
// 所有操作在发起时捕获所属画布的引用，异步结果写回原画布——
// 各画布可以并行进行结构检查、保存模型、导出代码、训练与查看训练任务。

import {
  cancelTraining,
  createProject,
  deleteProject,
  fetchProjectTemplate,
  fetchProjectTemplates,
  getProject,
  isBackendNotImplemented,
  listProjects,
  startTraining,
} from "./api/client";
import { auth, isLoggedIn } from "./auth";
import { addCanvas, applyTemplateGraph } from "./canvas";
import { openTrainingMonitor } from "./monitor";
import {
  activeCanvas,
  agent,
  getCurrentModelGraph,
  getTrainConfig,
  getTrainingLayers,
  setTrainingJob,
  showToast,
  templateLibrary,
  ui,
  updateShapeHints,
} from "./store";
import type { WorkCanvas } from "./store";
import type { ProjectMeta, TrainConfig, TrainStartResponse, ValidationResult } from "./types";
import { requestAgent } from "./ws";


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

  // 结构校验由本机 Agent 的训练运行时执行（云端不含 PyTorch）
  if (!agent.online) {
    showToast("warning", "结构校验需要本机训练 Agent，请先启动本地 Agent。");
    ui.agentModalOpen = true;
    return;
  }

  canvas.validating = true;
  try {
    const result = await requestAgent<ValidationResult>("validate", { model: getCurrentModelGraph(canvas) });
    applyValidationResult(canvas, result);
  } catch (error) {
    showToast("error", (error as Error)?.message || "结构校验失败。");
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

// 点击「保存模型」：打开内置保存弹窗（替代浏览器 prompt）
export function handleSaveProject() {
  if (!isLoggedIn() || !auth.user?.id) {
    showToast("warning", "登录状态已失效，请重新登录。");
    return;
  }
  ui.saveModalOpen = true;
}


// 由保存弹窗提交：以给定名称/描述保存当前画布的模型图
export async function saveProject(name: string, description: string): Promise<boolean> {
  const canvas = activeCanvas();
  if (!auth.user?.id) {
    showToast("warning", "登录状态已失效，请重新登录。");
    return false;
  }
  try {
    const result = await createProject({
      user_id: auth.user.id,
      name,
      model_graph: getCurrentModelGraph(canvas),
      description,
    });
    canvas.name = name;
    showToast("success", `模型已保存：${result?.data?.name || name}`);
    return true;
  } catch (error) {
    showBackendError(error, "保存模型失败。");
    return false;
  }
}


// —————————————————————————————————————————————
// 我的项目（加载 / 删除已保存的模型）
// —————————————————————————————————————————————

export async function fetchMyProjects(): Promise<ProjectMeta[]> {
  if (!auth.user?.id) return [];
  const result = await listProjects(auth.user.id);
  return result?.data ?? [];
}


// 把已保存的项目加载到画布：新建一个画布并铺开模型图
export async function loadProjectToCanvas(project: ProjectMeta): Promise<void> {
  try {
    const detail = await getProject(project.id);
    const graph = detail?.data?.model_graph;
    if (!graph) {
      showToast("error", "项目数据为空，无法加载。");
      return;
    }
    // 新建画布承载该项目，避免覆盖当前正在编辑的画布
    addCanvas();
    const canvas = activeCanvas();
    canvas.name = project.name;
    applyTemplateGraph(graph);
    ui.projectsModalOpen = false;
    showToast("success", `已加载模型：${project.name}`);
  } catch (error) {
    showBackendError(error, "加载模型失败。");
  }
}


export async function removeProject(project: ProjectMeta): Promise<boolean> {
  try {
    await deleteProject(project.id);
    showToast("success", `已删除模型：${project.name}`);
    return true;
  } catch (error) {
    showBackendError(error, "删除模型失败。");
    return false;
  }
}


export async function handleExportCode() {
  const canvas = activeCanvas();

  // 代码导出由本机 Agent 的训练运行时执行
  if (!agent.online) {
    showToast("warning", "代码导出需要本机训练 Agent，请先启动本地 Agent。");
    ui.agentModalOpen = true;
    return;
  }

  ui.exportModalOpen = true;
  canvas.exportCodeDisplay = "正在请求本机 Agent 导出代码...";

  try {
    const result = await requestAgent<{ code?: string }>("export", {
      model: getCurrentModelGraph(canvas),
      class_name: "GeneratedModel",
    });
    const code = result?.code;
    canvas.lastExportCode = typeof code === "string" ? code : JSON.stringify(result, null, 2);
    canvas.exportCodeDisplay = canvas.lastExportCode;
    showToast("success", `${canvas.name} 的 PyTorch 代码已导出。`);
  } catch (error) {
    canvas.lastExportCode = "";
    canvas.exportCodeDisplay = (error as Error)?.message || "代码导出失败。";
    showToast("error", canvas.exportCodeDisplay);
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

// 提交训练任务到云端，云端下发给本机 Agent 执行。进度由 WebSocket 推送。
async function submitTrainingJob(canvas: WorkCanvas): Promise<{ result: TrainStartResponse; trainConfig: TrainConfig; jobId?: string }> {
  const trainConfig = getTrainConfig(canvas);
  const result = await startTraining(getCurrentModelGraph(canvas), trainConfig, auth.user!.id!);
  return { result, trainConfig, jobId: result?.job_id };
}


export async function handleStartTraining() {
  const canvas = activeCanvas();
  if (canvas.trainStarting) return;

  // 训练在用户本机 Agent 执行，需先确认 Agent 在线
  if (!agent.online) {
    showToast("warning", "训练需要本机训练 Agent，请先启动本地 Agent。");
    ui.agentModalOpen = true;
    return;
  }

  canvas.trainStarting = true;
  try {
    const { result, trainConfig, jobId } = await submitTrainingJob(canvas);
    // 云端确认无在线 Agent（竞态：刚下发时 Agent 掉线）
    if (result?.agent_status === "offline") {
      showToast("warning", result.message || "未检测到在线的本机训练 Agent。");
      ui.agentModalOpen = true;
      return;
    }
    setTrainingJob(canvas, {
      job_id: jobId,
      status: result?.job_status || "dispatched",
      current_epoch: 0,
      total_epochs: trainConfig.epochs,
      progress: 0,
      trainConfig,
    });
    showToast("success", `训练任务已下发到本机 Agent。`);
    if (jobId) {
      openTrainingMonitorForCanvas(canvas);
    }
  } catch (error) {
    showBackendError(error, "训练任务下发失败。");
  } finally {
    canvas.trainStarting = false;
  }
}


// 打开指定画布的训练监控页（进度由 WebSocket 推送，重新训练回写到该画布）
function openTrainingMonitorForCanvas(canvas: WorkCanvas) {
  if (!canvas.trainingJob?.job_id) {
    showToast("warning", "当前画布没有可查看的训练任务。");
    return;
  }

  openTrainingMonitor({
    live: true,
    jobId: canvas.trainingJob.job_id,
    cancelJob: (jobId: string) => cancelTraining(jobId, auth.user!.id!),
    hyperparams: canvas.trainingJob.trainConfig || getTrainConfig(canvas),
    layers: getTrainingLayers(canvas),
    onRerun: async () => {
      const { jobId, trainConfig, result } = await submitTrainingJob(canvas);
      if (result?.agent_status === "offline") {
        showToast("warning", "本机 Agent 已离线，无法重新训练。");
        return { jobId: undefined };
      }
      setTrainingJob(canvas, {
        job_id: jobId,
        status: result?.job_status || "dispatched",
        current_epoch: 0,
        total_epochs: trainConfig.epochs,
        progress: 0,
        trainConfig,
      });
      return { jobId };
    },
  });
}


export function openCurrentTrainingMonitor() {
  openTrainingMonitorForCanvas(activeCanvas());
}
