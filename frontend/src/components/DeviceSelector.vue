<script setup lang="ts">
import { agent, showToast, store } from "../store";

// 训练设备选择：CPU / GPU（cuda）。GPU 不可用时禁用并提示。
function selectDevice(device: "cpu" | "cuda") {
  if (device === "cuda" && !store.cudaAvailable) {
    showToast(
      "warning",
      agent.online
        ? "未检测到可用的 GPU，将使用 CPU 训练。"
        : "请先运行本机训练应用，才能检测你电脑上的 GPU。"
    );
    return;
  }
  if (store.device === device) return;
  store.device = device;
  showToast("info", device === "cuda" ? "训练将使用 GPU 加速。" : "训练将使用 CPU。");
}
</script>

<template>
  <div class="device-pill">
    <span class="dataset-label">训练设备</span>
    <div class="device-toggle" title="选择训练模型时使用的计算设备">
      <button
        id="device-cpu"
        :class="{ active: store.device === 'cpu' }"
        @click="selectDevice('cpu')"
      >
        <iconify-icon icon="mdi:cpu-64-bit"></iconify-icon>
        CPU
      </button>
      <button
        id="device-gpu"
        :class="{ active: store.device === 'cuda', unavailable: !store.cudaAvailable }"
        :title="store.cudaAvailable ? 'NVIDIA GPU 加速训练' : '未检测到可用的 GPU'"
        @click="selectDevice('cuda')"
      >
        <iconify-icon icon="mdi:expansion-card"></iconify-icon>
        GPU
      </button>
    </div>
  </div>
</template>
