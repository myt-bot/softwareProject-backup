<script setup lang="ts">
import { computed } from "vue";
import { agentDownloadUrl } from "../api/client";
import { auth } from "../auth";
import { agent, showToast, ui } from "../store";

// 启动本机 Agent 的命令（携带当前用户令牌以绑定身份）
const command = computed(
  () => `python -m local_agent.main --server http://127.0.0.1:8000 --token ${auth.token ?? "<你的令牌>"}`
);

const downloadUrl = agentDownloadUrl();

function close() {
  ui.agentModalOpen = false;
}

async function copyCommand() {
  try {
    await navigator.clipboard.writeText(command.value);
    showToast("success", "启动命令已复制。");
  } catch {
    showToast("warning", "当前浏览器不支持自动复制。");
  }
}
</script>

<template>
  <div class="modal" :class="{ hidden: !ui.agentModalOpen }" id="agent-modal">
    <div class="modal-card agent-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:laptop"></iconify-icon>
          <div>
            <h2>本机训练 Agent</h2>
            <p>训练在你自己的电脑上进行，需要先启动本地训练 Agent</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-agent" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="agent-body">
        <!-- 当前状态 -->
        <div class="agent-status-row" :class="agent.online ? 'online' : 'offline'">
          <span class="agent-dot"></span>
          <div>
            <strong>{{ agent.online ? "本机 Agent 已连接" : "本机 Agent 未连接" }}</strong>
            <span v-if="agent.online" class="agent-status-detail">
              运行时 {{ agent.runtimeVersion || "?" }} ·
              设备 {{ agent.deviceSummary?.available_devices?.join(" / ") || "未知" }}
              <template v-if="agent.deviceSummary?.cuda_available"> · GPU 可用</template>
            </span>
            <span v-else class="agent-status-detail">按下方步骤启动后将自动连接</span>
          </div>
        </div>

        <!-- 首次使用：下载 Agent -->
        <a class="agent-download" :href="downloadUrl" download>
          <iconify-icon icon="mdi:download"></iconify-icon>
          <div>
            <strong>下载本机 Agent（首次使用）</strong>
            <span>本机还没有 Agent 程序？点此下载压缩包，解压后按下方步骤启动</span>
          </div>
        </a>

        <!-- 启动步骤 -->
        <ol class="agent-steps">
          <li>
            <strong>准备环境</strong>：确保已安装 Python 3.10+，解压下载的压缩包并进入其目录。
          </li>
          <li>
            <strong>安装依赖</strong>（首次）：<code>pip install -r requirements-agent.txt</code>
          </li>
          <li>
            <strong>启动本机 Agent</strong>：复制并运行下面的命令。首次运行会自动从云端下载训练运行时代码。
            <div class="agent-command">
              <code>{{ command }}</code>
              <button class="icon-button" title="复制命令" @click="copyCommand">
                <iconify-icon icon="mdi:content-copy"></iconify-icon>
              </button>
            </div>
          </li>
          <li>
            Agent 连接成功后，本页顶部会显示「本机训练已连接」，即可进行结构校验、训练与代码导出。
          </li>
        </ol>

        <p class="agent-note">
          <iconify-icon icon="mdi:shield-check-outline"></iconify-icon>
          令牌用于把本机 Agent 绑定到你的账号，请勿分享给他人。
        </p>
      </div>

      <div class="modal-footer">
        <button class="primary-button" @click="close">
          <iconify-icon icon="mdi:check"></iconify-icon>
          我知道了
        </button>
      </div>
    </div>
  </div>
</template>
