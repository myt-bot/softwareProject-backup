import type {
  CreateProjectPayload,
  CreateProjectResponse,
  DevicesResponse,
  ExportCodeResponse,
  ModelGraph,
  TemplateResponse,
  TemplatesResponse,
  TrainConfig,
  TrainingResult,
  TrainingStatus,
  TrainStartResponse,
  ValidationResult,
} from "../types";

const API_BASE_URL = "http://127.0.0.1:8000";

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


async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
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
    const detail = (data as { detail?: unknown } | null)?.detail ?? data ?? response.statusText;
    throw new Error(`后端请求失败 (${response.status}): ${detail}`);
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


export async function fetchDevices(): Promise<DevicesResponse> {
  return request("/devices");
}


export async function validateModel(modelGraph: ModelGraph): Promise<ValidationResult> {
  return request("/validate", {
    method: "POST",
    body: JSON.stringify({ model: modelGraph }),
  });
}


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


export async function startTraining(modelGraph: ModelGraph, trainConfig: TrainConfig): Promise<TrainStartResponse> {
  return request("/train", {
    method: "POST",
    body: JSON.stringify({
      model: modelGraph,
      train_config: trainConfig,
    }),
  });
}


export async function fetchTrainingStatus(jobId: string): Promise<TrainingStatus> {
  return request(`/train/${encodeURIComponent(jobId)}/status`);
}


export async function fetchTrainingResult(jobId: string): Promise<TrainingResult> {
  return request(`/train/${encodeURIComponent(jobId)}/result`);
}


export async function exportPytorchCode(modelGraph: ModelGraph): Promise<ExportCodeResponse> {
  return request("/export/pytorch", {
    method: "POST",
    body: JSON.stringify({
      model: modelGraph,
      class_name: "MNIST_CNN",
    }),
  });
}
