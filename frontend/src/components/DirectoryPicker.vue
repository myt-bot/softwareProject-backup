<script setup lang="ts">
import { ref, watch } from "vue";
import { agent, showToast } from "../store";
import { requestAgent } from "../ws";

interface DirEntry {
  name: string;
  path: string;
}
interface ListDirResult {
  path: string;
  parent: string | null;
  entries: DirEntry[];
}

const props = defineProps<{
  open: boolean;
  title?: string;
  startPath?: string;
}>();

const emit = defineEmits<{
  select: [path: string];
  close: [];
}>();

const currentPath = ref("");
const parentPath = ref<string | null>(null);
const entries = ref<DirEntry[]>([]);
const loading = ref(false);

async function browse(path?: string) {
  if (!agent.online) {
    showToast("warning", "浏览目录需要本机训练 Agent，请先启动本地 Agent。");
    return;
  }
  loading.value = true;
  try {
    const result = await requestAgent<ListDirResult>("list_dir", { path: path ?? "" });
    currentPath.value = result.path;
    parentPath.value = result.parent;
    entries.value = result.entries || [];
  } catch (error) {
    showToast("error", (error as Error)?.message || "读取目录失败。");
  } finally {
    loading.value = false;
  }
}

// 打开时从起始路径（或本机主目录）开始浏览
watch(
  () => props.open,
  open => {
    if (open) {
      entries.value = [];
      void browse(props.startPath || "");
    }
  }
);

function choose() {
  emit("select", currentPath.value);
}
</script>

<template>
  <div class="modal" :class="{ hidden: !open }" id="dir-picker">
    <div class="modal-card dir-picker-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:folder-search-outline"></iconify-icon>
          <div>
            <h2>{{ title || "选择目录" }}</h2>
            <p>浏览本机文件夹，选择一个目录作为存储位置</p>
          </div>
        </div>
        <button class="icon-button" @click="emit('close')"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="dir-current">
        <iconify-icon icon="mdi:folder-outline"></iconify-icon>
        <code>{{ currentPath || "…" }}</code>
      </div>

      <div class="dir-list">
        <div v-if="loading" class="dir-empty"><iconify-icon icon="mdi:loading" class="spin"></iconify-icon> 读取中...</div>
        <template v-else>
          <button v-if="parentPath" class="dir-entry up" @click="browse(parentPath)">
            <iconify-icon icon="mdi:arrow-up-left"></iconify-icon>
            <span>上级目录</span>
          </button>
          <button
            v-for="entry in entries"
            :key="entry.path"
            class="dir-entry"
            @click="browse(entry.path)"
          >
            <iconify-icon icon="mdi:folder-outline"></iconify-icon>
            <span>{{ entry.name }}</span>
          </button>
          <div v-if="!parentPath && entries.length === 0" class="dir-empty">该目录下没有子文件夹</div>
        </template>
      </div>

      <div class="modal-footer">
        <button class="text-button" @click="emit('close')">取消</button>
        <button class="primary-button" @click="choose">
          <iconify-icon icon="mdi:check"></iconify-icon>
          选择此目录
        </button>
      </div>
    </div>
  </div>
</template>
