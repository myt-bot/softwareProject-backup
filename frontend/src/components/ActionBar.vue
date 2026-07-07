<script setup lang="ts">
import { computed } from "vue";
import {
  handleExportCode,
  handleSaveProject,
  handleStartTraining,
  handleValidateModel,
  openCurrentTrainingMonitor,
} from "../actions";
import { activeCanvas, clamp, getTrainingStatusLabel, showToast, ui } from "../store";

// 底部操作栏跟随当前激活画布：各画布的校验/训练状态相互独立、并行进行
const canvas = computed(() => activeCanvas());

const MAX_EPOCHS = 100;

// 训练轮次输入（按画布独立保存）
function handleEpochsChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const value = Number(input.value);

  if (!Number.isInteger(value) || value < 1 || value > MAX_EPOCHS) {
    showToast("warning", `训练轮次须为 1-${MAX_EPOCHS} 的整数。`);
    canvas.value.epochs = clamp(Math.round(value) || 1, 1, MAX_EPOCHS);
  } else {
    canvas.value.epochs = value;
  }
  // 输入被纠正时同步回输入框（响应式值可能未变化）
  input.value = String(canvas.value.epochs);
}

const job = computed(() => canvas.value.trainingJob);

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

const trainDisabled = computed(
  () => canvas.value.trainStarting || canvas.value.validationStatus !== "passing"
);
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
      <button
        class="secondary-button"
        id="btn-validate"
        title="自动检查每一层的尺寸是否匹配"
        :disabled="canvas.validating"
        @click="handleValidateModel"
      >
        <iconify-icon v-if="canvas.validating" icon="mdi:loading" class="spin"></iconify-icon>
        <iconify-icon v-else icon="mdi:check-circle-outline"></iconify-icon>
        {{ canvas.validating ? "正在校验..." : "检查结构" }}
      </button>
      <button class="secondary-button" id="btn-save" title="把当前模型保存到我的项目" @click="handleSaveProject">
        <iconify-icon icon="mdi:content-save-outline"></iconify-icon>
        保存模型
      </button>
      <button class="secondary-button" id="btn-my-projects" title="加载已保存的模型" @click="ui.projectsModalOpen = true">
        <iconify-icon icon="mdi:folder-open-outline"></iconify-icon>
        我的项目
      </button>
      <button class="secondary-button" id="btn-export" title="生成可直接运行的 PyTorch 代码" @click="handleExportCode">
        <iconify-icon icon="mdi:code-json"></iconify-icon>
        导出代码
      </button>
      <label class="epochs-field" title="完整遍历训练集的次数（1-100）">
        <span>训练轮次</span>
        <input
          id="epochs-input"
          type="number"
          min="1"
          :max="MAX_EPOCHS"
          :value="canvas.epochs"
          @change="handleEpochsChange"
        >
      </label>
      <button
        class="success-button"
        id="btn-train"
        :disabled="trainDisabled"
        title="先通过“检查结构”，此按钮才会亮起"
        @click="handleStartTraining"
      >
        <iconify-icon v-if="canvas.trainStarting" icon="mdi:loading" class="spin"></iconify-icon>
        <iconify-icon v-else icon="mdi:play"></iconify-icon>
        {{ canvas.trainStarting ? "启动训练..." : "开始训练" }}
      </button>
    </div>
  </footer>
</template>
