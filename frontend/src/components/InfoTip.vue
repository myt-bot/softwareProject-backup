<script setup lang="ts">
// 术语/参数旁的"?"气泡：悬浮或聚焦时显示一句大白话解释。
// 气泡 Teleport 到 body 并用 fixed 定位，避免被右侧参数面板（overflow 容器）裁切，
// 也不会撑出面板的横向滚动条。
import { onBeforeUnmount, ref } from "vue";

defineProps<{ text: string }>();

const anchor = ref<HTMLElement | null>(null);
const open = ref(false);
const style = ref<Record<string, string>>({});

function show() {
  const el = anchor.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const half = 125; // 气泡最大宽度 250 的一半，用于夹在视口内
  const left = Math.min(Math.max(rect.left + rect.width / 2, half + 8), window.innerWidth - half - 8);
  style.value = { top: `${rect.top - 9}px`, left: `${left}px` };
  open.value = true;
}

function hide() {
  open.value = false;
}

onBeforeUnmount(hide);
</script>

<template>
  <span
    ref="anchor"
    class="info-tip"
    tabindex="0"
    @mouseenter="show"
    @mouseleave="hide"
    @focus="show"
    @blur="hide"
    @click.stop
  >
    <iconify-icon icon="mdi:help-circle-outline"></iconify-icon>
  </span>

  <Teleport to="body">
    <span v-if="open" class="info-tip-bubble" :style="style">{{ text }}</span>
  </Teleport>
</template>
