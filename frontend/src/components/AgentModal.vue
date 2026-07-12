<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { agentDownloadUrl, fetchAgentToken } from "../api/client";
import { auth } from "../auth";
import { agent, showToast, ui } from "../store";

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

// 下载链接内含用户令牌与目标平台：下载的应用已绑定账号，启动后自动连接
const downloadUrl = computed(() => agentDownloadUrl(auth.token ?? "", selectedOs.value));

const gpuName = computed(() => {
  const dev = agent.deviceSummary?.cuda_devices?.[0];
  return typeof dev === "string" ? dev : dev?.name || "GPU";
});

// 首次准备环境需下载的依赖大小（CUDA 版 PyTorch 较大；macOS 默认版较小）
const depsSize = computed(() => (selectedOs.value === "macos" ? "约 200 MB" : "约 2–3 GB"));

// 长期有效的 Agent 令牌（令牌失效时在应用界面里粘贴更新）
const agentToken = ref("");
const tokenDays = ref(365);

watch(
  () => ui.agentModalOpen,
  async open => {
    if (!open || !auth.token) return;
    try {
      const res = await fetchAgentToken(auth.token);
      agentToken.value = res.token;
      if (res.expires_days) tokenDays.value = res.expires_days;
    } catch {
      agentToken.value = "";
    }
  }
);

async function copyToken() {
  if (!agentToken.value) return;
  try {
    await navigator.clipboard.writeText(agentToken.value);
    showToast("success", "令牌已复制，粘贴到应用界面的令牌输入框即可。");
  } catch {
    showToast("warning", "当前浏览器不支持自动复制，请手动选中复制。");
  }
}

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

        <!-- 下载训练应用（醒目脉冲，提示可点击下载） -->
        <a class="agent-download pulse" :href="downloadUrl" download id="btn-agent-download">
          <iconify-icon icon="mdi:download"></iconify-icon>
          <div>
            <strong>点击下载本机训练应用（{{ OS_OPTIONS.find(o => o.key === selectedOs)?.label }}）</strong>
            <span>已绑定你的账号，无需手动配置</span>
          </div>
          <span class="agent-download-cue">点此下载 <iconify-icon icon="mdi:arrow-down-bold"></iconify-icon></span>
        </a>

        <!-- 使用步骤（无需手敲命令） -->
        <ol class="agent-steps">
          <li>
            <strong>下载并解压</strong>上面的压缩包（首次请照包内 <code>README</code> 说明完成准备）。
          </li>
          <li>
            <strong>双击启动</strong>：Windows 双击 <strong>「启动.bat」</strong>、macOS / Linux 双击
            <strong>「启动.command」</strong>。弹出界面后点 <strong>「准备训练环境」</strong> 下载依赖
            （首次含 PyTorch，<strong>{{ depsSize }}</strong>，较慢、只需一次），再点
            <strong>「启动并连接云端」</strong>；之后每次启动直接连接。
          </li>
          <li>
            连接成功后，本页顶部会显示「本机训练已连接」，即可进行结构校验、训练与代码导出。
          </li>
        </ol>

        <!-- 令牌失效时手动更新（醒目红色区域） -->
        <div class="agent-token-box">
          <div class="agent-token-head">
            <iconify-icon icon="mdi:alert-circle-outline"></iconify-icon>
            <strong>应用连不上 / 提示令牌失效？无需重新下载</strong>
          </div>
          <p>
            复制下面这串<b>长期有效令牌</b>（{{ tokenDays }} 天），直接粘贴到本机训练应用界面里的
            <b>令牌输入框</b>，然后重新连接即可。
          </p>
          <div class="agent-token-value">
            <code>{{ agentToken || "加载中…" }}</code>
            <button class="icon-button" title="复制令牌" :disabled="!agentToken" @click="copyToken">
              <iconify-icon icon="mdi:content-copy"></iconify-icon>
            </button>
          </div>
        </div>

        <p class="agent-note">
          <iconify-icon icon="mdi:shield-check-outline"></iconify-icon>
          令牌用于把应用绑定到你的账号，请勿分享给他人。
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
