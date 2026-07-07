<script setup lang="ts">
import { ref, watch } from "vue";
import { fetchMyProjects, loadProjectToCanvas, removeProject } from "../actions";
import { ui } from "../store";
import type { ProjectMeta } from "../types";

const projects = ref<ProjectMeta[]>([]);
const loading = ref(false);
const confirmingId = ref<string | null>(null);

// 打开时拉取用户已保存的项目
watch(
  () => ui.projectsModalOpen,
  async open => {
    if (!open) return;
    confirmingId.value = null;
    loading.value = true;
    try {
      projects.value = await fetchMyProjects();
    } catch {
      projects.value = [];
    } finally {
      loading.value = false;
    }
  }
);

function close() {
  ui.projectsModalOpen = false;
}

function formatTime(iso?: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function layerCount(project: ProjectMeta) {
  return project.model_graph?.layers?.length ?? 0;
}

async function confirmDelete(project: ProjectMeta) {
  if (confirmingId.value !== project.id) {
    confirmingId.value = project.id;
    return;
  }
  const ok = await removeProject(project);
  confirmingId.value = null;
  if (ok) {
    projects.value = projects.value.filter(item => item.id !== project.id);
  }
}
</script>

<template>
  <div class="modal" :class="{ hidden: !ui.projectsModalOpen }" id="projects-modal">
    <div class="modal-card projects-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:folder-open-outline"></iconify-icon>
          <div>
            <h2>我的项目</h2>
            <p>加载之前保存过的模型，将在新画布中打开</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-projects" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="projects-body">
        <div v-if="loading" class="projects-empty">
          <iconify-icon icon="mdi:loading" class="spin"></iconify-icon>
          正在加载...
        </div>
        <div v-else-if="projects.length === 0" class="projects-empty">
          <iconify-icon icon="mdi:folder-outline"></iconify-icon>
          <p>还没有保存过的模型</p>
          <span>在画布上搭好模型后，点击底部「保存模型」即可保存到这里</span>
        </div>
        <ul v-else class="projects-list">
          <li v-for="project in projects" :key="project.id" class="project-item">
            <div class="project-icon"><iconify-icon icon="mdi:vector-polyline"></iconify-icon></div>
            <div class="project-info">
              <strong>{{ project.name }}</strong>
              <p v-if="project.description">{{ project.description }}</p>
              <span class="project-meta">{{ layerCount(project) }} 层 · 更新于 {{ formatTime(project.updated_at) }}</span>
            </div>
            <div class="project-actions">
              <button class="secondary-button" @click="loadProjectToCanvas(project)">
                <iconify-icon icon="mdi:open-in-app"></iconify-icon>
                加载
              </button>
              <button
                class="icon-button project-delete"
                :class="{ confirming: confirmingId === project.id }"
                :title="confirmingId === project.id ? '再次点击确认删除' : '删除'"
                @click="confirmDelete(project)"
              >
                <iconify-icon :icon="confirmingId === project.id ? 'mdi:delete-alert-outline' : 'mdi:delete-outline'"></iconify-icon>
              </button>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
