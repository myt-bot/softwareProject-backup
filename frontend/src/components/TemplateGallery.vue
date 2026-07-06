<script setup lang="ts">
import { loadTemplateToCanvas } from "../actions";
import { templateLibrary, ui } from "../store";
import type { TemplateMeta } from "../types";

// 模板分类的展示样式（图标 + 中文标签 + 颜色）
const FAMILY_STYLES: Record<string, { icon: string; label: string; color: string }> = {
  feedforward: { icon: "mdi:ray-start-end", label: "全连接", color: "cyan" },
  cnn: { icon: "mdi:grid-large", label: "卷积", color: "blue" },
  sequence: { icon: "mdi:repeat", label: "序列", color: "indigo" },
  attention: { icon: "mdi:eye-outline", label: "注意力", color: "purple" },
  generative: { icon: "mdi:creation", label: "生成", color: "rose" },
  graph: { icon: "mdi:graph", label: "图网络", color: "emerald" },
};

function familyStyle(template: TemplateMeta) {
  return FAMILY_STYLES[template.family || ""] || { icon: "mdi:shape-outline", label: "模板", color: "cyan" };
}

function shapeText(template: TemplateMeta) {
  const input = template.input_shape?.join("×");
  const output = template.output_shape?.join("×");
  return input && output ? `${input} → ${output}` : "";
}

function close() {
  ui.templateGalleryOpen = false;
}

function pick(template: TemplateMeta) {
  void loadTemplateToCanvas(template.key, template.name);
}
</script>

<template>
  <!-- 快速开始模板库 -->
  <div class="modal" :class="{ hidden: !ui.templateGalleryOpen }" id="template-gallery">
    <div class="modal-card template-gallery-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:lightning-bolt"></iconify-icon>
          <div>
            <h2>快速开始模板</h2>
            <p>选择一个经典网络，一键加载到当前画布</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-gallery" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="template-grid">
        <button
          v-for="template in templateLibrary.items"
          :key="template.key"
          class="template-card"
          :data-template="template.key"
          @click="pick(template)"
        >
          <div class="template-card-head">
            <span :class="`template-icon ${familyStyle(template).color}`">
              <iconify-icon :icon="familyStyle(template).icon"></iconify-icon>
            </span>
            <span :class="`template-tag ${familyStyle(template).color}`">{{ familyStyle(template).label }}</span>
          </div>
          <strong>{{ template.name }}</strong>
          <p>{{ template.description }}</p>
          <code v-if="shapeText(template)">{{ shapeText(template) }}</code>
        </button>
      </div>
    </div>
  </div>
</template>
