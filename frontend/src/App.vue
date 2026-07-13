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
import HomePage from "./components/HomePage.vue";
import InspectorPanel from "./components/InspectorPanel.vue";
import LayerSidebar from "./components/LayerSidebar.vue";
import MyProjectsModal from "./components/MyProjectsModal.vue";
import SaveProjectModal from "./components/SaveProjectModal.vue";
import StorageSettings from "./components/StorageSettings.vue";
import TemplateGallery from "./components/TemplateGallery.vue";
import TeachingPanel from "./components/TeachingPanel.vue";
import ToastContainer from "./components/ToastContainer.vue";
import TrainSettingsModal from "./components/TrainSettingsModal.vue";
import TopBar from "./components/TopBar.vue";
import TrainingMonitor from "./components/TrainingMonitor.vue";
import type { ProjectMeta } from "./types";

// 登录门槛：未登录只显示登录/注册页，登录成功后才挂载主界面
const loggedIn = computed(() => isLoggedIn());
const teachingPanelOpen = ref(false);
const currentPage = ref<"home" | "workspace">("home");
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

function browseTemplatesFromHome() {
  // 首页只打开模板选择窗口；用户真正选择模板后再进入工作台。
  ui.templateGalleryOpen = true;
}

function openProjectsFromHome() {
  // 首页只打开项目列表；关闭窗口时仍停留在首页。
  ui.projectsModalOpen = true;
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
    <Transition name="app-page-switch" mode="out-in">
      <HomePage
        v-if="currentPage === 'home'"
        key="home"
        @enter-workspace="enterWorkspace"
        @create-project="createBlankProject"
        @browse-templates="browseTemplatesFromHome"
        @open-projects="openProjectsFromHome"
        @open-project="openRecentProject"
      />

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
.app-page-switch-enter-active,
.app-page-switch-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.app-page-switch-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.app-page-switch-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
