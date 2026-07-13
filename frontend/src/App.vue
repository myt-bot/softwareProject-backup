<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { loadProjectTemplates, loadProjectToCanvas } from "./actions";
import { auth, initializeAuth, isLoggedIn } from "./auth";
import { addCanvas, cancelPendingConnection, hideConnectionMenu, hideNodeMenu, redoGraphChange, undoGraphChange } from "./canvas";
import { activeCanvas, closeHelpModal, confirmDialog, CONTAINER_ID_SEP, getCurrentModelGraph, initializeBeginnerGuide, resolveConfirm, store, ui, WORKSPACE_COACH_KEY } from "./store";
import ActionBar from "./components/ActionBar.vue";
import AgentModal from "./components/AgentModal.vue";
import AssistantPanel from "./components/AssistantPanel.vue";
import AuthPage from "./components/AuthPage.vue";
import CanvasBoard from "./components/CanvasBoard.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import ContextMenus from "./components/ContextMenus.vue";
import ExportModal from "./components/ExportModal.vue";
import GuideStrip from "./components/GuideStrip.vue";
import HelpModal from "./components/HelpModal.vue";
import HomeChrome from "./components/HomeChrome.vue";
import HomePage from "./components/HomePage.vue";
import InspectorPanel from "./components/InspectorPanel.vue";
import LayerSidebar from "./components/LayerSidebar.vue";
import MyProjectsModal from "./components/MyProjectsModal.vue";
import ProjectsPage from "./components/ProjectsPage.vue";
import SaveProjectModal from "./components/SaveProjectModal.vue";
import StorageSettings from "./components/StorageSettings.vue";
import TemplateGallery from "./components/TemplateGallery.vue";
import TemplatesPage from "./components/TemplatesPage.vue";
import TeachingPanel from "./components/TeachingPanel.vue";
import ToastContainer from "./components/ToastContainer.vue";
import TrainSettingsModal from "./components/TrainSettingsModal.vue";
import TopBar from "./components/TopBar.vue";
import TrainingMonitor from "./components/TrainingMonitor.vue";
import WorkspaceCoach from "./components/WorkspaceCoach.vue";
import type { ProjectMeta } from "./types";

// 登录门槛：未登录只显示登录/注册页，登录成功后才挂载主界面
const loggedIn = computed(() => isLoggedIn());
const teachingPanelOpen = ref(false);
const currentPage = ref<"home" | "templates" | "projects" | "workspace">("home");

// 用户是否已进入过工作台：只有从工作台返回后，首页各页才提供“回到工作台”按钮
const enteredWorkspace = ref(false);

// 首次进入工作台的聚光灯引导（E）
const coachActive = ref(false);
function coachDone() {
  try { return !!localStorage.getItem(WORKSPACE_COACH_KEY); } catch { return false; }
}
function finishCoach() {
  coachActive.value = false;
  try { localStorage.setItem(WORKSPACE_COACH_KEY, "1"); } catch { /* ignore */ }
}

// 从顶栏「帮助」菜单打开教学辅助面板（与 AI 助手互斥，避免右侧面板重叠）
function openTeaching() {
  ui.assistantOpen = false;
  teachingPanelOpen.value = true;
}

// 页面左右滑动过渡：按页面顺序判断方向（前进滑向左、后退滑向右）
const PAGE_ORDER: Record<string, number> = { home: 0, templates: 1, projects: 2, workspace: 3 };
const pageTransition = ref<"page-forward" | "page-back">("page-forward");
watch(currentPage, (next, prev) => {
  pageTransition.value = (PAGE_ORDER[next] ?? 0) >= (PAGE_ORDER[prev] ?? 0) ? "page-forward" : "page-back";
  if (next === "workspace") {
    enteredWorkspace.value = true;
    // 首次进入工作台且有画布时，启动一次聚光灯引导（等 DOM 就绪再测量目标）
    if (!coachDone() && store.canvases.length > 0) {
      void nextTick(() => { coachActive.value = true; });
    }
  } else {
    // 离开工作台时先收起引导（未完成则下次进入再触发）
    coachActive.value = false;
  }
});
const canvas = computed(() => activeCanvas());
// 工作台是否还有画布：删到 0 个时进入“无画布”空态，隐藏组件库等，提示先新建
const hasCanvas = computed(() => store.canvases.length > 0);
const selectedTeachingNode = computed(() =>
  canvas.value.nodes.find(node => node.id === canvas.value.selectedNodeId) ?? null
);
const teachingModelGraph = computed(() => getCurrentModelGraph(canvas.value));
const teachingValidationResult = computed(() =>
  canvas.value.validationStatus === "unvalidated" ? null : canvas.value.lastValidationResult
);


function closeWorkspaceOverlays() {
  ui.templateGalleryOpen = false;
  ui.projectsModalOpen = false;
  ui.storageSettingsOpen = false;
  ui.agentModalOpen = false;
  ui.saveModalOpen = false;
  ui.trainSettingsOpen = false;
  ui.assistantOpen = false;
  teachingPanelOpen.value = false;
}

function goHome() {
  closeWorkspaceOverlays();
  currentPage.value = "home";
}

// 首页 / 模板库 / 我的项目 之间的整页切换
function goPage(page: "home" | "templates" | "projects") {
  if (page === "home") {
    goHome();
    return;
  }
  currentPage.value = page;
}

function enterWorkspace() {
  currentPage.value = "workspace";
}

function createBlankProject() {
  // 无画布时先建一个；否则当前画布有内容才新建，避免覆盖或产生多余空标签页。
  if (store.canvases.length === 0) {
    addCanvas();
  } else {
    const current = activeCanvas();
    if (current.nodes.length > 0 || current.connections.length > 0) {
      addCanvas();
    }
  }
  currentPage.value = "workspace";
}

async function openRecentProject(project: ProjectMeta) {
  currentPage.value = "workspace";
  await nextTick();
  await loadProjectToCanvas(project);
}

function locateTeachingLayer(layerId: string) {
  const directNode = canvas.value.nodes.find(node => node.id === layerId);
  const containerId = layerId.includes(CONTAINER_ID_SEP)
    ? layerId.split(CONTAINER_ID_SEP)[0]
    : null;
  const targetNode = directNode ?? (
    containerId
      ? canvas.value.nodes.find(node => node.id === containerId && node.type === "Container")
      : null
  );
  if (!targetNode) return;

  canvas.value.selectedNodeId = targetNode.id;
  canvas.value.selectedConnectionKey = null;
  ui.inspectorCollapsed = false;
  teachingPanelOpen.value = false;
}

function handleDocumentClick() {
  hideConnectionMenu();
  hideNodeMenu();
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    // 优先关闭确认弹窗（按取消处理）
    if (confirmDialog.open) {
      resolveConfirm(false);
      return;
    }
    cancelPendingConnection();
    hideConnectionMenu();
    hideNodeMenu();
    closeHelpModal();
    ui.templateGalleryOpen = false;
    ui.storageSettingsOpen = false;
    ui.agentModalOpen = false;
    ui.saveModalOpen = false;
    ui.projectsModalOpen = false;
    ui.trainSettingsOpen = false;
    teachingPanelOpen.value = false;
    return;
  }

  // 撤销 / 重做（Ctrl/⌘ + Z，Ctrl/⌘ + Shift + Z 或 Ctrl + Y 重做）
  if (!loggedIn.value) return;
  const target = event.target as HTMLElement | null;
  // 正在输入框里打字时不拦截，交给浏览器原生撤销
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
    return;
  }
  const mod = event.ctrlKey || event.metaKey;
  if (!mod) return;
  const key = event.key.toLowerCase();
  if (key === "z" && !event.shiftKey) {
    event.preventDefault();
    undoGraphChange();
  } else if ((key === "z" && event.shiftKey) || key === "y") {
    event.preventDefault();
    redoGraphChange();
  }
}

// 进入主界面后再加载后端资源与新手引导
watch(loggedIn, entered => {
  if (entered) {
    currentPage.value = "home";
    // 设备信息由本机 Agent 通过 WebSocket 上报，无需单独拉取
    initializeBeginnerGuide();
    void loadProjectTemplates();
  }
}, { immediate: true });

watch(() => ui.assistantOpen, open => {
  if (open) teachingPanelOpen.value = false;
});

onMounted(() => {
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleKeydown);
  void initializeAuth();
});

onBeforeUnmount(() => {
  document.removeEventListener("click", handleDocumentClick);
  document.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
  <!-- 会话恢复中：加载屏，避免登录页闪现 -->
  <div v-if="auth.restoring" class="auth-restoring">
    <iconify-icon icon="mdi:loading" class="spin"></iconify-icon>
    正在恢复登录状态...
  </div>

  <!-- 未登录：独立登录/注册页 -->
  <AuthPage v-else-if="!loggedIn" />

  <!-- 已登录：首页与工作台使用同一套品牌视觉，并通过过渡避免页面切换割裂 -->
  <template v-else>
    <Transition name="app-section" mode="out-in">
      <!-- 首页区：顶栏/页脚常驻不动，仅中间内容区左右滑动 + 淡入淡出 -->
      <HomeChrome
        v-if="currentPage !== 'workspace'"
        key="home-section"
        :active="currentPage"
        :can-return="enteredWorkspace"
        @navigate="goPage"
        @enter-workspace="enterWorkspace"
      >
        <div class="app-viewport">
          <Transition :name="pageTransition">
            <HomePage
              v-if="currentPage === 'home'"
              key="home"
              @navigate="goPage"
              @create-project="createBlankProject"
              @open-project="openRecentProject"
            />
            <TemplatesPage
              v-else-if="currentPage === 'templates'"
              key="templates"
              @enter-workspace="enterWorkspace"
            />
            <ProjectsPage
              v-else
              key="projects"
              @enter-workspace="enterWorkspace"
            />
          </Transition>
        </div>
      </HomeChrome>

      <!-- 工作台 -->
      <div v-else key="workspace" class="app-shell">
        <TopBar @home="goHome" @open-teaching="openTeaching" />

        <!-- 有画布：正常工作台 -->
        <template v-if="hasCanvas">
          <GuideStrip />

          <div class="workspace" :class="{ 'sidebar-collapsed': ui.sidebarCollapsed }">
            <LayerSidebar />
            <CanvasBoard />
            <InspectorPanel />
            <TeachingPanel
              :open="teachingPanelOpen"
              :available="!ui.assistantOpen"
              :selected-layer="selectedTeachingNode"
              :model-graph="teachingModelGraph"
              :validation-result="teachingValidationResult"
              :validation-request-error="canvas.validationRequestError"
              :validation-in-progress="canvas.validating"
              @open="teachingPanelOpen = true"
              @close="teachingPanelOpen = false"
              @locate-layer="locateTeachingLayer"
            />
            <!-- 左侧组件库收起/展开把手（贴在侧栏右缘，跟随收拢动画） -->
            <button
              class="sidebar-toggle"
              :title="ui.sidebarCollapsed ? '展开组件库' : '收起组件库'"
              @click="ui.sidebarCollapsed = !ui.sidebarCollapsed"
            >
              <iconify-icon :icon="ui.sidebarCollapsed ? 'mdi:chevron-right' : 'mdi:chevron-left'"></iconify-icon>
            </button>
          </div>

          <ActionBar />
        </template>

        <!-- 无画布：隐藏组件库/检查器/操作栏，提示先新建画布 -->
        <div v-else class="workspace-empty">
          <div class="workspace-empty-card">
            <div class="we-illustration" aria-hidden="true">
              <span class="we-node n1"></span>
              <span class="we-node n2"></span>
              <span class="we-node n3"></span>
              <span class="we-plus"><iconify-icon icon="mdi:plus"></iconify-icon></span>
            </div>
            <h2>当前没有画布</h2>
            <p>你已删除全部画布，新建一个即可继续搭建模型。</p>
            <button class="workspace-empty-btn" @click="addCanvas">
              <iconify-icon icon="mdi:plus"></iconify-icon>
              新建画布
            </button>
            <span class="we-sub">也可点顶部「首页」，从模板快速开始</span>
          </div>
        </div>
      </div>
    </Transition>

    <ContextMenus />
    <ExportModal />
    <HelpModal />
    <TemplateGallery @selected="enterWorkspace" />
    <StorageSettings />
    <AgentModal />
    <SaveProjectModal />
    <MyProjectsModal @selected="enterWorkspace" />
    <TrainSettingsModal />
    <AssistantPanel />
    <TrainingMonitor />
    <ConfirmDialog />
    <WorkspaceCoach v-if="coachActive" @done="finishCoach" />
  </template>

  <ToastContainer />
</template>

<style scoped>
/* 内容区：填满顶栏与页脚之间；纵向可滚动（隐藏滚动条），横向裁掉滑出屏幕外的部分。
   离开页绝对定位以便与进入页重叠一起滑动。 */
.app-viewport {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: clip;
  scrollbar-width: none;
}
.app-viewport::-webkit-scrollbar { display: none; }

/* 首页区 ⇄ 工作台：整体淡入淡出切换 */
.app-section-enter-active,
.app-section-leave-active {
  transition: opacity 0.24s ease;
}
.app-section-enter-from,
.app-section-leave-to {
  opacity: 0;
}

/* 无画布空态：整块做成“空画布”网格底，中央一张精致卡片提示先新建画布 */
.workspace-empty {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background-color: #f5f8fe;
  background-image: radial-gradient(#d5deee 1.1px, transparent 1.1px);
  background-size: 22px 22px;
}
/* 顶部/底部柔光，避免纯网格显得死板 */
.workspace-empty::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(60% 55% at 50% 42%, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0) 70%),
    radial-gradient(40% 40% at 82% 12%, rgba(96, 170, 244, 0.12), transparent 70%);
  pointer-events: none;
}

.workspace-empty-card {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 40px 46px 34px;
  border: 1px solid #e4ecf7;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.86);
  backdrop-filter: blur(8px);
  box-shadow: 0 24px 60px rgba(43, 84, 138, 0.16), 0 2px 0 rgba(255, 255, 255, 0.8) inset;
  animation: we-card-in 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
}
@keyframes we-card-in {
  from { opacity: 0; transform: translateY(14px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

/* 空画布占位插画：虚线画框 + 幽灵节点 + 悬浮渐变“＋” */
.we-illustration {
  position: relative;
  width: 188px;
  height: 116px;
  margin-bottom: 22px;
  border: 2px dashed #bcd4f0;
  border-radius: 16px;
  background:
    radial-gradient(#cfdcef 1px, transparent 1px) 0 0 / 15px 15px,
    linear-gradient(180deg, #fbfdff, #f2f8ff);
}
.we-node {
  position: absolute;
  border-radius: 6px;
  background: #fff;
  border: 1.5px solid #d7e3f4;
  box-shadow: 0 4px 10px rgba(52, 96, 150, 0.08);
}
.we-node.n1 { width: 34px; height: 20px; left: 16px; top: 20px; border-color: #bfe3d8; }
.we-node.n2 { width: 30px; height: 20px; right: 20px; top: 26px; border-color: #cdd9ff; }
.we-node.n3 { width: 34px; height: 20px; left: 50%; bottom: 16px; transform: translateX(-50%); border-color: #f3cdbf; }
.we-plus {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 48px;
  height: 48px;
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  font-size: 26px;
  background: linear-gradient(135deg, #37b0f2, #1281e6);
  box-shadow: 0 10px 22px rgba(20, 130, 230, 0.4);
  animation: we-float 2.6s ease-in-out infinite;
}
@keyframes we-float {
  0%, 100% { transform: translate(-50%, -50%); }
  50% { transform: translate(-50%, calc(-50% - 5px)); }
}

.workspace-empty-card h2 {
  margin: 0;
  font-size: 21px;
  font-weight: 800;
  letter-spacing: -0.01em;
  background: linear-gradient(90deg, #1f3557, #1c74c9);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.workspace-empty-card p {
  margin: 9px 0 0;
  max-width: 360px;
  font-size: 13.5px;
  line-height: 1.6;
  color: #6b7d99;
}
.workspace-empty-btn {
  margin-top: 22px;
  height: 46px;
  padding: 0 30px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(135deg, #1aa2ed, #1181e2);
  box-shadow: 0 12px 24px rgba(19, 132, 226, 0.32);
  font-size: 15px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease;
}
.workspace-empty-btn:hover { transform: translateY(-2px); box-shadow: 0 16px 30px rgba(19, 132, 226, 0.4); filter: brightness(1.03); }
.workspace-empty-btn:active { transform: translateY(0); }
.workspace-empty-btn iconify-icon { font-size: 20px; }
.we-sub { margin-top: 16px; font-size: 12px; color: #9aa8bd; }

/* 方向性横向位移 + 淡入淡出：进入页与离开页朝同一方向一起平移并淡入淡出 */
.page-forward-enter-active,
.page-forward-leave-active,
.page-back-enter-active,
.page-back-leave-active {
  transition: opacity 0.3s ease, transform 0.34s cubic-bezier(0.4, 0, 0.2, 1);
}
.page-forward-leave-active,
.page-back-leave-active {
  position: absolute;
  inset: 0;
}

/* 前进（目标页在右，如 首页→模板库）：两页一起向左移，旧页向左淡出、新页自右向左淡入 */
.page-forward-enter-from { opacity: 0; transform: translateX(48px); }
.page-forward-leave-to { opacity: 0; transform: translateX(-48px); }

/* 后退（目标页在左，如 模板库→首页）：两页一起向右移 */
.page-back-enter-from { opacity: 0; transform: translateX(-48px); }
.page-back-leave-to { opacity: 0; transform: translateX(48px); }
</style>
