<script setup lang="ts">
import { agent, showToast, store } from "../store";
import InfoTip from "./InfoTip.vue";

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
    <span class="dataset-label">设备 <InfoTip text="选择用 CPU 还是 GPU 来做训练计算。GPU（显卡）的并行算力远高于 CPU，检测到可用 GPU 时建议优先选它；没有可用 GPU 时会自动改用 CPU，速度较慢但一样能完成训练。" /></span>
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
