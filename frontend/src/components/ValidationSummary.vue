<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { focusNodeInCanvas } from "../canvas";
import { activeCanvas } from "../store";
import type { ValidationIssue } from "../store";

const canvas = computed(() => activeCanvas());
const issues = computed(() => canvas.value.validationIssues);
const collapsed = ref(false);

watch(
  () => canvas.value.lastValidationResult,
  result => {
    if (result) collapsed.value = false;
  },
);

function locateIssue(issue: ValidationIssue) {
  if (issue.nodeId) focusNodeInCanvas(issue.nodeId, issue.parameter);
}
</script>

<template>
  <aside
    v-if="canvas.validationStatus === 'failed' && issues.length"
    class="validation-summary"
    :class="{ collapsed }"
    aria-live="polite"
    @mousedown.stop
    @click.stop
  >
    <header class="validation-summary-head">
      <span class="validation-summary-icon">
        <iconify-icon icon="mdi:alert-circle-outline"></iconify-icon>
      </span>
      <div>
        <strong>发现 {{ issues.length }} 个问题</strong>
        <small v-if="!collapsed">点击问题可定位并查看相关参数</small>
      </div>
      <button
        type="button"
        :title="collapsed ? '展开问题列表' : '收起问题列表'"
        @click="collapsed = !collapsed"
      >
        <iconify-icon :icon="collapsed ? 'mdi:chevron-up' : 'mdi:chevron-down'"></iconify-icon>
      </button>
    </header>

    <ol v-if="!collapsed" class="validation-issue-list">
      <li v-for="(issue, index) in issues" :key="issue.id">
        <button
          type="button"
          :class="{ locatable: issue.nodeId }"
          :title="issue.detail"
          @click="locateIssue(issue)"
        >
          <span class="validation-issue-index">{{ index + 1 }}</span>
          <span class="validation-issue-copy">
            <strong>{{ issue.title }}</strong>
            <small class="validation-issue-suggestion">{{ issue.suggestion }}</small>
          </span>
          <iconify-icon
            :icon="issue.nodeId ? 'mdi:crosshairs-gps' : 'mdi:information-outline'"
          ></iconify-icon>
        </button>
      </li>
    </ol>
  </aside>
</template>
