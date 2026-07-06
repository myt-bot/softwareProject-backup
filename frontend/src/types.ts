// 前端共享类型定义

export interface Point {
  x: number;
  y: number;
}

// 画布节点（一个网络层"积木"）
export interface GraphNode {
  id: string;
  type: string;
  title: string;
  badge: string;
  color: string;
  note?: string;
  hint: string;
  x: number;
  y: number;
  params: Record<string, unknown>;
}

// 连线：[源节点 id, 目标节点 id]
export type Connection = [string, string];

// 左侧组件库条目
export interface LayerPaletteItem {
  type: string;
  desc: string;
  icon: string;
  color: string;
}

export interface LayerGroup {
  title: string;
  layers: LayerPaletteItem[];
}

// —————————————————————————————————————————————
// 后端数据格式（backend/schemas.py）
// —————————————————————————————————————————————

export interface ModelGraphLayer {
  id: string;
  type: string;
  name?: string;
  params?: Record<string, unknown>;
}

export interface ModelGraphConnection {
  source: string;
  target: string;
}

export interface ModelGraph {
  layers: ModelGraphLayer[];
  connections: ModelGraphConnection[];
}

export interface TrainConfig {
  dataset_name: string;
  epochs: number;
  batch_size: number;
  rate: number;
  device: string;
  loss_fn: string;
  optimizer: string;
}

export interface ValidationResult {
  valid?: boolean;
  status?: string;
  message?: string;
}

export interface EpochMetrics {
  epoch?: number;
  train?: { loss?: number; accuracy?: number };
  eval?: { loss?: number; accuracy?: number };
}

export interface TrainingStatus {
  job_id?: string;
  status?: string;
  current_epoch?: number;
  total_epochs?: number;
  progress?: number;
  metrics?: EpochMetrics[];
  error?: string;
}

export interface TrainingResult extends TrainingStatus {
  accuracy?: number;
  loss?: number;
  device?: string;
}

export interface TrainStartResponse extends TrainingStatus {
  job_status?: string;
}

// 前端本地维护的训练任务（底部任务面板）
export interface TrainingJob extends TrainingStatus {
  trainConfig?: TrainConfig;
}

export interface DevicesResponse {
  default_device?: string;
}

export interface TemplatesResponse {
  count?: number;
}

export interface TemplateResponse {
  model?: ModelGraph;
}

export interface CreateProjectPayload {
  user_id: string;
  name: string;
  model_graph: ModelGraph;
  description?: string;
}

export interface CreateProjectResponse {
  data?: { name?: string };
}

export type ExportCodeResponse =
  | string
  | {
      code?: string;
      source_code?: string;
    };

// —————————————————————————————————————————————
// UI
// —————————————————————————————————————————————

export type ToastType = "success" | "error" | "warning" | "info";

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
  leaving: boolean;
}

// 训练监控页左侧 minimap 的层
export interface MonitorLayer {
  type: string;
  color: string;
}
