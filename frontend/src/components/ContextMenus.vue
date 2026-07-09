<script setup lang="ts">
import { computed } from "vue";
import {
  connectFromMenuNode,
  deleteMenuConnection,
  deleteMenuNode,
  groupFromMenu,
  ungroupFromMenu,
} from "../canvas";
import { activeCanvas, store } from "../store";

// 右键所指节点是否为容器（决定是否显示"解组"）
const menuNodeIsContainer = computed(() => {
  const node = activeCanvas().nodes.find(item => item.id === store.menuNodeId);
  return node?.type === "Container";
});

// 当前多选是否达到可打包的数量
const canGroup = computed(() => activeCanvas().selectedNodeIds.length >= 2);
</script>

<template>
  <div
    class="context-menu"
    :class="{ hidden: !store.connectionMenu.visible }"
    id="connection-menu"
    :style="{ left: `${store.connectionMenu.x}px`, top: `${store.connectionMenu.y}px` }"
  >
    <button id="btn-delete-connection" @click="deleteMenuConnection">
      <iconify-icon icon="mdi:link-variant-off"></iconify-icon>
      删除连线
    </button>
  </div>
  <div
    class="context-menu"
    :class="{ hidden: !store.nodeMenu.visible }"
    id="node-menu"
    :style="{ left: `${store.nodeMenu.x}px`, top: `${store.nodeMenu.y}px` }"
  >
    <button id="btn-connect-node" @click="connectFromMenuNode">
      <iconify-icon icon="mdi:transit-connection-variant"></iconify-icon>
      进行连线
    </button>
    <button v-if="canGroup" id="btn-group-container" @click="groupFromMenu">
      <iconify-icon icon="mdi:package-variant-closed"></iconify-icon>
      打包为容器
    </button>
    <button v-if="menuNodeIsContainer" id="btn-ungroup-container" @click="ungroupFromMenu">
      <iconify-icon icon="mdi:package-variant"></iconify-icon>
      解组容器
    </button>
    <button id="btn-delete-node" class="text-rose" @click="deleteMenuNode">
      <iconify-icon icon="mdi:delete-outline"></iconify-icon>
      删除节点
    </button>
  </div>
</template>
