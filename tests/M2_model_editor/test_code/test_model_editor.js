const assert = require("node:assert/strict");

function createEditorState() {
  return {
    nodes: [],
    connections: [],
    nodeCounters: {},
  };
}

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
      params: {},
    },
    Conv2D: {
      type: "Conv2D",
      title: "Conv2D",
      badge: "Conv2D",
      color: "blue",
      note: "out=16, k=3, s=1, p=0",
      params: { out_channels: 16, kernel_size: 3, stride: 1, padding: 0 },
    },
    MaxPooling: {
      type: "Pooling",
      title: "MaxPooling",
      badge: "MaxPool",
      color: "purple",
      note: "k=2, s=2",
      params: { kernel_size: 2, stride: 2, padding: 0 },
    },
    Flatten: {
      type: "Flatten",
      title: "Flatten",
      badge: "Flatten",
      color: "indigo",
      params: {},
    },
    Linear: {
      type: "Linear",
      title: "Linear",
      badge: "Linear",
      color: "cyan",
      note: "out=128",
      params: { out_features: 128 },
    },
    Dropout: {
      type: "Dropout",
      title: "Dropout",
      badge: "Dropout",
      color: "amber",
      note: "p=0.5",
      params: { p: 0.5 },
    },
  };

  return configs[layerType] || configs.Linear;
}

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

function deleteNode(state, nodeId) {
  state.nodes = state.nodes.filter(node => node.id !== nodeId);
  state.connections = state.connections.filter(
    ([source, target]) => source !== nodeId && target !== nodeId
  );
}

function connectNodes(state, sourceId, targetId) {
  if (!sourceId || !targetId) return false;
  if (sourceId === targetId) return false;

  const sourceExists = state.nodes.some(node => node.id === sourceId);
  const targetExists = state.nodes.some(node => node.id === targetId);

  if (!sourceExists || !targetExists) return false;

  const exists = state.connections.some(
    ([source, target]) => source === sourceId && target === targetId
  );

  if (exists) return false;

  state.connections.push([sourceId, targetId]);
  return true;
}

function updateNodeParam(state, nodeId, key, value) {
  const node = state.nodes.find(item => item.id === nodeId);
  if (!node) return false;

  node.params = {
    ...node.params,
    [key]: value,
  };

  return true;
}

function getCurrentModelGraph(state) {
  return {
    layers: state.nodes.map(node => ({
      id: node.id,
      type: node.type,
      name: node.title,
      params: { ...node.params },
    })),
    connections: state.connections.map(([source, target]) => ({ source, target })),
  };
}

function runTests() {
  // M2-001 空画布导出
  let state = createEditorState();
  let graph = getCurrentModelGraph(state);
  assert.deepEqual(graph.layers, []);
  assert.deepEqual(graph.connections, []);

  // M2-002 添加节点
  const input = addNodeFromLayer(state, "Input");
  const conv = addNodeFromLayer(state, "Conv2D");

  assert.equal(state.nodes.length, 2);
  assert.equal(input.type, "Input");
  assert.deepEqual(input.params.shape, [1, 28, 28]);
  assert.equal(conv.type, "Conv2D");
  assert.equal(conv.params.out_channels, 16);

  // M2-003 连接节点
  const connectResult = connectNodes(state, input.id, conv.id);
  assert.equal(connectResult, true);
  assert.equal(state.connections.length, 1);

  // M2-004 拒绝自连接
  const selfConnectResult = connectNodes(state, input.id, input.id);
  assert.equal(selfConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-005 拒绝重复连接
  const duplicateConnectResult = connectNodes(state, input.id, conv.id);
  assert.equal(duplicateConnectResult, false);
  assert.equal(state.connections.length, 1);

  // M2-006 修改参数
  const updateResult = updateNodeParam(state, conv.id, "out_channels", 32);
  assert.equal(updateResult, true);
  assert.equal(state.nodes.find(node => node.id === conv.id).params.out_channels, 32);

  // M2-007 导出 ModelGraph
  graph = getCurrentModelGraph(state);
  assert.equal(Array.isArray(graph.layers), true);
  assert.equal(Array.isArray(graph.connections), true);
  assert.equal(graph.layers.length, 2);
  assert.deepEqual(graph.connections[0], {
    source: input.id,
    target: conv.id,
  });

  const exportedConv = graph.layers.find(layer => layer.id === conv.id);
  assert.equal(exportedConv.params.out_channels, 32);

  // M2-008 删除节点时删除相关连接
  deleteNode(state, conv.id);
  assert.equal(state.nodes.some(node => node.id === conv.id), false);
  assert.equal(state.connections.length, 0);

  // M2-009 参数为空或非法节点
  const missingNodeUpdate = updateNodeParam(state, "missing_node", "out_features", 64);
  assert.equal(missingNodeUpdate, false);

  console.log("M2 model editor tests passed.");
}

runTests();