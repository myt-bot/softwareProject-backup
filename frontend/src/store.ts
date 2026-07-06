// 全局响应式状态与纯数据逻辑（不直接操作 DOM）。
// 画布交互（拖拽、连线、SVG 绘制等需要测量 DOM 的逻辑）在 canvas.ts。

import { reactive } from "vue";
import type {
  Connection,
  GraphNode,
  LayerGroup,
  ModelGraph,
  ModelGraphConnection,
  MonitorLayer,
  Point,
  Toast,
  ToastType,
  TrainConfig,
  TrainingJob,
} from "./types";

export const GUIDE_VISITED_KEY = "model-workshop-visited";
export const GUIDE_STRIP_HIDDEN_KEY = "model-workshop-guide-hidden";

export const datasetOptions: Record<string, { shapeLabel: string }> = {
  MNIST: { shapeLabel: "(1x28x28)" },
  FashionMNIST: { shapeLabel: "(1x28x28)" },
  KMNIST: { shapeLabel: "(1x28x28)" },
  CIFAR10: { shapeLabel: "(3x32x32)" },
  CIFAR100: { shapeLabel: "(3x32x32)" },
};

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
      { type: "Input", desc: "输入张量定义", icon: "mdi:login-variant", color: "emerald" },
      { type: "Output", desc: "分类输出节点", icon: "mdi:logout-variant", color: "rose" },
      { type: "Add", desc: "多分支逐元素相加", icon: "mdi:plus-circle-outline", color: "cyan" },
    ],
  },
  {
    title: "卷积与池化 / Conv & Pooling",
    layers: [
      { type: "Conv2D", desc: "特征提取卷积层", icon: "mdi:grid-large", color: "blue" },
      { type: "MaxPooling", desc: "下采样空间压缩", icon: "mdi:resize", color: "purple" },
      { type: "ReLU", desc: "非线性激活函数", icon: "mdi:vector-rectangle", color: "orange" },
    ],
  },
  {
    title: "全连接与正则 / Linear & Regular",
    layers: [
      { type: "Flatten", desc: "多维展平为一维", icon: "mdi:layers-triple", color: "indigo" },
      { type: "Linear", desc: "密集全连接层", icon: "mdi:ray-start-end", color: "cyan" },
      { type: "Dropout", desc: "随机失活防过拟合", icon: "mdi:filter-off-outline", color: "amber" },
    ],
  },
];

export const templateChoices = [
  { key: "linear", label: "Linear", title: "最简单的单层线性模型" },
  { key: "mlp", label: "MLP", title: "多层感知机——最基础的神经网络" },
  { key: "perceptron", label: "Perceptron", title: "感知机——神经网络的起点" },
  { key: "lenet", label: "LeNet", title: "经典卷积网络，手写数字识别首选" },
  { key: "resnet", label: "ResNet Tiny", title: "带残差连接的小型 ResNet" },
  { key: "lstm", label: "LSTM", title: "循环网络，擅长处理序列数据" },
  { key: "seq2seq", label: "Seq2Seq", title: "序列到序列模型" },
  { key: "transformer", label: "Transformer", title: "Transformer 编码器" },
  { key: "attention", label: "Attention", title: "自注意力机制" },
  { key: "vae", label: "VAE", title: "变分自编码器" },
  { key: "gcn", label: "GCN", title: "图卷积网络" },
];

const initialNodes: GraphNode[] = [
  {
    id: "input",
    type: "Input",
    title: "MNIST Input",
    badge: "Input",
    color: "emerald",
    hint: "28x28x1",
    x: 438,
    y: 60,
    params: { shape: [1, 28, 28] },
  },
  {
    id: "conv",
    type: "Conv2D",
    title: "Feature Extractor",
    badge: "Conv2D",
    color: "blue",
    note: "out=16, k=3, s=1, p=0",
    hint: "?",
    x: 438,
    y: 265,
    params: { out_channels: 16, kernel_size: 3, stride: 1, padding: 0 },
  },
  {
    id: "pool",
    type: "Pooling",
    title: "Dimension Reducer",
    badge: "MaxPool",
    color: "purple",
    note: "k=2, s=2",
    hint: "?",
    x: 438,
    y: 470,
    params: { kernel_size: 2, stride: 2, padding: 0 },
  },
  {
    id: "flatten",
    type: "Flatten",
    title: "Vectorize",
    badge: "Flatten",
    color: "indigo",
    hint: "?",
    x: 438,
    y: 675,
    params: {},
  },
  {
    id: "linear",
    type: "Linear",
    title: "Classifier FC",
    badge: "Linear",
    color: "cyan",
    note: "out=128, in=1024",
    hint: "?",
    x: 438,
    y: 880,
    params: { out_features: 128 },
  },
  {
    id: "output",
    type: "Output",
    title: "MNIST Classes",
    badge: "Output",
    color: "rose",
    hint: "?",
    x: 438,
    y: 1085,
    params: {},
  },
];

const initialConnections: Connection[] = [
  ["input", "conv"],
  ["conv", "pool"],
  ["pool", "flatten"],
  ["flatten", "linear"],
  ["linear", "output"],
];

export type ValidationStatus = "unvalidated" | "passing" | "failed";
export type NodeBadgeState = "none" | "passed" | "pending";

export interface ValidationSummary {
  visible: boolean;
  kind: "success" | "error" | "warning";
  icon: string;
  text: string;
}

export const store = reactive({
  dataset: "MNIST",
  nodes: initialNodes as GraphNode[],
  connections: initialConnections as Connection[],
  selectedNodeId: null as string | null,
  validationStatus: "unvalidated" as ValidationStatus,
  nodeBadge: "none" as NodeBadgeState,
  validationSummary: {
    visible: false,
    kind: "warning",
    icon: "mdi:alert-circle",
    text: "尚未检查",
  } as ValidationSummary,
  inFeatures: 1024,
  jobId: null as string | null,
  lastExportCode: "",
  exportCodeDisplay: "点击“导出代码”后会从后端生成 PyTorch 代码。",
  trainingJob: null as TrainingJob | null,
  isConnecting: false,
  connectSourceId: null as string | null,
  connectTargetId: null as string | null,
  menuConnection: null as Connection | null,
  menuNodeId: null as string | null,
  connectionMenu: { visible: false, x: 0, y: 0 },
  nodeMenu: { visible: false, x: 0, y: 0 },
  selectedConnectionKey: null as string | null,
  edgeControls: {} as Record<string, Point>,
  nodeCounters: {} as Record<string, number>,
  zoom: 1,
  hasCenteredInitialGraph: false,
  suppressNextClick: false,
  draggingNodeId: null as string | null,
  draggingEdgeControlKey: null as string | null,
});

// UI 开关（弹窗、引导条）
export const ui = reactive({
  helpModalOpen: false,
  guideStripHidden: false,
  exportModalOpen: false,
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
    if (localStorage.getItem(GUIDE_STRIP_HIDDEN_KEY)) {
      ui.guideStripHidden = true;
    }
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

export function dismissGuideStrip() {
  ui.guideStripHidden = true;
  try {
    localStorage.setItem(GUIDE_STRIP_HIDDEN_KEY, "1");
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
    params: { hidden_size: 32, num_layers: 1, return_sequences: false },
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


export function resetValidationAfterGraphChange() {
  store.validationStatus = "unvalidated";
  store.nodeBadge = "none";
  store.validationSummary.visible = false;
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
}


export function updateNodeParam(nodeId: string, key: string, value: unknown) {
  const node = store.nodes.find(item => item.id === nodeId);
  if (!node) return;

  node.params = {
    ...node.params,
    [key]: value,
  };

  updateNodeDisplay(node);
  resetValidationAfterGraphChange();
}


// 校验通过后为初始示例图的节点填充尺寸提示
export function updateShapeHints() {
  const hints: Record<string, string> = {
    conv: "26x26x16",
    pool: "13x13x16",
    flatten: "2704",
    linear: "128",
    output: "10",
  };

  Object.entries(hints).forEach(([id, value]) => {
    const node = store.nodes.find(item => item.id === id);
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

function buildBackendModelGraph() {
  const addNodeIds = new Set(store.nodes.filter(node => node.type === "Add").map(node => node.id));
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

  store.connections.forEach(([source, target]) => {
    if (!addNodeIds.has(source) && !addNodeIds.has(target)) {
      addExportConnection(source, target);
    }
  });

  addNodeIds.forEach(addNodeId => {
    const sources = store.connections
      .filter(([, target]) => target === addNodeId)
      .map(([source]) => source)
      .filter(source => !addNodeIds.has(source));
    const targets = store.connections
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

export function getCurrentModelGraph(): ModelGraph {
  const backendGraph = buildBackendModelGraph();

  return {
    layers: store.nodes
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


export function getTrainConfig(): TrainConfig {
  return {
    dataset_name: store.dataset,
    epochs: 1,
    batch_size: 64,
    rate: 0.001,
    device: "cpu",
    loss_fn: "cross_entropy",
    optimizer: "sgd",
  };
}


export function getTrainingLayers(): MonitorLayer[] {
  return store.nodes
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


export function setTrainingJob(job: TrainingJob) {
  store.trainingJob = {
    ...(store.trainingJob || {}),
    ...job,
  };
  store.jobId = store.trainingJob.job_id || store.jobId;
}
