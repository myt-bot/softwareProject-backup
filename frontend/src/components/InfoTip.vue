<script setup lang="ts">
// 术语/参数旁的 "?" 气泡：悬浮或聚焦时只显示当前这一条说明。
// 说明气泡 Teleport 到 body 并用 fixed 定位，避免被右侧参数面板裁切。
// 另外通过全局自定义事件保证同一时间只显示一个气泡，避免多个解释框常驻挡住页面。
import { onBeforeUnmount, onMounted, ref } from "vue";

defineProps<{ text: string }>();

const anchor = ref<HTMLElement | null>(null);
const open = ref(false);
const style = ref<Record<string, string>>({});
const tipId = `info-tip-${Math.random().toString(36).slice(2)}`;

function updatePosition() {
  const el = anchor.value;
  if (!el) return;

  const rect = el.getBoundingClientRect();
  const bubbleHalfWidth = 125; // 与 CSS max-width: 250px 对应，防止气泡超出屏幕
  const left = Math.min(
    Math.max(rect.left + rect.width / 2, bubbleHalfWidth + 8),
    window.innerWidth - bubbleHalfWidth - 8,
  );

  style.value = {
    top: `${Math.max(rect.top - 9, 12)}px`,
    left: `${left}px`,
  };
}

function show() {
  window.dispatchEvent(new CustomEvent("info-tip-open", { detail: tipId }));
  updatePosition();
  open.value = true;
}

function hide() {
  open.value = false;
}

function handleOtherTipOpen(event: Event) {
  const customEvent = event as CustomEvent<string>;
  if (customEvent.detail !== tipId) {
    hide();
  }
}

function handleWindowChange() {
  // 滚动、缩放、窗口变化时关闭气泡，避免位置错乱或残留在页面上。
  hide();
}

function handlePointerDown(event: PointerEvent) {
  const el = anchor.value;
  if (el && !el.contains(event.target as Node)) {
    hide();
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    hide();
  }
}

onMounted(() => {
  window.addEventListener("info-tip-open", handleOtherTipOpen as EventListener);
  window.addEventListener("resize", handleWindowChange);
  window.addEventListener("scroll", handleWindowChange, true);
  document.addEventListener("pointerdown", handlePointerDown, true);
  document.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  hide();
  window.removeEventListener("info-tip-open", handleOtherTipOpen as EventListener);
  window.removeEventListener("resize", handleWindowChange);
  window.removeEventListener("scroll", handleWindowChange, true);
  document.removeEventListener("pointerdown", handlePointerDown, true);
  document.removeEventListener("keydown", handleKeydown);
});
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
    @click.stop="show"
  >
    <iconify-icon icon="mdi:help-circle-outline"></iconify-icon>
  </span>

  <Teleport to="body">
    <span v-if="open" class="info-tip-bubble" :style="style">{{ text }}</span>
  </Teleport>
</template>
