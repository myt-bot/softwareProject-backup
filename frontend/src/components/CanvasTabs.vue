<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import {
  addCanvas,
  autoLayoutGraph,
  centerGraphInCanvas,
  closeCanvas,
  redoGraphChange,
  switchCanvas,
  undoGraphChange,
} from "../canvas";
import { activeCanvas, isTrainingJobActive, store, ui } from "../store";
import type { WorkCanvas } from "../store";

// 空画布时由画布中央的大 CTA 提供模板入口，这里的右上角按钮就不再重复出现
const canvasHasNodes = computed(() => activeCanvas().nodes.length > 0);

// 有进行中训练任务的标签显示脉冲圆点，便于并行训练时一眼看到状态
function isTraining(canvas: WorkCanvas) {
  return isTrainingJobActive(canvas.trainingJob);
}

// 双击标签名进入重命名
const renamingId = ref<number | null>(null);
const renamingValue = ref("");

function startRename(canvas: WorkCanvas) {
  renamingId.value = canvas.id;
  renamingValue.value = canvas.name;
  void nextTick(() => {
    const input = document.querySelector<HTMLInputElement>(".canvas-tab-rename");
    input?.focus();
    input?.select();
  });
}

function commitRename(canvas: WorkCanvas) {
  if (renamingId.value !== canvas.id) return;
  const name = renamingValue.value.trim();
  if (name) {
    canvas.name = name;
  }
  renamingId.value = null;
}

function cancelRename() {
  renamingId.value = null;
}
</script>

<template>
  <div class="canvas-tabs">
    <!-- 仅标签列表滚动，右侧常用工具始终留在可视区域 -->
    <div class="canvas-tab-list">
      <button
        v-for="canvas in store.canvases"
        :key="canvas.id"
        class="canvas-tab"
        :class="{ active: canvas.id === store.activeCanvasId }"
        :title="`${canvas.name}（双击重命名）`"
        @click="switchCanvas(canvas.id)"
        @dblclick="startRename(canvas)"
      >
        <iconify-icon icon="mdi:vector-polyline"></iconify-icon>
        <input
          v-if="renamingId === canvas.id"
          v-model="renamingValue"
          class="canvas-tab-rename"
          maxlength="20"
          @click.stop
          @dblclick.stop
          @keydown.enter="commitRename(canvas)"
          @keydown.esc="cancelRename"
          @blur="commitRename(canvas)"
        >
        <span v-else class="canvas-tab-name">{{ canvas.name }}</span>
        <span v-if="isTraining(canvas)" class="canvas-tab-dot" title="训练进行中"></span>
        <span
          class="canvas-tab-close"
          title="关闭画布"
          @click.stop="closeCanvas(canvas.id)"
        ><iconify-icon icon="mdi:close"></iconify-icon></span>
      </button>
      <button class="canvas-tab-add" title="新建画布" @click="addCanvas">
        <iconify-icon icon="mdi:plus"></iconify-icon>
      </button>
    </div>

    <!-- 常用编辑操作直接放在模板入口前：撤销/重做只保留图标，布局操作保留文字 -->
    <nav v-if="canvasHasNodes" class="tab-canvas-tools" aria-label="画布编辑工具">
      <button
        type="button"
        class="icon-only"
        id="btn-undo"
        aria-label="撤销上一步"
        title="撤销上一步 (Ctrl+Z)"
        @click="undoGraphChange"
      >
        <iconify-icon icon="mdi:undo-variant"></iconify-icon>
      </button>
      <button
        type="button"
        class="icon-only"
        id="btn-redo"
        aria-label="重做"
        title="重做 (Ctrl+Shift+Z / Ctrl+Y)"
        @click="redoGraphChange"
      >
        <iconify-icon icon="mdi:redo-variant"></iconify-icon>
      </button>
      <span class="tab-canvas-tools-divider" aria-hidden="true"></span>
      <button
        type="button"
        class="primary"
        id="btn-auto-layout"
        title="3 个及以下节点竖排，更多节点向右折列，分支左右展开"
        @click="autoLayoutGraph"
      >
        <iconify-icon icon="mdi:sitemap-outline"></iconify-icon>
        <span>智能布局</span>
      </button>
      <button
        type="button"
        id="zoom-fit"
        title="定位并居中所有节点"
        @click="centerGraphInCanvas"
      >
        <iconify-icon icon="mdi:fit-to-screen-outline"></iconify-icon>
        <span>适应视图</span>
      </button>
    </nav>

    <!-- 快速开始模板入口（画布非空时才显示，空态由中央大 CTA 承担，避免重复） -->
    <button v-if="canvasHasNodes" class="template-gallery-button" id="btn-template-gallery" title="从经典网络模板快速开始" @click="ui.templateGalleryOpen = true">
      <iconify-icon icon="mdi:lightning-bolt"></iconify-icon>
      快速开始模板
    </button>
  </div>
</template>
