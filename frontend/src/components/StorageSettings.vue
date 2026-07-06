<script setup lang="ts">
import { reactive, watch } from "vue";
import { saveStoragePaths, showToast, storagePaths, ui } from "../store";

// 表单草稿：打开弹窗时从已保存的设置同步
const form = reactive({ dataDir: storagePaths.dataDir, artifactsDir: storagePaths.artifactsDir });

watch(
  () => ui.storageSettingsOpen,
  open => {
    if (open) {
      form.dataDir = storagePaths.dataDir;
      form.artifactsDir = storagePaths.artifactsDir;
    }
  }
);

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
            <p>路径位于运行后端服务的电脑上，留空则使用默认位置</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-storage" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="storage-body">
        <label class="form-field">
          <span>数据集下载位置</span>
          <input
            id="storage-data-dir"
            type="text"
            v-model="form.dataDir"
            placeholder="默认：项目目录下（如 ./MNIST）"
          >
          <small>训练数据集（MNIST、CIFAR10 等）将下载并缓存到该目录，例如 ~/datasets</small>
        </label>

        <label class="form-field">
          <span>结果文件存储位置</span>
          <input
            id="storage-artifacts-dir"
            type="text"
            v-model="form.artifactsDir"
            placeholder="默认：项目目录下的 training_artifacts"
          >
          <small>每次训练的模型权重（model.pt）和指标（metrics.json）将保存到该目录，例如 ~/model_results</small>
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
  </div>
</template>
