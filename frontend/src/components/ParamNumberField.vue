<script setup lang="ts">
import { ref, watch } from "vue";
import { showToast } from "../store";
import InfoTip from "./InfoTip.vue";

const props = withDefaults(defineProps<{
  label: string;
  paramKey?: string;
  value: unknown;
  hint?: string;       // 参数解释（? 气泡）
  recommend?: string;  // 推荐取值范围
  min?: number;        // 最小允许值
  max?: number;        // 最大允许值
  integer?: boolean;   // 是否要求整数，默认要求整数
  step?: string | number;
  emptyMessage?: string;
  numberMessage?: string;
  integerMessage?: string;
  rangeMessage?: string;
}>(), {
  integer: true,
});

const emit = defineEmits<{
  change: [value: number];
}>();

const localError = ref("");

watch(() => props.value, () => {
  localError.value = "";
});

function reject(message: string) {
  localError.value = message;
  showToast("warning", message);
}

function handleChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const rawValue = input.value.trim();

  if (rawValue === "") {
    reject(props.emptyMessage || `${props.label} 不能为空。`);
    return;
  }

  const value = Number(rawValue);

  if (Number.isNaN(value) || !Number.isFinite(value)) {
    reject(props.numberMessage || `${props.label} 必须是数字。`);
    return;
  }

  if (props.integer && !Number.isInteger(value)) {
    reject(props.integerMessage || `${props.label} 必须是整数。`);
    return;
  }

  if (props.min !== undefined && value < props.min) {
    reject(props.rangeMessage || `${props.label} 不能小于 ${props.min}。`);
    return;
  }

  if (props.max !== undefined && value > props.max) {
    reject(props.rangeMessage || `${props.label} 不能大于 ${props.max}。`);
    return;
  }

  localError.value = "";
  emit("change", value);
}
</script>

<template>
  <label class="form-field" :data-param-key="paramKey">
    <span>{{ label }} <InfoTip v-if="hint" :text="hint" /></span>
    <input
      class="param-input"
      type="number"
      :value="(value as number | undefined) ?? ''"
      :min="min"
      :max="max"
      :step="step ?? (integer ? 1 : 'any')"
      :class="{ 'param-input-error': Boolean(localError) }"
      @change="handleChange"
    >
    <small v-if="localError" class="param-error">{{ localError }}</small>
    <small v-else-if="recommend" class="param-recommend">{{ recommend }}</small>
  </label>
</template>
