import type {
  AgentStatus,
  CancelTrainingResponse,
  CreateProjectPayload,
  CreateProjectResponse,
  LoginPayload,
  ModelGraph,
  ValidationResult,
  RegisterPayload,
  ProjectResponse,
  ProjectsResponse,
  TemplateResponse,
  TemplatesResponse,
  TokenResponse,
  TrainConfig,
  TrainingResult,
  TrainingStatus,
  TrainStartResponse,
  AuthUser,
} from "../types";

// 后端地址：生产构建时由 VITE_API_BASE_URL 注入（见 frontend/.env.production），
// 未设置时回退到本地开发地址。
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

// 浏览器与云端服务器的持久化 WebSocket 地址（接收 Agent 状态与训练进度）
export function clientWebSocketUrl(token: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/client/ws?token=${encodeURIComponent(token)}`;
}

// 本机训练应用的下载地址（内含用户令牌，双击即自动连接绑定账号）
export function agentDownloadUrl(token: string, platform?: string): string {
  const base = `${API_BASE_URL}/agent/download?token=${encodeURIComponent(token)}`;
  return platform ? `${base}&platform=${encodeURIComponent(platform)}` : base;
}

// 获取长期有效的 Agent 令牌（供用户手动更新已下载应用 config.json 的 token）
export async function fetchAgentToken(token: string): Promise<{ token: string; expires_days?: number }> {
  return request(`/agent/token?token=${encodeURIComponent(token)}`);
}

// 结构校验与维度推导：在云端完成，不依赖本地 Agent（训练才需要 Agent）
export async function validateModelStructure(model: ModelGraph): Promise<ValidationResult> {
  return request("/validate", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

// 请求超时：后端接口都是快速返回的（训练在后台线程执行），
// 超过该时间视为后端未启动或无响应，避免按钮永远卡在加载态。
const REQUEST_TIMEOUT_MS = 10_000;


export class BackendNotImplementedError extends Error {
  path: string;

  constructor(path: string) {
    super(`后端接口 ${path} 暂未实现`);
    this.name = "BackendNotImplementedError";
    this.path = path;
  }
}


export class BackendUnavailableError extends Error {
  constructor() {
    super(`无法连接后端服务 ${API_BASE_URL}，请确认 FastAPI 已启动。`);
    this.name = "BackendUnavailableError";
  }
}


// 登录后由 auth 模块注入的 JWT，自动附加到所有请求头
let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
}


async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...(options.headers || {}),
      },
      signal: options.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch {
    // 连接被拒绝、DNS/网络错误、超时（连接挂起）都视为后端不可用
    throw new BackendUnavailableError();
  }

  const text = await response.text();
  let data: unknown = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const body = data as { detail?: unknown; message?: unknown } | null;
    // FastAPI 校验错误在 detail，业务错误在 message
    const detail = body?.detail ?? body?.message ?? data ?? response.statusText;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(`后端请求失败 (${response.status}): ${message}`);
  }

  if (data === null || data === undefined || data === "") {
    throw new BackendNotImplementedError(path);
  }

  return data as T;
}


export function isBackendNotImplemented(error: unknown): boolean {
  return (error as Error | null)?.name === "BackendNotImplementedError";
}


export function isBackendUnavailable(error: unknown): boolean {
  return (error as Error | null)?.name === "BackendUnavailableError";
}


export async function fetchHealth(): Promise<unknown> {
  return request("/health");
}


// —————————————————————————————————————————————
// 认证（M1 模块）
// —————————————————————————————————————————————

export async function registerUser(payload: RegisterPayload): Promise<TokenResponse> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


export async function loginUser(payload: LoginPayload): Promise<TokenResponse> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


export async function fetchCurrentUser(): Promise<{ status?: string; data?: AuthUser }> {
  return request("/auth/me");
}


// 注：结构校验 /validate、设备查询 /devices、代码导出 /export 已迁移到
// 用户本机 Agent（云端不含 PyTorch），前端改为通过 WebSocket 的 requestAgent 调用。

export async function fetchProjectTemplates(): Promise<TemplatesResponse> {
  return request("/projects/templates");
}


export async function fetchProjectTemplate(templateName: string): Promise<TemplateResponse> {
  return request(`/projects/templates/${encodeURIComponent(templateName)}`);
}


export async function createProject(project: CreateProjectPayload): Promise<CreateProjectResponse> {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify(project),
  });
}


export async function createProjectFromTemplate(templateProject: unknown): Promise<unknown> {
  return request("/projects/from-template", {
    method: "POST",
    body: JSON.stringify(templateProject),
  });
}


export async function listProjects(userId: string): Promise<ProjectsResponse> {
  return request(`/projects?user_id=${encodeURIComponent(userId)}`);
}


export async function getProject(projectId: string): Promise<ProjectResponse> {
  return request(`/projects/${encodeURIComponent(projectId)}`);
}


export async function deleteProject(projectId: string): Promise<{ status?: string; message?: string }> {
  return request(`/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}


// 云端只做任务中转，训练在用户本机 Agent 执行；这些接口都需要 user_id。
export async function startTraining(
  modelGraph: ModelGraph,
  trainConfig: TrainConfig,
  userId: string,
): Promise<TrainStartResponse> {
  return request(`/train?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
    body: JSON.stringify({
      model: modelGraph,
      train_config: trainConfig,
    }),
  });
}


export async function fetchTrainingStatus(jobId: string, userId: string): Promise<TrainingStatus> {
  return request(`/train/${encodeURIComponent(jobId)}/status?user_id=${encodeURIComponent(userId)}`);
}


export async function fetchTrainingResult(jobId: string, userId: string): Promise<TrainingResult> {
  return request(`/train/${encodeURIComponent(jobId)}/result?user_id=${encodeURIComponent(userId)}`);
}


export async function cancelTraining(jobId: string, userId: string): Promise<CancelTrainingResponse> {
  return request(`/train/${encodeURIComponent(jobId)}/cancel?user_id=${encodeURIComponent(userId)}`, {
    method: "POST",
  });
}


export async function fetchAgentStatus(userId: string): Promise<AgentStatus> {
  return request(`/agents/status?user_id=${encodeURIComponent(userId)}`);
}
