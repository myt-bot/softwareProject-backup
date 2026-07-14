<script setup lang="ts">
import { computed } from "vue";
import { closeExportModal, copyExportCode, downloadExportCode, setExportFormat } from "../actions";
import { activeCanvas, ui } from "../store";

// 显示当前激活画布的导出结果（各画布的导出相互独立）
const canvas = computed(() => activeCanvas());
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
            <p>把画布上的模型打包成可直接运行的代码与依赖清单（zip 内含 requirements.txt）</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-modal" @click="closeExportModal"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>
      <div class="modal-body">
        <div class="model-summary">
          <h3>模型结构摘要</h3>
          <div class="export-format-toggle" role="group" aria-label="导出格式">
            <button
              type="button"
              :class="{ active: canvas.exportFormat === 'py' }"
              title="导出 Python 文件"
              @click="setExportFormat('py')"
            >
              <iconify-icon icon="mdi:language-python"></iconify-icon>
              <span>.py</span>
            </button>
            <button
              type="button"
              :class="{ active: canvas.exportFormat === 'ipynb' }"
              title="导出 Jupyter Notebook"
              @click="setExportFormat('ipynb')"
            >
              <iconify-icon icon="mdi:notebook-outline"></iconify-icon>
              <span>.ipynb</span>
            </button>
          </div>
          <div class="summary-row blue">
            <i></i>
            <div>
              <strong>{{ canvas.nodes.length }} 个节点</strong>
              <span>当前画布会按连接顺序生成 forward</span>
            </div>
          </div>
          <div class="summary-row indigo">
            <i></i>
            <div>
              <strong>{{ canvas.connections.length }} 条连线</strong>
              <span>分支会按节点参数执行 concat 或 add</span>
            </div>
          </div>
        </div>
        <div class="code-panel">
          <button class="copy-button" id="btn-copy-code" @click="copyExportCode">
            <iconify-icon icon="mdi:content-copy"></iconify-icon>
            复制代码
          </button>
          <pre id="export-code">{{ canvas.exportCodeDisplay }}</pre>
        </div>
      </div>
      <div class="modal-footer">
        <button class="text-button" id="btn-cancel-modal" @click="closeExportModal">取消</button>
        <button class="primary-button" id="btn-download-code" @click="downloadExportCode">
          <iconify-icon icon="mdi:download"></iconify-icon>
          下载 .zip（含 {{ canvas.exportFormat === "ipynb" ? ".ipynb" : ".py" }} + requirements.txt）
        </button>
      </div>
    </div>
  </div>
</template>
