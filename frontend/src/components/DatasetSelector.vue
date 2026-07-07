<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { datasetChoices, store } from "../store";

const dropdownOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

function toggleDropdown(event: MouseEvent) {
  event.stopPropagation();
  dropdownOpen.value = !dropdownOpen.value;
}

function selectDataset(event: MouseEvent, value: string) {
  event.stopPropagation();
  store.dataset = value;
  dropdownOpen.value = false;
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
    <span class="dataset-label">数据集</span>

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
