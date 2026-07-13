<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { fetchMyProjects } from "../actions";
import { auth, handleLogout } from "../auth";
import type { ProjectMeta } from "../types";

const emit = defineEmits<{
  enterWorkspace: [];
  createProject: [];
  browseTemplates: [];
  openProjects: [];
  openProject: [project: ProjectMeta];
}>();

const recentProjects = ref<ProjectMeta[]>([]);
const loadingProjects = ref(false);

const displayName = computed(() => auth.user?.username || auth.user?.email?.split("@")[0] || "用户");
const greeting = computed(() => {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 11) return "上午好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
});

onMounted(async () => {
  loadingProjects.value = true;
  try {
    const projects = await fetchMyProjects();
    recentProjects.value = [...projects]
      .sort((a, b) => Date.parse(b.updated_at || "") - Date.parse(a.updated_at || ""))
      .slice(0, 2);
  } catch {
    recentProjects.value = [];
  } finally {
    loadingProjects.value = false;
  }
});

function formatTime(iso?: string) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function projectType(project: ProjectMeta, index: number) {
  const name = project.name.toLowerCase();
  if (name.includes("图像") || name.includes("cnn") || name.includes("resnet")) return "image";
  if (name.includes("预测") || name.includes("回归") || name.includes("股票")) return "chart";
  return index % 2 === 0 ? "image" : "chart";
}
</script>

<template>
  <div class="mw-home-page">
    <header class="mw-home-header">
      <div class="mw-brand">
        <span class="mw-brand-mark"><iconify-icon icon="mdi:brain"></iconify-icon></span>
        <span class="mw-brand-copy">
          <strong>模型工坊</strong>
          <small>深度学习可视化搭建平台</small>
        </span>
      </div>

      <nav class="mw-nav" aria-label="首页导航">
        <button class="mw-nav-item active" type="button">
          <iconify-icon icon="mdi:home-variant"></iconify-icon>
          首页
        </button>
        <button class="mw-nav-item" type="button" @click="emit('browseTemplates')">
          <iconify-icon icon="mdi:cube-outline"></iconify-icon>
          模板库
        </button>
        <button class="mw-nav-item" type="button" @click="emit('openProjects')">
          <iconify-icon icon="mdi:account-outline"></iconify-icon>
          我的项目
        </button>
      </nav>

      <div class="mw-header-actions">
        <button class="mw-notice" type="button" title="暂无新通知">
          <iconify-icon icon="mdi:bell-outline"></iconify-icon>
        </button>
        <button class="mw-enter-button" type="button" @click="emit('enterWorkspace')">
          进入工作台
          <iconify-icon icon="mdi:chevron-right"></iconify-icon>
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

    <main class="mw-home-main">
      <section class="mw-hero">
        <div class="mw-hero-copy">
          <h1>{{ greeting }}，{{ displayName }}！今天想做点什么？</h1>
          <p>选择一种方式进入搭建流程，第一次使用推荐从模板开始。</p>
        </div>

        <div class="mw-hero-art" aria-hidden="true">
          <span class="mw-art-orbit orbit-a"></span>
          <span class="mw-art-orbit orbit-b"></span>
          <div class="mw-art-board">
            <span class="mw-art-card card-a"><iconify-icon icon="mdi:database-outline"></iconify-icon></span>
            <span class="mw-art-card card-b"><iconify-icon icon="mdi:cube-outline"></iconify-icon></span>
            <span class="mw-art-card card-c"><iconify-icon icon="mdi:chart-line"></iconify-icon></span>
            <span class="mw-art-card card-d"><iconify-icon icon="mdi:code-tags"></iconify-icon></span>
            <span class="mw-art-dot dot-a"></span>
            <span class="mw-art-dot dot-b"></span>
            <span class="mw-art-dot dot-c"></span>
            <span class="mw-art-line line-a"></span>
            <span class="mw-art-line line-b"></span>
          </div>
        </div>
      </section>

      <section class="mw-entry-grid" aria-label="开始方式">
        <article class="mw-entry-card blue">
          <span class="mw-entry-icon"><iconify-icon icon="mdi:plus"></iconify-icon></span>
          <div>
            <h2>从零开始创建</h2>
            <p>自由搭建网络结构，探索更多可能</p>
            <button type="button" @click="emit('createProject')">
              新建空白项目
              <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            </button>
          </div>
        </article>

        <article class="mw-entry-card green">
          <span class="mw-entry-icon"><iconify-icon icon="mdi:layers-triple"></iconify-icon></span>
          <div>
            <h2>从模板开始</h2>
            <p>使用优秀模板，快速构建经典模型</p>
            <button type="button" @click="emit('browseTemplates')">
              浏览模板库
              <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            </button>
          </div>
        </article>

        <article class="mw-entry-card purple">
          <span class="mw-entry-icon"><iconify-icon icon="mdi:folder-open-outline"></iconify-icon></span>
          <div>
            <h2>打开已有项目</h2>
            <p>继续上次的工作，快速进入状态</p>
            <button type="button" @click="emit('openProjects')">
              打开项目
              <iconify-icon icon="mdi:chevron-right"></iconify-icon>
            </button>
          </div>
        </article>
      </section>

      <section class="mw-dashboard-grid">
        <div class="mw-left-stack">
          <article class="mw-panel mw-guide-panel">
            <header class="mw-panel-title">
              <span><iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon></span>
              <h2>新手快速上手指南</h2>
            </header>

            <div class="mw-guide-steps">
              <div class="mw-guide-step">
                <span class="mw-step-icon blue"><iconify-icon icon="mdi:target"></iconify-icon></span>
                <strong><b>1</b> 选择任务</strong>
                <small>选择合适的任务类型，如图像分类、回归等</small>
              </div>
              <span class="mw-guide-arrow"><iconify-icon icon="mdi:arrow-right-thin"></iconify-icon></span>
              <div class="mw-guide-step">
                <span class="mw-step-icon green"><iconify-icon icon="mdi:cube-outline"></iconify-icon></span>
                <strong><b>2</b> 搭建模型</strong>
                <small>拖拽组件搭建网络结构，可视化连接各层</small>
              </div>
              <span class="mw-guide-arrow"><iconify-icon icon="mdi:arrow-right-thin"></iconify-icon></span>
              <div class="mw-guide-step">
                <span class="mw-step-icon amber"><iconify-icon icon="mdi:shield-check-outline"></iconify-icon></span>
                <strong><b>3</b> 检查结构</strong>
                <small>检查网络结构与参数，确保模型正确无误</small>
              </div>
              <span class="mw-guide-arrow"><iconify-icon icon="mdi:arrow-right-thin"></iconify-icon></span>
              <div class="mw-guide-step">
                <span class="mw-step-icon cyan"><iconify-icon icon="mdi:play"></iconify-icon></span>
                <strong><b>4</b> 开始训练</strong>
                <small>配置训练参数，启动训练并查看指标</small>
              </div>
            </div>
          </article>

          <article class="mw-panel mw-recent-panel">
            <header class="mw-panel-title mw-recent-title">
              <span><iconify-icon icon="mdi:clock-outline"></iconify-icon></span>
              <h2>最近项目</h2>
              <button type="button" @click="emit('openProjects')">
                查看全部项目
                <iconify-icon icon="mdi:chevron-right"></iconify-icon>
              </button>
            </header>

            <div v-if="loadingProjects" class="mw-recent-empty">
              <iconify-icon class="spin" icon="mdi:loading"></iconify-icon>
              正在读取最近项目...
            </div>

            <div v-else-if="recentProjects.length === 0" class="mw-recent-empty">
              <iconify-icon icon="mdi:folder-plus-outline"></iconify-icon>
              <span><strong>还没有保存过项目</strong><small>进入工作台完成模型后即可保存</small></span>
            </div>

            <div v-else class="mw-recent-list">
              <button
                v-for="(project, index) in recentProjects"
                :key="project.id"
                class="mw-project-card"
                type="button"
                @click="emit('openProject', project)"
              >
                <span class="mw-project-preview" :class="projectType(project, index)">
                  <iconify-icon :icon="projectType(project, index) === 'image' ? 'mdi:image-outline' : 'mdi:chart-line'"></iconify-icon>
                </span>
                <span class="mw-project-copy">
                  <strong>{{ project.name }}</strong>
                  <em>{{ projectType(project, index) === 'image' ? '图像分类' : '时间序列' }}</em>
                  <small>更新于 {{ formatTime(project.updated_at) }}</small>
                </span>
                <iconify-icon class="mw-project-more" icon="mdi:dots-vertical"></iconify-icon>
              </button>
            </div>
          </article>
        </div>

        <article class="mw-panel mw-preview-panel">
          <header class="mw-preview-title">
            <div>
              <span><iconify-icon icon="mdi:vector-polyline"></iconify-icon></span>
              <h2>快速预览：可视化搭建流程</h2>
            </div>
            <div class="mw-preview-tools" aria-hidden="true">
              <span><iconify-icon icon="mdi:fit-to-screen-outline"></iconify-icon></span>
              <span class="zoom">100%</span>
              <span><iconify-icon icon="mdi:undo-variant"></iconify-icon></span>
              <span><iconify-icon icon="mdi:redo-variant"></iconify-icon></span>
            </div>
          </header>

          <div class="mw-preview-workspace">
            <aside class="mw-preview-sidebar">
              <strong>组件库</strong>
              <div class="mw-preview-search"><iconify-icon icon="mdi:magnify"></iconify-icon> 搜索组件</div>
              <small>基础组件</small>
              <span><i class="cyan"></i>Conv2D</span>
              <span><i class="green"></i>Linear</span>
              <span><i class="purple"></i>ReLU</span>
              <span><i class="blue"></i>MaxPool2d</span>
              <small>工具组件</small>
              <span><i class="orange"></i>Dropout</span>
              <span><i class="gray"></i>Flatten</span>
            </aside>

            <div class="mw-preview-canvas">
              <svg class="mw-preview-links" viewBox="0 0 620 320" preserveAspectRatio="none" aria-hidden="true">
                <path d="M96 76 C132 76 132 76 164 76" />
                <path d="M252 76 C284 76 284 76 320 76" />
                <path d="M406 76 C446 76 442 118 488 118" />
                <path d="M532 148 C532 205 480 210 420 210" />
                <path d="M356 232 C330 232 312 232 286 232" />
                <path d="M222 232 C196 232 180 232 150 232" />
              </svg>

              <div class="mw-node input"><b>INPUT</b><strong>输入层</strong><small>[3, 224, 224]</small></div>
              <div class="mw-node conv"><b>Conv2D</b><strong>卷积层</strong><small>64, 3×3, s=1</small></div>
              <div class="mw-node relu"><b>ReLU</b><strong>激活层</strong></div>
              <div class="mw-node pool"><b>MaxPool2d</b><strong>最大池化层</strong><small>2×2, s=2</small></div>
              <div class="mw-node flatten"><b>Flatten</b><strong>展平层</strong></div>
              <div class="mw-node linear"><b>Linear</b><strong>全连接层</strong><small>128</small></div>
              <div class="mw-node output"><b>OUTPUT</b><strong>输出层</strong><small>10</small></div>
            </div>
          </div>

        </article>
      </section>
    </main>

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
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
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
.mw-user-chip,
.mw-panel-title,
.mw-preview-title > div {
  display: flex;
  align-items: center;
}

.mw-brand { width: fit-content; gap: 12px; }
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

.mw-nav { height: 100%; gap: 10px; }
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
.mw-nav-item.active { color: #118fe7; border-bottom-color: #1ca2eb; }

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

.mw-home-main {
  width: min(1390px, calc(100% - 64px));
  margin: 0 auto;
  flex: 1;
}

.mw-hero {
  min-height: 190px;
  margin-inline: calc((100vw - min(1390px, calc(100vw - 64px))) / -2);
  padding: 42px max(72px, calc((100vw - 1390px) / 2 + 32px)) 66px;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 83% 12%, rgba(76,164,242,.13), transparent 22%),
    linear-gradient(155deg,#fbfdff 0%,#f2f8ff 54%,#e9f5ff 100%);
}
.mw-hero::before,
.mw-hero::after {
  content: "";
  position: absolute;
  border-radius: 50%;
}
.mw-hero::before {
  width: 520px;
  height: 230px;
  right: -150px;
  bottom: -120px;
  background: rgba(127,196,247,.13);
  transform: rotate(-8deg);
}
.mw-hero::after {
  width: 820px;
  height: 300px;
  left: -230px;
  bottom: -225px;
  background: rgba(255,255,255,.7);
}
.mw-hero-copy { position: relative; z-index: 2; max-width: 720px; }
.mw-hero-copy h1 { margin: 0; font-size: 39px; line-height: 1.18; letter-spacing: -.035em; }
.mw-hero-copy p { margin: 12px 0 0; color: #667a98; font-size: 15px; }

.mw-hero-art {
  width: 390px;
  height: 155px;
  position: absolute;
  top: 17px;
  right: max(72px, calc((100vw - 1390px) / 2 + 24px));
  opacity: .82;
  transform: rotate(-3deg);
}
.mw-art-board {
  width: 226px;
  height: 128px;
  position: absolute;
  top: 15px;
  right: 48px;
  border: 1px solid rgba(111,177,231,.32);
  border-radius: 24px;
  background: linear-gradient(145deg,rgba(255,255,255,.9),rgba(213,236,255,.66));
  box-shadow: 0 24px 42px rgba(69,132,191,.12);
  transform: perspective(700px) rotateX(58deg) rotateZ(-18deg);
}
.mw-art-board::before {
  content: "";
  position: absolute;
  inset: 13px;
  border-radius: 18px;
  background-image: radial-gradient(#8fc7ee 1px,transparent 1px);
  background-size: 16px 16px;
  opacity: .42;
}
.mw-art-card {
  width: 36px;
  height: 36px;
  position: absolute;
  z-index: 2;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #178fdf;
  background: rgba(255,255,255,.95);
  box-shadow: 0 7px 14px rgba(31,123,184,.14);
  font-size: 18px;
}
.card-a { left: 23px; top: 23px; }
.card-b { left: 91px; top: 66px; }
.card-c { right: 24px; top: 29px; }
.card-d { right: 46px; bottom: 13px; }
.mw-art-dot { width: 13px; height: 13px; position: absolute; border-radius: 5px; background: #159de9; }
.dot-a { left: 77px; top: 41px; }
.dot-b { left: 132px; top: 41px; }
.dot-c { left: 133px; top: 86px; }
.mw-art-line { height: 2px; position: absolute; background: #69b7eb; transform-origin: left center; }
.line-a { width: 57px; left: 83px; top: 47px; }
.line-b { width: 54px; left: 135px; top: 47px; transform: rotate(48deg); }
.mw-art-orbit { position: absolute; border: 1px dashed rgba(48,154,226,.4); border-radius: 50%; }
.orbit-a { width: 295px; height: 95px; right: 0; top: 30px; transform: rotate(-13deg); }
.orbit-b { width: 205px; height: 72px; right: 72px; top: 43px; transform: rotate(25deg); }

.mw-entry-grid {
  margin-top: -55px;
  position: relative;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(3,minmax(0,1fr));
  gap: 16px;
}
.mw-entry-card {
  min-height: 154px;
  padding: 20px 24px;
  display: flex;
  align-items: flex-start;
  gap: 18px;
  border: 1px solid #dfe8f3;
  border-radius: 17px;
  background: rgba(255,255,255,.985);
  box-shadow: 0 13px 28px rgba(39,75,116,.075);
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.mw-entry-card:hover { transform: translateY(-4px); box-shadow: 0 18px 35px rgba(39,75,116,.13); }
.mw-entry-card.blue:hover { border-color: #8fcafb; }
.mw-entry-card.green:hover { border-color: #73d8c3; }
.mw-entry-card.purple:hover { border-color: #b7a3fa; }
.mw-entry-icon {
  width: 60px;
  height: 60px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 16px;
  font-size: 29px;
}
.mw-entry-card.blue .mw-entry-icon { color: #138fdf; background: #e6f5ff; }
.mw-entry-card.green .mw-entry-icon { color: #08aa90; background: #e5f9f4; }
.mw-entry-card.purple .mw-entry-icon { color: #7658e9; background: #eeeaff; }
.mw-entry-card > div { min-width: 0; flex: 1; }
.mw-entry-card h2 { margin: 4px 0 6px; font-size: 18px; }
.mw-entry-card p { margin: 0; color: #7889a2; font-size: 13px; line-height: 1.5; }
.mw-entry-card button {
  min-width: 165px;
  height: 39px;
  margin-top: 15px;
  padding: 0 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 0;
  border-radius: 8px;
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  box-shadow: 0 8px 16px rgba(55,111,174,.14);
}
.mw-entry-card.blue button { background: linear-gradient(135deg,#1ca4ee,#158dde); }
.mw-entry-card.green button { background: linear-gradient(135deg,#10baa0,#05a78d); }
.mw-entry-card.purple button { background: linear-gradient(135deg,#8067ee,#6d55df); }
.mw-entry-card button:hover { filter: brightness(.98); transform: translateY(-1px); }

.mw-dashboard-grid {
  height: 372px;
  margin-top: 15px;
  display: grid;
  grid-template-columns: minmax(0,.98fr) minmax(0,1.02fr);
  gap: 16px;
}
.mw-left-stack {
  min-width: 0;
  display: grid;
  grid-template-rows: minmax(0,1fr) 138px;
  gap: 14px;
}
.mw-panel {
  min-width: 0;
  border: 1px solid #dfe8f3;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 9px 24px rgba(39,75,116,.055);
}
.mw-guide-panel { min-height: 0; padding: 17px; }
.mw-recent-panel { min-height: 0; padding: 14px 17px; }
.mw-panel-title { gap: 9px; }
.mw-panel-title > span { color: #1596e8; font-size: 20px; }
.mw-panel-title h2 { margin: 0; font-size: 16px; }
.mw-recent-title button {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border: 0;
  color: #178fe4;
  background: transparent;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.mw-guide-steps { margin-top: 17px; display: flex; align-items: stretch; }
.mw-guide-step {
  min-width: 0;
  flex: 1;
  padding: 11px 7px 8px;
  text-align: center;
  border: 1px solid #e7edf5;
  border-radius: 13px;
  background: #fff;
}
.mw-step-icon {
  width: 34px;
  height: 34px;
  margin: 0 auto 8px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #fff;
  font-size: 18px;
}
.mw-step-icon.blue { background: #2a9de8; }
.mw-step-icon.green { background: #12b69a; }
.mw-step-icon.amber { background: #ffb316; }
.mw-step-icon.cyan { background: #21a6e8; }
.mw-guide-step strong { display: block; font-size: 12px; }
.mw-guide-step strong b { color: #1597e7; }
.mw-guide-step small { display: block; margin-top: 6px; color: #8594aa; font-size: 10px; line-height: 1.42; }
.mw-guide-arrow { width: 26px; flex: 0 0 26px; display: grid; place-items: center; color: #86b7df; font-size: 22px; }

.mw-recent-list { margin-top: 10px; display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 11px; }
.mw-project-card {
  min-width: 0;
  height: 76px;
  padding: 8px 9px;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid #e4eaf3;
  border-radius: 11px;
  color: #28364e;
  background: #fff;
  text-align: left;
  cursor: pointer;
}
.mw-project-card:hover { border-color: #a9cff1; background: #f8fbff; }
.mw-project-preview { width: 52px; height: 50px; flex: 0 0 auto; display: grid; place-items: center; border-radius: 9px; font-size: 24px; }
.mw-project-preview.image { color: #168f7a; background: linear-gradient(145deg,#e5f8f1,#d8efe7); }
.mw-project-preview.chart { color: #327fcf; background: linear-gradient(145deg,#e8f2ff,#ddeafe); }
.mw-project-copy { min-width: 0; flex: 1; }
.mw-project-copy strong,
.mw-project-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mw-project-copy strong { font-size: 12px; }
.mw-project-copy em {
  display: inline-block;
  margin-top: 3px;
  padding: 2px 6px;
  border-radius: 5px;
  color: #168f7a;
  background: #e7f8f2;
  font-size: 9px;
  font-style: normal;
}
.mw-project-preview.chart + .mw-project-copy em { color: #327fcf; background: #eaf3ff; }
.mw-project-copy small { margin-top: 3px; color: #91a0b3; font-size: 9px; }
.mw-project-more { color: #6f819b; }
.mw-recent-empty { height: 84px; display: flex; align-items: center; justify-content: center; gap: 9px; color: #8998ad; font-size: 12px; }
.mw-recent-empty > iconify-icon { font-size: 25px; }
.mw-recent-empty strong,
.mw-recent-empty small { display: block; }
.mw-recent-empty strong { color: #41536e; font-size: 12px; }
.mw-recent-empty small { margin-top: 3px; font-size: 10px; }

.mw-preview-panel {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.mw-preview-title {
  height: 48px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e7edf5;
}
.mw-preview-title > div:first-child { gap: 8px; }
.mw-preview-title > div:first-child > span { color: #178fdf; font-size: 18px; }
.mw-preview-title h2 { margin: 0; font-size: 15px; }
.mw-preview-tools { display: flex; align-items: center; gap: 6px; color: #7186a5; }
.mw-preview-tools span { min-width: 27px; height: 27px; display: grid; place-items: center; border: 1px solid #e4ebf4; border-radius: 8px; background: #fbfdff; font-size: 13px; }
.mw-preview-tools .zoom { min-width: 48px; font-size: 10px; }
.mw-preview-workspace { min-height: 0; flex: 1; display: grid; grid-template-columns: 132px 1fr; }
.mw-preview-sidebar { padding: 12px 9px; border-right: 1px solid #e6edf6; background: #f9fbfe; }
.mw-preview-sidebar strong { display: block; margin-bottom: 9px; font-size: 11px; }
.mw-preview-search { height: 26px; padding: 0 8px; display: flex; align-items: center; gap: 5px; border: 1px solid #e0e8f2; border-radius: 7px; color: #9aa8bb; background: #fff; font-size: 9px; }
.mw-preview-sidebar small { display: block; margin: 10px 0 4px; color: #8a9ab0; font-size: 8px; font-weight: 700; }
.mw-preview-sidebar > span { height: 23px; display: flex; align-items: center; gap: 6px; color: #52647f; font-size: 9px; }
.mw-preview-sidebar i { width: 14px; height: 14px; display: inline-block; border-radius: 5px; }
.mw-preview-sidebar i.cyan { background: #d9f7fa; }
.mw-preview-sidebar i.green { background: #dff8ef; }
.mw-preview-sidebar i.purple { background: #eee7ff; }
.mw-preview-sidebar i.blue { background: #e2edff; }
.mw-preview-sidebar i.orange { background: #fff0dc; }
.mw-preview-sidebar i.gray { background: #edf0f4; }
.mw-preview-canvas {
  min-height: 0;
  position: relative;
  overflow: hidden;
  background-color: #fbfdff;
  background-image: radial-gradient(#cfdced 1px,transparent 1px);
  background-size: 18px 18px;
}
.mw-preview-links { position: absolute; inset: 0; width: 100%; height: 100%; }
.mw-preview-links path { fill: none; stroke: #8ba7cc; stroke-width: 2.2; }
.mw-node {
  width: 78px;
  min-height: 54px;
  padding: 7px;
  position: absolute;
  z-index: 2;
  border: 1px solid #dce5f0;
  border-radius: 9px;
  background: rgba(255,255,255,.97);
  box-shadow: 0 7px 15px rgba(44,74,115,.08);
}
.mw-node b,
.mw-node strong,
.mw-node small { display: block; }
.mw-node b { margin-bottom: 4px; color: #367fbf; font-size: 8px; }
.mw-node strong { font-size: 9px; }
.mw-node small { margin-top: 4px; color: #8b99ad; font-size: 8px; }
.mw-node.input { left: 20px; top: 31px; }
.mw-node.conv { left: 150px; top: 31px; border-color: #9ee2d1; }
.mw-node.conv b { color: #129d82; }
.mw-node.relu { left: 292px; top: 31px; border-color: #d6c6ff; }
.mw-node.relu b { color: #7755d8; }
.mw-node.pool { right: 28px; top: 68px; border-color: #f5cc8b; }
.mw-node.pool b { color: #bf7b10; }
.mw-node.flatten { right: 178px; bottom: 27px; }
.mw-node.linear { left: 202px; bottom: 27px; }
.mw-node.output { left: 76px; bottom: 27px; border-color: #f4b1b8; }
.mw-node.output b { color: #d45361; }
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

@media (max-width: 960px) {
  .mw-home-main { width: min(100% - 30px, 900px); }
  .mw-hero { margin-inline: -15px; padding-inline: 28px; }
  .mw-entry-grid { grid-template-columns: 1fr; margin-top: -34px; }
  .mw-entry-card { min-height: 120px; }
  .mw-dashboard-grid { height: auto; grid-template-columns: 1fr; }
  .mw-left-stack { grid-template-rows: auto auto; }
  .mw-preview-panel { min-height: 360px; }
}

@media (max-width: 720px) {
  .mw-home-header { height: 62px; flex-basis: 62px; padding: 0 13px; }
  .mw-brand-copy small,
  .mw-notice,
  .mw-user-chip > span:not(.mw-avatar) { display: none; }
  .mw-enter-button { padding: 0 12px; }
  .mw-home-main { width: min(100% - 22px, 680px); }
  .mw-hero { min-height: 188px; padding: 34px 20px 58px; margin-inline: -11px; }
  .mw-hero-copy h1 { font-size: 32px; }
  .mw-hero-copy p { max-width: 330px; font-size: 14px; }
  .mw-hero-art { right: -150px; opacity: .2; }
  .mw-entry-card { padding: 17px; }
  .mw-recent-list { grid-template-columns: 1fr; }
  .mw-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
  .mw-guide-arrow { display: none; }
  .mw-preview-workspace { grid-template-columns: 100px 1fr; }
  .mw-node { transform: scale(.8); transform-origin: top left; }
  .mw-footer { flex-direction: column; gap: 6px; padding: 10px 16px; }
  .mw-footer nav { gap: 12px; }
}

@media (max-height: 820px) and (min-width: 961px) {
  .mw-home-header { height: 64px; flex-basis: 64px; }
  .mw-hero { min-height: 168px; padding-top: 32px; padding-bottom: 60px; }
  .mw-hero-copy h1 { font-size: 38px; }
  .mw-hero-art { top: 2px; transform: scale(.87) rotate(-3deg); transform-origin: center; }
  .mw-entry-card { min-height: 140px; padding-top: 17px; padding-bottom: 17px; }
  .mw-entry-icon { width: 54px; height: 54px; }
  .mw-entry-card button { height: 35px; margin-top: 10px; }
  .mw-dashboard-grid { height: 334px; }
  .mw-left-stack { grid-template-rows: minmax(0,1fr) 124px; gap: 12px; }
  .mw-guide-panel { padding: 14px; }
  .mw-guide-steps { margin-top: 12px; }
  .mw-guide-step { padding-top: 8px; }
  .mw-step-icon { width: 31px; height: 31px; margin-bottom: 6px; }
  .mw-recent-panel { padding: 12px 15px; }
  .mw-project-card { height: 66px; }
  .mw-project-preview { width: 46px; height: 44px; }
  .mw-preview-title { height: 44px; }
  .mw-footer { min-height: 36px; margin-top: 10px; }
}
</style>
