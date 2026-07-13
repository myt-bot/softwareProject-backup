<script setup lang="ts">
// 首页 / 模板库 / 我的项目 三个整页共用的外壳：顶部品牌导航 + 页脚。
// 通过 active 高亮当前页，navigate 事件交由 App 切换 currentPage。
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { auth, handleLogout } from "../auth";

// canReturn：用户已进过工作台时才显示“回到工作台”按钮（首次进入系统不显示）
const props = defineProps<{ active: "home" | "templates" | "projects"; canReturn?: boolean }>();
const emit = defineEmits<{
  navigate: [page: "home" | "templates" | "projects"];
  enterWorkspace: [];
}>();

// 顶部导航高亮下划线：测量当前激活项的位置，让下划线在切换时平滑左右滑动
const navEl = ref<HTMLElement>();
const underline = ref({ left: 0, width: 0, top: 0 });
const animated = ref(false);

function updateUnderline() {
  const nav = navEl.value;
  if (!nav) return;
  const activeBtn = nav.querySelector<HTMLElement>(".mw-nav-item.active");
  if (!activeBtn) {
    underline.value = { ...underline.value, width: 0 };
    return;
  }
  // 用相对 nav 的实际渲染位置计算，避免 offsetParent 歧义导致的偏移
  const navRect = nav.getBoundingClientRect();
  const btnRect = activeBtn.getBoundingClientRect();
  underline.value = {
    left: btnRect.left - navRect.left,
    width: btnRect.width,
    top: btnRect.bottom - navRect.top - 3,
  };
}

watch(() => props.active, () => nextTick(updateUnderline));

let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  nextTick(() => {
    updateUnderline();
    // 首帧不带动画，避免初始从最左滑入；随后开启过渡
    requestAnimationFrame(() => { animated.value = true; });
  });
  // 图标（iconify-icon 为异步渲染的 Web Component）/字体加载完会改变导航尺寸，
  // 用 ResizeObserver 自动重新测量，避免首次进入时下划线错位
  if (typeof ResizeObserver !== "undefined" && navEl.value) {
    resizeObserver = new ResizeObserver(() => updateUnderline());
    resizeObserver.observe(navEl.value);
  }
  window.addEventListener("resize", updateUnderline);
  document.fonts?.ready?.then(() => updateUnderline()).catch(() => {});
});
onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  window.removeEventListener("resize", updateUnderline);
});
</script>

<template>
  <div class="mw-home-page">
    <header class="mw-home-header">
      <div class="mw-brand" role="button" title="返回首页" @click="emit('navigate', 'home')">
        <span class="mw-brand-mark"><iconify-icon icon="mdi:brain"></iconify-icon></span>
        <span class="mw-brand-copy">
          <strong>模型工坊</strong>
          <small>深度学习可视化搭建平台</small>
        </span>
      </div>

      <nav ref="navEl" class="mw-nav" aria-label="首页导航">
        <button class="mw-nav-item" :class="{ active: active === 'home' }" type="button" @click="emit('navigate', 'home')">
          <iconify-icon icon="mdi:home-variant"></iconify-icon>
          首页
        </button>
        <button class="mw-nav-item" :class="{ active: active === 'templates' }" type="button" @click="emit('navigate', 'templates')">
          <iconify-icon icon="mdi:cube-outline"></iconify-icon>
          模板库
        </button>
        <button class="mw-nav-item" :class="{ active: active === 'projects' }" type="button" @click="emit('navigate', 'projects')">
          <iconify-icon icon="mdi:account-outline"></iconify-icon>
          我的项目
        </button>
        <span
          class="mw-nav-underline"
          :class="{ 'is-animated': animated }"
          :style="{ width: `${underline.width}px`, top: `${underline.top}px`, transform: `translateX(${underline.left}px)` }"
        ></span>
      </nav>

      <div class="mw-header-actions">
        <button class="mw-notice" type="button" title="暂无新通知">
          <iconify-icon icon="mdi:bell-outline"></iconify-icon>
        </button>
        <button v-if="canReturn" class="mw-enter-button" type="button" title="回到工作台" @click="emit('enterWorkspace')">
          回到工作台
          <iconify-icon icon="mdi:arrow-right"></iconify-icon>
        </button>
        <div class="mw-user-chip" :title="auth.user?.email || ''">
          <span class="mw-avatar"><iconify-icon icon="mdi:account"></iconify-icon></span>
          <span>{{ auth.user?.username || auth.user?.email }}</span>
          <button class="mw-logout" type="button" title="退出登录" @click="handleLogout">
            <iconify-icon icon="mdi:logout-variant"></iconify-icon>
          </button>
        </div>
      </div>
    </header>

    <slot />

    <footer class="mw-footer">
      <span>© 2026 模型工坊 · 深度学习可视化搭建平台</span>
      <nav aria-label="页脚信息">
        <span>帮助文档</span>
        <span>社区支持</span>
        <span>意见反馈</span>
        <span>关于我们</span>
      </nav>
    </footer>
  </div>
</template>

<style scoped>
.mw-home-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: #172541;
  background: #f7faff;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

button { font: inherit; }

.mw-home-header {
  height: 70px;
  flex: 0 0 70px;
  padding: 0 30px;
  display: grid;
  grid-template-columns: minmax(250px, 1fr) auto minmax(340px, 1fr);
  align-items: center;
  gap: 18px;
  position: relative;
  z-index: 20;
  background: rgba(255,255,255,.98);
  border-bottom: 1px solid #e6edf7;
  box-shadow: 0 4px 18px rgba(34,65,108,.035);
}

.mw-brand,
.mw-nav,
.mw-nav-item,
.mw-header-actions,
.mw-enter-button,
.mw-user-chip {
  display: flex;
  align-items: center;
}

.mw-brand { width: fit-content; gap: 12px; cursor: pointer; }
.mw-brand-mark {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #fff;
  font-size: 24px;
  background: linear-gradient(145deg,#2b9cf0,#0bb7dc);
  box-shadow: 0 8px 20px rgba(20,158,226,.25);
}
.mw-brand-copy strong,
.mw-brand-copy small { display: block; }
.mw-brand-copy strong { font-size: 21px; letter-spacing: .01em; }
.mw-brand-copy small { margin-top: 3px; color: #8a9bb3; font-size: 12px; }

.mw-nav { height: 100%; gap: 10px; position: relative; }
.mw-nav-item {
  height: 52px;
  padding: 0 14px;
  gap: 7px;
  border: 0;
  border-bottom: 3px solid transparent;
  color: #53647e;
  background: transparent;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.mw-nav-item iconify-icon { font-size: 18px; }
.mw-nav-item:hover { color: #128ce5; }
.mw-nav-item.active { color: #118fe7; }

/* 滑动高亮下划线：位置由 JS 测量当前激活项得出，切换时平滑左右滑动 */
.mw-nav-underline {
  position: absolute;
  left: 0;
  height: 3px;
  border-radius: 3px;
  background: #1ca2eb;
  pointer-events: none;
}
.mw-nav-underline.is-animated {
  transition: transform 0.34s cubic-bezier(0.4, 0, 0.2, 1), width 0.34s cubic-bezier(0.4, 0, 0.2, 1);
}

.mw-header-actions { justify-content: flex-end; gap: 12px; }
.mw-notice,
.mw-logout {
  border: 0;
  color: #6f819d;
  background: transparent;
  cursor: pointer;
}
.mw-notice { width: 34px; height: 34px; display: grid; place-items: center; font-size: 19px; }
.mw-notice:hover { color: #138fe8; }
.mw-enter-button {
  height: 42px;
  padding: 0 19px;
  gap: 7px;
  border: 0;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg,#1aa2ed,#118ce3);
  box-shadow: 0 8px 18px rgba(19,148,229,.22);
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease;
}
.mw-enter-button:hover { transform: translateY(-1px); box-shadow: 0 11px 24px rgba(19,148,229,.28); }
.mw-user-chip {
  gap: 8px;
  padding: 4px 6px;
  border-radius: 22px;
  color: #33445f;
  background: #f4f7fc;
  font-size: 13px;
  font-weight: 700;
}
.mw-avatar {
  width: 31px;
  height: 31px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #7b91b3;
  background: #e5edf8;
  font-size: 18px;
}
.mw-logout { width: 28px; height: 28px; border-radius: 50%; }
.mw-logout:hover { color: #e85865; background: #fff0f2; }

.mw-footer {
  min-height: 42px;
  margin-top: 14px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 42px;
  border-top: 1px solid #e6edf5;
  color: #8090a6;
  background: #fff;
  font-size: 11px;
}
.mw-footer nav { display: flex; gap: 28px; }

@media (max-width: 1040px) {
  .mw-home-header { grid-template-columns: 1fr auto; }
  .mw-nav { display: none; }
  .mw-header-actions { justify-self: end; }
}

@media (max-width: 720px) {
  .mw-home-header { height: 62px; flex-basis: 62px; padding: 0 13px; }
  .mw-brand-copy small,
  .mw-notice,
  .mw-user-chip > span:not(.mw-avatar) { display: none; }
  .mw-enter-button { padding: 0 12px; }
  .mw-footer { flex-direction: column; gap: 6px; padding: 10px 16px; }
  .mw-footer nav { gap: 12px; }
}

@media (max-height: 820px) and (min-width: 961px) {
  .mw-home-header { height: 64px; flex-basis: 64px; }
  .mw-footer { min-height: 36px; margin-top: 10px; }
}
</style>
