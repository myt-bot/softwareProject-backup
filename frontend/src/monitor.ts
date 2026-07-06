// 训练监控页（Training Monitor）状态机。
// 视图渲染在 components/TrainingMonitor.vue；本模块负责数据与轮询。
//
// 数据来源分两种：
//   live 模式：轮询后端 /train/{id}/status 与 /result，用真实逐轮 metrics 画曲线。
//   demo 模式：后端不可用时回退到预设指标曲线（MOCK）做原型演示。
//
// 后端 metrics 结构（backend/trainer.py）：
//   [{ "epoch": 1, "train": {"loss":.., "accuracy":..}, "eval": {"loss":.., "accuracy":..} }, ...]
//   train = 训练集指标，eval = 验证集指标（对应前端的 val 曲线）。

import { reactive } from "vue";
import { showToast } from "./store";
import type { CancelTrainingResponse, EpochMetrics, MonitorLayer, TrainingResult, TrainingStatus } from "./types";

// 预设指标曲线（mock），趋势合理：loss 下降、acc 上升、val 略低但接近。
export const MOCK = {
  totalEpochs: 10,
  loss: [1.2, 0.85, 0.62, 0.5, 0.42, 0.36, 0.32, 0.29, 0.27, 0.25],
  valLoss: [1.28, 0.94, 0.71, 0.58, 0.5, 0.45, 0.41, 0.39, 0.38, 0.37],
  trainAcc: [0.35, 0.55, 0.68, 0.76, 0.82, 0.86, 0.89, 0.91, 0.92, 0.93],
  valAcc: [0.32, 0.52, 0.65, 0.73, 0.79, 0.83, 0.86, 0.88, 0.89, 0.9],
};

const DEFAULT_LAYERS: MonitorLayer[] = [
  { type: "Input", color: "emerald" },
  { type: "Conv2D", color: "blue" },
  { type: "ReLU", color: "orange" },
  { type: "MaxPool", color: "purple" },
  { type: "Flatten", color: "indigo" },
  { type: "Linear", color: "cyan" },
  { type: "Dropout", color: "amber" },
  { type: "Output", color: "rose" },
];

export interface MonitorHyperparams {
  epochs: number;
  batch_size: number | string;
  rate: number | string;
  optimizer: string;
  loss_fn: string;
  device: string;
}

const DEFAULT_HYPERPARAMS: MonitorHyperparams = {
  epochs: 10,
  batch_size: 64,
  rate: 0.001,
  optimizer: "Adam",
  loss_fn: "CrossEntropyLoss",
  device: "CPU",
};

export interface MonitorSeries {
  totalEpochs: number;
  loss: number[];
  valLoss: number[];
  trainAcc: number[];
  valAcc: number[];
}

// 空的实时数据序列（live 模式逐轮填充）。
function emptySeries(totalEpochs: number): MonitorSeries {
  return {
    totalEpochs: totalEpochs || 1,
    loss: [],
    valLoss: [],
    trainAcc: [],
    valAcc: [],
  };
}

export interface OpenMonitorOptions {
  live?: boolean;
  jobId?: string;
  fetchStatus?: (jobId: string) => Promise<TrainingStatus>;
  fetchResult?: (jobId: string) => Promise<TrainingResult>;
  cancelJob?: (jobId: string) => Promise<CancelTrainingResponse>;
  onBackToBuilder?: () => void;
  onRerun?: () => Promise<{ jobId?: string } | undefined>;
  hyperparams?: Partial<MonitorHyperparams>;
  layers?: MonitorLayer[];
  paramCount?: number;
}

// 非响应式的回调与定时器
let fetchStatusFn: OpenMonitorOptions["fetchStatus"] = undefined;
let fetchResultFn: OpenMonitorOptions["fetchResult"] = undefined;
let cancelJobFn: OpenMonitorOptions["cancelJob"] = undefined;
let onBackToBuilderFn: OpenMonitorOptions["onBackToBuilder"] = undefined;
let onRerunFn: OpenMonitorOptions["onRerun"] = undefined;
let pollTimer: number | null = null;

export const monitor = reactive({
  visible: false,
  state: "running" as "running" | "completed",
  visibleEpochs: 3, // demo running 状态曲线画到第几轮
  live: false,
  jobId: null as string | null,
  hyperparams: { ...DEFAULT_HYPERPARAMS } as MonitorHyperparams,
  layers: DEFAULT_LAYERS as MonitorLayer[],
  paramCount: 367114,
  pollAttempt: 0,
  progress: 0.3,
  currentEpoch: 3,
  currentStep: 180,
  totalSteps: 600,
  series: emptySeries(10) as MonitorSeries, // live 模式的真实逐轮指标
  result: null as TrainingResult | null,
  error: null as string | null,
  stopping: false, // 停止请求已发出、等待后端确认
});


export function openTrainingMonitor(options: OpenMonitorOptions = {}) {
  monitor.live = Boolean(options.live);
  monitor.jobId = options.jobId || null;
  fetchStatusFn = options.fetchStatus;
  fetchResultFn = options.fetchResult;
  cancelJobFn = options.cancelJob;
  onBackToBuilderFn = options.onBackToBuilder;
  onRerunFn = options.onRerun;
  monitor.stopping = false;
  monitor.hyperparams = { ...DEFAULT_HYPERPARAMS, ...(options.hyperparams || {}) };
  monitor.layers = options.layers?.length ? options.layers : DEFAULT_LAYERS;
  monitor.paramCount = options.paramCount || monitor.paramCount;

  monitor.state = "running";
  monitor.visibleEpochs = 3;
  monitor.progress = monitor.live ? 0 : 0.3;
  monitor.currentEpoch = monitor.live ? 0 : 3;
  monitor.currentStep = monitor.live ? 0 : 180;
  monitor.totalSteps = monitor.live ? 0 : 600;
  monitor.series = emptySeries(monitor.hyperparams.epochs);
  monitor.result = null;
  monitor.error = null;
  monitor.pollAttempt = 0;

  monitor.visible = true;

  if (monitor.live && monitor.jobId && fetchStatusFn) {
    startPolling();
  }
}


export function closeTrainingMonitor() {
  stopPolling();
  monitor.visible = false;
}


// —————————————————————————————————————————————
// 数据访问：live 用真实序列，demo 用 MOCK
// —————————————————————————————————————————————

export function activeSeries(): MonitorSeries {
  return monitor.live ? monitor.series : MOCK;
}


// 当前应绘制到第几个点（已完成的 epoch 数）。
export function visibleCount() {
  if (monitor.live) {
    return monitor.series.loss.length;
  }
  return monitor.state === "running" ? monitor.visibleEpochs : MOCK.totalEpochs;
}


// 从后端 metrics 数组构建 live 数据序列。
function ingestMetrics(metrics: EpochMetrics[] | undefined, totalEpochs: number) {
  const loss: number[] = [];
  const valLoss: number[] = [];
  const trainAcc: number[] = [];
  const valAcc: number[] = [];

  (metrics || []).forEach(item => {
    const train = item.train || {};
    const evalM = item.eval || {};
    loss.push(numberOr(train.loss, 0));
    trainAcc.push(numberOr(train.accuracy, 0));
    valLoss.push(numberOr(evalM.loss, 0));
    valAcc.push(numberOr(evalM.accuracy, 0));
  });

  monitor.series = {
    totalEpochs: totalEpochs || monitor.hyperparams.epochs || metrics?.length || 1,
    loss,
    valLoss,
    trainAcc,
    valAcc,
  };
}


// 计算完成态的四张结果卡数值。
export function computeResults() {
  const s = activeSeries();
  const n = s.trainAcc.length;
  if (!n) return null;

  const finalAcc = s.trainAcc[n - 1]!;
  const bestVal = Math.max(...s.valAcc);
  const finalLoss = s.valLoss[n - 1]!;
  const gap = finalAcc - s.valAcc[n - 1]!;

  return {
    finalAcc: `${(finalAcc * 100).toFixed(1)}%`,
    bestVal: `${(bestVal * 100).toFixed(1)}%`,
    finalLoss: finalLoss.toFixed(4),
    gap: `${(gap * 100).toFixed(1)}%`,
  };
}


// —————————————————————————————————————————————
// 交互
// —————————————————————————————————————————————

export function handleBack() {
  stopPolling();
  closeTrainingMonitor();
  onBackToBuilderFn?.();
}


// 停止进行中的训练：请求后端取消，轮询会在状态变为 cancelled 后收尾
export async function handleStopTraining() {
  if (!monitor.jobId || !cancelJobFn || monitor.stopping) return;
  monitor.stopping = true;

  try {
    const result = await cancelJobFn(monitor.jobId);
    if (result?.cancelled) {
      showToast("warning", "已请求停止训练。");
    } else {
      showToast("info", `任务已处于「${result?.status || "未知"}」状态，无需停止。`);
      monitor.stopping = false;
    }
  } catch (error) {
    showToast("error", (error as Error)?.message || "停止训练失败");
    monitor.stopping = false;
  }
}


export async function handleRerun() {
  stopPolling();
  monitor.stopping = false;
  monitor.state = "running";
  monitor.visibleEpochs = 3;
  monitor.progress = monitor.live ? 0 : 0.3;
  monitor.currentEpoch = monitor.live ? 0 : 3;
  monitor.currentStep = monitor.live ? 0 : 180;
  monitor.totalSteps = monitor.live ? 0 : 600;
  monitor.series = emptySeries(monitor.hyperparams.epochs);
  monitor.result = null;
  monitor.error = null;

  if (onRerunFn) {
    try {
      const res = await onRerunFn();
      if (res?.jobId && fetchStatusFn) {
        monitor.jobId = res.jobId;
        monitor.live = true;
        showToast("info", "已重新提交训练任务。");
        startPolling();
      } else {
        showToast("warning", "重新训练未返回任务号，进入原型演示。");
      }
    } catch (error) {
      showToast("error", (error as Error)?.message || "重新训练失败");
    }
  } else {
    showToast("info", "开始训练（mock）");
  }
}


export function handleSimulateComplete() {
  // 仅 demo 模式提供，用于演示 Running → Completed 切换。
  stopPolling();
  monitor.state = "completed";
  monitor.visibleEpochs = MOCK.totalEpochs;
  monitor.progress = 1;
  monitor.currentEpoch = MOCK.totalEpochs;
  monitor.currentStep = monitor.totalSteps;
  showToast("success", "训练完成，Final Accuracy 93.0%");
}




// —————————————————————————————————————————————
// 真实后端轮询（live 模式）
// —————————————————————————————————————————————

function startPolling() {
  stopPolling();
  monitor.pollAttempt = 0;
  void poll();
}


function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}


async function poll() {
  const MAX = 3600; // 最长约 1 小时（每秒一次）
  if (!fetchStatusFn || !monitor.jobId) return;
  try {
    const status = await fetchStatusFn(monitor.jobId);
    applyLiveStatus(status);

    const s = status?.status;
    if (s === "completed") {
      monitor.stopping = false;
      try {
        const result = await fetchResultFn!(monitor.jobId);
        applyLiveResult(result);
      } catch {
        // 结果接口异常时，用最后一次 status 的 metrics 收尾。
        monitor.state = "completed";
        showToast("warning", "训练已完成，但结果接口读取失败。");
      }
      return;
    }
    if (s === "failed") {
      monitor.stopping = false;
      monitor.error = status?.error || "未知错误";
      monitor.state = "completed";
      showToast("error", `训练失败: ${monitor.error}`);
      return;
    }
    if (s === "cancelled") {
      monitor.stopping = false;
      monitor.state = "completed";
      showToast("warning", "训练任务已取消。");
      return;
    }
    if (monitor.pollAttempt >= MAX) {
      showToast("warning", "训练轮询超时，请稍后手动查看结果。");
      return;
    }
    monitor.pollAttempt += 1;
    pollTimer = window.setTimeout(() => void poll(), 1000);
  } catch (error) {
    showToast("error", (error as Error)?.message || "训练状态查询失败");
  }
}


function applyLiveStatus(status: TrainingStatus) {
  const total = status?.total_epochs || monitor.hyperparams.epochs;
  const current = status?.current_epoch ?? 0;

  ingestMetrics(status?.metrics, total);
  monitor.currentEpoch = current;
  monitor.hyperparams.epochs = total;
  // 轮次内 step 进度（后端每个 batch 更新一次）
  monitor.currentStep = status?.current_step ?? 0;
  monitor.totalSteps = status?.total_steps ?? 0;
  monitor.progress = typeof status?.progress === "number"
    ? status.progress
    : (total ? current / total : 0);
  monitor.state = "running";
  monitor.error = status?.error || null;
}


function applyLiveResult(result: TrainingResult) {
  monitor.result = result;
  ingestMetrics(result?.metrics, result?.metrics?.length || monitor.hyperparams.epochs);
  monitor.state = "completed";
  monitor.progress = 1;
  monitor.currentEpoch = monitor.series.loss.length || monitor.hyperparams.epochs;
  if (result?.device) {
    monitor.hyperparams.device = String(result.device).toUpperCase();
  }

  const acc = typeof result?.accuracy === "number" ? `${(result.accuracy * 100).toFixed(1)}%` : "未知";
  const loss = typeof result?.loss === "number" ? result.loss.toFixed(4) : "未知";
  showToast("success", `训练完成，accuracy=${acc}，loss=${loss}`);
}


// —————————————————————————————————————————————
// 工具函数
// —————————————————————————————————————————————

export function niceLossMax(values: number[]) {
  // 为 loss 轴选一个"漂亮"的上界：至少 0.1，向上取整到 0.1 的倍数。
  const nums = values.filter(v => typeof v === "number" && !Number.isNaN(v));
  if (!nums.length) return 1.4;
  const max = Math.max(...nums);
  if (max <= 0) return 1;
  return Math.max(0.1, Math.ceil(max * 10) / 10);
}


export function ticksFor(yMax: number) {
  return [0, 0.25, 0.5, 0.75, 1].map(fraction => Number((fraction * yMax).toFixed(4)));
}


export function formatTick(key: string, value: number) {
  return key === "loss" ? value.toFixed(2) : `${Math.round(value * 100)}%`;
}


export function fmt(key: string, value: number | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return key === "loss" ? value.toFixed(3) : `${(value * 100).toFixed(1)}%`;
}


export function labelFor(key: string, series: string) {
  if (key === "loss") return series === "train" ? "train loss" : "val loss";
  return series === "train" ? "train acc" : "val acc";
}


function numberOr(value: number | undefined, fallback: number) {
  return typeof value === "number" && !Number.isNaN(value) ? value : fallback;
}


export function numToStr(value: number | undefined) {
  return typeof value === "number" && !Number.isNaN(value) ? value.toFixed(2) : "—";
}


export function formatInt(value: number) {
  return Number(value).toLocaleString("en-US");
}
