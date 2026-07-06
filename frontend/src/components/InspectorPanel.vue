<script setup lang="ts">
import { computed } from "vue";
import { redrawAfterDomUpdate } from "../canvas";
import { activeCanvas, showToast, ui, updateNodeParam } from "../store";
import ParamNumberField from "./ParamNumberField.vue";

const canvas = computed(() => activeCanvas());

const selectedNode = computed(() =>
  canvas.value.nodes.find(item => item.id === canvas.value.selectedNodeId) || null
);

// 面板悬浮于画布之上：选中节点且未被手动收起时滑入，不改变画布尺寸
const panelOpen = computed(() => Boolean(selectedNode.value) && !ui.inspectorCollapsed);

function collapsePanel() {
  ui.inspectorCollapsed = true;
}

// Linear 的 shape mismatch 提示（教学演示：in_features 应为 2704）
const linearShapeError = computed(
  () => canvas.value.validationStatus === "failed" && canvas.value.inFeatures !== 2704
);

function setParam(key: string, value: number) {
  if (!selectedNode.value) return;
  updateNodeParam(selectedNode.value.id, key, value);
  // 节点卡片上的 note 可能变化导致高度变化，需要重绘连线
  void redrawAfterDomUpdate();
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

  updateNodeParam(node.id, "shape", shape);
  void redrawAfterDomUpdate();
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
        <ParamNumberField label="Out Channels (输出通道)" :value="selectedNode.params.out_channels" @change="setParam('out_channels', $event)" />
        <ParamNumberField label="Kernel Size (卷积核大小)" :value="selectedNode.params.kernel_size" @change="setParam('kernel_size', $event)" />
        <div class="field-grid">
          <ParamNumberField label="Stride" :value="selectedNode.params.stride" @change="setParam('stride', $event)" />
          <ParamNumberField label="Padding" :value="selectedNode.params.padding" @change="setParam('padding', $event)" />
        </div>
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

        <ParamNumberField label="Out Features 输出神经元" :value="selectedNode.params.out_features" @change="setParam('out_features', $event)" />
      </div>
    </div>

    <!-- Pooling -->
    <div v-else-if="selectedNode.type === 'Pooling'" class="inspector-scroll">
      <div class="inspector-title">
        <iconify-icon class="text-purple" icon="mdi:resize"></iconify-icon>
        <h2>Pooling 参数</h2>
      </div>

      <div class="field-stack">
        <ParamNumberField label="Kernel Size 池化核大小" :value="selectedNode.params.kernel_size" @change="setParam('kernel_size', $event)" />
        <ParamNumberField label="Stride 步长" :value="selectedNode.params.stride" @change="setParam('stride', $event)" />
        <ParamNumberField label="Padding 填充" :value="selectedNode.params.padding" @change="setParam('padding', $event)" />
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
        <p>p 一般取 0 到 1 之间的小数，例如 0.5。</p>
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

    <!-- 其他无参数节点 -->
    <div v-else class="simple-inspector">
      <iconify-icon icon="mdi:layers-outline"></iconify-icon>
      <h2>{{ selectedNode.badge || selectedNode.type }} 节点</h2>
      <p>该节点无可编辑参数，当前使用默认设置。</p>
    </div>
  </aside>
</template>
