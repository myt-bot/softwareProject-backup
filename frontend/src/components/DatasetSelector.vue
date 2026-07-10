<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { applyDatasetInputShapes, datasetChoices, datasetInputShape, showToast, store } from "../store";
import { redrawAfterDomUpdate } from "../canvas";
import InfoTip from "./InfoTip.vue";

const dropdownOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

function toggleDropdown(event: MouseEvent) {
  event.stopPropagation();
  dropdownOpen.value = !dropdownOpen.value;
}

function selectDataset(event: MouseEvent, value: string) {
  event.stopPropagation();
  dropdownOpen.value = false;
  if (store.dataset === value) return;

  store.dataset = value;
  // 切换数据集：把所有画布的 Input 形状同步为该数据集对应的维度，新手无需手动记忆
  const changed = applyDatasetInputShapes();
  const shapeText = datasetInputShape().join("×");
  if (changed) {
    showToast("success", `已切换到 ${value}，输入维度自动设为 ${shapeText}（请重新「检查结构」）。`);
    void redrawAfterDomUpdate();
  } else {
    showToast("info", `已切换到 ${value}，输入维度为 ${shapeText}。`);
  }
}

// 点击页面其他区域时关闭下拉菜单
function handleDocumentClick(event: MouseEvent) {
  if (!dropdownRef.value?.contains(event.target as Node)) {
    dropdownOpen.value = false;
  }
}

onMounted(() => document.addEventListener("click", handleDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", handleDocumentClick));
</script>

<template>
  <div class="dataset-pill">
    <span class="dataset-label">数据集 <InfoTip text="用来训练模型的数据。可在右侧下拉里挑选不同的数据集，它们的图片内容、尺寸和类别数量各不相同；首次使用某个数据集时会自动下载并缓存到本地。" /></span>

    <!-- 圆润风格的自定义下拉菜单（向上弹出，适配底栏） -->
    <div
      ref="dropdownRef"
      class="dataset-card drop-up"
      :class="{ open: dropdownOpen }"
      id="custom-dataset-dropdown"
      title="选择用于训练模型的数据集"
      @click="toggleDropdown"
    >
      <iconify-icon icon="mdi:database"></iconify-icon>
      <div class="custom-select-value" id="custom-select-value">{{ store.dataset }}</div>
      <iconify-icon icon="mdi:chevron-down" class="arrow-icon"></iconify-icon>

      <div class="custom-options">
        <div
          v-for="choice in datasetChoices"
          :key="choice.value"
          class="custom-option"
          :class="{ active: store.dataset === choice.value }"
          :data-value="choice.value"
          @click="selectDataset($event, choice.value)"
        >{{ choice.label }}</div>
      </div>
    </div>
  </div>
</template>
