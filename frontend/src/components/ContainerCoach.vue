<script setup lang="ts">
// 容器聚光引导：拖入容器后自动开始，像新手四步引导一样逐步高亮真实元素，
// 并跟随用户的实际操作（双击进入子画板 / 返回主画布）自动前进。
// 勾选"不再自动播放"后持久化关闭（见 store.stopContainerCoach）。
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { activeCanvas, containerCoach, stopContainerCoach } from "../store";

interface CoachStep {
  title: string;
  text: string;
  // 需要等待用户真实操作才能前进的步骤：enter=双击进入容器；exit=返回主画布
  waitFor?: "enter" | "exit";
  waitHint?: string;
}

const steps: CoachStep[] = [
  {
    title: "① 双击这个容器",
    text: "容器能把一段网络打包成一个节点。现在双击它，进入容器内部的子画板。",
    waitFor: "enter",
    waitHint: "双击容器后自动继续",
  },
  {
    title: "② 这是输入端口",
    text: "子画板里已备好一个 Input——它就是容器对外的一个输入端口。想要多个入口，就再拖一个 Input 进来。",
  },
  {
    title: "③ 这是输出端口",
    text: "每个 Output 就是一个出口。现在单击或拖入需要的层（比如 Conv2D），把 Input → 层 → Output 连起来。",
  },
  {
    title: "④ 搭好后返回主画布",
    text: "点这个按钮回到主画布，容器的上下沿就会出现对应的输入 / 输出端口点。",
    waitFor: "exit",
    waitHint: "点「返回上一层」后自动继续",
  },
  {
    title: "⑤ 把连线接到端口上",
    text: "外部连线接到容器上下沿的端口点：每个端口只接一路，要合并多条分支先经过 Merge。选中容器还能在右侧「存为可复用」。",
  },
];

const index = ref(0);
const rect = ref<{ top: number; left: number; width: number; height: number } | null>(null);
const dontAutoPlay = ref(false);
const current = computed(() => steps[index.value]!);
const isLast = computed(() => index.value >= steps.length - 1);

// 正在编辑容器子画板（editStack 非空）
const editing = computed(() => activeCanvas().editStack.length > 0);

// 跟随真实操作前进：进入容器 → 第②步；中途返回主画布 → 直接跳到最后一步
watch(editing, now => {
  if (now && index.value === 0) {
    index.value = 1;
    void nextTick(measure);
  } else if (!now && index.value >= 1 && index.value <= 3) {
    index.value = 4;
    void nextTick(measure);
  }
});

// 每步的聚光目标（画布节点会平移/缩放，selector 动态求值 + 定时重测）
function currentSelector(): string | null {
  switch (index.value) {
    case 0:
    case 4:
      return `#node-${containerCoach.nodeId}`;
    case 1: {
      const node = activeCanvas().nodes.find(n => n.type === "Input");
      return node ? `#node-${node.id}` : null;
    }
    case 2: {
      const node = activeCanvas().nodes.find(n => n.type === "Output");
      return node ? `#node-${node.id}` : null;
    }
    case 3:
      return ".editor-back";
  }
  return null;
}

function measure() {
  // 主画布步骤中容器节点被删除 → 静默结束引导
  if ((index.value === 0 || index.value === 4) && !editing.value) {
    const exists = activeCanvas().nodes.some(n => n.id === containerCoach.nodeId);
    if (!exists) {
      stopContainerCoach(false);
      return;
    }
  }
  const selector = currentSelector();
  const el = selector ? document.querySelector<HTMLElement>(selector) : null;
  if (!el) {
    rect.value = null;
    return;
  }
  const r = el.getBoundingClientRect();
  rect.value = { top: r.top, left: r.left, width: r.width, height: r.height };
}

function next() {
  if (isLast.value) {
    stopContainerCoach(dontAutoPlay.value);
    return;
  }
  index.value += 1;
  void nextTick(measure);
}

function skip() {
  stopContainerCoach(dontAutoPlay.value);
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
  // 画布节点随拖拽/平移/缩放移动，聚光孔需持续跟随
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
      <span class="coach-idx">容器引导 · {{ index + 1 }} / {{ steps.length }}</span>
      <h3>{{ current.title }}</h3>
      <p>{{ current.text }}</p>
      <div class="coach-actions">
        <button type="button" class="coach-skip" @click="skip">跳过引导</button>
        <span v-if="current.waitFor" class="coach-wait">
          <iconify-icon icon="mdi:gesture-double-tap" class="coach-wait-icon"></iconify-icon>
          {{ current.waitHint }}
        </span>
        <button v-else type="button" class="coach-next" @click="next">
          {{ isLast ? "完成" : "下一步" }}
          <iconify-icon v-if="!isLast" icon="mdi:arrow-right"></iconify-icon>
        </button>
      </div>
      <label class="coach-mute">
        <input type="checkbox" v-model="dontAutoPlay">
        不再自动播放容器引导
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
  box-shadow: 0 0 0 9999px rgba(15, 30, 55, 0.5), 0 0 0 4px rgba(37, 160, 240, 0.6);
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
  color: #0d9488;
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
  color: #0d9488;
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
  background: linear-gradient(135deg, #14b8a6, #0d9488);
  box-shadow: 0 8px 18px rgba(13, 148, 136, 0.32);
  font-size: 13.5px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.coach-next:hover { transform: translateY(-1px); box-shadow: 0 11px 22px rgba(13, 148, 136, 0.4); }
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
.coach-mute input { width: 13px; height: 13px; accent-color: #0d9488; cursor: pointer; }
</style>
