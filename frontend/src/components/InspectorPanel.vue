<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { validateModelStructure } from "../api/client";
import { enterContainer, recordHistory, redrawAfterDomUpdate } from "../canvas";
import {
  activeCanvas,
  containerInputPorts,
  containerLayerCount,
  containerOutputPorts,
  getCurrentModelGraph,
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
  <aside class="inspector-panel" :class="{ open: panelOpen }" id="inspector-content">
    <!-- 收起箭头：收起后再次点击节点卡片才会重新展开 -->
    <button v-if="panelOpen" class="inspector-collapse" title="收起参数面板" @click="collapsePanel">
      <iconify-icon icon="mdi:chevron-right"></iconify-icon>
    </button>

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
        <span>名称</span>
        <input type="text" :value="selectedNode.title" @change="renamePort">
        <small>在容器里作为输入端口的名字，多个输入时便于区分</small>
      </label>

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

      <label class="form-field">
        <span>名称</span>
        <input type="text" :value="selectedNode.title" @change="renamePort">
        <small>在容器里作为输出端口的名字，多个输出时便于区分</small>
      </label>

      <section class="info-card">
        <p>Output 标记数据的出口。放在容器子画板里时，它就是容器对外的一个输出端口。</p>
      </section>
    </div>

    <!-- Add -->
    <div v-else-if="selectedNode.type === 'Add'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-cyan" icon="mdi:plus-circle-outline"></iconify-icon>
        <h2>Add 节点</h2>
      </div>
      <section class="info-card">
        <p>Add 节点会在导出给后端时折叠为目标节点的 add 合并方式。</p>
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
        <p>容器把一整张子图打包成一个节点。<b>双击容器</b>（或点"进入编辑"）进入子画板，像搭模型一样拖入层；子图里每个 <b>Input</b> = 一个输入端口，每个 <b>Output</b> = 一个输出端口。输入 / 输出尺寸显示在画布上各端口旁。</p>
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
          <label v-else class="form-field switch-field">
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
