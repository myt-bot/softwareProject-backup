<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  fetchErrorTeaching,
  fetchLayerTeaching,
  fetchModelTeaching,
  fetchParameterTeaching,
  isBackendUnavailable,
} from "../api/client";
import { CONTAINER_ID_SEP } from "../store";
import type {
  ErrorTeachingSuggestion,
  GraphNode,
  LayerShapeInfo,
  LayerTeaching,
  ModelGraph,
  ModelGraphLayer,
  ModelTeachingOverview,
  ParameterTeaching,
  ValidationResult,
} from "../types";

const props = defineProps<{
  open: boolean;
  available: boolean;
  selectedLayer: GraphNode | null;
  modelGraph: ModelGraph;
  validationResult: ValidationResult | null;
  validationRequestError: string | null;
  validationInProgress: boolean;
}>();

const emit = defineEmits<{
  open: [];
  close: [];
  "locate-layer": [layerId: string];
}>();

type TeachingTab = "layer" | "parameters" | "model" | "guidance";

interface GuidanceTarget {
  layerId: string;
  layerType: string | null;
  originalError: string;
  parameter: string | null;
  currentValue: unknown;
  expectedValue: unknown;
  suggestedValue: unknown;
  isContainerInternal: boolean;
}

interface GuidanceValues {
  parameter: string | null;
  currentValue: unknown;
  expectedValue: unknown;
  suggestedValue: unknown;
}

interface GuidanceValueSummary extends GuidanceValues {
  hasValues: boolean;
  consistent: boolean;
}

interface GuidanceGroup {
  category: string;
  severity: string;
  title: string;
  reason: string;
  suggestions: string[];
  related_layers: string[];
  related_parameters: string[];
  targets: GuidanceTarget[];
  valueSamples: GuidanceValues[];
  valueSummary: GuidanceValueSummary;
}

interface ParsedLayerReference {
  layerId: string;
  layerType: string | null;
}

interface ResolvedLayerLocation {
  isContainerInternal: boolean;
}

const activeTab = ref<TeachingTab>("layer");

// tab 切换的左右滑动方向（仿首页页面切换）：目标在右→向左推(forward)，反之向右(back)
const TAB_ORDER: Record<TeachingTab, number> = { layer: 0, parameters: 1, model: 2, guidance: 3 };
const tabTransition = ref<"teach-forward" | "teach-back">("teach-forward");
watch(activeTab, (next, prev) => {
  tabTransition.value = TAB_ORDER[next] >= TAB_ORDER[prev] ? "teach-forward" : "teach-back";
});
const layerTeaching = ref<LayerTeaching | null>(null);
const selectedParameter = ref<string | null>(null);
const parameterTeaching = ref<ParameterTeaching | null>(null);
const modelOverview = ref<ModelTeachingOverview | null>(null);
const errorSuggestions = ref<GuidanceGroup[]>([]);
const currentTargetIndexes = ref<Record<string, number>>({});
const layerLoading = ref(false);
const parameterLoading = ref(false);
const modelLoading = ref(false);
const guidanceLoading = ref(false);
const layerError = ref("");
const parameterError = ref("");
const modelError = ref("");
const guidanceError = ref("");
const layerCache = new Map<string, LayerTeaching>();
const parameterCache = new Map<string, ParameterTeaching>();
let layerRequestId = 0;
let parameterRequestId = 0;
let modelRequestId = 0;
let guidanceRequestId = 0;
let loadedGuidanceResult: ValidationResult | null = null;
let observedGuidanceResult: ValidationResult | null | undefined;

const parameters = computed(() => Object.keys(props.selectedLayer?.params ?? {}));
const validationRequestMessage = computed(() => props.validationRequestError?.trim() ?? "");
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

function findModelLayer(layerId: string): ModelGraphLayer | null {
  const directLayer = props.modelGraph.layers.find(layer => layer.id === layerId);
  if (directLayer) return directLayer;
  if (!layerId.includes(CONTAINER_ID_SEP)) return null;

  const path = layerId.split(CONTAINER_ID_SEP);
  let currentLayer = props.modelGraph.layers.find(layer => layer.id === path[0]);
  for (const innerId of path.slice(1)) {
    currentLayer = currentLayer?.subgraph?.layers.find(layer => layer.id === innerId);
    if (!currentLayer) return null;
  }
  return currentLayer ?? null;
}

function resolveLayerLocation(layerId: string): ResolvedLayerLocation | null {
  if (props.modelGraph.layers.some(layer => layer.id === layerId)) {
    return { isContainerInternal: false };
  }
  if (!layerId.includes(CONTAINER_ID_SEP)) return null;

  const containerId = layerId.split(CONTAINER_ID_SEP)[0];
  const container = props.modelGraph.layers.find(
    layer => layer.id === containerId && layer.type === "Container",
  );
  if (!container || !findModelLayer(layerId)) return null;
  return { isContainerInternal: true };
}

function parseExplicitLayerReference(errorText: string): ParsedLayerReference | null {
  const colonMatch = errorText.match(/^层\s+([^\s():]+)(?:\(([^)]+)\))?\s*:/);
  if (colonMatch?.[1]) {
    return {
      layerId: colonMatch[1],
      layerType: colonMatch[2]?.trim() || null,
    };
  }

  const connectionMatch = errorText.match(
    /^层\s+([^\s():]+)\s+(?:没有输入连接|没有输出连接|不在任何 Input 出发的路径上|无法到达任何 Output)(?:[，。\s]|$)/,
  );
  if (connectionMatch?.[1]) {
    return { layerId: connectionMatch[1], layerType: null };
  }

  const isolatedMatch = errorText.match(/^存在孤立节点或连接异常:\s*([^\s,\[\]]+)\s*$/);
  if (isolatedMatch?.[1]) {
    return { layerId: isolatedMatch[1], layerType: null };
  }

  return null;
}

function buildErrorContext(
  errorMessage: string,
  result: ValidationResult,
): Record<string, unknown> {
  const shapes = result.shapes ?? {};
  const explicitReference = parseExplicitLayerReference(errorMessage);
  const exactShapeEntries = Object.entries(shapes).filter(
    ([, info]) => info.error === errorMessage,
  );

  let parsedReference: ParsedLayerReference | null = null;
  if (explicitReference) {
    if (!resolveLayerLocation(explicitReference.layerId)) return {};
    parsedReference = explicitReference;
  } else if (exactShapeEntries.length === 1) {
    const uniqueLayerId = exactShapeEntries[0]?.[0];
    if (!uniqueLayerId || !resolveLayerLocation(uniqueLayerId)) return {};
    parsedReference = { layerId: uniqueLayerId, layerType: null };
  } else {
    return {};
  }

  const layerId = parsedReference.layerId;
  const shapeInfo: LayerShapeInfo | undefined = shapes[layerId];
  const layerType = shapeInfo?.layer_type
    ?? parsedReference.layerType
    ?? findModelLayer(layerId)?.type
    ?? null;
  return {
    layer_id: layerId,
    layer_type: layerType,
    ...(shapeInfo ? { shape_info: shapeInfo } : {}),
  };
}

function validationPassed(result: ValidationResult): boolean {
  return result.valid === true || result.status === "ok";
}

function isNonEmptyText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function normalizedSuggestionCategory(suggestion: ErrorTeachingSuggestion): string {
  return isNonEmptyText(suggestion.category)
    ? suggestion.category.trim().toLowerCase()
    : "";
}

function isReliableSuggestion(suggestion: ErrorTeachingSuggestion): boolean {
  const category = normalizedSuggestionCategory(suggestion);
  return suggestion.matched === true
    && category.length > 0
    && category !== "unknown"
    && category !== "unknown_error"
    && isNonEmptyText(suggestion.title)
    && isNonEmptyText(suggestion.reason)
    && Array.isArray(suggestion.suggestions)
    && suggestion.suggestions.some(isNonEmptyText);
}

function normalizedSuggestionLayerId(
  suggestion: ErrorTeachingSuggestion,
): string | null {
  if (
    suggestion.can_locate !== true
    || typeof suggestion.layer_id !== "string"
  ) {
    return null;
  }

  const layerId = suggestion.layer_id.trim();
  if (!layerId || !resolveLayerLocation(layerId)) return null;
  return layerId;
}

function suppressContainedSuggestions(
  suggestions: ErrorTeachingSuggestion[],
): ErrorTeachingSuggestion[] {
  const reliableSuggestions = suggestions.filter(isReliableSuggestion);
  const isolatedLayerIds = new Set<string>();

  for (const suggestion of reliableSuggestions) {
    if (normalizedSuggestionCategory(suggestion) !== "isolated_node") continue;
    const layerId = normalizedSuggestionLayerId(suggestion);
    if (layerId) isolatedLayerIds.add(layerId);
  }

  return reliableSuggestions.filter(suggestion => {
    const category = normalizedSuggestionCategory(suggestion);
    if (
      category !== "missing_input_connection"
      && category !== "missing_output_connection"
    ) {
      return true;
    }

    const layerId = normalizedSuggestionLayerId(suggestion);
    return !layerId || !isolatedLayerIds.has(layerId);
  });
}

const GLOBAL_GUIDANCE_CATEGORIES = new Set([
  "missing_input",
  "missing_output",
  "cycle_detected",
]);

function suggestionValues(suggestion: ErrorTeachingSuggestion): GuidanceValues {
  return {
    parameter: typeof suggestion.parameter === "string" ? suggestion.parameter : null,
    currentValue: suggestion.current_value,
    expectedValue: suggestion.expected_value,
    suggestedValue: suggestion.suggested_value,
  };
}

function hasConcreteGuidanceValue(values: GuidanceValues): boolean {
  return values.currentValue != null
    || values.expectedValue != null
    || values.suggestedValue != null;
}

function valuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  try {
    return JSON.stringify(left) === JSON.stringify(right);
  } catch {
    return false;
  }
}

function guidanceValuesEqual(left: GuidanceValues, right: GuidanceValues): boolean {
  return left.parameter === right.parameter
    && valuesEqual(left.currentValue, right.currentValue)
    && valuesEqual(left.expectedValue, right.expectedValue)
    && valuesEqual(left.suggestedValue, right.suggestedValue);
}

function summarizeGuidanceValues(group: GuidanceGroup): GuidanceValueSummary {
  const samples: GuidanceValues[] = group.targets.length
    ? group.targets
    : group.valueSamples;
  const first = samples[0] ?? {
    parameter: null,
    currentValue: null,
    expectedValue: null,
    suggestedValue: null,
  };
  return {
    ...first,
    hasValues: samples.some(hasConcreteGuidanceValue),
    consistent: samples.every(sample => guidanceValuesEqual(first, sample)),
  };
}

function buildGuidanceGroups(suggestions: ErrorTeachingSuggestion[]): GuidanceGroup[] {
  const groups = new Map<string, GuidanceGroup>();

  for (const suggestion of suggestions) {
    if (!isReliableSuggestion(suggestion)) continue;

    const category = normalizedSuggestionCategory(suggestion);
    let group = groups.get(category);
    if (!group) {
      group = {
        category,
        severity: suggestion.severity,
        title: suggestion.title.trim(),
        reason: suggestion.reason.trim(),
        suggestions: suggestion.suggestions.filter(isNonEmptyText).map(item => item.trim()),
        related_layers: Array.isArray(suggestion.related_layers)
          ? suggestion.related_layers.filter(isNonEmptyText)
          : [],
        related_parameters: Array.isArray(suggestion.related_parameters)
          ? suggestion.related_parameters.filter(isNonEmptyText)
          : [],
        targets: [],
        valueSamples: [],
        valueSummary: {
          parameter: null,
          currentValue: null,
          expectedValue: null,
          suggestedValue: null,
          hasValues: false,
          consistent: true,
        },
      };
      groups.set(category, group);
    }

    const values = suggestionValues(suggestion);
    group.valueSamples.push(values);

    const layerId = typeof suggestion.layer_id === "string"
      ? suggestion.layer_id.trim()
      : "";
    const resolvedLocation = layerId ? resolveLayerLocation(layerId) : null;
    if (
      suggestion.can_locate === true
      && layerId
      && resolvedLocation
      && !GLOBAL_GUIDANCE_CATEGORIES.has(category)
      && !group.targets.some(target => target.layerId === layerId)
    ) {
      group.targets.push({
        layerId,
        layerType: typeof suggestion.layer_type === "string"
          ? suggestion.layer_type
          : null,
        originalError: typeof suggestion.original_error === "string"
          ? suggestion.original_error
          : String(suggestion.original_error ?? ""),
        ...values,
        isContainerInternal: resolvedLocation.isContainerInternal,
      });
    }
  }

  const result = [...groups.values()];
  for (const group of result) {
    group.valueSummary = summarizeGuidanceValues(group);
  }
  return result;
}

function currentTargetIndex(group: GuidanceGroup): number {
  const index = currentTargetIndexes.value[group.category] ?? 0;
  return index >= 0 && index < group.targets.length ? index : 0;
}

function currentTarget(group: GuidanceGroup): GuidanceTarget | null {
  return group.targets[currentTargetIndex(group)] ?? null;
}

function currentTargetLabel(group: GuidanceGroup): string {
  const target = currentTarget(group);
  if (!target) return "";
  const modelLayer = findModelLayer(target.layerId);
  return modelLayer?.name?.trim() || target.layerType || target.layerId;
}

function selectPreviousTarget(group: GuidanceGroup) {
  const index = currentTargetIndex(group);
  if (index > 0) currentTargetIndexes.value[group.category] = index - 1;
}

function selectNextTarget(group: GuidanceGroup) {
  const index = currentTargetIndex(group);
  if (index < group.targets.length - 1) {
    currentTargetIndexes.value[group.category] = index + 1;
  }
}

function locateCurrentTarget(group: GuidanceGroup) {
  const target = currentTarget(group);
  if (target) emit("locate-layer", target.layerId);
}

function clearGuidanceState() {
  guidanceRequestId += 1;
  loadedGuidanceResult = null;
  errorSuggestions.value = [];
  currentTargetIndexes.value = {};
  guidanceError.value = "";
  guidanceLoading.value = false;
}

async function loadErrorGuidance() {
  const validationResult = props.validationResult;
  if (!props.open) return;
  if (
    props.validationInProgress
    || (!validationResult && validationRequestMessage.value)
  ) {
    clearGuidanceState();
    return;
  }
  if (!validationResult || validationPassed(validationResult)) {
    clearGuidanceState();
    return;
  }
  if (loadedGuidanceResult === validationResult) {
    guidanceLoading.value = false;
    return;
  }

  const errors = validationResult.errors ?? [];
  if (!errors.length) {
    loadedGuidanceResult = validationResult;
    guidanceLoading.value = false;
    return;
  }

  const requestId = ++guidanceRequestId;
  guidanceError.value = "";
  guidanceLoading.value = true;
  try {
    const settledSuggestions = await Promise.allSettled(
      errors.map(errorMessage => fetchErrorTeaching(
        errorMessage,
        buildErrorContext(errorMessage, validationResult),
      )),
    );
    const suggestions = settledSuggestions.flatMap(result =>
      result.status === "fulfilled" ? [result.value] : []
    );
    const hasFulfilledSuggestion = settledSuggestions.some(
      result => result.status === "fulfilled",
    );
    if (
      requestId === guidanceRequestId
      && props.open
      && props.validationResult === validationResult
    ) {
      errorSuggestions.value = buildGuidanceGroups(
        suppressContainedSuggestions(suggestions),
      );
      loadedGuidanceResult = hasFulfilledSuggestion ? validationResult : null;
    }
  } catch (error) {
    if (
      requestId === guidanceRequestId
      && props.open
      && props.validationResult === validationResult
    ) {
      guidanceError.value = errorMessage(error);
    }
  } finally {
    if (requestId === guidanceRequestId) guidanceLoading.value = false;
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

watch(
  () => [
    props.open,
    props.validationResult,
    props.validationInProgress,
    props.validationRequestError,
  ] as const,
  ([open, validationResult, validationInProgress, validationRequestError]) => {
    const resultChanged = observedGuidanceResult !== validationResult;
    observedGuidanceResult = validationResult;
    const hasRequestError = !validationResult && isNonEmptyText(validationRequestError);

    if (resultChanged || validationInProgress || hasRequestError) {
      clearGuidanceState();
    }
    if (!open) {
      guidanceRequestId += 1;
      guidanceLoading.value = false;
      return;
    }
    if (validationInProgress || hasRequestError) return;
    void loadErrorGuidance();
  },
  { immediate: true },
);
</script>

<template>
  <!-- 启动入口已并入顶栏「帮助」菜单；此处仅渲染展开后的面板 -->
  <Transition name="teaching-slide">
  <aside v-if="open" class="teaching-panel" aria-label="教学辅助面板">
    <header class="teaching-head">
      <span class="teaching-head-icon"><iconify-icon icon="mdi:school-outline"></iconify-icon></span>
      <div class="teaching-head-copy">
        <h2>教学辅助</h2>
        <span>逐层讲解 · 参数说明 · 修改指导</span>
      </div>
      <button class="teaching-icon-button" type="button" title="关闭教学辅助" @click="$emit('close')">
        <iconify-icon icon="mdi:close"></iconify-icon>
      </button>
    </header>

    <nav class="teaching-tabs" aria-label="教学内容切换">
      <button :class="{ active: activeTab === 'layer' }" @click="activeTab = 'layer'">当前层</button>
      <button :class="{ active: activeTab === 'parameters' }" @click="activeTab = 'parameters'">参数说明</button>
      <button :class="{ active: activeTab === 'model' }" @click="activeTab = 'model'">模型概览</button>
      <button :class="{ active: activeTab === 'guidance' }" @click="activeTab = 'guidance'">修改指导</button>
      <span class="teaching-tab-underline" :style="{ transform: `translateX(${TAB_ORDER[activeTab] * 100}%)` }"></span>
    </nav>

    <div class="teaching-content">
      <Transition :name="tabTransition">
      <div class="teaching-pane" :key="activeTab">
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

      <section v-else-if="activeTab === 'model'" class="teaching-section">
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

      <section v-else class="teaching-section guidance-section">
        <div v-if="validationInProgress" class="teaching-state">
          <iconify-icon class="spin" icon="mdi:loading"></iconify-icon>
          正在检查模型结构，请稍候。
        </div>
        <div
          v-else-if="!validationResult && validationRequestMessage"
          class="teaching-error guidance-request-error"
        >
          <strong>结构检查请求未完成</strong>
          <span>{{ validationRequestMessage }}</span>
          <small>请根据页面提示处理后重新点击“检查结构”。</small>
        </div>
        <div v-else-if="!validationResult" class="teaching-empty">
          <iconify-icon icon="mdi:clipboard-search-outline"></iconify-icon>
          <p>暂无可用的结构检查结果，请点击“检查结构”。</p>
        </div>
        <div v-else-if="validationPassed(validationResult)" class="guidance-success">
          <iconify-icon icon="mdi:check-circle-outline"></iconify-icon>
          <div><strong>模型结构检查通过</strong><span>目前没有需要修改的问题。</span></div>
        </div>
        <div v-else-if="!(validationResult.errors?.length)" class="teaching-notice">
          结构检查未通过，但校验器没有返回可解释的错误信息。
        </div>
        <div v-else-if="guidanceLoading" class="teaching-state">
          <iconify-icon class="spin" icon="mdi:loading"></iconify-icon> 正在生成修改指导
        </div>
        <div v-else-if="guidanceError" class="teaching-error">{{ guidanceError }}</div>
        <div v-else-if="!errorSuggestions.length" class="teaching-notice">
          当前检查结果中没有能够确定原因的修改指导，请根据画布中的错误提示检查连接和参数。
        </div>
        <div v-else class="guidance-list">
          <article v-for="(suggestion, index) in errorSuggestions" :key="suggestion.category" class="guidance-card">
            <header>
              <span class="guidance-index">{{ index + 1 }}</span>
              <div>
                <h3>{{ suggestion.title }}</h3>
                <small v-if="suggestion.targets.length > 1">发现 {{ suggestion.targets.length }} 处</small>
              </div>
            </header>
            <p class="guidance-reason">{{ suggestion.reason }}</p>
            <div class="teaching-list-block">
              <h4>修改步骤</h4>
              <ol><li v-for="item in suggestion.suggestions" :key="item">{{ item }}</li></ol>
            </div>
            <dl class="guidance-meta">
              <div v-if="suggestion.related_layers.length"><dt>相关层</dt><dd>{{ suggestion.related_layers.join("、") }}</dd></div>
              <div v-if="suggestion.related_parameters.length"><dt>相关参数</dt><dd>{{ suggestion.related_parameters.join("、") }}</dd></div>
              <div v-if="suggestion.valueSummary.consistent && suggestion.valueSummary.currentValue != null"><dt>当前值</dt><dd>{{ displayValue(suggestion.valueSummary.currentValue) }}</dd></div>
              <div v-if="suggestion.valueSummary.consistent && suggestion.valueSummary.expectedValue != null"><dt>期望值</dt><dd>{{ displayValue(suggestion.valueSummary.expectedValue) }}</dd></div>
              <div v-if="suggestion.valueSummary.consistent && suggestion.valueSummary.suggestedValue != null"><dt>建议值</dt><dd>{{ displayValue(suggestion.valueSummary.suggestedValue) }}</dd></div>
            </dl>
            <div
              v-if="suggestion.targets.length > 1 && suggestion.valueSummary.hasValues && !suggestion.valueSummary.consistent"
              class="teaching-notice guidance-value-warning"
            >
              不同位置的具体参数值可能不同，请逐个定位检查。
            </div>
            <div v-if="suggestion.targets.length > 0" class="guidance-target-block">
              <div v-if="suggestion.targets.length > 1" class="guidance-target-position">
                位置 {{ currentTargetIndex(suggestion) + 1 }} / {{ suggestion.targets.length }}：{{ currentTargetLabel(suggestion) }}
              </div>
              <div v-if="currentTarget(suggestion)?.isContainerInternal" class="guidance-container-hint">
                问题位于该容器内部，定位后请打开容器继续检查。
              </div>
              <div v-if="suggestion.targets.length > 1" class="guidance-target-actions">
                <button
                  class="guidance-target-step"
                  type="button"
                  title="上一处问题位置"
                  :disabled="currentTargetIndex(suggestion) === 0"
                  @click="selectPreviousTarget(suggestion)"
                >
                  <iconify-icon icon="mdi:chevron-left"></iconify-icon>
                  上一处
                </button>
                <button class="locate-layer-button" type="button" @click="locateCurrentTarget(suggestion)">
                  <iconify-icon icon="mdi:crosshairs-gps"></iconify-icon>
                  定位当前节点
                </button>
                <button
                  class="guidance-target-step"
                  type="button"
                  title="下一处问题位置"
                  :disabled="currentTargetIndex(suggestion) === suggestion.targets.length - 1"
                  @click="selectNextTarget(suggestion)"
                >
                  下一处
                  <iconify-icon icon="mdi:chevron-right"></iconify-icon>
                </button>
              </div>
              <button v-else class="locate-layer-button" type="button" @click="locateCurrentTarget(suggestion)">
                <iconify-icon icon="mdi:crosshairs-gps"></iconify-icon>
                定位问题节点
              </button>
            </div>
          </article>
        </div>
      </section>
      </div>
      </Transition>
    </div>
  </aside>
  </Transition>
</template>

<style scoped>
.teaching-launch {
  position: absolute;
  right: 18px;
  bottom: 18px;
  z-index: 55;
  height: 40px;
  padding: 0 15px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  color: var(--text);
  box-shadow: var(--shadow-md);
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-weight: 700;
  cursor: pointer;
}
.teaching-launch:hover { color: var(--indigo-strong); border-color: var(--indigo); }
.teaching-launch iconify-icon { font-size: 18px; color: var(--indigo); }
.teaching-panel { position: absolute; inset: 0 0 0 auto; z-index: 60; width: min(410px, 100%); background: var(--panel); border-left: 1px solid var(--border); box-shadow: -16px 0 36px -20px rgba(35, 48, 74, .32); display: flex; flex-direction: column; color: var(--text); }
/* 面板滑入 / 滑出（右侧） */
.teaching-slide-enter-active, .teaching-slide-leave-active { transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.28s ease; }
.teaching-slide-enter-from, .teaching-slide-leave-to { transform: translateX(100%); opacity: 0.5; }
.teaching-head { min-height: 64px; padding: 12px 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 12px; background: linear-gradient(180deg, var(--panel-2), var(--panel)); }
.teaching-head-icon { flex: 0 0 auto; width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-size: 22px; color: var(--indigo); background: rgba(99, 102, 241, .1); }
.teaching-head-copy { flex: 1; min-width: 0; }
.teaching-head-copy h2 { margin: 0; font-size: 17px; font-weight: 800; }
.teaching-head-copy span { display: block; margin-top: 2px; font-size: 11.5px; color: var(--muted); }
.teaching-icon-button { width: 34px; height: 34px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--muted); display: grid; place-items: center; cursor: pointer; }
.teaching-icon-button:hover { color: var(--text); border-color: var(--border-2); }
.teaching-tabs { position: relative; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: 1px solid var(--border); padding: 0; }
.teaching-tabs button { min-width: 0; height: 42px; border: 0; background: transparent; color: var(--muted); font-weight: 700; cursor: pointer; transition: color 0.15s ease; }
.teaching-tabs button:hover { color: var(--text); }
.teaching-tabs button.active { color: var(--indigo-strong); }
/* 滑动下划线：随激活 tab 平移（仿首页导航） */
.teaching-tab-underline { position: absolute; left: 0; bottom: -1px; width: 25%; height: 2px; border-radius: 2px; background: var(--indigo); transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1); }
.teaching-content { position: relative; min-height: 0; flex: 1; overflow-y: auto; overflow-x: hidden; }
.teaching-pane { width: 100%; }
/* tab 内容左右滑动过渡（方向由 tabTransition 决定） */
.teach-forward-enter-active, .teach-forward-leave-active, .teach-back-enter-active, .teach-back-leave-active { transition: transform 0.26s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.22s ease; }
.teach-forward-leave-active, .teach-back-leave-active { position: absolute; top: 0; left: 0; width: 100%; }
.teach-forward-enter-from { opacity: 0; transform: translateX(42px); }
.teach-forward-leave-to { opacity: 0; transform: translateX(-42px); }
.teach-back-enter-from { opacity: 0; transform: translateX(-42px); }
.teach-back-leave-to { opacity: 0; transform: translateX(42px); }
.teaching-section { padding: 18px; display: grid; gap: 14px; }
.teaching-empty { min-height: 240px; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--muted); text-align: center; }
.teaching-empty iconify-icon { font-size: 34px; color: var(--faint); }
.teaching-empty p { margin: 0; line-height: 1.6; }
.teaching-empty.compact { min-height: 100px; border: 1px dashed var(--border-2); border-radius: 8px; padding: 14px; }
.teaching-state, .teaching-error, .teaching-notice, .teaching-hint { border-radius: 8px; padding: 11px 12px; font-size: 13px; line-height: 1.55; }
.teaching-state { background: var(--panel-2); color: var(--muted); display: flex; align-items: center; gap: 8px; }
.teaching-error { background: #fff1f2; border: 1px solid #fecdd3; color: #be123c; }
.guidance-request-error { display: grid; gap: 5px; }
.guidance-request-error strong { font-size: 14px; }
.guidance-request-error span, .guidance-request-error small { overflow-wrap: anywhere; }
.guidance-request-error small { color: #9f1239; }
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
.teaching-list-block ol { margin: 0; padding-left: 21px; display: grid; gap: 7px; color: var(--muted); font-size: 13px; line-height: 1.55; }
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
.guidance-section { align-content: start; }
.guidance-success { display: flex; align-items: center; gap: 12px; padding: 14px; border: 1px solid #a7f3d0; border-radius: 8px; background: #ecfdf5; color: #047857; }
.guidance-success iconify-icon { flex: 0 0 auto; font-size: 26px; }
.guidance-success div { display: grid; gap: 3px; }
.guidance-success span { font-size: 12px; }
.guidance-list { display: grid; gap: 12px; }
.guidance-card { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); }
.guidance-card header { display: flex; align-items: flex-start; gap: 10px; }
.guidance-card header h3 { margin: 0 0 3px; font-size: 14px; line-height: 1.4; }
.guidance-card header code { color: var(--muted); font-size: 10px; }
.guidance-index { flex: 0 0 auto; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%; background: #fee2e2; color: #b91c1c; font-size: 11px; font-weight: 800; }
.guidance-reason { margin: 0; padding: 10px; border-left: 3px solid #fb7185; background: #fff1f2; color: #881337; font-size: 13px; line-height: 1.55; }
.guidance-meta { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.guidance-meta div { min-width: 0; padding: 8px; border-radius: 7px; background: var(--panel-2); }
.guidance-meta dt { color: var(--faint); font-size: 10px; font-weight: 800; }
.guidance-meta dd { margin: 3px 0 0; color: var(--text); font-size: 12px; overflow-wrap: anywhere; }
.guidance-value-warning { margin: 0; }
.guidance-target-block { display: grid; gap: 8px; }
.guidance-target-position { color: var(--text); font-size: 12px; font-weight: 800; overflow-wrap: anywhere; }
.guidance-container-hint { padding: 8px 10px; border-left: 3px solid #f59e0b; background: #fff7ed; color: #9a3412; font-size: 12px; line-height: 1.5; }
.guidance-target-actions { display: grid; grid-template-columns: minmax(0, 1fr) minmax(116px, 1.35fr) minmax(0, 1fr); gap: 6px; }
.guidance-target-step { min-height: 36px; padding: 0 7px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); display: flex; align-items: center; justify-content: center; gap: 2px; font-size: 12px; font-weight: 800; cursor: pointer; }
.guidance-target-step:hover:not(:disabled) { border-color: var(--indigo); color: var(--indigo-strong); }
.guidance-target-step:disabled { opacity: .45; cursor: not-allowed; }
.locate-layer-button { min-height: 36px; border: 1px solid var(--indigo); border-radius: 8px; background: rgba(99, 102, 241, .07); color: var(--indigo-strong); display: flex; align-items: center; justify-content: center; gap: 7px; font-weight: 800; cursor: pointer; }
.locate-layer-button:hover { background: rgba(99, 102, 241, .13); }
@media (max-width: 720px) {
  .teaching-launch {
    right: 10px;
    bottom: 10px;
  }

  .teaching-panel {
    width: 100%;
  }
}
</style>
