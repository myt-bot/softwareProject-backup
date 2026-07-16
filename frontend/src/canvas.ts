// 画布交互引擎：节点拖拽、连线、贝塞尔曲线绘制、缩放、右键菜单定位。
// 连线层（SVG）涉及大量测量与逐帧重绘，保持命令式实现；节点卡片由 Vue 响应式渲染。

import { nextTick } from "vue";
import { isLoggedIn } from "./auth";
import {
  activeCanvas,
  askConfirm,
  askConfirmChoice,
  clamp,
  containerInputPorts,
  containerLibrary,
  containerOutputPorts,
  CONTAINER_TYPE,
  createCanvas,
  createEmptyContainerNode,
  datasetInputShape,
  deriveNodeCounters,
  endpointBaseId,
  endpointPortId,
  formatLayerNote,
  getConnectionKey,
  getLayerConfig,
  instantiateContainerDef,
  isTrainingJobActive,
  isKnownLayerType,
  nextCanvasName,
  openSaveModalAndWait,
  startContainerCoach,
  startMergeCoach,
  pokeMinimap,
  resetValidationAfterGraphChange,
  showToast,
  store,
  subgraphFromCanvas,
  ui,
  updateNodeDisplay,
} from "./store";
import type { WorkCanvas } from "./store";
import type { Connection, GraphNode, ModelGraph, Point } from "./types";

// 从组件库拖入"空白容器"的 dataTransfer 标记
export const NEW_CONTAINER_PAYLOAD = "__new_container__";

const SVG_NS = "http://www.w3.org/2000/svg";

interface BezierSegment {
  start: Point;
  c1: Point;
  c2: Point;
  end: Point;
}

interface BezierSample extends Point {
  segment: BezierSegment;
  t: number;
}

interface ConnectorPoints {
  from: string;
  to: string;
  key: string;
  index: number;
  start: Point;
  end: Point;
  routing: "vertical" | "horizontal";
  endApproach: "free" | "top-biased";
}

interface Connector extends ConnectorPoints {
  segments: BezierSegment[];
  d: string;
  samples: BezierSample[];
}

interface Bridge {
  point: Point;
  tangent: Point;
}

// —————————————————————————————————————————————
// DOM 引用（由 CanvasBoard 挂载时注册）
// —————————————————————————————————————————————

let canvasEl: HTMLElement | null = null;
let svgEl: SVGSVGElement | null = null;
let nodesEl: HTMLElement | null = null;
let gridEl: HTMLElement | null = null;

let pendingConnection: SVGPathElement | null = null;
let dragCandidate: { nodeId: string; startClientX: number; startClientY: number } | null = null;
let dragOffsetX = 0;
let dragOffsetY = 0;

// 节点剪贴板只保存节点本身，不复制它与其它节点之间的连线。
// 这样 Ctrl+C / Ctrl+V、右键复制和悬浮工具条共用同一套行为。
let copiedNode: GraphNode | null = null;
let pasteOffsetStep = 0;

// 按住空白区域拖动画布（视口平移量 panX/panY 属于各画布自身状态）
let panState: {
  startClientX: number;
  startClientY: number;
  startPanX: number;
  startPanY: number;
  moved: boolean;
} | null = null;

export function registerCanvasElements(elements: {
  canvas: HTMLElement;
  svg: SVGSVGElement;
  nodes: HTMLElement;
  grid: HTMLElement;
}) {
  canvasEl = elements.canvas;
  svgEl = elements.svg;
  nodesEl = elements.nodes;
  gridEl = elements.grid;
}


// 当前画布可视区（视口）的像素尺寸，供迷你地图计算视口框
export function getCanvasViewportSize() {
  return canvasEl
    ? { width: canvasEl.clientWidth, height: canvasEl.clientHeight }
    : { width: 0, height: 0 };
}


// 把当前激活画布的平移 + 缩放应用到内容层；点阵背景跟随平移，营造整体移动感
function applyTransform() {
  if (!nodesEl || !svgEl) return;
  const canvas = activeCanvas();
  const transform = `translate(${canvas.panX}px, ${canvas.panY}px) scale(${canvas.zoom})`;
  nodesEl.style.transform = transform;
  svgEl.style.transform = transform;
  if (gridEl) {
    gridEl.style.backgroundPosition = `${canvas.panX}px ${canvas.panY}px`;
  }
}


// —————————————————————————————————————————————
// 多画布管理（标签页）
// —————————————————————————————————————————————

export function addCanvas() {
  store.canvasSeq += 1;
  const canvas = createCanvas(store.canvasSeq, nextCanvasName());
  store.canvases.push(canvas);
  activateCanvas(canvas.id);
  showToast("success", `已新建 ${canvas.name}。`);
}


export function switchCanvas(id: number) {
  if (id === store.activeCanvasId) return;
  activateCanvas(id);
}


export async function closeCanvas(id: number) {
  const index = store.canvases.findIndex(canvas => canvas.id === id);
  const canvas = store.canvases[index];
  if (!canvas) return;

  const isTraining = isTrainingJobActive(canvas.trainingJob);
  if (isTraining) {
    const ok = await askConfirm({
      title: "关闭画布",
      message: `${canvas.name} 有训练任务进行中，关闭后将不再跟踪其进度。确定关闭吗？`,
      confirmText: "关闭画布",
      cancelText: "取消",
      danger: true,
    });
    if (!ok) return;
  } else if (canvas.nodes.length > 0) {
    // Word 式关闭询问：保存 / 不保存 / 取消（快捷键 S / N / Esc，Enter 也视为保存）
    const choice = await askConfirmChoice({
      title: "关闭画布",
      message: `是否保存对 ${canvas.name} 的更改？`,
      confirmText: "保存",
      denyText: "不保存",
      cancelText: "取消",
    });
    if (choice === "cancel") return;
    if (choice === "confirm") {
      if (!isLoggedIn()) {
        showToast("warning", "登录状态已失效，请重新登录后再保存。");
        return;
      }
      // 保存的是"被关闭的这块画布"：先切换过去，保证保存弹窗作用于它
      if (store.activeCanvasId !== id) activateCanvas(id);
      const saved = await openSaveModalAndWait();
      if (!saved) return; // 在保存弹窗中取消 → 中止关闭
    }
  }

  store.canvases.splice(index, 1);

  // 删除了最后一个画布：工作台进入“无画布”空态，由界面提示用户先新建画布
  if (store.canvases.length === 0) {
    store.activeCanvasId = -1;
    showToast("success", `已删除 ${canvas.name}。`);
    return;
  }

  if (store.activeCanvasId === id) {
    const neighbor = store.canvases[Math.min(index, store.canvases.length - 1)]!;
    activateCanvas(neighbor.id);
  }
  showToast("success", `已关闭 ${canvas.name}。`);
}


function activateCanvas(id: number) {
  // 切换前结束当前画布上的瞬时交互
  cancelPendingConnection();
  hideConnectionMenu();
  hideNodeMenu();
  store.activeCanvasId = id;
  applyTransform();
  void redrawAfterDomUpdate();
}


// —————————————————————————————————————————————
// 初始化
// —————————————————————————————————————————————

export function initializeCanvasView() {
  centerInitialNodesInViewport();
  drawLines();
  setTimeout(() => {
    drawLines();
    centerGraphHorizontally();
  }, 100);
}


function centerInitialNodesInViewport() {
  if (activeCanvas().hasCenteredInitialGraph) return;
  if (!canvasEl || canvasEl.clientWidth === 0) return;

  const nodeWidth = 224;
  const centeredX = Math.max(40, (canvasEl.clientWidth - nodeWidth) / 2);
  activeCanvas().nodes.forEach(node => {
    node.x = centeredX;
  });
  activeCanvas().hasCenteredInitialGraph = true;
}


// —————————————————————————————————————————————
// 连线绘制
// —————————————————————————————————————————————

export function drawLines() {
  if (!svgEl) return;
  const svg = svgEl;
  svg.innerHTML = "";
  appendConnectorMarkers(svg);
  const flowingAll = activeCanvas().validationStatus === "passing";
  const renderedConnectors: Connector[] = [];
  const hitPaths: SVGPathElement[] = [];
  const bridges: Bridge[] = [];
  const connectorsByKey: Record<string, Connector> = {};

  activeCanvas().connections.forEach(([from, to], connectionIndex) => {
    const points = getConnectionPoints(from, to, connectionIndex);
    if (!points) return;

    const connector = buildConnector(points);
    connectorsByKey[connector.key] = connector;
    bridges.push(...findConnectorBridges(connector, renderedConnectors));
    const group = document.createElementNS(SVG_NS, "g");
    const visiblePath = document.createElementNS(SVG_NS, "path");
    const hitPath = document.createElementNS(SVG_NS, "path");

    visiblePath.setAttribute("d", connector.d);
    // 结构校验通过后：连线变成"数据通路"——浅色管道 + 末端箭头，
    // 再叠加一条流动的亮色虚线，营造数据在管道里移动的感觉。
    const isSelected = activeCanvas().selectedConnectionKey === connector.key;
    const markerId = flowingAll ? "connector-arrow-flow" : isSelected ? "connector-arrow-selected" : "connector-arrow";
    visiblePath.setAttribute(
      "class",
      `line-connector${isSelected ? " line-selected" : ""}${flowingAll ? " line-flow-track" : ""}`
    );
    visiblePath.setAttribute("marker-end", `url(#${markerId})`);
    visiblePath.dataset.from = from;
    visiblePath.dataset.to = to;

    hitPath.setAttribute("d", connector.d);
    hitPath.setAttribute("class", "line-hit-area");
    hitPath.dataset.from = from;
    hitPath.dataset.to = to;
    hitPath.addEventListener("mouseenter", () => {
      visiblePath.classList.add("line-hover");
      visiblePath.setAttribute("marker-end", "url(#connector-arrow-selected)");
      setConnectionTrace(from, to, visiblePath, true);
    });
    hitPath.addEventListener("mouseleave", () => {
      visiblePath.classList.remove("line-hover");
      visiblePath.setAttribute("marker-end", `url(#${markerId})`);
      setConnectionTrace(from, to, visiblePath, false);
    });
    hitPath.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      selectConnection(from, to, connector);
    });
    hitPath.addEventListener("contextmenu", event => {
      event.preventDefault();
      event.stopPropagation();
      selectConnection(from, to, connector);
      showConnectionMenu(event.clientX, event.clientY, from, to);
    });

    group.appendChild(visiblePath);
    // 流动的亮色数据段叠在管道之上（营造数据在通路里移动的感觉）
    if (flowingAll) {
      const flowPath = document.createElementNS(SVG_NS, "path");
      flowPath.setAttribute("d", connector.d);
      flowPath.setAttribute("class", "line-flow-dash");
      group.appendChild(flowPath);
    }
    svg.appendChild(group);
    hitPaths.push(hitPath);
    renderedConnectors.push(connector);
  });

  renderLineJumps(svg, bridges);
  hitPaths.forEach(hitPath => svg.appendChild(hitPath));
  renderEdgeControlPoints(svg, connectorsByKey);
}


function appendConnectorMarkers(svg: SVGSVGElement) {
  const defs = document.createElementNS(SVG_NS, "defs");
  const markers = [
    ["connector-arrow", "#9fb0cc"],
    ["connector-arrow-selected", "#6366f1"],
    ["connector-arrow-flow", "#10b981"],
  ] as const;

  markers.forEach(([id, color]) => {
    const marker = document.createElementNS(SVG_NS, "marker");
    marker.setAttribute("id", id);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "8.5");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "10");
    marker.setAttribute("markerHeight", "10");
    marker.setAttribute("markerUnits", "userSpaceOnUse");
    // marker-end 使用 auto 后，会按照贝塞尔曲线终点处的切线自动旋转。
    // 箭头方向由真实来线方向决定，不再固定为朝下或朝上。
    marker.setAttribute("orient", "auto");
    const arrow = document.createElementNS(SVG_NS, "path");
    // 圆角空心箭头与连线使用同样的视觉重量；尖端正好落在路径终点，
    // 不再像旧版大号实心三角形那样与线条割裂。
    arrow.setAttribute("d", "M 1.5 1.5 L 8.5 5 L 1.5 8.5");
    arrow.setAttribute("fill", "none");
    arrow.setAttribute("stroke", color);
    arrow.setAttribute("stroke-width", "2");
    arrow.setAttribute("stroke-linecap", "round");
    arrow.setAttribute("stroke-linejoin", "round");
    marker.appendChild(arrow);
    defs.appendChild(marker);
  });
  svg.appendChild(defs);
}


function setConnectionTrace(from: string, to: string, activePath: SVGPathElement, active: boolean) {
  const endpointIds = [endpointBaseId(from), endpointBaseId(to)];
  endpointIds.forEach(id => {
    document.getElementById(`node-${id}`)?.classList.toggle("node-connection-focus", active);
  });
  const activeGroup = activePath.parentElement;
  svgEl?.querySelectorAll<SVGPathElement>(".line-connector, .line-flow-dash").forEach(path => {
    const belongsToActiveConnection = path === activePath || path.parentElement === activeGroup;
    path.classList.toggle("line-dimmed", active && !belongsToActiveConnection);
  });
}


// 节点增删后需等 Vue 更新 DOM 再重绘（需要测量节点尺寸）
export async function redrawAfterDomUpdate() {
  await nextTick();
  drawLines();
  pokeMinimap(); // 节点增删 / 参数更新等结构变化时短暂显现迷你地图
}


// —————————————————————————————————————————————
// 撤销 / 重做（每个画布独立的历史栈）
// —————————————————————————————————————————————

interface GraphSnapshot {
  nodes: GraphNode[];
  connections: Connection[];
  edgeControls: Record<string, Point>;
  nodeCounters: Record<string, number>;
}

const historyMap = new Map<number, { undo: GraphSnapshot[]; redo: GraphSnapshot[] }>();
const HISTORY_LIMIT = 60;

function getHistory(canvasId: number) {
  let entry = historyMap.get(canvasId);
  if (!entry) {
    entry = { undo: [], redo: [] };
    historyMap.set(canvasId, entry);
  }
  return entry;
}

// 进入/退出容器子画板时清空撤销栈：父层与子图共用一个 canvasId，
// 不清空会导致跨层撤销把一层的快照错误地套到另一层。
function clearHistory(canvasId: number) {
  historyMap.delete(canvasId);
}

function takeSnapshot(): GraphSnapshot {
  const canvas = activeCanvas();
  return {
    nodes: canvas.nodes.map(node => ({ ...node, params: { ...node.params } })),
    connections: canvas.connections.map(conn => [...conn] as Connection),
    edgeControls: Object.fromEntries(
      Object.entries(canvas.edgeControls).map(([key, point]) => [key, { ...point }])
    ),
    nodeCounters: { ...canvas.nodeCounters },
  };
}

// 在任何改图操作"之前"调用：把当前状态压入撤销栈，并清空重做栈
export function recordHistory() {
  const canvas = activeCanvas();
  const history = getHistory(canvas.id);
  history.undo.push(takeSnapshot());
  if (history.undo.length > HISTORY_LIMIT) history.undo.shift();
  history.redo = [];
}

function applySnapshot(snapshot: GraphSnapshot) {
  const canvas = activeCanvas();
  canvas.nodes = snapshot.nodes.map(node => ({ ...node, params: { ...node.params } }));
  canvas.connections = snapshot.connections.map(conn => [...conn] as Connection);
  canvas.edgeControls = Object.fromEntries(
    Object.entries(snapshot.edgeControls).map(([key, point]) => [key, { ...point }])
  );
  canvas.nodeCounters = { ...snapshot.nodeCounters };
  canvas.selectedNodeId = null;
  canvas.selectedConnectionKey = null;
  resetValidationAfterGraphChange(canvas);
  void redrawAfterDomUpdate();
}

export function undoGraphChange() {
  const canvas = activeCanvas();
  const history = getHistory(canvas.id);
  if (!history.undo.length) {
    showToast("info", "没有可撤销的操作了。");
    return;
  }
  history.redo.push(takeSnapshot());
  applySnapshot(history.undo.pop()!);
}

export function redoGraphChange() {
  const canvas = activeCanvas();
  const history = getHistory(canvas.id);
  if (!history.redo.length) {
    showToast("info", "没有可重做的操作了。");
    return;
  }
  history.undo.push(takeSnapshot());
  applySnapshot(history.redo.pop()!);
}


// —————————————————————————————————————————————
// 智能布局：短图竖排；超出视口高度后向右折列；分支在同层左右展开。
// —————————————————————————————————————————————

type SmartLayoutMode = "vertical" | "wrapped" | "branched" | "wrapped-branched";

interface SmartLayoutResult {
  mode: SmartLayoutMode;
  columns: number;
}

export function autoLayoutGraph() {
  const canvas = activeCanvas();
  if (canvas.nodes.length === 0) {
    showToast("info", "画布上还没有节点。");
    return;
  }
  recordHistory();
  const result = layoutGraphNodes(canvas);
  void redrawAfterDomUpdate().then(centerGraphInCanvas);
  pokeMinimap();
  const message = result.mode === "vertical"
    ? "已按数据流向竖向排列。"
    : result.mode === "branched"
      ? "已按数据流向排列，分支已左右展开。"
      : `已按数据流向排列，并折成 ${result.columns} 列。`;
  showToast("success", message);
}


// 按数据流向做拓扑分层布局（重心法减少交叉）。每个拓扑层占一行：
// 同层分支左右展开，汇合节点自然回到下一行中央；行数超过当前视口后整段移到右侧新列。
// 手动「自动布局」按钮与内置模板 / 已保存项目加载共用，普通拖拽不会调用。
function layoutGraphNodes(canvas: ReturnType<typeof activeCanvas>): SmartLayoutResult {
  const nodes = canvas.nodes;
  if (nodes.length === 0) return { mode: "vertical", columns: 0 };

  const ids = nodes.map(node => node.id);
  const preds: Record<string, string[]> = {};
  const succ: Record<string, string[]> = {};
  ids.forEach(id => {
    preds[id] = [];
    succ[id] = [];
  });
  canvas.connections.forEach(([fromEndpoint, toEndpoint]) => {
    const from = endpointBaseId(fromEndpoint);
    const to = endpointBaseId(toEndpoint);
    if (preds[to] && !preds[to].includes(from)) preds[to].push(from);
    if (succ[from] && !succ[from].includes(to)) succ[from].push(to);
  });

  // 1) 分层：Kahn 拓扑排序 + 最长路径，layer[n] = max(layer[前驱]) + 1
  const indegree: Record<string, number> = {};
  const layer: Record<string, number> = {};
  ids.forEach(id => {
    indegree[id] = preds[id].length;
    layer[id] = 0;
  });
  const queue = ids.filter(id => indegree[id] === 0);
  const topo: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    topo.push(id);
    for (const next of succ[id]) {
      layer[next] = Math.max(layer[next], layer[id] + 1);
      indegree[next] -= 1;
      if (indegree[next] === 0) queue.push(next);
    }
  }
  // 有环或孤立节点兜底：未排到的按层 0 追加
  ids.forEach(id => {
    if (!topo.includes(id)) topo.push(id);
  });

  // 2) 按层分组（初始顺序 = 拓扑序）
  const maxLayer = Math.max(...ids.map(id => layer[id]));
  const layers: string[][] = Array.from({ length: maxLayer + 1 }, () => []);
  topo.forEach(id => layers[layer[id]].push(id));

  // 3) 层内重心法排序：多趟上下扫描，让每个节点靠近其相邻层邻居的平均位置，减少连线交叉
  const orderIndex: Record<string, number> = {};
  layers.forEach(row => row.forEach((id, i) => (orderIndex[id] = i)));
  const barycenter = (neighbors: string[]) =>
    neighbors.length ? neighbors.reduce((sum, n) => sum + (orderIndex[n] ?? 0), 0) / neighbors.length : -1;
  for (let sweep = 0; sweep < 4; sweep++) {
    const goingDown = sweep % 2 === 0;
    const order = goingDown
      ? [...layers.keys()]
      : [...layers.keys()].reverse();
    for (const d of order) {
      const neighborsOf = goingDown ? preds : succ;
      layers[d].sort((a, b) => {
        const ba = barycenter(neighborsOf[a]);
        const bb = barycenter(neighborsOf[b]);
        if (ba < 0 || bb < 0) return 0;
        return ba - bb;
      });
      layers[d].forEach((id, i) => (orderIndex[id] = i));
    }
  }

  // 4) 根据画布可视高度切分为若干列。切点若正好落在 Merge 前，向前移动一层，
  // 尽量让“分支层 + 汇合层”留在同一列中，阅读方向更连贯。
  const NODE_W = 224;
  const NODE_H = 150;
  const V_GAP = 205;
  const H_GAP = 56;
  const COLUMN_GAP = 140;
  const TOP = 60;
  const BOTTOM = 60;
  const viewportHeight = Math.max(520, canvasEl?.clientHeight || 720);
  // 3 个及以下节点始终保持旧版单列竖排；从第 4 个节点开始才根据视口高度折列。
  const rowsThatFit = nodes.length <= 3
    ? layers.length
    : Math.max(
        2,
        Math.floor((viewportHeight - TOP - BOTTOM - NODE_H) / V_GAP) + 1
      );

  const columns: string[][][] = [];
  let startDepth = 0;
  while (startDepth < layers.length) {
    let endDepth = Math.min(layers.length, startDepth + rowsThatFit);
    if (
      endDepth < layers.length
      && endDepth - startDepth > 1
      && layers[endDepth]!.some(id => preds[id].length > 1)
    ) {
      endDepth -= 1;
    }
    columns.push(layers.slice(startDepth, endDepth));
    startDepth = endDepth;
  }

  const rowWidth = (row: string[]) =>
    row.length * NODE_W + Math.max(0, row.length - 1) * H_GAP;
  const columnWidths = columns.map(column => Math.max(NODE_W, ...column.map(rowWidth)));

  let columnLeft = 40;
  columns.forEach((column, columnIndex) => {
    const columnWidth = columnWidths[columnIndex]!;
    column.forEach((row, rowIndex) => {
      const width = rowWidth(row);
      const rowLeft = columnLeft + (columnWidth - width) / 2;
      row.forEach((id, nodeIndex) => {
        const node = nodes.find(item => item.id === id);
        if (!node) return;
        node.x = Math.round(rowLeft + nodeIndex * (NODE_W + H_GAP));
        node.y = TOP + rowIndex * V_GAP;
      });
    });
    columnLeft += columnWidth + COLUMN_GAP;
  });

  // 节点已整体换位，旧的手工连线控制点不再对应新的几何位置。
  canvas.edgeControls = {};

  const hasBranches = ids.some(id => preds[id].length > 1 || succ[id].length > 1)
    || layers.some(row => row.length > 1);
  const wrapped = columns.length > 1;
  const mode: SmartLayoutMode = wrapped
    ? hasBranches ? "wrapped-branched" : "wrapped"
    : hasBranches ? "branched" : "vertical";

  return { mode, columns: columns.length };
}


function getConnectionPoints(from: string, to: string, index = 0): ConnectorPoints | null {
  // from/to 是"端点"：普通层为节点 id，容器端口为 容器id::端口层id
  const fromId = endpointBaseId(from);
  const toId = endpointBaseId(to);
  const fromNode = activeCanvas().nodes.find(node => node.id === fromId);
  const toNode = activeCanvas().nodes.find(node => node.id === toId);
  if (!fromNode || !toNode) {
    return null;
  }

  // 折列边沿阅读方向从左列进入右列。左右侧锚点可避免原先
  // “从底部绕到下一列顶部”的巨大 U 形线，让主链和跳连更容易追踪。
  const multiInputEnd = getMultiInputPoint(to, from);
  const crossesToNextColumn = !multiInputEnd
    && toNode.x - fromNode.x > 300
    && toNode.y <= fromNode.y + 40;

  return {
    from,
    to,
    key: getConnectionKey(from, to),
    index,
    start: crossesToNextColumn ? getNodeRightCenter(fromId) : getEndpointOutPoint(from),
    end: multiInputEnd ?? (crossesToNextColumn ? getNodeLeftCenter(toId) : getEndpointInPoint(to)),
    routing: crossesToNextColumn ? "horizontal" : "vertical",
    // 多输入线从节点顶边进入：允许箭头顺着来线偏转，但不能接近水平，
    // 否则箭头会贴住卡片上边框而难以辨认。
    endApproach: multiInputEnd ? "top-biased" : "free",
  };
}


// 普通节点有多个输入时，为每条连线分配独立的顶部入口。
// 入口按来源节点的水平位置排序，左侧来源接左端口、右侧来源接右端口，
// 避免多根线在进入节点前重合成一根、或形成难看的交合点。
function getMultiInputPoint(targetEndpoint: string, sourceEndpoint: string): Point | null {
  if (endpointPortId(targetEndpoint)) return null;

  const targetId = endpointBaseId(targetEndpoint);
  const incoming = activeCanvas().connections
    .filter(([, target]) => endpointBaseId(target) === targetId && !endpointPortId(target))
    .sort(([sourceA], [sourceB]) => {
      const nodeA = activeCanvas().nodes.find(node => node.id === endpointBaseId(sourceA));
      const nodeB = activeCanvas().nodes.find(node => node.id === endpointBaseId(sourceB));
      return (nodeA?.x ?? 0) - (nodeB?.x ?? 0) || (nodeA?.y ?? 0) - (nodeB?.y ?? 0);
    });
  if (incoming.length <= 1) return null;

  const sourceIndex = incoming.findIndex(([source]) => source === sourceEndpoint);
  const rect = getNodeRect(targetId);
  if (sourceIndex < 0 || !rect) return null;

  return {
    x: rect.left + rect.width * ((sourceIndex + 1) / (incoming.length + 1)),
    y: rect.top,
  };
}


function buildConnector(points: ConnectorPoints): Connector;
function buildConnector(points: { start: Point; end: Point }): { d: string };
function buildConnector(points: Partial<ConnectorPoints> & { start: Point; end: Point }) {
  const segments = buildBezierSegments(points);
  return {
    ...points,
    key: points.key || (points.from && points.to ? getConnectionKey(points.from, points.to) : ""),
    segments,
    d: buildBezierPath(segments),
    samples: sampleBezierSegments(segments, 24),
  };
}


function buildBezierSegments(points: Partial<ConnectorPoints> & { start: Point; end: Point }): BezierSegment[] {
  const { start, end } = points;
  const controlPoint = points.key ? activeCanvas().edgeControls[points.key] : null;
  // tan(32°) ≈ 0.625：顶部入口的箭头最多偏离竖直方向约 32°。
  const maxEndHorizontalRatio = points.endApproach === "top-biased" ? 0.625 : undefined;

  if (controlPoint) {
    return buildControlledBezierSegments(start, controlPoint, end, maxEndHorizontalRatio);
  }

  if (points.routing === "horizontal") {
    return [buildHorizontalBezierSegment(start, end)];
  }

  // 折列后的跨列连线：先从源节点底部向下离开，再沿两列之间的留白向上，
  // 最后从目标节点上方进入。避免普通反向贝塞尔直接穿过源节点或中间卡片。
  if (end.y < start.y - 80 && Math.abs(end.x - start.x) > 180) {
    const gutterX = (start.x + end.x) / 2;
    const lowerTurn = { x: gutterX, y: start.y + 54 };
    const upperTurn = { x: gutterX, y: Math.max(8, end.y - 54) };
    return [
      buildBezierSegment(start, lowerTurn),
      buildBezierSegment(lowerTurn, upperTurn),
      buildBezierSegment(upperTurn, end, maxEndHorizontalRatio),
    ];
  }

  const rawDeltaY = Math.abs(end.y - start.y);
  const yDistance = Math.max(24, rawDeltaY);
  const yDirection = end.y >= start.y ? 1 : -1;

  // 节点感知绕行：若直线会穿过中间节点，则把连线整体侧弯到更近一侧的节点外缘之外
  const bowX = computeAvoidanceBow(points);
  const detour = Math.abs(bowX) > 1;
  // 需要绕行时用更长的纵向控制点，让侧弯更圆润、在节点高度处更贴近目标 x
  const verticalControl = detour
    ? clamp(rawDeltaY * 0.32, 70, 240)
    : clamp(yDistance * 0.42, 42, 120);
  // 终点控制点沿“实际来线 → 节点入口”的方向回退。
  // SVG marker 会读取 c2 → end 的切线，因此斜向、横向进入时箭头也会同步转向。
  const endControl = getAdaptiveEndControl(
    { x: start.x + bowX, y: start.y },
    end,
    verticalControl,
    maxEndHorizontalRatio
  );

  return [
    {
      start,
      c1: {
        x: start.x + bowX,
        y: start.y + yDirection * verticalControl,
      },
      c2: endControl,
      end,
    },
  ];
}


// 计算“绕开中间节点”所需的水平侧弯量（画布坐标系）。返回带符号的 bow：
// >0 向右绕，<0 向左绕，0 表示直线没有被任何中间节点挡住、无需绕行。
function computeAvoidanceBow(points: Partial<ConnectorPoints> & { start: Point; end: Point }): number {
  // 仅对真实连线（有 from/to）绕行；连线预览（拖到光标）保持直，不参与
  if (!points.from || !points.to) return 0;

  const { start, end } = points;
  const fromId = endpointBaseId(points.from);
  const toId = endpointBaseId(points.to);
  const yLo = Math.min(start.y, end.y);
  const yHi = Math.max(start.y, end.y);
  const dy = end.y - start.y || 1;

  const blockers: Array<{ left: number; right: number }> = [];
  for (const node of activeCanvas().nodes) {
    if (node.id === fromId || node.id === toId) continue;
    const rect = getNodeRect(node.id);
    if (!rect) continue;
    // 纵向需与连线区间有实质重叠（排除仅擦到端点的情况）
    if (rect.bottom <= yLo + 12 || rect.top >= yHi - 12) continue;
    // 直线在该节点中部高度处的 x 是否落在（略扩的）节点水平范围内 → 会穿过它
    const midY = Math.min(Math.max((rect.top + rect.bottom) / 2, yLo), yHi);
    const t = (midY - start.y) / dy;
    const lineX = start.x + (end.x - start.x) * t;
    if (lineX > rect.left - 26 && lineX < rect.right + 26) {
      blockers.push({ left: rect.left, right: rect.right });
    }
  }
  if (!blockers.length) return 0;

  const minLeft = Math.min(...blockers.map(b => b.left));
  const maxRight = Math.max(...blockers.map(b => b.right));
  const midX = (start.x + end.x) / 2;
  const MARGIN = 42;
  const targetRight = maxRight + MARGIN;
  const targetLeft = minLeft - MARGIN;
  // 选更近的一侧绕行
  const targetX = targetRight - midX <= midX - targetLeft ? targetRight : targetLeft;
  // 三次贝塞尔中点 x ≈ midX + 0.75 * bow → 解出所需 bow
  return (targetX - midX) / 0.75;
}


function buildControlledBezierSegments(
  start: Point,
  control: Point,
  end: Point,
  maxEndHorizontalRatio?: number
): BezierSegment[] {
  return [
    buildBezierSegment(start, control),
    buildBezierSegment(control, end, maxEndHorizontalRatio),
  ];
}


function buildBezierSegment(start: Point, end: Point, maxEndHorizontalRatio?: number): BezierSegment {
  const deltaY = Math.abs(end.y - start.y);
  const yDirection = end.y >= start.y ? 1 : -1;
  const verticalControl = clamp(deltaY * 0.42, 28, 120);

  return {
    start,
    c1: {
      x: start.x,
      y: start.y + yDirection * verticalControl,
    },
    c2: getAdaptiveEndControl(start, end, verticalControl, maxEndHorizontalRatio),
    end,
  };
}


// 沿连线整体方向从终点向后取控制点，使最后一小段的切线与来线一致。
// 当两个节点正好竖直排列时 dx=0，行为与原先完全相同；横向或斜向时则自然旋转。
function getAdaptiveEndControl(
  approachFrom: Point,
  end: Point,
  maxDistance: number,
  maxHorizontalRatio?: number
): Point {
  let dx = end.x - approachFrom.x;
  const dy = end.y - approachFrom.y;
  if (maxHorizontalRatio !== undefined && Math.abs(dy) > 0.001) {
    const maxHorizontal = Math.abs(dy) * maxHorizontalRatio;
    dx = Math.sign(dx) * Math.min(Math.abs(dx), maxHorizontal);
  }
  const length = Math.hypot(dx, dy);
  if (length < 0.001) {
    return { x: end.x, y: end.y - maxDistance };
  }

  const distance = Math.min(maxDistance, length * 0.38);
  return {
    x: end.x - (dx / length) * distance,
    y: end.y - (dy / length) * distance,
  };
}


function buildHorizontalBezierSegment(start: Point, end: Point): BezierSegment {
  const deltaX = Math.abs(end.x - start.x);
  const direction = end.x >= start.x ? 1 : -1;
  const horizontalControl = clamp(deltaX * 0.42, 56, 180);

  return {
    start,
    c1: { x: start.x + direction * horizontalControl, y: start.y },
    c2: { x: end.x - direction * horizontalControl, y: end.y },
    end,
  };
}


function buildBezierPath(segments: BezierSegment[]) {
  if (segments.length === 0) return "";

  const [firstSegment, ...remainingSegments] = segments;
  const commands = [
    `M ${firstSegment!.start.x} ${firstSegment!.start.y}`,
    cubicCommand(firstSegment!),
  ];

  remainingSegments.forEach(segment => {
    commands.push(cubicCommand(segment));
  });

  return commands.join(" ");
}


function cubicCommand(segment: BezierSegment) {
  return `C ${segment.c1.x} ${segment.c1.y}, ${segment.c2.x} ${segment.c2.y}, ${segment.end.x} ${segment.end.y}`;
}


function sampleBezierSegments(segments: BezierSegment[], stepsPerSegment: number): BezierSample[] {
  const samples: BezierSample[] = [];

  segments.forEach((segment, segmentIndex) => {
    for (let step = 0; step <= stepsPerSegment; step += 1) {
      if (segmentIndex > 0 && step === 0) continue;
      const t = step / stepsPerSegment;
      samples.push({
        ...getCubicPoint(segment, t),
        segment,
        t,
      });
    }
  });

  return samples;
}


function getCubicPoint(segment: BezierSegment, t: number): Point {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const t2 = t * t;

  return {
    x:
      mt2 * mt * segment.start.x +
      3 * mt2 * t * segment.c1.x +
      3 * mt * t2 * segment.c2.x +
      t2 * t * segment.end.x,
    y:
      mt2 * mt * segment.start.y +
      3 * mt2 * t * segment.c1.y +
      3 * mt * t2 * segment.c2.y +
      t2 * t * segment.end.y,
  };
}


function findConnectorBridges(connector: Connector, previousConnectors: Connector[]): Bridge[] {
  const bridges: Bridge[] = [];

  previousConnectors.forEach(previousConnector => {
    findPolylineIntersections(connector.samples, previousConnector.samples).forEach(intersection => {
      if (isNearConnectorEndpoint(connector, intersection.point)) return;
      if (bridges.some(bridge => getDistance(bridge.point, intersection.point) < 16)) return;

      bridges.push({
        point: intersection.point,
        tangent: getSegmentTangent(intersection.currentStart, intersection.currentEnd),
      });
    });
  });

  return bridges;
}


function findPolylineIntersections(currentSamples: BezierSample[], previousSamples: BezierSample[]) {
  const intersections: { point: Point; currentStart: Point; currentEnd: Point }[] = [];

  for (let currentIndex = 0; currentIndex < currentSamples.length - 1; currentIndex += 1) {
    const currentStart = currentSamples[currentIndex]!;
    const currentEnd = currentSamples[currentIndex + 1]!;

    for (let previousIndex = 0; previousIndex < previousSamples.length - 1; previousIndex += 1) {
      const previousStart = previousSamples[previousIndex]!;
      const previousEnd = previousSamples[previousIndex + 1]!;
      const point = getSegmentIntersection(currentStart, currentEnd, previousStart, previousEnd);

      if (point) {
        intersections.push({
          point,
          currentStart,
          currentEnd,
        });
      }
    }
  }

  return intersections;
}


function getSegmentIntersection(a1: Point, a2: Point, b1: Point, b2: Point): Point | null {
  const denominator =
    (a1.x - a2.x) * (b1.y - b2.y) -
    (a1.y - a2.y) * (b1.x - b2.x);

  if (Math.abs(denominator) < 0.0001) return null;

  const t =
    ((a1.x - b1.x) * (b1.y - b2.y) -
      (a1.y - b1.y) * (b1.x - b2.x)) /
    denominator;
  const u =
    -(
      (a1.x - a2.x) * (a1.y - b1.y) -
      (a1.y - a2.y) * (a1.x - b1.x)
    ) / denominator;

  if (t <= 0.04 || t >= 0.96 || u <= 0.04 || u >= 0.96) return null;

  return {
    x: a1.x + t * (a2.x - a1.x),
    y: a1.y + t * (a2.y - a1.y),
  };
}


function isNearConnectorEndpoint(connector: Connector, point: Point) {
  return getDistance(connector.start, point) < 30 || getDistance(connector.end, point) < 30;
}


function getSegmentTangent(start: Point, end: Point): Point {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;

  return {
    x: dx / length,
    y: dy / length,
  };
}


function getDistance(a: Point, b: Point) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}


// 两条连线交叉处画"过桥"弧
function renderLineJumps(svg: SVGSVGElement, bridges: Bridge[]) {
  bridges.forEach(bridge => {
    const radius = 6;
    const gap = document.createElementNS(SVG_NS, "circle");
    const arc = document.createElementNS(SVG_NS, "path");
    const start = {
      x: bridge.point.x - bridge.tangent.x * radius,
      y: bridge.point.y - bridge.tangent.y * radius,
    };
    const end = {
      x: bridge.point.x + bridge.tangent.x * radius,
      y: bridge.point.y + bridge.tangent.y * radius,
    };

    gap.setAttribute("cx", String(bridge.point.x));
    gap.setAttribute("cy", String(bridge.point.y));
    gap.setAttribute("r", String(radius + 3));
    gap.setAttribute("class", "line-jump-gap");

    arc.setAttribute("d", `M ${start.x} ${start.y} A ${radius} ${radius} 0 0 1 ${end.x} ${end.y}`);
    arc.setAttribute("class", "line-connector line-jump-arc");

    svg.appendChild(gap);
    svg.appendChild(arc);
  });
}


// 被选中连线的可拖拽控制点
function renderEdgeControlPoints(svg: SVGSVGElement, connectorsByKey: Record<string, Connector>) {
  const selectedKey = activeCanvas().selectedConnectionKey;
  if (!selectedKey || !activeCanvas().edgeControls[selectedKey]) return;

  const connector = connectorsByKey[selectedKey];
  if (!connector) return;

  const controlPoint = activeCanvas().edgeControls[selectedKey];
  const halo = document.createElementNS(SVG_NS, "circle");
  const handle = document.createElementNS(SVG_NS, "circle");
  const dot = document.createElementNS(SVG_NS, "circle");

  // 外圈柔光：提示这是一个可交互的控制点
  halo.setAttribute("cx", String(controlPoint.x));
  halo.setAttribute("cy", String(controlPoint.y));
  halo.setAttribute("r", "15");
  halo.setAttribute("class", "edge-control-halo");

  // 手柄本体：白底圆环 + 阴影
  handle.setAttribute("cx", String(controlPoint.x));
  handle.setAttribute("cy", String(controlPoint.y));
  handle.setAttribute("r", "7.5");
  handle.setAttribute("class", "edge-control");
  handle.dataset.connectionKey = selectedKey;
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = "拖动可弯曲连线";
  handle.appendChild(title);
  handle.addEventListener("mousedown", event => {
    event.preventDefault();
    event.stopPropagation();
    startEdgeControlDrag(selectedKey);
  });
  handle.addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
  });

  // 内圆点：作为"抓取点"，让手柄更像一个实体控件而非幽灵点
  dot.setAttribute("cx", String(controlPoint.x));
  dot.setAttribute("cy", String(controlPoint.y));
  dot.setAttribute("r", "2.75");
  dot.setAttribute("class", "edge-control-dot");

  svg.appendChild(halo);
  svg.appendChild(handle);
  svg.appendChild(dot);
}


export function selectConnection(from: string, to: string, connector: Connector | null = null) {
  const key = getConnectionKey(from, to);
  activeCanvas().selectedConnectionKey = key;
  activeCanvas().selectedNodeId = null;

  if (!activeCanvas().edgeControls[key]) {
    const points = getConnectionPoints(from, to);
    if (points) {
      activeCanvas().edgeControls[key] = getDefaultEdgeControlPoint(connector || buildConnector(points));
    }
  }

  drawLines();
}


function getDefaultEdgeControlPoint(connector: Connector): Point {
  if (!connector?.samples?.length) {
    return { x: 0, y: 0 };
  }

  const middleIndex = Math.floor(connector.samples.length / 2);
  const middlePoint = connector.samples[middleIndex]!;

  return {
    x: middlePoint.x,
    y: middlePoint.y,
  };
}


function startEdgeControlDrag(connectionKey: string) {
  recordHistory();  // 记录弯折前的控制点，便于撤销
  store.draggingEdgeControlKey = connectionKey;
  store.suppressNextClick = true;
  document.body.classList.add("is-edge-control-dragging");
}


function dragEdgeControlToPointer(clientX: number, clientY: number) {
  if (!store.draggingEdgeControlKey) return;
  const point = getCanvasPoint(clientX, clientY);
  activeCanvas().edgeControls[store.draggingEdgeControlKey] = {
    x: point.x,
    y: point.y,
  };
  drawLines();
}


function finishEdgeControlDrag() {
  store.draggingEdgeControlKey = null;
  store.suppressNextClick = true;
  document.body.classList.remove("is-edge-control-dragging");
}


function removeEdgeControl(from: string, to: string) {
  delete activeCanvas().edgeControls[getConnectionKey(from, to)];
}


function removeEdgeControlsForNode(nodeId: string) {
  Object.keys(activeCanvas().edgeControls).forEach(key => {
    const [source, target] = key.split("->");
    // 端点可能是容器端口（容器id::端口层id），按基节点 id 匹配
    if (endpointBaseId(source || "") === nodeId || endpointBaseId(target || "") === nodeId) {
      delete activeCanvas().edgeControls[key];
    }
  });
}


// —————————————————————————————————————————————
// 节点几何
// —————————————————————————————————————————————

function getNodeRect(nodeId: string) {
  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  if (!node) return null;

  const element = document.getElementById(`node-${nodeId}`);
  const width = element?.offsetWidth || 224;
  const height = element?.offsetHeight || 150;

  return {
    left: node.x,
    top: node.y,
    right: node.x + width,
    bottom: node.y + height,
    width,
    height,
  };
}


function getNodeBottomCenter(nodeId: string): Point {
  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  const rect = getNodeRect(nodeId);
  if (!node || !rect) {
    return { x: 0, y: 0 };
  }

  return {
    x: node.x + rect.width / 2,
    y: node.y + rect.height,
  };
}


function getNodeTopCenter(nodeId: string): Point {
  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  const rect = getNodeRect(nodeId);
  if (!node || !rect) {
    return { x: 0, y: 0 };
  }

  return {
    x: node.x + rect.width / 2,
    y: node.y,
  };
}


function getNodeRightCenter(nodeId: string): Point {
  const rect = getNodeRect(nodeId);
  return rect
    ? { x: rect.right, y: rect.top + rect.height / 2 }
    : { x: 0, y: 0 };
}


function getNodeLeftCenter(nodeId: string): Point {
  const rect = getNodeRect(nodeId);
  return rect
    ? { x: rect.left, y: rect.top + rect.height / 2 }
    : { x: 0, y: 0 };
}


// 端点的连出/连入坐标：容器端口取端口锚点 DOM 中心，普通层取节点底/顶中点。
function getEndpointOutPoint(endpoint: string): Point {
  if (endpointPortId(endpoint)) {
    return getPortAnchorCenter(endpoint) ?? getNodeBottomCenter(endpointBaseId(endpoint));
  }
  return getNodeBottomCenter(endpoint);
}

function getEndpointInPoint(endpoint: string): Point {
  if (endpointPortId(endpoint)) {
    return getPortAnchorCenter(endpoint) ?? getNodeTopCenter(endpointBaseId(endpoint));
  }
  return getNodeTopCenter(endpoint);
}

// 容器端口锚点（带 data-endpoint 属性的 DOM 元素）在画布坐标系里的中心点
function getPortAnchorCenter(endpoint: string): Point | null {
  const element = document.querySelector(`[data-endpoint="${endpoint}"]`) as HTMLElement | null;
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return getCanvasPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
}


export function getCanvasPoint(clientX: number, clientY: number): Point {
  if (!canvasEl) return { x: 0, y: 0 };
  const rect = canvasEl.getBoundingClientRect();
  return {
    x: (clientX - rect.left - activeCanvas().panX) / activeCanvas().zoom,
    y: (clientY - rect.top - activeCanvas().panY) / activeCanvas().zoom,
  };
}


// —————————————————————————————————————————————
// 节点拖拽
// —————————————————————————————————————————————

export function handleNodeMouseDown(event: MouseEvent, nodeId: string) {
  if (event.button !== 0) return;
  if (store.isConnecting) return;

  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  const point = getCanvasPoint(event.clientX, event.clientY);
  hideConnectionMenu();
  hideNodeMenu();
  dragCandidate = {
    nodeId,
    startClientX: event.clientX,
    startClientY: event.clientY,
  };
  dragOffsetX = point.x - (node?.x || 0);
  dragOffsetY = point.y - (node?.y || 0);
}


// 在画布空白区域按下鼠标 → 进入平移模式（节点、连线、悬浮控件除外）
export function handleCanvasMouseDown(event: MouseEvent) {
  if (event.button !== 0) return;
  if (store.isConnecting) return;
  if (!canvasEl) return;

  const target = event.target as Element | null;
  if (target?.closest?.(".node-card, .edge-control, .edge-control-halo, .line-hit-area, .zoom-control, .exit-connect-button")) {
    return;
  }

  hideConnectionMenu();
  hideNodeMenu();
  panState = {
    startClientX: event.clientX,
    startClientY: event.clientY,
    startPanX: activeCanvas().panX,
    startPanY: activeCanvas().panY,
    moved: false,
  };
}


function dragCanvasToPointer(clientX: number, clientY: number) {
  if (!panState) return;

  const deltaX = clientX - panState.startClientX;
  const deltaY = clientY - panState.startClientY;
  if (!panState.moved && Math.hypot(deltaX, deltaY) > 3) {
    panState.moved = true;
  }
  if (panState.moved) {
    const canvas = activeCanvas();
    canvas.panX = panState.startPanX + deltaX;
    canvas.panY = panState.startPanY + deltaY;
    applyTransform();
    pokeMinimap();
  }
}


// 滚轮平移（触控板双向、鼠标滚轮纵向），同样无边界限制
export function handleCanvasWheel(event: WheelEvent) {
  hideConnectionMenu();
  hideNodeMenu();
  const canvas = activeCanvas();
  canvas.panX -= event.deltaX;
  canvas.panY -= event.deltaY;
  applyTransform();
  pokeMinimap();
}


export function handleDocumentMouseMove(event: MouseEvent) {
  if (panState) {
    dragCanvasToPointer(event.clientX, event.clientY);
    return;
  }

  if (store.draggingEdgeControlKey) {
    dragEdgeControlToPointer(event.clientX, event.clientY);
    return;
  }

  if (store.draggingNodeId) {
    dragNodeToPointer(event.clientX, event.clientY);
    return;
  }

  if (dragCandidate && !store.isConnecting) {
    if ((event.buttons & 1) !== 1) {
      dragCandidate = null;
      return;
    }

    const moved = Math.hypot(
      event.clientX - dragCandidate.startClientX,
      event.clientY - dragCandidate.startClientY
    );
    if (moved > 5) {
      startNodeDrag(dragCandidate.nodeId);
      dragNodeToPointer(event.clientX, event.clientY);
      return;
    }
  }

  if (!store.isConnecting) return;
  updatePendingConnection(event.clientX, event.clientY);
  updateConnectionTargetState(event.clientX, event.clientY);
}


export function handleDocumentMouseUp() {
  dragCandidate = null;

  // 端口拖拽连线：在目标节点上松开即完成，否则取消
  if (store.isConnecting && store.connectingByDrag) {
    const target = store.connectTargetId;
    if (target) {
      completeConnection(target);
    }
    cancelPendingConnection();
    store.suppressNextClick = true;
    return;
  }

  if (panState) {
    // 拖动过画布则吞掉随后的 click，避免误触发"取消选中"
    if (panState.moved) {
      store.suppressNextClick = true;
    }
    panState = null;
    return;
  }

  if (store.draggingEdgeControlKey) {
    finishEdgeControlDrag();
    return;
  }

  if (store.draggingNodeId) {
    finishNodeDrag();
    return;
  }
}


function startNodeDrag(nodeId: string) {
  recordHistory();  // 记录移动前位置，便于撤销
  store.draggingNodeId = nodeId;
  store.suppressNextClick = true;
  document.body.classList.add("is-node-dragging");
}


function dragNodeToPointer(clientX: number, clientY: number) {
  const node = activeCanvas().nodes.find(item => item.id === store.draggingNodeId);
  if (!node) return;

  // 自由画布：节点可以放置在任意坐标（含负坐标），不做边界限制
  const point = getCanvasPoint(clientX, clientY);
  node.x = point.x - dragOffsetX;
  node.y = point.y - dragOffsetY;
  pokeMinimap();
  drawLines();
}


function finishNodeDrag() {
  store.draggingNodeId = null;
  dragCandidate = null;
  document.body.classList.remove("is-node-dragging");
  store.suppressNextClick = true;
  // 拖动只改变节点位置、不改变图结构，因此不重置校验状态；
  // 只有增删节点/连线（或修改参数）才会使校验结果失效。
  drawLines();
}


// —————————————————————————————————————————————
// 连线模式
// —————————————————————————————————————————————

export function beginConnection(sourceId: string, clientX: number, clientY: number) {
  store.isConnecting = true;
  store.connectSourceId = sourceId;
  store.suppressNextClick = false;

  // 连线模式下收起参数面板，避免遮挡画布右侧与"退出连线"按钮
  ui.inspectorCollapsed = true;
  document.body.classList.add("is-connecting");
  createPendingConnection();
  updatePendingConnection(clientX, clientY);
  showToast("info", "已进入连线模式，点击目标节点即可连线。");
}


// 从节点底部端口按住拖拽连线：更直观，松开在目标节点上即完成
export function beginConnectionDrag(sourceId: string, clientX: number, clientY: number) {
  store.isConnecting = true;
  store.connectingByDrag = true;
  store.connectSourceId = sourceId;
  store.connectTargetId = null;
  store.suppressNextClick = false;
  document.body.classList.add("is-connecting");
  createPendingConnection();
  updatePendingConnection(clientX, clientY);
}


function createPendingConnection() {
  if (!svgEl) return;
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("class", "line-connector pending-connector");
  path.id = "pending-connector";
  svgEl.appendChild(path);
  pendingConnection = path;
}


function updatePendingConnection(clientX: number, clientY: number) {
  if (!pendingConnection || !store.connectSourceId) return;
  if (!pendingConnection.isConnected) {
    createPendingConnection();
  }

  const start = getEndpointOutPoint(store.connectSourceId);
  const end = getCanvasPoint(clientX, clientY);

  pendingConnection!.setAttribute(
    "d",
    buildConnector({ start, end }).d
  );
}


// 找出指针下的"可连入目标端点"：优先容器输入端口锚点，否则普通层节点本体
// （容器必须连到具体端口锚点，不接受连到容器卡片本体）。
function resolveTargetEndpoint(clientX: number, clientY: number): string | null {
  const element = document.elementFromPoint(clientX, clientY);
  const portElement = element?.closest?.("[data-endpoint][data-port-kind='in']") as HTMLElement | null;
  if (portElement?.dataset.endpoint) return portElement.dataset.endpoint;

  const card = element?.closest?.(".node-card") as HTMLElement | null;
  const nodeId = card?.dataset.nodeId;
  if (!nodeId) return null;

  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  if (node?.type === CONTAINER_TYPE) return null;
  return nodeId;
}


function updateConnectionTargetState(clientX: number, clientY: number) {
  const targetEndpoint = resolveTargetEndpoint(clientX, clientY);
  const source = store.connectSourceId;
  store.connectTargetId =
    targetEndpoint && (!source || endpointBaseId(targetEndpoint) !== endpointBaseId(source))
      ? targetEndpoint
      : null;
}


export function completeConnection(targetEndpoint: string) {
  const sourceEndpoint = store.connectSourceId;
  if (!sourceEndpoint || endpointBaseId(sourceEndpoint) === endpointBaseId(targetEndpoint)) {
    showToast("warning", "不能将节点连接到自身。");
    return;
  }

  const exists = activeCanvas().connections.some(
    ([source, target]) => source === sourceEndpoint && target === targetEndpoint
  );
  if (exists) {
    showToast("warning", "这两个端点之间已经存在连线。");
    return;
  }

  recordHistory();
  activeCanvas().connections.push([sourceEndpoint, targetEndpoint]);
  resetValidationAfterGraphChange();
  drawLines();
  showToast("success", "连线成功。");
}


export function cancelPendingConnection() {
  store.isConnecting = false;
  store.connectingByDrag = false;
  store.connectSourceId = null;
  store.connectTargetId = null;
  pendingConnection?.remove();
  pendingConnection = null;
  document.body.classList.remove("is-connecting");
}


// —————————————————————————————————————————————
// 右键菜单
// —————————————————————————————————————————————

function showConnectionMenu(clientX: number, clientY: number, from: string, to: string) {
  // 右键连线时只保留连线菜单，避免与节点菜单同时显示。
  hideNodeMenu();
  store.menuConnection = [from, to];
  store.connectionMenu = { visible: true, x: clientX, y: clientY };
}


export function hideConnectionMenu() {
  store.connectionMenu.visible = false;
}


export function showNodeMenu(clientX: number, clientY: number, nodeId: string) {
  selectNode(nodeId);
  store.menuNodeId = nodeId;
  hideConnectionMenu();
  store.nodeMenu = { visible: true, x: clientX, y: clientY };
}


function cloneGraphNode(node: GraphNode): GraphNode {
  // GraphNode 只包含可序列化的数据；深拷贝可同时保护 params 数组与容器 subgraph。
  return JSON.parse(JSON.stringify(node)) as GraphNode;
}


export function copyNodeById(nodeId: string): boolean {
  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  if (!node) return false;
  copiedNode = cloneGraphNode(node);
  pasteOffsetStep = 0;
  showToast("success", `已复制 ${node.title}，可按 Ctrl+V 粘贴。`);
  return true;
}


export function copySelectedNode(): boolean {
  const nodeId = activeCanvas().selectedNodeId;
  return nodeId ? copyNodeById(nodeId) : false;
}


export function copyMenuNode(event: Event) {
  event.stopPropagation();
  const nodeId = store.menuNodeId;
  hideNodeMenu();
  if (nodeId) copyNodeById(nodeId);
}


function nextCopiedNodeId(type: string): string {
  const canvas = activeCanvas();
  let counter = canvas.nodeCounters[type] || 0;
  let id = "";
  do {
    counter += 1;
    id = `${type.toLowerCase()}_${counter}`;
  } while (canvas.nodes.some(node => node.id === id));
  canvas.nodeCounters[type] = counter;
  return id;
}


export function pasteCopiedNode(): boolean {
  if (!copiedNode) {
    showToast("info", "还没有复制节点，请先选中节点并按 Ctrl+C。");
    return false;
  }

  recordHistory();
  pasteOffsetStep += 1;
  const node = cloneGraphNode(copiedNode);
  node.id = nextCopiedNodeId(node.type);
  node.title = `${copiedNode.title} 副本`;
  node.x = copiedNode.x + 36 * pasteOffsetStep;
  node.y = copiedNode.y + 36 * pasteOffsetStep;
  activeCanvas().nodes.push(node);
  void redrawAfterDomUpdate();
  selectNode(node.id, { openInspector: false });
  resetValidationAfterGraphChange();
  showToast("success", `已粘贴 ${node.title}。`);
  return true;
}


export function hideNodeMenu() {
  store.nodeMenu.visible = false;
}


export function connectFromMenuNode(event: Event) {
  event.stopPropagation();
  const nodeId = store.menuNodeId;
  if (!nodeId) return;

  const node = document.getElementById(`node-${nodeId}`);
  if (!node) return;
  const rect = node.getBoundingClientRect();
  hideNodeMenu();
  beginConnection(nodeId, rect.left + rect.width / 2, rect.bottom);
}


// 按 id 删除节点及其连线（UI 右键删除与 AI 助手 delete_node 共用，保证行为一致：
// 记录历史、清理边控制点与挂起连线、重置校验状态并重绘）。返回是否删除成功。
export function deleteNodeById(nodeId: string): boolean {
  const canvas = activeCanvas();
  if (!canvas.nodes.some(node => node.id === nodeId)) return false;

  recordHistory();
  canvas.nodes = canvas.nodes.filter(node => node.id !== nodeId);
  // 端点可能是容器端口（容器id::端口层id），按基节点 id 过滤，删除该节点相关的所有连线
  canvas.connections = canvas.connections.filter(
    ([source, target]) => endpointBaseId(source) !== nodeId && endpointBaseId(target) !== nodeId
  );
  removeEdgeControlsForNode(nodeId);
  if (canvas.selectedNodeId === nodeId) {
    canvas.selectedNodeId = null;
  }
  if (store.connectSourceId && endpointBaseId(store.connectSourceId) === nodeId) {
    cancelPendingConnection();
  }
  void redrawAfterDomUpdate();
  resetValidationAfterGraphChange();
  return true;
}

export function deleteMenuNode(event: Event) {
  event.stopPropagation();
  const nodeId = store.menuNodeId;
  if (!nodeId) return;
  store.menuNodeId = null;
  hideNodeMenu();
  if (deleteNodeById(nodeId)) showToast("success", "节点已删除。");
}


export function deleteMenuConnection(event: Event) {
  event.stopPropagation();
  if (!store.menuConnection) return;

  const [from, to] = store.menuConnection;
  recordHistory();
  activeCanvas().connections = activeCanvas().connections.filter(([source, target]) => !(source === from && target === to));
  removeEdgeControl(from, to);
  store.menuConnection = null;
  activeCanvas().selectedConnectionKey = null;
  hideConnectionMenu();
  resetValidationAfterGraphChange();
  drawLines();
  showToast("success", "连线已删除。");
}


export function deleteConnectionByKey(connectionKey: string): boolean {
  const canvas = activeCanvas();
  const connection = canvas.connections.find(
    ([source, target]) => getConnectionKey(source, target) === connectionKey
  );
  if (!connection) return false;

  const [from, to] = connection;
  recordHistory();
  canvas.connections = canvas.connections.filter(
    ([source, target]) => !(source === from && target === to)
  );
  removeEdgeControl(from, to);
  canvas.selectedConnectionKey = null;
  resetValidationAfterGraphChange();
  drawLines();
  return true;
}


export function deleteSelectedGraphItem(): boolean {
  const canvas = activeCanvas();
  if (canvas.selectedNodeId) {
    const deleted = deleteNodeById(canvas.selectedNodeId);
    if (deleted) showToast("success", "节点已删除。");
    return deleted;
  }
  if (canvas.selectedConnectionKey) {
    const deleted = deleteConnectionByKey(canvas.selectedConnectionKey);
    if (deleted) showToast("success", "连线已删除。");
    return deleted;
  }
  return false;
}


// —————————————————————————————————————————————
// 画布点击 / 拖放 / 缩放
// —————————————————————————————————————————————

export function handleCanvasClick(event: MouseEvent) {
  if (store.suppressNextClick) {
    store.suppressNextClick = false;
    return;
  }

  if (store.isConnecting || store.draggingNodeId) {
    return;
  }

  const target = event.target as Element | null;

  if (target?.closest?.(".node-card")) {
    return;
  }

  if (target?.closest?.(".edge-control, .edge-control-halo, .line-hit-area")) {
    return;
  }

  if (target?.closest?.(".zoom-control, .exit-connect-button")) {
    return;
  }

  // 若当前有选中的连线，点击空白处取消选中并重绘（清掉高亮与控制点）
  const hadConnectionSelected = !!activeCanvas().selectedConnectionKey;
  deselectNode();
  if (hadConnectionSelected) {
    drawLines();
  }
}


export function handleCanvasDrop(event: DragEvent) {
  event.preventDefault();
  const payload = event.dataTransfer?.getData("text/plain");
  if (!payload) return;

  const point = getCanvasPoint(event.clientX, event.clientY);

  // 从组件库拖入"空白容器"：生成一个带 1 进 1 出端口的空容器，等待双击进入编辑
  if (payload === NEW_CONTAINER_PAYLOAD) {
    recordHistory();
    const node = createEmptyContainerNode(activeCanvas(), point.x - 112, point.y - 70);
    activeCanvas().nodes.push(node);
    void redrawAfterDomUpdate();
    selectNode(node.id, { openInspector: false });
    resetValidationAfterGraphChange();
    startContainerCoach(node.id);
    return;
  }

  // 从"我的容器"库拖入：实例化一个已保存的容器
  if (payload.startsWith("container:")) {
    const def = containerLibrary.items.find(item => item.defId === payload.slice("container:".length));
    if (!def) return;
    recordHistory();
    const node = instantiateContainerDef(activeCanvas(), def, point.x - 112, point.y - 70);
    activeCanvas().nodes.push(node);
    void redrawAfterDomUpdate();
    selectNode(node.id, { openInspector: false });
    resetValidationAfterGraphChange();
    showToast("success", `已添加容器 ${def.name}。`);
    startContainerCoach(node.id);
    return;
  }

  // 只接受组件库拖来的已知层类型；忽略浏览器原生拖拽（选中文本、文件等）
  if (!isKnownLayerType(payload)) return;
  const node = addNodeFromLayer(payload, point.x - 112, point.y - 70);
  // Merge 是"合并分支"的进阶概念：拖入时自动播放聚光引导（可勾选不再自动播放）
  if (node.type === "Merge") {
    startMergeCoach(node.id);
  }
}


// —————————————————————————————————————————————
// 自定义容器：进入 / 退出子画板、折叠
// —————————————————————————————————————————————

// 当前是否在编辑某个容器的子画板
export function isEditingContainer(): boolean {
  return activeCanvas().editStack.length > 0;
}

// 面包屑路径：主画布 + 依次进入的各层容器名
export function containerBreadcrumb(): string[] {
  return ["主画布", ...activeCanvas().editStack.map(frame => frame.containerName)];
}

// 双击容器 → 进入其子画板：把父层压栈，画布字段换成容器子图
export function enterContainer(containerId: string) {
  const canvas = activeCanvas();
  const node = canvas.nodes.find(item => item.id === containerId && item.type === CONTAINER_TYPE);
  if (!node || !node.subgraph) return;

  cancelPendingConnection();
  hideNodeMenu();

  canvas.editStack.push({
    containerId,
    containerName: node.title,
    nodes: canvas.nodes,
    connections: canvas.connections,
    edgeControls: canvas.edgeControls,
    nodeCounters: canvas.nodeCounters,
    selectedNodeId: canvas.selectedNodeId,
    selectedConnectionKey: canvas.selectedConnectionKey,
    validationStatus: canvas.validationStatus,
    nodeBadge: canvas.nodeBadge,
    nodeErrors: canvas.nodeErrors,
    inFeatures: canvas.inFeatures,
    zoom: canvas.zoom,
    panX: canvas.panX,
    panY: canvas.panY,
    hasCenteredInitialGraph: canvas.hasCenteredInitialGraph,
  });

  const subgraph = node.subgraph;
  canvas.nodes = subgraph.nodes;
  canvas.connections = subgraph.connections;
  canvas.edgeControls = {};
  canvas.nodeCounters = subgraph.nodeCounters || deriveNodeCounters(subgraph.nodes);
  canvas.selectedNodeId = null;
  canvas.selectedConnectionKey = null;
  canvas.validationStatus = "unvalidated";
  canvas.nodeBadge = "none";
  canvas.nodeErrors = {};
  canvas.validationIssues = [];
  canvas.lastValidationResult = null;
  canvas.validationRequestError = null;
  canvas.hasCenteredInitialGraph = true;
  clearHistory(canvas.id);

  void redrawAfterDomUpdate().then(() => centerGraphInCanvas());
  showToast("info", `进入容器「${node.title}」：单击或拖入层搭建；每个 Input=一个输入端口，每个 Output=一个输出端口。`);
}

// 退出一层：把编辑好的子图写回容器节点，并还原父层
export function exitContainer() {
  const canvas = activeCanvas();
  const frame = canvas.editStack.pop();
  if (!frame) return;

  cancelPendingConnection();
  hideNodeMenu();

  const editedSubgraph = subgraphFromCanvas(canvas.nodes, canvas.connections, canvas.nodeCounters);

  canvas.nodes = frame.nodes;
  canvas.connections = frame.connections;
  canvas.edgeControls = frame.edgeControls;
  canvas.nodeCounters = frame.nodeCounters;
  canvas.selectedNodeId = frame.selectedNodeId;
  canvas.selectedConnectionKey = frame.selectedConnectionKey;
  // 子图改动会使父层校验结果失效，重置为未校验
  canvas.validationStatus = "unvalidated";
  canvas.nodeBadge = "none";
  canvas.nodeErrors = {};
  canvas.validationIssues = [];
  canvas.lastValidationResult = null;
  canvas.validationRequestError = null;
  canvas.inFeatures = frame.inFeatures;
  canvas.zoom = frame.zoom;
  canvas.panX = frame.panX;
  canvas.panY = frame.panY;
  canvas.hasCenteredInitialGraph = frame.hasCenteredInitialGraph;
  // 立刻把恢复的平移/缩放应用到 DOM。否则 DOM 上还是子画板的变换，
  // 随后 drawLines 用 getBoundingClientRect 测量容器端口锚点时会把
  // "旧变换下的屏幕坐标"用"新 pan/zoom"换算，导致连线落点偏离容器端口。
  applyTransform();
  clearHistory(canvas.id);

  const container = canvas.nodes.find(item => item.id === frame.containerId);
  if (container) {
    container.subgraph = editedSubgraph;
    updateNodeDisplay(container);
    pruneStaleContainerPortConnections(canvas, container);
  }

  void redrawAfterDomUpdate();
}

// 从面包屑退回到指定深度（0 = 主画布）
export function exitToDepth(depth: number) {
  while (activeCanvas().editStack.length > depth) {
    exitContainer();
  }
}

// 端口（Input/Output 节点）增删后，清理外层引用了不存在端口的连线
function pruneStaleContainerPortConnections(canvas: WorkCanvas, container: GraphNode) {
  const validPorts = new Set([
    ...containerInputPorts(container).map(port => port.id),
    ...containerOutputPorts(container).map(port => port.id),
  ]);
  canvas.connections = canvas.connections.filter(([source, target]) => {
    for (const endpoint of [source, target]) {
      if (endpointBaseId(endpoint) === container.id) {
        const portId = endpointPortId(endpoint);
        if (portId && !validPorts.has(portId)) return false;
      }
    }
    return true;
  });
}


export function toggleContainerCollapse(nodeId: string) {
  const node = activeCanvas().nodes.find(item => item.id === nodeId);
  if (!node || node.type !== CONTAINER_TYPE) return;
  node.collapsed = !node.collapsed;
  // 折叠态变化会改变卡片高度，需要重绘连线
  void redrawAfterDomUpdate();
}


export function enterContainerFromMenu(event: Event) {
  event.stopPropagation();
  const nodeId = store.menuNodeId;
  hideNodeMenu();
  if (nodeId) enterContainer(nodeId);
}


export function handleZoomAction(actionId: "zoom-out" | "zoom-in" | "reset") {
  const newZoom = actionId === "zoom-in"
    ? Math.min(1.5, Number((activeCanvas().zoom + 0.1).toFixed(2)))
    : actionId === "zoom-out"
      ? Math.max(0.6, Number((activeCanvas().zoom - 0.1).toFixed(2)))
      : 1;

  setZoomAroundViewportCenter(newZoom);
}


// 缩放时保持视口中心对应的画布点不动
function setZoomAroundViewportCenter(newZoom: number) {
  if (!canvasEl) return;

  const centerX = canvasEl.clientWidth / 2;
  const centerY = canvasEl.clientHeight / 2;
  const canvas = activeCanvas();
  const contentX = (centerX - canvas.panX) / canvas.zoom;
  const contentY = (centerY - canvas.panY) / canvas.zoom;

  canvas.zoom = newZoom;
  canvas.panX = centerX - contentX * newZoom;
  canvas.panY = centerY - contentY * newZoom;
  applyTransform();
  pokeMinimap();
}


// —————————————————————————————————————————————
// 节点增删 / 模板加载
// —————————————————————————————————————————————

export function addNodeFromLayer(layerType: string, x: number, y: number): GraphNode {
  recordHistory();
  const node = createNodeConfig(layerType, x, y);
  activeCanvas().nodes.push(node);
  void redrawAfterDomUpdate();
  selectNode(node.id, { openInspector: false });
  resetValidationAfterGraphChange();
  showToast("success", `已添加 ${node.badge} 节点。`);
  return node;
}


// 单击组件库时的推荐落点：空画布放在视口中心；已有节点则放在
// 当前选中节点（没有则最后一个节点）后方，超出右侧视口时自动换到下一行。
function suggestedClickAddPosition(): Point {
  const canvas = activeCanvas();
  if (!canvas.nodes.length) {
    if (!canvasEl) return { x: 80, y: 80 };
    const rect = canvasEl.getBoundingClientRect();
    const center = getCanvasPoint(
      rect.left + canvasEl.clientWidth / 2,
      rect.top + canvasEl.clientHeight / 2
    );
    return { x: center.x - 112, y: center.y - 70 };
  }

  const anchor = canvas.nodes.find(node => node.id === canvas.selectedNodeId)
    ?? canvas.nodes[canvas.nodes.length - 1]!;
  let x = anchor.x + 280;
  let y = anchor.y;
  if (canvasEl) {
    const visibleRight = (canvasEl.clientWidth - canvas.panX) / canvas.zoom;
    if (x + 224 > visibleRight - 24) {
      x = anchor.x;
      y = anchor.y + 210;
    }
  }
  return { x, y };
}


export function addLayerByClick(layerType: string): GraphNode | null {
  if (!isKnownLayerType(layerType)) return null;
  const point = suggestedClickAddPosition();
  const node = addNodeFromLayer(layerType, point.x, point.y);
  if (node.type === "Merge") startMergeCoach(node.id);
  return node;
}


export function addEmptyContainerByClick(): GraphNode {
  const point = suggestedClickAddPosition();
  recordHistory();
  const node = createEmptyContainerNode(activeCanvas(), point.x, point.y);
  activeCanvas().nodes.push(node);
  void redrawAfterDomUpdate();
  selectNode(node.id, { openInspector: false });
  resetValidationAfterGraphChange();
  showToast("success", "已添加空白容器。");
  startContainerCoach(node.id);
  return node;
}


export function addSavedContainerByClick(defId: string): GraphNode | null {
  const def = containerLibrary.items.find(item => item.defId === defId);
  if (!def) return null;
  const point = suggestedClickAddPosition();
  recordHistory();
  const node = instantiateContainerDef(activeCanvas(), def, point.x, point.y);
  activeCanvas().nodes.push(node);
  void redrawAfterDomUpdate();
  selectNode(node.id, { openInspector: false });
  resetValidationAfterGraphChange();
  showToast("success", `已添加容器 ${def.name}。`);
  startContainerCoach(node.id);
  return node;
}


function createNodeConfig(layerType: string, x: number, y: number): GraphNode {
  const config = getLayerConfig(layerType);
  const type = config.type;
  activeCanvas().nodeCounters[type] = (activeCanvas().nodeCounters[type] || 0) + 1;
  const id = `${type.toLowerCase()}_${activeCanvas().nodeCounters[type]}`;
  // 自由画布：新节点直接落在拖放位置，不做边界限制
  const canvasX = x;
  const canvasY = y;

  // 新建的 Input 默认形状跟随当前数据集（如 MNIST→[1,28,28]、CIFAR→[3,32,32]）
  const params = { ...config.params };
  if (type === "Input") {
    params.shape = datasetInputShape();
  }
  const hint = type === "Input" && Array.isArray(params.shape)
    ? (params.shape as number[]).join("x")
    : (config.hint || "?");

  return {
    id,
    type,
    title: config.title,
    badge: config.badge,
    color: config.color,
    // 配置未提供说明时，用参数摘要生成（序列与高级层）
    note: config.note ?? (Object.keys(config.params).length ? formatLayerNote({ params: config.params }) : undefined),
    hint,
    x: canvasX,
    y: canvasY,
    params,
  };
}


export function applyTemplateGraph(modelGraph: ModelGraph) {
  recordHistory();
  const centeredX = Math.max(40, ((canvasEl?.clientWidth || 0) - 224) / 2);

  activeCanvas().nodes = modelGraph.layers.map((layer, index) => {
    const config = getLayerConfig(layer.type);
    return {
      id: layer.id,
      type: layer.type,
      title: layer.name || config.title || layer.type,
      badge: config.badge || layer.type,
      color: config.color || "cyan",
      note: formatLayerNote(layer),
      hint: "?",
      x: centeredX,
      y: 60 + index * 205,
      params: { ...(layer.params || {}) },
    };
  });
  activeCanvas().connections = modelGraph.connections.map(connection => [connection.source, connection.target] as Connection);
  activeCanvas().selectedNodeId = null;
  activeCanvas().edgeControls = {};
  activeCanvas().selectedConnectionKey = null;
  activeCanvas().hasCenteredInitialGraph = true;
  // 内置模板、AI 生成模型和已保存项目统一经过智能布局；以后新增模板无需手写坐标。
  layoutGraphNodes(activeCanvas());
  void redrawAfterDomUpdate().then(() => {
    centerGraphHorizontally();
    pokeMinimap();
  });
  resetValidationAfterGraphChange();
}


// 清空当前画布上的模型（节点、连线、选中、校验态一并重置）。
// 返回是否确实清空了内容（本来就空则返回 false，便于调用方提示"无需清空"）。
export function clearActiveCanvas(): boolean {
  const canvas = activeCanvas();
  if (canvas.nodes.length === 0 && canvas.connections.length === 0) return false;
  recordHistory();
  canvas.nodes = [];
  canvas.connections = [];
  canvas.edgeControls = {};
  canvas.nodeErrors = {};
  canvas.selectedNodeId = null;
  canvas.selectedConnectionKey = null;
  void redrawAfterDomUpdate();
  resetValidationAfterGraphChange();
  return true;
}


// —————————————————————————————————————————————
// 选中状态
// —————————————————————————————————————————————

export function selectNode(nodeId: string, options: { openInspector?: boolean } = {}) {
  const canvas = activeCanvas();
  canvas.selectedNodeId = nodeId;
  canvas.selectedConnectionKey = null;
  ui.inspectorFocusParam = null;
  // 新增/粘贴节点时仅保留选中反馈，避免面板遮住刚落下的节点；
  // 用户明确点击节点或检查问题时再展开。
  ui.inspectorCollapsed = options.openInspector === false;
}


export function deselectNode() {
  activeCanvas().selectedNodeId = null;
  activeCanvas().selectedConnectionKey = null;
}


// 结构检查的问题定位：选中节点、将它移到未被参数面板遮挡的可视区中心，
// 同时展开面板并请求滚动到相关参数字段。
export function focusNodeInCanvas(nodeId: string, parameter: string | null = null): boolean {
  const canvas = activeCanvas();
  const node = canvas.nodes.find(item => item.id === nodeId);
  if (!node) return false;

  selectNode(nodeId);
  ui.inspectorFocusParam = parameter;

  if (canvasEl) {
    const inspectorReserve = 360;
    const visibleWidth = Math.max(320, canvasEl.clientWidth - inspectorReserve);
    const nodeCenterX = node.x + 112;
    const nodeCenterY = node.y + 75;
    canvas.panX = visibleWidth / 2 - nodeCenterX * canvas.zoom;
    canvas.panY = canvasEl.clientHeight / 2 - nodeCenterY * canvas.zoom;
    applyTransform();
    pokeMinimap();
    void redrawAfterDomUpdate();
  }
  return true;
}


// —————————————————————————————————————————————
// 画布定位
// —————————————————————————————————————————————

// 将画布平移到节点处，使整个模型图在视口中居中（缩放级别保持不变）
export function centerGraphInCanvas() {
  const canvas = activeCanvas();
  if (!canvasEl || canvas.nodes.length === 0) return;

  const bounds = getGraphBounds();
  const graphCenterX = (bounds.left + bounds.right) / 2;
  const graphCenterY = (bounds.top + bounds.bottom) / 2;

  canvas.panX = canvasEl.clientWidth / 2 - graphCenterX * canvas.zoom;
  canvas.panY = canvasEl.clientHeight / 2 - graphCenterY * canvas.zoom;
  applyTransform();
}


// 初始加载 / 模板加载：能完整显示时水平居中；多列宽于视口时从 Input 一侧开始，
// 避免居中后首尾同时被裁掉。竖向始终回到图的顶部。
function centerGraphHorizontally() {
  const canvas = activeCanvas();
  if (!canvasEl || canvas.nodes.length === 0) return;

  const bounds = getGraphBounds();
  const graphCenterX = (bounds.left + bounds.right) / 2;
  const graphWidth = bounds.right - bounds.left;
  const visibleWidth = canvasEl.clientWidth / canvas.zoom;

  canvas.panX = graphWidth <= visibleWidth - 80
    ? canvasEl.clientWidth / 2 - graphCenterX * canvas.zoom
    : 40 - bounds.left * canvas.zoom;
  canvas.panY = 0;
  applyTransform();
}


function getGraphBounds() {
  return activeCanvas().nodes.reduce(
    (bounds, node) => ({
      left: Math.min(bounds.left, node.x),
      top: Math.min(bounds.top, node.y),
      right: Math.max(bounds.right, node.x + 224),
      bottom: Math.max(bounds.bottom, node.y + 150),
    }),
    {
      left: Infinity,
      top: Infinity,
      right: -Infinity,
      bottom: -Infinity,
    }
  );
}
