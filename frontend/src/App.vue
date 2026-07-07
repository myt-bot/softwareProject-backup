<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { loadProjectTemplates } from "./actions";
import { auth, initializeAuth, isLoggedIn } from "./auth";
import { cancelPendingConnection, hideConnectionMenu, hideNodeMenu } from "./canvas";
import { closeHelpModal, initializeBeginnerGuide, ui } from "./store";
import ActionBar from "./components/ActionBar.vue";
import AgentModal from "./components/AgentModal.vue";
import AuthPage from "./components/AuthPage.vue";
import CanvasBoard from "./components/CanvasBoard.vue";
import ContextMenus from "./components/ContextMenus.vue";
import ExportModal from "./components/ExportModal.vue";
import GuideStrip from "./components/GuideStrip.vue";
import HelpModal from "./components/HelpModal.vue";
import InspectorPanel from "./components/InspectorPanel.vue";
import LayerSidebar from "./components/LayerSidebar.vue";
import MyProjectsModal from "./components/MyProjectsModal.vue";
import SaveProjectModal from "./components/SaveProjectModal.vue";
import StorageSettings from "./components/StorageSettings.vue";
import TemplateGallery from "./components/TemplateGallery.vue";
import ToastContainer from "./components/ToastContainer.vue";
import TopBar from "./components/TopBar.vue";
import TrainingMonitor from "./components/TrainingMonitor.vue";

// 登录门槛：未登录只显示登录/注册页，登录成功后才挂载主界面
const loggedIn = computed(() => isLoggedIn());

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
  }
}

// 进入主界面后再加载后端资源与新手引导
watch(loggedIn, entered => {
  if (entered) {
    // 设备信息由本机 Agent 通过 WebSocket 上报，无需单独拉取
    initializeBeginnerGuide();
    void loadProjectTemplates();
  }
}, { immediate: true });

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

  <!-- 已登录：模型搭建主界面 -->
  <template v-else>
    <div class="app-shell">
      <TopBar />
      <GuideStrip />

      <div class="workspace" :class="{ 'sidebar-collapsed': ui.sidebarCollapsed }">
        <LayerSidebar />
        <CanvasBoard />
        <InspectorPanel />
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

    <ContextMenus />
    <ExportModal />
    <HelpModal />
    <TemplateGallery />
    <StorageSettings />
    <AgentModal />
    <SaveProjectModal />
    <MyProjectsModal />
    <TrainingMonitor />
  </template>

  <ToastContainer />
</template>
