<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { loadDevices, loadProjectTemplates } from "./actions";
import { cancelPendingConnection, hideConnectionMenu, hideNodeMenu } from "./canvas";
import { closeHelpModal, initializeBeginnerGuide } from "./store";
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

    <div class="workspace">
      <LayerSidebar />
      <CanvasBoard />
      <InspectorPanel />
    </div>

    <ActionBar />
  </div>

  <ToastContainer />
  <ContextMenus />
  <ExportModal />
  <HelpModal />
  <TrainingMonitor />
</template>
