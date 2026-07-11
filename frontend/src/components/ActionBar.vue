<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  handleExportCode,
  handleSaveProject,
  handleStartTraining,
  handleValidateModel,
  openCurrentTrainingMonitor,
} from "../actions";
import { isEditingContainer } from "../canvas";
import { activeCanvas, clamp, getTrainingStatusLabel, isTrainingJobActive, showToast, ui } from "../store";
import DatasetSelector from "./DatasetSelector.vue";
import DeviceSelector from "./DeviceSelector.vue";
import InfoTip from "./InfoTip.vue";

// 「更多」下拉菜单（收纳保存/我的项目/导出，给底栏腾出空间）
const moreMenuOpen = ref(false);
const moreRef = ref<HTMLElement | null>(null);

function handleDocumentClick(event: MouseEvent) {
  if (!moreRef.value?.contains(event.target as Node)) {
    moreMenuOpen.value = false;
  }
}
onMounted(() => document.addEventListener("click", handleDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", handleDocumentClick));

function runMore(action: () => void) {
  moreMenuOpen.value = false;
  action();
}

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
const hasActiveJob = computed(() => isTrainingJobActive(job.value));

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

// 编辑容器子画板时：只允许"检查结构"验证内部，训练/导出面向整个模型，需退出后再用
const editingContainer = computed(() => isEditingContainer());

const trainDisabled = computed(
  () => canvas.value.trainStarting || hasActiveJob.value || editingContainer.value || canvas.value.validationStatus !== "passing"
);

const trainButtonTitle = computed(() => {
  if (editingContainer.value) return "正在编辑容器内部，返回主画布后才能训练整个模型。";
  if (hasActiveJob.value) return "当前画布已有训练任务进行中，请先查看训练详情。";
  if (canvas.value.validationStatus !== "passing") return "先通过“检查结构”，此按钮才会亮起";
  return "开始训练当前模型";
});

const trainButtonText = computed(() => {
  if (canvas.value.trainStarting) return "启动训练...";
  if (hasActiveJob.value) return "训练进行中";
  return "开始训练";
});

// 有模型但还没校验通过 → 提醒"先检查结构"
const needsCheck = computed(
  () => canvas.value.nodes.length > 0 && canvas.value.validationStatus !== "passing"
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
      <!-- 模型操作组：对当前模型做的事 -->
      <div class="action-group model-group">
        <button
          class="secondary-button"
          id="btn-validate"
          :class="{ 'attention-pulse': needsCheck }"
          :title="needsCheck ? '训练前先点这里检查结构是否正确' : '自动检查每一层的尺寸是否匹配'"
          :disabled="canvas.validating"
          @click="handleValidateModel"
        >
          <iconify-icon v-if="canvas.validating" icon="mdi:loading" class="spin"></iconify-icon>
          <iconify-icon v-else-if="needsCheck" icon="mdi:numeric-1-circle"></iconify-icon>
          <iconify-icon v-else icon="mdi:check-circle-outline"></iconify-icon>
          {{ canvas.validating ? "正在校验..." : (needsCheck ? "先检查结构" : "检查结构") }}
        </button>
        <!-- 更多：保存 / 我的项目 / 导出（收进下拉，底栏更清爽） -->
        <div class="more-menu-wrap" ref="moreRef">
          <button
            class="secondary-button"
            id="btn-more"
            :class="{ active: moreMenuOpen }"
            title="保存 / 加载 / 导出"
            @click.stop="moreMenuOpen = !moreMenuOpen"
          >
            <iconify-icon icon="mdi:dots-horizontal"></iconify-icon>
            更多
            <iconify-icon icon="mdi:chevron-up" class="more-caret"></iconify-icon>
          </button>
          <div class="more-menu" :class="{ open: moreMenuOpen }">
            <button id="btn-save" @click="runMore(handleSaveProject)">
              <iconify-icon icon="mdi:content-save-outline"></iconify-icon> 保存模型
            </button>
            <button id="btn-my-projects" @click="runMore(() => (ui.projectsModalOpen = true))">
              <iconify-icon icon="mdi:folder-open-outline"></iconify-icon> 我的项目
            </button>
            <button id="btn-export" :disabled="editingContainer" :title="editingContainer ? '返回主画布后再导出整个模型' : ''" @click="runMore(handleExportCode)">
              <iconify-icon icon="mdi:code-json"></iconify-icon> 导出代码
            </button>
          </div>
        </div>
      </div>

      <div class="action-divider"></div>

      <!-- 训练区：一处集齐训练设置并启动 -->
      <div class="action-group train-group">
        <DatasetSelector />
        <DeviceSelector />
        <label class="epochs-field">
          <span>轮次 <InfoTip text="Epoch（轮次）：把整个训练集完整过一遍算一轮。轮次越多学得越充分，但太多会过拟合、也更慢。新手可先设 1~5 轮。" /></span>
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
          class="secondary-button"
          id="btn-hyperparams"
          title="训练超参数：批大小 / 学习率 / 优化器 / 损失函数"
          @click="ui.trainSettingsOpen = true"
        >
          <iconify-icon icon="mdi:tune-variant"></iconify-icon>
          超参数
        </button>
        <button
          class="success-button"
          id="btn-train"
          :disabled="trainDisabled"
          :title="trainButtonTitle"
          @click="handleStartTraining"
        >
          <iconify-icon v-if="canvas.trainStarting" icon="mdi:loading" class="spin"></iconify-icon>
          <iconify-icon v-else-if="hasActiveJob" icon="mdi:timer-sand"></iconify-icon>
          <iconify-icon v-else icon="mdi:play"></iconify-icon>
          {{ trainButtonText }}
        </button>
      </div>
    </div>
  </footer>
</template>
