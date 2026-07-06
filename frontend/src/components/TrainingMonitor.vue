<script setup lang="ts">
// 训练监控页（Training Monitor）
// 作为一个全屏视图挂载在主 shell 之上：训练开始时打开，"返回继续修改"关闭回到搭建页。
import { computed } from "vue";
import {
  activeSeries,
  computeResults,
  formatInt,
  handleBack,
  handleRerun,
  handleSimulateComplete,
  MOCK,
  monitor,
  niceLossMax,
  numToStr,
  ticksFor,
  toggleSeries,
  visibleCount,
} from "../monitor";
import TmChart from "./TmChart.vue";

const isRunning = computed(() => monitor.state === "running");

const series = computed(() => activeSeries());
const visible = computed(() => visibleCount());

const chartTotal = computed(() =>
  monitor.live ? (series.value.totalEpochs || monitor.hyperparams.epochs) : MOCK.totalEpochs
);

const lossMax = computed(() => niceLossMax([...series.value.loss, ...series.value.valLoss]));
const lossTicks = computed(() => ticksFor(lossMax.value));

// 侧边栏训练状态
const totalEpochs = computed(() =>
  monitor.live ? (series.value.totalEpochs || monitor.hyperparams.epochs) : monitor.hyperparams.epochs
);
// 后端未提供 step 粒度，live 模式下 Step 显示占位。
const stepText = computed(() =>
  monitor.live ? "—" : `${monitor.currentStep}/${monitor.totalSteps}`
);
const etaText = computed(() =>
  isRunning.value ? (monitor.live ? "—" : "00:45") : "00:00"
);
const progressPercent = computed(() =>
  Math.round((isRunning.value ? monitor.progress : 1) * 100)
);

const hpRows = computed(() => [
  { label: "epochs", value: monitor.hyperparams.epochs },
  { label: "batch size", value: monitor.hyperparams.batch_size },
  { label: "learning rate", value: monitor.hyperparams.rate },
  { label: "optimizer", value: monitor.hyperparams.optimizer },
  { label: "loss", value: monitor.hyperparams.loss_fn },
  { label: "device", value: monitor.hyperparams.device },
]);

// 完成态的四张结果卡
const results = computed(() => (isRunning.value ? null : computeResults()));

const resultCards = computed(() => {
  const val = (key: "finalAcc" | "bestVal" | "finalLoss" | "gap") =>
    results.value ? results.value[key] : null;
  return [
    { label: "Final Accuracy", value: val("finalAcc"), hint: "最终训练准确率", highlight: true },
    { label: "Best Val Accuracy", value: val("bestVal"), hint: "最佳验证准确率", highlight: false },
    { label: "Final Loss", value: val("finalLoss"), hint: "最终验证损失", highlight: false },
    { label: "Generalization Gap", value: val("gap"), hint: "train acc − val acc", highlight: false },
  ];
});

// 训练日志
const logLines = computed(() => {
  const s = series.value;
  const count = visible.value;
  const total = monitor.live ? (s.totalEpochs || monitor.hyperparams.epochs) : MOCK.totalEpochs;
  const lines: string[] = [];

  for (let i = 0; i < count; i += 1) {
    lines.push(
      `Epoch ${i + 1}/${total} - loss=${numToStr(s.loss[i])} - acc=${numToStr(s.trainAcc[i])} - val_acc=${numToStr(s.valAcc[i])}`
    );
  }

  if (isRunning.value) {
    if (monitor.live && count === 0) {
      lines.push(`> 正在准备数据集并启动训练 ...`);
    } else {
      lines.push(`> 正在训练 Epoch ${Math.min(count + 1, total)}/${total} ...`);
    }
  } else {
    lines.push(`> 训练完成，模型权重已保存。`);
  }

  return lines;
});
</script>

<template>
  <div id="training-monitor" :class="{ hidden: !monitor.visible }">
    <div v-if="monitor.visible" class="tm-shell">
      <header class="tm-topbar">
        <div class="tm-topbar-left">
          <button class="icon-button" id="tm-back-icon" title="返回" @click="handleBack">
            <iconify-icon icon="mdi:arrow-left"></iconify-icon>
          </button>
          <nav class="tm-breadcrumb">
            <span>项目</span>
            <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            <span>MNIST-CNN</span>
            <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            <strong>Training</strong>
          </nav>
        </div>
        <div class="tm-topbar-center">
          <span v-if="isRunning" class="tm-badge running"><span class="tm-dot"></span>Running</span>
          <span v-else class="tm-badge completed"><iconify-icon icon="mdi:check-circle"></iconify-icon>Completed</span>
        </div>
        <div class="tm-topbar-right">
          <button class="secondary-button" id="tm-back" @click="handleBack">
            <iconify-icon icon="mdi:pencil-outline"></iconify-icon>
            返回继续修改 Back to Builder
          </button>
          <button class="primary-button" id="tm-rerun" @click="handleRerun">
            <iconify-icon icon="mdi:restart"></iconify-icon>
            重新训练 Re-run
          </button>
        </div>
      </header>

      <div class="tm-body">
        <aside class="tm-sidebar">
          <section class="tm-card">
            <h3>模型结构 Model Graph</h3>
            <div class="tm-minimap">
              <template v-for="(layer, index) in monitor.layers" :key="index">
                <div :class="`tm-mini-node ${layer.color}`">{{ layer.type }}</div>
                <iconify-icon
                  v-if="index < monitor.layers.length - 1"
                  class="tm-mini-arrow"
                  icon="mdi:chevron-down"
                ></iconify-icon>
              </template>
            </div>
            <div class="tm-summary-grid">
              <div><span>#params</span><strong>{{ formatInt(monitor.paramCount) }}</strong></div>
              <div><span>Input shape</span><strong>28×28×1</strong></div>
              <div><span>num_classes</span><strong>10</strong></div>
            </div>
          </section>

          <section class="tm-card">
            <h3>训练超参数 Hyperparameters</h3>
            <div class="tm-hp-list">
              <div v-for="row in hpRows" :key="row.label" class="tm-hp-row"><span>{{ row.label }}</span><code>{{ row.value }}</code></div>
            </div>
          </section>

          <section class="tm-card">
            <h3>训练状态 Training Status</h3>
            <div class="tm-status-rows">
              <div class="tm-status-item">
                <span>Epoch</span>
                <strong>{{ monitor.currentEpoch }}/{{ totalEpochs }}</strong>
              </div>
              <div class="tm-status-item">
                <span>Step</span>
                <strong>{{ stepText }}</strong>
              </div>
              <div class="tm-status-item">
                <span>ETA</span>
                <strong>{{ etaText }}</strong>
              </div>
            </div>
            <div class="tm-progress">
              <div class="tm-progress-bar" :class="{ done: !isRunning }" :style="{ width: `${progressPercent}%` }"></div>
            </div>
            <p class="tm-progress-label">{{ isRunning ? `训练中 ${Math.round(monitor.progress * 100)}%` : "训练完成 100%" }}</p>
          </section>
        </aside>

        <main class="tm-main">
          <div class="tm-charts">
            <TmChart
              chart-key="loss"
              title="Loss 曲线"
              subtitle="损失越低越好"
              :train="series.loss"
              :val="series.valLoss"
              :y-min="0"
              :y-max="lossMax"
              :y-ticks="lossTicks"
              :total="chartTotal"
              :visible="visible"
              :show-train-only="monitor.showTrainOnly"
              @toggle="toggleSeries"
            />
            <TmChart
              chart-key="acc"
              title="Accuracy 曲线"
              subtitle="准确率越高越好"
              :train="series.trainAcc"
              :val="series.valAcc"
              :y-min="0"
              :y-max="1"
              :y-ticks="[0, 0.25, 0.5, 0.75, 1]"
              :total="chartTotal"
              :visible="visible"
              :show-train-only="monitor.showTrainOnly"
              @toggle="toggleSeries"
            />
          </div>

          <div class="tm-result-cards">
            <div
              v-for="card in resultCards"
              :key="card.label"
              class="tm-result-card"
              :class="{ highlight: card.highlight && card.value }"
            >
              <span class="tm-result-label">{{ card.label }}</span>
              <strong class="tm-result-value">{{ card.value ?? "--" }}</strong>
              <span class="tm-result-hint">{{ card.value == null ? "实时更新中..." : card.hint }}</span>
            </div>
          </div>

          <section v-if="!isRunning" class="tm-teaching-tip">
            <iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon>
            <div>
              <strong>教学提示 Teaching Tip</strong>
              <p>如果 train acc 持续上升但 val acc 停滞，可能出现 overfitting（过拟合）。可尝试增大 Dropout、加数据增强或提前停止。</p>
            </div>
          </section>

          <section class="tm-logs">
            <div class="tm-logs-head">
              <h3><iconify-icon icon="mdi:console-line"></iconify-icon> 训练日志 Training Logs</h3>
              <button v-if="!monitor.live" class="tm-mini-btn" id="tm-complete" @click="handleSimulateComplete">
                <iconify-icon icon="mdi:fast-forward"></iconify-icon>
                模拟完成 Complete
              </button>
            </div>
            <div class="tm-logs-body" id="tm-logs-body">
              <div v-if="monitor.error" class="tm-log-line" style="color: var(--rose);">✗ 训练失败：{{ monitor.error }}</div>
              <template v-else>
                <div
                  v-for="(line, index) in logLines"
                  :key="index"
                  class="tm-log-line"
                  :class="{ muted: line.startsWith('>') }"
                >{{ line }}</div>
              </template>
            </div>
          </section>
        </main>
      </div>

      <div class="tm-footnote">
        {{ monitor.live
          ? "已连接训练服务（training backend），曲线与指标来自后端真实训练结果。"
          : "原型阶段使用预设指标曲线模拟训练过程，后续可对接真实训练服务（training backend）。" }}
      </div>
    </div>
  </div>
</template>
