<script setup lang="ts">
import { computed, ref } from "vue";
import { NEW_CONTAINER_PAYLOAD } from "../canvas";
import { containerLibrary, layerGroups } from "../store";

const searchQuery = ref("");

// —— 手风琴：一次展开一组；搜索时全部展开以免漏掉匹配项 ——
const CONTAINER_TITLE = "自定义容器 / Container";
const openGroup = ref<string>(layerGroups[0]?.title ?? CONTAINER_TITLE); // 默认展开第一组
const searchActive = computed(() => searchQuery.value.trim().length > 0);
function toggleGroup(title: string) {
  openGroup.value = openGroup.value === title ? "" : title;
}
function isOpen(title: string) {
  return searchActive.value || openGroup.value === title;
}

function handleNewContainerDragStart(event: DragEvent) {
  event.dataTransfer?.setData("text/plain", NEW_CONTAINER_PAYLOAD);
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "copy";
  }
}

// "我的容器"：会话内已保存的可复用容器（按搜索词过滤）
const filteredContainers = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  return containerLibrary.items.filter(def => !query || def.name.toLowerCase().includes(query));
});

// 自定义容器文件夹的“露头”：空白容器 + 已保存容器，按实际数量取前 3（只有空白容器时就 1 片）
const containerPeeks = computed(() => {
  const peeks = [
    { icon: "mdi:package-variant-closed", color: "teal" },
    ...containerLibrary.items.map(def => ({ icon: "mdi:package-variant", color: def.color })),
  ];
  return peeks.slice(0, 3);
});

function handleContainerDragStart(event: DragEvent, defId: string) {
  event.dataTransfer?.setData("text/plain", `container:${defId}`);
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "copy";
  }
}

// 组件库节点悬停详细介绍卡（自定义样式，替代原生 title）
type LayerLike = { type: string; desc: string; icon: string; color: string; hint?: string };
const blankContainerLayer: LayerLike = {
  type: "空白容器",
  desc: "封装可复用子网络",
  icon: "mdi:package-variant-closed",
  color: "teal",
  hint: "把一段完整的网络结构打包成一个节点。拖到画布后双击进入子画板，在里面像搭普通模型一样放入层并连线；子图里的每个 Input 都会变成容器顶部的一个输入端口，每个 Output 都会变成底部的一个输出端口。适合封装残差块、编码器、分类头等重复结构，保存后还能在“我的容器”中反复拖入复用。",
};
const hovered = ref<{ layer: LayerLike; top: number; left: number } | null>(null);

function showTip(event: MouseEvent, layer: LayerLike) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  // 显示在组件项右侧，避免遮挡列表；纵向对齐并夹在视口内
  const top = Math.max(12, Math.min(rect.top - 4, window.innerHeight - 250));
  hovered.value = { layer, top, left: rect.right + 12 };
}
function hideTip() {
  hovered.value = null;
}

// 文件夹悬停介绍卡：列出该组包含的层
const hoveredGroup = ref<{ title: string; layers: LayerLike[]; top: number; left: number } | null>(null);
function showGroupTip(event: MouseEvent, title: string, layers: LayerLike[]) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  const height = Math.min(360, 70 + layers.length * 30);
  const top = Math.max(12, Math.min(rect.top - 4, window.innerHeight - height));
  hoveredGroup.value = { title, layers, top, left: rect.right + 12 };
}
function hideGroupTip() {
  hoveredGroup.value = null;
}
// 自定义容器组的“包含层”：空白容器 + 已保存容器
const containerTipLayers = computed<LayerLike[]>(() => [
  blankContainerLayer,
  ...containerLibrary.items.map(def => ({ type: def.name, desc: "已保存容器", icon: "mdi:package-variant", color: def.color })),
]);

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
      <!-- 自定义容器：拖入空白容器，双击进入子画板搭建内部 -->
      <section class="layer-group" :class="{ collapsed: !isOpen(CONTAINER_TITLE) }">
        <div class="folder-back" aria-hidden="true"></div>
        <div class="folder-peeks" aria-hidden="true">
          <span
            v-for="(pk, i) in containerPeeks"
            :key="i"
            :class="`folder-peek p${i} ${pk.color}`"
          ><iconify-icon :icon="pk.icon"></iconify-icon></span>
        </div>
        <div class="folder-front">
        <h3
          @click="toggleGroup(CONTAINER_TITLE)"
          @mouseenter="showGroupTip($event, '自定义容器 / Container', containerTipLayers)"
          @mouseleave="hideGroupTip"
        >
          <span>自定义容器 / Container</span>
          <iconify-icon class="layer-group-chevron" icon="mdi:chevron-down"></iconify-icon>
        </h3>
        <div class="layer-group-body">
          <div class="layer-items">
          <article
            class="layer-item layer-item-container"
            draggable="true"
            @mouseenter="showTip($event, blankContainerLayer)"
            @mouseleave="hideTip"
            @dragstart="handleNewContainerDragStart($event); hideTip()"
          >
            <span class="layer-icon teal"><iconify-icon icon="mdi:package-variant-closed"></iconify-icon></span>
            <div>
              <strong>空白容器</strong>
              <span>拖入后双击进入编辑</span>
            </div>
          </article>
          <article
            v-for="def in filteredContainers"
            :key="def.defId"
            class="layer-item"
            draggable="true"
            @dragstart="handleContainerDragStart($event, def.defId)"
          >
            <span :class="`layer-icon ${def.color}`"><iconify-icon icon="mdi:package-variant"></iconify-icon></span>
            <div>
              <strong>{{ def.name }}</strong>
              <span>已保存容器</span>
            </div>
          </article>
          </div>
        </div>
        </div>
      </section>

      <section
        v-for="group in filteredGroups"
        :key="group.title"
        class="layer-group"
        :class="{ collapsed: !isOpen(group.title) }"
        v-show="group.layers.some(layer => layer.matched)"
      >
        <div class="folder-back" aria-hidden="true"></div>
        <div class="folder-peeks" aria-hidden="true">
          <span
            v-for="(layer, i) in group.layers.slice(0, 3)"
            :key="i"
            :class="`folder-peek p${i} ${layer.color}`"
          ><iconify-icon :icon="layer.icon"></iconify-icon></span>
        </div>
        <div class="folder-front">
        <h3
          @click="toggleGroup(group.title)"
          @mouseenter="showGroupTip($event, group.title, group.layers)"
          @mouseleave="hideGroupTip"
        >
          <span>{{ group.title }}</span>
          <iconify-icon class="layer-group-chevron" icon="mdi:chevron-down"></iconify-icon>
        </h3>
        <div class="layer-group-body">
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
        </div>
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

  <!-- 文件夹悬停介绍卡：列出该组包含的层 -->
  <Teleport to="body">
    <div
      v-if="hoveredGroup"
      class="layer-tip-card group-tip-card"
      :style="{ top: `${hoveredGroup.top}px`, left: `${hoveredGroup.left}px` }"
    >
      <div class="group-tip-title">
        <iconify-icon icon="mdi:folder-outline"></iconify-icon>
        <strong>{{ hoveredGroup.title }}</strong>
        <em>{{ hoveredGroup.layers.length }} 个层</em>
      </div>
      <div class="group-tip-list">
        <div v-for="l in hoveredGroup.layers" :key="l.type" class="group-tip-item">
          <span :class="`layer-icon ${l.color}`"><iconify-icon :icon="l.icon"></iconify-icon></span>
          <span class="group-tip-name">{{ l.type }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>
