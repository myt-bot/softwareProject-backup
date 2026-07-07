<script setup lang="ts">
import { computed, ref } from "vue";
import { agentDownloadUrl } from "../api/client";
import { auth } from "../auth";
import { agent, ui } from "../store";

type OsKey = "windows" | "macos" | "linux";
const OS_OPTIONS: Array<{ key: OsKey; label: string; icon: string }> = [
  { key: "windows", label: "Windows", icon: "mdi:microsoft-windows" },
  { key: "macos", label: "macOS", icon: "mdi:apple" },
  { key: "linux", label: "Linux", icon: "mdi:linux" },
];

// 按浏览器 UA 猜测当前系统，作为默认下载平台
function detectOs(): OsKey {
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("windows")) return "windows";
  if (ua.includes("mac os") || ua.includes("macintosh")) return "macos";
  if (ua.includes("linux") || ua.includes("x11")) return "linux";
  return "windows";
}

const selectedOs = ref<OsKey>(detectOs());

// 下载链接内含用户令牌与目标平台：下载的应用已绑定账号，双击即自动连接
const downloadUrl = computed(() => agentDownloadUrl(auth.token ?? "", selectedOs.value));

const gpuName = computed(() => {
  const dev = agent.deviceSummary?.cuda_devices?.[0];
  return typeof dev === "string" ? dev : dev?.name || "GPU";
});

function close() {
  ui.agentModalOpen = false;
}
</script>

<template>
  <div class="modal" :class="{ hidden: !ui.agentModalOpen }" id="agent-modal">
    <div class="modal-card agent-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:laptop"></iconify-icon>
          <div>
            <h2>本机训练应用</h2>
            <p>训练在你自己的电脑上进行，需要先运行本机训练应用</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-agent" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="agent-body">
        <!-- 当前状态 -->
        <div class="agent-status-row" :class="agent.online ? 'online' : 'offline'">
          <span class="agent-dot"></span>
          <div>
            <strong>{{ agent.online ? "本机训练已连接" : "本机训练未连接" }}</strong>
            <span v-if="agent.online" class="agent-status-detail">
              运行时 {{ agent.runtimeVersion || "?" }} ·
              设备 {{ agent.deviceSummary?.available_devices?.join(" / ") || "未知" }}
              <template v-if="agent.deviceSummary?.cuda_available"> · GPU 可用（{{ gpuName }}）</template>
            </span>
            <span v-else class="agent-status-detail">按下方步骤运行应用后将自动连接</span>
          </div>
        </div>

        <!-- 选择操作系统（默认按你的系统自动识别） -->
        <div class="agent-os-tabs" id="agent-os-tabs">
          <button
            v-for="os in OS_OPTIONS"
            :key="os.key"
            class="agent-os-tab"
            :class="{ active: selectedOs === os.key }"
            :data-os="os.key"
            @click="selectedOs = os.key"
          >
            <iconify-icon :icon="os.icon"></iconify-icon>
            {{ os.label }}
          </button>
        </div>

        <!-- 下载训练应用 -->
        <a class="agent-download" :href="downloadUrl" download>
          <iconify-icon icon="mdi:download"></iconify-icon>
          <div>
            <strong>下载本机训练应用（{{ OS_OPTIONS.find(o => o.key === selectedOs)?.label }}）</strong>
            <span>已绑定你的账号，无需手动配置</span>
          </div>
        </a>

        <!-- 使用步骤（无需手敲命令） -->
        <ol class="agent-steps">
          <li>
            <strong>下载并解压</strong>上面的训练应用压缩包。
          </li>
          <li>
            <strong>双击运行</strong>应用（Windows 为 .exe、macOS 为 .app）。首次运行会
            自动准备训练环境（创建专属虚拟环境并安装 PyTorch，较慢、只需一次），
            之后每次打开都会直接连接。
          </li>
          <li>
            连接成功后，本页顶部会显示「本机训练已连接」，即可进行结构校验、训练与代码导出。
          </li>
        </ol>

        <p class="agent-note">
          <iconify-icon icon="mdi:shield-check-outline"></iconify-icon>
          该应用已内置登录令牌以绑定你的账号，请勿分享给他人。
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
