<script setup lang="ts">
import { computed } from "vue";
// AI 助手吉祥物：我的世界方块小鸡（带黑色描边，白鸡不融进白底）。
// live=true：常驻原地踏步走。greet=true（气泡出现时）：单翅挥手打招呼。
// 二者独立：踏步一直进行，招手只在气泡冒出时触发。size 控制大小、描边随之缩放。
const props = withDefaults(defineProps<{ size?: number; live?: boolean; greet?: boolean }>(), {
  size: 64,
  live: false,
  greet: false,
});

// 整体黑色描边（4 向 drop-shadow 勾出轮廓，随尺寸变粗，动作时跟随剪影）
const outline = computed(() => {
  const w = Math.max(1, Math.round(props.size / 55));
  const c = "#232323";
  return `drop-shadow(${w}px 0 0 ${c}) drop-shadow(-${w}px 0 0 ${c}) drop-shadow(0 ${w}px 0 ${c}) drop-shadow(0 -${w}px 0 ${c})`;
});
</script>

<template>
  <svg
    class="pet-mascot"
    :class="{ 'pet-live': live, 'pet-greet': greet }"
    :style="{ filter: outline }"
    :width="size"
    :height="size"
    viewBox="0 0 64 64"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    shape-rendering="crispEdges"
    aria-hidden="true"
  >
    <!-- 落影（不参与跳动） -->
    <ellipse class="pet-shadow" cx="32" cy="58" rx="15" ry="2.6" fill="#3a2a1a" opacity="0.14" />

    <g class="pet-body">
      <!-- 翅膀（在身体下层，可煽动） -->
      <g class="pet-wing pet-wing-l">
        <rect x="11" y="33" width="6" height="10" fill="#f7f7f7" />
        <rect x="11" y="39" width="6" height="4" fill="#dcdcdc" />
      </g>
      <g class="pet-wing pet-wing-r">
        <rect x="47" y="33" width="6" height="10" fill="#f7f7f7" />
        <rect x="47" y="39" width="6" height="4" fill="#dcdcdc" />
      </g>

      <!-- 鸡冠 -->
      <rect x="26" y="4" width="4" height="4" fill="#d63b2f" />
      <rect x="34" y="4" width="4" height="4" fill="#d63b2f" />
      <rect x="24" y="8" width="16" height="4" fill="#d63b2f" />
      <!-- 头 -->
      <rect x="20" y="12" width="24" height="20" fill="#f7f7f7" />
      <rect x="20" y="12" width="24" height="3" fill="#ffffff" />
      <!-- 眼睛 -->
      <rect x="24" y="17" width="4" height="7" fill="#241c1c" />
      <rect x="36" y="17" width="4" height="7" fill="#241c1c" />
      <rect x="24" y="17" width="4" height="2" fill="#6b5b5b" />
      <rect x="36" y="17" width="4" height="2" fill="#6b5b5b" />
      <!-- 喙 -->
      <rect x="28" y="24" width="8" height="4" fill="#f6b03a" />
      <rect x="28" y="28" width="8" height="2" fill="#e0871a" />
      <!-- 肉垂 -->
      <rect x="30" y="30" width="4" height="4" fill="#d63b2f" />
      <!-- 身体 -->
      <rect x="16" y="32" width="32" height="16" fill="#f7f7f7" />
      <rect x="16" y="32" width="32" height="2" fill="#ffffff" />

      <!-- 脚（原地踏步交替抬起） -->
      <g class="pet-leg pet-leg-l">
        <rect x="24" y="48" width="4" height="5" fill="#e8881a" />
        <rect x="21" y="53" width="10" height="2" fill="#e8881a" />
      </g>
      <g class="pet-leg pet-leg-r">
        <rect x="36" y="48" width="4" height="5" fill="#e8881a" />
        <rect x="33" y="53" width="10" height="2" fill="#e8881a" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.pet-mascot { display: block; overflow: visible; }

/* —— 常驻：原地踏步（交替抬腿）+ 轻微走动起伏 —— */
.pet-live .pet-body { animation: petWalkBob 0.5s ease-in-out infinite; }
.pet-live .pet-leg-l {
  transform-box: fill-box;
  transform-origin: top center;
  animation: petStep 0.5s ease-in-out infinite;
}
.pet-live .pet-leg-r {
  transform-box: fill-box;
  transform-origin: top center;
  animation: petStep 0.5s ease-in-out infinite;
  animation-delay: 0.25s;
}
/* —— 招手：仅气泡出现时，单翅（右翅）向上挥两下 —— */
.pet-greet .pet-wing-r {
  transform-box: fill-box;
  transform-origin: left top;
  animation: petWave 1s ease-in-out 1;
}

@keyframes petWalkBob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-1.2px); }
}
/* 单翅挥手：向上举起 → 来回摆两下 → 放下（负角度=向上举） */
@keyframes petWave {
  0% { transform: rotate(0deg); }
  18% { transform: rotate(-52deg); }
  38% { transform: rotate(-32deg); }
  58% { transform: rotate(-52deg); }
  78% { transform: rotate(-32deg); }
  100% { transform: rotate(0deg); }
}
@keyframes petStep {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
@media (prefers-reduced-motion: reduce) {
  .pet-live .pet-body,
  .pet-live .pet-leg-l,
  .pet-live .pet-leg-r,
  .pet-greet .pet-wing-r { animation: none; }
}
</style>
