<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { ui } from "../store";
import { buildAssistantSnapshot, executeAssistantCommand } from "../assistant";
import { renderMarkdown } from "../markdown";

// 后端地址（与 api/client 一致）：生产由 VITE_API_BASE_URL 注入
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string) || "http://127.0.0.1:8000";

// 唤醒词：命令模式下单独输入它即进入 AI 对话
const WAKE_WORD = "agent";

// —— 模型配置（模型名 / API Key / API 地址），持久化到 localStorage ——
const model = ref(localStorage.getItem("assistant.model") || "");
const apiKey = ref(localStorage.getItem("assistant.apiKey") || "");
const baseUrl = ref(localStorage.getItem("assistant.baseUrl") || "");
const showSettings = ref(false);

function saveSettings() {
  localStorage.setItem("assistant.model", model.value.trim());
  localStorage.setItem("assistant.apiKey", apiKey.value.trim());
  localStorage.setItem("assistant.baseUrl", baseUrl.value.trim());
  showSettings.value = false;
}

// —— 会话状态 ——
type Mode = "command" | "ai";
const mode = ref<Mode>("command"); // 默认命令模式；输入 agent 进入 AI

// AI 回合内按时序穿插的片段：一段文本（Markdown）或一次工具调用
type AssistantStep = { kind: "text"; text: string } | { kind: "tool"; command: string };

interface ChatMessage {
  role: "user" | "assistant" | "tool" | "note" | "help" | "result";
  text: string;
  // role==='result' 专用：命令执行结果卡
  ok?: boolean;
  command?: string;
  body?: string;
  // role==='assistant' 专用：把本回合的多段文本与多次工具调用合并进一张卡
  steps?: AssistantStep[];
  done?: boolean;     // 本回合是否已产出最终回答（收到 final）
  expanded?: boolean; // 「思考过程」是否展开（完成后默认折叠）
}

// 命令帮助（结构化，供 help 命令渲染成美观卡片）。
// 带 JSON / 数组 / 空格的参数值一律用单引号整体包住。
const HELP_GROUPS = [
  {
    title: "只读 · 了解现状",
    items: [
      { cmd: "get_model_graph", desc: "获取当前模型图" },
      { cmd: "list_nodes", desc: "列出全部节点及 id" },
      { cmd: "get_shapes", desc: "查看各层输出维度" },
      { cmd: "validate_model", desc: "校验结构，返回错误/警告" },
      { cmd: "list_templates", desc: "列出内置模板（拿到 key 供 load_template 用）" },
      { cmd: "get_train_config", desc: "查看当前训练配置" },
      { cmd: "get_training_result", desc: "查看训练结果与逐轮指标" },
      { cmd: "get_system_status", desc: "查看本机 Agent/设备/存储等系统状态" },
    ],
  },
  {
    title: "画布操作",
    items: [
      { cmd: "load_template --key lenet", desc: "载入内置模板；key 见 list_templates" },
      { cmd: "add_node --type Conv2D --params '{\"out_channels\":16}'", desc: "新增层；参数用单引号包 JSON（层与参数见下方表）" },
      { cmd: "connect_nodes --source conv2d_1 --target relu_1", desc: "连接两个节点（id 见 list_nodes）" },
      { cmd: "set_param --node_id linear_1 --name out_features --value 10", desc: "改参数；数组/对象用单引号，如 --value '[1,16,16]'" },
      { cmd: "delete_node --node_id dropout_1", desc: "删除节点及其连线" },
      { cmd: "set_dataset --name FashionMNIST", desc: "切换数据集，自动同步 Input 维度" },
      { cmd: "set_train_config --epochs 10 --optimizer adam", desc: "改训练超参数（epochs/batch_size/rate/optimizer/loss_fn/device）" },
      { cmd: "auto_layout", desc: "自动整理布局" },
      { cmd: "export_code", desc: "导出 PyTorch 代码（需本机 Agent）" },
      { cmd: "start_training", desc: "发起训练（需本机 Agent）；可选 --config '<JSON>'" },
      { cmd: "stop_training", desc: "停止当前训练（需本机 Agent）" },
    ],
  },
  {
    title: "AI · 帮助",
    items: [
      { cmd: "agent", desc: "进入 AI 对话，用自然语言让 AI 帮你操作" },
      { cmd: "clear", desc: "清空命令台内容" },
      { cmd: "help", desc: "显示本帮助" },
    ],
  },
];

// 各层类型可设置的参数（用于 add_node 的 --params 与 set_param 的 --name/--value）
const LAYER_PARAMS = [
  { type: "Input", params: "shape：数组 [通道,高,宽]，如 [1,28,28]" },
  { type: "Conv2D", params: "out_channels / kernel_size / stride / padding：整数" },
  { type: "MaxPooling", params: "kernel_size / stride / padding：整数" },
  { type: "Linear", params: "out_features：整数（末层设为类别数）" },
  { type: "Dropout", params: "p：0~1 小数" },
  { type: "LSTM", params: "hidden_size / num_layers：整数；return_sequences / bidirectional：true|false" },
  { type: "TransformerEncoder", params: "d_model / num_heads / num_layers / dim_feedforward：整数；dropout：小数" },
  { type: "SelfAttention", params: "embed_dim / num_heads：整数；dropout：小数" },
  { type: "Seq2Seq", params: "hidden_size / output_size / target_length / num_layers：整数" },
  { type: "VAE", params: "latent_dim / output_features：整数" },
  { type: "GraphConv", params: "out_features：整数" },
  { type: "ReLU / Flatten / Add / Output", params: "无可设参数" },
];
const messages = ref<ChatMessage[]>([]);
const input = ref("");
const busy = ref(false); // AI 本轮是否正在处理
const status = ref<"idle" | "connecting" | "open" | "closed" | "error">("idle");
const listRef = ref<HTMLElement | null>(null);

let ws: WebSocket | null = null;

// 当前 AI 回合在 messages 中的下标；-1 表示本回合尚未落卡（下一段文本/工具会新建一张卡）。
// 同一回合内的所有助手文本与工具调用都并入这张卡，避免每步各成一张卡片。
let aiTurnIndex = -1;
function currentAiTurn(): ChatMessage {
  const existing = messages.value[aiTurnIndex];
  if (aiTurnIndex >= 0 && existing && existing.role === "assistant") return existing;
  messages.value.push({ role: "assistant", text: "", steps: [], done: false, expanded: false });
  aiTurnIndex = messages.value.length - 1;
  return messages.value[aiTurnIndex];
}

// 本回合里“最终回答”= 完成后的最后一段文本；其余（中间叙述 + 工具调用）归为“思考过程”。
function turnSteps(m: ChatMessage): AssistantStep[] {
  return m.steps || [];
}
function finalStep(m: ChatMessage): AssistantStep | null {
  const s = turnSteps(m);
  if (m.done && s.length && s[s.length - 1].kind === "text") return s[s.length - 1];
  return null;
}
function thinkingSteps(m: ChatMessage): AssistantStep[] {
  const s = turnSteps(m);
  return finalStep(m) ? s.slice(0, -1) : s;
}
function finalText(m: ChatMessage): string {
  const s = finalStep(m);
  return s && s.kind === "text" ? s.text : "";
}

function wsUrl(): string {
  const token = localStorage.getItem("model-workshop-token") || "";
  return `${API_BASE.replace(/^http/, "ws")}/assistant/ws?token=${encodeURIComponent(token)}`;
}

function scrollToBottom() {
  void nextTick(() => {
    const el = listRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function push(role: ChatMessage["role"], text: string) {
  messages.value.push({ role, text });
  scrollToBottom();
}

// —————————————————————— 命令模式 ——————————————————————
// 把一行命令解析成 { command, args }：command --key value ...
// 值优先按 JSON 解析（数字/对象/布尔），失败按字符串；支持单双引号包裹带空格的值。
function parseCommandLine(line: string): { command: string; args: Record<string, unknown> } | null {
  const tokens = line.match(/'[^']*'|"[^"]*"|\S+/g);
  if (!tokens || !tokens.length) return null;
  const strip = (s: string) =>
    (s.startsWith("'") && s.endsWith("'")) || (s.startsWith('"') && s.endsWith('"')) ? s.slice(1, -1) : s;
  const command = strip(tokens[0]);
  const args: Record<string, unknown> = {};
  for (let i = 1; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.startsWith("--")) {
      const key = t.slice(2);
      let raw = "true";
      if (i + 1 < tokens.length && !tokens[i + 1].startsWith("--")) raw = strip(tokens[++i]);
      let val: unknown = raw;
      try {
        val = JSON.parse(raw);
      } catch {
        val = raw;
      }
      args[key] = val;
    }
  }
  return { command, args };
}

function prettyResult(result: unknown): string {
  if (result == null) return "";
  if (typeof result === "string") return result;
  try {
    const s = JSON.stringify(result, null, 2);
    return s.length > 1200 ? s.slice(0, 1200) + " …（已截断）" : s;
  } catch {
    return String(result);
  }
}

async function runCommand(line: string) {
  const parsed = parseCommandLine(line);
  if (!parsed) return;
  if (parsed.command === "help") {
    push("help", "");
    return;
  }
  if (parsed.command === "clear") {
    messages.value = []; // 清空命令台内容
    return;
  }
  const res = await executeAssistantCommand(parsed.command, parsed.args);
  messages.value.push({
    role: "result",
    text: "",
    ok: res.ok,
    command: parsed.command,
    body: res.ok ? prettyResult(res.result) : res.error || "命令执行失败",
  });
  scrollToBottom();
}

// 结果体是否为结构化 JSON（决定用代码块渲染还是普通文字）
function looksJson(body?: string): boolean {
  if (!body) return false;
  const t = body.trimStart();
  return t.startsWith("{") || t.startsWith("[");
}

// —————————————————————— AI 模式 ——————————————————————
async function onMessage(event: MessageEvent) {
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(event.data as string);
  } catch {
    return;
  }
  if (msg.type === "assistant_message") {
    const text = String(msg.text ?? "");
    const turn = currentAiTurn();
    if (text) turn.steps!.push({ kind: "text", text });
    scrollToBottom();
    if (msg.final) {
      turn.done = true; // 收到最终回答：思考过程折叠起来
      busy.value = false;
      aiTurnIndex = -1; // 本回合结束，下条消息另起新卡
    }
  } else if (msg.type === "tool_request") {
    const command = String(msg.command ?? "");
    const args = (msg.args as Record<string, unknown>) || {};
    currentAiTurn().steps!.push({ kind: "tool", command });
    scrollToBottom();
    const res = await executeAssistantCommand(command, args);
    ws?.send(
      JSON.stringify({
        type: "tool_result",
        call_id: msg.call_id,
        ok: res.ok,
        result: res.result,
        error: res.error,
      })
    );
  }
}

function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      if (ws.readyState === WebSocket.OPEN) resolve();
      else ws.addEventListener("open", () => resolve(), { once: true });
      return;
    }
    status.value = "connecting";
    ws = new WebSocket(wsUrl());
    ws.onopen = () => {
      status.value = "open";
      resolve();
    };
    ws.onmessage = onMessage;
    ws.onerror = () => {
      status.value = "error";
      reject(new Error("WebSocket 连接失败"));
    };
    ws.onclose = () => {
      status.value = "closed";
      busy.value = false;
      ws = null;
    };
  });
}

function enterAi() {
  mode.value = "ai";
  messages.value = []; // 切换模式时清空命令台内容
  aiTurnIndex = -1;
  push("note", "已进入 AI 对话：直接说你想做什么，例如“帮我建一个 LeNet 并解释”。点上方「退出 AI」可回到命令模式。");
  void connect().catch(() => {});
}

function exitAi() {
  mode.value = "command";
  busy.value = false;
  messages.value = []; // 切换模式时清空命令台内容
  aiTurnIndex = -1;
  push("note", "已退出 AI 对话，回到命令模式。输入 help 查看命令，或再次输入 agent 呼出 AI。");
}

async function sendToAi(text: string) {
  // AI 模式需要模型名 + API Key + API 地址（均必填，后端不做任何默认）
  if (!model.value.trim() || !apiKey.value.trim() || !baseUrl.value.trim()) {
    showSettings.value = true;
    push("assistant", "请先在上方「模型设置」里填写模型名、API Key 和 API 地址，然后再发送。");
    return;
  }
  busy.value = true;
  aiTurnIndex = -1; // 新一轮提问：下一段助手输出另起新卡
  try {
    await connect();
  } catch {
    push("assistant", "无法连接助手服务，请确认已登录且后端已启动。");
    busy.value = false;
    return;
  }
  ws?.send(
    JSON.stringify({
      type: "user_message",
      text,
      snapshot: buildAssistantSnapshot(),
      model: model.value.trim() || undefined,
      api_key: apiKey.value.trim() || undefined,
      base_url: baseUrl.value.trim() || undefined,
    })
  );
}

// —— 统一提交：按当前模式分流 ——
async function submit() {
  const text = input.value.trim();
  if (!text || busy.value) return;

  if (mode.value === "command") {
    // 命令模式：唤醒词 → 进入 AI；否则当命令执行
    if (text.toLowerCase() === WAKE_WORD) {
      input.value = "";
      enterAi();
      return;
    }
    input.value = "";
    push("user", text);
    await runCommand(text);
    return;
  }

  // AI 模式
  input.value = "";
  push("user", text);
  await sendToAi(text);
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    void submit();
  }
}

function close() {
  ui.assistantOpen = false;
}

const statusText = computed(() => {
  if (mode.value !== "ai") return "";
  switch (status.value) {
    case "connecting":
      return "连接中…";
    case "open":
      return "已连接";
    case "error":
      return "连接失败";
    case "closed":
      return "已断开";
    default:
      return "";
  }
});

const placeholder = computed(() =>
  mode.value === "ai"
    ? "和 AI 说你想做什么，Enter 发送、Shift+Enter 换行"
    : "输入命令（如 help、load_template --key lenet）；输入 agent 呼出 AI"
);

// 打开面板不自动连 WS；进入 AI 模式时才连（对话历史保留在后端会话里）
watch(
  () => ui.assistantOpen,
  open => {
    if (open && mode.value === "ai") void connect().catch(() => {});
  }
);
</script>

<template>
  <div class="assistant-drawer" :class="{ open: ui.assistantOpen }" id="assistant-panel">
    <!-- 头部（随模式变色，切换更明显） -->
    <header class="assistant-head" :class="mode">
      <div class="assistant-title">
        <span class="assistant-avatar">
          <iconify-icon :icon="mode === 'ai' ? 'mdi:robot-happy-outline' : 'mdi:console-line'"></iconify-icon>
        </span>
        <span class="assistant-title-name">{{ mode === "ai" ? "AI 助手" : "命令台" }}</span>
        <em v-if="statusText" class="assistant-status">{{ statusText }}</em>
      </div>
      <div class="assistant-head-actions">
        <button class="icon-button" title="模型设置" @click="showSettings = !showSettings">
          <iconify-icon icon="mdi:cog-outline"></iconify-icon>
        </button>
        <button class="icon-button" title="关闭" @click="close">
          <iconify-icon icon="mdi:close"></iconify-icon>
        </button>
      </div>
    </header>

    <!-- 模式条：清晰标示当前处于命令模式 / AI 对话；AI 模式在右侧提供「退出」。
         :key 让每次切换都重放入场动画，切换更醒目 -->
    <div class="assistant-mode-bar" :class="mode" :key="mode">
      <div class="assistant-mode-label">
        <template v-if="mode === 'ai'">
          <span class="assistant-mode-dot"></span> AI 对话中 · 你说需求，AI 在画布上操作
        </template>
        <template v-else>
          命令模式 · 直接敲命令；输入 <b>agent</b> 呼出 AI
        </template>
      </div>
      <button
        v-if="mode === 'ai'"
        class="assistant-exit-chip"
        title="退出 AI 对话，回到命令模式"
        @click="exitAi"
      >
        <iconify-icon icon="mdi:logout-variant"></iconify-icon>
        退出
      </button>
    </div>

    <!-- 模型设置：模型名 / API Key / API 地址（AI 模式需要） -->
    <Transition name="assistant-settings">
    <section v-if="showSettings" class="assistant-settings">
      <label>
        <span>模型名</span>
        <input v-model="model" type="text" placeholder="例如 gpt-4.1-mini" />
      </label>
      <label>
        <span>模型 API Key</span>
        <input v-model="apiKey" type="password" placeholder="sk-..." />
      </label>
      <label>
        <span>API 地址</span>
        <input v-model="baseUrl" type="text" placeholder="必填，如 https://api.openai.com/v1" />
      </label>
      <div class="assistant-settings-actions">
        <button class="primary-button" @click="saveSettings">保存</button>
        <small>密钥仅保存在本浏览器，随对话发给你自己的后端使用。</small>
      </div>
    </section>
    </Transition>

    <!-- 消息区 -->
    <div ref="listRef" class="assistant-messages">
      <!-- AI 模式：中央大号 agent 图标水印（置于消息下层，不挡文字） -->
      <div v-if="mode === 'ai'" class="assistant-watermark" aria-hidden="true">
        <iconify-icon icon="mdi:robot-happy-outline"></iconify-icon>
      </div>
      <div v-if="!messages.length" class="assistant-empty">
        <iconify-icon icon="mdi:console-line"></iconify-icon>
        <p>命令模式。直接敲命令，例如：</p>
        <ul>
          <li><code>help</code>（查看全部命令）</li>
          <li><code>load_template --key lenet</code></li>
          <li><code>validate_model</code></li>
        </ul>
        <p>想让 AI 帮你建模 / 答疑？输入 <b>agent</b> 进入对话。</p>
      </div>
      <div v-for="(m, i) in messages" :key="i" class="assistant-msg" :class="`role-${m.role}`">
        <template v-if="m.role === 'tool'">
          <iconify-icon icon="mdi:flash-outline"></iconify-icon>
          <span>{{ m.text }}</span>
        </template>
        <!-- 命令执行结果卡 -->
        <div v-else-if="m.role === 'result'" class="assistant-result" :class="m.ok ? 'ok' : 'err'">
          <div class="assistant-result-head">
            <iconify-icon :icon="m.ok ? 'mdi:check-circle' : 'mdi:alert-circle-outline'"></iconify-icon>
            <code>{{ m.command }}</code>
            <span>{{ m.ok ? "已执行" : "失败" }}</span>
          </div>
          <pre v-if="m.body && looksJson(m.body)" class="assistant-result-code">{{ m.body }}</pre>
          <p v-else-if="m.body" class="assistant-result-text">{{ m.body }}</p>
        </div>
        <!-- help：结构化命令卡片 -->
        <div v-else-if="m.role === 'help'" class="assistant-help">
          <div class="assistant-help-tip">
            语法 <code>命令 --参数 值</code>。值含 <b>JSON / 数组 / 空格</b> 时用<b>单引号整体包住</b>，
            例如 <code>--params '{"out_channels":16}'</code>、<code>--value '[1,16,16]'</code>。
            想让 AI 帮你，输入 <b>agent</b>。
          </div>
          <div v-for="g in HELP_GROUPS" :key="g.title" class="assistant-help-group">
            <h5>{{ g.title }}</h5>
            <div v-for="it in g.items" :key="it.cmd" class="assistant-help-row">
              <code>{{ it.cmd }}</code>
              <span>{{ it.desc }}</span>
            </div>
          </div>
          <div class="assistant-help-group">
            <h5>层类型 · 可设参数（add_node 的 --params / set_param）</h5>
            <div v-for="lp in LAYER_PARAMS" :key="lp.type" class="assistant-help-row">
              <code>{{ lp.type }}</code>
              <span>{{ lp.params }}</span>
            </div>
          </div>
        </div>
        <!-- AI 回合：思考过程（中间叙述 + 工具调用）折叠，最终回答常显 -->
        <div v-else-if="m.role === 'assistant'" class="assistant-turn">
          <span class="assistant-turn-avatar">
            <iconify-icon icon="mdi:robot-happy-outline"></iconify-icon>
          </span>
          <div class="assistant-turn-body">
            <!-- 思考过程：完成后默认折叠，点击展开；运行中实时展开显示进度 -->
            <div v-if="thinkingSteps(m).length" class="assistant-think" :class="{ live: !m.done }">
              <button v-if="m.done" class="assistant-think-toggle" @click="m.expanded = !m.expanded">
                <iconify-icon :icon="m.expanded ? 'mdi:chevron-down' : 'mdi:chevron-right'"></iconify-icon>
                思考过程 · {{ thinkingSteps(m).length }} 步
              </button>
              <div v-else class="assistant-think-live">
                <iconify-icon icon="mdi:loading" class="spin"></iconify-icon>
                思考中…
              </div>
              <div v-show="!m.done || m.expanded" class="assistant-think-body">
                <template v-for="(s, si) in thinkingSteps(m)" :key="si">
                  <div v-if="s.kind === 'text'" class="assistant-md assistant-think-text" v-html="renderMarkdown(s.text)"></div>
                  <div v-else class="assistant-turn-tool">
                    <iconify-icon icon="mdi:flash-outline"></iconify-icon>
                    <span>执行命令 · {{ s.command }}</span>
                  </div>
                </template>
              </div>
            </div>
            <!-- 最终回答 -->
            <div v-if="finalText(m)" class="assistant-md" v-html="renderMarkdown(finalText(m))"></div>
            <!-- 无 steps 的简单消息（如错误提示） -->
            <div v-else-if="!turnSteps(m).length && m.text" class="assistant-md" v-html="renderMarkdown(m.text)"></div>
          </div>
        </div>
        <template v-else>{{ m.text }}</template>
      </div>
      <div v-if="busy" class="assistant-msg role-assistant assistant-typing">
        <span></span><span></span><span></span>
      </div>
    </div>

    <!-- 输入区 -->
    <footer class="assistant-input">
      <textarea
        v-model="input"
        rows="2"
        :placeholder="placeholder"
        :disabled="busy"
        @keydown="onInputKeydown"
      ></textarea>
      <button class="primary-button" :disabled="busy || !input.trim()" @click="submit">
        <iconify-icon icon="mdi:send"></iconify-icon>
      </button>
    </footer>
  </div>
</template>
