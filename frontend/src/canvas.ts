// 画布交互引擎：节点拖拽、连线、贝塞尔曲线绘制、缩放、右键菜单定位。
// 连线层（SVG）涉及大量测量与逐帧重绘，保持命令式实现；节点卡片由 Vue 响应式渲染。

import { nextTick } from "vue";
import {
  activeCanvas,
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


export function closeCanvas(id: number) {
  if (store.canvases.length <= 1) {
    showToast("warning", "至少保留一个画布。");
    return;
  }

  const index = store.canvases.findIndex(canvas => canvas.id === id);
  const canvas = store.canvases[index];
  if (!canvas) return;

  const isTraining = isTrainingJobActive(canvas.trainingJob);
  if (canvas.nodes.length > 0 || isTraining) {
    const message = isTraining
      ? `${canvas.name} 有训练任务进行中，关闭后将不再跟踪其进度。确定关闭？`
      : `确定关闭 ${canvas.name}？画布上的模型将被丢弃。`;
    if (!window.confirm(message)) return;
  }

  store.canvases.splice(index, 1);
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
    visiblePath.setAttribute(
      "class",
      `line-connector${isSelected ? " line-selected" : ""}${flowingAll ? " line-flow-track" : ""}`
    );
    visiblePath.dataset.from = from;
    visiblePath.dataset.to = to;

    hitPath.setAttribute("d", connector.d);
    hitPath.setAttribute("class", "line-hit-area");
    hitPath.dataset.from = from;
    hitPath.dataset.to = to;
    hitPath.addEventListener("mouseenter", () => visiblePath.classList.add("line-hover"));
    hitPath.addEventListener("mouseleave", () => visiblePath.classList.remove("line-hover"));
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


// 节点增删后需等 Vue 更新 DOM 再重绘（需要测量节点尺寸）
export async function redrawAfterDomUpdate() {
  await nextTick();
  drawLines();
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
// 自动布局：分层（拓扑最长路径）+ 层内重心法排序，把 DAG 排整齐
// —————————————————————————————————————————————

export function autoLayoutGraph() {
  const canvas = activeCanvas();
  const nodes = canvas.nodes;
  if (nodes.length === 0) {
    showToast("info", "画布上还没有节点。");
    return;
  }
  recordHistory();

  const ids = nodes.map(node => node.id);
  const preds: Record<string, string[]> = {};
  const succ: Record<string, string[]> = {};
  ids.forEach(id => {
    preds[id] = [];
    succ[id] = [];
  });
  canvas.connections.forEach(([from, to]) => {
    if (preds[to]) preds[to].push(from);
    if (succ[from]) succ[from].push(to);
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

  // 4) 落位：竖直方向按层、水平方向层内居中对齐
  const NODE_W = 224;
  const V_GAP = 205;
  const H_GAP = 64;
  const TOP = 60;
  const widestRow = Math.max(...layers.map(row => row.length));
  const centerX = 40 + (widestRow * NODE_W + (widestRow - 1) * H_GAP) / 2;
  layers.forEach((row, depth) => {
    const rowWidth = row.length * NODE_W + (row.length - 1) * H_GAP;
    const startX = centerX - rowWidth / 2;
    row.forEach((id, i) => {
      const node = nodes.find(item => item.id === id);
      if (!node) return;
      node.x = Math.round(startX + i * (NODE_W + H_GAP));
      node.y = TOP + depth * V_GAP;
    });
  });

  void redrawAfterDomUpdate();
  centerGraphInCanvas();
  showToast("success", "已按数据流向自动分层排列。");
}


function getConnectionPoints(from: string, to: string, index = 0): ConnectorPoints | null {
  // from/to 是"端点"：普通层为节点 id，容器端口为 容器id::端口层id
  if (
    !activeCanvas().nodes.some(node => node.id === endpointBaseId(from)) ||
    !activeCanvas().nodes.some(node => node.id === endpointBaseId(to))
  ) {
    return null;
  }

  return {
    from,
    to,
    key: getConnectionKey(from, to),
    index,
    start: getEndpointOutPoint(from),
    end: getEndpointInPoint(to),
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

  if (controlPoint) {
    return buildControlledBezierSegments(start, controlPoint, end);
  }

  const nodeHeight = 150;
  const rawDeltaY = Math.abs(end.y - start.y);
  const yDistance = Math.max(24, rawDeltaY);
  const yDirection = end.y >= start.y ? 1 : -1;
  const isLongConnection = rawDeltaY > nodeHeight * 1.5;
  const bowX = isLongConnection ? rawDeltaY * 0.3 * getBezierBowDirection(points) : 0;
  const verticalControl = isLongConnection
    ? rawDeltaY * 0.4
    : clamp(yDistance * 0.42, 42, 120);

  return [
    {
      start,
      c1: {
        x: start.x + bowX,
        y: start.y + yDirection * verticalControl,
      },
      c2: {
        x: end.x + bowX,
        y: end.y - yDirection * verticalControl,
      },
      end,
    },
  ];
}


function buildControlledBezierSegments(start: Point, control: Point, end: Point): BezierSegment[] {
  return [
    buildBezierSegment(start, control),
    buildBezierSegment(control, end),
  ];
}


function buildBezierSegment(start: Point, end: Point): BezierSegment {
  const deltaY = Math.abs(end.y - start.y);
  const yDirection = end.y >= start.y ? 1 : -1;
  const verticalControl = clamp(deltaY * 0.42, 28, 120);

  return {
    start,
    c1: {
      x: start.x,
      y: start.y + yDirection * verticalControl,
    },
    c2: {
      x: end.x,
      y: end.y - yDirection * verticalControl,
    },
    end,
  };
}


function getBezierBowDirection(points: { start: Point; end: Point }) {
  const deltaX = points.end.x - points.start.x;

  if (Math.abs(deltaX) > 4) {
    return deltaX > 0 ? 1 : -1;
  }

  return 1;
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
  store.menuNodeId = nodeId;
  hideConnectionMenu();
  store.nodeMenu = { visible: true, x: clientX, y: clientY };
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


export function deleteMenuNode(event: Event) {
  event.stopPropagation();
  const nodeId = store.menuNodeId;
  if (!nodeId) return;

  recordHistory();
  activeCanvas().nodes = activeCanvas().nodes.filter(node => node.id !== nodeId);
  // 端点可能是容器端口（容器id::端口层id），按基节点 id 过滤，删除该节点相关的所有连线
  activeCanvas().connections = activeCanvas().connections.filter(
    ([source, target]) => endpointBaseId(source) !== nodeId && endpointBaseId(target) !== nodeId
  );
  removeEdgeControlsForNode(nodeId);
  if (activeCanvas().selectedNodeId === nodeId) {
    activeCanvas().selectedNodeId = null;
  }
  if (store.connectSourceId && endpointBaseId(store.connectSourceId) === nodeId) {
    cancelPendingConnection();
  }
  store.menuNodeId = null;
  hideNodeMenu();
  void redrawAfterDomUpdate();
  resetValidationAfterGraphChange();
  showToast("success", "节点已删除。");
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
    selectNode(node.id);
    resetValidationAfterGraphChange();
    showToast("info", "已放入空白容器：双击它进入子画板，像搭模型一样拖入层，用 Input/Output 定义输入输出端口。");
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
    selectNode(node.id);
    resetValidationAfterGraphChange();
    showToast("success", `已添加容器 ${def.name}。`);
    return;
  }

  // 只接受组件库拖来的已知层类型；忽略浏览器原生拖拽（选中文本、文件等）
  if (!isKnownLayerType(payload)) return;
  addNodeFromLayer(payload, point.x - 112, point.y - 70);
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
  canvas.hasCenteredInitialGraph = true;
  clearHistory(canvas.id);

  void redrawAfterDomUpdate().then(() => centerGraphInCanvas());
  showToast("info", `进入容器「${node.title}」：拖入层搭建；每个 Input=一个输入端口，每个 Output=一个输出端口。`);
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
  canvas.inFeatures = frame.inFeatures;
  canvas.zoom = frame.zoom;
  canvas.panX = frame.panX;
  canvas.panY = frame.panY;
  canvas.hasCenteredInitialGraph = frame.hasCenteredInitialGraph;
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


export function handleZoomAction(actionId: "zoom-out" | "zoom-in") {
  const newZoom = actionId === "zoom-in"
    ? Math.min(1.5, Number((activeCanvas().zoom + 0.1).toFixed(2)))
    : Math.max(0.6, Number((activeCanvas().zoom - 0.1).toFixed(2)));

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
}


// —————————————————————————————————————————————
// 节点增删 / 模板加载
// —————————————————————————————————————————————

export function addNodeFromLayer(layerType: string, x: number, y: number) {
  recordHistory();
  const node = createNodeConfig(layerType, x, y);
  activeCanvas().nodes.push(node);
  void redrawAfterDomUpdate();
  selectNode(node.id);
  resetValidationAfterGraphChange();
  showToast("success", `已添加 ${node.badge} 节点。`);
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
  void redrawAfterDomUpdate().then(centerGraphHorizontally);
  resetValidationAfterGraphChange();
}


// —————————————————————————————————————————————
// 选中状态
// —————————————————————————————————————————————

export function selectNode(nodeId: string) {
  const canvas = activeCanvas();
  canvas.selectedNodeId = nodeId;
  canvas.selectedConnectionKey = null;
  // 点击节点卡片时重新展开参数面板
  ui.inspectorCollapsed = false;
}


export function deselectNode() {
  activeCanvas().selectedNodeId = null;
  activeCanvas().selectedConnectionKey = null;
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


// 初始加载 / 模板加载：水平居中并回到图的顶部（保持旧版首屏视角）
function centerGraphHorizontally() {
  const canvas = activeCanvas();
  if (!canvasEl || canvas.nodes.length === 0) return;

  const bounds = getGraphBounds();
  const graphCenterX = (bounds.left + bounds.right) / 2;

  canvas.panX = canvasEl.clientWidth / 2 - graphCenterX * canvas.zoom;
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
