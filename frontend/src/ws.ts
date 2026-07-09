// 浏览器与云端服务器之间的持久化 WebSocket。
//
// 分布式训练架构下，云端只做中转：本机 Agent 把训练进度/结果回传给云端，
// 云端再通过这条 WebSocket 实时推送给浏览器。浏览器不再轮询训练状态。
//
// 收到的消息：
//   agent_status     —— 本机 Agent 上线/离线及设备信息
//   training_update  —— 训练进度（逐 batch / 逐 epoch）
//   training_result  —— 训练最终结果
//   command_ack      —— Agent 对指令的回执（如拒绝训练）

import { clientWebSocketUrl } from "./api/client";
import { applyResultMessage, applyStatusMessage, monitor } from "./monitor";
import {
  agent,
  getTrainingStatusLabel,
  setAgentStatus,
  setTrainingJob,
  showToast,
  store,
} from "./store";
import type { TrainingResult, TrainingStatus, WsMessage } from "./types";

let socket: WebSocket | null = null;
let currentToken: string | null = null;
let reconnectTimer: number | null = null;
let closedByUser = false;

// 请求-响应类操作（校验/设备/导出）的等待表：request_id -> resolver
interface PendingRequest {
  resolve: (data: unknown) => void;
  reject: (error: Error) => void;
  timer: number;
}
const pending = new Map<string, PendingRequest>();
let requestSeq = 0;


export function isSocketOpen(): boolean {
  return socket?.readyState === WebSocket.OPEN;
}


// 通过 WebSocket 请求本机 Agent 执行一次操作（校验/设备/导出），返回其结果。
export function requestAgent<T = unknown>(action: string, payload: unknown = {}, timeoutMs = 15000): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (!isSocketOpen()) {
      reject(new Error("与服务器的实时连接尚未建立。"));
      return;
    }
    const requestId = `req_${++requestSeq}_${Date.now()}`;
    const timer = window.setTimeout(() => {
      pending.delete(requestId);
      reject(new Error("本机 Agent 未在预期时间内响应，请确认本地训练 Agent 正在运行。"));
    }, timeoutMs);
    pending.set(requestId, { resolve: resolve as (d: unknown) => void, reject, timer });
    socket!.send(JSON.stringify({ type: "agent_request", request_id: requestId, action, payload }));
  });
}


export function connectClientWebSocket(token: string) {
  closedByUser = false;
  currentToken = token;
  openSocket();
}


export function disconnectClientWebSocket() {
  closedByUser = true;
  currentToken = null;
  agent.online = false;
  rejectAllPending("连接已关闭。");
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    socket.onclose = null;
    socket.close();
    socket = null;
  }
}


function rejectAllPending(reason: string) {
  for (const [, entry] of pending) {
    clearTimeout(entry.timer);
    entry.reject(new Error(reason));
  }
  pending.clear();
}


function openSocket() {
  if (!currentToken) return;
  try {
    socket = new WebSocket(clientWebSocketUrl(currentToken));
  } catch {
    scheduleReconnect();
    return;
  }

  socket.onmessage = event => {
    let message: WsMessage;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    handleMessage(message);
  };

  socket.onclose = () => {
    socket = null;
    agent.online = false;
    rejectAllPending("与服务器的连接中断。");
    if (!closedByUser) scheduleReconnect();
  };

  socket.onerror = () => {
    // 错误后由 onclose 触发重连
    socket?.close();
  };
}


function scheduleReconnect() {
  if (closedByUser || reconnectTimer) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null;
    openSocket();
  }, 3000);
}


function handleMessage(message: WsMessage) {
  switch (message.type) {
    case "agent_status":
      setAgentStatus({
        online: Boolean(message.online),
        agent_id: message.agent_id,
        runtime_version: message.runtime_version,
        platform: message.platform,
        device_summary: message.device_summary,
      });
      break;

    case "training_update":
      routeTrainingMessage(message, false);
      break;

    case "training_result":
      routeTrainingMessage(message, true);
      break;

    case "command_ack":
      if (message.accepted === false) {
        showToast("error", message.message || "本机 Agent 拒绝了训练指令。");
      }
      break;

    case "agent_response": {
      const entry = message.request_id ? pending.get(message.request_id) : undefined;
      if (entry && message.request_id) {
        clearTimeout(entry.timer);
        pending.delete(message.request_id);
        if (message.ok) {
          entry.resolve(message.data);
        } else {
          entry.reject(new Error(message.error || "本机 Agent 处理失败。"));
        }
      }
      break;
    }
  }
}


// 把训练消息路由到对应画布（更新任务面板）与监控页（如正在展示该任务）
function routeTrainingMessage(message: WsMessage, isFinal: boolean) {
  const jobId = message.job_id;
  if (!jobId) return;

  const canvas = store.canvases.find(item => item.trainingJob?.job_id === jobId);
  if (canvas) {
    setTrainingJob(canvas, {
      job_id: jobId,
      status: message.status,
      current_epoch: message.current_epoch,
      total_epochs: message.total_epochs,
      progress: isFinal ? 1 : message.progress,
      metrics: message.metrics,
      dataset_progress: message.dataset_progress,
    });
  }

  // 监控页正在展示该任务时，渲染实时曲线
  if (monitor.visible && monitor.jobId === jobId) {
    if (isFinal) {
      applyResultMessage(messageToResult(message));
    } else {
      applyStatusMessage(messageToStatus(message));
    }
  }

  if (isFinal) {
    const label = getTrainingStatusLabel(message.status);
    const name = canvas?.name || "训练";
    if (message.status === "completed") {
      const acc = typeof message.accuracy === "number" ? `${(message.accuracy * 100).toFixed(1)}%` : "未知";
      showToast("success", `${name} 训练完成，accuracy=${acc}`);
    } else if (message.status === "failed") {
      showToast("error", `${name} 训练失败：${message.error || "未知错误"}`);
    } else if (message.status === "cancelled") {
      showToast("warning", `${name} 训练已取消。`);
    } else {
      showToast("info", `${name} 训练${label}。`);
    }
  }
}


function messageToStatus(message: WsMessage): TrainingStatus {
  return {
    job_id: message.job_id,
    status: message.status,
    current_epoch: message.current_epoch,
    total_epochs: message.total_epochs,
    current_step: message.current_step,
    total_steps: message.total_steps,
    progress: message.progress,
    metrics: message.metrics,
    dataset_progress: message.dataset_progress,
    error: message.error,
  };
}


function messageToResult(message: WsMessage): TrainingResult {
  return {
    job_id: message.job_id,
    status: message.status,
    accuracy: message.accuracy,
    loss: message.loss,
    device: message.device,
    metrics: message.metrics,
    dataset_progress: message.dataset_progress,
    error: message.error,
  };
}
