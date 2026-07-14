// AI 助手：把后端下发的 tool_request 命令，落到前端现有的建模函数上执行。
// 命令名与后端 command_specs() 一一对应；执行结果回传后端喂回大模型。

import {
  activeCanvas,
  agent,
  datasetChoices,
  datasetInputShape,
  getCurrentModelGraph,
  getTrainConfig,
  resetValidationAfterGraphChange,
  setDataset,
  storagePaths,
  templateLibrary,
  updateNodeParam,
  store,
} from "./store";
import {
  addNodeFromLayer,
  applyTemplateGraph,
  autoLayoutGraph,
  deleteNodeById,
  drawLines,
  recordHistory,
  redrawAfterDomUpdate,
} from "./canvas";
import {
  fetchProjectTemplate,
  fetchProjectTemplates,
  validateModelStructure,
} from "./api/client";
import { handleExportCode, handleStartTraining, handleValidateModel } from "./actions";
import { handleStopTraining, monitor } from "./monitor";

export interface AssistantCommandResult {
  ok: boolean;
  result?: unknown;
  error?: string;
}

// 训练超参数的合法取值（与「训练超参数」弹窗、后端 _build_optimizer / _build_loss_fn 对齐）
const OPTIMIZERS = ["sgd", "adam", "adamw", "rmsprop", "adagrad", "adadelta"];
const LOSSES = ["cross_entropy", "nll", "mse", "l1", "smooth_l1"];

// 把训练监控（monitor）的状态压成一份结构化结果，供 AI 就训练结果答疑。
// 只反映真实训练（live / 有 result / 已有逐轮数据）；未真正训练时明确告知，避免编造。
function summarizeTraining() {
  const m = monitor;
  const s = m.series;
  const n = Math.max(s.loss.length, s.valLoss.length, s.trainAcc.length, s.valAcc.length);
  const started = m.live || m.result != null || n > 0;
  if (!started) {
    return {
      started: false,
      note: "本会话尚未进行真实训练。请先在页面点「开始训练」，或用 start_training 发起（需本机 Agent 在线）。",
    };
  }
  const metricsPerEpoch = [];
  for (let i = 0; i < n; i++) {
    metricsPerEpoch.push({
      epoch: i + 1,
      loss: s.loss[i] ?? null,
      val_loss: s.valLoss[i] ?? null,
      train_acc: s.trainAcc[i] ?? null,
      val_acc: s.valAcc[i] ?? null,
    });
  }
  const status = m.error ? "failed" : m.result?.status || (m.state === "completed" ? "completed" : "running");
  return {
    started: true,
    live: m.live,
    status,
    running: m.state === "running" && m.result == null && !m.error,
    progress: Math.round((m.result ? 1 : m.progress) * 100) / 100,
    current_epoch: m.currentEpoch,
    total_epochs: s.totalEpochs || m.hyperparams.epochs,
    final_accuracy: m.result?.accuracy ?? (s.valAcc.length ? s.valAcc[s.valAcc.length - 1] : null),
    final_loss: m.result?.loss ?? (s.loss.length ? s.loss[s.loss.length - 1] : null),
    device: m.result?.device ?? m.hyperparams.device,
    dataset: store.dataset,
    hyperparams: m.hyperparams,
    model_summary: m.modelSummary,
    param_count: m.paramCount,
    metrics_per_epoch: metricsPerEpoch,
    error: m.error || m.result?.error || null,
    artifacts: m.result?.artifacts || null,
  };
}

// 随每条用户消息上送的当前项目快照（后端据此了解现状、少走工具往返）
export function buildAssistantSnapshot() {
  return {
    model_graph: getCurrentModelGraph(),
    training: getTrainConfig(),
  };
}

// 新节点落点：在现有节点下方错开，避免重叠
function nextNodePosition() {
  const nodes = activeCanvas().nodes;
  if (!nodes.length) return { x: 480, y: 120 };
  const maxY = Math.max(...nodes.map(n => n.y));
  return { x: 480, y: maxY + 150 };
}

// 执行一条来自大模型的命令，返回 { ok, result, error }
export async function executeAssistantCommand(
  command: string,
  args: Record<string, unknown> = {}
): Promise<AssistantCommandResult> {
  try {
    switch (command) {
      case "get_model_graph":
        return { ok: true, result: getCurrentModelGraph() };

      case "list_nodes":
        return {
          ok: true,
          result: activeCanvas().nodes.map(n => ({ id: n.id, type: n.type, title: n.title })),
        };

      case "list_canvases": {
        const activeId = activeCanvas().id;
        return {
          ok: true,
          result: store.canvases.map((c, i) => ({
            index: i + 1, // 第几个（从 1 开始）
            id: c.id,
            name: c.name,
            node_count: c.nodes.length,
            active: c.id === activeId, // 是否当前焦点画布
          })),
        };
      }

      case "get_canvas_graph": {
        // 读取指定画布的结构与维度，不改变用户当前焦点。用 index / name / id 之一定位。
        const canvases = store.canvases;
        let target: (typeof canvases)[number] | undefined;
        if (args.index != null) {
          const i = Math.trunc(Number(args.index));
          if (!Number.isFinite(i) || i < 1 || i > canvases.length) {
            return { ok: false, error: `没有第 ${args.index} 个画布（当前共 ${canvases.length} 个）` };
          }
          target = canvases[i - 1];
        } else if (args.name != null && String(args.name).trim()) {
          const name = String(args.name).trim();
          const matches = canvases.filter(c => c.name === name);
          if (!matches.length) return { ok: false, error: `没有名为「${name}」的画布` };
          if (matches.length > 1) {
            return { ok: false, error: `有 ${matches.length} 个画布都叫「${name}」，请改用 index 指定第几个` };
          }
          target = matches[0];
        } else if (args.id != null) {
          target = canvases.find(c => c.id === Number(args.id));
          if (!target) return { ok: false, error: `没有 id=${args.id} 的画布` };
        } else {
          return { ok: false, error: "需要提供 index（第几个）/ name（画布名）/ id 之一" };
        }
        const graph = getCurrentModelGraph(target);
        const v = await validateModelStructure(graph);
        return {
          ok: true,
          result: {
            index: canvases.indexOf(target) + 1,
            id: target.id,
            name: target.name,
            graph,
            shapes: v.shapes || {},
            valid: v.valid,
            errors: v.errors,
            warnings: v.warnings,
          },
        };
      }

      case "get_shapes": {
        const r = await validateModelStructure(getCurrentModelGraph());
        return { ok: true, result: r.shapes || {} };
      }

      case "validate_model": {
        // 复用用户「检查结构」按钮的处理：同步更新各层徽标 / 维度提示 / 底栏状态，再把结论回传模型
        const r = await handleValidateModel();
        if (!r) return { ok: false, error: "校验未执行（可能正在校验中），请稍后重试" };
        return {
          ok: true,
          result: { valid: r.valid, errors: r.errors, warnings: r.warnings, message: r.message },
        };
      }

      case "list_templates": {
        let items = templateLibrary.items;
        if (!items.length) {
          const resp = await fetchProjectTemplates();
          items = (resp as { data?: typeof items }).data || [];
        }
        return {
          ok: true,
          result: items.map(t => ({ key: t.key, name: t.name, description: t.description })),
        };
      }

      case "load_template": {
        const key = String(args.key ?? "").trim();
        if (!key) return { ok: false, error: "缺少参数 key" };
        const resp = await fetchProjectTemplate(key);
        const graph =
          (resp as { model?: unknown }).model ??
          (resp as { data?: { model?: unknown } }).data?.model;
        if (!graph) return { ok: false, error: `未找到模板：${key}` };
        applyTemplateGraph(graph as never);
        return { ok: true, result: { loaded: key } };
      }

      case "add_node": {
        const type = String(args.type ?? "").trim();
        if (!type) return { ok: false, error: "缺少参数 type" };
        const before = new Set(activeCanvas().nodes.map(n => n.id));
        const pos = nextNodePosition();
        addNodeFromLayer(type, pos.x, pos.y);
        const created = activeCanvas().nodes.find(n => !before.has(n.id));
        if (!created) return { ok: false, error: `无法添加节点：${type}（未知层类型？）` };
        // 应用可选的初始参数
        const params = args.params;
        if (params && typeof params === "object") {
          for (const [k, v] of Object.entries(params)) updateNodeParam(created.id, k, v);
        }
        return { ok: true, result: { node_id: created.id, type: created.type } };
      }

      case "connect_nodes": {
        const source = String(args.source ?? "").trim();
        const target = String(args.target ?? "").trim();
        if (!source || !target) return { ok: false, error: "缺少 source 或 target" };
        if (source === target) return { ok: false, error: "不能把节点连到它自己" };
        const nodes = activeCanvas().nodes;
        if (!nodes.some(n => n.id === source) || !nodes.some(n => n.id === target)) {
          return { ok: false, error: "source 或 target 节点不存在" };
        }
        const conns = activeCanvas().connections;
        if (conns.some(([s, t]) => s === source && t === target)) {
          return { ok: true, result: { connected: [source, target], note: "该连接已存在" } };
        }
        // 与用户手动连线（completeConnection）一致：记录历史 + 重置校验状态 + 重绘
        recordHistory();
        conns.push([source, target]);
        resetValidationAfterGraphChange();
        drawLines();
        return { ok: true, result: { connected: [source, target] } };
      }

      case "set_param": {
        const nodeId = String(args.node_id ?? "").trim();
        const name = String(args.name ?? "").trim();
        if (!nodeId || !name) return { ok: false, error: "缺少 node_id 或 name" };
        if (!activeCanvas().nodes.some(n => n.id === nodeId)) {
          return { ok: false, error: "节点不存在" };
        }
        updateNodeParam(nodeId, name, args.value);
        return { ok: true, result: { node_id: nodeId, name, value: args.value } };
      }

      case "delete_node": {
        const nodeId = String(args.node_id ?? "").trim();
        if (!nodeId) return { ok: false, error: "缺少 node_id" };
        // 复用用户右键删除的同一函数：记录历史、清边控制点/挂起连线、重置校验并重绘
        if (!deleteNodeById(nodeId)) return { ok: false, error: "节点不存在" };
        return { ok: true, result: { deleted: nodeId } };
      }

      case "set_dataset": {
        const name = String(args.name ?? args.dataset ?? "").trim();
        if (!name) return { ok: false, error: "缺少参数 name（数据集名）" };
        const choice = datasetChoices.find(c => c.value.toLowerCase() === name.toLowerCase());
        if (!choice) {
          return { ok: false, error: `未知数据集：${name}。可选：${datasetChoices.map(c => c.value).join("、")}` };
        }
        const inputSynced = setDataset(choice.value);
        void redrawAfterDomUpdate();
        return {
          ok: true,
          result: {
            dataset: choice.value,
            input_shape: datasetInputShape(choice.value),
            input_synced: inputSynced, // Input 维度是否被自动改动（改动后需重新校验）
          },
        };
      }

      case "get_system_status": {
        const dev = agent.deviceSummary;
        return {
          ok: true,
          result: {
            local_agent: {
              online: agent.online, // false 时训练/导出无法进行，需用户启动本机训练应用
              runtime_version: agent.runtimeVersion || null,
              platform: agent.platform || null,
            },
            device: {
              current: store.device, // cpu / cuda
              cuda_available: store.cudaAvailable,
              cuda_device_count: dev?.cuda_device_count ?? 0,
              cuda_devices: dev?.cuda_devices ?? [],
              available: dev?.available_devices ?? [],
            },
            dataset: store.dataset,
            storage: {
              data_dir: storagePaths.dataDir || "（后端默认位置）",
              artifacts_dir: storagePaths.artifactsDir || "（后端默认位置）",
            },
            canvas: {
              name: activeCanvas().name,
              canvas_count: store.canvases.length,
              node_count: activeCanvas().nodes.length,
            },
          },
        };
      }

      case "get_train_config":
        return { ok: true, result: getTrainConfig() };

      case "get_training_result":
        return { ok: true, result: summarizeTraining() };

      case "set_train_config": {
        const changes: Record<string, unknown> = {};
        const skipped: string[] = [];
        if (args.epochs != null) {
          const e = Math.round(Number(args.epochs));
          if (!Number.isFinite(e) || e < 1 || e > 100) skipped.push("epochs 须为 1~100 的整数");
          else { activeCanvas().epochs = e; changes.epochs = e; }
        }
        if (args.batch_size != null) {
          const b = Math.round(Number(args.batch_size));
          if (!Number.isFinite(b) || b < 1) skipped.push("batch_size 须为正整数");
          else { store.batchSize = b; changes.batch_size = b; }
        }
        const rate = args.rate ?? args.learning_rate;
        if (rate != null) {
          const r = Number(rate);
          if (!Number.isFinite(r) || r <= 0) skipped.push("rate 须为正数");
          else { store.learningRate = r; changes.rate = r; }
        }
        if (args.optimizer != null) {
          const o = String(args.optimizer).toLowerCase();
          if (!OPTIMIZERS.includes(o)) skipped.push(`optimizer 只能取：${OPTIMIZERS.join("、")}`);
          else { store.optimizer = o; changes.optimizer = o; }
        }
        const loss = args.loss_fn ?? args.loss;
        if (loss != null) {
          const l = String(loss).toLowerCase();
          if (!LOSSES.includes(l)) skipped.push(`loss_fn 只能取：${LOSSES.join("、")}`);
          else { store.lossFn = l; changes.loss_fn = l; }
        }
        if (args.device != null) {
          const d = String(args.device).toLowerCase();
          if (d !== "cpu" && d !== "cuda") skipped.push("device 只能是 cpu 或 cuda");
          else if (d === "cuda" && !store.cudaAvailable) skipped.push("本机没有可用的 CUDA(GPU)，无法切到 cuda");
          else { store.device = d; changes.device = d; }
        }
        if (!Object.keys(changes).length) {
          return {
            ok: false,
            error: skipped.length ? skipped.join("；") : "没有可设置的字段。可设：epochs / batch_size / rate / optimizer / loss_fn / device",
          };
        }
        return { ok: true, result: { updated: changes, ...(skipped.length ? { skipped } : {}), train_config: getTrainConfig() } };
      }

      case "stop_training":
        await handleStopTraining();
        return { ok: true, result: "已请求终止训练（若当前没有进行中的任务会自动忽略）" };

      case "auto_layout":
        autoLayoutGraph();
        return { ok: true, result: "已自动整理布局" };

      case "export_code": {
        await handleExportCode();
        const code = activeCanvas().lastExportCode;
        return {
          ok: true,
          result: { code: code || "（导出需要本机 Agent 在线，已提示用户启动）" },
        };
      }

      case "start_training": {
        await handleStartTraining();
        return { ok: true, result: "已尝试发起训练（需本机 Agent 在线，否则会提示用户启动）" };
      }

      default:
        return { ok: false, error: `前端暂不支持该命令：${command}` };
    }
  } catch (e) {
    return { ok: false, error: (e as Error)?.message || String(e) };
  }
}

// 未使用，占位：连线时清理 store 的临时状态（保持与 UI 一致，避免残留）
export function resetAssistantConnectState() {
  store.connectSourceId = null;
  store.connectTargetId = null;
}
