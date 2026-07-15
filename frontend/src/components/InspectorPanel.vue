<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { validateModelStructure } from "../api/client";
import { enterContainer, recordHistory, redrawAfterDomUpdate } from "../canvas";
import {
  activeCanvas,
  containerInputPorts,
  containerLayerCount,
  containerOutputPorts,
  endpointBaseId,
  getCurrentModelGraph,
  layerGroups,
  MERGE_MODES,
  saveContainerToLibrary,
  showToast,
  ui,
  updateNodeParam,
} from "../store";
import type { LayerShapeInfo } from "../types";
import ParamNumberField from "./ParamNumberField.vue";

const canvas = computed(() => activeCanvas());

const selectedNode = computed(() =>
  canvas.value.nodes.find(item => item.id === canvas.value.selectedNodeId) || null
);

// 层类型 → 图标 / 颜色 / 描述（用于参数面板顶部的节点头部）
const LAYER_META: Record<string, { icon: string; color: string; desc: string }> = Object.fromEntries(
  layerGroups.flatMap(group => group.layers.map(l => [l.type, { icon: l.icon, color: l.color, desc: l.desc }]))
);
const nodeMeta = computed(() => {
  const node = selectedNode.value;
  if (!node) return null;
  const meta = LAYER_META[node.type];
  return {
    icon: meta?.icon || "mdi:cube-outline",
    color: node.color || meta?.color || "cyan",
    desc: meta?.desc || "",
    badge: node.badge || node.type,
  };
});

// 实时形状预览：改参数时向云端请求维度推导（防抖），无需本地 Agent
const shapesMap = ref<Record<string, LayerShapeInfo>>({});
let shapeTimer: ReturnType<typeof setTimeout> | undefined;
let shapeRequestId = 0;

function refreshShapes() {
  clearTimeout(shapeTimer);
  const requestId = ++shapeRequestId;
  const requestCanvas = canvas.value;
  const modelSnapshot = getCurrentModelGraph(requestCanvas);

  shapeTimer = setTimeout(async () => {
    try {
      const result = await validateModelStructure(modelSnapshot);
      if (requestId === shapeRequestId && activeCanvas() === requestCanvas) {
        shapesMap.value = result.shapes || {};
      }
    } catch {
      // 预览失败不打扰用户（点"检查结构"仍会给出明确结果）
    }
  }, 250);
}

const liveOutputShape = computed(() => {
  const node = selectedNode.value;
  const shape = node ? shapesMap.value[node.id]?.output_shape : null;
  return shape && shape.length ? shape.join("×") : "—";
});

// 画布或选中节点变化时先清除旧预览，并使仍在途的请求失效。
watch(
  () => [canvas.value.id, selectedNode.value?.id] as const,
  ([, nodeId]) => {
    clearTimeout(shapeTimer);
    shapeRequestId += 1;
    shapesMap.value = {};
    if (nodeId) refreshShapes();
  },
  { immediate: true },
);

// 面板悬浮于画布之上：选中节点且未被手动收起时滑入，不改变画布尺寸
const panelOpen = computed(() => Boolean(selectedNode.value) && !ui.inspectorCollapsed);
const inspectorRef = ref<HTMLElement | null>(null);

// 从结构问题列表定位过来时，等面板完成渲染后滚动并短暂高亮相关字段。
watch(
  () => ui.inspectorFocusParam,
  async paramKey => {
    if (!paramKey || !panelOpen.value) return;
    await nextTick();
    const aliases: Record<string, string[]> = {
      in_features: ["In Features", "输入特征数"],
      out_features: ["Out Features", "输出神经元"],
      out_channels: ["Out Channels", "输出通道"],
      kernel_size: ["Kernel Size", "卷积核", "池化核"],
      stride: ["Stride", "步长"],
      padding: ["Padding", "填充"],
      shape: ["Input Shape", "输入形状"],
      merge: ["合并方式", "Merge"],
      p: ["Dropout Rate", "失活比例"],
    };
    const fields = inspectorRef.value?.querySelectorAll<HTMLElement>(".form-field, [data-param-key]") || [];
    const field = Array.from(fields).find(item =>
      item.dataset.paramKey === paramKey
      || (aliases[paramKey] || [paramKey]).some(alias => item.textContent?.includes(alias))
    );
    if (field) {
      field.scrollIntoView({ behavior: "smooth", block: "center" });
      field.classList.remove("param-focus-flash");
      requestAnimationFrame(() => field.classList.add("param-focus-flash"));
      setTimeout(() => field.classList.remove("param-focus-flash"), 1800);
    }
    ui.inspectorFocusParam = null;
  },
);

function collapsePanel() {
  ui.inspectorCollapsed = true;
}

const linearActualInFeatures = computed(() => {
  const node = selectedNode.value;
  if (!node) return "自动推导";
  const value = shapesMap.value[node.id]?.actual_in_features;
  return typeof value === "number" ? String(value) : "自动推导";
});

function setParam(key: string, value: number | boolean) {
  if (!selectedNode.value) return;
  recordHistory();  // 记录改参数前的状态，便于撤销
  updateNodeParam(selectedNode.value.id, key, value);
  // 节点卡片上的 note 可能变化导致高度变化，需要重绘连线
  void redrawAfterDomUpdate();
  // 改参数后刷新实时形状预览
  refreshShapes();
}

// —————————————————————————————————————————————
// 合并运算模块（add / concat / matmul）参数交互
// —————————————————————————————————————————————

const mergeMode = computed(() =>
  selectedNode.value && typeof selectedNode.value.params.merge === "string"
    ? (selectedNode.value.params.merge as string)
    : ""
);
const currentMerge = computed(() => MERGE_MODES.find(item => item.value === mergeMode.value) || null);

// 已选中、准备用 ⬅ / ➡ 调整顺序的输入 id
const selectedMergeInputId = ref<string | null>(null);

// 合并模块的有序输入列表：按 params.order 排序，自动补齐新连线、剔除失效连线
const mergeInputs = computed(() => {
  const node = selectedNode.value;
  if (!node || node.type !== "Merge") return [];
  const graph = canvas.value;

  const sources: string[] = [];
  for (const [source, target] of graph.connections) {
    if (endpointBaseId(target) !== node.id) continue;
    const sourceId = endpointBaseId(source);
    if (!sources.includes(sourceId)) sources.push(sourceId);
  }

  const order = Array.isArray(node.params.order) ? (node.params.order as string[]) : [];
  const rank = new Map(order.map((id, index) => [id, index]));
  const ordered = sources
    .map((id, index) => ({ id, index }))
    .sort((a, b) => (rank.get(a.id) ?? order.length + a.index) - (rank.get(b.id) ?? order.length + b.index))
    .map(item => item.id);

  return ordered.map((id, index) => {
    const source = graph.nodes.find(item => item.id === id);
    return { id, position: index, title: source?.title || source?.badge || id };
  });
});

const selectedMergeIndex = computed(() => mergeInputs.value.findIndex(item => item.id === selectedMergeInputId.value));
const canMoveMergeLeft = computed(() => selectedMergeIndex.value > 0);
const canMoveMergeRight = computed(() =>
  selectedMergeIndex.value >= 0 && selectedMergeIndex.value < mergeInputs.value.length - 1
);

function setMergeMode(mode: string) {
  const node = selectedNode.value;
  if (!node) return;
  recordHistory();
  updateNodeParam(node.id, "merge", mode);
  void redrawAfterDomUpdate();
  refreshShapes();
}

function selectMergeInput(id: string) {
  selectedMergeInputId.value = selectedMergeInputId.value === id ? null : id;
}

function moveMergeInput(direction: -1 | 1) {
  const node = selectedNode.value;
  const from = selectedMergeIndex.value;
  const to = from + direction;
  if (!node || from < 0 || to < 0 || to >= mergeInputs.value.length) return;
  const ids = mergeInputs.value.map(item => item.id);
  [ids[from], ids[to]] = [ids[to]!, ids[from]!];
  recordHistory();
  updateNodeParam(node.id, "order", ids);
  void redrawAfterDomUpdate();
  refreshShapes();
}

// 切换选中节点时清空合并输入的选中态
watch(() => selectedNode.value?.id, () => {
  selectedMergeInputId.value = null;
});

// 序列与高级层的参数编辑配置（与后端 model_builder 支持的参数一致）
interface AdvancedField {
  key: string;
  label: string;
  kind: "number" | "boolean";
}

interface AdvancedInspector {
  icon: string;
  color: string;
  title: string;
  intro: string;
  fields: AdvancedField[];
}

const ADVANCED_INSPECTORS: Record<string, AdvancedInspector> = {
  LSTM: {
    icon: "mdi:repeat",
    color: "text-cyan",
    title: "LSTM 参数",
    intro: "循环神经网络层，擅长处理序列数据；hidden_size 决定记忆容量。",
    fields: [
      { key: "hidden_size", label: "Hidden Size 隐藏维度", kind: "number" },
      { key: "num_layers", label: "Num Layers 堆叠层数", kind: "number" },
      { key: "return_sequences", label: "Return Sequences 返回完整序列", kind: "boolean" },
      { key: "bidirectional", label: "Bidirectional 双向", kind: "boolean" },
    ],
  },
  Seq2Seq: {
    icon: "mdi:swap-horizontal",
    color: "text-indigo",
    title: "Seq2Seq 参数",
    intro: "编码器-解码器结构，把一个序列转换成另一个序列。",
    fields: [
      { key: "hidden_size", label: "Hidden Size 隐藏维度", kind: "number" },
      { key: "output_size", label: "Output Size 输出维度", kind: "number" },
      { key: "target_length", label: "Target Length 目标序列长度", kind: "number" },
      { key: "num_layers", label: "Num Layers 堆叠层数", kind: "number" },
    ],
  },
  TransformerEncoder: {
    icon: "mdi:layers-outline",
    color: "text-purple",
    title: "Transformer 参数",
    intro: "自注意力编码器；d_model 需能被 num_heads 整除。",
    fields: [
      { key: "d_model", label: "d_model 特征维度", kind: "number" },
      { key: "num_heads", label: "Num Heads 注意力头数", kind: "number" },
      { key: "num_layers", label: "Num Layers 编码器层数", kind: "number" },
      { key: "dim_feedforward", label: "FFN 维度", kind: "number" },
      { key: "dropout", label: "Dropout 比例", kind: "number" },
    ],
  },
  SelfAttention: {
    icon: "mdi:eye-outline",
    color: "text-blue",
    title: "Self Attention 参数",
    intro: "多头自注意力；embed_dim 需能被 num_heads 整除。",
    fields: [
      { key: "embed_dim", label: "Embed Dim 嵌入维度", kind: "number" },
      { key: "num_heads", label: "Num Heads 注意力头数", kind: "number" },
      { key: "dropout", label: "Dropout 比例", kind: "number" },
    ],
  },
  VAE: {
    icon: "mdi:creation",
    color: "text-rose",
    title: "VAE 参数",
    intro: "变分自编码器，把输入压缩到 latent_dim 维隐空间再重建。",
    fields: [
      { key: "latent_dim", label: "Latent Dim 隐空间维度", kind: "number" },
      { key: "output_features", label: "Output Features 重建维度", kind: "number" },
    ],
  },
  GraphConv: {
    icon: "mdi:graph",
    color: "text-emerald",
    title: "GraphConv 参数",
    intro: "图卷积层，沿邻接关系聚合节点特征。",
    fields: [
      { key: "out_features", label: "Out Features 输出特征数", kind: "number" },
    ],
  },
};

const advancedInspector = computed(() =>
  selectedNode.value ? ADVANCED_INSPECTORS[selectedNode.value.type] ?? null : null
);

// —— 自定义容器 ——
const containerSummary = computed(() => {
  const node = selectedNode.value;
  if (!node || node.type !== "Container") return null;
  return {
    layers: containerLayerCount(node),
    inputs: containerInputPorts(node).length,
    outputs: containerOutputPorts(node).length,
  };
});

function renameContainer(event: Event) {
  const node = selectedNode.value;
  if (!node) return;
  const name = (event.target as HTMLInputElement).value.trim();
  if (!name) return;
  node.title = name;
  void redrawAfterDomUpdate();
}

// Input/Output 端口改名（title 即端口标签）
function renamePort(event: Event) {
  const node = selectedNode.value;
  if (!node) return;
  const name = (event.target as HTMLInputElement).value.trim();
  if (!name) return;
  node.title = name;
  void redrawAfterDomUpdate();
}

function enterCurrentContainer() {
  const node = selectedNode.value;
  if (node) enterContainer(node.id);
}

function saveCurrentToLibrary() {
  const node = selectedNode.value;
  if (!node) return;
  const def = saveContainerToLibrary(node, node.title);
  if (def) {
    showToast("success", `已保存容器「${def.name}」到组件库，可在左侧"我的容器"复用。`);
  }
}

function handleBooleanChange(key: string, event: Event) {
  setParam(key, (event.target as HTMLInputElement).checked);
}

function handleInputShapeChange(event: Event) {
  const node = selectedNode.value;
  if (!node) return;

  const rawItems = (event.target as HTMLInputElement).value.split(",").map(item => item.trim());

  if (rawItems.length === 0 || rawItems.some(item => item === "")) {
    showToast("warning", "Input shape 不能为空，格式示例：1,28,28。");
    return;
  }

  const shape = rawItems.map(item => Number(item));

  if (shape.some(item => Number.isNaN(item) || item <= 0)) {
    showToast("warning", "Input shape 必须是正数，格式示例：1,28,28。");
    return;
  }

  recordHistory();
  updateNodeParam(node.id, "shape", shape);
  void redrawAfterDomUpdate();
  refreshShapes();
}

const inputShapeValue = computed(() => {
  const shape = selectedNode.value?.params?.shape;
  return Array.isArray(shape) ? shape.join(",") : "";
});
</script>

<template>
  <!-- 右侧：参数面板（悬浮层，选中节点时滑入，不挤压画布） -->
  <aside ref="inspectorRef" class="inspector-panel" :class="{ open: panelOpen }" id="inspector-content">
    <!-- 收起箭头：收起后再次点击节点卡片才会重新展开 -->
    <button v-if="panelOpen" class="inspector-collapse" title="收起参数面板" @click="collapsePanel">
      <iconify-icon icon="mdi:chevron-right"></iconify-icon>
    </button>

    <!-- 节点头部：彩色图标 + 可编辑名称 + 类型（所有卡片通用；容器用其专属段落） -->
    <div v-if="selectedNode && selectedNode.type !== 'Container'" class="inspector-head">
      <span v-if="nodeMeta" :class="`inspector-head-icon layer-icon ${nodeMeta.color}`">
        <iconify-icon :icon="nodeMeta.icon"></iconify-icon>
      </span>
      <div class="inspector-head-main">
        <div class="inspector-name-row">
          <input
            class="inspector-name-input"
            type="text"
            :value="selectedNode.title"
            placeholder="未命名"
            title="点击可修改这张卡片的名称"
            @change="renamePort"
          >
          <iconify-icon class="inspector-name-pencil" icon="mdi:pencil-outline"></iconify-icon>
        </div>
        <span class="inspector-head-type">{{ nodeMeta?.badge }}<template v-if="nodeMeta?.desc"> · {{ nodeMeta?.desc }}</template></span>
      </div>
    </div>

    <!-- 未选中节点 -->
    <div v-if="!selectedNode" class="empty-inspector">
      <iconify-icon icon="mdi:cursor-default-click-outline"></iconify-icon>
      <p>还没有选中节点</p>
      <span>单击画布中的任意节点，<br>即可在这里查看和修改它的参数</span>
    </div>

    <!-- Conv2D -->
    <div v-else-if="selectedNode.type === 'Conv2D'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-blue" icon="mdi:grid-large"></iconify-icon>
        <h2>Conv2D 参数</h2>
      </div>

      <div class="field-stack">
        <ParamNumberField label="Out Channels (输出通道)" :value="selectedNode.params.out_channels" hint="输出多少个特征图。越大能学到越丰富的特征，但更慢、更容易过拟合。" recommend="推荐 8 ~ 64" :min="1" range-message="输出通道数必须为正整数。" integer-message="输出通道数必须为正整数。" empty-message="输出通道数不能为空。" @change="setParam('out_channels', $event)" />
        <ParamNumberField label="Kernel Size (卷积核大小)" :value="selectedNode.params.kernel_size" hint="每次扫描覆盖的局部区域边长。数值越大，一次看到的范围越广，但输出尺寸缩得越多、计算也越大。" recommend="常用 3 或 5" :min="1" range-message="卷积核大小必须为正整数。" integer-message="卷积核大小必须为正整数。" empty-message="卷积核大小不能为空。" @change="setParam('kernel_size', $event)" />
        <div class="field-grid">
          <ParamNumberField label="Stride" :value="selectedNode.params.stride" hint="卷积核每次移动的步长。越大输出尺寸越小。" recommend="常用 1" :min="1" range-message="Stride 必须为正整数。" integer-message="Stride 必须为正整数。" empty-message="Stride 不能为空。" @change="setParam('stride', $event)" />
          <ParamNumberField label="Padding" :value="selectedNode.params.padding" hint="在边缘补几圈 0，用来保持输出尺寸不缩得太快。" recommend="常用 0 或 1" :min="0" range-message="Padding 必须是非负整数。" integer-message="Padding 必须是非负整数。" empty-message="Padding 不能为空。" @change="setParam('padding', $event)" />
        </div>
      </div>

      <div class="shape-preview">
        <span>预计输出尺寸</span>
        <strong>{{ liveOutputShape }}</strong>
      </div>

      <section class="info-card blue-card">
        <h4><iconify-icon icon="mdi:information-outline"></iconify-icon> 卷积层 Conv2D</h4>
        <p>卷积层用于提取局部特征，out_channels 越大，学习到的特征映射越丰富，但计算开销也会增加。</p>
      </section>
    </div>

    <!-- Linear -->
    <div v-else-if="selectedNode.type === 'Linear'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-cyan" icon="mdi:ray-start-end"></iconify-icon>
        <h2>Linear 参数</h2>
      </div>

      <div class="field-stack">
        <label class="form-field muted-field">
          <span>In Features 输入特征数</span>
          <input type="text" :value="linearActualInFeatures" readonly>
          <small>由前一层自动推导</small>
        </label>

        <ParamNumberField label="Out Features 输出神经元" :value="selectedNode.params.out_features" hint="这一层输出多少个数。若是整张网络的最后一层，一般把它设成要区分的类别总数。" recommend="末层 = 类别数" :min="1" range-message="输出神经元数必须为正整数。" integer-message="输出神经元数必须为正整数。" empty-message="输出神经元数不能为空。" @change="setParam('out_features', $event)" />
      </div>

      <div class="shape-preview">
        <span>预计输出尺寸</span>
        <strong>{{ liveOutputShape }}</strong>
      </div>
    </div>

    <!-- Pooling -->
    <div v-else-if="selectedNode.type === 'Pooling'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-purple" icon="mdi:resize"></iconify-icon>
        <h2>Pooling 参数</h2>
      </div>

      <div class="field-stack">
        <ParamNumberField label="Kernel Size 池化核大小" :value="selectedNode.params.kernel_size" hint="池化窗口大小。2 表示每 2×2 区域取一个值，把特征图缩小一半。" recommend="推荐 2" :min="1" range-message="池化核大小必须为正整数。" integer-message="池化核大小必须为正整数。" empty-message="池化核大小不能为空。" @change="setParam('kernel_size', $event)" />
        <ParamNumberField label="Stride 步长" :value="selectedNode.params.stride" hint="窗口每次移动的步长，通常与池化核大小相同。" recommend="常用 2" :min="1" range-message="池化步长必须为正整数。" integer-message="池化步长必须为正整数。" empty-message="池化步长不能为空。" @change="setParam('stride', $event)" />
        <ParamNumberField label="Padding 填充" :value="selectedNode.params.padding" hint="边缘补零圈数，一般不用。" recommend="常用 0" :min="0" range-message="池化填充必须是非负整数。" integer-message="池化填充必须是非负整数。" empty-message="池化填充不能为空。" @change="setParam('padding', $event)" />
      </div>

      <div class="shape-preview">
        <span>预计输出尺寸</span>
        <strong>{{ liveOutputShape }}</strong>
      </div>
    </div>

    <!-- Dropout -->
    <div v-else-if="selectedNode.type === 'Dropout'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-amber" icon="mdi:filter-off-outline"></iconify-icon>
        <h2>Dropout 参数</h2>
      </div>

      <div class="field-stack">
        <ParamNumberField label="Dropout Rate 随机失活比例" :value="selectedNode.params.p" :min="0" :max="1" :integer="false" step="0.01" range-message="Dropout Rate 必须在 0 到 1 之间。" empty-message="Dropout Rate 不能为空。" @change="setParam('p', $event)" />
      </div>

      <section class="info-card">
        <p>p 取 0 到 1 之间的小数，表示每次随机丢弃神经元的比例；值越大丢弃越多、正则化越强。</p>
      </section>
    </div>

    <!-- Input -->
    <div v-else-if="selectedNode.type === 'Input'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-emerald" icon="mdi:login-variant"></iconify-icon>
        <h2>Input 参数</h2>
      </div>

      <label class="form-field">
        <span>Input Shape 输入形状</span>
        <input id="input-shape-field" type="text" :value="inputShapeValue" @change="handleInputShapeChange">
        <small>格式示例：1,28,28（作为容器端口时，实际尺寸由外部连接决定）</small>
      </label>
    </div>

    <!-- Output（在容器里作为输出端口） -->
    <div v-else-if="selectedNode.type === 'Output'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-rose" icon="mdi:logout-variant"></iconify-icon>
        <h2>Output 参数</h2>
      </div>

      <section class="info-card">
        <p>Output 标记数据的出口。放在容器子画板里时，它就是容器对外的一个输出端口。</p>
      </section>
    </div>

    <!-- 合并运算模块：add / concat / matmul 三合一 -->
    <div v-else-if="selectedNode.type === 'Merge'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-cyan" icon="mdi:call-merge"></iconify-icon>
        <h2>合并运算</h2>
      </div>

      <section class="info-card">
        <p>把两条或多条分支合并成一条：先选择合并模式，矩阵乘法还可调整输入顺序。</p>
      </section>

      <!-- 模式选择：初始为空，点选后高亮 -->
      <div class="merge-section">
        <span class="merge-section-label">合并模式</span>
        <div class="merge-mode-toggle" role="group" aria-label="合并模式">
          <button
            v-for="m in MERGE_MODES"
            :key="m.value"
            type="button"
            :class="{ active: mergeMode === m.value }"
            @click="setMergeMode(m.value)"
          >
            <span class="merge-mode-op">{{ m.op }}</span>
            <span class="merge-mode-name">{{ m.label }}</span>
            <span class="merge-mode-en">{{ m.en }}</span>
          </button>
        </div>
        <small v-if="!mergeMode" class="merge-warn">尚未选择模式，请点选 add / concat / matmul。</small>
        <small v-else class="merge-desc">{{ currentMerge?.desc }}</small>
      </div>

      <!-- 计算过程可视化 + 顺序控制 -->
      <div class="merge-section">
        <span class="merge-section-label">
          计算过程
          <em v-if="mergeMode === 'matmul'">（顺序影响结果）</em>
        </span>

        <div v-if="mergeInputs.length === 0" class="merge-empty">
          还没有输入连线。请从其它节点连线到本模块（支持两个及以上输入）。
        </div>

        <template v-else>
          <div class="merge-flow">
            <template v-for="(item, i) in mergeInputs" :key="item.id">
              <button
                type="button"
                class="merge-chip"
                :class="{ active: selectedMergeInputId === item.id }"
                :title="item.title"
                @click="selectMergeInput(item.id)"
              >
                <span class="merge-chip-tag">input{{ i + 1 }}</span>
                <span class="merge-chip-name">{{ item.title }}</span>
              </button>
              <span v-if="i < mergeInputs.length - 1" class="merge-op">{{ currentMerge?.op || "·" }}</span>
            </template>
            <span class="merge-eq">=</span>
            <span class="merge-out">输出</span>
          </div>

          <div class="merge-order-bar">
            <button type="button" class="merge-arrow" :disabled="!canMoveMergeLeft" title="向前移动" @click="moveMergeInput(-1)">⬅</button>
            <button type="button" class="merge-arrow" :disabled="!canMoveMergeRight" title="向后移动" @click="moveMergeInput(1)">➡</button>
            <span class="merge-order-hint">
              {{ selectedMergeInputId ? "已选中输入，可用 ⬅ / ➡ 调整顺序" : "点选上方某个 input，再用 ⬅ / ➡ 调整顺序" }}
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- Add（旧版本模块，保留兼容） -->
    <div v-else-if="selectedNode.type === 'Add'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-cyan" icon="mdi:plus-circle-outline"></iconify-icon>
        <h2>Add 节点（旧版）</h2>
      </div>
      <section class="info-card">
        <p>这是旧版的相加合并节点，仅为兼容历史项目保留。新建模型请改用「合并运算」模块（支持 add / concat / matmul）。</p>
      </section>
    </div>

    <!-- 自定义容器（组合容器） -->
    <div v-else-if="selectedNode.type === 'Container'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-teal" icon="mdi:package-variant-closed"></iconify-icon>
        <h2>容器</h2>
      </div>

      <label class="form-field">
        <span>容器名称</span>
        <input type="text" :value="selectedNode.title" @change="renameContainer">
        <small>作为导出代码里的子模块名</small>
      </label>

      <div v-if="containerSummary" class="container-summary">
        <div><strong>{{ containerSummary.layers }}</strong><span>内部层</span></div>
        <div><strong>{{ containerSummary.inputs }}</strong><span>输入端口</span></div>
        <div><strong>{{ containerSummary.outputs }}</strong><span>输出端口</span></div>
      </div>

      <div class="container-actions">
        <button class="container-action-btn primary" @click="enterCurrentContainer">
          <iconify-icon icon="mdi:folder-open-outline"></iconify-icon>
          进入编辑
        </button>
        <button class="container-action-btn" @click="saveCurrentToLibrary">
          <iconify-icon icon="mdi:content-save-outline"></iconify-icon>
          存为可复用
        </button>
      </div>

      <section class="info-card">
        <p>容器把一整张子图打包成一个节点。<b>双击容器</b>（或点"进入编辑"）进入子画板，像搭模型一样单击或拖入层；子图里每个 <b>Input</b> = 一个输入端口，每个 <b>Output</b> = 一个输出端口。输入 / 输出尺寸显示在画布上各端口旁。</p>
      </section>
    </div>

    <!-- 序列与高级层（LSTM / Seq2Seq / Transformer / Attention / VAE / GCN） -->
    <div v-else-if="advancedInspector" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon :class="advancedInspector.color" :icon="advancedInspector.icon"></iconify-icon>
        <h2>{{ advancedInspector.title }}</h2>
      </div>

      <div class="field-stack">
        <template v-for="field in advancedInspector.fields" :key="field.key">
          <ParamNumberField
            v-if="field.kind === 'number'"
            :param-key="field.key"
            :label="field.label"
            :value="selectedNode.params[field.key]"
            :min="field.key === 'dropout' ? 0 : 1"
            :max="field.key === 'dropout' ? 1 : undefined"
            :integer="field.key !== 'dropout'"
            :step="field.key === 'dropout' ? 0.01 : 1"
            :range-message="field.key === 'dropout' ? 'Dropout 比例必须在 0 到 1 之间。' : `${field.label} 必须为正整数。`"
            :integer-message="`${field.label} 必须为正整数。`"
            :empty-message="`${field.label} 不能为空。`"
            @change="setParam(field.key, $event)"
          />
          <label v-else class="form-field switch-field" :data-param-key="field.key">
            <span>{{ field.label }}</span>
            <input
              type="checkbox"
              :checked="Boolean(selectedNode.params[field.key])"
              @change="handleBooleanChange(field.key, $event)"
            >
          </label>
        </template>
      </div>

      <section class="info-card">
        <p>{{ advancedInspector.intro }}</p>
      </section>
    </div>

    <!-- 其他无参数节点 -->
    <div v-else class="simple-inspector">
      <iconify-icon icon="mdi:layers-outline"></iconify-icon>
      <h2>{{ selectedNode.badge || selectedNode.type }} 节点</h2>
      <p>该节点无可编辑参数，当前使用默认设置。</p>
    </div>
  </aside>
</template>
