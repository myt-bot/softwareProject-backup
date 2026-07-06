<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
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
  registerCanvasElements,
  selectNode,
  showNodeMenu,
} from "../canvas";
import { showToast, store } from "../store";

const canvasRef = ref<HTMLElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const nodesRef = ref<HTMLElement | null>(null);
const gridRef = ref<HTMLElement | null>(null);

const zoomLabel = computed(() => `${Math.round(store.zoom * 100)}%`);

const statusBadgeText = computed(() =>
  store.nodeBadge === "passed" ? "通过" : store.nodeBadge === "pending" ? "待检查" : "未校验"
);
const statusBadgeClass = computed(() =>
  store.nodeBadge === "passed" ? "status-badge passed" : "status-badge"
);

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
  <!-- 中间：模型画布 -->
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
    <div class="zoom-control">
      <button id="zoom-out" title="缩小画布" @click="handleZoomAction('zoom-out')"><iconify-icon icon="mdi:minus"></iconify-icon></button>
      <span>{{ zoomLabel }}</span>
      <button id="zoom-in" title="放大画布" @click="handleZoomAction('zoom-in')"><iconify-icon icon="mdi:plus"></iconify-icon></button>
      <i></i>
      <button id="zoom-fit" title="定位到节点并居中" @click="centerGraphInCanvas"><iconify-icon icon="mdi:image-filter-center-focus"></iconify-icon></button>
    </div>
    <div ref="gridRef" class="canvas-grid connections-svg"></div>
    <svg ref="svgRef" class="connections-svg" id="connections-svg"></svg>
    <div ref="nodesRef" class="nodes-container" id="nodes-container">
      <article
        v-for="node in store.nodes"
        :key="node.id"
        class="node-card"
        :id="`node-${node.id}`"
        :data-node-id="node.id"
        :class="{
          'node-selected': store.selectedNodeId === node.id,
          'connection-source': store.connectSourceId === node.id,
          'connection-target': store.connectTargetId === node.id,
          'node-dragging': store.draggingNodeId === node.id,
        }"
        :style="{ left: `${node.x}px`, top: `${node.y}px` }"
        @mousedown="handleNodeMouseDown($event, node.id)"
        @click="onNodeClick($event, node.id)"
        @contextmenu="onNodeContextMenu($event, node.id)"
      >
        <div class="node-head">
          <span :class="`node-type ${node.color}`">{{ node.badge }}</span>
          <span :class="statusBadgeClass">{{ statusBadgeText }}</span>
        </div>
        <h4>{{ node.title }}</h4>
        <p v-if="node.note" class="node-note">{{ node.note }}</p>
        <div class="shape-row">
          <span>Shape Hint:</span>
          <strong class="shape-value">{{ node.hint }}</strong>
        </div>
      </article>
    </div>
  </main>
</template>
