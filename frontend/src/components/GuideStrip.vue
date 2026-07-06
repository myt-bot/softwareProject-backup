<script setup lang="ts">
import { dismissGuideStrip, ui } from "../store";
</script>

<template>
  <!-- 新手引导条：四步上手 -->
  <div class="guide-strip" :class="{ hidden: ui.guideStripHidden }" id="guide-strip">
    <div class="guide-steps">
      <div class="guide-step">
        <span class="guide-step-num">1</span>
        <div>
          <strong>拖入组件</strong>
          <span>从左侧组件库拖到画布</span>
        </div>
      </div>
      <iconify-icon class="guide-arrow" icon="mdi:chevron-right"></iconify-icon>
      <div class="guide-step">
        <span class="guide-step-num">2</span>
        <div>
          <strong>连接节点</strong>
          <span>右键节点，选择“进行连线”</span>
        </div>
      </div>
      <iconify-icon class="guide-arrow" icon="mdi:chevron-right"></iconify-icon>
      <div class="guide-step">
        <span class="guide-step-num">3</span>
        <div>
          <strong>检查结构</strong>
          <span>点击底部“检查结构”按钮</span>
        </div>
      </div>
      <iconify-icon class="guide-arrow" icon="mdi:chevron-right"></iconify-icon>
      <div class="guide-step">
        <span class="guide-step-num">4</span>
        <div>
          <strong>开始训练</strong>
          <span>检查通过后一键训练</span>
        </div>
      </div>
    </div>
    <button class="guide-close" id="btn-close-guide" title="收起引导条" @click="dismissGuideStrip">
      <iconify-icon icon="mdi:close"></iconify-icon>
    </button>
  </div>
</template>
