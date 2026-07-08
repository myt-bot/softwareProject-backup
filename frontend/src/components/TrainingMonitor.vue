<script setup lang="ts">
// 训练监控页（Training Monitor）
// 作为一个全屏视图挂载在主 shell 之上：训练开始时打开，"返回继续修改"关闭回到搭建页。
import { computed, onBeforeUnmount, ref, watchEffect } from "vue";
import {
  activeSeries,
  computeResults,
  formatInt,
  handleBack,
  handleRerun,
  handleSimulateComplete,
  handleStopTraining,
  MOCK,
  monitor,
  niceLossMax,
  numToStr,
  ticksFor,
  visibleCount,
} from "../monitor";
import TmChart from "./TmChart.vue";

const isRunning = computed(() => monitor.state === "running");
const isCancelled = computed(() => monitor.result?.status === "cancelled");

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
const stepText = computed(() =>
  monitor.totalSteps > 0 ? `${monitor.currentStep}/${monitor.totalSteps}` : "—"
);

// 轮次内进度（顶栏显眼位置）：current_epoch 为已完成轮数，进行中的是下一轮
const displayEpoch = computed(() => Math.min(monitor.currentEpoch + 1, totalEpochs.value || 1));
const epochPercent = computed(() =>
  monitor.totalSteps > 0 ? Math.round((monitor.currentStep / monitor.totalSteps) * 100) : 0
);

// 高亮"正在运行的层"：训练进行时按数据流动方向循环点亮 minimap 中的层
const activeLayerIndex = ref(-1);
let layerTimer: number | null = null;

watchEffect(() => {
  const running = monitor.visible && monitor.state === "running";
  if (running && layerTimer === null) {
    activeLayerIndex.value = 0;
    layerTimer = window.setInterval(() => {
      activeLayerIndex.value = (activeLayerIndex.value + 1) % Math.max(monitor.layers.length, 1);
    }, 550);
  } else if (!running && layerTimer !== null) {
    clearInterval(layerTimer);
    layerTimer = null;
    activeLayerIndex.value = -1;
  }
});

onBeforeUnmount(() => {
  if (layerTimer !== null) clearInterval(layerTimer);
});

// 超参数用中文 + 英文名标注，对新手更友好
const hpRows = computed(() => [
  { label: "训练轮次 epochs", value: monitor.hyperparams.epochs },
  { label: "批大小 batch size", value: monitor.hyperparams.batch_size },
  { label: "学习率 learning rate", value: monitor.hyperparams.rate },
  { label: "优化器 optimizer", value: monitor.hyperparams.optimizer },
  { label: "损失函数 loss", value: monitor.hyperparams.loss_fn },
  { label: "设备 device", value: monitor.hyperparams.device },
]);

// —— 进度总览（新手友好的主视觉区）——
const overallPercent = computed(() =>
  Math.round((isRunning.value ? monitor.progress : 1) * 100)
);

const heroTitle = computed(() => {
  if (monitor.error) return "训练失败";
  if (monitor.stopping) return `正在停止：等待第 ${displayEpoch.value}/${totalEpochs.value} 轮结束`;
  if (isCancelled.value) return "训练已停止";
  if (isRunning.value) return `正在进行第 ${displayEpoch.value}/${totalEpochs.value} 轮训练`;
  return "训练完成 🎉";
});

const heroSubtitle = computed(() => {
  if (monitor.error) return monitor.error;
  if (monitor.stopping) {
    return "停止请求已发送。当前轮会继续跑完并写入 loss / accuracy 曲线，完成后训练会自动停止。";
  }
  if (isCancelled.value) {
    return "训练已按请求停止，曲线保留了停止前已完成轮次的真实指标。";
  }
  if (isRunning.value) {
    return monitor.live && monitor.currentStep === 0 && monitor.currentEpoch === 0
      ? "正在准备数据集并启动训练，稍等片刻..."
      : "模型正在逐批学习训练数据：损失（loss）越来越低、准确率（accuracy）越来越高，说明学习有效。";
  }
  const final = computeResults();
  return final ? `最终训练准确率 ${final.finalAcc}，详细表现见下方结果卡。` : "查看下方结果卡了解本次训练的表现。";
});

// 完成态的四张结果卡
const results = computed(() => (isRunning.value ? null : computeResults()));

const resultCards = computed(() => {
  const val = (key: "finalAcc" | "bestVal" | "finalLoss" | "gap") =>
    results.value ? results.value[key] : null;
  return [
    { label: "最终训练准确率 Final Accuracy", value: val("finalAcc"), hint: "最后一轮在训练集上的准确率", highlight: true },
    { label: "最佳验证准确率 Best Val Accuracy", value: val("bestVal"), hint: "验证集上表现最好的一轮", highlight: false },
    { label: "最终验证损失 Final Loss", value: val("finalLoss"), hint: "最后一轮在验证集上的损失", highlight: false },
    { label: "泛化差距 Generalization Gap", value: val("gap"), hint: "训练准确率 − 验证准确率，过大提示过拟合", highlight: false },
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
    if (monitor.stopping) {
      lines.push(`> 已请求停止，等待当前轮完成后写入本轮指标 ...`);
    } else if (monitor.live && count === 0) {
      lines.push(`> 正在准备数据集并启动训练 ...`);
    } else {
      lines.push(`> 正在训练 Epoch ${Math.min(count + 1, total)}/${total} ...`);
    }
  } else if (isCancelled.value) {
    lines.push(`> 训练已停止，已保留 ${count}/${total} 轮指标。`);
  } else {
    lines.push(`> 训练完成，模型权重已保存。`);
  }

  return lines;
});
</script>

<template>
  <Transition name="tm">
  <div id="training-monitor" v-if="monitor.visible">
    <div class="tm-shell">
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
          <span v-if="monitor.stopping" class="tm-badge stopping"><span class="tm-dot"></span>Stopping</span>
          <span v-else-if="isRunning" class="tm-badge running"><span class="tm-dot"></span>Running</span>
          <span v-else-if="isCancelled" class="tm-badge cancelled"><iconify-icon icon="mdi:stop-circle-outline"></iconify-icon>Stopped</span>
          <span v-else class="tm-badge completed"><iconify-icon icon="mdi:check-circle"></iconify-icon>Completed</span>
          <!-- 轮次内进度条：每个 batch 实时推进 -->
          <div v-if="isRunning && monitor.live" class="tm-epoch-progress" title="当前轮次内的训练进度">
            <span class="tm-ep-label">Epoch {{ displayEpoch }}/{{ totalEpochs }}</span>
            <div class="tm-ep-track"><i :style="{ width: `${epochPercent}%` }"></i></div>
            <span class="tm-ep-value">{{ epochPercent }}%</span>
          </div>
        </div>
        <div class="tm-topbar-right">
          <!-- 状态切换：训练中显示"停止训练"，已结束显示"重新训练" -->
          <button
            v-if="monitor.live && isRunning"
            class="danger-button"
            id="tm-stop"
            :disabled="monitor.stopping"
            @click="handleStopTraining"
          >
            <iconify-icon v-if="monitor.stopping" icon="mdi:loading" class="spin"></iconify-icon>
            <iconify-icon v-else icon="mdi:stop-circle-outline"></iconify-icon>
            {{ monitor.stopping ? "正在停止..." : "停止训练 Stop" }}
          </button>
          <button v-else class="primary-button" id="tm-rerun" @click="handleRerun">
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
                <div
                  :class="[`tm-mini-node ${layer.color}`, { 'running-layer': index === activeLayerIndex }]"
                >{{ layer.type }}</div>
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
        </aside>

        <main class="tm-main">
          <!-- 训练进度总览：状态一目了然，无需滚动 -->
          <section class="tm-card tm-progress-hero" :class="{ done: !isRunning, failed: Boolean(monitor.error) }">
            <div class="tm-hero-head">
              <div class="tm-hero-icon">
                <iconify-icon :icon="monitor.error ? 'mdi:alert-circle-outline' : isRunning ? 'mdi:run-fast' : 'mdi:flag-checkered'"></iconify-icon>
              </div>
              <div class="tm-hero-text">
                <strong>{{ heroTitle }}</strong>
                <span>{{ heroSubtitle }}</span>
              </div>
            </div>
            <div v-if="isRunning" class="tm-hero-bars">
              <div class="tm-hero-bar">
                <span class="tm-hero-bar-label">本轮进度</span>
                <div class="tm-ep-track big"><i :style="{ width: `${epochPercent}%` }"></i></div>
                <span class="tm-hero-bar-value">{{ epochPercent }}%<template v-if="monitor.totalSteps > 0"> · 步 {{ stepText }}</template></span>
              </div>
              <div class="tm-hero-bar">
                <span class="tm-hero-bar-label">整体进度</span>
                <div class="tm-ep-track big overall"><i :style="{ width: `${overallPercent}%` }"></i></div>
                <span class="tm-hero-bar-value">{{ overallPercent }}% · 第 {{ displayEpoch }}/{{ totalEpochs }} 轮</span>
              </div>
            </div>
          </section>

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
  </Transition>
</template>
