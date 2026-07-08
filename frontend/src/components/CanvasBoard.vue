<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  autoLayoutGraph,
  beginConnectionDrag,
  cancelPendingConnection,
  centerGraphInCanvas,
  completeConnection,
  handleCanvasClick,
  handleCanvasDrop,
  handleCanvasMouseDown,
  handleCanvasWheel,
  handleDocumentMouseMove,
  handleDocumentMouseUp,
  handleNodeMouseDown,
  handleZoomAction,
  initializeCanvasView,
  redoGraphChange,
  registerCanvasElements,
  selectNode,
  showNodeMenu,
  undoGraphChange,
} from "../canvas";
import { activeCanvas, showToast, store } from "../store";
import CanvasTabs from "./CanvasTabs.vue";

const canvasRef = ref<HTMLElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const nodesRef = ref<HTMLElement | null>(null);
const gridRef = ref<HTMLElement | null>(null);

const canvas = computed(() => activeCanvas());

const zoomLabel = computed(() => `${Math.round(canvas.value.zoom * 100)}%`);

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

function onNodeContextMenu(event: MouseEvent, nodeId: string) {
  event.preventDefault();
  event.stopPropagation();
  if (store.isConnecting) return;
  showNodeMenu(event.clientX, event.clientY, nodeId);
}

// 从节点底部端口按住拖拽 → 开始连线（更直观）
function onPortMouseDown(event: MouseEvent, nodeId: string) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  beginConnectionDrag(nodeId, event.clientX, event.clientY);
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
    <main
    ref="canvasRef"
    class="canvas"
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

    <!-- 空画布引导态：告诉新手第一步该做什么 -->
    <div v-if="canvas.nodes.length === 0" class="canvas-empty-hint" id="canvas-empty-hint">
      <iconify-icon icon="mdi:gesture-tap-hold"></iconify-icon>
      <h3>从这里开始搭建你的模型</h3>
      <p>👈 从左侧「组件库」拖一个 <b>Input</b> 层到这里<br>或点右上角 <b>⚡ 快速开始模板</b> 一键加载示例</p>
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
          'connection-source': store.connectSourceId === node.id,
          'connection-target': store.connectTargetId === node.id,
          'node-dragging': store.draggingNodeId === node.id,
          'node-error': !!canvas.nodeErrors[node.id],
        }"
        :style="{ left: `${node.x}px`, top: `${node.y}px` }"
        @mousedown="handleNodeMouseDown($event, node.id)"
        @click="onNodeClick($event, node.id)"
        @contextmenu="onNodeContextMenu($event, node.id)"
      >
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
        <!-- 输入锚点（顶部）：与输出端口对称，作为连线的接入点 -->
        <div
          v-if="node.type !== 'Input'"
          class="node-port node-port-in"
          title="连线接入点"
        ></div>
        <!-- 输出端口（底部）：按住拖到另一个节点即可连线 -->
        <div
          v-if="node.type !== 'Output'"
          class="node-port node-port-out"
          title="按住拖到另一个节点即可连线"
          @mousedown="onPortMouseDown($event, node.id)"
        ><iconify-icon icon="mdi:plus"></iconify-icon></div>
      </article>
    </div>
    </main>
  </section>
</template>
