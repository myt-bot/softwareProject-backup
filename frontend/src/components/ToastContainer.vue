<script setup lang="ts">
import { toasts } from "../store";
import type { ToastType } from "../types";

const icons: Record<ToastType, string> = {
  success: "mdi:check-circle",
  error: "mdi:alert",
  warning: "mdi:clock-alert-outline",
  info: "mdi:information-outline",
};
</script>

<template>
  <div class="toast-container" id="toast-container">
    <div
      v-for="toast in toasts"
      :key="toast.id"
      class="toast"
      :class="[toast.type, { 'toast-out': toast.leaving }]"
    >
      <iconify-icon :icon="icons[toast.type] || 'mdi:information-outline'"></iconify-icon>
      <span>{{ toast.message }}</span>
    </div>
  </div>
</template>
