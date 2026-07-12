<script setup lang="ts">
import { computed } from "vue";
import {
  connectFromMenuNode,
  deleteMenuConnection,
  deleteMenuNode,
  enterContainerFromMenu,
} from "../canvas";
import { activeCanvas, store } from "../store";

// 右键所指节点是否为容器（决定显示"进入编辑"、隐藏"进行连线"）
const menuNodeIsContainer = computed(() => {
  const node = activeCanvas().nodes.find(item => item.id === store.menuNodeId);
  return node?.type === "Container";
});
</script>

<template>
  <div
    class="context-menu"
    :class="{ hidden: !store.connectionMenu.visible }"
    id="connection-menu"
    :style="{ left: `${store.connectionMenu.x}px`, top: `${store.connectionMenu.y}px` }"
  >
    <button id="btn-delete-connection" class="text-rose" @click="deleteMenuConnection">
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
    <button v-if="menuNodeIsContainer" id="btn-enter-container" @click="enterContainerFromMenu">
      <iconify-icon icon="mdi:folder-open-outline"></iconify-icon>
      进入容器编辑
    </button>
    <button v-else id="btn-connect-node" @click="connectFromMenuNode">
      <iconify-icon icon="mdi:transit-connection-variant"></iconify-icon>
      进行连线
    </button>
    <button id="btn-delete-node" class="text-rose" @click="deleteMenuNode">
      <iconify-icon icon="mdi:delete-outline"></iconify-icon>
      删除节点
    </button>
  </div>
</template>
