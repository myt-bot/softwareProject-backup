<script setup lang="ts">
// 术语/参数旁的"?"气泡：悬浮或聚焦时显示一句大白话解释
defineProps<{ text: string }>();
</script>

<template>
  <span class="info-tip" tabindex="0" @click.stop>
    <iconify-icon icon="mdi:help-circle-outline"></iconify-icon>
    <span class="info-tip-bubble">{{ text }}</span>
  </span>
</template>
