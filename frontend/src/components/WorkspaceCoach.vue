<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

const emit = defineEmits<{ done: [] }>();

interface CoachStep {
  selector: string;
  title: string;
  text: string;
}

// 按四步流程依次聚光高亮真实元素，用视觉焦点替代文字引导
const steps: CoachStep[] = [
  {
    selector: '#layer-palette [data-layer-type="Input"]',
    title: "① 拖入第一个层",
    text: "按住这个高亮的 Input 层，拖到中间画布松手，就放下了模型的输入。",
  },
  {
    selector: "#btn-validate",
    title: "② 检查结构",
    text: "把层连好线后点这里，会自动检查每一层的尺寸是否匹配。",
  },
  {
    selector: "#btn-train-config",
    title: "③ 训练设置（可选）",
    text: "数据集、设备、训练轮次都收在这里，保持默认也能直接训练。",
  },
  {
    selector: "#btn-train",
    title: "④ 开始训练",
    text: "检查通过后点这里，模型会在你本机开始训练并显示指标。",
  },
];

const index = ref(0);
const rect = ref<{ top: number; left: number; width: number; height: number } | null>(null);
const current = computed(() => steps[index.value]!);
const isLast = computed(() => index.value >= steps.length - 1);

function measure() {
  const el = document.querySelector<HTMLElement>(current.value.selector);
  if (!el) {
    rect.value = null;
    return;
  }
  const r = el.getBoundingClientRect();
  rect.value = { top: r.top, left: r.left, width: r.width, height: r.height };
}

function next() {
  if (isLast.value) {
    emit("done");
    return;
  }
  index.value += 1;
  void nextTick(measure);
}

function skip() {
  emit("done");
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

const TIP_W = 300;
const tipStyle = computed(() => {
  const r = rect.value;
  if (!r) {
    return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  }
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const spaceBelow = vh - (r.top + r.height);
  const placeBelow = spaceBelow > 200;
  const top = placeBelow ? r.top + r.height + 14 : Math.max(14, r.top - 14 - 172);
  // 水平对齐目标中心，并夹在视口内
  let left = r.left + r.width / 2 - TIP_W / 2;
  left = Math.min(Math.max(14, left), vw - TIP_W - 14);
  return { top: `${top}px`, left: `${left}px` };
});

onMounted(() => {
  void nextTick(measure);
  window.addEventListener("resize", measure);
  window.addEventListener("scroll", measure, true);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", measure);
  window.removeEventListener("scroll", measure, true);
});
</script>

<template>
  <div class="coach-overlay" :class="{ 'no-target': !rect }">
    <div class="coach-hole" :style="holeStyle"></div>
    <div class="coach-tip" :style="tipStyle">
      <span class="coach-idx">{{ index + 1 }} / {{ steps.length }}</span>
      <h3>{{ current.title }}</h3>
      <p>{{ current.text }}</p>
      <div class="coach-actions">
        <button type="button" class="coach-skip" @click="skip">跳过引导</button>
        <button type="button" class="coach-next" @click="next">
          {{ isLast ? "完成" : "下一步" }}
          <iconify-icon v-if="!isLast" icon="mdi:arrow-right"></iconify-icon>
        </button>
      </div>
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
/* 无目标时整屏压暗（正常情况下由聚光孔的大投影压暗四周） */
.coach-overlay.no-target::before {
  content: "";
  position: absolute;
  inset: 0;
  background: rgba(15, 30, 55, 0.55);
}

.coach-hole {
  position: fixed;
  border-radius: 12px;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 9999px rgba(15, 30, 55, 0.55), 0 0 0 4px rgba(37, 160, 240, 0.6);
  pointer-events: none;
  transition: top 0.25s ease, left 0.25s ease, width 0.25s ease, height 0.25s ease;
}

.coach-tip {
  position: fixed;
  width: 300px;
  padding: 18px 18px 14px;
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
  color: #1f8ae0;
  letter-spacing: 0.02em;
}
.coach-tip h3 { margin: 6px 0 6px; font-size: 16px; color: #17233b; }
.coach-tip p { margin: 0; font-size: 13px; line-height: 1.6; color: #56657f; }
.coach-actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
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
.coach-next {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 20px;
  border: 0;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg, #1aa2ed, #1181e2);
  box-shadow: 0 8px 18px rgba(19, 132, 226, 0.32);
  font-size: 13.5px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.coach-next:hover { transform: translateY(-1px); box-shadow: 0 11px 22px rgba(19, 132, 226, 0.4); }
.coach-next iconify-icon { font-size: 16px; }
</style>
