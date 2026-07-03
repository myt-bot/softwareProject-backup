// 训练监控页（Training Monitor）
// 作为一个全屏视图挂载在主 shell 之上：训练开始时打开，"返回继续修改"关闭回到搭建页。
// 图表用手绘 SVG 实现，无需外部依赖；支持 Running / Completed 两个动态状态。
//
// 数据来源分两种：
//   live 模式：轮询后端 /train/{id}/status 与 /result，用真实逐轮 metrics 画曲线。
//   demo 模式：后端不可用时回退到预设指标曲线（MOCK）做原型演示。
//
// 后端 metrics 结构（backend/trainer.py）：
//   [{ "epoch": 1, "train": {"loss":.., "accuracy":..}, "eval": {"loss":.., "accuracy":..} }, ...]
//   train = 训练集指标，eval = 验证集指标（对应前端的 val 曲线）。

const SVG_NS = "http://www.w3.org/2000/svg";

// 预设指标曲线（mock），趋势合理：loss 下降、acc 上升、val 略低但接近。
const MOCK = {
  totalEpochs: 10,
  loss: [1.2, 0.85, 0.62, 0.5, 0.42, 0.36, 0.32, 0.29, 0.27, 0.25],
  valLoss: [1.28, 0.94, 0.71, 0.58, 0.5, 0.45, 0.41, 0.39, 0.38, 0.37],
  trainAcc: [0.35, 0.55, 0.68, 0.76, 0.82, 0.86, 0.89, 0.91, 0.92, 0.93],
  valAcc: [0.32, 0.52, 0.65, 0.73, 0.79, 0.83, 0.86, 0.88, 0.89, 0.9],
};

const DEFAULT_LAYERS = [
  { type: "Input", color: "emerald" },
  { type: "Conv2D", color: "blue" },
  { type: "ReLU", color: "orange" },
  { type: "MaxPool", color: "purple" },
  { type: "Flatten", color: "indigo" },
  { type: "Linear", color: "cyan" },
  { type: "Dropout", color: "amber" },
  { type: "Output", color: "rose" },
];

const DEFAULT_HYPERPARAMS = {
  epochs: 10,
  batch_size: 64,
  rate: 0.001,
  optimizer: "Adam",
  loss_fn: "CrossEntropyLoss",
  device: "CPU",
};

// 空的实时数据序列（live 模式逐轮填充）。
function emptySeries(totalEpochs) {
  return {
    totalEpochs: totalEpochs || 1,
    loss: [],
    valLoss: [],
    trainAcc: [],
    valAcc: [],
  };
}

const monitor = {
  root: null,
  mounted: false,
  state: "running", // running | completed
  showTrainOnly: false, // legend 交互：show both / show train only
  visibleEpochs: 3, // demo running 状态曲线画到第几轮
  live: false,
  jobId: null,
  fetchStatus: null,
  fetchResult: null,
  onBackToBuilder: null,
  onRerun: null,
  hyperparams: { ...DEFAULT_HYPERPARAMS },
  layers: DEFAULT_LAYERS,
  paramCount: 367114,
  pollTimer: null,
  pollAttempt: 0,
  progress: 0.3,
  currentEpoch: 3,
  currentStep: 180,
  totalSteps: 600,
  series: emptySeries(10), // live 模式的真实逐轮指标
  result: null,
  error: null,
};


export function openTrainingMonitor(options = {}) {
  monitor.live = Boolean(options.live);
  monitor.jobId = options.jobId || null;
  monitor.fetchStatus = options.fetchStatus || null;
  monitor.fetchResult = options.fetchResult || null;
  monitor.onBackToBuilder = options.onBackToBuilder || null;
  monitor.onRerun = options.onRerun || null;
  monitor.hyperparams = { ...DEFAULT_HYPERPARAMS, ...(options.hyperparams || {}) };
  monitor.layers = options.layers?.length ? options.layers : DEFAULT_LAYERS;
  monitor.paramCount = options.paramCount || monitor.paramCount;

  monitor.state = "running";
  monitor.showTrainOnly = false;
  monitor.visibleEpochs = 3;
  monitor.progress = monitor.live ? 0 : 0.3;
  monitor.currentEpoch = monitor.live ? 0 : 3;
  monitor.currentStep = monitor.live ? 0 : 180;
  monitor.series = emptySeries(monitor.hyperparams.epochs);
  monitor.result = null;
  monitor.error = null;
  monitor.pollAttempt = 0;

  mount();
  render();

  if (monitor.live && monitor.jobId && monitor.fetchStatus) {
    startPolling();
  }
}


export function closeTrainingMonitor() {
  stopPolling();
  if (monitor.root) {
    monitor.root.classList.add("hidden");
  }
  monitor.mounted = false;
}


function mount() {
  monitor.root = document.getElementById("training-monitor");
  if (!monitor.root) {
    monitor.root = document.createElement("div");
    monitor.root.id = "training-monitor";
    document.body.appendChild(monitor.root);
  }
  monitor.root.classList.remove("hidden");
  monitor.mounted = true;
}


// —————————————————————————————————————————————
// 数据访问：live 用真实序列，demo 用 MOCK
// —————————————————————————————————————————————

function activeSeries() {
  return monitor.live ? monitor.series : MOCK;
}


// 当前应绘制到第几个点（已完成的 epoch 数）。
function visibleCount() {
  if (monitor.live) {
    return monitor.series.loss.length;
  }
  return monitor.state === "running" ? monitor.visibleEpochs : MOCK.totalEpochs;
}


// 从后端 metrics 数组构建 live 数据序列。
function ingestMetrics(metrics, totalEpochs) {
  const loss = [];
  const valLoss = [];
  const trainAcc = [];
  const valAcc = [];

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
function computeResults() {
  const s = activeSeries();
  const n = s.trainAcc.length;
  if (!n) return null;

  const finalAcc = s.trainAcc[n - 1];
  const bestVal = Math.max(...s.valAcc);
  const finalLoss = s.valLoss[n - 1];
  const gap = finalAcc - s.valAcc[n - 1];

  return {
    finalAcc: `${(finalAcc * 100).toFixed(1)}%`,
    bestVal: `${(bestVal * 100).toFixed(1)}%`,
    finalLoss: finalLoss.toFixed(4),
    gap: `${(gap * 100).toFixed(1)}%`,
  };
}


// —————————————————————————————————————————————
// 渲染
// —————————————————————————————————————————————

function render() {
  if (!monitor.root) return;
  const isRunning = monitor.state === "running";

  monitor.root.innerHTML = `
    <div class="tm-shell">
      ${renderTopBar(isRunning)}
      <div class="tm-body">
        ${renderSidebar(isRunning)}
        ${renderMain(isRunning)}
      </div>
      <div class="tm-footnote">
        ${monitor.live
          ? "已连接训练服务（training backend），曲线与指标来自后端真实训练结果。"
          : "原型阶段使用预设指标曲线模拟训练过程，后续可对接真实训练服务（training backend）。"}
      </div>
    </div>
  `;

  bindEvents();
  drawCharts();
}


function renderTopBar(isRunning) {
  const badge = isRunning
    ? `<span class="tm-badge running"><span class="tm-dot"></span>Running</span>`
    : `<span class="tm-badge completed"><iconify-icon icon="mdi:check-circle"></iconify-icon>Completed</span>`;

  return `
    <header class="tm-topbar">
      <div class="tm-topbar-left">
        <button class="icon-button" id="tm-back-icon" title="返回">
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
      <div class="tm-topbar-center">${badge}</div>
      <div class="tm-topbar-right">
        <button class="secondary-button" id="tm-back">
          <iconify-icon icon="mdi:pencil-outline"></iconify-icon>
          返回继续修改 Back to Builder
        </button>
        <button class="primary-button" id="tm-rerun">
          <iconify-icon icon="mdi:restart"></iconify-icon>
          重新训练 Re-run
        </button>
      </div>
    </header>
  `;
}


function renderSidebar(isRunning) {
  const hp = monitor.hyperparams;
  const total = monitor.live ? (monitor.series.totalEpochs || hp.epochs) : hp.epochs;
  // 后端未提供 step 粒度，live 模式下 Step 显示占位。
  const stepText = monitor.live ? "—" : `${monitor.currentStep}/${monitor.totalSteps}`;
  const etaText = isRunning ? (monitor.live ? "—" : "00:45") : "00:00";

  return `
    <aside class="tm-sidebar">
      <section class="tm-card">
        <h3>模型结构 Model Graph</h3>
        <div class="tm-minimap">
          ${monitor.layers
            .map(
              (layer, index) => `
            <div class="tm-mini-node ${layer.color}">${layer.type}</div>
            ${index < monitor.layers.length - 1 ? `<iconify-icon class="tm-mini-arrow" icon="mdi:chevron-down"></iconify-icon>` : ""}
          `
            )
            .join("")}
        </div>
        <div class="tm-summary-grid">
          <div><span>#params</span><strong>${formatInt(monitor.paramCount)}</strong></div>
          <div><span>Input shape</span><strong>28×28×1</strong></div>
          <div><span>num_classes</span><strong>10</strong></div>
        </div>
      </section>

      <section class="tm-card">
        <h3>训练超参数 Hyperparameters</h3>
        <div class="tm-hp-list">
          ${hpRow("epochs", hp.epochs)}
          ${hpRow("batch size", hp.batch_size)}
          ${hpRow("learning rate", hp.rate)}
          ${hpRow("optimizer", hp.optimizer)}
          ${hpRow("loss", hp.loss_fn)}
          ${hpRow("device", hp.device)}
        </div>
      </section>

      <section class="tm-card">
        <h3>训练状态 Training Status</h3>
        <div class="tm-status-rows">
          <div class="tm-status-item">
            <span>Epoch</span>
            <strong>${monitor.currentEpoch}/${total}</strong>
          </div>
          <div class="tm-status-item">
            <span>Step</span>
            <strong>${stepText}</strong>
          </div>
          <div class="tm-status-item">
            <span>ETA</span>
            <strong>${etaText}</strong>
          </div>
        </div>
        <div class="tm-progress">
          <div class="tm-progress-bar ${isRunning ? "" : "done"}" style="width: ${Math.round((isRunning ? monitor.progress : 1) * 100)}%"></div>
        </div>
        <p class="tm-progress-label">${isRunning ? `训练中 ${Math.round(monitor.progress * 100)}%` : "训练完成 100%"}</p>
      </section>
    </aside>
  `;
}


function renderMain(isRunning) {
  const results = isRunning ? null : computeResults();
  const val = key => (results ? results[key] : null);

  return `
    <main class="tm-main">
      <div class="tm-charts">
        ${renderChartCard("loss", "Loss 曲线", "损失越低越好")}
        ${renderChartCard("acc", "Accuracy 曲线", "准确率越高越好")}
      </div>

      <div class="tm-result-cards">
        ${resultCard("Final Accuracy", val("finalAcc"), "最终训练准确率", true)}
        ${resultCard("Best Val Accuracy", val("bestVal"), "最佳验证准确率", false)}
        ${resultCard("Final Loss", val("finalLoss"), "最终验证损失", false)}
        ${resultCard("Generalization Gap", val("gap"), "train acc − val acc", false)}
      </div>

      ${isRunning ? "" : renderTeachingTip()}

      <section class="tm-logs">
        <div class="tm-logs-head">
          <h3><iconify-icon icon="mdi:console-line"></iconify-icon> 训练日志 Training Logs</h3>
          ${monitor.live
            ? ""
            : `<button class="tm-mini-btn" id="tm-complete">
                <iconify-icon icon="mdi:fast-forward"></iconify-icon>
                模拟完成 Complete
              </button>`}
        </div>
        <div class="tm-logs-body" id="tm-logs-body">
          ${renderLogs(isRunning)}
        </div>
      </section>
    </main>
  `;
}


function renderChartCard(key, title, subtitle) {
  const trainOnly = monitor.showTrainOnly;
  const valLabel = key === "loss" ? "val loss" : "val acc";
  const trainLabel = key === "loss" ? "train loss" : "train acc";
  return `
    <section class="tm-card tm-chart-card">
      <div class="tm-chart-head">
        <div>
          <h3>${title}</h3>
          <span class="tm-chart-sub">${subtitle} · 横轴 epoch</span>
        </div>
        <div class="tm-legend" data-chart="${key}">
          <button class="tm-legend-item ${trainOnly ? "" : "active"}" data-series="train">
            <i class="dot train"></i>${trainLabel}
          </button>
          <button class="tm-legend-item ${trainOnly ? "muted" : "active"}" data-series="val">
            <i class="dot val"></i>${valLabel}
          </button>
        </div>
      </div>
      <div class="tm-chart-wrap">
        <svg class="tm-chart" id="tm-chart-${key}" viewBox="0 0 520 260" preserveAspectRatio="none"></svg>
        <div class="tm-tooltip hidden" id="tm-tooltip-${key}"></div>
      </div>
    </section>
  `;
}


function renderTeachingTip() {
  return `
    <section class="tm-teaching-tip">
      <iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon>
      <div>
        <strong>教学提示 Teaching Tip</strong>
        <p>如果 train acc 持续上升但 val acc 停滞，可能出现 overfitting（过拟合）。可尝试增大 Dropout、加数据增强或提前停止。</p>
      </div>
    </section>
  `;
}


function resultCard(label, value, hint, highlight) {
  const shown = value === null || value === undefined ? "--" : value;
  const cls = highlight && value ? "highlight" : "";
  const sub = value === null || value === undefined ? "实时更新中..." : hint;
  return `
    <div class="tm-result-card ${cls}">
      <span class="tm-result-label">${label}</span>
      <strong class="tm-result-value">${shown}</strong>
      <span class="tm-result-hint">${sub}</span>
    </div>
  `;
}


function renderLogs(isRunning) {
  if (monitor.error) {
    return `<div class="tm-log-line" style="color: var(--rose);">✗ 训练失败：${monitor.error}</div>`;
  }

  const s = activeSeries();
  const visible = visibleCount();
  const total = monitor.live ? (s.totalEpochs || monitor.hyperparams.epochs) : MOCK.totalEpochs;
  const lines = [];

  for (let i = 0; i < visible; i += 1) {
    lines.push(
      `Epoch ${i + 1}/${total} - loss=${numToStr(s.loss[i])} - acc=${numToStr(s.trainAcc[i])} - val_acc=${numToStr(s.valAcc[i])}`
    );
  }

  if (isRunning) {
    if (monitor.live && visible === 0) {
      lines.push(`> 正在准备数据集并启动训练 ...`);
    } else {
      lines.push(`> 正在训练 Epoch ${Math.min(visible + 1, total)}/${total} ...`);
    }
  } else {
    lines.push(`> 训练完成，模型权重已保存。`);
  }

  return lines
    .map(line => {
      const running = line.startsWith(">");
      return `<div class="tm-log-line ${running ? "muted" : ""}">${line}</div>`;
    })
    .join("");
}


function hpRow(label, value) {
  return `<div class="tm-hp-row"><span>${label}</span><code>${value}</code></div>`;
}


// —————————————————————————————————————————————
// 图表绘制（手绘 SVG）
// —————————————————————————————————————————————

function drawCharts() {
  const s = activeSeries();
  const lossMax = niceLossMax([...s.loss, ...s.valLoss]);

  drawChart("loss", {
    train: s.loss,
    val: s.valLoss,
    yMin: 0,
    yMax: lossMax,
    yTicks: ticksFor(lossMax),
  });
  drawChart("acc", {
    train: s.trainAcc,
    val: s.valAcc,
    yMin: 0,
    yMax: 1,
    yTicks: [0, 0.25, 0.5, 0.75, 1],
  });
}


function drawChart(key, cfg) {
  const svg = document.getElementById(`tm-chart-${key}`);
  if (!svg) return;
  svg.innerHTML = "";

  const W = 520;
  const H = 260;
  const pad = { left: 42, right: 16, top: 16, bottom: 30 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;

  const s = activeSeries();
  const total = Math.max(monitor.live ? (s.totalEpochs || monitor.hyperparams.epochs) : MOCK.totalEpochs, 2);
  const visible = visibleCount();

  const xOf = epochIndex => pad.left + (plotW * epochIndex) / (total - 1);
  const yOf = value => pad.top + plotH * (1 - (value - cfg.yMin) / (cfg.yMax - cfg.yMin));

  // 网格 + Y 轴刻度
  cfg.yTicks.forEach(tick => {
    const y = yOf(tick);
    line(svg, pad.left, y, W - pad.right, y, "tm-grid");
    text(svg, pad.left - 8, y + 3, formatTick(key, tick), "tm-axis-label", "end");
  });

  // X 轴刻度（epoch）
  for (let i = 0; i < total; i += 1) {
    const x = xOf(i);
    text(svg, x, H - pad.bottom + 18, String(i + 1), "tm-axis-label", "middle");
  }

  // 灰色占位区（尚未训练到的部分）
  if (visible < total && visible > 0) {
    const startX = xOf(visible - 1);
    rect(svg, startX, pad.top, W - pad.right - startX, plotH, "tm-placeholder");
  } else if (visible === 0) {
    rect(svg, pad.left, pad.top, plotW, plotH, "tm-placeholder");
  }

  const series = [
    { name: "val", data: cfg.val, cls: "val" },
    { name: "train", data: cfg.train, cls: "train" },
  ];

  series.forEach(item => {
    if (item.name === "val" && monitor.showTrainOnly) return;
    const pts = [];
    for (let i = 0; i < Math.max(visible, 0); i += 1) {
      if (typeof item.data[i] !== "number") continue;
      pts.push({ x: xOf(i), y: yOf(item.data[i]) });
    }
    if (pts.length >= 2) {
      polyline(svg, pts, `tm-series ${item.cls}`);
    }
    pts.forEach(p => dot(svg, p.x, p.y, `tm-point ${item.cls}`));
  });

  // 交互层：hover 显示 tooltip
  attachChartHover(svg, key, { xOf, cfg, visible });
}


function attachChartHover(svg, key, ctx) {
  const tooltip = document.getElementById(`tm-tooltip-${key}`);
  const guide = line(svg, 0, 16, 0, 230, "tm-guide hidden");

  svg.addEventListener("mousemove", event => {
    if (ctx.visible <= 0) return;
    const rect = svg.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const px = ratio * 520;
    let nearest = 0;
    let best = Infinity;
    for (let i = 0; i < ctx.visible; i += 1) {
      const d = Math.abs(ctx.xOf(i) - px);
      if (d < best) {
        best = d;
        nearest = i;
      }
    }

    const gx = ctx.xOf(nearest);
    guide.setAttribute("x1", gx);
    guide.setAttribute("x2", gx);
    guide.classList.remove("hidden");

    const trainVal = ctx.cfg.train[nearest];
    const valVal = ctx.cfg.val[nearest];
    const rows = monitor.showTrainOnly
      ? `<div><i class="dot train"></i>${labelFor(key, "train")}: <b>${fmt(key, trainVal)}</b></div>`
      : `<div><i class="dot train"></i>${labelFor(key, "train")}: <b>${fmt(key, trainVal)}</b></div>
         <div><i class="dot val"></i>${labelFor(key, "val")}: <b>${fmt(key, valVal)}</b></div>`;

    tooltip.innerHTML = `<div class="tm-tt-title">Epoch ${nearest + 1}</div>${rows}`;
    tooltip.classList.remove("hidden");
    const leftPct = (gx / 520) * 100;
    tooltip.style.left = `${leftPct}%`;
  });

  svg.addEventListener("mouseleave", () => {
    guide.classList.add("hidden");
    tooltip.classList.add("hidden");
  });
}


// —————————————————————————————————————————————
// 事件绑定与交互
// —————————————————————————————————————————————

function bindEvents() {
  byId("tm-back-icon")?.addEventListener("click", handleBack);
  byId("tm-back")?.addEventListener("click", handleBack);
  byId("tm-rerun")?.addEventListener("click", handleRerun);
  byId("tm-complete")?.addEventListener("click", handleSimulateComplete);

  monitor.root.querySelectorAll(".tm-legend-item").forEach(btn => {
    btn.addEventListener("click", () => toggleSeries(btn.dataset.series));
  });
}


function handleBack() {
  stopPolling();
  closeTrainingMonitor();
  monitor.onBackToBuilder?.();
}


async function handleRerun() {
  stopPolling();
  monitor.state = "running";
  monitor.showTrainOnly = false;
  monitor.visibleEpochs = 3;
  monitor.progress = monitor.live ? 0 : 0.3;
  monitor.currentEpoch = monitor.live ? 0 : 3;
  monitor.currentStep = monitor.live ? 0 : 180;
  monitor.series = emptySeries(monitor.hyperparams.epochs);
  monitor.result = null;
  monitor.error = null;
  render();

  if (monitor.onRerun) {
    try {
      const res = await monitor.onRerun();
      if (res?.jobId && monitor.fetchStatus) {
        monitor.jobId = res.jobId;
        monitor.live = true;
        toast("info", "已重新提交训练任务。");
        startPolling();
      } else {
        toast("warning", "重新训练未返回任务号，进入原型演示。");
      }
    } catch (error) {
      toast("error", error.message || "重新训练失败");
    }
  } else {
    toast("info", "开始训练（mock）");
  }
}


function handleSimulateComplete() {
  // 仅 demo 模式提供，用于演示 Running → Completed 切换。
  stopPolling();
  monitor.state = "completed";
  monitor.visibleEpochs = MOCK.totalEpochs;
  monitor.progress = 1;
  monitor.currentEpoch = MOCK.totalEpochs;
  monitor.currentStep = monitor.totalSteps;
  render();
  toast("success", "训练完成，Final Accuracy 93.0%");
}


function toggleSeries(series) {
  // 只对 val 做显隐切换：show both / show train only
  if (series === "val") {
    monitor.showTrainOnly = !monitor.showTrainOnly;
  } else {
    monitor.showTrainOnly = false;
  }
  render();
}


// —————————————————————————————————————————————
// 真实后端轮询（live 模式）
// —————————————————————————————————————————————

function startPolling() {
  stopPolling();
  monitor.pollAttempt = 0;
  poll();
}


function stopPolling() {
  if (monitor.pollTimer) {
    clearTimeout(monitor.pollTimer);
    monitor.pollTimer = null;
  }
}


async function poll() {
  const MAX = 3600; // 最长约 1 小时（每秒一次）
  try {
    const status = await monitor.fetchStatus(monitor.jobId);
    applyLiveStatus(status);

    const s = status?.status;
    if (s === "completed") {
      try {
        const result = await monitor.fetchResult(monitor.jobId);
        applyLiveResult(result);
      } catch (error) {
        // 结果接口异常时，用最后一次 status 的 metrics 收尾。
        monitor.state = "completed";
        render();
        toast("warning", "训练已完成，但结果接口读取失败。");
      }
      return;
    }
    if (s === "failed") {
      monitor.error = status?.error || "未知错误";
      monitor.state = "completed";
      render();
      toast("error", `训练失败: ${monitor.error}`);
      return;
    }
    if (s === "cancelled") {
      monitor.state = "completed";
      render();
      toast("warning", "训练任务已取消。");
      return;
    }
    if (monitor.pollAttempt >= MAX) {
      toast("warning", "训练轮询超时，请稍后手动查看结果。");
      return;
    }
    monitor.pollAttempt += 1;
    monitor.pollTimer = setTimeout(poll, 1000);
  } catch (error) {
    toast("error", error.message || "训练状态查询失败");
  }
}


function applyLiveStatus(status) {
  const total = status?.total_epochs || monitor.hyperparams.epochs;
  const current = status?.current_epoch ?? 0;

  ingestMetrics(status?.metrics, total);
  monitor.currentEpoch = current;
  monitor.hyperparams.epochs = total;
  monitor.progress = typeof status?.progress === "number"
    ? status.progress
    : (total ? current / total : 0);
  monitor.state = "running";
  monitor.error = status?.error || null;
  render();
}


function applyLiveResult(result) {
  monitor.result = result;
  ingestMetrics(result?.metrics, result?.metrics?.length || monitor.hyperparams.epochs);
  monitor.state = "completed";
  monitor.progress = 1;
  monitor.currentEpoch = monitor.series.loss.length || monitor.hyperparams.epochs;
  if (result?.device) {
    monitor.hyperparams.device = String(result.device).toUpperCase();
  }
  render();

  const acc = typeof result?.accuracy === "number" ? `${(result.accuracy * 100).toFixed(1)}%` : "未知";
  const loss = typeof result?.loss === "number" ? result.loss.toFixed(4) : "未知";
  toast("success", `训练完成，accuracy=${acc}，loss=${loss}`);
}


// —————————————————————————————————————————————
// SVG / 工具函数
// —————————————————————————————————————————————

function line(svg, x1, y1, x2, y2, cls) {
  const el = document.createElementNS(SVG_NS, "line");
  el.setAttribute("x1", x1);
  el.setAttribute("y1", y1);
  el.setAttribute("x2", x2);
  el.setAttribute("y2", y2);
  el.setAttribute("class", cls);
  svg.appendChild(el);
  return el;
}


function rect(svg, x, y, w, h, cls) {
  const el = document.createElementNS(SVG_NS, "rect");
  el.setAttribute("x", x);
  el.setAttribute("y", y);
  el.setAttribute("width", Math.max(0, w));
  el.setAttribute("height", Math.max(0, h));
  el.setAttribute("class", cls);
  svg.appendChild(el);
  return el;
}


function polyline(svg, points, cls) {
  const el = document.createElementNS(SVG_NS, "polyline");
  el.setAttribute("points", points.map(p => `${p.x},${p.y}`).join(" "));
  el.setAttribute("class", cls);
  svg.appendChild(el);
  return el;
}


function dot(svg, cx, cy, cls) {
  const el = document.createElementNS(SVG_NS, "circle");
  el.setAttribute("cx", cx);
  el.setAttribute("cy", cy);
  el.setAttribute("r", 3);
  el.setAttribute("class", cls);
  svg.appendChild(el);
  return el;
}


function text(svg, x, y, content, cls, anchor) {
  const el = document.createElementNS(SVG_NS, "text");
  el.setAttribute("x", x);
  el.setAttribute("y", y);
  el.setAttribute("class", cls);
  el.setAttribute("text-anchor", anchor || "start");
  el.textContent = content;
  svg.appendChild(el);
  return el;
}


// 为 loss 轴选一个"漂亮"的上界：至少 0.1，向上取整到 0.1 的倍数。
function niceLossMax(values) {
  const nums = values.filter(v => typeof v === "number" && !Number.isNaN(v));
  if (!nums.length) return 1.4;
  const max = Math.max(...nums);
  if (max <= 0) return 1;
  return Math.max(0.1, Math.ceil(max * 10) / 10);
}


function ticksFor(yMax) {
  return [0, 0.25, 0.5, 0.75, 1].map(fraction => Number((fraction * yMax).toFixed(4)));
}


function formatTick(key, value) {
  return key === "loss" ? value.toFixed(2) : `${Math.round(value * 100)}%`;
}


function fmt(key, value) {
  if (typeof value !== "number" || Number.isNaN(value)) return "—";
  return key === "loss" ? value.toFixed(3) : `${(value * 100).toFixed(1)}%`;
}


function labelFor(key, series) {
  if (key === "loss") return series === "train" ? "train loss" : "val loss";
  return series === "train" ? "train acc" : "val acc";
}


function numberOr(value, fallback) {
  return typeof value === "number" && !Number.isNaN(value) ? value : fallback;
}


function numToStr(value) {
  return typeof value === "number" && !Number.isNaN(value) ? value.toFixed(2) : "—";
}


function formatInt(value) {
  return Number(value).toLocaleString("en-US");
}


function byId(id) {
  return document.getElementById(id);
}


function toast(type, message) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  const icon = {
    success: "mdi:check-circle",
    error: "mdi:alert",
    warning: "mdi:clock-alert-outline",
    info: "mdi:information-outline",
  }[type] || "mdi:information-outline";
  el.className = `toast ${type}`;
  el.innerHTML = `<iconify-icon icon="${icon}"></iconify-icon><span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-out");
    setTimeout(() => el.remove(), 450);
  }, 3200);
}
