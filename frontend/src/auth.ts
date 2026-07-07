// 登录状态管理（M1 认证模块的前端侧）。
// token 持久化到 localStorage，刷新页面后通过 /auth/me 恢复会话。

import { reactive } from "vue";
import {
  fetchCurrentUser,
  isBackendUnavailable,
  loginUser,
  registerUser,
  setAuthToken,
} from "./api/client";
import { showToast } from "./store";
import type { LoginPayload, RegisterPayload, AuthUser } from "./types";
import { connectClientWebSocket, disconnectClientWebSocket } from "./ws";

const AUTH_TOKEN_KEY = "model-workshop-token";

export const auth = reactive({
  token: null as string | null,
  user: null as AuthUser | null,
  submitting: false,
  // 启动时正在用本地 token 恢复会话（期间显示加载屏，避免登录页闪现）
  restoring: false,
});

export function isLoggedIn() {
  return Boolean(auth.token && auth.user);
}


function applySession(token: string, user: AuthUser) {
  auth.token = token;
  auth.user = user;
  setAuthToken(token);
  // 建立与云端的持久化 WebSocket（接收 Agent 状态与训练进度）
  connectClientWebSocket(token);
  try {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // localStorage 不可用时仅保留内存会话
  }
}


function clearSession() {
  auth.token = null;
  auth.user = null;
  setAuthToken(null);
  disconnectClientWebSocket();
  try {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
}


// 应用启动时恢复上次会话
export async function initializeAuth() {
  let token: string | null = null;
  try {
    token = localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return;
  }
  if (!token) return;

  auth.restoring = true;
  auth.token = token;
  setAuthToken(token);
  try {
    const result = await fetchCurrentUser();
    if (result?.data) {
      auth.user = result.data;
      // 会话恢复成功后建立持久化 WebSocket
      connectClientWebSocket(token);
      return;
    }
    clearSession();
  } catch (error) {
    // 令牌失效则清除；后端未启动也回到登录页（登录本身同样需要后端）
    clearSession();
    if (isBackendUnavailable(error)) {
      showToast("error", "无法连接后端服务，请启动后端后重新登录。");
    }
  } finally {
    auth.restoring = false;
  }
}


export async function handleLogin(payload: LoginPayload): Promise<boolean> {
  if (auth.submitting) return false;
  auth.submitting = true;
  try {
    const result = await loginUser(payload);
    applySession(result.access_token, result.user);
    showToast("success", `欢迎回来，${result.user?.username || result.user?.email || "用户"}！`);
    return true;
  } catch (error) {
    showToast("error", (error as Error)?.message || "登录失败");
    return false;
  } finally {
    auth.submitting = false;
  }
}


export async function handleRegister(payload: RegisterPayload): Promise<boolean> {
  if (auth.submitting) return false;
  auth.submitting = true;
  try {
    const result = await registerUser(payload);
    applySession(result.access_token, result.user);
    showToast("success", `注册成功，欢迎 ${result.user?.username || "新用户"}！`);
    return true;
  } catch (error) {
    showToast("error", (error as Error)?.message || "注册失败");
    return false;
  } finally {
    auth.submitting = false;
  }
}


export function handleLogout() {
  clearSession();
  showToast("info", "已退出登录。");
}
