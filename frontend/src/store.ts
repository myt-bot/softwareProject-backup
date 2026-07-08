// 全局响应式状态与纯数据逻辑（不直接操作 DOM）。
// 画布交互（拖拽、连线、SVG 绘制等需要测量 DOM 的逻辑）在 canvas.ts。

import { reactive } from "vue";
import type {
  AgentStatus,
  Connection,
  DeviceSummary,
  GraphNode,
  LayerGroup,
  ModelGraph,
  ModelGraphConnection,
  MonitorLayer,
  Point,
  TemplateMeta,
  Toast,
  ToastType,
  TrainConfig,
  TrainingJob,
} from "./types";

export const GUIDE_VISITED_KEY = "model-workshop-visited";

export const datasetChoices = [
  { value: "MNIST", label: "MNIST · 手写数字" },
  { value: "FashionMNIST", label: "FashionMNIST · 服饰图片" },
  { value: "KMNIST", label: "KMNIST · 日文假名" },
  { value: "CIFAR10", label: "CIFAR10 · 彩色小图" },
  { value: "CIFAR100", label: "CIFAR100 · 彩色百类" },
];

export const layerGroups: LayerGroup[] = [
  {
    title: "基础层 / Base Layers",
    layers: [
      { type: "Input", desc: "输入张量定义", icon: "mdi:login-variant", color: "emerald", hint: "Input：模型的入口，定义数据形状（如图片 1×28×28）。每个模型从它开始。" },
      { type: "Output", desc: "分类输出节点", icon: "mdi:logout-variant", color: "rose", hint: "Output：模型的出口，输出最终结果（如各类别的分数）。每个模型以它结尾。" },
      { type: "Add", desc: "多分支逐元素相加", icon: "mdi:plus-circle-outline", color: "cyan", hint: "Add：把两条分支的结果逐元素相加，用于残差/跳连结构（如 ResNet）。" },
    ],
  },
  {
    title: "卷积与池化 / Conv & Pooling",
    layers: [
      { type: "Conv2D", desc: "特征提取卷积层", icon: "mdi:grid-large", color: "blue", hint: "Conv2D：提取图像的局部特征，像用放大镜扫过图片。处理图像时最常用。" },
      { type: "MaxPooling", desc: "下采样空间压缩", icon: "mdi:resize", color: "purple", hint: "MaxPooling：把特征图缩小一半，保留最显著的信息，减少计算、防过拟合。通常接在卷积后。" },
      { type: "ReLU", desc: "非线性激活函数", icon: "mdi:vector-rectangle", color: "orange", hint: "ReLU：给网络加“非线性”，把负值变 0。几乎每个卷积/全连接层后都会加它。" },
    ],
  },
  {
    title: "全连接与正则 / Linear & Regular",
    layers: [
      { type: "Flatten", desc: "多维展平为一维", icon: "mdi:layers-triple", color: "indigo", hint: "Flatten：把多维特征图“摊平”成一长条向量。卷积之后、接全连接层之前必须先展平。" },
      { type: "Linear", desc: "密集全连接层", icon: "mdi:ray-start-end", color: "cyan", hint: "Linear：全连接层，把所有输入加权组合。常用在网络末端做分类，out_features 就是类别数。" },
      { type: "Dropout", desc: "随机失活防过拟合", icon: "mdi:filter-off-outline", color: "amber", hint: "Dropout：训练时随机丢弃一部分神经元，防止模型死记硬背（过拟合）。比例一般 0.2~0.5。" },
    ],
  },
  {
    title: "序列与高级 / Sequence & Advanced",
    layers: [
      { type: "LSTM", desc: "循环网络处理序列", icon: "mdi:repeat", color: "cyan", hint: "LSTM：循环网络，擅长按顺序处理序列（文本、时间序列），能记住前面的信息。" },
      { type: "Seq2Seq", desc: "序列到序列生成", icon: "mdi:swap-horizontal", color: "indigo", hint: "Seq2Seq：把一段序列转成另一段序列，用于翻译、摘要等。" },
      { type: "TransformerEncoder", desc: "自注意力编码器", icon: "mdi:layers-outline", color: "purple", hint: "TransformerEncoder：Transformer 的编码器，靠注意力机制理解序列，是大模型的基础模块。" },
      { type: "SelfAttention", desc: "自注意力机制", icon: "mdi:eye-outline", color: "blue", hint: "SelfAttention：自注意力，让每个位置都能“关注”序列里其它位置，抓住长距离关系。" },
      { type: "VAE", desc: "变分自编码器", icon: "mdi:creation", color: "rose", hint: "VAE：变分自编码器，一种生成模型，能学习数据分布并生成新样本。" },
      { type: "GraphConv", desc: "图卷积层", icon: "mdi:graph", color: "emerald", hint: "GraphConv：图卷积，处理图结构数据（社交网络、分子等），在节点与邻居间传递信息。" },
    ],
  },
];

// 后端不可用时模板库的兜底列表（正常情况下由 /projects/templates 提供完整元数据）
export const fallbackTemplates: TemplateMeta[] = [
  { key: "linear", name: "Linear Classifier", description: "最简单的单层线性模型。", family: "feedforward" },
  { key: "mlp", name: "MLP", description: "多层感知机——最基础的神经网络。", family: "feedforward" },
  { key: "perceptron", name: "Perceptron", description: "感知机——神经网络的起点。", family: "feedforward" },
  { key: "lenet", name: "LeNet", description: "经典卷积网络，手写数字识别首选。", family: "cnn" },
  { key: "resnet", name: "ResNet Tiny", description: "带残差连接的小型 ResNet。", family: "cnn" },
  { key: "lstm", name: "LSTM", description: "循环网络，擅长处理序列数据。", family: "sequence" },
  { key: "seq2seq", name: "Seq2Seq", description: "序列到序列模型。", family: "sequence" },
  { key: "transformer", name: "Transformer", description: "Transformer 编码器。", family: "attention" },
  { key: "attention", name: "Attention", description: "自注意力机制。", family: "attention" },
  { key: "vae", name: "VAE", description: "变分自编码器。", family: "generative" },
  { key: "gcn", name: "GCN", description: "图卷积网络。", family: "graph" },
];

export type ValidationStatus = "unvalidated" | "passing" | "failed";
export type NodeBadgeState = "none" | "passed" | "pending";

// 一个独立画布：模型图、选中态、校验态、训练任务、导出结果、视口都相互隔离，
// 使各画布可以并行进行结构检查 / 保存 / 导出 / 训练。
// 异步操作在发起时捕获画布引用，完成时把结果写回原画布（即使用户已切换标签页）。
export interface WorkCanvas {
  id: number;
  name: string;
  // 模型图
  nodes: GraphNode[];
  connections: Connection[];
  edgeControls: Record<string, Point>;
  nodeCounters: Record<string, number>;
  // 选中态
  selectedNodeId: string | null;
  selectedConnectionKey: string | null;
  // 结构校验（结果通过 toast 弹窗提示）
  validationStatus: ValidationStatus;
  nodeBadge: NodeBadgeState;
  // 校验失败时每个出错节点的人话提示（nodeId → 说明），用于在画布上标红定位
  nodeErrors: Record<string, string>;
  inFeatures: number;
  validating: boolean;
  // 训练任务
  epochs: number;
  trainStarting: boolean;
  trainingJob: TrainingJob | null;
  jobId: string | null;
  // 代码导出
  lastExportCode: string;
  exportCodeDisplay: string;
  // 视口
  zoom: number;
  panX: number;
  panY: number;
  hasCenteredInitialGraph: boolean;
}

export function createCanvas(
  id: number,
  name: string,
  nodes: GraphNode[] = [],
  connections: Connection[] = []
): WorkCanvas {
  return {
    id,
    name,
    nodes,
    connections,
    edgeControls: {},
    nodeCounters: {},
    selectedNodeId: null,
    selectedConnectionKey: null,
    validationStatus: "unvalidated",
    nodeBadge: "none",
    nodeErrors: {},
    inFeatures: 1024,
    validating: false,
    epochs: 1,
    trainStarting: false,
    trainingJob: null,
    jobId: null,
    lastExportCode: "",
    exportCodeDisplay: "点击“导出代码”后会从后端生成 PyTorch 代码。",
    zoom: 1,
    panX: 0,
    panY: 0,
    // 新建的空画布无需初始居中；带初始示例图的画布需要
    hasCenteredInitialGraph: nodes.length === 0,
  };
}

export const store = reactive({
  dataset: "MNIST",
  // 训练设备（cpu / cuda），由顶栏设备选择器切换；GPU 可用性来自后端 /devices
  device: "cpu",
  cudaAvailable: false,
  // 多画布：标签页切换，至少保留一个。初始进入为空白画布（不预置示例模型，
  // 需要示例可用顶部「快速开始模板」加载）
  canvases: [createCanvas(1, "画布 1")] as WorkCanvas[],
  activeCanvasId: 1,
  canvasSeq: 1,
  // 以下为全局交互状态（只作用于当前激活画布的瞬时操作）
  isConnecting: false,
  // 从节点端口"拖拽"连线（区别于右键菜单的点击式连线）
  connectingByDrag: false,
  connectSourceId: null as string | null,
  connectTargetId: null as string | null,
  menuConnection: null as Connection | null,
  menuNodeId: null as string | null,
  connectionMenu: { visible: false, x: 0, y: 0 },
  nodeMenu: { visible: false, x: 0, y: 0 },
  suppressNextClick: false,
  draggingNodeId: null as string | null,
  draggingEdgeControlKey: null as string | null,
});

export function activeCanvas(): WorkCanvas {
  return store.canvases.find(canvas => canvas.id === store.activeCanvasId) ?? store.canvases[0]!;
}

// 模板库（从后端 /projects/templates 拉取，失败时用兜底列表）
export const templateLibrary = reactive<{ items: TemplateMeta[] }>({ items: [...fallbackTemplates] });

// —————————————————————————————————————————————
// 本机训练 Agent 状态（分布式训练：训练在用户本机执行）
// —————————————————————————————————————————————

export const agent = reactive({
  online: false,
  agentId: "",
  runtimeVersion: "",
  platform: "",
  deviceSummary: null as DeviceSummary | null,
});

export function setAgentStatus(status: AgentStatus) {
  agent.online = Boolean(status.online);
  agent.agentId = status.agent_id || "";
  agent.runtimeVersion = status.runtime_version || "";
  agent.platform = status.platform || "";
  agent.deviceSummary = status.device_summary || null;

  // 设备可用性来自本机 Agent 上报的设备信息（离线时回落到 CPU）
  store.cudaAvailable = Boolean(status.device_summary?.cuda_available);
  if (!store.cudaAvailable && store.device !== "cpu") {
    store.device = "cpu";
  }
  if (status.device_summary?.default_device && agent.online) {
    store.device = status.device_summary.default_device;
  }
}

// —————————————————————————————————————————————
// 存储位置设置（数据集下载 / 训练产物保存，持久化到 localStorage）
// —————————————————————————————————————————————

const STORAGE_PATHS_KEY = "model-workshop-storage-paths";

export const storagePaths = reactive({
  // 留空表示使用后端默认位置
  dataDir: "",
  artifactsDir: "",
});

try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_PATHS_KEY) || "{}");
  if (typeof saved.dataDir === "string") storagePaths.dataDir = saved.dataDir;
  if (typeof saved.artifactsDir === "string") storagePaths.artifactsDir = saved.artifactsDir;
} catch {
  // localStorage 不可用或数据损坏时使用默认值
}

export function saveStoragePaths(dataDir: string, artifactsDir: string) {
  storagePaths.dataDir = dataDir.trim();
  storagePaths.artifactsDir = artifactsDir.trim();
  try {
    localStorage.setItem(
      STORAGE_PATHS_KEY,
      JSON.stringify({ dataDir: storagePaths.dataDir, artifactsDir: storagePaths.artifactsDir })
    );
  } catch {
    // ignore
  }
}

// 新画布名称取最小未占用编号：关闭"画布 2"后再新建，名称仍为"画布 2"。
// （内部 id 由 canvasSeq 单调递增保证唯一，与显示名称无关）
export function nextCanvasName(): string {
  const names = new Set(store.canvases.map(canvas => canvas.name));
  let n = 1;
  while (names.has(`画布 ${n}`)) n += 1;
  return `画布 ${n}`;
}

// UI 开关（弹窗、面板收起状态）
export const ui = reactive({
  helpModalOpen: false,
  exportModalOpen: false,
  // 快速开始模板库弹窗
  templateGalleryOpen: false,
  // 存储位置设置弹窗
  storageSettingsOpen: false,
  // 本机训练 Agent 指引弹窗（如何启动本地 Agent）
  agentModalOpen: false,
  // 保存模型弹窗
  saveModalOpen: false,
  // 我的项目（加载已保存模型）弹窗
  projectsModalOpen: false,
  // 左侧组件库收起
  sidebarCollapsed: false,
  // 右侧参数面板被用户手动收起（点击节点卡片时自动重新展开）
  inspectorCollapsed: false,
});


// —————————————————————————————————————————————
// Toast
// —————————————————————————————————————————————

export const toasts = reactive<Toast[]>([]);
let toastSeq = 0;

export function showToast(type: ToastType, message: string) {
  toasts.push({ id: ++toastSeq, type, message, leaving: false });
  const toast = toasts[toasts.length - 1]!;

  setTimeout(() => {
    toast.leaving = true;
    setTimeout(() => {
      const index = toasts.indexOf(toast);
      if (index >= 0) toasts.splice(index, 1);
    }, 450);
  }, 3200);
}


// —————————————————————————————————————————————
// 新手引导
// —————————————————————————————————————————————

export function initializeBeginnerGuide() {
  try {
    // 第一次访问时自动打开新手指南
    if (!localStorage.getItem(GUIDE_VISITED_KEY)) {
      ui.helpModalOpen = true;
    }
  } catch {
    // localStorage 不可用时静默降级
  }
}

export function openHelpModal() {
  ui.helpModalOpen = true;
}

export function closeHelpModal() {
  ui.helpModalOpen = false;
  try {
    localStorage.setItem(GUIDE_VISITED_KEY, "1");
  } catch {
    // ignore
  }
}


// —————————————————————————————————————————————
// 图结构工具
// —————————————————————————————————————————————

export function getConnectionKey(from: string, to: string) {
  return `${from}->${to}`;
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

interface LayerConfig {
  type: string;
  title: string;
  badge: string;
  color: string;
  note?: string;
  hint?: string;
  params: Record<string, unknown>;
}

const LAYER_CONFIGS: Record<string, LayerConfig> = {
  Input: {
    type: "Input",
    title: "Input",
    badge: "Input",
    color: "emerald",
    hint: "28x28x1",
    params: { shape: [1, 28, 28] },
  },
  Output: {
    type: "Output",
    title: "Output",
    badge: "Output",
    color: "rose",
    params: {},
  },
  Add: {
    type: "Add",
    title: "Add",
    badge: "Add",
    color: "cyan",
    note: "merge=add",
    params: {},
  },
  Conv2D: {
    type: "Conv2D",
    title: "Conv2D",
    badge: "Conv2D",
    color: "blue",
    note: "out=16, k=3, s=1, p=0",
    params: { out_channels: 16, kernel_size: 3, stride: 1, padding: 0 },
  },
  MaxPooling: {
    type: "Pooling",
    title: "MaxPooling",
    badge: "MaxPool",
    color: "purple",
    note: "k=2, s=2",
    params: { kernel_size: 2, stride: 2, padding: 0 },
  },
  ReLU: {
    type: "ReLU",
    title: "ReLU",
    badge: "ReLU",
    color: "orange",
    params: {},
  },
  Flatten: {
    type: "Flatten",
    title: "Flatten",
    badge: "Flatten",
    color: "indigo",
    params: {},
  },
  Linear: {
    type: "Linear",
    title: "Linear",
    badge: "Linear",
    color: "cyan",
    note: "out=128",
    params: { out_features: 128 },
  },
  Dropout: {
    type: "Dropout",
    title: "Dropout",
    badge: "Dropout",
    color: "amber",
    note: "p=0.5",
    params: { p: 0.5 },
  },
  LSTM: {
    type: "LSTM",
    title: "LSTM",
    badge: "LSTM",
    color: "cyan",
    params: { hidden_size: 32, num_layers: 1, return_sequences: false, bidirectional: false },
  },
  Seq2Seq: {
    type: "Seq2Seq",
    title: "Seq2Seq",
    badge: "Seq2Seq",
    color: "indigo",
    params: { hidden_size: 32, output_size: 12, target_length: 6, num_layers: 1 },
  },
  TransformerEncoder: {
    type: "TransformerEncoder",
    title: "Transformer",
    badge: "Transformer",
    color: "purple",
    params: { d_model: 32, num_heads: 4, num_layers: 1, dim_feedforward: 64, dropout: 0.1 },
  },
  SelfAttention: {
    type: "SelfAttention",
    title: "Self Attention",
    badge: "Attention",
    color: "blue",
    params: { embed_dim: 32, num_heads: 4, dropout: 0 },
  },
  VAE: {
    type: "VAE",
    title: "VAE",
    badge: "VAE",
    color: "rose",
    params: { latent_dim: 32, output_features: 784 },
  },
  GraphConv: {
    type: "GraphConv",
    title: "GraphConv",
    badge: "GCN",
    color: "emerald",
    params: { out_features: 32 },
  },
};

// 判断是否是组件库/模板中的已知层类型。
// 画布 drop 时必须先校验：浏览器拖入的选中文本等任意内容也会触发 drop，
// 不校验会因 getLayerConfig 的 Linear 兜底而凭空添加节点。
export function isKnownLayerType(layerType: string): boolean {
  return Object.prototype.hasOwnProperty.call(LAYER_CONFIGS, layerType);
}

export function getLayerConfig(layerType: string): LayerConfig {
  return LAYER_CONFIGS[layerType] || LAYER_CONFIGS.Linear!;
}


export function resetValidationAfterGraphChange(canvas: WorkCanvas = activeCanvas()) {
  canvas.validationStatus = "unvalidated";
  canvas.nodeBadge = "none";
  canvas.nodeErrors = {};
}


export function updateNodeDisplay(node: GraphNode) {
  if (node.type === "Input" && Array.isArray(node.params.shape)) {
    node.hint = node.params.shape.join("x");
  }

  if (node.type === "Conv2D") {
    node.note = `out=${node.params.out_channels}, k=${node.params.kernel_size}, s=${node.params.stride}, p=${node.params.padding}`;
  }

  if (node.type === "Pooling") {
    node.note = `k=${node.params.kernel_size}, s=${node.params.stride}, p=${node.params.padding}`;
  }

  if (node.type === "Linear") {
    node.note = `out=${node.params.out_features}`;
  }

  if (node.type === "Dropout") {
    node.note = `p=${node.params.p}`;
  }

  // 序列与高级层：用参数摘要作为节点说明
  if (["LSTM", "Seq2Seq", "TransformerEncoder", "SelfAttention", "VAE", "GraphConv"].includes(node.type)) {
    node.note = formatLayerNote({ params: node.params });
  }
}


export function updateNodeParam(nodeId: string, key: string, value: unknown) {
  const canvas = activeCanvas();
  const node = canvas.nodes.find(item => item.id === nodeId);
  if (!node) return;

  node.params = {
    ...node.params,
    [key]: value,
  };

  updateNodeDisplay(node);
  resetValidationAfterGraphChange(canvas);
}


// 校验通过后为初始示例图的节点填充尺寸提示
export function updateShapeHints(canvas: WorkCanvas = activeCanvas()) {
  const hints: Record<string, string> = {
    conv: "26x26x16",
    pool: "13x13x16",
    flatten: "2704",
    linear: "128",
    output: "10",
  };

  Object.entries(hints).forEach(([id, value]) => {
    const node = canvas.nodes.find(item => item.id === id);
    if (node) {
      node.hint = value;
    }
  });
}


export function formatLayerNote(layer: { params?: Record<string, unknown> }) {
  const params = layer.params || {};
  const entries = Object.entries(params)
    .filter(([, value]) => typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => `${key}=${value}`);

  return entries.join(", ");
}


// —————————————————————————————————————————————
// 导出给后端的模型图（Add 节点折叠为 merge 参数）
// —————————————————————————————————————————————

function getExportParams(
  node: GraphNode,
  exportConnections: ModelGraphConnection[],
  addTargetIds: Set<string>
): Record<string, unknown> {
  const params = { ...node.params };
  delete params.merge;
  delete params.dim;
  delete params.concat_dim;

  const incomingCount = exportConnections.filter(connection => connection.target === node.id).length;
  if (incomingCount <= 1) {
    return params;
  }

  params.merge = addTargetIds.has(node.id) ? "add" : "concat";
  if (params.merge === "concat" && params.dim === undefined) {
    params.dim = 1;
  }

  return params;
}

function buildBackendModelGraph(canvas: WorkCanvas) {
  const addNodeIds = new Set(canvas.nodes.filter(node => node.type === "Add").map(node => node.id));
  const addTargetIds = new Set<string>();
  const exportConnections: ModelGraphConnection[] = [];
  const seenConnections = new Set<string>();

  function addExportConnection(source: string, target: string) {
    if (!source || !target || source === target) return;

    const key = `${source}->${target}`;
    if (seenConnections.has(key)) return;

    seenConnections.add(key);
    exportConnections.push({ source, target });
  }

  canvas.connections.forEach(([source, target]) => {
    if (!addNodeIds.has(source) && !addNodeIds.has(target)) {
      addExportConnection(source, target);
    }
  });

  addNodeIds.forEach(addNodeId => {
    const sources = canvas.connections
      .filter(([, target]) => target === addNodeId)
      .map(([source]) => source)
      .filter(source => !addNodeIds.has(source));
    const targets = canvas.connections
      .filter(([source]) => source === addNodeId)
      .map(([, target]) => target)
      .filter(target => !addNodeIds.has(target));

    targets.forEach(target => {
      addTargetIds.add(target);
      sources.forEach(source => addExportConnection(source, target));
    });
  });

  return {
    addTargetIds,
    connections: exportConnections,
  };
}

export function getCurrentModelGraph(canvas: WorkCanvas = activeCanvas()): ModelGraph {
  const backendGraph = buildBackendModelGraph(canvas);

  return {
    layers: canvas.nodes
      .filter(node => node.type !== "Add")
      .map(node => ({
        id: node.id,
        type: node.type,
        name: node.title,
        params: getExportParams(node, backendGraph.connections, backendGraph.addTargetIds),
      })),
    connections: backendGraph.connections,
  };
}


export function getTrainConfig(canvas: WorkCanvas = activeCanvas()): TrainConfig {
  return {
    dataset_name: store.dataset,
    // 训练轮次由用户在底部操作栏按画布设置
    epochs: canvas.epochs,
    batch_size: 64,
    rate: 0.001,
    // 训练设备由顶栏设备选择器决定
    device: store.device,
    loss_fn: "cross_entropy",
    optimizer: "sgd",
    // 存储位置设置（留空使用后端默认位置）
    data_dir: storagePaths.dataDir,
    artifacts_dir: storagePaths.artifactsDir,
  };
}


export function getTrainingLayers(canvas: WorkCanvas = activeCanvas()): MonitorLayer[] {
  return canvas.nodes
    .filter(node => node.type !== "Add")
    .map(node => ({
      type: node.badge || node.type,
      color: node.color || "cyan",
    }));
}


export function getTrainingStatusLabel(status: string | undefined) {
  return (
    {
      pending: "等待中",
      running: "训练中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    } as Record<string, string>
  )[status || ""] || "未知";
}


// 把训练任务状态写回它所属的画布（并行训练时各画布互不影响）
export function setTrainingJob(canvas: WorkCanvas, job: TrainingJob) {
  canvas.trainingJob = {
    ...(canvas.trainingJob || {}),
    ...job,
  };
  canvas.jobId = canvas.trainingJob.job_id || canvas.jobId;
}
