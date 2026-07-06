<script setup lang="ts">
import { computed, ref } from "vue";
import { loadTemplateToCanvas } from "../actions";
import { layerGroups, templateChoices } from "../store";

const searchQuery = ref("");

// 按搜索词过滤组件库（与原实现一致：匹配名称或描述）
const filteredGroups = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  return layerGroups.map(group => ({
    ...group,
    layers: group.layers.map(layer => ({
      ...layer,
      matched: !query || `${layer.type} ${layer.desc}`.toLowerCase().includes(query),
    })),
  }));
});

function handleDragStart(event: DragEvent, layerType: string) {
  event.dataTransfer?.setData("text/plain", layerType);
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "copy";
  }
}
</script>

<template>
  <!-- 左侧：网络层组件库 -->
  <aside class="layer-sidebar">
    <div class="sidebar-header">
      <h2><iconify-icon icon="mdi:shape-plus"></iconify-icon>网络层组件库</h2>
      <p>把下面的“积木”拖到中间画布上</p>
    </div>
    <div class="sidebar-search">
      <iconify-icon icon="mdi:magnify"></iconify-icon>
      <input type="text" id="layer-search-input" placeholder="搜索组件，例如 Conv" v-model="searchQuery">
    </div>
    <div class="template-section">
      <h3><iconify-icon icon="mdi:lightning-bolt"></iconify-icon>快速开始模板</h3>
      <div class="template-tabs">
        <button
          v-for="template in templateChoices"
          :key="template.key"
          :data-template="template.key"
          :title="template.title"
          @click="loadTemplateToCanvas(template.key)"
        >{{ template.label }}</button>
      </div>
    </div>
    <div class="layer-list" id="layer-palette">
      <section
        v-for="group in filteredGroups"
        :key="group.title"
        class="layer-group"
        v-show="group.layers.some(layer => layer.matched)"
      >
        <h3>{{ group.title }}</h3>
        <div class="layer-items">
          <article
            v-for="layer in group.layers"
            :key="layer.type"
            v-show="layer.matched"
            class="layer-item"
            :data-layer-type="layer.type"
            draggable="true"
            title="按住拖拽到中间画布即可添加"
            @dragstart="handleDragStart($event, layer.type)"
          >
            <span :class="`layer-icon ${layer.color}`"><iconify-icon :icon="layer.icon"></iconify-icon></span>
            <div>
              <strong>{{ layer.type }}</strong>
              <span>{{ layer.desc }}</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  </aside>
</template>
