<script setup lang="ts">
import { nextTick, ref } from "vue";
import { addCanvas, closeCanvas, switchCanvas } from "../canvas";
import { store } from "../store";
import type { WorkCanvas } from "../store";

// 有进行中训练任务的标签显示脉冲圆点，便于并行训练时一眼看到状态
function isTraining(canvas: WorkCanvas) {
  return ["pending", "running"].includes(canvas.trainingJob?.status || "");
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
        v-if="store.canvases.length > 1"
        class="canvas-tab-close"
        title="关闭画布"
        @click.stop="closeCanvas(canvas.id)"
      ><iconify-icon icon="mdi:close"></iconify-icon></span>
    </button>
    <button class="canvas-tab-add" title="新建画布" @click="addCanvas">
      <iconify-icon icon="mdi:plus"></iconify-icon>
    </button>
  </div>
</template>
