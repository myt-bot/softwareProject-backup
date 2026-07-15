<script setup lang="ts">
import { computed } from "vue";
import { activeCanvas, getWorkflowProgress } from "../store";

// 四步条跟随当前画布的真实进度：已完成打勾、当前步高亮、未到步骤置灰
const progress = computed(() => getWorkflowProgress(activeCanvas()));

const steps = [
  { n: 1, title: "添加组件", desc: "单击快速添加，或拖到指定位置" },
  { n: 2, title: "连接与删除", desc: "右键节点可连线或删除；右键连线可删除" },
  { n: 3, title: "检查结构", desc: "点击底部“检查结构”按钮" },
  { n: 4, title: "开始训练", desc: "检查通过后一键训练" },
];

function stateOf(n: number): "done" | "current" | "todo" {
  if (progress.value.done[n - 1]) return "done";
  return progress.value.step === n ? "current" : "todo";
}
</script>

<template>
  <!-- 新手引导条：跟随实际进度的四步状态机（常驻） -->
  <div class="guide-strip" id="guide-strip">
    <div class="guide-steps">
      <template v-for="(s, i) in steps" :key="s.n">
        <div class="guide-step" :class="`is-${stateOf(s.n)}`">
          <span class="guide-step-num">
            <iconify-icon v-if="stateOf(s.n) === 'done'" icon="mdi:check"></iconify-icon>
            <template v-else>{{ s.n }}</template>
          </span>
          <div>
            <strong>{{ s.title }}</strong>
            <span v-if="stateOf(s.n) === 'current'">{{ s.desc }}</span>
          </div>
        </div>
        <iconify-icon v-if="i < steps.length - 1" class="guide-arrow" icon="mdi:chevron-right"></iconify-icon>
      </template>
    </div>
  </div>
</template>
