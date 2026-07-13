<script setup lang="ts">
import { computed } from "vue";
import { getCanvasViewportSize } from "../canvas";
import { activeCanvas, minimap } from "../store";

// 迷你地图：把整张模型图缩略到右上角，并画出当前视口框。
// 仅在移动 / 缩放 / 更新画布时短暂淡入（由 store.minimap.visible + pokeMinimap 控制）。

// 节点在迷你地图里用近似尺寸即可（缩略图无需精确）
const NODE_W = 224;
const NODE_H = 132;

// 各层颜色 → 缩略块填充色
const COLOR_FILL: Record<string, string> = {
  emerald: "#6ee7b7",
  rose: "#fda4af",
  blue: "#93c5fd",
  purple: "#d8b4fe",
  indigo: "#a5b4fc",
  cyan: "#67e8f9",
  amber: "#fcd34d",
  orange: "#fdba74",
  teal: "#5eead4",
};
function fillOf(color: string) {
  return COLOR_FILL[color] || "#c7d2e4";
}

const nodes = computed(() => activeCanvas().nodes);

const layout = computed(() => {
  const canvas = activeCanvas();
  const ns = nodes.value;
  const vp = getCanvasViewportSize();
  const zoom = canvas.zoom || 1;

  // 当前视口在画布坐标系里的矩形
  const viewport = {
    x: -canvas.panX / zoom,
    y: -canvas.panY / zoom,
    w: (vp.width || 800) / zoom,
    h: (vp.height || 600) / zoom,
  };

  // 包围盒：所有节点 + 视口
  let minX = viewport.x;
  let minY = viewport.y;
  let maxX = viewport.x + viewport.w;
  let maxY = viewport.y + viewport.h;
  for (const n of ns) {
    minX = Math.min(minX, n.x);
    minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + NODE_W);
    maxY = Math.max(maxY, n.y + NODE_H);
  }
  const pad = 80;
  minX -= pad;
  minY -= pad;
  maxX += pad;
  maxY += pad;

  return {
    viewBox: `${minX} ${minY} ${Math.max(1, maxX - minX)} ${Math.max(1, maxY - minY)}`,
    nodes: ns.map(n => ({ x: n.x, y: n.y, fill: fillOf(n.color) })),
    viewport,
  };
});
</script>

<template>
  <div class="canvas-minimap" :class="{ 'is-visible': minimap.visible && nodes.length > 0 }" aria-hidden="true">
    <svg :viewBox="layout.viewBox" preserveAspectRatio="xMidYMid meet">
      <rect
        v-for="(n, i) in layout.nodes"
        :key="i"
        :x="n.x"
        :y="n.y"
        :width="NODE_W"
        :height="NODE_H"
        :rx="20"
        :fill="n.fill"
        class="mm-node"
      />
      <rect
        class="mm-viewport"
        :x="layout.viewport.x"
        :y="layout.viewport.y"
        :width="layout.viewport.w"
        :height="layout.viewport.h"
        :rx="10"
        vector-effect="non-scaling-stroke"
      />
    </svg>
  </div>
</template>
