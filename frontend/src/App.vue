<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { loadDevices, loadProjectTemplates } from "./actions";
import { cancelPendingConnection, hideConnectionMenu, hideNodeMenu } from "./canvas";
import { closeHelpModal, initializeBeginnerGuide, ui } from "./store";
import ActionBar from "./components/ActionBar.vue";
import CanvasBoard from "./components/CanvasBoard.vue";
import ContextMenus from "./components/ContextMenus.vue";
import ExportModal from "./components/ExportModal.vue";
import GuideStrip from "./components/GuideStrip.vue";
import HelpModal from "./components/HelpModal.vue";
import InspectorPanel from "./components/InspectorPanel.vue";
import LayerSidebar from "./components/LayerSidebar.vue";
import ToastContainer from "./components/ToastContainer.vue";
import TopBar from "./components/TopBar.vue";
import TrainingMonitor from "./components/TrainingMonitor.vue";

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
  }
}

onMounted(() => {
  initializeBeginnerGuide();
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleKeydown);
  void loadDevices();
  void loadProjectTemplates();
});

onBeforeUnmount(() => {
  document.removeEventListener("click", handleDocumentClick);
  document.removeEventListener("keydown", handleKeydown);
});
</script>

<template>
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

  <ToastContainer />
  <ContextMenus />
  <ExportModal />
  <HelpModal />
  <TrainingMonitor />
</template>
