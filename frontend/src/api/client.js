const API_BASE_URL = "http://127.0.0.1:8000";


class BackendNotImplementedError extends Error {
  constructor(path) {
    super(`后端接口 ${path} 暂未实现`);
    this.name = "BackendNotImplementedError";
    this.path = path;
  }
}


async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (error) {
    throw new Error(`无法连接后端服务 ${API_BASE_URL}，请确认 FastAPI 已启动。`);
  }

  const text = await response.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const detail = data?.detail || data || response.statusText;
    throw new Error(`后端请求失败 (${response.status}): ${detail}`);
  }

  if (data === null || data === undefined || data === "") {
    throw new BackendNotImplementedError(path);
  }

  return data;
}


export function isBackendNotImplemented(error) {
  return error?.name === "BackendNotImplementedError";
}


export async function fetchHealth() {
  return request("/health");
}


export async function fetchDevices() {
  return request("/devices");
}


export async function validateModel(modelGraph) {
  return request("/validate", {
    method: "POST",
    body: JSON.stringify({ model: modelGraph }),
  });
}


export async function fetchProjectTemplates() {
  return request("/projects/templates");
}


export async function fetchProjectTemplate(templateName) {
  return request(`/projects/templates/${encodeURIComponent(templateName)}`);
}


export async function createProject(project) {
  return request("/projects", {
    method: "POST",
    body: JSON.stringify(project),
  });
}


export async function createProjectFromTemplate(templateProject) {
  return request("/projects/from-template", {
    method: "POST",
    body: JSON.stringify(templateProject),
  });
}


export async function startTraining(modelGraph, trainConfig) {
  return request("/train", {
    method: "POST",
    body: JSON.stringify({
      model: modelGraph,
      train_config: trainConfig,
    }),
  });
}


export async function fetchTrainingStatus(jobId) {
  return request(`/train/${encodeURIComponent(jobId)}/status`);
}


export async function fetchTrainingResult(jobId) {
  return request(`/train/${encodeURIComponent(jobId)}/result`);
}


export async function exportPytorchCode(modelGraph) {
  return request("/export/pytorch", {
    method: "POST",
    body: JSON.stringify({
      model: modelGraph,
      class_name: "MNIST_CNN",
    }),
  });
}
