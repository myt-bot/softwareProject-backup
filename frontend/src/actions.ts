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
  validateModelStructure,
} from "./api/client";
import { auth, isLoggedIn } from "./auth";
import { addCanvas, applyTemplateGraph, drawLines } from "./canvas";
import { openTrainingMonitor } from "./monitor";
import {
  activeCanvas,
  agent,
  CONTAINER_ID_SEP,
  getCurrentModelGraph,
  getTrainConfig,
  getTrainingLayers,
  isTrainingJobActive,
  setTrainingJob,
  showToast,
  templateLibrary,
  ui,
  updateShapeHints,
} from "./store";
import type { WorkCanvas } from "./store";
import type { ProjectMeta, TrainConfig, TrainStartResponse, ValidationResult } from "./types";
import { requestAgent } from "./ws";

type ExportCodeFormat = "py" | "ipynb";
type ExportAgentResult = {
  code?: string;
  format?: ExportCodeFormat;
  filename?: string;
};

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

  // 结构校验与维度推导在云端完成，无需本地 Agent（训练才需要 Agent）
  canvas.validating = true;
  try {
    const result = await validateModelStructure(getCurrentModelGraph(canvas));
    applyValidationResult(canvas, result);
  } catch (error) {
    showToast("error", (error as Error)?.message || "结构校验失败。");
    canvas.validationStatus = "unvalidated";
  } finally {
    canvas.validating = false;
    // 重绘连线：校验通过则显示数据流向动画，否则清除
    drawLines();
  }
}


function applyValidationResult(canvas: WorkCanvas, result: ValidationResult) {
  canvas.nodeErrors = {};
  const valid = result?.valid === true || result?.status === "ok";
  if (valid) {
    canvas.validationStatus = "passing";
    canvas.nodeBadge = "passed";
    updateShapeHints(canvas, result?.shapes);
    showToast("success", `${canvas.name} 结构校验通过。`);
    return;
  }

  canvas.validationStatus = "failed";
  canvas.nodeBadge = "pending";

  // 把每个出错节点标红并给人话提示（用节点标题而非内部 id），实现"定位"
  const nodeErrors: Record<string, string> = {};
  const shapes = result?.shapes || {};
  for (const [layerId, info] of Object.entries(shapes)) {
    if (info?.status && info.status !== "ok") {
      // 容器内部层的错误（层级 id 形如 容器id__内部层id）归到容器节点上标红
      const containerId = layerId.split(CONTAINER_ID_SEP)[0]!;
      const node = canvas.nodes.find(n => n.id === layerId) || canvas.nodes.find(n => n.id === containerId);
      const targetId = node ? node.id : layerId;
      nodeErrors[targetId] = friendlyShapeError(node?.title || layerId, info);
    }
  }
  canvas.nodeErrors = nodeErrors;

  const errorNodeIds = Object.keys(nodeErrors);
  if (errorNodeIds.length > 0) {
    // 选中并聚焦第一个出错节点，方便用户直接看到
    const firstMsg = nodeErrors[errorNodeIds[0]!]!;
    showToast("error", `结构有问题：${firstMsg}（出错的层已在画布上标红）`);
    return;
  }

  // 没有具体到某一层的错误（如缺少 Input/Output、节点未连通）：给整体的人话提示
  showToast("error", `${canvas.name}：${friendlyGraphError(result)}`);
}


// 把维度类错误翻译成初学者能懂的话（引用节点标题，给可操作建议）
function friendlyShapeError(nodeTitle: string, info: { layer_type?: string; actual_in_features?: number; expected_in_features?: number }): string {
  if (info.layer_type === "Linear" && info.actual_in_features != null) {
    return `「${nodeTitle}」全连接层输入维度对不上：上一层实际输出 ${info.actual_in_features} 个特征，但这里设定的输入是 ${info.expected_in_features}。把该层的“输入特征数”改成 ${info.actual_in_features}，或调整它前面的层。`;
  }
  return `「${nodeTitle}」这一层的输出尺寸算不出来，请检查它的参数，或它前面的连接是否接对了。`;
}


// 把整体结构错误（缺节点/未连通等）翻译成人话
function friendlyGraphError(result: ValidationResult): string {
  const first = (result?.errors && result.errors[0]) || result?.message || "结构校验没通过";
  if (first.includes("缺少必要节点") && first.includes("Input")) {
    return "模型缺少输入节点：请先从左侧拖一个「Input」层进来。";
  }
  if (first.includes("缺少必要节点") && first.includes("Output")) {
    return "模型缺少输出节点：请加一个「Output」层作为结尾。";
  }
  if (first.includes("未连通") || first.includes("连接") || first.includes("孤立") || first.includes("环")) {
    return "各层还没连成一条通路：请检查是否有节点没连线，从 Input 一路连到 Output。";
  }
  return first;
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


export async function handleExportCode(format?: ExportCodeFormat) {
  const canvas = activeCanvas();
  if (format) {
    canvas.exportFormat = format;
  }

  // 代码导出由本机 Agent 的训练运行时执行
  if (!agent.online) {
    showToast("warning", "代码导出需要本机训练 Agent，请先启动本地 Agent。");
    ui.agentModalOpen = true;
    return;
  }

  ui.exportModalOpen = true;
  canvas.exportCodeDisplay = `正在请求本机 Agent 导出 ${canvas.exportFormat === "ipynb" ? "Notebook" : "Python"} 代码...`;

  try {
    const result = await requestAgent<ExportAgentResult>("export", {
      model: getCurrentModelGraph(canvas),
      class_name: "GeneratedModel",
      format: canvas.exportFormat,
      train_config: getTrainConfig(canvas),
    });
    const code = result?.code;
    canvas.lastExportCode = typeof code === "string" ? code : JSON.stringify(result, null, 2);
    canvas.exportCodeDisplay = canvas.lastExportCode;
    canvas.exportFilename = result?.filename || `GeneratedModel.${canvas.exportFormat}`;
    if (result?.format === "py" || result?.format === "ipynb") {
      canvas.exportFormat = result.format;
    }
    showToast("success", `${canvas.name} 的 ${canvas.exportFormat === "ipynb" ? "Notebook" : "PyTorch 代码"} 已导出。`);
  } catch (error) {
    canvas.lastExportCode = "";
    canvas.exportCodeDisplay = (error as Error)?.message || "代码导出失败。";
    showToast("error", canvas.exportCodeDisplay);
  }
}


export function setExportFormat(format: ExportCodeFormat) {
  const canvas = activeCanvas();
  if (canvas.exportFormat === format) return;
  canvas.exportFormat = format;
  canvas.exportFilename = `GeneratedModel.${format}`;
  if (agent.online) {
    void handleExportCode(format);
    return;
  }
  canvas.exportCodeDisplay = "请选择导出格式后点击“导出代码”。";
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

  const type = canvas.exportFormat === "ipynb"
    ? "application/x-ipynb+json;charset=utf-8"
    : "text/x-python;charset=utf-8";
  const blob = new Blob([canvas.lastExportCode], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = canvas.exportFilename || `GeneratedModel.${canvas.exportFormat}`;
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

  if (isTrainingJobActive(canvas.trainingJob)) {
    showToast("info", "当前画布已有训练任务进行中，请打开训练详情查看进度。");
    openTrainingMonitorForCanvas(canvas);
    return;
  }

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
    initialStatus: {
      ...canvas.trainingJob,
      current_epoch: canvas.trainingJob.current_epoch ?? canvas.trainingJob.metrics?.length ?? 0,
      total_epochs: canvas.trainingJob.total_epochs ?? canvas.trainingJob.trainConfig?.epochs,
    },
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
