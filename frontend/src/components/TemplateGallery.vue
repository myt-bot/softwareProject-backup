<script setup lang="ts">
import { computed } from "vue";
import { loadTemplateToCanvas } from "../actions";
import { templateLibrary, ui } from "../store";
import type { TemplateMeta } from "../types";

const emit = defineEmits<{ selected: [] }>();

// 模板分类的展示样式（图标 + 中文标签 + 颜色）
const FAMILY_STYLES: Record<string, { icon: string; label: string; color: string }> = {
  feedforward: { icon: "mdi:ray-start-end", label: "全连接", color: "cyan" },
  cnn: { icon: "mdi:grid-large", label: "卷积", color: "blue" },
  sequence: { icon: "mdi:repeat", label: "序列", color: "indigo" },
  attention: { icon: "mdi:eye-outline", label: "注意力", color: "purple" },
  generative: { icon: "mdi:creation", label: "生成", color: "rose" },
  graph: { icon: "mdi:graph", label: "图网络", color: "emerald" },
};

// 每个模板的新手友好元信息：难度、一句话用途、结构预览、是否推荐新手
interface ExtraMeta {
  difficulty: "新手" | "进阶";
  purpose: string;
  structure: string[];
  recommended?: boolean;
}
const META_RULES: Array<{ test: RegExp; meta: ExtraMeta }> = [
  { test: /linear|perceptron|感知/i, meta: { difficulty: "新手", purpose: "最简单的分类模型，理解训练流程的第一站", structure: ["Input", "Linear", "Output"], recommended: true } },
  { test: /mlp/i, meta: { difficulty: "新手", purpose: "多层全连接网络，能识别简单的图像", structure: ["Input", "Flatten", "Linear", "ReLU", "Linear", "Output"] } },
  { test: /lenet/i, meta: { difficulty: "新手", purpose: "结构清晰的经典小型卷积网络，适合入门", structure: ["Input", "Conv", "Pool", "Conv", "Pool", "Flatten", "Linear", "Output"], recommended: true } },
  { test: /resnet/i, meta: { difficulty: "进阶", purpose: "带残差连接的卷积网络，更深也易训练", structure: ["Input", "Conv", "残差块", "Pool", "Linear", "Output"] } },
  { test: /lstm/i, meta: { difficulty: "进阶", purpose: "循环网络，处理有先后顺序的序列数据", structure: ["Input", "LSTM", "Linear", "Output"] } },
  { test: /seq2seq/i, meta: { difficulty: "进阶", purpose: "序列到序列，把一段序列转换成另一段", structure: ["Input", "编码器", "解码器", "Output"] } },
  { test: /transformer/i, meta: { difficulty: "进阶", purpose: "注意力编码器，大模型的基础结构", structure: ["Input", "Attention", "前馈", "Output"] } },
  { test: /attention|注意/i, meta: { difficulty: "进阶", purpose: "自注意力机制演示", structure: ["Input", "SelfAttention", "Output"] } },
  { test: /vae/i, meta: { difficulty: "进阶", purpose: "变分自编码器，能生成新样本", structure: ["Input", "编码器", "隐变量", "解码器", "Output"] } },
  { test: /gcn|graph|图/i, meta: { difficulty: "进阶", purpose: "图卷积网络，处理图结构数据", structure: ["Input", "GraphConv", "GraphConv", "Output"] } },
];

function extraMeta(template: TemplateMeta): ExtraMeta {
  const found = META_RULES.find(rule => rule.test.test(`${template.key} ${template.name}`));
  return found?.meta || { difficulty: "进阶", purpose: template.description || "", structure: [] };
}

function familyStyle(template: TemplateMeta) {
  return FAMILY_STYLES[template.family || ""] || { icon: "mdi:shape-outline", label: "模板", color: "cyan" };
}

// 新手模板排在前面，便于初学者先看到简单的
const sortedTemplates = computed(() =>
  [...templateLibrary.items].sort((a, b) => {
    const da = extraMeta(a).difficulty === "新手" ? 0 : 1;
    const db = extraMeta(b).difficulty === "新手" ? 0 : 1;
    return da - db;
  })
);

function close() {
  ui.templateGalleryOpen = false;
}

async function pick(template: TemplateMeta) {
  await loadTemplateToCanvas(template.key, template.name);
  // loadTemplateToCanvas 仅在加载成功后关闭窗口。
  // 因此只有真正选择并成功加载模板时，才通知首页进入工作台。
  if (!ui.templateGalleryOpen) emit("selected");
}
</script>

<template>
  <!-- 快速开始模板库 -->
  <div class="modal" :class="{ hidden: !ui.templateGalleryOpen }" id="template-gallery">
    <div class="modal-card template-gallery-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:lightning-bolt"></iconify-icon>
          <div>
            <h2>快速开始模板</h2>
            <p>选择一个经典网络，一键加载到当前画布</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-gallery" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="template-grid">
        <button
          v-for="template in sortedTemplates"
          :key="template.key"
          class="template-card"
          :data-template="template.key"
          @click="pick(template)"
        >
          <span v-if="extraMeta(template).recommended" class="template-recommend">👍 推荐新手先试</span>
          <div class="template-card-head">
            <span :class="`template-icon ${familyStyle(template).color}`">
              <iconify-icon :icon="familyStyle(template).icon"></iconify-icon>
            </span>
            <div class="template-tags">
              <span :class="`template-tag ${familyStyle(template).color}`">{{ familyStyle(template).label }}</span>
              <span class="template-difficulty" :class="extraMeta(template).difficulty === '新手' ? 'easy' : 'hard'">
                {{ extraMeta(template).difficulty }}
              </span>
            </div>
          </div>
          <strong>{{ template.name }}</strong>
          <p>{{ extraMeta(template).purpose || template.description }}</p>
          <!-- 结构预览：层的流程缩略 -->
          <div v-if="extraMeta(template).structure.length" class="template-structure">
            <template v-for="(step, i) in extraMeta(template).structure" :key="i">
              <span class="template-step">{{ step }}</span>
              <iconify-icon v-if="i < extraMeta(template).structure.length - 1" icon="mdi:chevron-right" class="template-arrow"></iconify-icon>
            </template>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>
