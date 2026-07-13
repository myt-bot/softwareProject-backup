<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { ui } from "../store";
import { buildAssistantSnapshot, executeAssistantCommand } from "../assistant";
import { renderMarkdown } from "../markdown";
import PetMascot from "./PetMascot.vue";
import assistantHelp from "../assistantHelp.json";

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
const mode = ref<Mode>("ai"); // 默认 AI 对话；点「退出」进入命令行，命令行里输入 agent 再回 AI

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
  suggestions?: string[]; // 本回合回答后的「猜你想问」（挂在该气泡下方，下次提问即消失）
  suggestLoading?: boolean; // 追问正在生成（回答刚结束、建议还没到，先占位）
}

// 命令表 / 层参数 / 宠物气泡等文案已抽到 data/assistantHelp.json，改文案无需动组件代码。
interface CmdParam { name: string; type: string; required: boolean; desc: string }
interface CmdSpec { name: string; group: string; summary: string; usage: string; params: CmdParam[] }
const COMMAND_GROUPS = assistantHelp.commandGroups;
const COMMANDS = assistantHelp.commands as CmdSpec[];
const LAYER_PARAMS = assistantHelp.layerParams;
const messages = ref<ChatMessage[]>([]);
const input = ref("");
const busy = ref(false); // AI 本轮是否正在处理
const status = ref<"idle" | "connecting" | "open" | "closed" | "error">("idle");
const listRef = ref<HTMLElement | null>(null);
const inputRef = ref<HTMLTextAreaElement | null>(null);

// 清掉所有已挂出的「猜你想问」及其占位（用户继续下一句时调用）
function clearSuggestions() {
  for (const m of messages.value) {
    if (m.suggestions) m.suggestions = undefined;
    if (m.suggestLoading) m.suggestLoading = false;
  }
}

// —— help 卡片辅助 ——（topic 存于 help 消息的 text 字段）
function helpCommand(topic: string): CmdSpec | undefined {
  const t = topic.trim().toLowerCase();
  return COMMANDS.find(c => c.name.toLowerCase() === t);
}
function helpLayer(topic: string): (typeof LAYER_PARAMS)[number] | undefined {
  const t = topic.trim().toLowerCase();
  return LAYER_PARAMS.find(lp => lp.type.split(/\s*\/\s*/).some(name => name.toLowerCase() === t));
}
function commandsIn(group: string): CmdSpec[] {
  return COMMANDS.filter(c => c.group === group);
}
// 点击命令 → 把它的用法填进输入框并聚焦，少手敲
function insertCmd(usage: string) {
  input.value = usage;
  void nextTick(() => inputRef.value?.focus());
}

let ws: WebSocket | null = null;

// 当前 AI 回合在 messages 中的下标；-1 表示本回合尚未落卡（下一段文本/工具会新建一张卡）。
// 同一回合内的所有助手文本与工具调用都并入这张卡，避免每步各成一张卡片。
let aiTurnIndex = -1;
// 是否有“正在流式追加”的文本段：为 true 时 assistant_delta 继续追加到最后一段文本，
// 否则新起一段。工具调用到来 / 本回合结束时置 false，让后续文本另起一段。
let streamOpen = false;
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
    // help [topic]：topic 可为命令名 / layers / 层类型；空则总览
    const topic = line.trim().split(/\s+/)[1] || "";
    push("help", topic);
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
  if (msg.type === "assistant_delta") {
    // 流式增量：追加到当前文本段（没有则新起一段）
    const piece = String(msg.text ?? "");
    if (!piece) return;
    const steps = currentAiTurn().steps!;
    const last = steps[steps.length - 1];
    if (streamOpen && last && last.kind === "text") {
      last.text += piece;
    } else {
      steps.push({ kind: "text", text: piece });
      streamOpen = true;
    }
    scrollToBottom();
  } else if (msg.type === "assistant_message") {
    const text = String(msg.text ?? "");
    const turn = currentAiTurn();
    // 正文一般已由 assistant_delta 送达；仅当带非空 text（兜底/报错等）时另起一段
    if (text) turn.steps!.push({ kind: "text", text });
    streamOpen = false;
    scrollToBottom();
    if (msg.final) {
      turn.done = true; // 收到最终回答：思考过程折叠起来
      turn.suggestLoading = true; // 先占位「猜你想问 · 生成中…」，建议到了再填
      busy.value = false;
      aiTurnIndex = -1; // 本回合结束，下条消息另起新卡
    }
  } else if (msg.type === "suggestions") {
    // 猜你想问：挂到最近一条 AI 回合气泡下方；用户已开始下一句则忽略
    if (busy.value) return;
    const items = Array.isArray(msg.items) ? (msg.items as unknown[]).slice(0, 3).map(String) : [];
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i];
      if (m.role === "assistant") {
        m.suggestions = items.length ? items : undefined;
        m.suggestLoading = false;
        break;
      }
    }
    scrollToBottom();
  } else if (msg.type === "tool_request") {
    const command = String(msg.command ?? "");
    const args = (msg.args as Record<string, unknown>) || {};
    streamOpen = false; // 关闭当前流式文本段，工具后另起新段
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
  streamOpen = false;
  clearSuggestions();
  push("note", "已进入 AI 对话：直接说你想做什么，例如“帮我建一个 LeNet 并解释”。点上方「退出 AI」可回到命令模式。");
  void connect().catch(() => {});
}

function exitAi() {
  mode.value = "command";
  busy.value = false;
  messages.value = []; // 切换模式时清空命令台内容
  aiTurnIndex = -1;
  streamOpen = false;
  clearSuggestions();
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
  streamOpen = false;
  clearSuggestions(); // 发新问题时清掉上一轮的追问建议
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

// 点选一条「猜你想问」→ 作为下一条用户消息发送
function applySuggestion(q: string) {
  if (busy.value) return;
  clearSuggestions();
  push("user", q);
  void sendToAi(q);
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
    ? "说你想做什么，Enter 发送"
    : "输入命令；help 看全部，agent 呼出 AI"
);

// 小宠物：AI 模式下、尚未开始对话（没有用户/助手消息）时露面卖萌，一开口就消失
const showPet = computed(
  () => mode.value === "ai" && !messages.value.some(m => m.role === "user" || m.role === "assistant")
);

// 长时间不开口时，宠物头顶轮换冒气泡，提示用户可以做什么
const petBubble = ref<string | null>(null);
const PET_NUDGES = assistantHelp.petNudges;
const PET_FIRST_MS = 3500; // 进入后先安静一会
const PET_SHOW_MS = 4500; // 一句气泡停留时长
const PET_HIDE_MS = 3800; // 两句之间的空档
let petTimer: ReturnType<typeof setTimeout> | undefined;
let petIdx = 0;
function stopPetNudges() {
  if (petTimer) clearTimeout(petTimer);
  petTimer = undefined;
  petBubble.value = null;
  petIdx = 0;
}
// 出现一句 → 停留 → 消失 → 空档 → 再出现下一句，如此循环
function petShow() {
  petBubble.value = PET_NUDGES[petIdx % PET_NUDGES.length];
  petIdx++;
  petTimer = setTimeout(petHide, PET_SHOW_MS);
}
function petHide() {
  petBubble.value = null;
  petTimer = setTimeout(petShow, PET_HIDE_MS);
}
function startPetNudges() {
  stopPetNudges();
  petTimer = setTimeout(petShow, PET_FIRST_MS);
}
watch(showPet, visible => (visible ? startPetNudges() : stopPetNudges()), { immediate: true });
onBeforeUnmount(stopPetNudges);

// 打开面板：进入 AI 模式时连 WS；并把焦点落到输入框，打开即可直接开始输入
watch(
  () => ui.assistantOpen,
  open => {
    if (!open) return;
    if (mode.value === "ai") void connect().catch(() => {});
    void nextTick(() => inputRef.value?.focus({ preventScroll: true }));
  }
);
</script>

<template>
  <div class="assistant-drawer" :class="{ open: ui.assistantOpen }" id="assistant-panel">
    <!-- 头部（随模式变色，切换更明显） -->
    <header class="assistant-head" :class="mode">
      <div class="assistant-title">
        <span class="assistant-avatar" :class="{ pet: mode === 'ai' }">
          <PetMascot v-if="mode === 'ai'" :size="30" />
          <iconify-icon v-else icon="mdi:console-line"></iconify-icon>
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
      <!-- AI 模式且未开始对话：会动的小宠物；用户一开口就消失 -->
      <Transition name="assistant-pet">
        <div v-if="showPet" class="assistant-pet" aria-hidden="true">
          <!-- 长时间不开口时，头顶冒气泡催一下 -->
          <Transition name="assistant-bubble" mode="out-in">
            <div v-if="petBubble" :key="petBubble" class="assistant-pet-bubble">{{ petBubble }}</div>
          </Transition>
          <!-- 常驻原地踏步；气泡出现时额外挥翅打招呼 -->
          <PetMascot :size="150" :live="true" :greet="!!petBubble" />
        </div>
      </Transition>
      <div v-if="mode === 'command' && !messages.length" class="assistant-empty">
        <iconify-icon icon="mdi:console-line"></iconify-icon>
        <p>命令模式。直接敲命令，例如：</p>
        <ul>
          <li><code>help</code>（命令总览；<code>help &lt;命令&gt;</code> 看详情）</li>
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
        <!-- help：分层帮助（总览 / 单条命令 / 层参数） -->
        <div v-else-if="m.role === 'help'" class="assistant-help">
          <!-- 单条命令详情：help <命令> -->
          <template v-if="helpCommand(m.text)">
            <div class="assistant-help-detail-head">
              <code>{{ helpCommand(m.text)!.name }}</code>
              <span>{{ helpCommand(m.text)!.summary }}</span>
            </div>
            <button class="assistant-help-usage" :title="'点击填入输入框'" @click="insertCmd(helpCommand(m.text)!.usage)">
              <iconify-icon icon="mdi:arrow-down-left"></iconify-icon>
              <code>{{ helpCommand(m.text)!.usage }}</code>
            </button>
            <div v-if="helpCommand(m.text)!.params.length" class="assistant-help-params">
              <div v-for="p in helpCommand(m.text)!.params" :key="p.name" class="assistant-help-row">
                <code>{{ p.name }}</code>
                <span><em>{{ p.type }} · {{ p.required ? "必填" : "可选" }}</em>{{ p.desc }}</span>
              </div>
            </div>
            <div v-else class="assistant-help-empty">无参数，直接执行。</div>
            <div class="assistant-help-foot">回 <code>help</code> 看命令总览</div>
          </template>
          <!-- 全部层参数：help layers -->
          <template v-else-if="m.text === 'layers' || m.text === 'layer'">
            <div class="assistant-help-tip">
              <b>层类型 · 可设参数</b>（用于 <code>add_node --params</code> 与 <code>set_param</code>）。
              值含 JSON/数组时用<b>单引号整体包住</b>，如 <code>--params '{"out_channels":16}'</code>。
            </div>
            <div class="assistant-help-params">
              <div v-for="lp in LAYER_PARAMS" :key="lp.type" class="assistant-help-row">
                <code>{{ lp.type }}</code>
                <span>{{ lp.params }}</span>
              </div>
            </div>
            <div class="assistant-help-foot">回 <code>help</code> 看命令总览</div>
          </template>
          <!-- 单个层参数：help Conv2D -->
          <template v-else-if="helpLayer(m.text)">
            <div class="assistant-help-detail-head">
              <code>{{ helpLayer(m.text)!.type }}</code>
              <span>可设参数</span>
            </div>
            <div class="assistant-help-empty">{{ helpLayer(m.text)!.params }}</div>
            <div class="assistant-help-foot">全部层见 <code>help layers</code></div>
          </template>
          <!-- 未知 topic -->
          <template v-else-if="m.text">
            <div class="assistant-help-empty">未找到 “{{ m.text }}”。输入 <code>help</code> 看命令总览。</div>
          </template>
          <!-- 总览：语法一行 + 分组命令名（可点击填入） -->
          <template v-else>
            <div class="assistant-help-tip">
              语法 <code>命令 --参数 值</code>；值含空格/JSON 用单引号包住。点命令名即可填入输入框。
            </div>
            <div v-for="g in COMMAND_GROUPS" :key="g" class="assistant-help-group">
              <h5>{{ g }}</h5>
              <div class="assistant-help-chips">
                <button
                  v-for="c in commandsIn(g)"
                  :key="c.name"
                  class="assistant-cmd-chip"
                  :title="c.summary + '（点击填入）'"
                  @click="insertCmd(c.usage)"
                >{{ c.name }}</button>
              </div>
            </div>
            <div class="assistant-help-foot">
              看某条用法参数：<code>help &lt;命令&gt;</code>（如 <code>help add_node</code>）· 层参数：<code>help layers</code>
            </div>
          </template>
        </div>
        <!-- AI 回合：思考过程（中间叙述 + 工具调用）折叠，最终回答常显 -->
        <div v-else-if="m.role === 'assistant'" class="assistant-turn">
          <span class="assistant-turn-avatar">
            <PetMascot :size="28" />
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
            <!-- 猜你想问：挂在本回复下方；标签单独一行，胶囊从下一行起；点一下即发送 -->
            <div v-if="m.suggestions && m.suggestions.length" class="assistant-turn-suggest">
              <span class="assistant-suggest-label">
                <iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon> 猜你想问
              </span>
              <div class="assistant-suggest-chips">
                <button
                  v-for="(s, si) in m.suggestions"
                  :key="si"
                  class="assistant-suggest-chip"
                  :title="s"
                  @click="applySuggestion(s)"
                >{{ s }}</button>
              </div>
            </div>
            <div v-else-if="m.suggestLoading" class="assistant-turn-suggest loading">
              <iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon>
              猜你想问 · 生成中…
            </div>
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
        ref="inputRef"
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
