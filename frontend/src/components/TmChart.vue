<script setup lang="ts">
// 训练指标折线图（手绘 SVG，无外部依赖），对应原 training.js 的 drawChart。
import { computed, ref } from "vue";
import { fmt, formatTick, labelFor } from "../monitor";
import type { Point } from "../types";

const props = defineProps<{
  chartKey: "loss" | "acc";
  title: string;
  subtitle: string;
  train: number[];
  val: number[];
  yMin: number;
  yMax: number;
  yTicks: number[];
  total: number;
  visible: number;
  showTrainOnly: boolean;
}>();

const emit = defineEmits<{
  toggle: [series: string];
}>();

const W = 520;
const H = 260;
const pad = { left: 42, right: 16, top: 16, bottom: 30 };
const plotW = W - pad.left - pad.right;
const plotH = H - pad.top - pad.bottom;

const totalEpochs = computed(() => Math.max(props.total, 2));

function xOf(epochIndex: number) {
  return pad.left + (plotW * epochIndex) / (totalEpochs.value - 1);
}

function yOf(value: number) {
  return pad.top + plotH * (1 - (value - props.yMin) / (props.yMax - props.yMin));
}

// 网格 + Y 轴刻度
const gridLines = computed(() =>
  props.yTicks.map(tick => ({
    y: yOf(tick),
    label: formatTick(props.chartKey, tick),
  }))
);

// X 轴刻度（epoch）
const xLabels = computed(() =>
  Array.from({ length: totalEpochs.value }, (_, i) => ({
    x: xOf(i),
    label: String(i + 1),
  }))
);

// 灰色占位区（尚未训练到的部分）
const placeholder = computed(() => {
  if (props.visible < totalEpochs.value && props.visible > 0) {
    const startX = xOf(props.visible - 1);
    return { x: startX, y: pad.top, width: Math.max(0, W - pad.right - startX), height: plotH };
  }
  if (props.visible === 0) {
    return { x: pad.left, y: pad.top, width: plotW, height: plotH };
  }
  return null;
});

// val 先画、train 后画（train 在上层）
const renderSeries = computed(() => {
  const series = [
    { name: "val", data: props.val, cls: "val" },
    { name: "train", data: props.train, cls: "train" },
  ];

  return series
    .filter(item => !(item.name === "val" && props.showTrainOnly))
    .map(item => {
      const pts: Point[] = [];
      for (let i = 0; i < Math.max(props.visible, 0); i += 1) {
        const value = item.data[i];
        if (typeof value !== "number") continue;
        pts.push({ x: xOf(i), y: yOf(value) });
      }
      return {
        cls: item.cls,
        pts,
        pointsAttr: pts.map(p => `${p.x},${p.y}`).join(" "),
      };
    });
});

// 交互层：hover 显示 tooltip
const hoverIndex = ref<number | null>(null);

function handleMouseMove(event: MouseEvent) {
  if (props.visible <= 0) return;
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
  const ratio = (event.clientX - rect.left) / rect.width;
  const px = ratio * W;
  let nearest = 0;
  let best = Infinity;
  for (let i = 0; i < props.visible; i += 1) {
    const d = Math.abs(xOf(i) - px);
    if (d < best) {
      best = d;
      nearest = i;
    }
  }
  hoverIndex.value = nearest;
}

function handleMouseLeave() {
  hoverIndex.value = null;
}

const guideX = computed(() => (hoverIndex.value === null ? 0 : xOf(hoverIndex.value)));
const tooltipLeft = computed(() => `${(guideX.value / W) * 100}%`);
const hoverTrain = computed(() => (hoverIndex.value === null ? undefined : props.train[hoverIndex.value]));
const hoverVal = computed(() => (hoverIndex.value === null ? undefined : props.val[hoverIndex.value]));
</script>

<template>
  <section class="tm-card tm-chart-card">
    <div class="tm-chart-head">
      <div>
        <h3>{{ title }}</h3>
        <span class="tm-chart-sub">{{ subtitle }} · 横轴 epoch</span>
      </div>
      <div class="tm-legend" :data-chart="chartKey">
        <button class="tm-legend-item" :class="showTrainOnly ? '' : 'active'" data-series="train" @click="emit('toggle', 'train')">
          <i class="dot train"></i>{{ labelFor(chartKey, "train") }}
        </button>
        <button class="tm-legend-item" :class="showTrainOnly ? 'muted' : 'active'" data-series="val" @click="emit('toggle', 'val')">
          <i class="dot val"></i>{{ labelFor(chartKey, "val") }}
        </button>
      </div>
    </div>
    <div class="tm-chart-wrap">
      <svg
        class="tm-chart"
        :id="`tm-chart-${chartKey}`"
        viewBox="0 0 520 260"
        preserveAspectRatio="none"
        @mousemove="handleMouseMove"
        @mouseleave="handleMouseLeave"
      >
        <template v-for="(grid, index) in gridLines" :key="`grid-${index}`">
          <line :x1="pad.left" :y1="grid.y" :x2="W - pad.right" :y2="grid.y" class="tm-grid" />
          <text :x="pad.left - 8" :y="grid.y + 3" class="tm-axis-label" text-anchor="end">{{ grid.label }}</text>
        </template>

        <text
          v-for="(label, index) in xLabels"
          :key="`x-${index}`"
          :x="label.x"
          :y="H - pad.bottom + 18"
          class="tm-axis-label"
          text-anchor="middle"
        >{{ label.label }}</text>

        <rect
          v-if="placeholder"
          :x="placeholder.x"
          :y="placeholder.y"
          :width="placeholder.width"
          :height="placeholder.height"
          class="tm-placeholder"
        />

        <template v-for="series in renderSeries" :key="series.cls">
          <polyline v-if="series.pts.length >= 2" :points="series.pointsAttr" :class="`tm-series ${series.cls}`" />
          <circle
            v-for="(pt, index) in series.pts"
            :key="`pt-${index}`"
            :cx="pt.x"
            :cy="pt.y"
            r="3"
            :class="`tm-point ${series.cls}`"
          />
        </template>

        <line :x1="guideX" y1="16" :x2="guideX" y2="230" class="tm-guide" :class="{ hidden: hoverIndex === null }" />
      </svg>
      <div class="tm-tooltip" :class="{ hidden: hoverIndex === null }" :id="`tm-tooltip-${chartKey}`" :style="{ left: tooltipLeft }">
        <div class="tm-tt-title">Epoch {{ (hoverIndex ?? 0) + 1 }}</div>
        <div><i class="dot train"></i>{{ labelFor(chartKey, "train") }}: <b>{{ fmt(chartKey, hoverTrain) }}</b></div>
        <div v-if="!showTrainOnly"><i class="dot val"></i>{{ labelFor(chartKey, "val") }}: <b>{{ fmt(chartKey, hoverVal) }}</b></div>
      </div>
    </div>
  </section>
</template>
