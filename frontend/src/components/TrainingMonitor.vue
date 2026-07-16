<script setup lang="ts">
// 训练监控页（Training Monitor）
// 作为一个全屏视图挂载在主 shell 之上：训练开始时打开，"返回继续修改"关闭回到搭建页。
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
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
import { isTrainingJobActive, showToast, store } from "../store";
import { switchTrainingMonitorToCanvas } from "../actions";
import TmChart from "./TmChart.vue";

const isRunning = computed(() => monitor.state === "running");
const isCancelling = computed(() => monitor.state === "cancelling");
const isActive = computed(() => isRunning.value || isCancelling.value);
const isCompleted = computed(() => monitor.state === "completed");
const isFailed = computed(() => monitor.state === "failed");
const isCancelled = computed(() => monitor.state === "cancelled");

// 训练产物保存位置：从回传的 artifacts.model_path 取出所在文件夹，方便用户直接找到
const savedPath = computed(() => {
  const artifacts = monitor.result?.artifacts as { model_path?: string } | undefined;
  const modelPath = artifacts?.model_path;
  if (!modelPath) return null;
  const cut = Math.max(modelPath.lastIndexOf("\\"), modelPath.lastIndexOf("/"));
  return cut > 0 ? modelPath.slice(0, cut) : modelPath;
});

async function copySavedPath() {
  if (!savedPath.value) return;
  try {
    await navigator.clipboard.writeText(savedPath.value);
    showToast("success", "保存路径已复制到剪贴板。");
  } catch {
    showToast("info", savedPath.value);
  }
}

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

// 高亮"正在运行的层"：由本机训练运行时的真实 forward 事件驱动。
const activeLayerIndex = computed(() => monitor.activeLayerIndex);

// 模型结构分支图：按拓扑行列坐标定位节点，边用直角折线（横平竖直）连接，展现分支。
const TM_NODE_W = 64;
const TM_NODE_H = 30;
const TM_H_GAP = 12;
const TM_V_GAP = 24;
const graphLayout = computed(() => {
  const raw = monitor.layers;
  const hasLayout = raw.some(l => l.row != null); // 真实训练带行列；demo 默认无 → 退回单列
  const positioned = raw.map((l, i) => ({
    id: l.id ?? `d${i}`,
    type: l.type,
    color: l.color,
    row: hasLayout ? l.row ?? 0 : i,
    col: hasLayout ? l.col ?? 0 : 0,
    index: i,
  }));
  const rowCount = new Map<number, number>();
  positioned.forEach(l => rowCount.set(l.row, Math.max(rowCount.get(l.row) ?? 0, l.col + 1)));
  const maxCols = Math.max(1, ...positioned.map(l => l.col + 1));
  const maxRow = Math.max(0, ...positioned.map(l => l.row));
  const totalW = maxCols * TM_NODE_W + (maxCols - 1) * TM_H_GAP;
  const totalH = (maxRow + 1) * TM_NODE_H + maxRow * TM_V_GAP;
  const pos = new Map<string, { x: number; y: number }>();
  const nodes = positioned.map(l => {
    const count = rowCount.get(l.row) ?? 1;
    const rowW = count * TM_NODE_W + (count - 1) * TM_H_GAP;
    const x = (totalW - rowW) / 2 + l.col * (TM_NODE_W + TM_H_GAP);
    const y = l.row * (TM_NODE_H + TM_V_GAP);
    pos.set(l.id, { x, y });
    return { ...l, x, y };
  });
  const rawEdges = monitor.edges?.length
    ? monitor.edges
    : nodes.slice(0, -1).map((n, i) => ({ source: n.id, target: nodes[i + 1].id }));
  const edges = rawEdges
    .map(e => {
      const s = pos.get(e.source);
      const t = pos.get(e.target);
      if (!s || !t) return null;
      const x1 = s.x + TM_NODE_W / 2;
      const y1 = s.y + TM_NODE_H;
      const x2 = t.x + TM_NODE_W / 2;
      const y2 = t.y;
      const midY = y1 + (y2 - y1) / 2;
      // 直角折线：竖 → 横 → 竖
      return { d: `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}` };
    })
    .filter((e): e is { d: string } => e !== null);
  return { nodes, edges, totalW, totalH };
});

// 分支结构：同一层（拓扑行）上的并列分支是并行关系，应同时点亮，而不是按索引从左到右逐个闪。
// 由当前执行到的层索引，反查其所在行，点亮整行。
const activeRow = computed(() => {
  const idx = activeLayerIndex.value;
  if (idx == null || idx < 0) return null;
  const node = graphLayout.value.nodes.find(n => n.index === idx);
  return node ? node.row : null;
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

const modelName = computed(() => monitor.modelSummary.modelName || "模型");
const inputShapeText = computed(() => formatShape(monitor.modelSummary.inputShape));
const numClassesText = computed(() => monitor.modelSummary.numClasses ?? "--");

// —— 顶栏任务切换器：在并行训练的各画布结果间跳转 ——
// 列出所有带训练任务的画布；选中即切到该任务（同步活动画布 + 重装 monitor）。
const taskEntries = computed(() =>
  store.canvases
    .filter(canvas => canvas.trainingJob?.job_id)
    .map(canvas => ({
      canvasId: canvas.id,
      name: canvas.name,
      jobId: canvas.trainingJob!.job_id!,
      active: isTrainingJobActive(canvas.trainingJob),
      isCurrent: canvas.trainingJob!.job_id === monitor.jobId,
    }))
);
const showTaskSwitcher = computed(() => taskEntries.value.length > 1);

const switcherOpen = ref(false);
const switcherRef = ref<HTMLElement | null>(null);

function toggleSwitcher(event: MouseEvent) {
  event.stopPropagation();
  switcherOpen.value = !switcherOpen.value;
}

function selectTask(event: MouseEvent, canvasId: number) {
  event.stopPropagation();
  switcherOpen.value = false;
  switchTrainingMonitorToCanvas(canvasId);
}

function handleSwitcherOutside(event: MouseEvent) {
  if (!switcherRef.value?.contains(event.target as Node)) {
    switcherOpen.value = false;
  }
}

onMounted(() => document.addEventListener("click", handleSwitcherOutside));
onBeforeUnmount(() => document.removeEventListener("click", handleSwitcherOutside));

// —— 进度总览（新手友好的主视觉区）——
const overallPercent = computed(() =>
  Math.round((isActive.value ? monitor.progress : 1) * 100)
);

const datasetProgress = computed(() => monitor.datasetProgress);
const datasetStatus = computed(() => datasetProgress.value?.status || "");
const datasetPercent = computed(() => {
  const raw = datasetProgress.value?.percent;
  if (typeof raw === "number" && Number.isFinite(raw)) return clampPercent(raw);
  if (datasetStatus.value === "ready" || monitor.totalSteps > 0) return 100;
  return 0;
});
const datasetPercentText = computed(() => `${datasetPercent.value.toFixed(datasetPercent.value % 1 === 0 ? 0 : 1)}%`);
const datasetBytesText = computed(() => {
  const downloaded = datasetProgress.value?.downloaded_bytes || 0;
  const total = datasetProgress.value?.total_bytes || 0;
  if (!downloaded || !total) return "";
  return `${formatBytes(downloaded)} / ${formatBytes(total)}`;
});
const datasetStageActive = computed(() =>
  isActive.value && ["pending", "checking", "downloading"].includes(datasetStatus.value)
);
const datasetLabel = computed(() => datasetProgress.value?.dataset_name || "数据集");
const datasetFileLabel = computed(() => datasetProgress.value?.file_name || datasetLabel.value);

const heroTitle = computed(() => {
  if (isFailed.value) return "训练失败";
  if (isCancelling.value) return "正在终止训练";
  if (isCancelled.value) return "训练已终止";
  if (datasetStageActive.value) {
    if (datasetStatus.value === "downloading") return `正在下载 ${datasetFileLabel.value} · ${datasetPercentText.value}`;
    return `正在准备 ${datasetLabel.value} 数据集`;
  }
  if (isRunning.value) return `正在进行第 ${displayEpoch.value}/${totalEpochs.value} 轮训练`;
  if (isCompleted.value) return "训练完成 🎉";
  return "训练状态未知";
});

const heroSubtitle = computed(() => {
  if (isFailed.value) return monitor.error || "训练失败，请点「检查结构」排查模型与数据集是否匹配。";
  if (isCancelling.value) {
    return "停止请求已发送。数据集准备 / 下载阶段会尽快中断；训练批次进行中时会在可中断点安全停止。";
  }
  if (isCancelled.value) {
    return "训练已按请求停止，曲线保留了停止前已完成轮次的真实指标。";
  }
  if (isActive.value) {
    return monitor.live && monitor.currentStep === 0 && monitor.currentEpoch === 0
      ? "正在准备数据集并启动训练，稍等片刻..."
      : "模型正在逐批学习训练数据：损失（loss）越来越低、准确率（accuracy）越来越高，说明学习有效。";
  }
  const final = computeResults();
  return final ? `最终训练准确率 ${final.finalAcc}，详细表现见下方结果卡。` : "查看下方结果卡了解本次训练的表现。";
});

// 完成态的四张结果卡
const results = computed(() => (isActive.value ? null : computeResults()));

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

  if (isActive.value) {
    if (monitor.stopping) {
      lines.push(`> 已请求停止，等待当前轮完成后写入本轮指标 ...`);
    } else if (monitor.live && count === 0) {
      lines.push(`> 正在准备数据集并启动训练 ...`);
    } else {
      lines.push(`> 正在训练 Epoch ${Math.min(count + 1, total)}/${total} ...`);
    }
  } else if (isCancelled.value) {
    lines.push(`> 训练已终止，已保留 ${count}/${total} 轮指标。`);
  } else if (isFailed.value) {
    lines.push(`> 训练失败，已保留 ${count}/${total} 轮指标。`);
  } else if (isCompleted.value) {
    lines.push(`> 训练完成，模型权重已保存。`);
  }

  return lines;
});

function formatShape(shape: number[] | null | undefined) {
  if (!Array.isArray(shape) || shape.length === 0) return "--";
  if (shape.length === 3) {
    return `${shape[1]}×${shape[2]}×${shape[0]}`;
  }
  return shape.join("×");
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, value));
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}
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
            <span>{{ modelName }}</span>
            <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            <strong>Training</strong>
          </nav>
          <!-- 任务切换器：并行训练多个画布时，在结果间直接跳转，无需返回 -->
          <div
            v-if="showTaskSwitcher"
            ref="switcherRef"
            class="tm-task-switcher"
            :class="{ open: switcherOpen }"
          >
            <button class="tm-switcher-trigger" title="切换训练任务" @click="toggleSwitcher">
              <iconify-icon icon="mdi:swap-horizontal"></iconify-icon>
              <span class="tm-switcher-current">{{ modelName }}</span>
              <iconify-icon icon="mdi:chevron-down" class="tm-switcher-arrow"></iconify-icon>
            </button>
            <div class="tm-switcher-menu">
              <button
                v-for="entry in taskEntries"
                :key="entry.canvasId"
                class="tm-switcher-option"
                :class="{ active: entry.isCurrent }"
                @click="selectTask($event, entry.canvasId)"
              >
                <span class="tm-switcher-dot" :class="{ live: entry.active }"></span>
                <span class="tm-switcher-name">{{ entry.name }}</span>
                <iconify-icon
                  v-if="entry.isCurrent"
                  icon="mdi:check"
                  class="tm-switcher-check"
                ></iconify-icon>
              </button>
            </div>
          </div>
        </div>
        <div class="tm-topbar-center">
          <span v-if="isCancelling" class="tm-badge stopping"><span class="tm-dot"></span>Stopping</span>
          <span v-else-if="isRunning" class="tm-badge running"><span class="tm-dot"></span>Running</span>
          <span v-else-if="isFailed" class="tm-badge failed"><iconify-icon icon="mdi:alert-circle-outline"></iconify-icon>Failed</span>
          <span v-else-if="isCancelled" class="tm-badge cancelled"><iconify-icon icon="mdi:stop-circle-outline"></iconify-icon>Stopped</span>
          <span v-else-if="isCompleted" class="tm-badge completed"><iconify-icon icon="mdi:check-circle"></iconify-icon>Completed</span>
          <!-- 轮次内进度条：每个 batch 实时推进 -->
          <div v-if="isActive && monitor.live" class="tm-epoch-progress" title="当前轮次内的训练进度">
            <span class="tm-ep-label">Epoch {{ displayEpoch }}/{{ totalEpochs }}</span>
            <div class="tm-ep-track"><i :style="{ width: `${epochPercent}%` }"></i></div>
            <span class="tm-ep-value">{{ epochPercent }}%</span>
          </div>
        </div>
        <div class="tm-topbar-right">
          <!-- 状态切换：训练中显示"终止训练"，已结束显示"重新训练" -->
          <button
            v-if="monitor.live && isActive"
            class="danger-button"
            id="tm-stop"
            :disabled="monitor.stopping"
            @click="handleStopTraining"
          >
            <iconify-icon v-if="monitor.stopping" icon="mdi:loading" class="spin"></iconify-icon>
            <iconify-icon v-else icon="mdi:stop-circle-outline"></iconify-icon>
            {{ monitor.stopping ? "正在终止..." : "终止训练 Stop" }}
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
            <div class="tm-graph-scroll">
              <div class="tm-graph" :style="{ width: graphLayout.totalW + 'px', height: graphLayout.totalH + 'px' }">
                <svg class="tm-graph-edges" :width="graphLayout.totalW" :height="graphLayout.totalH">
                  <defs>
                    <marker id="tm-arrow" markerWidth="7" markerHeight="7" refX="3" refY="3" orient="auto">
                      <path d="M0,0 L4,3 L0,6 Z" class="tm-arrow-head" />
                    </marker>
                  </defs>
                  <path
                    v-for="(e, i) in graphLayout.edges"
                    :key="i"
                    :d="e.d"
                    class="tm-edge"
                    marker-end="url(#tm-arrow)"
                  />
                </svg>
                <div
                  v-for="n in graphLayout.nodes"
                  :key="n.id"
                  :class="['tm-gnode', n.color, { 'running-layer': activeRow !== null && n.row === activeRow }]"
                  :style="{ left: n.x + 'px', top: n.y + 'px' }"
                  :title="n.type"
                >{{ n.type }}</div>
              </div>
            </div>
            <div class="tm-summary-grid">
              <div><span>#params</span><strong>{{ formatInt(monitor.paramCount) }}</strong></div>
              <div><span>Input shape</span><strong>{{ inputShapeText }}</strong></div>
              <div><span>num_classes</span><strong>{{ numClassesText }}</strong></div>
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
          <section class="tm-card tm-progress-hero" :class="{ done: isCompleted, cancelling: isCancelling, failed: isFailed, cancelled: isCancelled }">
            <div class="tm-hero-head">
              <div class="tm-hero-icon">
                <iconify-icon :icon="isFailed ? 'mdi:alert-circle-outline' : isCancelling ? 'mdi:loading' : isCancelled ? 'mdi:stop-circle-outline' : isRunning ? 'mdi:run-fast' : 'mdi:flag-checkered'" :class="{ spin: isCancelling }"></iconify-icon>
              </div>
              <div class="tm-hero-text">
                <strong>{{ heroTitle }}</strong>
                <span>{{ heroSubtitle }}</span>
              </div>
            </div>
            <div v-if="isActive" class="tm-hero-bars">
              <div class="tm-hero-bar dataset">
                <span class="tm-hero-bar-label">数据集下载</span>
                <div class="tm-ep-track big dataset"><i :style="{ width: `${datasetPercent}%` }"></i></div>
                <span class="tm-hero-bar-value">{{ datasetPercentText }}<template v-if="datasetBytesText"> · {{ datasetBytesText }}</template></span>
              </div>
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

          <section v-if="isCompleted && savedPath" class="tm-saved">
            <iconify-icon icon="mdi:folder-check-outline"></iconify-icon>
            <div class="tm-saved-body">
              <strong>训练结果已保存到本机</strong>
              <code>{{ savedPath }}</code>
              <span>该文件夹内含 model.pt（模型权重）与 metrics.json（训练指标）</span>
            </div>
            <button class="secondary-button tm-saved-copy" @click="copySavedPath">
              <iconify-icon icon="mdi:content-copy"></iconify-icon>
              复制路径
            </button>
          </section>

          <section v-if="isCompleted" class="tm-teaching-tip">
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
              <div v-if="isFailed" class="tm-log-line" style="color: var(--rose);">✗ 训练失败：{{ monitor.error }}</div>
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
