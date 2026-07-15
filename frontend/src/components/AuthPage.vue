<script setup lang="ts">
import { reactive, ref } from "vue";
import { auth, handleLogin, handleRegister } from "../auth";
import { showToast } from "../store";

const activeTab = ref<"login" | "register">("login");

const loginForm = reactive({ email: "", password: "" });
const registerForm = reactive({ username: "", email: "", password: "", confirmPassword: "" });

async function submitLogin() {
  if (!loginForm.email.trim() || !loginForm.password) {
    showToast("warning", "请输入邮箱和密码。");
    return;
  }
  const ok = await handleLogin({ email: loginForm.email.trim(), password: loginForm.password });
  if (ok) {
    loginForm.password = "";
  }
}

async function submitRegister() {
  const username = registerForm.username.trim();
  const email = registerForm.email.trim();
  if (!username || !email || !registerForm.password || !registerForm.confirmPassword) {
    showToast("warning", "请完整填写注册信息。");
    return;
  }
  if (registerForm.password !== registerForm.confirmPassword) {
    showToast("warning", "两次输入的密码不一致。");
    return;
  }
  const ok = await handleRegister({
    username,
    email,
    password: registerForm.password,
    confirm_password: registerForm.confirmPassword,
  });
  if (ok) {
    registerForm.password = "";
    registerForm.confirmPassword = "";
  }
}
</script>

<template>
  <!-- 独立登录页：登录成功后才能进入模型搭建主界面 -->
  <div class="auth-page">
    <!-- 背景漂浮光斑 -->
    <div class="auth-blob blob-a"></div>
    <div class="auth-blob blob-b"></div>
    <div class="auth-blob blob-c"></div>

    <div class="auth-split">
      <!-- 左侧：品牌展示与动态神经网络 -->
      <aside class="auth-showcase">
        <div class="auth-brand">
          <div class="brand-mark">
            <iconify-icon icon="mdi:brain"></iconify-icon>
          </div>
          <h1>模型工坊</h1>
          <p>深度学习可视化搭建平台</p>
        </div>

        <!-- 数据流动的迷你神经网络 -->
        <svg class="auth-net" viewBox="0 0 240 170" aria-hidden="true">
          <path class="net-edge" d="M 36 36 C 70 36, 86 32, 118 32" />
          <path class="net-edge" d="M 36 36 C 72 50, 84 70, 118 84" />
          <path class="net-edge" d="M 36 85 C 70 70, 86 44, 118 32" />
          <path class="net-edge" d="M 36 85 C 72 85, 84 85, 118 84" />
          <path class="net-edge" d="M 36 85 C 72 102, 84 122, 118 138" />
          <path class="net-edge" d="M 36 134 C 70 120, 86 96, 118 84" />
          <path class="net-edge" d="M 36 134 C 72 134, 84 138, 118 138" />
          <path class="net-edge" d="M 118 32 C 152 40, 170 66, 204 82" />
          <path class="net-edge" d="M 118 84 C 152 84, 170 84, 204 84" />
          <path class="net-edge" d="M 118 138 C 152 128, 170 100, 204 86" />
          <circle class="net-node n1" cx="36" cy="36" r="8" />
          <circle class="net-node n2" cx="36" cy="85" r="8" />
          <circle class="net-node n3" cx="36" cy="134" r="8" />
          <circle class="net-node n4" cx="118" cy="32" r="8" />
          <circle class="net-node n5" cx="118" cy="84" r="8" />
          <circle class="net-node n6" cx="118" cy="138" r="8" />
          <circle class="net-node n7" cx="204" cy="84" r="9" />
        </svg>

        <ul class="auth-features">
          <li><iconify-icon icon="mdi:puzzle-outline"></iconify-icon>单击或拖拽组件，像搭积木一样构建神经网络</li>
          <li><iconify-icon icon="mdi:check-decagram-outline"></iconify-icon>一键校验结构，自动推导张量维度</li>
          <li><iconify-icon icon="mdi:chart-line"></iconify-icon>实时训练曲线与逐轮指标监控</li>
        </ul>
      </aside>

      <!-- 右侧：登录 / 注册表单 -->
      <section class="auth-panel">
        <h2 class="auth-panel-title">{{ activeTab === "login" ? "欢迎回来 👋" : "创建你的账号 ✨" }}</h2>
        <p class="auth-panel-sub">{{ activeTab === "login" ? "登录后继续搭建你的神经网络" : "注册即可开始搭建第一个神经网络" }}</p>

        <div class="auth-tabs">
          <span class="auth-tab-indicator" :class="{ register: activeTab === 'register' }"></span>
          <button
            class="auth-tab"
            :class="{ active: activeTab === 'login' }"
            id="auth-tab-login"
            @click="activeTab = 'login'"
          >登录</button>
          <button
            class="auth-tab"
            :class="{ active: activeTab === 'register' }"
            id="auth-tab-register"
            @click="activeTab = 'register'"
          >注册</button>
        </div>

        <!-- 两个表单叠放于同一网格单元：容器高度固定为较高者，切换只做交叉过渡 -->
        <div class="auth-form-stack">
          <!-- 登录表单 -->
          <form class="auth-form form-login" :class="{ active: activeTab === 'login' }" @submit.prevent="submitLogin">
            <label class="form-field">
              <span>邮箱 Email</span>
              <input id="login-email" type="email" v-model="loginForm.email" placeholder="you@example.com" autocomplete="email">
            </label>
            <label class="form-field">
              <span>密码 Password</span>
              <input id="login-password" type="password" v-model="loginForm.password" placeholder="请输入密码" autocomplete="current-password">
            </label>
            <button class="primary-button auth-submit" id="btn-login" type="submit" :disabled="auth.submitting">
              <iconify-icon v-if="auth.submitting" icon="mdi:loading" class="spin"></iconify-icon>
              <iconify-icon v-else icon="mdi:login-variant"></iconify-icon>
              {{ auth.submitting ? "登录中..." : "登录" }}
            </button>
            <p class="auth-hint">还没有账号？<a @click.prevent="activeTab = 'register'">去注册</a></p>
          </form>

          <!-- 注册表单 -->
          <form class="auth-form form-register" :class="{ active: activeTab === 'register' }" @submit.prevent="submitRegister">
            <label class="form-field">
              <span>用户名 Username</span>
              <input id="register-username" type="text" v-model="registerForm.username" placeholder="2-20 个字符" autocomplete="username">
            </label>
            <label class="form-field">
              <span>邮箱 Email</span>
              <input id="register-email" type="email" v-model="registerForm.email" placeholder="you@example.com" autocomplete="email">
            </label>
            <label class="form-field">
              <span>密码 Password</span>
              <input id="register-password" type="password" v-model="registerForm.password" placeholder="8-128 字符，至少含一个字母和一个数字" autocomplete="new-password">
            </label>
            <label class="form-field">
              <span>确认密码 Confirm Password</span>
              <input id="register-confirm" type="password" v-model="registerForm.confirmPassword" placeholder="再次输入密码" autocomplete="new-password">
            </label>
            <button class="primary-button auth-submit" id="btn-register" type="submit" :disabled="auth.submitting">
              <iconify-icon v-if="auth.submitting" icon="mdi:loading" class="spin"></iconify-icon>
              <iconify-icon v-else icon="mdi:account-plus-outline"></iconify-icon>
              {{ auth.submitting ? "注册中..." : "注册并登录" }}
            </button>
            <p class="auth-hint">已有账号？<a @click.prevent="activeTab = 'login'">去登录</a></p>
          </form>
        </div>
      </section>
    </div>

    <p class="auth-footnote">登录后即可搭建模型、检查结构、训练并保存到自己的项目</p>
  </div>
</template>
