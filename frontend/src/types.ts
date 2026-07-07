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
  // 数据集下载目录与训练产物保存目录（留空使用后端默认位置）
  data_dir?: string;
  artifacts_dir?: string;
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
  current_step?: number;
  total_steps?: number;
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
  // 云端中转架构：任务下发的 Agent 在线状态
  agent_status?: "online" | "offline";
  agent_id?: string;
  message?: string;
}

// —————————————————————————————————————————————
// 云端中转 / 本机 Agent（分布式训练）
// —————————————————————————————————————————————

export interface DeviceSummary {
  available_devices?: string[];
  default_device?: string;
  cuda_available?: boolean;
  cuda_device_count?: number;
  cuda_devices?: Array<{ index?: number; name?: string }> | string[];
}

export interface AgentStatus {
  type?: string;
  online: boolean;
  agent_id?: string;
  runtime_version?: string;
  platform?: string;
  device_summary?: DeviceSummary;
}

// 服务器通过客户端 WebSocket 推送的消息
export interface WsMessage {
  type: string;
  job_id?: string;
  status?: string;
  current_epoch?: number;
  total_epochs?: number;
  current_step?: number;
  total_steps?: number;
  progress?: number;
  metrics?: EpochMetrics[];
  loss?: number;
  accuracy?: number;
  device?: string;
  artifacts?: unknown;
  error?: string;
  // agent_status
  online?: boolean;
  agent_id?: string;
  runtime_version?: string;
  platform?: string;
  device_summary?: DeviceSummary;
  // command_ack
  command?: string;
  accepted?: boolean;
  message?: string;
  // agent_response（校验/设备/导出的请求-响应）
  request_id?: string;
  ok?: boolean;
  data?: unknown;
}

export interface CancelTrainingResponse {
  job_id?: string;
  cancelled?: boolean;
  status?: string;
}

// —————————————————————————————————————————————
// 认证（M1 模块）
// —————————————————————————————————————————————

export interface AuthUser {
  id?: string;
  username?: string;
  email?: string;
  [key: string]: unknown;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

// 前端本地维护的训练任务（底部任务面板）
export interface TrainingJob extends TrainingStatus {
  trainConfig?: TrainConfig;
}

export interface DevicesResponse {
  default_device?: string;
  available_devices?: string[];
  cuda_available?: boolean;
  cuda_device_count?: number;
  cuda_devices?: string[];
}

export interface TemplateMeta {
  key: string;
  name: string;
  description?: string;
  family?: string;
  input_shape?: number[];
  output_shape?: number[];
}

export interface TemplatesResponse {
  count?: number;
  data?: TemplateMeta[];
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

// 已保存的项目（模型）
export interface ProjectMeta {
  id: string;
  user_id?: string;
  name: string;
  description?: string;
  model_graph?: ModelGraph;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectsResponse {
  status?: string;
  data?: ProjectMeta[];
  count?: number;
}

export interface ProjectResponse {
  status?: string;
  data?: ProjectMeta;
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
