const assert = require("node:assert/strict");

/**
 * M2 前端模型搭建编辑器模块测试
 *
 * 说明：
 * 当前 frontend/src/app.js 主要依赖 DOM 事件和页面元素，不适合直接在 Node.js 中 import 执行。
 * 因此本测试文件抽取与 app.js 一致的核心数据结构和模型编辑逻辑进行测试，
 * 重点验证节点增删、连接管理、参数修改和 ModelGraph 导出格式。
 */

// 创建一个简化的编辑器状态
function createEditorState() {
  return {
    nodes: [],
    connections: [],
    nodeCounters: {},
  };
}

// 与 app.js / README 中保持一致的层配置
function getLayerConfig(layerType) {
  const configs = {
    Input: {
      type: "Input",
      title: "Input",
      badge: "Input",
      color: "emerald",
      hint: "28x28x1",
      params: { shape: [1, 28, 28] },
    },

    Output: {
      type: "Output",
      title: "Output",
      badge: "Output",
      color: "rose",
      hint: "?",
      params: {},
    },

    Conv2D: {
      type: "Conv2D",
      title: "Conv2D",
      badge: "Conv2D",
      color: "blue",
      note: "out=16, k=3, s=1, p=0",
      hint: "?",
      params: {
        out_channels: 16,
        kernel_size: 3,
        stride: 1,
        padding: 0,
      },
    },

    MaxPooling: {
      type: "Pooling",
      title: "MaxPooling",
      badge: "MaxPool",
      color: "purple",
      note: "k=2, s=2, p=0",
      hint: "?",
      params: {
        kernel_size: 2,
        stride: 2,
        padding: 0,
      },
    },

    ReLU: {
      type: "ReLU",
      title: "ReLU",
      badge: "ReLU",
      color: "orange",
      hint: "?",
      params: {},
    },

    Flatten: {
      type: "Flatten",
      title: "Flatten",
      badge: "Flatten",
      color: "indigo",
      hint: "?",
      params: {},
    },

    Linear: {
      type: "Linear",
      title: "Linear",
      badge: "Linear",
      color: "cyan",
      note: "out=128",
      hint: "?",
      params: {
        out_features: 128,
      },
    },

    Dropout: {
      type: "Dropout",
      title: "Dropout",
      badge: "Dropout",
      color: "amber",
      note: "p=0.5",
      hint: "?",
      params: {
        p: 0.5,
      },
    },
  };

  return configs[layerType] || configs.Linear;
}

// 添加节点
function addNodeFromLayer(state, layerType) {
  const config = getLayerConfig(layerType);
  const type = config.type;

  state.nodeCounters[type] = (state.nodeCounters[type] || 0) + 1;

  const node = {
    id: `${type.toLowerCase()}_${state.nodeCounters[type]}`,
    type,
    title: config.title,
    badge: config.badge,
    color: config.color,
    note: config.note,
    hint: config.hint || "?",
    x: 40,
    y: 40,
    params: { ...config.params },
  };

  state.nodes.push(node);
  return node;
}

// 删除节点，同时删除相关连接
function deleteNode(state, nodeId) {
  const beforeLength = state.nodes.length;

  state.nodes = state.nodes.filter(node => node.id !== nodeId);
  state.connections = state.connections.filter(
    ([source, target]) => source !== nodeId && target !== nodeId
  );

  return state.nodes.length < beforeLength;
}

// 建立连接
function connectNodes(state, sourceId, targetId) {
  if (!sourceId || !targetId) return false;

  // 不允许自连接
  if (sourceId === targetId) return false;

  const sourceExists = state.nodes.some(node => node.id === sourceId);
  const targetExists = state.nodes.some(node => node.id === targetId);

  // 不允许连接不存在的节点
  if (!sourceExists || !targetExists) return false;

  // 不允许重复连接，包括同方向重复和反方向重复
  const exists = state.connections.some(
    ([source, target]) =>
      (source === sourceId && target === targetId) ||
      (source === targetId && target === sourceId)
  );

  if (exists) return false;

  state.connections.push([sourceId, targetId]);
  return true;
}

// 删除指定连接
function deleteConnection(state, sourceId, targetId) {
  const beforeLength = state.connections.length;

  state.connections = state.connections.filter(
    ([source, target]) => !(source === sourceId && target === targetId)
  );

  return state.connections.length < beforeLength;
}

// 修改节点参数
function updateNodeParam(state, nodeId, key, value) {
  const node = state.nodes.find(item => item.id === nodeId);
  if (!node) return false;

  // 模拟前端参数为空的情况
  if (value === "" || value === null || value === undefined) {
    return false;
  }

  node.params = {
    ...node.params,
    [key]: value,
  };

  return true;
}

// 修改 Input Shape
function updateInputShape(state, nodeId, shapeText) {
  const node = state.nodes.find(item => item.id === nodeId);
  if (!node || node.type !== "Input") return false;

  const rawItems = shapeText.split(",").map(item => item.trim());

  if (rawItems.length === 0 || rawItems.some(item => item === "")) {
    return false;
  }

  const shape = rawItems.map(item => Number(item));

  if (shape.some(item => Number.isNaN(item) || item <= 0)) {
    return false;
  }

  node.params = {
    ...node.params,
    shape,
  };

  node.hint = shape.join("x");

  return true;
}

// 导出 ModelGraph
function getCurrentModelGraph(state) {
  return {
    layers: state.nodes.map(node => ({
      id: node.id,
      type: node.type,
      name: node.title,
      params: { ...node.params },
    })),

    connections: state.connections.map(([source, target]) => ({
      source,
      target,
    })),
  };
}

function runTests() {
  // M2-001 空画布导出 ModelGraph
  let state = createEditorState();
  let graph = getCurrentModelGraph(state);

  assert.deepEqual(graph.layers, []);
  assert.deepEqual(graph.connections, []);

  // M2-002 添加 Input 节点
  const input = addNodeFromLayer(state, "Input");

  assert.equal(state.nodes.length, 1);
  assert.equal(input.type, "Input");
  assert.equal(input.id, "input_1");
  assert.deepEqual(input.params.shape, [1, 28, 28]);

  // M2-003 添加 Conv2D 节点
  const conv = addNodeFromLayer(state, "Conv2D");

  assert.equal(state.nodes.length, 2);
  assert.equal(conv.type, "Conv2D");
  assert.equal(conv.params.out_channels, 16);
  assert.equal(conv.params.kernel_size, 3);
  assert.equal(conv.params.stride, 1);
  assert.equal(conv.params.padding, 0);

  // M2-004 添加 Pooling 节点
  const pool = addNodeFromLayer(state, "MaxPooling");

  assert.equal(pool.type, "Pooling");
  assert.equal(pool.params.kernel_size, 2);
  assert.equal(pool.params.stride, 2);
  assert.equal(pool.params.padding, 0);

  // M2-005 添加 Linear 节点
  const linear = addNodeFromLayer(state, "Linear");

  assert.equal(linear.type, "Linear");
  assert.equal(linear.params.out_features, 128);

  // M2-006 建立节点连接
  const connectResult = connectNodes(state, input.id, conv.id);

  assert.equal(connectResult, true);
  assert.equal(state.connections.length, 1);
  assert.deepEqual(state.connections[0], [input.id, conv.id]);

  // M2-007 拒绝自连接
  const selfConnectResult = connectNodes(state, input.id, input.id);

  assert.equal(selfConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-008 拒绝同方向重复连接
  const duplicateConnectResult = connectNodes(state, input.id, conv.id);

  assert.equal(duplicateConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-009 拒绝反方向重复连接
  const reverseDuplicateConnectResult = connectNodes(state, conv.id, input.id);

  assert.equal(reverseDuplicateConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-010 拒绝连接不存在的节点
  const missingNodeConnectResult = connectNodes(state, input.id, "missing_node");

  assert.equal(missingNodeConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-011 修改 Conv2D 参数
  const updateConvResult = updateNodeParam(state, conv.id, "out_channels", 32);

  assert.equal(updateConvResult, true);
  assert.equal(
    state.nodes.find(node => node.id === conv.id).params.out_channels,
    32
  );

  // M2-012 修改 Pooling 参数
  const updatePoolingResult = updateNodeParam(state, pool.id, "kernel_size", 3);

  assert.equal(updatePoolingResult, true);
  assert.equal(
    state.nodes.find(node => node.id === pool.id).params.kernel_size,
    3
  );

  // M2-013 修改 Linear 参数
  const updateLinearResult = updateNodeParam(state, linear.id, "out_features", 64);

  assert.equal(updateLinearResult, true);
  assert.equal(
    state.nodes.find(node => node.id === linear.id).params.out_features,
    64
  );

  // M2-014 修改 Input Shape
  const updateShapeResult = updateInputShape(state, input.id, "3,224,224");

  assert.equal(updateShapeResult, true);
  assert.deepEqual(
    state.nodes.find(node => node.id === input.id).params.shape,
    [3, 224, 224]
  );
  assert.equal(
    state.nodes.find(node => node.id === input.id).hint,
    "3x224x224"
  );

  // M2-015 拒绝空参数
  const emptyParamResult = updateNodeParam(state, conv.id, "out_channels", "");

  assert.equal(emptyParamResult, false);

  // M2-016 拒绝非法 Input Shape
  const invalidShapeResult = updateInputShape(state, input.id, "1,a,28");

  assert.equal(invalidShapeResult, false);

  // M2-017 导出 ModelGraph
  graph = getCurrentModelGraph(state);

  assert.equal(Array.isArray(graph.layers), true);
  assert.equal(Array.isArray(graph.connections), true);
  assert.equal(graph.layers.length, 4);
  assert.equal(graph.connections.length, 1);

  const exportedInput = graph.layers.find(layer => layer.id === input.id);
  const exportedConv = graph.layers.find(layer => layer.id === conv.id);
  const exportedPool = graph.layers.find(layer => layer.id === pool.id);
  const exportedLinear = graph.layers.find(layer => layer.id === linear.id);

  assert.deepEqual(exportedInput.params.shape, [3, 224, 224]);
  assert.equal(exportedConv.params.out_channels, 32);
  assert.equal(exportedPool.params.kernel_size, 3);
  assert.equal(exportedLinear.params.out_features, 64);

  assert.deepEqual(graph.connections[0], {
    source: input.id,
    target: conv.id,
  });

  // M2-018 删除连接
  const deleteConnectionResult = deleteConnection(state, input.id, conv.id);

  assert.equal(deleteConnectionResult, true);
  assert.equal(state.connections.length, 0);

  // M2-019 删除不存在的连接
  const deleteMissingConnectionResult = deleteConnection(state, input.id, conv.id);

  assert.equal(deleteMissingConnectionResult, false);
  assert.equal(state.connections.length, 0);

  // M2-020 删除节点，同时删除相关连接
  const reconnectResult = connectNodes(state, conv.id, pool.id);
  assert.equal(reconnectResult, true);
  assert.equal(state.connections.length, 1);

  const deleteNodeResult = deleteNode(state, conv.id);

  assert.equal(deleteNodeResult, true);
  assert.equal(state.nodes.some(node => node.id === conv.id), false);
  assert.equal(state.connections.length, 0);

  console.log("M2 model editor tests passed.");
}

runTests();