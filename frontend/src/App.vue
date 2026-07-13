<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { loadProjectTemplates, loadProjectToCanvas } from "./actions";
import { auth, initializeAuth, isLoggedIn } from "./auth";
import { addCanvas, cancelPendingConnection, hideConnectionMenu, hideNodeMenu, redoGraphChange, undoGraphChange } from "./canvas";
import { activeCanvas, closeHelpModal, CONTAINER_ID_SEP, getCurrentModelGraph, initializeBeginnerGuide, ui } from "./store";
import ActionBar from "./components/ActionBar.vue";
import AgentModal from "./components/AgentModal.vue";
import AssistantPanel from "./components/AssistantPanel.vue";
import AuthPage from "./components/AuthPage.vue";
import CanvasBoard from "./components/CanvasBoard.vue";
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
import type { ProjectMeta } from "./types";

// 登录门槛：未登录只显示登录/注册页，登录成功后才挂载主界面
const loggedIn = computed(() => isLoggedIn());
const teachingPanelOpen = ref(false);
const currentPage = ref<"home" | "templates" | "projects" | "workspace">("home");

// 用户是否已进入过工作台：只有从工作台返回后，首页各页才提供“回到工作台”按钮
const enteredWorkspace = ref(false);

// 页面左右滑动过渡：按页面顺序判断方向（前进滑向左、后退滑向右）
const PAGE_ORDER: Record<string, number> = { home: 0, templates: 1, projects: 2, workspace: 3 };
const pageTransition = ref<"page-forward" | "page-back">("page-forward");
watch(currentPage, (next, prev) => {
  pageTransition.value = (PAGE_ORDER[next] ?? 0) >= (PAGE_ORDER[prev] ?? 0) ? "page-forward" : "page-back";
  if (next === "workspace") enteredWorkspace.value = true;
});
const canvas = computed(() => activeCanvas());
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
  const current = activeCanvas();
  // 当前画布已有内容时新建一个空画布，避免覆盖用户正在编辑的模型；
  // 当前画布本来就是空白时直接复用，避免产生多余标签页。
  if (current.nodes.length > 0 || current.connections.length > 0) {
    addCanvas();
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
        <TopBar @home="goHome" />
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
