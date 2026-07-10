<script setup lang="ts">
// 与系统风格统一的自定义下拉（替代原生 <select>，原生选项列表无法用 CSS 定制）。
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps<{
  modelValue: string;
  options: { value: string; label: string }[];
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const open = ref(false);
const rootRef = ref<HTMLElement | null>(null);

const currentLabel = computed(
  () => props.options.find(option => option.value === props.modelValue)?.label ?? props.modelValue
);

function toggle(event: MouseEvent) {
  event.stopPropagation();
  open.value = !open.value;
}

function pick(event: MouseEvent, value: string) {
  event.stopPropagation();
  emit("update:modelValue", value);
  open.value = false;
}

function handleDocumentClick(event: MouseEvent) {
  if (!rootRef.value?.contains(event.target as Node)) {
    open.value = false;
  }
}

onMounted(() => document.addEventListener("click", handleDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", handleDocumentClick));
</script>

<template>
  <div ref="rootRef" class="field-select" :class="{ open }" @click="toggle">
    <span class="field-select-value">{{ currentLabel }}</span>
    <iconify-icon icon="mdi:chevron-down" class="field-select-arrow"></iconify-icon>

    <div class="field-select-menu">
      <div
        v-for="option in options"
        :key="option.value"
        class="field-select-option"
        :class="{ active: option.value === modelValue }"
        @click="pick($event, option.value)"
      >
        <span>{{ option.label }}</span>
        <iconify-icon v-if="option.value === modelValue" icon="mdi:check" class="field-select-check"></iconify-icon>
      </div>
    </div>
  </div>
</template>
