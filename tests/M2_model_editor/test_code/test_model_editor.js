"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

/**
 * M2 前端模型搭建编辑器自动化测试
 *
 * 本文件直接检查项目中的真实前端实现，不再在测试文件里复制一套假的编辑器逻辑。
 * Vue 组件交互由源码契约测试覆盖；可以脱离浏览器验证的几何规则在本文件中做边界测试。
 *
 * 运行方式（项目根目录）：
 *   node tests/M2_model_editor/test_code/test_model_editor.js
 */

const PROJECT_ROOT = path.resolve(__dirname, "../../..");

function readProjectFile(relativePath) {
  const absolutePath = path.join(PROJECT_ROOT, relativePath);
  assert.equal(fs.existsSync(absolutePath), true, `缺少被测文件：${relativePath}`);
  return fs.readFileSync(absolutePath, "utf8");
}

const source = {
  app: readProjectFile("frontend/src/App.vue"),
  actions: readProjectFile("frontend/src/actions.ts"),
  canvas: readProjectFile("frontend/src/canvas.ts"),
  store: readProjectFile("frontend/src/store.ts"),
  canvasBoard: readProjectFile("frontend/src/components/CanvasBoard.vue"),
  canvasTabs: readProjectFile("frontend/src/components/CanvasTabs.vue"),
  contextMenus: readProjectFile("frontend/src/components/ContextMenus.vue"),
  layerSidebar: readProjectFile("frontend/src/components/LayerSidebar.vue"),
  paramField: readProjectFile("frontend/src/components/ParamNumberField.vue"),
  validationSummary: readProjectFile("frontend/src/components/ValidationSummary.vue"),
  styles: readProjectFile("frontend/src/styles.css"),
};

function indexOrFail(text, fragment, description) {
  const index = text.indexOf(fragment);
  assert.notEqual(index, -1, `未找到：${description}`);
  return index;
}

function buttonBlock(componentSource, id) {
  const idIndex = indexOrFail(componentSource, `id="${id}"`, `按钮 #${id}`);
  const start = componentSource.lastIndexOf("<button", idIndex);
  const end = componentSource.indexOf("</button>", idIndex);
  assert.ok(start >= 0 && end > idIndex, `无法提取按钮 #${id}`);
  return componentSource.slice(start, end + "</button>".length);
}

function limitedTopEntryDirection(dx, dy, maxHorizontalRatio = 0.625) {
  let limitedDx = dx;
  if (Math.abs(dy) > 0.001) {
    limitedDx = Math.sign(dx) * Math.min(Math.abs(dx), Math.abs(dy) * maxHorizontalRatio);
  }
  return { dx: limitedDx, dy };
}

function deviationFromVerticalDegrees(dx, dy) {
  return Math.atan2(Math.abs(dx), Math.abs(dy)) * 180 / Math.PI;
}

test("M2-001：所有模型编辑器核心文件存在", () => {
  Object.entries(source).forEach(([name, content]) => {
    assert.ok(content.length > 0, `${name} 不应为空`);
  });
});

test("M2-002：组件库支持单击和键盘添加节点", () => {
  assert.match(source.layerSidebar, /@click="handleLayerClick\(layer\.type\)"/);
  assert.match(source.layerSidebar, /@keydown\.enter\.prevent="handleLayerClick\(layer\.type\)"/);
  assert.match(source.layerSidebar, /@keydown\.space\.prevent="handleLayerClick\(layer\.type\)"/);
  assert.match(source.canvas, /export function addLayerByClick\(layerType: string\)/);
  assert.match(source.canvas, /function suggestedClickAddPosition\(\): Point/);
});

test("M2-003：新增节点不会自动打开可能遮挡画布的参数面板", () => {
  assert.match(source.canvas, /selectNode\(node\.id, \{ openInspector: false \}\)/);
  assert.match(source.canvas, /ui\.inspectorCollapsed = options\.openInspector === false/);
});

test("M2-004：选中节点显示复制和删除悬浮工具条", () => {
  assert.match(source.canvasBoard, /class="node-quick-toolbar"/);
  assert.match(source.canvasBoard, /@click="copyNodeFromToolbar\(node\.id\)"/);
  assert.match(source.canvasBoard, /@click="deleteNodeFromToolbar\(node\.id\)"/);
});

test("M2-005：右键菜单提供复制节点和删除节点", () => {
  assert.match(source.contextMenus, /id="btn-copy-node"/);
  assert.match(source.contextMenus, /@click="copyMenuNode"/);
  assert.match(source.contextMenus, /id="btn-delete-node"/);
  assert.match(source.contextMenus, /@click="deleteMenuNode"/);
});

test("M2-006：Ctrl+C、Ctrl+V、Delete 和 Backspace 快捷键已接入真实操作", () => {
  assert.match(source.app, /event\.key === "Delete" \|\| event\.key === "Backspace"/);
  assert.match(source.app, /deleteSelectedGraphItem\(\)/);
  assert.match(source.app, /key === "c"/);
  assert.match(source.app, /copySelectedNode\(\)/);
  assert.match(source.app, /key === "v"/);
  assert.match(source.app, /pasteCopiedNode\(\)/);
});

test("M2-007：输入框编辑时不会误触画布快捷键", () => {
  assert.match(source.app, /target\.tagName === "INPUT"/);
  assert.match(source.app, /target\.tagName === "TEXTAREA"/);
  assert.match(source.app, /target\.isContentEditable/);
});

test("M2-008：复制节点使用深拷贝，并为粘贴副本生成新 id 和偏移位置", () => {
  assert.match(source.canvas, /function cloneGraphNode\(node: GraphNode\)/);
  assert.match(source.canvas, /JSON\.parse\(JSON\.stringify\(node\)\)/);
  assert.match(source.canvas, /node\.id = nextCopiedNodeId\(node\.type\)/);
  assert.match(source.canvas, /node\.x = copiedNode\.x \+ 36 \* pasteOffsetStep/);
  assert.match(source.canvas, /node\.y = copiedNode\.y \+ 36 \* pasteOffsetStep/);
});

test("M2-009：删除节点时同步清除普通连接和容器端口连接", () => {
  assert.match(source.canvas, /export function deleteNodeById\(nodeId: string\)/);
  assert.match(source.canvas, /endpointBaseId\(source\) !== nodeId/);
  assert.match(source.canvas, /endpointBaseId\(target\) !== nodeId/);
  assert.match(source.canvas, /removeEdgeControlsForNode\(nodeId\)/);
});

test("M2-010：删除选中项同时支持节点和连线", () => {
  assert.match(source.canvas, /export function deleteSelectedGraphItem\(\): boolean/);
  assert.match(source.canvas, /deleteNodeById\(canvas\.selectedNodeId\)/);
  assert.match(source.canvas, /deleteConnectionByKey\(canvas\.selectedConnectionKey\)/);
});

test("M2-011：撤销和重做记录节点、连线、控制点及计数器", () => {
  assert.match(source.canvas, /interface GraphSnapshot/);
  assert.match(source.canvas, /nodes: GraphNode\[\]/);
  assert.match(source.canvas, /connections: Connection\[\]/);
  assert.match(source.canvas, /edgeControls: Record<string, Point>/);
  assert.match(source.canvas, /nodeCounters: Record<string, number>/);
  assert.match(source.canvas, /export function undoGraphChange\(\)/);
  assert.match(source.canvas, /export function redoGraphChange\(\)/);
});

test("M2-012：撤销、重做、智能布局和适应视图固定在模板按钮前", () => {
  const toolsIndex = indexOrFail(source.canvasTabs, "class=\"tab-canvas-tools\"", "标签栏工具组");
  const templateIndex = indexOrFail(source.canvasTabs, "id=\"btn-template-gallery\"", "快速开始模板按钮");
  assert.ok(toolsIndex < templateIndex, "画布工具组应位于快速开始模板按钮之前");
  assert.match(source.canvasTabs, /@click="undoGraphChange"/);
  assert.match(source.canvasTabs, /@click="redoGraphChange"/);
  assert.match(source.canvasTabs, /@click="autoLayoutGraph"/);
  assert.match(source.canvasTabs, /@click="centerGraphInCanvas"/);
  assert.match(source.styles, /\.canvas-tab-list\s*\{[\s\S]*?overflow-x: auto/);
});

test("M2-013：撤销和重做按钮仅显示图标", () => {
  const undo = buttonBlock(source.canvasTabs, "btn-undo");
  const redo = buttonBlock(source.canvasTabs, "btn-redo");
  assert.match(undo, /mdi:undo-variant/);
  assert.match(redo, /mdi:redo-variant/);
  assert.doesNotMatch(undo, /<span>撤销<\/span>/);
  assert.doesNotMatch(redo, /<span>重做<\/span>/);
  assert.match(undo, /aria-label="撤销上一步"/);
  assert.match(redo, /aria-label="重做"/);
});

test("M2-014：三个及以下节点采用单列竖向布局", () => {
  assert.match(source.canvas, /nodes\.length <= 3/);
  assert.match(source.canvas, /\? layers\.length/);
  assert.match(source.canvas, /mode: SmartLayoutMode/);
});

test("M2-015：复杂图按拓扑层排列、分支展开并在高度不足时折列", () => {
  assert.match(source.canvas, /const preds: Record<string, string\[]>/);
  assert.match(source.canvas, /const succ: Record<string, string\[]>/);
  assert.match(source.canvas, /const layers: string\[\]\[\]/);
  assert.match(source.canvas, /const columns: string\[\]\[\]\[\]/);
  assert.match(source.canvas, /const barycenter =/);
  assert.match(source.canvas, /columnLeft \+= columnWidth \+ COLUMN_GAP/);
});

test("M2-016：模板加载统一调用智能布局且不覆盖用户手动拖动", () => {
  assert.match(source.canvas, /export function applyTemplateGraph\(modelGraph: ModelGraph\)/);
  assert.match(source.canvas, /layoutGraphNodes\(activeCanvas\(\)\)/);
  assert.match(source.canvas, /export function autoLayoutGraph\(\)/);
  assert.doesNotMatch(source.canvas, /handleDocumentMouseMove[\s\S]{0,1000}layoutGraphNodes/);
});

test("M2-017：结构检查将连接类派生错误合并为一条完整通路问题", () => {
  assert.match(source.actions, /function isConnectivityError\(error: string\)/);
  assert.match(source.actions, /const connectionErrors = rawIssues\.filter/);
  assert.match(source.actions, /id: "connectivity"/);
  assert.match(source.actions, /Input 到 Output 未形成完整通路/);
  assert.match(source.actions, /建议补齐断开的连线/);
});

test("M2-018：结构检查去除同节点同参数的重复问题和下游级联错误", () => {
  assert.match(source.actions, /const seen = new Set<string>\(\)/);
  assert.match(source.actions, /const isCascadingShapeError =/);
  assert.match(source.actions, /if \(isCascadingShapeError\) return/);
  assert.match(source.actions, /if \(seen\.has\(key\)\) return/);
});

test("M2-019：错误列表显示修改建议，并可定位节点和对应参数", () => {
  assert.match(source.validationSummary, /issue\.suggestion/);
  assert.match(source.validationSummary, /focusNodeInCanvas\(issue\.nodeId, issue\.parameter\)/);
  assert.match(source.canvas, /ui\.inspectorFocusParam = parameter/);
  assert.match(source.canvas, /ui\.inspectorCollapsed = options\.openInspector === false/);
  assert.doesNotMatch(source.canvasBoard, /node-error-msg/);
});

test("M2-020：数字参数只在 change 确认后提交，非法值保留在本地错误状态", () => {
  assert.match(source.paramField, /@change="handleChange"/);
  assert.match(source.paramField, /if \(rawValue === ""\)/);
  assert.match(source.paramField, /Number\.isFinite\(value\)/);
  assert.match(source.paramField, /Number\.isInteger\(value\)/);
  assert.match(source.paramField, /value < props\.min/);
  assert.match(source.paramField, /value > props\.max/);
  assert.match(source.paramField, /emit\("change", value\)/);
});

test("M2-021：ModelGraph 导出包含层、连接和训练配置", () => {
  assert.match(source.store, /export function getCurrentModelGraph/);
  assert.match(source.store, /layers: serialized\.layers/);
  assert.match(source.store, /connections: serialized\.connections/);
  assert.match(source.store, /train_config: getTrainConfig\(canvas\)/);
});

test("M2-022：多输入节点使用独立顶部落点，但不再渲染入口圆点", () => {
  assert.match(source.canvas, /function getMultiInputPoint/);
  assert.match(source.canvas, /\(sourceIndex \+ 1\) \/ \(incoming\.length \+ 1\)/);
  assert.doesNotMatch(source.canvasBoard, /multi-input-port/);
  assert.doesNotMatch(source.styles, /\.multi-input-port/);
});

test("M2-023：连线箭头使用终点切线自动旋转", () => {
  assert.match(source.canvas, /marker\.setAttribute\("orient", "auto"\)/);
  assert.match(source.canvas, /function getAdaptiveEndControl/);
  assert.match(source.canvas, /c2: getAdaptiveEndControl/);
});

test("M2-024：顶部多输入箭头限制在距竖直方向约 32 度以内", () => {
  assert.match(source.canvas, /endApproach: multiInputEnd \? "top-biased" : "free"/);
  assert.match(source.canvas, /maxEndHorizontalRatio = points\.endApproach === "top-biased" \? 0\.625/);

  const direction = limitedTopEntryDirection(-500, 120);
  const deviation = deviationFromVerticalDegrees(direction.dx, direction.dy);
  assert.ok(deviation <= 32.01, `实际偏转角 ${deviation.toFixed(2)}° 超出限制`);
  assert.equal(direction.dx, -75);
});

test("M2-025：左右侧跨列连线仍使用水平路由，不受顶部角度限制", () => {
  assert.match(source.canvas, /routing: crossesToNextColumn \? "horizontal" : "vertical"/);
  assert.match(source.canvas, /if \(points\.routing === "horizontal"\)/);
  assert.match(source.canvas, /return \[buildHorizontalBezierSegment\(start, end\)\]/);
  assert.match(source.canvas, /function buildHorizontalBezierSegment/);
});

test("M2-026：连线支持悬停追踪源节点和目标节点", () => {
  assert.match(source.canvas, /function setConnectionTrace/);
  assert.match(source.canvas, /classList\.toggle\("node-connection-focus", active\)/);
  assert.match(source.canvas, /visiblePath\.classList\.add\("line-hover"\)/);
  assert.match(source.styles, /\.line-dimmed\s*\{\s*opacity: 0\.16/);
});

test("M2-027：当前前端工程能够通过 TypeScript 类型检查配置", () => {
  const packageJson = JSON.parse(readProjectFile("frontend/package.json"));
  assert.equal(typeof packageJson.scripts?.build, "string");
  assert.match(packageJson.scripts.build, /vue-tsc --noEmit/);
  assert.equal(fs.existsSync(path.join(PROJECT_ROOT, "frontend/tsconfig.json")), true);
});

