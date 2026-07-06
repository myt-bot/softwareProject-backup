<script setup lang="ts">
import { closeExportModal, copyExportCode, downloadExportCode } from "../actions";
import { store, ui } from "../store";
</script>

<template>
  <!-- 导出代码弹窗 -->
  <div class="modal" :class="{ hidden: !ui.exportModalOpen }" id="export-modal">
    <div class="modal-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:file-code-outline"></iconify-icon>
          <div>
            <h2>导出 PyTorch 代码</h2>
            <p>把画布上的模型变成可直接运行的 Python 文件</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-modal" @click="closeExportModal"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>
      <div class="modal-body">
        <div class="model-summary">
          <h3>模型结构摘要</h3>
          <div class="summary-row blue">
            <i></i>
            <div>
              <strong>特征提取部分</strong>
              <span>卷积、池化层负责“看懂”图像特征</span>
            </div>
          </div>
          <div class="summary-row indigo">
            <i></i>
            <div>
              <strong>分类输出部分</strong>
              <span>全连接层把特征变成类别预测</span>
            </div>
          </div>
        </div>
        <div class="code-panel">
          <button class="copy-button" id="btn-copy-code" @click="copyExportCode">
            <iconify-icon icon="mdi:content-copy"></iconify-icon>
            复制代码
          </button>
          <pre id="export-code">{{ store.exportCodeDisplay }}</pre>
        </div>
      </div>
      <div class="modal-footer">
        <button class="text-button" id="btn-cancel-modal" @click="closeExportModal">取消</button>
        <button class="primary-button" id="btn-download-code" @click="downloadExportCode">
          <iconify-icon icon="mdi:download"></iconify-icon>
          下载 .py 文件
        </button>
      </div>
    </div>
  </div>
</template>
