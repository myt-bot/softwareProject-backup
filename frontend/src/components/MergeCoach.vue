<script setup lang="ts">
// Merge 聚光引导：拖入 Merge 后自动开始，逐步高亮真实元素，
// 并在用户真的选好合并模式后自动前进（与容器引导同款交互）。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { activeCanvas, mergeCoach, stopMergeCoach } from "../store";

interface CoachStep {
  title: string;
  text: string;
  // 需要等待用户真实操作才能前进：mode=在右侧面板选好合并模式
  waitFor?: "mode";
  waitHint?: string;
}

const steps: CoachStep[] = [
  {
    title: "① 这是 Merge：多路进、一路出",
    text: "它把两条或多条分支合并成一条：把每条分支的输出都连到它上面，再从 Merge 连往下一层。",
  },
  {
    title: "② 在右侧选择合并模式",
    text: "add = 逐元素相加（各分支形状需完全一致）；concat = 拼接；matmul = 矩阵乘法。点选其中一种。",
    waitFor: "mode",
    waitHint: "点选一种模式后自动继续",
  },
  {
    title: "③ 分支必须先经 Merge 合并",
    text: "普通层和输出端口只能接一路输入，多条分支要先在这里合并成一条再往下连。matmul 对顺序敏感：可在右侧点选 input 用 ⬅ / ➡ 调整先后。",
  },
];

const index = ref(0);
const rect = ref<{ top: number; left: number; width: number; height: number } | null>(null);
const dontAutoPlay = ref(false);
const current = computed(() => steps[index.value]!);
const isLast = computed(() => index.value >= steps.length - 1);

const mergeNode = computed(() => activeCanvas().nodes.find(n => n.id === mergeCoach.nodeId));

// 用户在右侧面板选好模式 → 自动进入下一步
const modeChosen = computed(() => {
  const merge = mergeNode.value?.params?.merge;
  return typeof merge === "string" && merge.length > 0;
});
watch(modeChosen, chosen => {
  if (chosen && index.value === 1) {
    index.value = 2;
    void nextTick(measure);
  }
});

// 每步聚光目标（带兜底：面板控件不在时退回高亮 Merge 节点本身）
function currentSelectors(): string[] {
  switch (index.value) {
    case 0:
    case 2:
      return [`#node-${mergeCoach.nodeId}`];
    case 1:
      return [".merge-mode-toggle", `#node-${mergeCoach.nodeId}`];
  }
  return [];
}

function measure() {
  // Merge 节点被删除 → 静默结束引导
  if (!mergeNode.value) {
    stopMergeCoach(false);
    return;
  }
  let el: HTMLElement | null = null;
  for (const selector of currentSelectors()) {
    el = document.querySelector<HTMLElement>(selector);
    if (el) break;
  }
  if (!el) {
    rect.value = null;
    return;
  }
  const r = el.getBoundingClientRect();
  rect.value = { top: r.top, left: r.left, width: r.width, height: r.height };
}

function next() {
  if (isLast.value) {
    stopMergeCoach(dontAutoPlay.value);
    return;
  }
  index.value += 1;
  void nextTick(measure);
}

function skip() {
  stopMergeCoach(dontAutoPlay.value);
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") skip();
}

const holeStyle = computed(() => {
  const r = rect.value;
  if (!r) return { display: "none" };
  const pad = 8;
  return {
    top: `${r.top - pad}px`,
    left: `${r.left - pad}px`,
    width: `${r.width + pad * 2}px`,
    height: `${r.height + pad * 2}px`,
  };
});

const TIP_W = 306;
const tipStyle = computed(() => {
  const r = rect.value;
  if (!r) {
    return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  }
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const spaceBelow = vh - (r.top + r.height);
  const placeBelow = spaceBelow > 230;
  const top = placeBelow ? r.top + r.height + 14 : Math.max(14, r.top - 14 - 200);
  let left = r.left + r.width / 2 - TIP_W / 2;
  left = Math.min(Math.max(14, left), vw - TIP_W - 14);
  return { top: `${top}px`, left: `${left}px` };
});

let measureTimer: ReturnType<typeof setInterval> | undefined;

onMounted(() => {
  void nextTick(measure);
  // 节点随拖拽/平移/缩放移动，聚光孔需持续跟随
  measureTimer = setInterval(measure, 280);
  window.addEventListener("resize", measure);
  window.addEventListener("scroll", measure, true);
  window.addEventListener("keydown", handleKeydown);
});
onBeforeUnmount(() => {
  if (measureTimer) clearInterval(measureTimer);
  window.removeEventListener("resize", measure);
  window.removeEventListener("scroll", measure, true);
  window.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <div class="coach-overlay">
    <div class="coach-hole" :style="holeStyle"></div>
    <div class="coach-tip" :style="tipStyle">
      <span class="coach-idx">Merge 引导 · {{ index + 1 }} / {{ steps.length }}</span>
      <h3>{{ current.title }}</h3>
      <p>{{ current.text }}</p>
      <div class="coach-actions">
        <button type="button" class="coach-skip" @click="skip">跳过引导</button>
        <span v-if="current.waitFor" class="coach-wait">
          <iconify-icon icon="mdi:cursor-default-click-outline" class="coach-wait-icon"></iconify-icon>
          {{ current.waitHint }}
        </span>
        <button v-else type="button" class="coach-next" @click="next">
          {{ isLast ? "完成" : "下一步" }}
          <iconify-icon v-if="!isLast" icon="mdi:arrow-right"></iconify-icon>
        </button>
      </div>
      <label class="coach-mute">
        <input type="checkbox" v-model="dontAutoPlay">
        不再自动播放 Merge 引导
      </label>
    </div>
  </div>
</template>

<style scoped>
.coach-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  pointer-events: none;
}

.coach-hole {
  position: fixed;
  border-radius: 12px;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 9999px rgba(15, 30, 55, 0.5), 0 0 0 4px rgba(8, 145, 178, 0.6);
  pointer-events: none;
  transition: top 0.22s ease, left 0.22s ease, width 0.22s ease, height 0.22s ease;
}

.coach-tip {
  position: fixed;
  width: 306px;
  padding: 17px 18px 12px;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 20px 48px rgba(15, 40, 80, 0.32);
  pointer-events: auto;
  animation: coach-tip-in 0.24s ease both;
}
@keyframes coach-tip-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.coach-idx {
  font-size: 12px;
  font-weight: 800;
  color: #0e7490;
  letter-spacing: 0.02em;
}
.coach-tip h3 { margin: 6px 0 6px; font-size: 16px; color: #17233b; }
.coach-tip p { margin: 0; font-size: 13px; line-height: 1.6; color: #56657f; }
.coach-actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.coach-skip {
  border: 0;
  background: transparent;
  color: #8394ab;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}
.coach-skip:hover { color: #5a6b84; }
/* 等待用户真实操作的步骤：显示动作提示而不是"下一步" */
.coach-wait {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 700;
  color: #0e7490;
}
.coach-wait-icon { font-size: 18px; animation: coach-wait-pulse 1.4s ease-in-out infinite; }
@keyframes coach-wait-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(1.15); }
}
.coach-next {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 20px;
  border: 0;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg, #22b8cf, #0e7490);
  box-shadow: 0 8px 18px rgba(14, 116, 144, 0.32);
  font-size: 13.5px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.coach-next:hover { transform: translateY(-1px); box-shadow: 0 11px 22px rgba(14, 116, 144, 0.4); }
.coach-next iconify-icon { font-size: 16px; }
.coach-mute {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid #eef2f8;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 600;
  color: #97a5ba;
  cursor: pointer;
  user-select: none;
}
.coach-mute input { width: 13px; height: 13px; accent-color: #0e7490; cursor: pointer; }
</style>
