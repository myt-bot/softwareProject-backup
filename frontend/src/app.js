import {
  createProject,
  exportPytorchCode,
  fetchDevices,
  fetchProjectTemplate,
  fetchProjectTemplates,
  fetchTrainingResult,
  fetchTrainingStatus,
  isBackendNotImplemented,
  startTraining,
  validateModel,
} from "./api/client.js";
import { openTrainingMonitor } from "./training.js";

const datasetOptions = {
  MNIST: { shapeLabel: "(1x28x28)" },
  FashionMNIST: { shapeLabel: "(1x28x28)" },
  KMNIST: { shapeLabel: "(1x28x28)" },
  CIFAR10: { shapeLabel: "(3x32x32)" },
  CIFAR100: { shapeLabel: "(3x32x32)" },
};


const layerGroups = [
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

let nodes = [
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

let connections = [
  ["input", "conv"],
  ["conv", "pool"],
  ["pool", "flatten"],
  ["flatten", "linear"],
  ["linear", "output"],
];

const state = {
  selectedNodeId: null,
  validationStatus: "unvalidated",
  inFeatures: 1024,
  jobId: null,
  lastExportCode: "",
  trainingPollTimer: null,
  trainingJob: null,
  isConnecting: false,
  connectSourceId: null,
  pendingConnection: null,
  suppressNextClick: false,
  menuConnection: null,
  menuNodeId: null,
  selectedConnectionKey: null,
  draggingEdgeControlKey: null,
  edgeControls: {},
  dragCandidate: null,
  draggingNodeId: null,
  dragOffsetX: 0,
  dragOffsetY: 0,
  nodeCounters: {},
  zoom: 1,
  hasCenteredInitialGraph: false,
};


function initializeApp() {
  initializeLayerPalette();
  initializeCanvas();
  initializeInspector();
  initializeDatasetSelector();
  initializeTrainingJobPanel();
  bindEvents();
  loadDevices();
  loadProjectTemplates();
  setTimeout(() => {
    drawLines();
    centerGraphInCanvas();
    updateFloatingControlPositions();
  }, 100);
}


function initializeDatasetSelector() {
  updateSelectedDatasetDisplay();

  const dropdown = document.getElementById("custom-dataset-dropdown");
  const nativeSelect = document.getElementById("dataset-select");
  const displayValue = document.getElementById("custom-select-value");

  // 安全检查：如果没找到对应DOM元素则直接返回，防止JS崩溃
  if (!dropdown || !nativeSelect || !displayValue) {
    console.error("未找到下拉菜单的相关DOM节点。");
    return;
  }

  const options = dropdown.querySelectorAll(".custom-option");

  // 点击展开/收起下拉菜单 (阻止冒泡非常关键，否则会被 document 的 click 瞬间关掉)
  dropdown.addEventListener("click", (e) => {
    e.stopPropagation();
    dropdown.classList.toggle("open");
  });

  // 点击页面其他区域时关闭下拉菜单
  document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target)) {
      dropdown.classList.remove("open");
    }
  });

  // 选中某一个选项的处理逻辑
  options.forEach(option => {
    option.addEventListener("click", (e) => {
      e.stopPropagation(); // 阻止冒泡，避免触发上方 dropdown 的 toggle
      const value = option.dataset.value;

      // 1. 更新下拉菜单的 UI 高亮状态
      options.forEach(opt => opt.classList.remove("active"));
      option.classList.add("active");
      displayValue.textContent = value;

      // 2. 将值同步给隐藏的原生 select
      nativeSelect.value = value;

      // 3. 手动派发 change 事件，触发 app.js 原有的形状自动同步逻辑
      nativeSelect.dispatchEvent(new Event("change"));

      // 4. 收起下拉菜单
      dropdown.classList.remove("open");
    });
  });
}


function initializeLayerPalette() {
  const palette = document.getElementById("layer-palette");
  palette.innerHTML = layerGroups.map(group => `
    <section class="layer-group">
      <h3>${group.title}</h3>
      <div class="layer-items">
        ${group.layers.map(layer => `
          <article class="layer-item" data-layer-type="${layer.type}" draggable="true">
            <iconify-icon class="text-${layer.color}" icon="${layer.icon}"></iconify-icon>
            <div>
              <strong>${layer.type}</strong>
              <span>${layer.desc}</span>
            </div>
          </article>
        `).join("")}
      </div>
    </section>
  `).join("");
}


function initializeCanvas() {
  centerInitialNodesInViewport();
  updateCanvasSize();
  renderCanvasNodes();
}


function renderCanvasNodes() {
  const container = document.getElementById("nodes-container");
  container.innerHTML = nodes.map(node => `
    <article class="node-card" id="node-${node.id}" data-node-id="${node.id}" style="left: ${node.x}px; top: ${node.y}px;">
      <div class="node-head">
        <span class="node-type ${node.color}">${node.badge}</span>
        <span class="status-badge">未校验</span>
      </div>
      <h4>${node.title}</h4>
      ${node.note ? `<p class="node-note">${node.note}</p>` : ""}
      <div class="shape-row">
        <span>Shape Hint:</span>
        <strong class="shape-value">${node.hint}</strong>
      </div>
    </article>
  `).join("");
  bindCanvasNodeEvents();
  drawLines();
}


function centerInitialNodesInViewport() {
  if (state.hasCenteredInitialGraph) return;

  const canvas = document.getElementById("canvas-container");
  if (!canvas || canvas.clientWidth === 0) return;

  const nodeWidth = 224;
  const centeredX = Math.max(40, (canvas.clientWidth - nodeWidth) / 2);
  nodes = nodes.map(node => ({
    ...node,
    x: centeredX,
  }));
  state.hasCenteredInitialGraph = true;
}


function initializeInspector() {
  document.getElementById("inspector-content").innerHTML = `
    <div class="empty-inspector">
      <iconify-icon icon="mdi:cursor-default-click-outline"></iconify-icon>
      <p>未选中节点</p>
      <span>点击画布中的节点查看或编辑参数</span>
    </div>
  `;
}


function bindEvents() {
  window.addEventListener("resize", () => {
    drawLines();
    updateFloatingControlPositions();
  });
  document.getElementById("canvas-container").addEventListener("scroll", () => {
    hideConnectionMenu();
    hideNodeMenu();
    drawLines();
    updateFloatingControlPositions();
  });

  document.addEventListener("mousemove", handleDocumentMouseMove);
  document.addEventListener("mouseup", handleDocumentMouseUp);
  document.addEventListener("click", () => {
    hideConnectionMenu();
    hideNodeMenu();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      cancelPendingConnection();
      hideConnectionMenu();
      hideNodeMenu();
    }
  });

  document.getElementById("btn-validate").addEventListener("click", handleValidateModel);
  document.getElementById("btn-save").addEventListener("click", handleSaveProject);
  document.getElementById("btn-export").addEventListener("click", handleExportCode);
  document.getElementById("btn-train").addEventListener("click", handleStartTraining);
  document.getElementById("btn-view-training")?.addEventListener("click", openCurrentTrainingMonitor);
  document.getElementById("dataset-select")?.addEventListener("change", () => {
    updateSelectedDatasetDisplay();
  });
  document.getElementById("btn-help").addEventListener("click", () => {
    showToast("info", "这是 MNIST-CNN 模型搭建页，功能按钮已接入后端接口。");
  });

  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("btn-cancel-modal").addEventListener("click", closeModal);
  document.getElementById("btn-copy-code").addEventListener("click", copyExportCode);
  document.getElementById("btn-download-code").addEventListener("click", downloadExportCode);
  document.getElementById("btn-delete-connection").addEventListener("click", deleteMenuConnection);
  document.getElementById("btn-connect-node").addEventListener("click", connectFromMenuNode);
  document.getElementById("btn-delete-node").addEventListener("click", deleteMenuNode);
  document.getElementById("btn-exit-connect").addEventListener("click", () => {
    cancelPendingConnection();
    showToast("info", "已退出连线模式。");
  });
  document.querySelectorAll(".layer-item").forEach(item => {
    item.addEventListener("dragstart", handlePaletteDragStart);
  });

  const canvas = document.getElementById("canvas-container");
  canvas.addEventListener("click", handleCanvasClick);
  canvas.addEventListener("dragover", event => event.preventDefault());
  canvas.addEventListener("drop", handleCanvasDrop);

  document.querySelectorAll("[data-template]").forEach(button => {
    button.addEventListener("click", () => loadTemplateToCanvas(button.dataset.template));
  });

  ["zoom-out", "zoom-in", "zoom-fit"].forEach(id => {
    document.getElementById(id).addEventListener("click", () => handleZoomAction(id));
  });
}


function initializeTrainingJobPanel() {
  updateTrainingJobPanel();
}


function getSelectedDatasetName() {
  return document.getElementById("dataset-select")?.value || "MNIST";
}


function updateSelectedDatasetDisplay() {
  const datasetName = getSelectedDatasetName();
  const datasetShape = document.getElementById("dataset-shape");
  if (datasetShape) {
    datasetShape.textContent = datasetOptions[datasetName]?.shapeLabel || "";
  }
}


function bindCanvasNodeEvents() {
  document.querySelectorAll(".node-card").forEach(node => {
    node.addEventListener("mousedown", handleNodeMouseDown);
    node.addEventListener("click", event => {
      if (state.isConnecting) {
        event.preventDefault();
        completeConnection(node.dataset.nodeId);
        cancelPendingConnection();
        return;
      }
      if (state.suppressNextClick) {
        state.suppressNextClick = false;
        event.preventDefault();
        return;
      }
      selectNode(node.dataset.nodeId);
    });
    node.addEventListener("contextmenu", event => {
      event.preventDefault();
      event.stopPropagation();
      if (state.isConnecting) return;
      showNodeMenu(event.clientX, event.clientY, node.dataset.nodeId);
    });
  });
}


async function loadDevices() {
  try {
    const devices = await fetchDevices();
    if (devices?.default_device) {
      showToast("success", `后端设备已连接: ${devices.default_device}`);
    }
  } catch (error) {
    showBackendError(error, "设备接口暂未实现。");
  }
}


function drawLines() {
  const svg = document.getElementById("connections-svg");
  svg.innerHTML = "";
  const renderedConnectors = [];
  const hitPaths = [];
  const bridges = [];
  const connectorsByKey = {};

  connections.forEach(([from, to], connectionIndex) => {
    const points = getConnectionPoints(from, to, connectionIndex);
    if (!points) return;

    const connector = buildConnector(points);
    connectorsByKey[connector.key] = connector;
    bridges.push(...findConnectorBridges(connector, renderedConnectors));
    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const visiblePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");

    visiblePath.setAttribute("d", connector.d);
    visiblePath.setAttribute(
      "class",
      `line-connector${state.selectedConnectionKey === connector.key ? " line-selected" : ""}`
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
    svg.appendChild(group);
    hitPaths.push(hitPath);
    renderedConnectors.push(connector);
  });

  renderLineJumps(svg, bridges);
  hitPaths.forEach(hitPath => svg.appendChild(hitPath));
  renderEdgeControlPoints(svg, connectorsByKey);
}


function handleNodeMouseDown(event) {
  if (event.button !== 0) return;
  if (state.isConnecting) return;

  const nodeId = event.currentTarget.dataset.nodeId;
  const node = nodes.find(item => item.id === nodeId);
  const point = getCanvasPoint(event.clientX, event.clientY);
  hideConnectionMenu();
  hideNodeMenu();
  state.dragCandidate = {
    nodeId,
    startClientX: event.clientX,
    startClientY: event.clientY,
  };
  state.dragOffsetX = point.x - (node?.x || 0);
  state.dragOffsetY = point.y - (node?.y || 0);
}


function handleDocumentMouseMove(event) {
  if (state.draggingEdgeControlKey) {
    dragEdgeControlToPointer(event.clientX, event.clientY);
    return;
  }

  if (state.draggingNodeId) {
    dragNodeToPointer(event.clientX, event.clientY);
    return;
  }

  if (state.dragCandidate && !state.isConnecting) {
    if ((event.buttons & 1) !== 1) {
      state.dragCandidate = null;
      return;
    }

    const moved = Math.hypot(
      event.clientX - state.dragCandidate.startClientX,
      event.clientY - state.dragCandidate.startClientY
    );
    if (moved > 5) {
      startNodeDrag(state.dragCandidate.nodeId);
      dragNodeToPointer(event.clientX, event.clientY);
      return;
    }
  }

  if (!state.isConnecting) return;
  updatePendingConnection(event.clientX, event.clientY);
  updateConnectionTargetState(event.clientX, event.clientY);
}


function handleDocumentMouseUp(event) {
  state.dragCandidate = null;

  if (state.draggingEdgeControlKey) {
    finishEdgeControlDrag();
    return;
  }

  if (state.draggingNodeId) {
    finishNodeDrag();
    return;
  }
}


function startNodeDrag(nodeId) {
  state.draggingNodeId = nodeId;
  state.suppressNextClick = true;
  document.body.classList.add("is-node-dragging");
  document.getElementById(`node-${nodeId}`)?.classList.add("node-dragging");
}


function dragNodeToPointer(clientX, clientY) {
  const node = nodes.find(item => item.id === state.draggingNodeId);
  const element = document.getElementById(`node-${state.draggingNodeId}`);
  if (!node || !element) return;

  const point = getCanvasPoint(clientX, clientY);
  const maxX = Math.max(40, getCanvasWidth() - element.offsetWidth - 40);
  const maxY = Math.max(40, getCanvasHeight() - element.offsetHeight - 40);
  node.x = clamp(point.x - state.dragOffsetX, 40, maxX);
  node.y = clamp(point.y - state.dragOffsetY, 40, maxY);
  element.style.left = `${node.x}px`;
  element.style.top = `${node.y}px`;
  drawLines();
}


function finishNodeDrag() {
  document.getElementById(`node-${state.draggingNodeId}`)?.classList.remove("node-dragging");
  state.draggingNodeId = null;
  state.dragCandidate = null;
  document.body.classList.remove("is-node-dragging");
  state.suppressNextClick = true;
  resetValidationAfterGraphChange();
  updateCanvasSize();
  drawLines();
}


function beginConnection(sourceId, clientX, clientY) {
  state.isConnecting = true;
  state.connectSourceId = sourceId;
  state.suppressNextClick = false;

  document.body.classList.add("is-connecting");
  document.getElementById(`node-${sourceId}`).classList.add("connection-source");
  document.getElementById("btn-exit-connect").classList.remove("hidden");
  updateFloatingControlPositions();
  createPendingConnection();
  updatePendingConnection(clientX, clientY);
  showToast("info", "已进入连线模式，点击目标节点即可连线。");
}


function createPendingConnection() {
  const svg = document.getElementById("connections-svg");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("class", "line-connector pending-connector");
  path.id = "pending-connector";
  svg.appendChild(path);
  state.pendingConnection = path;
}


function updatePendingConnection(clientX, clientY) {
  if (!state.pendingConnection || !state.connectSourceId) return;
  if (!state.pendingConnection.isConnected) {
    createPendingConnection();
  }

  const start = getNodeBottomCenter(state.connectSourceId);
  const end = getCanvasPoint(clientX, clientY);

  state.pendingConnection.setAttribute(
    "d",
    buildConnector({ start, end }).d
  );
}


function updateConnectionTargetState(clientX, clientY) {
  document.querySelectorAll(".node-card").forEach(node => {
    node.classList.remove("connection-target");
  });

  const target = getNodeFromPoint(clientX, clientY);
  if (target && target.dataset.nodeId !== state.connectSourceId) {
    target.classList.add("connection-target");
  }
}


function completeConnection(targetId) {
  const sourceId = state.connectSourceId;
  if (!sourceId || sourceId === targetId) {
    showToast("warning", "不能将节点连接到自身。");
    return;
  }

  const exists = connections.some(([source, target]) => source === sourceId && target === targetId);
  if (exists) {
    showToast("warning", "这两个节点之间已经存在连线。");
    return;
  }

  connections = [...connections, [sourceId, targetId]];
  resetValidationAfterGraphChange();
  drawLines();
  showToast("success", "连线成功。");
}


function cancelPendingConnection() {
  state.isConnecting = false;
  state.connectSourceId = null;
  state.pendingConnection?.remove();
  state.pendingConnection = null;
  document.getElementById("btn-exit-connect").classList.add("hidden");
  document.body.classList.remove("is-connecting");
  document.querySelectorAll(".node-card").forEach(node => {
    node.classList.remove("connection-source", "connection-target");
  });
}


function getNodeBottomCenter(nodeId) {
  const node = nodes.find(item => item.id === nodeId);
  const rect = getNodeRect(nodeId);
  if (!node || !rect) {
    return { x: 0, y: 0 };
  }

  return {
    x: node.x + rect.width / 2,
    y: node.y + rect.height,
  };
}


function getNodeTopCenter(nodeId) {
  const node = nodes.find(item => item.id === nodeId);
  const rect = getNodeRect(nodeId);
  if (!node || !rect) {
    return { x: 0, y: 0 };
  }

  return {
    x: node.x + rect.width / 2,
    y: node.y,
  };
}


function getConnectionPoints(from, to, index = 0) {
  if (!nodes.some(node => node.id === from) || !nodes.some(node => node.id === to)) {
    return null;
  }

  return {
    from,
    to,
    key: getConnectionKey(from, to),
    index,
    start: getNodeBottomCenter(from),
    end: getNodeTopCenter(to),
  };
}


function buildConnector(points) {
  const segments = buildBezierSegments(points);
  return {
    ...points,
    key: points.key || getConnectionKey(points.from, points.to),
    segments,
    d: buildBezierPath(segments),
    samples: sampleBezierSegments(segments, 24),
  };
}


function buildBezierSegments(points) {
  const { start, end } = points;
  const controlPoint = points.key ? state.edgeControls[points.key] : null;

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


function buildControlledBezierSegments(start, control, end) {
  return [
    buildBezierSegment(start, control),
    buildBezierSegment(control, end),
  ];
}


function buildBezierSegment(start, end) {
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


function getBezierBowDirection(points) {
  const deltaX = points.end.x - points.start.x;

  if (Math.abs(deltaX) > 4) {
    return deltaX > 0 ? 1 : -1;
  }

  return 1;
}


function buildBezierPath(segments) {
  if (segments.length === 0) return "";

  const [firstSegment, ...remainingSegments] = segments;
  const commands = [
    `M ${firstSegment.start.x} ${firstSegment.start.y}`,
    cubicCommand(firstSegment),
  ];

  remainingSegments.forEach(segment => {
    commands.push(cubicCommand(segment));
  });

  return commands.join(" ");
}


function cubicCommand(segment) {
  return `C ${segment.c1.x} ${segment.c1.y}, ${segment.c2.x} ${segment.c2.y}, ${segment.end.x} ${segment.end.y}`;
}


function sampleBezierSegments(segments, stepsPerSegment) {
  const samples = [];

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


function getCubicPoint(segment, t) {
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


function findConnectorBridges(connector, previousConnectors) {
  const bridges = [];

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


function findPolylineIntersections(currentSamples, previousSamples) {
  const intersections = [];

  for (let currentIndex = 0; currentIndex < currentSamples.length - 1; currentIndex += 1) {
    const currentStart = currentSamples[currentIndex];
    const currentEnd = currentSamples[currentIndex + 1];

    for (let previousIndex = 0; previousIndex < previousSamples.length - 1; previousIndex += 1) {
      const previousStart = previousSamples[previousIndex];
      const previousEnd = previousSamples[previousIndex + 1];
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


function getSegmentIntersection(a1, a2, b1, b2) {
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


function isNearConnectorEndpoint(connector, point) {
  return getDistance(connector.start, point) < 30 || getDistance(connector.end, point) < 30;
}


function getSegmentTangent(start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;

  return {
    x: dx / length,
    y: dy / length,
  };
}


function getDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}


function renderLineJumps(svg, bridges) {
  bridges.forEach(bridge => {
    const radius = 6;
    const gap = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    const arc = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const start = {
      x: bridge.point.x - bridge.tangent.x * radius,
      y: bridge.point.y - bridge.tangent.y * radius,
    };
    const end = {
      x: bridge.point.x + bridge.tangent.x * radius,
      y: bridge.point.y + bridge.tangent.y * radius,
    };

    gap.setAttribute("cx", bridge.point.x);
    gap.setAttribute("cy", bridge.point.y);
    gap.setAttribute("r", radius + 3);
    gap.setAttribute("class", "line-jump-gap");

    arc.setAttribute("d", `M ${start.x} ${start.y} A ${radius} ${radius} 0 0 1 ${end.x} ${end.y}`);
    arc.setAttribute("class", "line-connector line-jump-arc");

    svg.appendChild(gap);
    svg.appendChild(arc);
  });
}


function renderEdgeControlPoints(svg, connectorsByKey) {
  const selectedKey = state.selectedConnectionKey;
  if (!selectedKey || !state.edgeControls[selectedKey]) return;

  const connector = connectorsByKey[selectedKey];
  if (!connector) return;

  const controlPoint = state.edgeControls[selectedKey];
  const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  const halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");

  halo.setAttribute("cx", controlPoint.x);
  halo.setAttribute("cy", controlPoint.y);
  halo.setAttribute("r", 13);
  halo.setAttribute("class", "edge-control-halo");

  handle.setAttribute("cx", controlPoint.x);
  handle.setAttribute("cy", controlPoint.y);
  handle.setAttribute("r", 6);
  handle.setAttribute("class", "edge-control");
  handle.dataset.connectionKey = selectedKey;
  handle.addEventListener("mousedown", event => {
    event.preventDefault();
    event.stopPropagation();
    startEdgeControlDrag(selectedKey);
  });
  handle.addEventListener("click", event => {
    event.preventDefault();
    event.stopPropagation();
  });

  svg.appendChild(halo);
  svg.appendChild(handle);
}


function selectConnection(from, to, connector = null) {
  const key = getConnectionKey(from, to);
  state.selectedConnectionKey = key;
  state.selectedNodeId = null;
  document.querySelectorAll(".node-card").forEach(node => node.classList.remove("node-selected"));

  if (!state.edgeControls[key]) {
    state.edgeControls[key] = getDefaultEdgeControlPoint(connector || buildConnector(getConnectionPoints(from, to)));
  }

  initializeInspector();
  drawLines();
}


function getDefaultEdgeControlPoint(connector) {
  if (!connector?.samples?.length) {
    return { x: 0, y: 0 };
  }

  const middleIndex = Math.floor(connector.samples.length / 2);
  const middlePoint = connector.samples[middleIndex];

  return {
    x: middlePoint.x,
    y: middlePoint.y,
  };
}


function startEdgeControlDrag(connectionKey) {
  state.draggingEdgeControlKey = connectionKey;
  state.suppressNextClick = true;
  document.body.classList.add("is-edge-control-dragging");
}


function dragEdgeControlToPointer(clientX, clientY) {
  const point = getCanvasPoint(clientX, clientY);
  state.edgeControls[state.draggingEdgeControlKey] = {
    x: point.x,
    y: point.y,
  };
  drawLines();
}


function finishEdgeControlDrag() {
  state.draggingEdgeControlKey = null;
  state.suppressNextClick = true;
  document.body.classList.remove("is-edge-control-dragging");
}


function getConnectionKey(from, to) {
  return `${from}->${to}`;
}


function removeEdgeControl(from, to) {
  delete state.edgeControls[getConnectionKey(from, to)];
}


function removeEdgeControlsForNode(nodeId) {
  Object.keys(state.edgeControls).forEach(key => {
    const [source, target] = key.split("->");
    if (source === nodeId || target === nodeId) {
      delete state.edgeControls[key];
    }
  });
}


function getNodeRect(nodeId) {
  const node = nodes.find(item => item.id === nodeId);
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


function getNodeFromPoint(clientX, clientY) {
  const element = document.elementFromPoint(clientX, clientY);
  return element?.closest?.(".node-card") || null;
}


function showConnectionMenu(clientX, clientY, from, to) {
  state.menuConnection = [from, to];
  const menu = document.getElementById("connection-menu");
  menu.style.left = `${clientX}px`;
  menu.style.top = `${clientY}px`;
  menu.classList.remove("hidden");
}


function hideConnectionMenu() {
  const menu = document.getElementById("connection-menu");
  if (!menu) return;
  menu.classList.add("hidden");
}


function showNodeMenu(clientX, clientY, nodeId) {
  state.menuNodeId = nodeId;
  hideConnectionMenu();
  const menu = document.getElementById("node-menu");
  menu.style.left = `${clientX}px`;
  menu.style.top = `${clientY}px`;
  menu.classList.remove("hidden");
}


function hideNodeMenu() {
  const menu = document.getElementById("node-menu");
  if (!menu) return;
  menu.classList.add("hidden");
}


function connectFromMenuNode(event) {
  event.stopPropagation();
  const nodeId = state.menuNodeId;
  if (!nodeId) return;

  const node = document.getElementById(`node-${nodeId}`);
  const rect = node.getBoundingClientRect();
  hideNodeMenu();
  beginConnection(nodeId, rect.left + rect.width / 2, rect.bottom);
}


function deleteMenuNode(event) {
  event.stopPropagation();
  const nodeId = state.menuNodeId;
  if (!nodeId) return;

  nodes = nodes.filter(node => node.id !== nodeId);
  connections = connections.filter(([source, target]) => source !== nodeId && target !== nodeId);
  removeEdgeControlsForNode(nodeId);
  if (state.selectedNodeId === nodeId) {
    state.selectedNodeId = null;
    initializeInspector();
  }
  if (state.connectSourceId === nodeId) {
    cancelPendingConnection();
  }
  state.menuNodeId = null;
  hideNodeMenu();
  updateCanvasSize();
  renderCanvasNodes();
  resetValidationAfterGraphChange();
  showToast("success", "节点已删除。");
}


function deleteMenuConnection(event) {
  event.stopPropagation();
  if (!state.menuConnection) return;

  const [from, to] = state.menuConnection;
  connections = connections.filter(([source, target]) => !(source === from && target === to));
  removeEdgeControl(from, to);
  state.menuConnection = null;
  state.selectedConnectionKey = null;
  hideConnectionMenu();
  resetValidationAfterGraphChange();
  drawLines();
  showToast("success", "连线已删除。");
}


function resetValidationAfterGraphChange() {
  state.validationStatus = "unvalidated";
  document.getElementById("btn-train").disabled = true;
  document.getElementById("validation-summary").classList.add("hidden");
  document.querySelectorAll(".status-badge").forEach(badge => {
    badge.innerText = "未校验";
    badge.className = "status-badge";
  });
}


function handlePaletteDragStart(event) {
  event.dataTransfer.setData("text/plain", event.currentTarget.dataset.layerType);
  event.dataTransfer.effectAllowed = "copy";
}


function handleCanvasDrop(event) {
  event.preventDefault();
  const layerType = event.dataTransfer.getData("text/plain");
  if (!layerType) return;

  const point = getCanvasPoint(event.clientX, event.clientY);
  addNodeFromLayer(layerType, point.x - 112, point.y - 70);
}


function handleCanvasClick(event) {
  if (state.suppressNextClick) {
    state.suppressNextClick = false;
    return;
  }

  if (state.isConnecting || state.draggingNodeId) {
    return;
  }

  if (event.target.closest?.(".node-card")) {
    return;
  }

  if (event.target.closest?.(".edge-control, .edge-control-halo, .line-hit-area")) {
    return;
  }

  if (event.target.closest?.(".zoom-control, .exit-connect-button")) {
    return;
  }

  deselectNode();
}


function handleZoomAction(actionId) {
  if (actionId === "zoom-fit") {
    state.zoom = 1;
  } else if (actionId === "zoom-in") {
    state.zoom = Math.min(1.5, Number((state.zoom + 0.1).toFixed(2)));
  } else if (actionId === "zoom-out") {
    state.zoom = Math.max(0.6, Number((state.zoom - 0.1).toFixed(2)));
  }

  applyZoom();
}


function applyZoom() {
  const content = document.getElementById("nodes-container");
  const svg = document.getElementById("connections-svg");
  const label = document.querySelector(".zoom-control span");
  content.style.transform = `scale(${state.zoom})`;
  svg.style.transform = `scale(${state.zoom})`;
  label.innerText = `${Math.round(state.zoom * 100)}%`;
  updateCanvasSize();
  updateFloatingControlPositions();
}


function addNodeFromLayer(layerType, x, y) {
  const node = createNodeConfig(layerType, x, y);
  nodes = [...nodes, node];
  updateCanvasSize();
  renderCanvasNodes();
  selectNode(node.id);
  resetValidationAfterGraphChange();
  showToast("success", `已添加 ${node.badge} 节点。`);
}


function createNodeConfig(layerType, x, y) {
  const config = getLayerConfig(layerType);
  const type = config.type;
  state.nodeCounters[type] = (state.nodeCounters[type] || 0) + 1;
  const id = `${type.toLowerCase()}_${state.nodeCounters[type]}`;
  const canvasX = clamp(x, 40, getCanvasWidth() - 264);
  const canvasY = clamp(y, 40, getCanvasHeight() - 180);

  return {
    id,
    type,
    title: config.title,
    badge: config.badge,
    color: config.color,
    note: config.note,
    hint: config.hint || "?",
    x: canvasX,
    y: canvasY,
    params: { ...config.params },
  };
}


function getLayerConfig(layerType) {
  const configs = {
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

  return configs[layerType] || configs.Linear;
}


async function loadProjectTemplates() {
  try {
    const result = await fetchProjectTemplates();
    if (result?.count) {
      showToast("info", `已连接模板库: ${result.count} 个模板`);
    }
  } catch (error) {
    showBackendError(error, "模板列表接口暂未实现。");
  }
}


async function loadTemplateToCanvas(templateName) {
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


function applyTemplateGraph(modelGraph) {
  const canvas = document.getElementById("canvas-container");
  const centeredX = Math.max(40, (canvas.clientWidth - 224) / 2);

  nodes = modelGraph.layers.map((layer, index) => {
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
  connections = modelGraph.connections.map(connection => [connection.source, connection.target]);
  state.selectedNodeId = null;
  state.edgeControls = {};
  state.selectedConnectionKey = null;
  state.hasCenteredInitialGraph = true;
  initializeInspector();
  updateCanvasSize();
  renderCanvasNodes();
  resetValidationAfterGraphChange();
  centerGraphInCanvas();
}


function formatLayerNote(layer) {
  const params = layer.params || {};
  const entries = Object.entries(params)
    .filter(([, value]) => typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => `${key}=${value}`);

  return entries.join(", ");
}


function getCanvasPoint(clientX, clientY) {
  const canvas = document.getElementById("canvas-container");
  const rect = canvas.getBoundingClientRect();
  return {
    x: (clientX - rect.left + canvas.scrollLeft) / state.zoom,
    y: (clientY - rect.top + canvas.scrollTop) / state.zoom,
  };
}


function updateCanvasSize() {
  const content = document.getElementById("nodes-container");
  const svg = document.getElementById("connections-svg");
  const width = getCanvasWidth();
  const height = getCanvasHeight();
  content.style.width = `${width}px`;
  content.style.height = `${height}px`;
  content.style.minWidth = `${width * state.zoom}px`;
  content.style.minHeight = `${height * state.zoom}px`;
  svg.style.width = `${width}px`;
  svg.style.height = `${height}px`;
  svg.style.minWidth = `${width * state.zoom}px`;
  svg.style.minHeight = `${height * state.zoom}px`;
}


function centerGraphInCanvas() {
  const canvas = document.getElementById("canvas-container");
  if (!canvas || nodes.length === 0) return;

  const bounds = getGraphBounds();
  const graphCenterX = (bounds.left + bounds.right) / 2;
  const targetScrollLeft = graphCenterX * state.zoom - canvas.clientWidth / 2;

  canvas.scrollLeft = clamp(
    targetScrollLeft,
    0,
    Math.max(0, canvas.scrollWidth - canvas.clientWidth)
  );
  canvas.scrollTop = 0;
}


function getGraphBounds() {
  return nodes.reduce(
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


function getCanvasWidth() {
  const canvas = document.getElementById("canvas-container");
  const maxNodeX = Math.max(...nodes.map(node => node.x + 320), 0);
  return Math.max(1200, canvas.clientWidth + 360, maxNodeX);
}


function getCanvasHeight() {
  const canvas = document.getElementById("canvas-container");
  const maxNodeY = Math.max(...nodes.map(node => node.y + 240), 0);
  return Math.max(1460, canvas.clientHeight + 420, maxNodeY);
}


function updateFloatingControlPositions() {
  const canvas = document.getElementById("canvas-container");
  const zoomControl = document.querySelector(".zoom-control");
  const exitButton = document.getElementById("btn-exit-connect");
  if (!canvas || !zoomControl || !exitButton) return;

  zoomControl.style.left = `${canvas.scrollLeft + 24}px`;
  zoomControl.style.top = `${canvas.scrollTop + canvas.clientHeight - zoomControl.offsetHeight - 24}px`;
  exitButton.style.left = `${canvas.scrollLeft + canvas.clientWidth - exitButton.offsetWidth - 24}px`;
  exitButton.style.top = `${canvas.scrollTop + 24}px`;
}


function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}


function highlightLines(nodeId, enabled) {
  document.querySelectorAll(".line-connector").forEach(line => {
    if (line.dataset.from === nodeId || line.dataset.to === nodeId) {
      line.classList.toggle("line-hover", enabled);
    }
  });
}


function selectNode(nodeId) {
  state.selectedNodeId = nodeId;
  state.selectedConnectionKey = null;
  document.querySelectorAll(".node-card").forEach(node => node.classList.remove("node-selected"));
  document.getElementById(`node-${nodeId}`).classList.add("node-selected");
  renderInspector();
}


function deselectNode() {
  state.selectedNodeId = null;
  state.selectedConnectionKey = null;
  document.querySelectorAll(".node-card").forEach(node => node.classList.remove("node-selected"));
  initializeInspector();
}


function renderInspector() {
  const node = nodes.find(item => item.id === state.selectedNodeId);

  if (!node) {
    initializeInspector();
    return;
  }

  if (node.type === "Conv2D") {
    renderConvInspector(node);
    return;
  }

  if (node.type === "Linear") {
    renderLinearInspector(node);
    return;
  }

  if (node.type === "Pooling") {
    renderPoolingInspector(node);
    return;
  }

  if (node.type === "Dropout") {
    renderDropoutInspector(node);
    return;
  }

  if (node.type === "Input") {
    renderInputInspector(node);
    return;
  }

  renderSimpleInspector(node);
}

function renderSimpleInspector(node) {
  if (node.type === "Add") {
    document.getElementById("inspector-content").innerHTML = `
      <div class="inspector-scroll">
        <div class="inspector-title">
          <iconify-icon class="text-cyan" icon="mdi:plus-circle-outline"></iconify-icon>
          <h2>Add 节点</h2>
        </div>
        <section class="info-card">
          <p>Add 节点会在导出给后端时折叠为目标节点的 add 合并方式。</p>
        </section>
      </div>
    `;
    return;
  }

  document.getElementById("inspector-content").innerHTML = `
    <div class="simple-inspector">
      <iconify-icon icon="mdi:layers-outline"></iconify-icon>
      <h2>${node.badge || node.type} 节点</h2>
      <p>该节点无可编辑参数，当前使用默认设置。</p>
    </div>
  `;
}

function updateNodeParam(nodeId, key, value) {
  const node = nodes.find(item => item.id === nodeId);
  if (!node) return;

  node.params = {
    ...node.params,
    [key]: value,
  };

  updateNodeDisplay(node);
  resetValidationAfterGraphChange();
}

function updateNodeDisplay(node) {
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

  renderCanvasNodes();

  if (state.selectedNodeId === node.id) {
    document.getElementById(`node-${node.id}`)?.classList.add("node-selected");
  }
}


function renderConvInspector(node) {
  document.getElementById("inspector-content").innerHTML = `
    <div class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-blue" icon="mdi:grid-large"></iconify-icon>
        <h2>Conv2D 参数</h2>
      </div>

      <div class="field-stack">
        ${editableNumberField("Out Channels (输出通道)", "out_channels", node.params.out_channels)}
        ${editableNumberField("Kernel Size (卷积核大小)", "kernel_size", node.params.kernel_size)}
        <div class="field-grid">
          ${editableNumberField("Stride", "stride", node.params.stride)}
          ${editableNumberField("Padding", "padding", node.params.padding)}
        </div>
      </div>

      <section class="info-card blue-card">
        <h4><iconify-icon icon="mdi:information-outline"></iconify-icon> 卷积层 Conv2D</h4>
        <p>卷积层用于提取局部特征，out_channels 越大，学习到的特征映射越丰富，但计算开销也会增加。</p>
      </section>
    </div>
  `;

  bindInspectorNumberInputs(node.id);
}

function editableNumberField(label, key, value) {
  return `
    <label class="form-field">
      <span>${label}</span>
      <input class="param-input" data-param-key="${key}" type="number" value="${value ?? ""}">
    </label>
  `;
}

function bindInspectorNumberInputs(nodeId) {
  document.querySelectorAll(".param-input").forEach(input => {
    input.addEventListener("change", event => {
      const key = event.target.dataset.paramKey;
      const rawValue = event.target.value;

      if (rawValue === "") {
        showToast("warning", "参数不能为空。");
        return;
      }

      const value = Number(rawValue);

      if (Number.isNaN(value)) {
        showToast("warning", "参数必须是数字。");
        return;
      }

      updateNodeParam(nodeId, key, value);
    });
  });
}

function renderLinearInspector(node) {
  const isError = state.validationStatus === "failed" && state.inFeatures !== 2704;

  document.getElementById("inspector-content").innerHTML = `
    <div class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-cyan" icon="mdi:ray-start-end"></iconify-icon>
        <h2>Linear 参数</h2>
      </div>

      ${isError ? `
        <section class="error-card">
          <h4><iconify-icon icon="mdi:alert-circle"></iconify-icon> Shape mismatch</h4>
          <p>前一层 Flatten 输出维度为 2704，而当前 Linear.in_features 设为 ${state.inFeatures}。</p>
          <button id="btn-autofix">一键修复</button>
        </section>
      ` : ""}

      <div class="field-stack">
        <label class="form-field muted-field">
          <span>In Features 输入特征数</span>
          <input type="text" value="${state.inFeatures}" readonly>
          <small>由前一层自动推导</small>
        </label>

        ${editableNumberField("Out Features 输出神经元", "out_features", node.params.out_features)}
      </div>
    </div>
  `;

  bindInspectorNumberInputs(node.id);

  const fixButton = document.getElementById("btn-autofix");
  if (fixButton) {
    fixButton.addEventListener("click", autoFix);
  }
}

function renderPoolingInspector(node) {
  document.getElementById("inspector-content").innerHTML = `
    <div class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-purple" icon="mdi:resize"></iconify-icon>
        <h2>Pooling 参数</h2>
      </div>

      <div class="field-stack">
        ${editableNumberField("Kernel Size 池化核大小", "kernel_size", node.params.kernel_size)}
        ${editableNumberField("Stride 步长", "stride", node.params.stride)}
        ${editableNumberField("Padding 填充", "padding", node.params.padding)}
      </div>
    </div>
  `;

  bindInspectorNumberInputs(node.id);
}


function renderDropoutInspector(node) {
  document.getElementById("inspector-content").innerHTML = `
    <div class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-amber" icon="mdi:filter-off-outline"></iconify-icon>
        <h2>Dropout 参数</h2>
      </div>

      <div class="field-stack">
        ${editableNumberField("Dropout Rate 随机失活比例", "p", node.params.p)}
      </div>

      <section class="info-card">
        <p>p 一般取 0 到 1 之间的小数，例如 0.5。</p>
      </section>
    </div>
  `;

  bindInspectorNumberInputs(node.id);
}

function renderInputInspector(node) {
  const shapeValue = Array.isArray(node.params?.shape)
    ? node.params.shape.join(",")
    : "";

  document.getElementById("inspector-content").innerHTML = `
    <div class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-emerald" icon="mdi:login-variant"></iconify-icon>
        <h2>Input 参数</h2>
      </div>

      <label class="form-field">
        <span>Input Shape 输入形状</span>
        <input id="input-shape-field" type="text" value="${shapeValue}">
        <small>格式示例：1,28,28</small>
      </label>
    </div>
  `;

  document.getElementById("input-shape-field").addEventListener("change", event => {
    const rawItems = event.target.value.split(",").map(item => item.trim());

    if (rawItems.length === 0 || rawItems.some(item => item === "")) {
      showToast("warning", "Input shape 不能为空，格式示例：1,28,28。");
      return;
    }

    const shape = rawItems.map(item => Number(item));

    if (shape.some(item => Number.isNaN(item) || item <= 0)) {
      showToast("warning", "Input shape 必须是正数，格式示例：1,28,28。");
      return;
    }

    updateNodeParam(node.id, "shape", shape);
  });
}

function stepperField(label, value) {
  return `
    <label class="form-field">
      <span>${label}</span>
      <div class="stepper">
        <button type="button">-</button>
        <input type="text" value="${value}">
        <button type="button">+</button>
      </div>
    </label>
  `;
}


function numberField(label, value) {
  return `
    <label class="form-field">
      <span>${label}</span>
      <input type="number" value="${value}">
    </label>
  `;
}


function getExportParams(node, exportConnections, addTargetIds) {
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
  const addNodeIds = new Set(nodes.filter(node => node.type === "Add").map(node => node.id));
  const addTargetIds = new Set();
  const exportConnections = [];
  const seenConnections = new Set();

  function addExportConnection(source, target) {
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

function getCurrentModelGraph() {
  const backendGraph = buildBackendModelGraph();

  return {
    layers: nodes
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


function getTrainConfig() {
  return {
    dataset_name: getSelectedDatasetName(),
    epochs: 1,
    batch_size: 64,
    rate: 0.001,
    device: "cpu",
    loss_fn: "cross_entropy",
    optimizer: "sgd",
  };
}


function getTrainingLayers() {
  return nodes
    .filter(node => node.type !== "Add")
    .map(node => ({
      type: node.badge || node.type,
      color: node.color || "cyan",
    }));
}


function getTrainingStatusLabel(status) {
  return {
    pending: "等待中",
    running: "训练中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  }[status] || "未知";
}


function updateTrainingJobPanel() {
  const panel = document.getElementById("training-job-panel");
  if (!panel) return;

  const job = state.trainingJob;
  if (!job) {
    panel.classList.add("is-empty");
    panel.classList.remove("is-running", "is-completed", "is-failed");
    document.getElementById("training-job-id").textContent = "暂无训练任务";
    document.getElementById("training-job-status").textContent = "Idle";
    document.getElementById("training-job-progress").style.width = "0%";
    document.getElementById("training-job-meta").textContent = "Validate 通过后可启动训练";
    document.getElementById("btn-view-training").disabled = true;
    return;
  }

  const status = job.status || "pending";
  const progress = typeof job.progress === "number"
    ? job.progress
    : (job.total_epochs ? (job.current_epoch || 0) / job.total_epochs : 0);
  const percentage = Math.round(clamp(progress, 0, 1) * 100);

  panel.classList.remove("is-empty", "is-running", "is-completed", "is-failed");
  panel.classList.add(
    status === "completed" ? "is-completed" : status === "failed" || status === "cancelled" ? "is-failed" : "is-running"
  );
  document.getElementById("training-job-id").textContent = job.job_id || "未知任务";
  document.getElementById("training-job-status").textContent = getTrainingStatusLabel(status);
  document.getElementById("training-job-progress").style.width = `${percentage}%`;
  document.getElementById("training-job-meta").textContent =
    `Epoch ${job.current_epoch ?? 0}/${job.total_epochs ?? "-"} · ${percentage}%`;
  document.getElementById("btn-view-training").disabled = false;
}


function setTrainingJob(job) {
  state.trainingJob = {
    ...(state.trainingJob || {}),
    ...job,
  };
  state.jobId = state.trainingJob.job_id || state.jobId;
  updateTrainingJobPanel();
}


function stopTrainingPanelPolling() {
  if (state.trainingPollTimer) {
    clearTimeout(state.trainingPollTimer);
    state.trainingPollTimer = null;
  }
}


async function submitTrainingJob() {
  const trainConfig = getTrainConfig();
  const result = await startTraining(getCurrentModelGraph(), trainConfig);
  return {
    result,
    trainConfig,
    jobId: result?.job_id,
  };
}


function openCurrentTrainingMonitor() {
  if (!state.trainingJob?.job_id) {
    showToast("warning", "当前没有可查看的训练任务。");
    return;
  }

  openTrainingMonitor({
    live: true,
    jobId: state.trainingJob.job_id,
    fetchStatus: fetchTrainingStatus,
    fetchResult: fetchTrainingResult,
    hyperparams: state.trainingJob.trainConfig || getTrainConfig(),
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
        pollTrainingStatus(jobId);
      }
      return { jobId };
    },
  });
}


async function handleValidateModel() {
  const button = document.getElementById("btn-validate");
  const originalHtml = button.innerHTML;
  setButtonLoading(button, "正在校验...");

  try {
    const result = await validateModel(getCurrentModelGraph());
    applyValidationResult(result);
    showToast("success", "结构校验完成。");
  } catch (error) {
    showBackendError(error, "结构校验接口暂未实现。");
    applyUnavailableValidation();
  } finally {
    button.innerHTML = originalHtml;
    button.disabled = false;
  }
}


function applyValidationResult(result) {
  const valid = result?.valid === true || result?.status === "ok";
  if (valid) {
    state.validationStatus = "passing";
    applyValidationUI(true, "结构校验通过");
    return;
  }

  state.validationStatus = "failed";
  applyValidationUI(false, result?.message || "结构校验失败");
}


function applyUnavailableValidation() {
  state.validationStatus = "unvalidated";
  document.getElementById("btn-train").disabled = true;
  const summary = document.getElementById("validation-summary");
  summary.classList.remove("hidden", "success", "error");
  summary.classList.add("warning");
  document.getElementById("summary-icon").setAttribute("icon", "mdi:clock-alert-outline");
  document.getElementById("summary-text").innerText = "结构校验接口暂未实现";
}


function applyValidationUI(isPass, message) {
  const summary = document.getElementById("validation-summary");
  const summaryIcon = document.getElementById("summary-icon");
  const summaryText = document.getElementById("summary-text");
  const trainButton = document.getElementById("btn-train");

  summary.classList.remove("hidden", "success", "error", "warning");
  summary.classList.add(isPass ? "success" : "error");
  summaryIcon.setAttribute("icon", isPass ? "mdi:check-circle" : "mdi:alert-circle");
  summaryText.innerText = message;
  trainButton.disabled = !isPass;

  document.querySelectorAll(".status-badge").forEach(badge => {
    badge.innerText = isPass ? "通过" : "待检查";
    badge.className = `status-badge ${isPass ? "passed" : ""}`;
  });

  if (isPass) {
    updateShapeHints();
    document.getElementById("node-linear")?.classList.remove("node-error");
  }
}


function updateShapeHints() {
  const hints = {
    conv: "26x26x16",
    pool: "13x13x16",
    flatten: "2704",
    linear: "128",
    output: "10",
  };

  Object.entries(hints).forEach(([id, value]) => {
    const element = document.querySelector(`#node-${id} .shape-value`);
    if (element) {
      element.innerText = value;
    }
  });
}


function autoFix() {
  state.inFeatures = 2704;
  showToast("success", "参数已自动修复为 2704。");

  const node = nodes.find(item => item.id === state.selectedNodeId);
  if (node && node.type === "Linear") {
    renderLinearInspector(node);
  }
}


async function handleSaveProject() {
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


async function handleExportCode() {
  openModal();
  const codeBlock = document.getElementById("export-code");
  codeBlock.textContent = "正在请求后端导出接口...";

  try {
    const result = await exportPytorchCode(getCurrentModelGraph());
    const code = result?.code || result?.source_code || result;
    state.lastExportCode = typeof code === "string" ? code : JSON.stringify(result, null, 2);
    codeBlock.textContent = state.lastExportCode;
    showToast("success", "PyTorch 代码已从后端导出。");
  } catch (error) {
    showBackendError(error, "代码导出接口暂未实现。");
    state.lastExportCode = "";
    codeBlock.textContent = "代码导出接口暂未实现。";
  }
}


async function handleStartTraining() {
  const button = document.getElementById("btn-train");
  const originalHtml = button.innerHTML;
  setButtonLoading(button, "启动训练...");

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
    showToast("success", `训练任务已创建: ${state.jobId || "未知任务"}`);
    if (jobId) {
      openCurrentTrainingMonitor();
      pollTrainingStatus(jobId);
    }
  } catch (error) {
    showBackendError(error, "训练接口暂未实现。");
  } finally {
    button.innerHTML = originalHtml;
    button.disabled = state.validationStatus !== "passing";
  }
}


async function pollTrainingStatus(jobId) {
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
    state.trainingPollTimer = setTimeout(() => pollTrainingStatus(jobId), 1000);
  } catch (error) {
    showBackendError(error, "训练状态接口暂未实现。");
  }
}


function openModal() {
  document.getElementById("export-modal").classList.remove("hidden");
}


function closeModal() {
  document.getElementById("export-modal").classList.add("hidden");
}


async function copyExportCode() {
  if (!state.lastExportCode) {
    showToast("warning", "暂无可复制代码。");
    return;
  }

  try {
    await navigator.clipboard.writeText(state.lastExportCode);
    showToast("success", "代码已复制。");
  } catch {
    showToast("warning", "当前浏览器不支持自动复制。");
  }
}


function downloadExportCode() {
  if (!state.lastExportCode) {
    showToast("warning", "暂无可下载代码。");
    return;
  }

  const blob = new Blob([state.lastExportCode], { type: "text/x-python;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "MNIST_CNN.py";
  link.click();
  URL.revokeObjectURL(url);
}


function setButtonLoading(button, text) {
  button.disabled = true;
  button.innerHTML = `<iconify-icon icon="mdi:loading" class="spin"></iconify-icon>${text}`;
}


function showBackendError(error, fallbackMessage) {
  if (isBackendNotImplemented(error)) {
    showToast("warning", fallbackMessage);
    return;
  }
  showToast("error", error.message || fallbackMessage);
}


function showToast(type, message) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  const icon = {
    success: "mdi:check-circle",
    error: "mdi:alert",
    warning: "mdi:clock-alert-outline",
    info: "mdi:information-outline",
  }[type] || "mdi:information-outline";

  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <iconify-icon icon="${icon}"></iconify-icon>
    <span>${message}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-out");
    setTimeout(() => toast.remove(), 450);
  }, 3200);
}


initializeApp();
