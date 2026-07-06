<script setup lang="ts">
import { showToast } from "../store";

defineProps<{
  label: string;
  value: unknown;
}>();

const emit = defineEmits<{
  change: [value: number];
}>();

function handleChange(event: Event) {
  const rawValue = (event.target as HTMLInputElement).value;

  if (rawValue === "") {
    showToast("warning", "参数不能为空。");
    return;
  }

  const value = Number(rawValue);

  if (Number.isNaN(value)) {
    showToast("warning", "参数必须是数字。");
    return;
  }

  emit("change", value);
}
</script>

<template>
  <label class="form-field">
    <span>{{ label }}</span>
    <input class="param-input" type="number" :value="(value as number | undefined) ?? ''" @change="handleChange">
  </label>
</template>
