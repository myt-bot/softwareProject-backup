<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  autoLayoutGraph,
  beginConnectionDrag,
  cancelPendingConnection,
  centerGraphInCanvas,
  completeConnection,
  containerBreadcrumb,
  enterContainer,
  exitToDepth,
  handleCanvasClick,
  handleCanvasDrop,
  handleCanvasMouseDown,
  handleCanvasWheel,
  handleDocumentMouseMove,
  handleDocumentMouseUp,
  handleNodeMouseDown,
  handleZoomAction,
  initializeCanvasView,
  isEditingContainer,
  redoGraphChange,
  registerCanvasElements,
  selectNode,
  showNodeMenu,
  toggleContainerCollapse,
  undoGraphChange,
} from "../canvas";
import {
  activeCanvas,
  containerInputPorts,
  containerOutputPorts,
  endpointBaseId,
  makePortEndpoint,
  showToast,
  store,
} from "../store";
import type { GraphNode } from "../types";
import CanvasTabs from "./CanvasTabs.vue";

const canvasRef = ref<HTMLElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const nodesRef = ref<HTMLElement | null>(null);
const gridRef = ref<HTMLElement | null>(null);

const canvas = computed(() => activeCanvas());

const zoomLabel = computed(() => `${Math.round(canvas.value.zoom * 100)}%`);

// 子画板编辑态：面包屑路径（主画布 / 容器名 / …）
const editing = computed(() => isEditingContainer());
const breadcrumb = computed(() => containerBreadcrumb());
const currentContainerName = computed(() => breadcrumb.value[breadcrumb.value.length - 1] || "");

const statusBadgeText = computed(() =>
  canvas.value.nodeBadge === "passed" ? "通过" : canvas.value.nodeBadge === "pending" ? "待检查" : "未校验"
);
const statusBadgeClass = computed(() =>
  canvas.value.nodeBadge === "passed" ? "status-badge passed" : "status-badge"
);

// 节点输出尺寸的新手友好显示：未推导时提示去检查结构，已推导时用 × 分隔（如 28×28×1）
function shapeHintText(hint: string) {
  return hint === "?" ? "检查结构后显示" : hint.replace(/x/gi, "×");
}
// 端口锚点旁的紧凑尺寸：未推导显示 "?"
function portShapeText(port: GraphNode) {
  return port.hint && port.hint !== "?" ? port.hint.replace(/x/gi, "×") : "?";
}
function portEndpoint(nodeId: string, portId: string) {
  return makePortEndpoint(nodeId, portId);
}

// 连线高亮：源/目标端点可能是容器端口，按基节点 id 比较
function isConnectionSource(nodeId: string) {
  return !!store.connectSourceId && endpointBaseId(store.connectSourceId) === nodeId;
}
function isConnectionTarget(nodeId: string) {
  return !!store.connectTargetId && endpointBaseId(store.connectTargetId) === nodeId;
}

function onNodeClick(event: MouseEvent, nodeId: string) {
  if (store.isConnecting) {
    event.preventDefault();
    completeConnection(nodeId);
    cancelPendingConnection();
    return;
  }
  if (store.suppressNextClick) {
    store.suppressNextClick = false;
    event.preventDefault();
    return;
  }
  selectNode(nodeId);
}

// 双击容器 → 进入子画板编辑
function onNodeDblClick(event: MouseEvent, node: GraphNode) {
  if (node.type !== "Container") return;
  event.preventDefault();
  event.stopPropagation();
  enterContainer(node.id);
}

function onNodeContextMenu(event: MouseEvent, nodeId: string) {
  event.preventDefault();
  event.stopPropagation();
  if (store.isConnecting) return;
  showNodeMenu(event.clientX, event.clientY, nodeId);
}

// 从输出端口按住拖拽 → 开始连线（endpoint 普通层为 node.id，容器端口为 容器id::端口层id）
function onPortMouseDown(event: MouseEvent, endpoint: string) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  beginConnectionDrag(endpoint, event.clientX, event.clientY);
}

function exitConnectMode() {
  cancelPendingConnection();
  showToast("info", "已退出连线模式。");
}

onMounted(() => {
  registerCanvasElements({
    canvas: canvasRef.value!,
    svg: svgRef.value!,
    nodes: nodesRef.value!,
    grid: gridRef.value!,
  });
  initializeCanvasView();
  document.addEventListener("mousemove", handleDocumentMouseMove);
  document.addEventListener("mouseup", handleDocumentMouseUp);
});

onBeforeUnmount(() => {
  document.removeEventListener("mousemove", handleDocumentMouseMove);
  document.removeEventListener("mouseup", handleDocumentMouseUp);
});
</script>

<template>
  <!-- 中间：模型画布（多画布标签页 + 画布主体） -->
  <section class="canvas-pane">
    <CanvasTabs />

    <!-- 容器子画板：面包屑 + 返回 + 新手指引 -->
    <div v-if="editing" class="container-editor-bar">
      <nav class="breadcrumb">
        <template v-for="(name, index) in breadcrumb" :key="index">
          <button
            v-if="index < breadcrumb.length - 1"
            class="crumb crumb-link"
            @click="exitToDepth(index)"
          >{{ name }}</button>
          <span v-else class="crumb crumb-current">{{ name }}</span>
          <iconify-icon v-if="index < breadcrumb.length - 1" icon="mdi:chevron-right" class="crumb-sep"></iconify-icon>
        </template>
      </nav>
      <div class="editor-hint">
        <iconify-icon icon="mdi:information-outline"></iconify-icon>
        正在编辑容器「{{ currentContainerName }}」：拖入层搭建，<b>Input</b>=输入端口、<b>Output</b>=输出端口（可放多个）。
      </div>
      <button class="editor-back" @click="exitToDepth(breadcrumb.length - 2)">
        <iconify-icon icon="mdi:arrow-u-left-top"></iconify-icon>
        返回上一层
      </button>
    </div>

    <main
    ref="canvasRef"
    class="canvas"
    :class="{ 'canvas-editing-container': editing }"
    id="canvas-container"
    @mousedown="handleCanvasMouseDown"
    @click="handleCanvasClick"
    @dragover.prevent
    @drop="handleCanvasDrop"
    @wheel.prevent="handleCanvasWheel"
  >
    <button
      class="exit-connect-button"
      :class="{ hidden: !store.isConnecting }"
      id="btn-exit-connect"
      @click="exitConnectMode"
    >
      <iconify-icon icon="mdi:close-circle-outline"></iconify-icon>
      退出连线
    </button>
    <div class="canvas-toolbar">
      <!-- 缩放组 -->
      <div class="toolbar-group zoom-control">
        <button id="zoom-out" title="缩小画布" @click="handleZoomAction('zoom-out')"><iconify-icon icon="mdi:minus"></iconify-icon></button>
        <span>{{ zoomLabel }}</span>
        <button id="zoom-in" title="放大画布" @click="handleZoomAction('zoom-in')"><iconify-icon icon="mdi:plus"></iconify-icon></button>
      </div>
      <!-- 工具组：自动布局 / 居中 / 撤销 / 重做 -->
      <div class="toolbar-group">
        <button id="btn-auto-layout" title="自动布局：一键把节点排列整齐" @click="autoLayoutGraph"><iconify-icon icon="mdi:auto-fix"></iconify-icon></button>
        <button id="zoom-fit" title="定位到节点并居中" @click="centerGraphInCanvas"><iconify-icon icon="mdi:image-filter-center-focus"></iconify-icon></button>
        <i></i>
        <button id="btn-undo" title="撤销 (Ctrl+Z)" @click="undoGraphChange"><iconify-icon icon="mdi:undo-variant"></iconify-icon></button>
        <button id="btn-redo" title="重做 (Ctrl+Shift+Z / Ctrl+Y)" @click="redoGraphChange"><iconify-icon icon="mdi:redo-variant"></iconify-icon></button>
      </div>
    </div>
    <div ref="gridRef" class="canvas-grid connections-svg"></div>
    <svg ref="svgRef" class="connections-svg" id="connections-svg"></svg>

    <!-- 空画布引导态：主画布与容器子画板给不同提示 -->
    <div v-if="canvas.nodes.length === 0" class="canvas-empty-hint" id="canvas-empty-hint">
      <iconify-icon icon="mdi:gesture-tap-hold"></iconify-icon>
      <template v-if="editing">
        <h3>开始搭建容器内部</h3>
        <p>从左侧拖入 <b>Input</b> 作为输入端口、<b>Output</b> 作为输出端口，<br>中间放需要的层并连起来。多个 Input/Output 即多输入多输出。</p>
      </template>
      <template v-else>
        <h3>从这里开始搭建你的模型</h3>
        <p>👈 从左侧「组件库」拖一个 <b>Input</b> 层到这里<br>或点右上角 <b>⚡ 快速开始模板</b> 一键加载示例</p>
      </template>
    </div>

    <div ref="nodesRef" class="nodes-container" id="nodes-container">
      <article
        v-for="node in canvas.nodes"
        :key="node.id"
        class="node-card"
        :id="`node-${node.id}`"
        :data-node-id="node.id"
        :class="{
          'node-selected': canvas.selectedNodeId === node.id,
          'node-container': node.type === 'Container',
          'connection-source': isConnectionSource(node.id),
          'connection-target': isConnectionTarget(node.id),
          'node-dragging': store.draggingNodeId === node.id,
          'node-error': !!canvas.nodeErrors[node.id],
        }"
        :style="{ left: `${node.x}px`, top: `${node.y}px` }"
        @mousedown="handleNodeMouseDown($event, node.id)"
        @click="onNodeClick($event, node.id)"
        @dblclick="onNodeDblClick($event, node)"
        @contextmenu="onNodeContextMenu($event, node.id)"
      >
        <!-- 自定义容器：顶部输入端口行 + 底部输出端口行，每端口带名称与尺寸 -->
        <template v-if="node.type === 'Container'">
          <div class="cport-row cport-row-in">
            <div
              v-for="port in containerInputPorts(node)"
              :key="port.id"
              class="cport cport-in"
              :data-endpoint="portEndpoint(node.id, port.id)"
              data-port-kind="in"
              :title="`输入端口 · ${port.title}`"
            >
              <span class="cport-dot"></span>
              <span class="cport-meta"><span class="cport-label">{{ port.title }}</span><span class="cport-shape">{{ portShapeText(port) }}</span></span>
            </div>
          </div>

          <div class="node-head">
            <span :class="`node-type ${node.color}`">{{ node.badge }}</span>
            <div class="container-head-actions">
              <span v-if="canvas.nodeErrors[node.id]" class="status-badge error">✕</span>
              <button
                class="container-toggle"
                :title="node.collapsed ? '展开查看内部层' : '折叠'"
                @click.stop="toggleContainerCollapse(node.id)"
              >
                <iconify-icon :icon="node.collapsed ? 'mdi:unfold-more-horizontal' : 'mdi:unfold-less-horizontal'"></iconify-icon>
              </button>
            </div>
          </div>
          <h4>{{ node.title }}</h4>
          <p class="node-note container-dbl-hint"><iconify-icon icon="mdi:cursor-default-click-outline"></iconify-icon> {{ node.note }} · 双击编辑</p>
          <div v-if="!node.collapsed" class="container-inner">
            <div
              v-for="inner in node.subgraph?.nodes.filter(n => n.type !== 'Input' && n.type !== 'Output')"
              :key="inner.id"
              class="container-inner-row"
            >
              <span :class="`node-type sm ${inner.color}`">{{ inner.badge }}</span>
              <span class="inner-name">{{ inner.title }}</span>
              <strong class="inner-shape" :class="{ pending: inner.hint === '?' }">{{ portShapeText(inner) }}</strong>
            </div>
          </div>

          <div class="cport-row cport-row-out">
            <div
              v-for="port in containerOutputPorts(node)"
              :key="port.id"
              class="cport cport-out"
              :data-endpoint="portEndpoint(node.id, port.id)"
              data-port-kind="out"
              :title="`输出端口 · ${port.title}（按住拖动连线）`"
              @mousedown="onPortMouseDown($event, portEndpoint(node.id, port.id))"
            >
              <span class="cport-meta"><span class="cport-label">{{ port.title }}</span><span class="cport-shape">{{ portShapeText(port) }}</span></span>
              <span class="cport-dot"></span>
            </div>
          </div>
        </template>

        <!-- 普通层节点 -->
        <template v-else>
          <div class="node-head">
            <span :class="`node-type ${node.color}`">{{ node.badge }}</span>
            <span v-if="canvas.nodeErrors[node.id]" class="status-badge error">✕ 有问题</span>
            <span v-else :class="statusBadgeClass">{{ statusBadgeText }}</span>
          </div>
          <h4>{{ node.title }}</h4>
          <p v-if="node.note" class="node-note">{{ node.note }}</p>
          <!-- 出错节点的人话提示，直接显示在节点上 -->
          <p v-if="canvas.nodeErrors[node.id]" class="node-error-msg">
            <iconify-icon icon="mdi:alert-circle-outline"></iconify-icon>
            {{ canvas.nodeErrors[node.id] }}
          </p>
          <div v-else class="shape-row" title="这一层输出数据的尺寸，点击底部“检查结构”后自动推导">
            <span>输出尺寸</span>
            <strong class="shape-value" :class="{ pending: node.hint === '?' }">{{ shapeHintText(node.hint) }}</strong>
          </div>
          <!-- 输入锚点（顶部） -->
          <div
            v-if="node.type !== 'Input'"
            class="node-port node-port-in"
            :data-endpoint="node.id"
            data-port-kind="in"
            title="连线接入点"
          ></div>
          <!-- 输出端口（底部）：按住拖到另一个节点即可连线 -->
          <div
            v-if="node.type !== 'Output'"
            class="node-port node-port-out"
            :data-endpoint="node.id"
            data-port-kind="out"
            title="按住拖到另一个节点即可连线"
            @mousedown="onPortMouseDown($event, node.id)"
          ><iconify-icon icon="mdi:plus"></iconify-icon></div>
        </template>
      </article>
    </div>
    </main>
  </section>
</template>
