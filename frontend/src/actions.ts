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
import { addCanvas, applyTemplateGraph, drawLines, switchCanvas } from "./canvas";
import { openTrainingMonitor } from "./monitor";
import {
  activeCanvas,
  agent,
  CONTAINER_ID_SEP,
  getCurrentModelGraph,
  getTrainConfig,
  getTrainingGraph,
  getTrainingSummary,
  isTrainingJobActive,
  setTrainingJob,
  showToast,
  store,
  templateLibrary,
  ui,
  updateShapeHints,
} from "./store";
import type { ValidationIssue, WorkCanvas } from "./store";
import type { GraphNode, LayerShapeInfo, ProjectMeta, TrainConfig, TrainStartResponse, ValidationResult } from "./types";
import { requestAgent } from "./ws";
import { createZip } from "./zip";

type ExportCodeFormat = "py" | "ipynb";
type ExportAgentResult = {
  code?: string;
  format?: ExportCodeFormat;
  filename?: string;
  requirements?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}

function isValidationResult(value: unknown): value is ValidationResult {
  if (!isRecord(value)) return false;
  if (typeof value.valid !== "boolean") return false;
  if (!isStringArray(value.errors)) return false;
  if (value.warnings !== undefined && !isStringArray(value.warnings)) return false;
  if (value.shapes !== undefined && !isRecord(value.shapes)) return false;
  if (
    value.message !== undefined
    && value.message !== null
    && typeof value.message !== "string"
  ) {
    return false;
  }
  if (value.status !== undefined && typeof value.status !== "string") return false;
  return true;
}

function validationToastMessage(canvas: WorkCanvas, message: string): string {
  return activeCanvas().id === canvas.id ? message : `${canvas.name}：${message}`;
}

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


export async function loadTemplateToCanvas(templateKey: string, templateName?: string): Promise<boolean> {
  try {
    const result = await fetchProjectTemplate(templateKey);
    const graph = result?.model;
    if (!graph) {
      showToast("error", "模板数据为空，无法加载。");
      return false;
    }

    // 防覆盖：无画布、或当前画布已有内容时，把模板载入到新画布，
    // 避免清掉用户正在编辑的模型，也避免落到占位画布上
    const current = store.canvases.length > 0 ? activeCanvas() : null;
    if (!current || current.nodes.length > 0 || current.connections.length > 0) {
      addCanvas();
    }
    const target = activeCanvas();
    // 画布名称与模板名保持一致，标签页一眼可辨
    if (templateName) target.name = templateName;
    applyTemplateGraph(graph);
    ui.templateGalleryOpen = false;
    showToast("success", `已加载模板: ${templateName || templateKey}`);
    return true;
  } catch (error) {
    showBackendError(error, "模板加载接口暂未实现。");
    return false;
  }
}


// —————————————————————————————————————————————
// 结构校验（按画布并行）
// —————————————————————————————————————————————

// 返回本次校验结果（供 AI 助手的 validate_model 命令复用同一套 UI 更新并把结论喂回模型）；
// 正在校验中或出错时返回 null。ActionBar 按钮以 void 方式调用，忽略返回值即可。
export async function handleValidateModel(): Promise<ValidationResult | null> {
  const canvas = activeCanvas();
  if (canvas.validating) return null;

  // 结构校验与维度推导在云端完成，无需本地 Agent（训练才需要 Agent）
  const modelSnapshot = getCurrentModelGraph(canvas);
  const serializedSnapshot = JSON.stringify(modelSnapshot);
  canvas.validating = true;
  canvas.validationRequestError = null;

  try {
    const response: unknown = await validateModelStructure(modelSnapshot);
    if (!isValidationResult(response)) {
      throw new Error("结构检查服务返回了无法识别的结果，请重新检查。");
    }
    const result = response;

    if (!store.canvases.includes(canvas)) {
      return null;
    }

    if (JSON.stringify(getCurrentModelGraph(canvas)) !== serializedSnapshot) {
      return null;
    }

    applyValidationResult(canvas, result);
    return result;
  } catch (error) {
    if (!store.canvases.includes(canvas)) return null;
    if (JSON.stringify(getCurrentModelGraph(canvas)) !== serializedSnapshot) return null;

    const message = (error as Error)?.message?.trim()
      || "结构检查请求未完成，请稍后重试。";
    showToast("error", validationToastMessage(canvas, message));
    canvas.validationStatus = "unvalidated";
    canvas.lastValidationResult = null;
    canvas.validationRequestError = message;
    canvas.nodeBadge = "none";
    canvas.nodeErrors = {};
    canvas.validationIssues = [];
    return null;
  } finally {
    canvas.validating = false;
    // 重绘连线：校验通过则显示数据流向动画，否则清除
    drawLines();
  }
}


function applyValidationResult(canvas: WorkCanvas, result: ValidationResult) {
  canvas.validationRequestError = null;
  canvas.lastValidationResult = result;
  canvas.nodeErrors = {};
  canvas.validationIssues = [];
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
  canvas.validationIssues = buildValidationIssues(canvas, result);
  // 校验失败只使用画布内的问题列表反馈，不再同时弹 Toast 或显示旧版节点错误文案。
}


function errorLayerId(error: string): string | null {
  const patterns = [
    /^层\s+([^\s:：,，]+)\s*[:：]/,
    /^(?:Input|Output)\s*节点[^:：]*[:：]\s*([^\s,，]+)\s*$/,
    /^(?:存在孤立节点或连接异常|连接起点不存在|连接终点不存在)\s*[:：]\s*([^\s,，]+)\s*$/,
    /^节点\s+([^\s]+)\s+不能连接到自身/,
  ];
  for (const pattern of patterns) {
    const matched = error.match(pattern);
    if (matched?.[1]) return matched[1];
  }
  return null;
}


function issueParameter(error: string, layerType?: string): string | null {
  if (/in_features|输入维度|输入特征/i.test(error)) return "in_features";
  if (/out_features|输出神经元/i.test(error)) return "out_features";
  if (/out_channels|输出通道/i.test(error)) return "out_channels";
  if (/kernel_size|卷积核|池化核/i.test(error)) return "kernel_size";
  if (/stride|步长/i.test(error)) return "stride";
  if (/padding|填充/i.test(error)) return "padding";
  if (/input shape|输入形状|shape/i.test(error) && layerType === "Input") return "shape";
  if (/merge|合并模式/i.test(error)) return "merge";
  // Conv2D / Pooling 无法推导输出尺寸时，最常见且最值得先检查的是窗口大小。
  if (/输出尺寸|无法推导输出维度/.test(error) && (layerType === "Conv2D" || layerType === "Pooling")) {
    return "kernel_size";
  }
  return null;
}


function issueTitle(error: string, nodeTitle?: string, layerType?: string): string {
  const prefix = nodeTitle || layerType || "模型";
  if (/Linear.*(?:输入维度|in_features).*不匹配/i.test(error)) return `${prefix} 输入维度不匹配`;
  if ((layerType === "Conv2D" || /Conv2D/i.test(error)) && /输出尺寸|无法推导输出维度|shape|维度/i.test(error)) {
    return `${prefix} 卷积核或输入尺寸不匹配`;
  }
  if (layerType === "Pooling" && /输出尺寸|无法推导输出维度|shape|维度/i.test(error)) {
    return `${prefix} 池化窗口大于输入尺寸`;
  }
  if (/没有输入连接|没有输出连接|孤立|无法到达|不在任何 Input|不能有输入连接|不能有输出连接/.test(error)) {
    return `${prefix} 未正确连接`;
  }
  if (/缺少必要节点/.test(error)) {
    const type = error.includes("Input") ? "Input" : error.includes("Output") ? "Output" : "必要";
    return `缺少 ${type} 节点`;
  }
  if (/合并模块的模式/.test(error)) return `${prefix} 尚未选择合并模式`;
  const withoutId = error.replace(/^层\s+[^:：]+\s*[:：]\s*/, "");
  return nodeTitle ? `${nodeTitle}：${withoutId}` : withoutId;
}


function issueSuggestion(error: string, node?: GraphNode, shapeInfo?: LayerShapeInfo): string {
  const inputShape = shapeInfo?.input_shape;
  const height = inputShape && inputShape.length >= 3 ? inputShape[inputShape.length - 2] : undefined;
  const width = inputShape && inputShape.length >= 3 ? inputShape[inputShape.length - 1] : undefined;
  const minSide = typeof height === "number" && typeof width === "number"
    ? Math.min(height, width)
    : undefined;

  if (node?.type === "Conv2D" && /输出尺寸|无法推导输出维度|shape|维度/i.test(error)) {
    const current = node.params.kernel_size;
    const recommended = minSide == null ? 3 : minSide >= 3 ? 3 : 1;
    const sizeNote = minSide == null ? "" : `（当前输入为 ${height}×${width}）`;
    return `建议将 Kernel Size 从 ${String(current ?? "当前值")} 改为 ${recommended}${sizeNote}`;
  }
  if (node?.type === "Pooling" && /输出尺寸|无法推导输出维度|shape|维度/i.test(error)) {
    const recommended = minSide == null ? 2 : minSide >= 2 ? 2 : 1;
    return `建议将 Kernel Size 改为 ${recommended}${minSide == null ? "" : `（不能大于 ${minSide}）`}`;
  }
  if (/Linear.*(?:输入维度|in_features).*不匹配/i.test(error)) {
    const actual = shapeInfo?.actual_in_features;
    return actual == null
      ? "建议检查前一层输出尺寸，再调整 Linear 的输入维度"
      : `建议将 in_features 调整为 ${actual}，或修改前一层输出`;
  }
  if (/out_channels|输出通道/i.test(error)) return "建议将 Out Channels 设为正整数，例如 16";
  if (/out_features|输出神经元/i.test(error)) return "建议将 Out Features 设为正整数；分类末层通常等于类别数";
  if (/stride|步长/i.test(error)) return "建议将 Stride 设为正整数，通常使用 1";
  if (/padding|填充/i.test(error)) return "建议将 Padding 设为非负整数，通常使用 0 或 1";
  if (/Dropout|\bp\b.*0.*1/i.test(error)) return "建议将 Dropout Rate 设在 0 到 1 之间，例如 0.5";
  if (/shape|输入形状/i.test(error) && node?.type === "Input") return "建议使用“通道,高度,宽度”格式，例如 1,28,28";
  if (/合并模块的模式/.test(error)) return "建议在参数面板选择 add、concat 或 matmul";
  if (/缺少必要节点/.test(error)) {
    return error.includes("Input") ? "建议从组件库添加一个 Input 节点" : "建议从组件库添加一个 Output 节点";
  }
  return "建议打开对应参数，按字段提示修改后重新检查";
}


function isConnectivityError(error: string): boolean {
  return /没有输入连接|没有输出连接|孤立|无法到达|不在任何 Input|不能有输入连接|不能有输出连接|多个层节点时必须提供 connections|连接起点不存在|连接终点不存在|不能连接到自身|重复连接|连接中存在环/.test(error);
}


function buildValidationIssues(canvas: WorkCanvas, result: ValidationResult): ValidationIssue[] {
  const errors = result.errors?.length
    ? result.errors
    : [result.message || "结构校验未通过"];
  const shapes = result.shapes || {};

  const rawIssues = errors.map((error, index) => {
    let layerId = errorLayerId(error);
    if (!layerId) {
      layerId = Object.entries(shapes).find(([, info]) => info?.error === error)?.[0] || null;
    }

    const topLevelId = layerId?.split(CONTAINER_ID_SEP)[0] || null;
    const node = canvas.nodes.find(item => item.id === layerId)
      || canvas.nodes.find(item => item.id === topLevelId)
      || null;
    const shapeInfo = layerId ? shapes[layerId] : undefined;
    const layerType = shapeInfo?.layer_type || node?.type;

    return {
      id: `${index}-${layerId || "graph"}`,
      title: issueTitle(error, node?.title, layerType),
      detail: error,
      suggestion: issueSuggestion(error, node || undefined, shapeInfo),
      nodeId: node?.id || null,
      parameter: issueParameter(error, layerType),
    };
  });

  const compactIssues: ValidationIssue[] = [];
  const seen = new Set<string>();
  const connectionErrors = rawIssues.filter((_, index) => isConnectivityError(errors[index]!));

  // 一处断链常会派生“无输入、无输出、孤立、不可达”等多条后端错误；
  // 对用户而言它们是同一个修复任务，因此合并成一条完整通路提示。
  if (connectionErrors.length) {
    const hasCycle = errors.some(error => /连接中存在环|不能连接到自身/.test(error));
    const targetNode = connectionErrors
      .map(issue => canvas.nodes.find(node => node.id === issue.nodeId))
      .find(node => node?.type === "Output")
      || connectionErrors
        .map(issue => canvas.nodes.find(node => node.id === issue.nodeId))
        .find(Boolean);
    compactIssues.push({
      id: "connectivity",
      title: hasCycle ? "模型连接存在环路" : "Input 到 Output 未形成完整通路",
      detail: hasCycle
        ? "请移除回到前面节点的连线，保证数据只向 Output 方向流动。"
        : "请检查节点之间的连线，确保数据能从 Input 依次流到 Output。",
      suggestion: hasCycle
        ? "建议删除形成回路的连线，再按从上游到下游的方向重新连接"
        : "建议补齐断开的连线，形成 Input → 中间层 → Output 的完整路径",
      nodeId: targetNode?.id || null,
      parameter: null,
    });
  }

  rawIssues.forEach((issue, index) => {
    if (isConnectivityError(errors[index]!)) return;
    // 上游参数已导致维度推导失败时，Output/ReLU 等下游节点的“无法推导”只是结果，
    // 不再单独列为新问题，避免用户误以为还要修改下游节点。
    const isCascadingShapeError = !issue.parameter
      && /无法推导输出维度|无法推导.*shape/i.test(errors[index]!)
      && rawIssues.some(other => other.nodeId !== issue.nodeId && Boolean(other.parameter));
    if (isCascadingShapeError) return;
    // 同一节点、同一参数的多条底层报错只保留第一条；没有参数时按标题去重。
    const key = issue.nodeId
      ? `${issue.nodeId}:${issue.parameter || issue.title}`
      : `graph:${issue.title}`;
    if (seen.has(key)) return;
    seen.add(key);
    compactIssues.push({ ...issue, id: `issue-${compactIssues.length}` });
  });

  return compactIssues;
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
export async function loadProjectToCanvas(project: ProjectMeta): Promise<boolean> {
  try {
    const detail = await getProject(project.id);
    const graph = detail?.data?.model_graph;
    if (!graph) {
      showToast("error", "项目数据为空，无法加载。");
      return false;
    }
    // 新建画布承载该项目，避免覆盖当前正在编辑的画布
    addCanvas();
    const canvas = activeCanvas();
    canvas.name = project.name;
    applyTemplateGraph(graph);
    ui.projectsModalOpen = false;
    showToast("success", `已加载模型：${project.name}`);
    return true;
  } catch (error) {
    showBackendError(error, "加载模型失败。");
    return false;
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
    canvas.exportRequirements = result?.requirements || "";
    if (result?.format === "py" || result?.format === "ipynb") {
      canvas.exportFormat = result.format;
    }
    showToast("success", `${canvas.name} 的 ${canvas.exportFormat === "ipynb" ? "Notebook" : "PyTorch 代码"} 已导出。`);
  } catch (error) {
    canvas.lastExportCode = "";
    canvas.exportRequirements = "";
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


function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// 兜底的依赖清单：当本机 Agent 版本较旧、未随代码返回 requirements 时使用
function defaultRequirements(format: ExportCodeFormat): string {
  const lines = [
    "# 运行本导出代码所需的 Python 依赖（建议 Python 3.9+）。",
    "# 若需 GPU 加速，请前往 https://pytorch.org 按你的 CUDA 版本选择",
    "# 对应的 torch / torchvision 安装命令后再安装其余依赖。",
    "torch>=2.0",
    "torchvision>=0.15",
  ];
  if (format === "ipynb") {
    lines.push("# 运行 Notebook 需要 Jupyter 环境");
    lines.push("notebook>=7.0");
  }
  return lines.join("\n") + "\n";
}

// 环境名：run-<模型名>，并过滤掉不适合作为环境名/shell 变量的字符
function envNameFromBase(baseName: string): string {
  const safe = baseName.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[-_.]+|[-_.]+$/g, "");
  return `run-${safe || "model"}`;
}

// Linux / macOS 环境配置脚本：优先用 conda 创建命名环境，缺失时回退到 venv
function setupScriptSh(envName: string): string {
  return [
    "#!/usr/bin/env bash",
    "# 自动化环境配置脚本 —— 读取 requirements.txt 创建并安装运行环境。",
    `# 环境名称：${envName}`,
    "set -e",
    `ENV_NAME="${envName}"`,
    'cd "$(dirname "$0")"',
    "",
    'if command -v conda >/dev/null 2>&1; then',
    '  echo "检测到 conda，创建环境 ${ENV_NAME} ..."',
    '  conda create -y -n "${ENV_NAME}" python=3.10',
    '  conda run -n "${ENV_NAME}" python -m pip install --upgrade pip',
    '  conda run -n "${ENV_NAME}" python -m pip install -r requirements.txt',
    '  echo ""',
    '  echo "环境已就绪。使用前请执行： conda activate ${ENV_NAME}"',
    "else",
    '  echo "未检测到 conda，改用 venv 在当前目录创建 ${ENV_NAME} ..."',
    '  python3 -m venv "${ENV_NAME}"',
    '  "${ENV_NAME}/bin/python" -m pip install --upgrade pip',
    '  "${ENV_NAME}/bin/python" -m pip install -r requirements.txt',
    '  echo ""',
    '  echo "环境已就绪。使用前请执行： source ${ENV_NAME}/bin/activate"',
    "fi",
    "",
  ].join("\n");
}

// Windows 环境配置脚本（CRLF 换行 + UTF-8 代码页，避免中文乱码）
function setupScriptBat(envName: string): string {
  return [
    "@echo off",
    "chcp 65001 >nul",
    "setlocal",
    "REM 自动化环境配置脚本 —— 读取 requirements.txt 创建并安装运行环境。",
    `REM 环境名称：${envName}`,
    `set "ENV_NAME=${envName}"`,
    'cd /d "%~dp0"',
    "",
    "where conda >nul 2>nul",
    "if %ERRORLEVEL%==0 (",
    "  echo 检测到 conda，创建环境 %ENV_NAME% ...",
    "  call conda create -y -n %ENV_NAME% python=3.10",
    "  call conda run -n %ENV_NAME% python -m pip install --upgrade pip",
    "  call conda run -n %ENV_NAME% python -m pip install -r requirements.txt",
    "  echo.",
    "  echo 环境已就绪。使用前请执行： conda activate %ENV_NAME%",
    ") else (",
    "  echo 未检测到 conda，改用 venv 创建 %ENV_NAME% ...",
    "  python -m venv %ENV_NAME%",
    '  call "%ENV_NAME%\\Scripts\\python.exe" -m pip install --upgrade pip',
    '  call "%ENV_NAME%\\Scripts\\python.exe" -m pip install -r requirements.txt',
    "  echo.",
    "  echo 环境已就绪。使用前请执行： %ENV_NAME%\\Scripts\\activate",
    ")",
    "endlocal",
    "",
  ].join("\r\n");
}

export function downloadExportCode() {
  const canvas = activeCanvas();
  if (!canvas.lastExportCode) {
    showToast("warning", "暂无可下载代码。");
    return;
  }

  // 在浏览器端把代码文件、requirements.txt 与环境配置脚本打包成 zip 下载。
  // 这样无需重装本机 Agent，导出 .py / .ipynb 都会得到一个 zip。
  const codeName = canvas.exportFilename || `GeneratedModel.${canvas.exportFormat}`;
  const baseName = codeName.replace(/\.[^./\\]+$/, "") || "GeneratedModel";
  const requirements = canvas.exportRequirements || defaultRequirements(canvas.exportFormat);
  const envName = envNameFromBase(baseName);
  const archive = createZip([
    { name: codeName, content: canvas.lastExportCode },
    { name: "requirements.txt", content: requirements },
    { name: "setup_env.sh", content: setupScriptSh(envName), mode: 0o755 },
    { name: "setup_env.bat", content: setupScriptBat(envName) },
  ]);
  const blob = new Blob([archive.buffer as ArrayBuffer], { type: "application/zip" });
  triggerDownload(blob, `${baseName}.zip`);
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

  // 必须先通过结构检查（按钮已不再禁用，这里做中央兜底，覆盖 AI 等其它入口）
  if (canvas.validationStatus !== "passing") {
    showToast(
      canvas.nodes.length ? "error" : "warning",
      canvas.nodes.length
        ? "请先点击「检查结构」并通过后，才能开始训练。"
        : "画布还是空的，先拖入层搭好模型。"
    );
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
      modelSummary: getTrainingSummary(canvas),
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

  const trainingGraph = getTrainingGraph(canvas);
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
    layers: trainingGraph.layers,
    edges: trainingGraph.edges,
    modelSummary: canvas.trainingJob.modelSummary || getTrainingSummary(canvas),
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
        modelSummary: getTrainingSummary(canvas),
      });
      return { jobId };
    },
  });
}


export function openCurrentTrainingMonitor() {
  openTrainingMonitorForCanvas(activeCanvas());
}


// 在监控页内切到另一个画布的训练任务（顶栏任务切换器调用）。
// 复用 openTrainingMonitorForCanvas 重新装载 monitor 单例（会更新 monitor.jobId，
// WS 路由随即匹配新任务），并同步活动画布，保证「返回」后回到对应画布。
export function switchTrainingMonitorToCanvas(canvasId: number) {
  const canvas = store.canvases.find(item => item.id === canvasId);
  if (!canvas?.trainingJob?.job_id) return;
  switchCanvas(canvas.id);
  openTrainingMonitorForCanvas(canvas);
}
