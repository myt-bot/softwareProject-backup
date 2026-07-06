<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { datasetChoices, datasetOptions, openHelpModal, store } from "../store";

const dropdownOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

const shapeLabel = computed(() => datasetOptions[store.dataset]?.shapeLabel || "");

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
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark">
        <iconify-icon icon="mdi:brain"></iconify-icon>
      </div>
      <h1>模型工坊<span>深度学习可视化搭建平台</span></h1>
    </div>

    <div class="dataset-pill">
      <span class="dataset-label">训练数据集</span>

      <!-- 圆润风格的自定义下拉菜单 -->
      <div
        ref="dropdownRef"
        class="dataset-card"
        :class="{ open: dropdownOpen }"
        id="custom-dataset-dropdown"
        title="选择用于训练模型的数据集"
        @click="toggleDropdown"
      >
        <iconify-icon icon="mdi:database"></iconify-icon>

        <!-- 当前展示值 -->
        <div class="custom-select-value" id="custom-select-value">{{ store.dataset }}</div>
        <iconify-icon icon="mdi:chevron-down" class="arrow-icon"></iconify-icon>

        <!-- 下拉选项面板 -->
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

        <span id="dataset-shape" class="shape-badge">{{ shapeLabel }}</span>
      </div>
    </div>

    <div class="top-actions">
      <button class="guide-button" id="btn-help" title="打开新手指南" @click="openHelpModal">
        <iconify-icon icon="mdi:school-outline"></iconify-icon>
        新手指南
      </button>
      <div class="avatar"></div>
    </div>
  </header>
</template>
