<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { validateModelStructure } from "../api/client";
import { recordHistory, redrawAfterDomUpdate } from "../canvas";
import { activeCanvas, getCurrentModelGraph, showToast, ui, updateNodeParam } from "../store";
import ParamNumberField from "./ParamNumberField.vue";

const canvas = computed(() => activeCanvas());

const selectedNode = computed(() =>
  canvas.value.nodes.find(item => item.id === canvas.value.selectedNodeId) || null
);

// 实时形状预览：改参数时向云端请求维度推导（防抖），无需本地 Agent
const shapesMap = ref<Record<string, { output_shape?: number[] | null }>>({});
let shapeTimer: ReturnType<typeof setTimeout> | undefined;

function refreshShapes() {
  clearTimeout(shapeTimer);
  shapeTimer = setTimeout(async () => {
    try {
      const result = await validateModelStructure(getCurrentModelGraph(canvas.value));
      shapesMap.value = result.shapes || {};
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

// 选中节点变化或组件挂载时刷新一次预览
watch(selectedNode, node => {
  if (node) refreshShapes();
}, { immediate: true });

// 面板悬浮于画布之上：选中节点且未被手动收起时滑入，不改变画布尺寸
const panelOpen = computed(() => Boolean(selectedNode.value) && !ui.inspectorCollapsed);

function collapsePanel() {
  ui.inspectorCollapsed = true;
}

// Linear 的 shape mismatch 提示（教学演示：in_features 应为 2704）
const linearShapeError = computed(
  () => canvas.value.validationStatus === "failed" && canvas.value.inFeatures !== 2704
);

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

function handleBooleanChange(key: string, event: Event) {
  setParam(key, (event.target as HTMLInputElement).checked);
}

function autoFix() {
  canvas.value.inFeatures = 2704;
  showToast("success", "参数已自动修复为 2704。");
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
        <ParamNumberField label="Out Channels (输出通道)" :value="selectedNode.params.out_channels" hint="输出多少个特征图。越大能学到越丰富的特征，但更慢、更容易过拟合。" recommend="推荐 8 ~ 64" @change="setParam('out_channels', $event)" />
        <ParamNumberField label="Kernel Size (卷积核大小)" :value="selectedNode.params.kernel_size" hint="每次扫描覆盖的局部区域边长。数值越大，一次看到的范围越广，但输出尺寸缩得越多、计算也越大。" recommend="常用 3 或 5" @change="setParam('kernel_size', $event)" />
        <div class="field-grid">
          <ParamNumberField label="Stride" :value="selectedNode.params.stride" hint="卷积核每次移动的步长。越大输出尺寸越小。" recommend="常用 1" @change="setParam('stride', $event)" />
          <ParamNumberField label="Padding" :value="selectedNode.params.padding" hint="在边缘补几圈 0，用来保持输出尺寸不缩得太快。" recommend="常用 0 或 1" @change="setParam('padding', $event)" />
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

      <section v-if="linearShapeError" class="error-card">
        <h4><iconify-icon icon="mdi:alert-circle"></iconify-icon> Shape mismatch</h4>
        <p>前一层 Flatten 输出维度为 2704，而当前 Linear.in_features 设为 {{ canvas.inFeatures }}。</p>
        <button id="btn-autofix" @click="autoFix">一键修复</button>
      </section>

      <div class="field-stack">
        <label class="form-field muted-field">
          <span>In Features 输入特征数</span>
          <input type="text" :value="canvas.inFeatures" readonly>
          <small>由前一层自动推导</small>
        </label>

        <ParamNumberField label="Out Features 输出神经元" :value="selectedNode.params.out_features" hint="这一层输出多少个数。若是整张网络的最后一层，一般把它设成要区分的类别总数。" recommend="末层 = 类别数" @change="setParam('out_features', $event)" />
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
        <ParamNumberField label="Kernel Size 池化核大小" :value="selectedNode.params.kernel_size" hint="池化窗口大小。2 表示每 2×2 区域取一个值，把特征图缩小一半。" recommend="推荐 2" @change="setParam('kernel_size', $event)" />
        <ParamNumberField label="Stride 步长" :value="selectedNode.params.stride" hint="窗口每次移动的步长，通常与池化核大小相同。" recommend="常用 2" @change="setParam('stride', $event)" />
        <ParamNumberField label="Padding 填充" :value="selectedNode.params.padding" hint="边缘补零圈数，一般不用。" recommend="常用 0" @change="setParam('padding', $event)" />
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
        <ParamNumberField label="Dropout Rate 随机失活比例" :value="selectedNode.params.p" @change="setParam('p', $event)" />
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
        <small>格式示例：1,28,28</small>
      </label>
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
