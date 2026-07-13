<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchMyProjects, loadProjectToCanvas, removeProject } from "../actions";
import type { ProjectMeta } from "../types";

const emit = defineEmits<{
  enterWorkspace: [];
}>();

const projects = ref<ProjectMeta[]>([]);
const loading = ref(false);
const confirmingId = ref<string | null>(null);

onMounted(load);

async function load() {
  loading.value = true;
  confirmingId.value = null;
  try {
    projects.value = await fetchMyProjects();
  } catch {
    projects.value = [];
  } finally {
    loading.value = false;
  }
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

async function openProject(project: ProjectMeta) {
  if (await loadProjectToCanvas(project)) emit("enterWorkspace");
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
  <main class="mw-subpage">
      <header class="mw-subpage-head">
        <span class="mw-subpage-icon folder"><iconify-icon icon="mdi:folder-open-outline"></iconify-icon></span>
        <div>
          <h1>我的项目</h1>
          <p>加载之前保存过的模型，将在新画布中打开并进入工作台</p>
        </div>
      </header>

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
            <button class="secondary-button" @click="openProject(project)">
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
  </main>
</template>

<style scoped>
.mw-subpage {
  width: min(920px, calc(100% - 64px));
  margin: 0 auto;
  flex: 1;
  padding: 32px 0 40px;
}
.mw-subpage-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 22px;
}
.mw-subpage-icon {
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 15px;
  font-size: 27px;
}
.mw-subpage-icon.folder { color: #6d55df; background: #eeeaff; }
.mw-subpage-head h1 { margin: 0; font-size: 26px; letter-spacing: -.02em; }
.mw-subpage-head p { margin: 5px 0 0; color: #6d7f9b; font-size: 14px; }

@media (max-width: 960px) {
  .mw-subpage { width: min(100% - 40px, 820px); }
}
</style>
