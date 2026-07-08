<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { agent, saveStoragePaths, showToast, storagePaths, ui } from "../store";
import DirectoryPicker from "./DirectoryPicker.vue";

// 表单草稿：打开弹窗时从已保存的设置同步
const form = reactive({ dataDir: storagePaths.dataDir, artifactsDir: storagePaths.artifactsDir });

// 目录选择器：picking 记录当前正在为哪个字段选择目录
const pickerOpen = ref(false);
const picking = ref<"dataDir" | "artifactsDir">("dataDir");
const pickerTitle = ref("");

watch(
  () => ui.storageSettingsOpen,
  open => {
    if (open) {
      form.dataDir = storagePaths.dataDir;
      form.artifactsDir = storagePaths.artifactsDir;
    }
  }
);

function openPicker(field: "dataDir" | "artifactsDir") {
  if (!agent.online) {
    showToast("warning", "浏览目录需要本机训练 Agent，请先启动本地 Agent。");
    ui.agentModalOpen = true;
    return;
  }
  picking.value = field;
  pickerTitle.value = field === "dataDir" ? "选择数据集下载位置" : "选择结果文件存储位置";
  pickerOpen.value = true;
}

function onPicked(path: string) {
  form[picking.value] = path;
  pickerOpen.value = false;
}

function close() {
  ui.storageSettingsOpen = false;
}

function save() {
  saveStoragePaths(form.dataDir, form.artifactsDir);
  close();
  showToast("success", "存储位置设置已保存，将在下次训练时生效。");
}

function resetDefaults() {
  form.dataDir = "";
  form.artifactsDir = "";
}
</script>

<template>
  <!-- 存储位置设置：数据集下载目录 / 训练产物保存目录 -->
  <div class="modal" :class="{ hidden: !ui.storageSettingsOpen }" id="storage-settings">
    <div class="modal-card storage-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:folder-cog-outline"></iconify-icon>
          <div>
            <h2>存储位置设置</h2>
            <p>路径位于运行本机训练 Agent 的电脑上（即你的电脑），留空则使用默认位置</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-storage" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="storage-body">
        <label class="form-field">
          <span>数据集下载位置</span>
          <div class="path-input">
            <input
              id="storage-data-dir"
              type="text"
              v-model="form.dataDir"
              placeholder="留空则使用项目目录下的默认位置"
            >
            <button class="secondary-button path-browse" id="browse-data-dir" @click="openPicker('dataDir')">
              <iconify-icon icon="mdi:folder-search-outline"></iconify-icon>
              浏览
            </button>
          </div>
          <small>训练用的数据集将下载并缓存到该目录，可自定义为任意本地路径。</small>
        </label>

        <label class="form-field">
          <span>结果文件存储位置</span>
          <div class="path-input">
            <input
              id="storage-artifacts-dir"
              type="text"
              v-model="form.artifactsDir"
              placeholder="默认：项目目录下的 training_artifacts"
            >
            <button class="secondary-button path-browse" id="browse-artifacts-dir" @click="openPicker('artifactsDir')">
              <iconify-icon icon="mdi:folder-search-outline"></iconify-icon>
              浏览
            </button>
          </div>
          <small>每次训练得到的模型权重和训练指标文件将保存到该目录，可自定义为任意本地路径。</small>
        </label>
      </div>

      <div class="modal-footer">
        <button class="text-button" id="btn-storage-reset" @click="resetDefaults">恢复默认</button>
        <button class="text-button" @click="close">取消</button>
        <button class="primary-button" id="btn-storage-save" @click="save">
          <iconify-icon icon="mdi:content-save-outline"></iconify-icon>
          保存设置
        </button>
      </div>
    </div>

    <!-- 目录选择器（浏览本机文件夹） -->
    <DirectoryPicker
      :open="pickerOpen"
      :title="pickerTitle"
      :start-path="form[picking]"
      @select="onPicked"
      @close="pickerOpen = false"
    />
  </div>
</template>
