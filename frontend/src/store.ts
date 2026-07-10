// 全局响应式状态与纯数据逻辑（不直接操作 DOM）。
// 画布交互（拖拽、连线、SVG 绘制等需要测量 DOM 的逻辑）在 canvas.ts。

import { reactive } from "vue";
import type {
  AgentStatus,
  Connection,
  ContainerDef,
  DeviceSummary,
  GraphNode,
  LayerGroup,
  LayerShapeInfo,
  ModelGraph,
  ModelGraphConnection,
  ModelGraphLayer,
  MonitorLayer,
  Point,
  SubGraph,
  TemplateMeta,
  Toast,
  ToastType,
  TrainConfig,
  TrainingJob,
  TrainingModelSummary,
} from "./types";

// 自定义容器节点的类型标识（与后端 graph_utils.CONTAINER_TYPE 对应）
export const CONTAINER_TYPE = "Container";
// 展平后内部层层级 id 分隔符（与后端 graph_utils.CONTAINER_ID_SEP 保持一致，
// 前端据此把 /validate 返回的内部层 shape 映射回容器子图各节点）
export const CONTAINER_ID_SEP = "__";
// 主画布连线里"容器端口"端点的分隔符：容器id::内部端口层id（与后端 graph_utils.PORT_SEP 一致）
export const PORT_SEP = "::";

// 连线端点工具：拆出基节点 id / 端口 id
export function endpointBaseId(endpoint: string): string {
  const index = endpoint.indexOf(PORT_SEP);
  return index === -1 ? endpoint : endpoint.slice(0, index);
}
export function endpointPortId(endpoint: string): string | null {
  const index = endpoint.indexOf(PORT_SEP);
  return index === -1 ? null : endpoint.slice(index + PORT_SEP.length);
}
export function makePortEndpoint(containerId: string, portId: string): string {
  return `${containerId}${PORT_SEP}${portId}`;
}

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
      { type: "Input", desc: "输入张量定义", icon: "mdi:login-variant", color: "emerald", hint: "模型的入口。在这里声明输入数据的形状（通道数、高、宽），后续每一层都据此推导自己的输出尺寸。任何模型都必须从它开始，一张图里通常只有一个入口。" },
      { type: "Output", desc: "分类输出节点", icon: "mdi:logout-variant", color: "rose", hint: "模型的出口，标记整张网络最终结果的汇聚位置。数据流经所有层后在这里输出，训练时以此处的输出与标准答案比对来计算误差。每个模型都以它结尾。" },
      { type: "Add", desc: "多分支逐元素相加", icon: "mdi:plus-circle-outline", color: "cyan", hint: "把两条或多条分支的输出按相同位置逐元素相加，合并成一条继续往下传。要求参与相加的分支形状完全一致，常用来搭建跳跃连接，让较深的网络更容易训练。" },
    ],
  },
  {
    title: "卷积与池化 / Conv & Pooling",
    layers: [
      { type: "Conv2D", desc: "特征提取卷积层", icon: "mdi:grid-large", color: "blue", hint: "卷积层。用一组可学习的小窗口在输入上滑动扫描，逐块提取局部特征（边缘、纹理等），并输出多张特征图。是处理图像等网格状数据最核心的层，输出通道越多，能表达的特征越丰富。" },
      { type: "MaxPooling", desc: "下采样空间压缩", icon: "mdi:resize", color: "purple", hint: "池化层。在每个小窗口内只取最大值，从而按比例缩小特征图的尺寸。它能减少计算量、扩大后续层的观察范围，并在一定程度上抑制过拟合，通常紧跟在卷积层之后。" },
      { type: "ReLU", desc: "非线性激活函数", icon: "mdi:vector-rectangle", color: "orange", hint: "激活函数，为网络引入非线性：把小于 0 的值置为 0，其余原样保留。没有它，再多层堆叠也只等价于一层线性变换。通常加在卷积层或全连接层之后，几乎每层都会用到。" },
    ],
  },
  {
    title: "全连接与正则 / Linear & Regular",
    layers: [
      { type: "Flatten", desc: "多维展平为一维", icon: "mdi:layers-triple", color: "indigo", hint: "把多维特征图按顺序摊平成一条一维向量，让数据能进入全连接层。它只改变数据的排列形状、不改变具体数值，一般放在卷积部分结束、全连接部分开始之前。" },
      { type: "Linear", desc: "密集全连接层", icon: "mdi:ray-start-end", color: "cyan", hint: "全连接层。把输入的每一个数与输出的每一个数之间都建立可学习的加权连接，实现特征的整体重组。常用于网络末端做汇总与分类，输出维度决定这一层给出多少个数。" },
      { type: "Dropout", desc: "随机失活防过拟合", icon: "mdi:filter-off-outline", color: "amber", hint: "一种正则化手段。训练时按设定概率随机把一部分神经元临时置零，迫使网络不过度依赖某几个神经元，从而缓解过拟合；推理时会自动关闭。丢弃比例越大，正则化越强。" },
    ],
  },
  {
    title: "序列与高级 / Sequence & Advanced",
    layers: [
      { type: "LSTM", desc: "循环网络处理序列", icon: "mdi:repeat", color: "cyan", hint: "一种循环网络。按先后顺序逐步读入序列，并用内部的记忆单元保留较早的信息，缓解普通循环网络难以记住长距离依赖的问题。适合处理有前后顺序关系的数据。" },
      { type: "Seq2Seq", desc: "序列到序列生成", icon: "mdi:swap-horizontal", color: "indigo", hint: "编码器-解码器结构。先由编码器把输入序列压缩成一个中间表示，再由解码器据此逐步生成另一段序列。适用于输入与输出都是序列、且两者长度可以不同的任务。" },
      { type: "TransformerEncoder", desc: "自注意力编码器", icon: "mdi:layers-outline", color: "purple", hint: "基于自注意力的编码器模块。让序列中每个位置都能参考其余所有位置来更新自身表示，可并行计算并捕捉长距离关系，是许多现代大型模型的基础构件。" },
      { type: "SelfAttention", desc: "自注意力机制", icon: "mdi:eye-outline", color: "blue", hint: "自注意力机制。为序列中每个位置计算它与其余位置的关联权重，再据此加权聚合信息，从而在任意两个位置之间直接建立联系，擅长捕捉长距离依赖关系。" },
      { type: "VAE", desc: "变分自编码器", icon: "mdi:creation", color: "rose", hint: "一类生成模型。编码器把输入映射到一个带概率分布的隐空间，解码器再从隐空间把数据重建出来；训练完成后，可从隐空间采样，生成与训练数据风格相近的新样本。" },
      { type: "GraphConv", desc: "图卷积层", icon: "mdi:graph", color: "emerald", hint: "图卷积层，面向以节点和边描述的图结构数据。它在每个节点上聚合来自邻居节点的特征来更新自身表示，从而让信息沿着连接关系在图上传播。" },
    ],
  },
];

// 后端不可用时模板库的兜底列表（正常情况下由 /projects/templates 提供完整元数据）
export const fallbackTemplates: TemplateMeta[] = [
  { key: "linear", name: "Linear Classifier", description: "最简单的单层线性模型。", family: "feedforward" },
  { key: "mlp", name: "MLP", description: "多层感知机——最基础的神经网络。", family: "feedforward" },
  { key: "perceptron", name: "Perceptron", description: "感知机——神经网络的起点。", family: "feedforward" },
  { key: "lenet", name: "LeNet", description: "结构清晰的经典小型卷积网络，适合入门理解卷积网络。", family: "cnn" },
  { key: "resnet", name: "ResNet Tiny", description: "带残差连接的小型卷积网络，层数更深也更易训练。", family: "cnn" },
  { key: "lstm", name: "LSTM", description: "循环网络，擅长处理有先后顺序的序列数据。", family: "sequence" },
  { key: "seq2seq", name: "Seq2Seq", description: "序列到序列模型。", family: "sequence" },
  { key: "transformer", name: "Transformer", description: "Transformer 编码器。", family: "attention" },
  { key: "attention", name: "Attention", description: "自注意力机制。", family: "attention" },
  { key: "vae", name: "VAE", description: "变分自编码器。", family: "generative" },
  { key: "gcn", name: "GCN", description: "图卷积网络。", family: "graph" },
];

export type ValidationStatus = "unvalidated" | "passing" | "failed";
export type NodeBadgeState = "none" | "passed" | "pending";
export type ExportCodeFormat = "py" | "ipynb";

// 进入容器子画板编辑时压栈的"父层"快照：退出时用它还原画布，并把编辑好的
// 子图写回对应容器节点。
export interface EditFrame {
  containerId: string;
  containerName: string;
  nodes: GraphNode[];
  connections: Connection[];
  edgeControls: Record<string, Point>;
  nodeCounters: Record<string, number>;
  selectedNodeId: string | null;
  selectedConnectionKey: string | null;
  validationStatus: ValidationStatus;
  nodeBadge: NodeBadgeState;
  nodeErrors: Record<string, string>;
  inFeatures: number;
  zoom: number;
  panX: number;
  panY: number;
  hasCenteredInitialGraph: boolean;
}

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
  // 容器子画板编辑：进入容器时把父层图压栈，画布字段换成容器子图；退出时还原
  editStack: EditFrame[];
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
  exportFormat: ExportCodeFormat;
  exportFilename: string;
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
    editStack: [],
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
    exportFormat: "py",
    exportFilename: "GeneratedModel.py",
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
  // 训练超参数（在「训练超参数」弹窗中修改；epochs 仍按画布单独保存）
  batchSize: 64,
  learningRate: 0.001,
  optimizer: "sgd",
  lossFn: "cross_entropy",
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
  // 训练超参数弹窗（批大小 / 学习率 / 优化器 / 损失函数）
  trainSettingsOpen: false,
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

  // 自定义容器：用内部层数量（不含端口）作为节点说明
  if (node.type === CONTAINER_TYPE && node.subgraph) {
    node.note = `${containerLayerCount(node)} 层`;
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


function formatShapeHint(shape: number[] | null | undefined) {
  if (!Array.isArray(shape) || shape.length === 0) return null;

  // 后端图像 shape 约定为 [C, H, W]；节点卡片延续界面中的 H×W×C 展示习惯。
  if (shape.length === 3 && shape.every(dimension => typeof dimension === "number")) {
    return `${shape[1]}x${shape[2]}x${shape[0]}`;
  }

  return shape.join("x");
}


// 校验通过后用后端推导出的真实尺寸填充节点提示；旧示例图保留兜底值。
// 含容器时按层级 id（容器id__内部层id）回查：容器卡片显示 输入→输出，
// 展开视图里每个内部层显示各自的输出尺寸。
export function updateShapeHints(canvas: WorkCanvas = activeCanvas(), shapes?: Record<string, LayerShapeInfo>) {
  if (shapes && Object.keys(shapes).length > 0) {
    applyShapeHintsToNodes(canvas.nodes, shapes, "");
    return;
  }

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


// 按层级前缀递归回填 shape：普通层取自身 output；容器下钻内部层（含 Input/Output
// 端口节点），端口节点的 hint 即各端口尺寸，供画布卡片在每个端口锚点旁显示。
function applyShapeHintsToNodes(
  nodes: GraphNode[],
  shapes: Record<string, LayerShapeInfo>,
  prefix: string
) {
  nodes.forEach(node => {
    const flatId = prefix + node.id;
    if (node.type === CONTAINER_TYPE && node.subgraph) {
      const innerPrefix = `${flatId}${CONTAINER_ID_SEP}`;
      // 容器整体输出摘要 = 第一个 Output 端口的输出
      const firstOutput = node.subgraph.nodes.find(inner => inner.type === "Output");
      const outputHint = firstOutput
        ? formatShapeHint(shapes[`${innerPrefix}${firstOutput.id}`]?.output_shape)
        : null;
      if (outputHint) node.hint = outputHint;
      applyShapeHintsToNodes(node.subgraph.nodes, shapes, innerPrefix);
    } else {
      const hint = formatShapeHint(shapes[flatId]?.output_shape);
      if (hint) {
        node.hint = hint;
      }
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
// 自定义容器（组合容器）：空白容器 / 子画板端口 / 会话内可复用库
// —————————————————————————————————————————————

// 会话内可复用容器库（组件库底部"我的容器"来源；跨设备持久化为后续里程碑）
export const containerLibrary = reactive<{ items: ContainerDef[] }>({ items: [] });
let containerDefSeq = 0;

// 新建空容器时子图里预置的入口示例形状
const DEFAULT_CONTAINER_INPUT_SHAPE = [1, 28, 28];

export function cloneSubgraph(subgraph: SubGraph): SubGraph {
  return {
    nodes: subgraph.nodes.map(node => ({
      ...node,
      params: { ...node.params },
      subgraph: node.subgraph ? cloneSubgraph(node.subgraph) : undefined,
    })),
    connections: subgraph.connections.map(connection => [...connection] as Connection),
    inputs: [...subgraph.inputs],
    outputs: [...subgraph.outputs],
    nodeCounters: { ...(subgraph.nodeCounters || {}) },
  };
}

// 容器的输入/输出端口 = 子图里的 Input / Output 节点（按数组顺序，多个即多输入/多输出）
export function containerInputPorts(node: GraphNode): GraphNode[] {
  return node.subgraph ? node.subgraph.nodes.filter(inner => inner.type === "Input") : [];
}
export function containerOutputPorts(node: GraphNode): GraphNode[] {
  return node.subgraph ? node.subgraph.nodes.filter(inner => inner.type === "Output") : [];
}

// 容器内部“真正的层数”（不含 Input/Output 端口）
export function containerLayerCount(node: GraphNode): number {
  if (!node.subgraph) return 0;
  return node.subgraph.nodes.filter(inner => inner.type !== "Input" && inner.type !== "Output").length;
}

// 从一组节点推导节点计数器（进入子画板编辑时避免新增节点 id 冲突）
export function deriveNodeCounters(nodes: GraphNode[]): Record<string, number> {
  const counters: Record<string, number> = {};
  nodes.forEach(node => {
    const match = /_(\d+)$/.exec(node.id);
    const n = match ? Number(match[1]) : 0;
    counters[node.type] = Math.max(counters[node.type] || 0, n);
  });
  return counters;
}

// 把编辑好的子画板（节点+连线）打包回一个 SubGraph（端口 = Input/Output 节点）
export function subgraphFromCanvas(
  nodes: GraphNode[],
  connections: Connection[],
  nodeCounters: Record<string, number>
): SubGraph {
  return {
    nodes: nodes.map(node => ({ ...node })),
    connections: connections.map(connection => [...connection] as Connection),
    inputs: nodes.filter(node => node.type === "Input").map(node => node.id),
    outputs: nodes.filter(node => node.type === "Output").map(node => node.id),
    nodeCounters: { ...nodeCounters },
  };
}

// 从组件库拖入的“空白容器”：预置一个 Input 和一个 Output 端口，等待双击进入编辑
export function createEmptyContainerNode(canvas: WorkCanvas, x: number, y: number): GraphNode {
  canvas.nodeCounters[CONTAINER_TYPE] = (canvas.nodeCounters[CONTAINER_TYPE] || 0) + 1;
  const containerId = `container_${canvas.nodeCounters[CONTAINER_TYPE]}`;

  const inputNode: GraphNode = {
    id: "input_1", type: "Input", title: "Input", badge: "Input", color: "emerald",
    hint: DEFAULT_CONTAINER_INPUT_SHAPE.join("x"),
    x: 96, y: 48, params: { shape: [...DEFAULT_CONTAINER_INPUT_SHAPE] },
  };
  const outputNode: GraphNode = {
    id: "output_1", type: "Output", title: "Output", badge: "Output", color: "rose",
    hint: "?", x: 96, y: 320, params: {},
  };
  const subgraph: SubGraph = {
    nodes: [inputNode, outputNode],
    connections: [],
    inputs: ["input_1"],
    outputs: ["output_1"],
    nodeCounters: { Input: 1, Output: 1 },
  };

  return {
    id: containerId, type: CONTAINER_TYPE, title: "Container", badge: "容器", color: "teal",
    note: "空容器 · 双击编辑", hint: "?", x, y, params: {}, collapsed: true, subgraph,
  };
}

// 把容器存入会话内可复用库
export function saveContainerToLibrary(container: GraphNode, name: string): ContainerDef | null {
  if (container.type !== CONTAINER_TYPE || !container.subgraph) return null;
  containerDefSeq += 1;
  const def: ContainerDef = {
    defId: `cdef_${containerDefSeq}`,
    name: name.trim() || container.title || "Container",
    color: container.color || "teal",
    subgraph: cloneSubgraph(container.subgraph),
  };
  containerLibrary.items.push(def);
  return def;
}

// 从库定义实例化一个容器节点（内部 id 沿用定义，靠容器 id 前缀保证展平后唯一）
export function instantiateContainerDef(canvas: WorkCanvas, def: ContainerDef, x: number, y: number): GraphNode {
  canvas.nodeCounters[CONTAINER_TYPE] = (canvas.nodeCounters[CONTAINER_TYPE] || 0) + 1;
  const containerId = `container_${canvas.nodeCounters[CONTAINER_TYPE]}`;
  const subgraph = cloneSubgraph(def.subgraph);
  const node: GraphNode = {
    id: containerId, type: CONTAINER_TYPE, title: def.name, badge: "容器", color: def.color,
    note: "", hint: "?", x, y, params: {}, collapsed: true, subgraph,
  };
  node.note = `${containerLayerCount(node)} 层`;
  return node;
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

function buildBackendModelGraph(nodes: GraphNode[], connections: Connection[]) {
  const addNodeIds = new Set(nodes.filter(node => node.type === "Add").map(node => node.id));
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

  connections.forEach(([source, target]) => {
    if (!addNodeIds.has(source) && !addNodeIds.has(target)) {
      addExportConnection(source, target);
    }
  });

  addNodeIds.forEach(addNodeId => {
    const sources = connections
      .filter(([, target]) => target === addNodeId)
      .map(([source]) => source)
      .filter(source => !addNodeIds.has(source));
    const targets = connections
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

// 把一组节点 + 连线序列化为后端模型图（Add 折叠为 merge 参数）。
// 遇到自定义容器时递归序列化其内部子图，端口 inputs/outputs 取子图里的
// Input/Output 节点 id（后端展平时把它们变为 Identity 直通端口）。
function serializeGraph(nodes: GraphNode[], connections: Connection[]): {
  layers: ModelGraphLayer[];
  connections: ModelGraphConnection[];
} {
  const backendGraph = buildBackendModelGraph(nodes, connections);

  const layers: ModelGraphLayer[] = nodes
    .filter(node => node.type !== "Add")
    .map(node => {
      const layer: ModelGraphLayer = {
        id: node.id,
        type: node.type,
        name: node.title,
        params: getExportParams(node, backendGraph.connections, backendGraph.addTargetIds),
      };

      if (node.type === CONTAINER_TYPE && node.subgraph) {
        const sub = serializeGraph(node.subgraph.nodes, node.subgraph.connections);
        layer.subgraph = {
          layers: sub.layers,
          connections: sub.connections,
          inputs: node.subgraph.nodes.filter(inner => inner.type === "Input").map(inner => inner.id),
          outputs: node.subgraph.nodes.filter(inner => inner.type === "Output").map(inner => inner.id),
        };
      }

      return layer;
    });

  return { layers, connections: backendGraph.connections };
}

export function getCurrentModelGraph(canvas: WorkCanvas = activeCanvas()): ModelGraph {
  const serialized = serializeGraph(canvas.nodes, canvas.connections);

  return {
    layers: serialized.layers,
    connections: serialized.connections,
    train_config: getTrainConfig(canvas),
  };
}


export function getTrainConfig(canvas: WorkCanvas = activeCanvas()): TrainConfig {
  return {
    dataset_name: store.dataset,
    // 训练轮次由用户在底部操作栏按画布设置
    epochs: canvas.epochs,
    // 以下超参数由「训练超参数」弹窗设置
    batch_size: store.batchSize,
    rate: store.learningRate,
    // 训练设备由顶栏设备选择器决定
    device: store.device,
    loss_fn: store.lossFn,
    optimizer: store.optimizer,
    // 存储位置设置（留空使用后端默认位置）
    data_dir: storagePaths.dataDir,
    artifacts_dir: storagePaths.artifactsDir,
  };
}


export function getTrainingLayers(canvas: WorkCanvas = activeCanvas()): MonitorLayer[] {
  return canvas.nodes
    .filter(node => node.type !== "Add")
    .map(node => ({
      id: node.id,
      type: node.badge || node.type,
      color: node.color || "cyan",
    }));
}


export function getTrainingSummary(canvas: WorkCanvas = activeCanvas()): TrainingModelSummary {
  const inputNode = canvas.nodes.find(node => node.type === "Input");
  const inputShape = numericShape(inputNode?.params.shape);

  return {
    modelName: canvas.name,
    inputShape,
    numClasses: inferNumClasses(canvas),
    paramCount: countModelParams(canvas, inputShape),
  };
}


function inferNumClasses(canvas: WorkCanvas): number | null {
  const outputIds = new Set(canvas.nodes.filter(node => node.type === "Output").map(node => node.id));
  const nodeMap = new Map(canvas.nodes.map(node => [node.id, node]));
  const visited = new Set<string>();
  const queue = canvas.connections
    .filter(([, target]) => outputIds.has(endpointBaseId(target)))
    .map(([source]) => endpointBaseId(source));

  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    if (visited.has(nodeId)) continue;
    visited.add(nodeId);

    const node = nodeMap.get(nodeId);
    const outFeatures = positiveNumber(node?.params.out_features);
    if (node?.type === "Linear" && outFeatures !== null) {
      return outFeatures;
    }

    canvas.connections
      .filter(([, target]) => endpointBaseId(target) === nodeId)
      .forEach(([source]) => queue.push(endpointBaseId(source)));
  }

  const linearNodes = canvas.nodes.filter(node => node.type === "Linear");
  const lastLinear = linearNodes[linearNodes.length - 1];
  return positiveNumber(lastLinear?.params.out_features);
}


function countModelParams(canvas: WorkCanvas, initialShape: number[] | null): number {
  const shapeByNode = new Map<string, number[]>();
  const pending = new Set(canvas.nodes.map(node => node.id));
  let total = 0;
  let changed = true;

  while (pending.size > 0 && changed) {
    changed = false;
    for (const node of canvas.nodes) {
      if (!pending.has(node.id)) continue;

      const inputShapes = incomingShapes(canvas, node.id, shapeByNode);
      if (node.type !== "Input" && inputShapes.length === 0 && canvas.connections.some(([, target]) => endpointBaseId(target) === node.id)) {
        continue;
      }

      const primaryInput = inputShapes[0] || null;
      const result = inferNodeParamAndShape(node, primaryInput, inputShapes, initialShape);
      total += result.params;
      if (result.shape) {
        shapeByNode.set(node.id, result.shape);
      }
      pending.delete(node.id);
      changed = true;
    }
  }

  return total;
}


function incomingShapes(canvas: WorkCanvas, nodeId: string, shapeByNode: Map<string, number[]>): number[][] {
  return canvas.connections
    .filter(([, target]) => endpointBaseId(target) === nodeId)
    .map(([source]) => shapeByNode.get(endpointBaseId(source)))
    .filter((shape): shape is number[] => Array.isArray(shape));
}


function inferNodeParamAndShape(
  node: GraphNode,
  primaryInput: number[] | null,
  inputShapes: number[][],
  initialShape: number[] | null
): { params: number; shape: number[] | null } {
  if (node.type === "Input") {
    return { params: 0, shape: numericShape(node.params.shape) || initialShape };
  }

  if (node.type === "Conv2D" && primaryInput?.length === 3) {
    const inChannels = primaryInput[0]!;
    const outChannels = positiveNumber(node.params.out_channels);
    const kernel = positiveNumber(node.params.kernel_size);
    const stride = positiveNumber(node.params.stride) || 1;
    const padding = nonNegativeNumber(node.params.padding) ?? 0;
    if (outChannels === null || kernel === null) return { params: 0, shape: primaryInput };
    const outH = Math.floor((primaryInput[1]! + 2 * padding - kernel) / stride + 1);
    const outW = Math.floor((primaryInput[2]! + 2 * padding - kernel) / stride + 1);
    return {
      params: outChannels * (inChannels * kernel * kernel + 1),
      shape: outH > 0 && outW > 0 ? [outChannels, outH, outW] : [outChannels],
    };
  }

  if ((node.type === "MaxPooling" || node.type === "Pooling") && primaryInput?.length === 3) {
    const kernel = positiveNumber(node.params.kernel_size) || 2;
    const stride = positiveNumber(node.params.stride) || kernel;
    const padding = nonNegativeNumber(node.params.padding) ?? 0;
    const outH = Math.floor((primaryInput[1]! + 2 * padding - kernel) / stride + 1);
    const outW = Math.floor((primaryInput[2]! + 2 * padding - kernel) / stride + 1);
    return { params: 0, shape: outH > 0 && outW > 0 ? [primaryInput[0]!, outH, outW] : primaryInput };
  }

  if (node.type === "Flatten") {
    return { params: 0, shape: primaryInput ? [shapeProduct(primaryInput)] : null };
  }

  if (node.type === "Linear") {
    const outFeatures = positiveNumber(node.params.out_features);
    if (outFeatures === null) return { params: 0, shape: primaryInput };
    const inFeatures = positiveNumber(node.params.in_features) ?? (primaryInput ? shapeProduct(primaryInput) : 0);
    return { params: inFeatures > 0 ? outFeatures * (inFeatures + 1) : 0, shape: [outFeatures] };
  }

  if (node.type === "GraphConv") {
    const outFeatures = positiveNumber(node.params.out_features);
    const inFeatures = primaryInput?.[primaryInput.length - 1] || 0;
    return {
      params: outFeatures && inFeatures ? outFeatures * (inFeatures + 1) : 0,
      shape: outFeatures && primaryInput ? [...primaryInput.slice(0, -1), outFeatures] : primaryInput,
    };
  }

  if (node.type === "Add" && inputShapes.length > 0) {
    return { params: 0, shape: inputShapes[0]! };
  }

  return { params: 0, shape: primaryInput };
}


function numericShape(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const shape = value.map(item => Number(item));
  return shape.length > 0 && shape.every(item => Number.isFinite(item) && item > 0) ? shape : null;
}


function shapeProduct(shape: number[]): number {
  return shape.reduce((total, value) => total * value, 1);
}


function positiveNumber(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) && num > 0 ? num : null;
}


function nonNegativeNumber(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) && num >= 0 ? num : null;
}


export function getTrainingStatusLabel(status: string | undefined) {
  return (
    {
      dispatched: "已下发",
      pending_agent: "等待 Agent",
      no_agent: "无可用 Agent",
      pending: "等待中",
      running: "训练中",
      cancelling: "停止中",
      completed: "已完成",
      failed: "失败",
      cancelled: "已取消",
    } as Record<string, string>
  )[status || ""] || "未知";
}


export function isTrainingJobActive(job: TrainingJob | null | undefined) {
  if (!job) return false;
  const status = job.status || "pending";
  return !["completed", "failed", "cancelled", "no_agent"].includes(status);
}


// 把训练任务状态写回它所属的画布（并行训练时各画布互不影响）
export function setTrainingJob(canvas: WorkCanvas, job: TrainingJob) {
  const definedJob = Object.fromEntries(
    Object.entries(job).filter(([, value]) => value !== undefined)
  ) as TrainingJob;
  canvas.trainingJob = {
    ...(canvas.trainingJob || {}),
    ...definedJob,
  };
  canvas.jobId = canvas.trainingJob.job_id || canvas.jobId;
}
