<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { auth, handleLogout } from "../auth";
import { agent, openHelpModal, ui } from "../store";
import PetMascot from "./PetMascot.vue";

const emit = defineEmits<{ home: []; openTeaching: [] }>();

// 「帮助」下拉：合并新手指南 + 教学辅助两个语义重叠的入口
const helpMenuOpen = ref(false);
const helpRef = ref<HTMLElement | null>(null);

function handleDocumentClick(event: MouseEvent) {
  if (!helpRef.value?.contains(event.target as Node)) {
    helpMenuOpen.value = false;
  }
}
function runHelp(action: () => void) {
  helpMenuOpen.value = false;
  action();
}
onMounted(() => document.addEventListener("click", handleDocumentClick));
onBeforeUnmount(() => document.removeEventListener("click", handleDocumentClick));
</script>

<template>
  <header class="topbar">
    <div class="brand" role="button" title="返回首页" @click="emit('home')">
      <div class="brand-mark">
        <iconify-icon icon="mdi:brain"></iconify-icon>
      </div>
      <h1>模型工坊<span>深度学习可视化搭建平台</span></h1>
    </div>

    <div class="top-actions">
      <!-- 返回首页 -->
      <button class="guide-button" id="btn-home" title="返回首页" @click="emit('home')">
        <iconify-icon icon="mdi:home-variant"></iconify-icon>
        首页
      </button>

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
        <PetMascot :size="20" />
        AI 助手
      </button>

      <!-- 帮助：合并「新手指南」与「教学辅助」 -->
      <div class="help-menu-wrap" ref="helpRef">
        <button
          class="guide-button"
          id="btn-help"
          :class="{ active: helpMenuOpen }"
          title="帮助与教学"
          @click.stop="helpMenuOpen = !helpMenuOpen"
        >
          <iconify-icon icon="mdi:lifebuoy"></iconify-icon>
          帮助
          <iconify-icon icon="mdi:chevron-down" class="help-caret"></iconify-icon>
        </button>
        <div class="help-menu" :class="{ open: helpMenuOpen }">
          <button @click="runHelp(openHelpModal)">
            <iconify-icon icon="mdi:school-outline"></iconify-icon>
            <span><b>新手指南</b><i>四步上手教程与快捷键</i></span>
          </button>
          <button @click="runHelp(() => emit('openTeaching'))">
            <iconify-icon icon="mdi:book-open-page-variant-outline"></iconify-icon>
            <span><b>教学辅助</b><i>逐层讲解、参数说明与修改指导</i></span>
          </button>
        </div>
      </div>

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

<style scoped>
.brand { cursor: pointer; }
</style>
