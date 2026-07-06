<script setup lang="ts">
import { computed } from "vue";
import {
  handleExportCode,
  handleSaveProject,
  handleStartTraining,
  handleValidateModel,
  openCurrentTrainingMonitor,
  trainStarting,
  validating,
} from "../actions";
import { clamp, getTrainingStatusLabel, store } from "../store";

const job = computed(() => store.trainingJob);

const jobPanelClass = computed(() => {
  if (!job.value) return "is-empty";
  const status = job.value.status || "pending";
  return status === "completed"
    ? "is-completed"
    : status === "failed" || status === "cancelled"
      ? "is-failed"
      : "is-running";
});

const jobPercentage = computed(() => {
  if (!job.value) return 0;
  const progress = typeof job.value.progress === "number"
    ? job.value.progress
    : (job.value.total_epochs ? (job.value.current_epoch || 0) / job.value.total_epochs : 0);
  return Math.round(clamp(progress, 0, 1) * 100);
});

const jobMeta = computed(() => {
  if (!job.value) return "通过结构检查后即可开始训练";
  return `Epoch ${job.value.current_epoch ?? 0}/${job.value.total_epochs ?? "-"} · ${jobPercentage.value}%`;
});

const trainDisabled = computed(() => trainStarting.value || store.validationStatus !== "passing");
</script>

<template>
  <footer class="actionbar">
    <div class="actionbar-left">
      <div class="training-job-panel" :class="jobPanelClass" id="training-job-panel">
        <div class="training-job-icon"><iconify-icon icon="mdi:timer-outline"></iconify-icon></div>
        <div class="training-job-body">
          <div class="training-job-head">
            <strong id="training-job-id">{{ job ? (job.job_id || "未知任务") : "暂无训练任务" }}</strong>
            <span id="training-job-status">{{ job ? getTrainingStatusLabel(job.status || "pending") : "待开始" }}</span>
          </div>
          <div class="training-job-track"><i id="training-job-progress" :style="{ width: `${jobPercentage}%` }"></i></div>
          <p id="training-job-meta">{{ jobMeta }}</p>
        </div>
        <button
          class="icon-button"
          id="btn-view-training"
          :disabled="!job"
          title="查看训练详情"
          @click="openCurrentTrainingMonitor"
        ><iconify-icon icon="mdi:chart-line"></iconify-icon></button>
      </div>
    </div>
    <div class="footer-actions">
      <div
        class="validation-summary"
        :class="[store.validationSummary.kind, { hidden: !store.validationSummary.visible }]"
        id="validation-summary"
      >
        <iconify-icon id="summary-icon" :icon="store.validationSummary.icon"></iconify-icon>
        <span id="summary-text">{{ store.validationSummary.text }}</span>
      </div>
      <div class="footer-divider"></div>
      <button
        class="secondary-button"
        id="btn-validate"
        title="自动检查每一层的尺寸是否匹配"
        :disabled="validating"
        @click="handleValidateModel"
      >
        <iconify-icon v-if="validating" icon="mdi:loading" class="spin"></iconify-icon>
        <iconify-icon v-else icon="mdi:check-circle-outline"></iconify-icon>
        {{ validating ? "正在校验..." : "检查结构" }}
      </button>
      <button class="secondary-button" id="btn-save" title="把当前模型保存到我的项目" @click="handleSaveProject">
        <iconify-icon icon="mdi:content-save-outline"></iconify-icon>
        保存模型
      </button>
      <button class="secondary-button" id="btn-export" title="生成可直接运行的 PyTorch 代码" @click="handleExportCode">
        <iconify-icon icon="mdi:code-json"></iconify-icon>
        导出代码
      </button>
      <button
        class="success-button"
        id="btn-train"
        :disabled="trainDisabled"
        title="先通过“检查结构”，此按钮才会亮起"
        @click="handleStartTraining"
      >
        <iconify-icon v-if="trainStarting" icon="mdi:loading" class="spin"></iconify-icon>
        <iconify-icon v-else icon="mdi:play"></iconify-icon>
        {{ trainStarting ? "启动训练..." : "开始训练" }}
      </button>
    </div>
  </footer>
</template>
