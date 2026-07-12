<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchLayerTeaching,
  fetchModelTeaching,
  fetchParameterTeaching,
  isBackendUnavailable,
} from "../api/client";
import type {
  GraphNode,
  LayerTeaching,
  ModelGraph,
  ModelTeachingOverview,
  ParameterTeaching,
} from "../types";

const props = defineProps<{
  open: boolean;
  available: boolean;
  selectedLayer: GraphNode | null;
  modelGraph: ModelGraph;
}>();

defineEmits<{
  open: [];
  close: [];
}>();

type TeachingTab = "layer" | "parameters" | "model";

const activeTab = ref<TeachingTab>("layer");
const layerTeaching = ref<LayerTeaching | null>(null);
const selectedParameter = ref<string | null>(null);
const parameterTeaching = ref<ParameterTeaching | null>(null);
const modelOverview = ref<ModelTeachingOverview | null>(null);
const layerLoading = ref(false);
const parameterLoading = ref(false);
const modelLoading = ref(false);
const layerError = ref("");
const parameterError = ref("");
const modelError = ref("");
const layerCache = new Map<string, LayerTeaching>();
const parameterCache = new Map<string, ParameterTeaching>();
let layerRequestId = 0;
let parameterRequestId = 0;
let modelRequestId = 0;

const parameters = computed(() => Object.keys(props.selectedLayer?.params ?? {}));
const currentParameterValue = computed(() => {
  if (!props.selectedLayer || !selectedParameter.value) return undefined;
  return props.selectedLayer.params[selectedParameter.value];
});

function errorMessage(error: unknown): string {
  if (isBackendUnavailable(error)) return "后端服务未启动，画布仍可继续使用。";
  return error instanceof Error ? error.message : "请求教学内容失败，请稍后重试。";
}

function displayValue(value: unknown): string {
  if (value === undefined) return "未设置";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

async function loadLayerTeaching() {
  const layerType = props.selectedLayer?.type;
  if (!props.open || !layerType) {
    layerTeaching.value = null;
    layerLoading.value = false;
    layerError.value = "";
    return;
  }

  const requestId = ++layerRequestId;
  const cached = layerCache.get(layerType);
  if (cached) {
    layerTeaching.value = cached;
    layerLoading.value = false;
    layerError.value = "";
    return;
  }

  layerLoading.value = true;
  layerError.value = "";
  try {
    const result = await fetchLayerTeaching(layerType);
    layerCache.set(layerType, result);
    if (requestId === layerRequestId && props.selectedLayer?.type === layerType) {
      layerTeaching.value = result;
    }
  } catch (error) {
    if (requestId === layerRequestId) layerError.value = errorMessage(error);
  } finally {
    if (requestId === layerRequestId) layerLoading.value = false;
  }
}

async function selectParameter(parameter: string) {
  const layerType = props.selectedLayer?.type;
  if (!layerType) return;
  selectedParameter.value = parameter;
  activeTab.value = "parameters";
  const requestId = ++parameterRequestId;
  const cacheKey = `${layerType}:${parameter}`;
  const cached = parameterCache.get(cacheKey);
  if (cached) {
    parameterTeaching.value = cached;
    parameterLoading.value = false;
    parameterError.value = "";
    return;
  }

  parameterLoading.value = true;
  parameterError.value = "";
  parameterTeaching.value = null;
  try {
    const result = await fetchParameterTeaching(layerType, parameter);
    parameterCache.set(cacheKey, result);
    if (
      requestId === parameterRequestId
      && props.selectedLayer?.type === layerType
      && selectedParameter.value === parameter
    ) {
      parameterTeaching.value = result;
    }
  } catch (error) {
    if (requestId === parameterRequestId) parameterError.value = errorMessage(error);
  } finally {
    if (requestId === parameterRequestId) parameterLoading.value = false;
  }
}

async function explainCurrentModel() {
  const requestId = ++modelRequestId;
  modelLoading.value = true;
  modelError.value = "";
  try {
    const result = await fetchModelTeaching(props.modelGraph);
    if (requestId === modelRequestId) modelOverview.value = result;
  } catch (error) {
    if (requestId === modelRequestId) modelError.value = errorMessage(error);
  } finally {
    if (requestId === modelRequestId) modelLoading.value = false;
  }
}

watch(
  () => [props.open, props.selectedLayer?.id, props.selectedLayer?.type] as const,
  () => {
    selectedParameter.value = null;
    parameterTeaching.value = null;
    parameterError.value = "";
    parameterRequestId += 1;
    void loadLayerTeaching();
  },
  { immediate: true },
);
</script>

<template>
  <button
    v-if="available && !open"
    class="teaching-launch"
    type="button"
    title="打开教学辅助"
    @click="$emit('open')"
  >
    <iconify-icon icon="mdi:school-outline"></iconify-icon>
    <span>教学辅助</span>
  </button>

  <aside v-if="open" class="teaching-panel" aria-label="教学辅助面板">
    <header class="teaching-head">
      <div>
        <span class="teaching-kicker">M5 TEACHING</span>
        <h2>教学辅助</h2>
      </div>
      <button class="teaching-icon-button" type="button" title="关闭教学辅助" @click="$emit('close')">
        <iconify-icon icon="mdi:close"></iconify-icon>
      </button>
    </header>

    <nav class="teaching-tabs" aria-label="教学内容切换">
      <button :class="{ active: activeTab === 'layer' }" @click="activeTab = 'layer'">当前层</button>
      <button :class="{ active: activeTab === 'parameters' }" @click="activeTab = 'parameters'">参数说明</button>
      <button :class="{ active: activeTab === 'model' }" @click="activeTab = 'model'">模型概览</button>
    </nav>

    <div class="teaching-content">
      <section v-if="activeTab === 'layer'" class="teaching-section">
        <div v-if="!selectedLayer" class="teaching-empty">
          <iconify-icon icon="mdi:cursor-default-click-outline"></iconify-icon>
          <p>请先在画布中选择一个模型层。</p>
        </div>
        <div v-else-if="layerLoading" class="teaching-state">
          <iconify-icon class="spin" icon="mdi:loading"></iconify-icon> 正在加载当前层讲解
        </div>
        <div v-else-if="layerError" class="teaching-error">{{ layerError }}</div>
        <template v-else-if="layerTeaching">
          <div class="teaching-title-row">
            <span class="teaching-layer-icon"><iconify-icon icon="mdi:layers-outline"></iconify-icon></span>
            <div><h3>{{ layerTeaching.display_name }}</h3><code>{{ layerTeaching.layer_type }}</code></div>
          </div>
          <div v-if="!layerTeaching.known" class="teaching-notice">{{ layerTeaching.purpose }}</div>
          <dl class="teaching-facts">
            <div><dt>作用</dt><dd>{{ layerTeaching.purpose }}</dd></div>
            <div><dt>输入要求</dt><dd>{{ layerTeaching.input_requirement }}</dd></div>
            <div><dt>输出影响</dt><dd>{{ layerTeaching.output_effect }}</dd></div>
            <div><dt>常见位置</dt><dd>{{ layerTeaching.common_position }}</dd></div>
          </dl>
          <div class="teaching-tip"><iconify-icon icon="mdi:lightbulb-outline"></iconify-icon><span>{{ layerTeaching.beginner_tip }}</span></div>
          <div class="teaching-list-block">
            <h4>常见错误</h4>
            <ul><li v-for="item in layerTeaching.common_mistakes" :key="item">{{ item }}</li></ul>
          </div>
        </template>
      </section>

      <section v-else-if="activeTab === 'parameters'" class="teaching-section">
        <div v-if="!selectedLayer" class="teaching-empty">
          <iconify-icon icon="mdi:tune-variant"></iconify-icon><p>请先选择一个带参数的模型层。</p>
        </div>
        <template v-else>
          <div class="teaching-section-head">
            <div><span>当前节点</span><strong>{{ selectedLayer.title }}</strong></div>
            <code>{{ selectedLayer.type }}</code>
          </div>
          <div v-if="parameters.length" class="parameter-list">
            <button
              v-for="parameter in parameters"
              :key="parameter"
              :class="{ active: selectedParameter === parameter }"
              type="button"
              :title="`查看 ${parameter} 的详细说明`"
              @click="selectParameter(parameter)"
            >
              <span><code>{{ parameter }}</code><small>{{ displayValue(selectedLayer.params[parameter]) }}</small></span>
              <iconify-icon icon="mdi:information-outline"></iconify-icon>
            </button>
          </div>
          <div v-else class="teaching-empty compact"><p>当前层没有可讲解参数。</p></div>

          <div v-if="parameterLoading" class="teaching-state">
            <iconify-icon class="spin" icon="mdi:loading"></iconify-icon> 正在加载参数说明
          </div>
          <div v-else-if="parameterError" class="teaching-error">{{ parameterError }}</div>
          <div v-else-if="parameterTeaching" class="parameter-detail">
            <div class="teaching-title-row compact-title">
              <div><h3>{{ parameterTeaching.display_name }}</h3><code>{{ parameterTeaching.parameter }}</code></div>
              <span class="current-value">当前值 {{ displayValue(currentParameterValue) }}</span>
            </div>
            <div v-if="!parameterTeaching.known" class="teaching-notice">{{ parameterTeaching.explanation }}</div>
            <dl class="teaching-facts">
              <div><dt>含义</dt><dd>{{ parameterTeaching.explanation }}</dd></div>
              <div><dt>推荐设置</dt><dd>{{ parameterTeaching.recommendation }}</dd></div>
              <div><dt>调大影响</dt><dd>{{ parameterTeaching.increase_effect }}</dd></div>
              <div><dt>调小影响</dt><dd>{{ parameterTeaching.decrease_effect }}</dd></div>
              <div><dt>取值约束</dt><dd>{{ parameterTeaching.constraint }}</dd></div>
            </dl>
            <div class="teaching-list-block"><h4>常见错误</h4><ul><li v-for="item in parameterTeaching.common_mistakes" :key="item">{{ item }}</li></ul></div>
          </div>
          <div v-else-if="parameters.length" class="teaching-hint">点击参数右侧的信息图标查看详细说明。</div>
        </template>
      </section>

      <section v-else class="teaching-section">
        <button class="explain-model-button" type="button" :disabled="modelLoading" @click="explainCurrentModel">
          <iconify-icon :class="{ spin: modelLoading }" :icon="modelLoading ? 'mdi:loading' : 'mdi:book-open-page-variant-outline'"></iconify-icon>
          {{ modelLoading ? "正在讲解" : "讲解当前模型" }}
        </button>
        <div v-if="modelError" class="teaching-error">{{ modelError }}</div>
        <div v-else-if="!modelOverview" class="teaching-empty compact"><p>点击按钮后生成当前画布的教学概览。</p></div>
        <template v-else>
          <div class="model-summary">
            <span>{{ modelOverview.model_family }}</span><h3>{{ modelOverview.title }}</h3><p>{{ modelOverview.summary }}</p>
          </div>
          <div class="model-stats"><div><strong>{{ modelOverview.layer_count }}</strong><span>节点</span></div><div><strong>{{ modelOverview.connection_count }}</strong><span>连接</span></div></div>
          <div v-if="modelOverview.flow.length" class="teaching-list-block">
            <h4>主要数据流</h4>
            <div class="model-flow"><template v-for="(item, index) in modelOverview.flow" :key="item.layer_id"><span>{{ item.display_name || item.layer_type }}</span><iconify-icon v-if="index < modelOverview.flow.length - 1" icon="mdi:chevron-right"></iconify-icon></template></div>
          </div>
          <div v-if="modelOverview.key_layers.length" class="teaching-list-block">
            <h4>关键层</h4>
            <div class="key-layer-list">
              <div v-for="item in modelOverview.key_layers" :key="item.layer_id">
                <code>{{ item.layer_type }}</code><span>{{ item.role }}</span>
              </div>
            </div>
          </div>
          <div v-if="modelOverview.learning_points.length" class="teaching-list-block"><h4>学习重点</h4><ul><li v-for="item in modelOverview.learning_points" :key="item">{{ item }}</li></ul></div>
          <div v-if="modelOverview.beginner_warnings.length" class="teaching-list-block warning"><h4>初学者提醒</h4><ul><li v-for="item in modelOverview.beginner_warnings" :key="item">{{ item }}</li></ul></div>
        </template>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.teaching-launch { position: absolute; top: 18px; right: 18px; z-index: 55; height: 36px; padding: 0 13px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); box-shadow: var(--shadow-md); display: inline-flex; align-items: center; gap: 7px; font-weight: 700; cursor: pointer; }
.teaching-launch:hover { color: var(--indigo-strong); border-color: var(--indigo); }
.teaching-launch iconify-icon { font-size: 18px; color: var(--indigo); }
.teaching-panel { position: absolute; inset: 0 0 0 auto; z-index: 60; width: min(410px, 100%); background: var(--panel); border-left: 1px solid var(--border); box-shadow: -16px 0 36px -20px rgba(35, 48, 74, .32); display: flex; flex-direction: column; color: var(--text); }
.teaching-head { min-height: 66px; padding: 12px 14px 10px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.teaching-kicker { font-size: 10px; font-weight: 800; color: var(--indigo); letter-spacing: 0; }
.teaching-head h2 { margin: 2px 0 0; font-size: 18px; }
.teaching-icon-button { width: 34px; height: 34px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--muted); display: grid; place-items: center; cursor: pointer; }
.teaching-icon-button:hover { color: var(--text); border-color: var(--border-2); }
.teaching-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 1px solid var(--border); padding: 0 12px; }
.teaching-tabs button { min-width: 0; height: 42px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--muted); font-weight: 700; cursor: pointer; }
.teaching-tabs button.active { color: var(--indigo-strong); border-bottom-color: var(--indigo); }
.teaching-content { min-height: 0; flex: 1; overflow-y: auto; }
.teaching-section { padding: 18px; display: grid; gap: 14px; }
.teaching-empty { min-height: 240px; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--muted); text-align: center; }
.teaching-empty iconify-icon { font-size: 34px; color: var(--faint); }
.teaching-empty p { margin: 0; line-height: 1.6; }
.teaching-empty.compact { min-height: 100px; border: 1px dashed var(--border-2); border-radius: 8px; padding: 14px; }
.teaching-state, .teaching-error, .teaching-notice, .teaching-hint { border-radius: 8px; padding: 11px 12px; font-size: 13px; line-height: 1.55; }
.teaching-state { background: var(--panel-2); color: var(--muted); display: flex; align-items: center; gap: 8px; }
.teaching-error { background: #fff1f2; border: 1px solid #fecdd3; color: #be123c; }
.teaching-notice { background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; }
.teaching-hint { background: var(--panel-2); color: var(--muted); text-align: center; }
.teaching-title-row { display: flex; align-items: center; gap: 12px; }
.teaching-title-row h3, .model-summary h3 { margin: 0 0 4px; font-size: 16px; }
.teaching-title-row code, .teaching-section-head code { color: var(--indigo-strong); font-size: 12px; }
.teaching-layer-icon { width: 38px; height: 38px; border-radius: 8px; display: grid; place-items: center; background: rgba(99, 102, 241, .1); color: var(--indigo); font-size: 20px; }
.teaching-facts { margin: 0; display: grid; gap: 1px; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--border); }
.teaching-facts div { background: var(--panel); padding: 10px 11px; }
.teaching-facts dt { margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 800; }
.teaching-facts dd { margin: 0; font-size: 13px; line-height: 1.58; }
.teaching-tip { display: flex; align-items: flex-start; gap: 9px; border-left: 3px solid #f59e0b; background: #fffbeb; padding: 11px 12px; color: #854d0e; font-size: 13px; line-height: 1.55; }
.teaching-tip iconify-icon { flex: 0 0 auto; font-size: 18px; }
.teaching-list-block { display: grid; gap: 8px; }
.teaching-list-block h4 { margin: 0; font-size: 13px; }
.teaching-list-block ul { margin: 0; padding-left: 19px; display: grid; gap: 6px; color: var(--muted); font-size: 13px; line-height: 1.5; }
.teaching-list-block.warning { border: 1px solid #fde68a; background: #fffbeb; padding: 12px; border-radius: 8px; }
.teaching-section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.teaching-section-head div { display: grid; gap: 2px; }
.teaching-section-head span { color: var(--muted); font-size: 11px; }
.parameter-list { display: grid; gap: 6px; }
.parameter-list button { width: 100%; min-height: 48px; border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; background: var(--panel); color: var(--text); display: flex; align-items: center; justify-content: space-between; cursor: pointer; text-align: left; }
.parameter-list button:hover, .parameter-list button.active { border-color: var(--indigo); background: rgba(99, 102, 241, .05); }
.parameter-list button > span { min-width: 0; display: grid; gap: 3px; }
.parameter-list small { color: var(--muted); overflow-wrap: anywhere; }
.parameter-list iconify-icon { flex: 0 0 auto; font-size: 19px; color: var(--indigo); }
.parameter-detail { display: grid; gap: 13px; padding-top: 4px; border-top: 1px solid var(--border); }
.compact-title { justify-content: space-between; align-items: flex-start; }
.current-value { max-width: 150px; padding: 5px 8px; border-radius: 6px; background: var(--panel-2); color: var(--muted); font-size: 11px; overflow-wrap: anywhere; }
.explain-model-button { width: 100%; min-height: 40px; border: 0; border-radius: 8px; background: var(--indigo); color: white; display: flex; align-items: center; justify-content: center; gap: 8px; font-weight: 800; cursor: pointer; }
.explain-model-button:disabled { opacity: .65; cursor: wait; }
.model-summary { border-bottom: 1px solid var(--border); padding-bottom: 12px; }
.model-summary > span { color: var(--indigo); font-size: 11px; font-weight: 800; }
.model-summary p { margin: 7px 0 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
.model-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.model-stats div { border: 1px solid var(--border); border-radius: 8px; padding: 11px; display: grid; gap: 2px; }
.model-stats strong { font-size: 20px; }
.model-stats span { color: var(--muted); font-size: 11px; }
.model-flow { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: 12px; }
.model-flow span { padding: 5px 7px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); }
.model-flow iconify-icon { color: var(--faint); }
.key-layer-list { display: grid; gap: 6px; }
.key-layer-list div { display: grid; gap: 4px; padding: 9px 10px; border: 1px solid var(--border); border-radius: 8px; }
.key-layer-list code { color: var(--indigo-strong); font-size: 12px; }
.key-layer-list span { color: var(--muted); font-size: 12px; line-height: 1.5; }
@media (max-width: 720px) { .teaching-launch { top: 10px; right: 10px; } .teaching-panel { width: 100%; } }
</style>
