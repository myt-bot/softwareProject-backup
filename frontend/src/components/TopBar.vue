<script setup lang="ts">
import { auth, handleLogout } from "../auth";
import { agent, openHelpModal, ui } from "../store";
</script>

<template>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark">
        <iconify-icon icon="mdi:brain"></iconify-icon>
      </div>
      <h1>模型工坊<span>深度学习可视化搭建平台</span></h1>
    </div>

    <div class="top-actions">
      <!-- 本机训练 Agent 连接状态（点击查看如何启动本地 Agent） -->
      <button
        class="agent-chip"
        :class="agent.online ? 'online' : 'offline'"
        id="btn-agent-status"
        :title="agent.online ? '本机训练 Agent 已连接' : '本机训练 Agent 未连接，点击查看如何启动'"
        @click="ui.agentModalOpen = true"
      >
        <span class="agent-dot"></span>
        {{ agent.online ? "本机训练已连接" : "本机训练未连接" }}
      </button>

      <!-- AI 助手：用自然语言让大模型帮你建模 / 答疑 -->
      <button
        class="guide-button assistant-button"
        :class="{ active: ui.assistantOpen }"
        id="btn-assistant"
        title="打开 AI 助手"
        @click="ui.assistantOpen = !ui.assistantOpen"
      >
        <iconify-icon icon="mdi:robot-happy-outline"></iconify-icon>
        AI 助手
      </button>

      <button class="guide-button" id="btn-help" title="打开新手指南" @click="openHelpModal">
        <iconify-icon icon="mdi:school-outline"></iconify-icon>
        新手指南
      </button>

      <!-- 存储位置设置（数据集下载 / 结果保存目录） -->
      <button class="icon-button" id="btn-storage-settings" title="存储位置设置" @click="ui.storageSettingsOpen = true">
        <iconify-icon icon="mdi:folder-cog-outline"></iconify-icon>
      </button>

      <!-- 当前登录用户（退出后回到登录页） -->
      <div class="user-chip" id="user-chip" :title="auth.user?.email || ''">
        <div class="avatar"></div>
        <span class="user-name">{{ auth.user?.username || auth.user?.email }}</span>
        <button class="icon-button" id="btn-logout" title="退出登录" @click="handleLogout">
          <iconify-icon icon="mdi:logout-variant"></iconify-icon>
        </button>
      </div>
    </div>
  </header>
</template>
