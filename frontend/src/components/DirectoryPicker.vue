<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { agent, showToast } from "../store";
import { requestAgent } from "../ws";

interface DirEntry {
  name: string;
  path: string;
  kind?: string;
}
interface ListDirResult {
  path: string;
  display?: string;
  is_root?: boolean;
  parent: string | null;
  entries: DirEntry[];
}

const DRIVES = "__drives__";

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
const displayPath = ref("");
const isRoot = ref(false);
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
    displayPath.value = result.display || result.path;
    isRoot.value = Boolean(result.is_root);
    parentPath.value = result.parent;
    entries.value = result.entries || [];
  } catch (error) {
    showToast("error", (error as Error)?.message || "读取目录失败。");
  } finally {
    loading.value = false;
  }
}

// 把当前路径拆成可点击的层级面包屑（像 Windows 资源管理器的地址栏）
const crumbs = computed(() => {
  const p = currentPath.value;
  if (!p || p === DRIVES) return [] as { label: string; path: string }[];
  const sep = p.includes("\\") ? "\\" : "/";
  const parts = p.split(sep);
  const out: { label: string; path: string }[] = [];
  let acc = "";
  parts.forEach((part, index) => {
    if (part === "") {
      if (index === 0 && sep === "/") {
        acc = "/";
        out.push({ label: "/", path: "/" });
      }
      return;
    }
    if (index === 0 && sep === "\\") {
      acc = `${part}\\`; // 盘符 C: → C:\
      out.push({ label: part, path: acc });
      return;
    }
    acc = acc.endsWith(sep) ? acc + part : acc + sep + part;
    out.push({ label: part, path: acc });
  });
  return out;
});

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
  if (isRoot.value || !currentPath.value) return;
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
            <p>浏览本机文件夹（含各磁盘），选择一个目录作为存储位置</p>
          </div>
        </div>
        <button class="icon-button" @click="emit('close')"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <!-- 地址栏：此电脑 + 面包屑层级，可点任意一级跳转 -->
      <div class="dir-crumbs">
        <button class="dir-crumb pc" :class="{ active: isRoot }" title="此电脑（切换磁盘）" @click="browse('__drives__')">
          <iconify-icon icon="mdi:monitor"></iconify-icon>
          <span>此电脑</span>
        </button>
        <template v-for="crumb in crumbs" :key="crumb.path">
          <iconify-icon class="dir-crumb-sep" icon="mdi:chevron-right"></iconify-icon>
          <button class="dir-crumb" @click="browse(crumb.path)">{{ crumb.label }}</button>
        </template>
      </div>

      <div class="dir-list">
        <div v-if="loading" class="dir-empty"><iconify-icon icon="mdi:loading" class="spin"></iconify-icon> 读取中...</div>
        <template v-else>
          <button v-if="parentPath" class="dir-entry up" @click="browse(parentPath)">
            <iconify-icon icon="mdi:arrow-up-left"></iconify-icon>
            <span>{{ parentPath === '__drives__' ? '此电脑（选择其它磁盘）' : '上级目录' }}</span>
          </button>
          <button
            v-for="entry in entries"
            :key="entry.path"
            class="dir-entry"
            :class="{ drive: entry.kind === 'drive' }"
            @click="browse(entry.path)"
          >
            <iconify-icon :icon="entry.kind === 'drive' ? 'mdi:harddisk' : 'mdi:folder'"></iconify-icon>
            <span>{{ entry.name }}</span>
            <iconify-icon class="dir-entry-go" icon="mdi:chevron-right"></iconify-icon>
          </button>
          <div v-if="!parentPath && entries.length === 0" class="dir-empty">该位置下没有可进入的文件夹</div>
        </template>
      </div>

      <div class="modal-footer dir-footer">
        <span class="dir-selected">
          <template v-if="isRoot">请先进入一个磁盘或文件夹</template>
          <template v-else>选定位置：<code>{{ displayPath || '…' }}</code></template>
        </span>
        <div class="dir-footer-actions">
          <button class="text-button" @click="emit('close')">取消</button>
          <button class="primary-button" :disabled="isRoot || !currentPath" @click="choose">
            <iconify-icon icon="mdi:check"></iconify-icon>
            选择此目录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
