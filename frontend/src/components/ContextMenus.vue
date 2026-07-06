<script setup lang="ts">
import { connectFromMenuNode, deleteMenuConnection, deleteMenuNode } from "../canvas";
import { store } from "../store";
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
    <button id="btn-delete-node" class="text-rose" @click="deleteMenuNode">
      <iconify-icon icon="mdi:delete-outline"></iconify-icon>
      删除节点
    </button>
  </div>
</template>
