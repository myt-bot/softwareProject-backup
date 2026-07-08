<script setup lang="ts">
import { computed, ref } from "vue";
import { layerGroups } from "../store";

const searchQuery = ref("");

// 组件库节点悬停详细介绍卡（自定义样式，替代原生 title）
type LayerLike = { type: string; desc: string; icon: string; color: string; hint?: string };
const hovered = ref<{ layer: LayerLike; top: number; left: number } | null>(null);

function showTip(event: MouseEvent, layer: LayerLike) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  // 显示在组件项右侧，避免遮挡列表；纵向对齐并夹在视口内
  const top = Math.max(12, Math.min(rect.top - 4, window.innerHeight - 190));
  hovered.value = { layer, top, left: rect.right + 12 };
}
function hideTip() {
  hovered.value = null;
}

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
    <div class="sidebar-inner">
    <div class="sidebar-header">
      <h2><iconify-icon icon="mdi:shape-plus"></iconify-icon>网络层组件库</h2>
      <p>把下面的“积木”拖到中间画布上</p>
    </div>
    <div class="sidebar-search">
      <iconify-icon icon="mdi:magnify"></iconify-icon>
      <input type="text" id="layer-search-input" placeholder="搜索组件，例如 Conv" v-model="searchQuery">
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
            @mouseenter="showTip($event, layer)"
            @mouseleave="hideTip"
            @dragstart="handleDragStart($event, layer.type); hideTip()"
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
    </div>
  </aside>

  <!-- 悬停详细介绍卡：Teleport 到 body，避免被侧栏裁剪；风格与系统统一 -->
  <Teleport to="body">
    <div
      v-if="hovered"
      class="layer-tip-card"
      :style="{ top: `${hovered.top}px`, left: `${hovered.left}px` }"
    >
      <div class="layer-tip-head">
        <span :class="`layer-icon ${hovered.layer.color}`">
          <iconify-icon :icon="hovered.layer.icon"></iconify-icon>
        </span>
        <div>
          <strong>{{ hovered.layer.type }}</strong>
          <span>{{ hovered.layer.desc }}</span>
        </div>
      </div>
      <p class="layer-tip-body">{{ hovered.layer.hint || hovered.layer.desc }}</p>
      <div class="layer-tip-foot">
        <iconify-icon icon="mdi:gesture-tap-hold"></iconify-icon>
        按住拖到中间画布即可添加
      </div>
    </div>
  </Teleport>
</template>
