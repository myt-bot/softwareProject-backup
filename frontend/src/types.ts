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
  // 自定义容器（type === "Container"）：内部子图 + 折叠态
  subgraph?: SubGraph;
  collapsed?: boolean;
}

// 连线端点：普通层为节点 id；容器端口为 "容器id::内部端口层id"（见 store.PORT_SEP）
// 连线：[源端点, 目标端点]
export type Connection = [string, string];

// —————————————————————————————————————————————
// 自定义容器（组合容器）
// —————————————————————————————————————————————

// 容器内部子图：一整张可编辑的模型图。里面的 Input / Output 节点即容器对外的
// 输入 / 输出端口（多个 Input = 多输入，多个 Output = 多输出）。
export interface SubGraph {
  nodes: GraphNode[];
  connections: Connection[];
  // 内部 Input 端口层 id 列表 / 内部 Output 端口层 id 列表（序列化时按此顺序）
  inputs: string[];
  outputs: string[];
  // 子图自己的节点计数器（进入子画板编辑时用于生成不冲突的新节点 id）
  nodeCounters?: Record<string, number>;
}

// 会话内可复用的容器定义（左侧"我的容器"）
export interface ContainerDef {
  defId: string;
  name: string;
  color: string;
  subgraph: SubGraph;
}

// 左侧组件库条目
export interface LayerPaletteItem {
  type: string;
  desc: string;
  icon: string;
  color: string;
  // 悬浮时给新手看的"是什么/何时用"大白话说明
  hint?: string;
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
  // 自定义容器序列化：内部子图（后端格式）与暴露参数绑定
  subgraph?: {
    layers: ModelGraphLayer[];
    connections: ModelGraphConnection[];
    inputs: string[];
    outputs: string[];
  };
  param_bindings?: Array<{ param: string; target: string; key: string }>;
}

export interface ModelGraphConnection {
  source: string;
  target: string;
}

export interface ModelGraph {
  layers: ModelGraphLayer[];
  connections: ModelGraphConnection[];
  train_config?: TrainConfig;
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

export interface LayerShapeInfo {
  status?: string;
  layer_type?: string;
  input_shape?: number[] | null;
  output_shape?: number[] | null;
  expected_in_features?: number;
  actual_in_features?: number;
}

export interface ValidationResult {
  valid?: boolean;
  status?: string;
  message?: string;
  errors?: string[];
  warnings?: string[];
  shapes?: Record<string, LayerShapeInfo>;
}

export interface EpochMetrics {
  epoch?: number;
  train?: { loss?: number; accuracy?: number };
  eval?: { loss?: number; accuracy?: number };
}

export interface DatasetProgress {
  dataset_name?: string;
  status?: "pending" | "checking" | "downloading" | "ready" | "cancelled" | "failed";
  percent?: number;
  downloaded_bytes?: number;
  total_bytes?: number;
  file_name?: string;
  message?: string;
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
  dataset_progress?: DatasetProgress | null;
  error?: string;
}

export interface TrainingResult extends TrainingStatus {
  accuracy?: number;
  loss?: number;
  device?: string;
  // 训练产物保存路径（本机 Agent 回传）
  artifacts?: { model_path?: string; metrics_path?: string };
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
  layer_id?: string;
  layer_type?: string;
  layer_index?: number;
  current_epoch?: number;
  total_epochs?: number;
  current_step?: number;
  total_steps?: number;
  progress?: number;
  metrics?: EpochMetrics[];
  dataset_progress?: DatasetProgress | null;
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
  modelSummary?: TrainingModelSummary;
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
  id?: string;
  type: string;
  color: string;
  row?: number; // 拓扑层（阶段，纵向）
  col?: number; // 层内列（并行分支，横向）
}

export interface MonitorEdge {
  source: string; // 源节点 id
  target: string; // 目标节点 id
}

export interface TrainingModelSummary {
  modelName: string;
  inputShape: number[] | null;
  numClasses: number | null;
  paramCount: number;
}
