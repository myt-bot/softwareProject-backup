# 结构检查与维度推导模块测试说明

## 1. 测试目标

验证 `backend/validator.py` 中模型结构检查与维度推导函数是否能按照前端模型图输入，正确判断图结构合法性、识别异常输入，并推导各层输出维度；同时验证 `backend/main.py` 中 `/validate` 接口能正确调用校验逻辑并返回结果。

## 2. 被测模块和负责代码路径

- `backend/validator.py`
- `backend/main.py` 中 `/validate` 接口

## 3. 测试范围

- 必要节点检查：缺少 `Input`、缺少 `Output`
- 连接关系检查：孤立节点、连接断裂、循环连接
- 参数检查：参数缺失、参数类型或取值非法
- 维度推导：`Conv2D`、`Pooling`、`Flatten`、`Linear`
- `/validate` 接口：合法模型、业务校验失败模型、请求体 schema 错误

## 4. 不测试的内容

- `backend/schemas.py` 中模型结构相关数据类
- 前端画布交互、拖拽连线和页面渲染
- 模型训练、训练任务状态、训练结果查询
- PyTorch 代码导出逻辑
- 真实深度学习框架中的算子执行结果
- 未在当前模块中声明或支持的层类型行为

## 5. 测试用例表

| 用例编号 | 测试场景 | 输入数据 | 操作步骤 | 预期结果 | 实际输出结果 | 优先级 |
|---|---|---|---|---|---|---|
| M3-001 | 正常 CNN 图结构校验和维度推导 | `Input -> Conv2D -> Pooling -> Flatten -> Linear -> Output`，输入维度 `[1, 28, 28]` | 调用 `validate_model_graph` | `valid=True`，无错误；`Conv2D=[8,28,28]`，`Pooling=[8,14,14]`，`Flatten=[1568]`，`Linear=[10]` | 与预期一致：返回 `valid=True`、`errors=[]`，各层输出维度分别为 `[8,28,28]`、`[8,14,14]`、`[1568]`、`[10]` | 高 |
| M3-002 | 缺少 Input 节点 | 图中只有 `Linear -> Output` | 调用 `validate_model_graph` | `valid=False`，错误包含“模型缺少必要节点: Input” | 与预期一致：返回 `valid=False`，`errors` 包含“模型缺少必要节点: Input” | 高 |
| M3-003 | 缺少 Output 节点 | 图中只有 `Input -> Flatten` | 调用 `validate_model_graph` | `valid=False`，错误包含“模型缺少必要节点: Output” | 与预期一致：返回 `valid=False`，`errors` 包含“模型缺少必要节点: Output” | 高 |
| M3-004 | 孤立节点 | 图中存在未参与连接的 `ReLU` 节点 | 调用 `validate_model_graph` | `valid=False`，错误提示存在孤立节点或连接异常 | 与预期一致：返回 `valid=False`，错误信息包含“孤立”或“连接” | 高 |
| M3-005 | 连接断裂 | 连接终点指向不存在的节点 `missing_output` | 调用 `validate_model_graph` | `valid=False`，错误包含“连接终点不存在: missing_output” | 与预期一致：返回 `valid=False`，`errors` 包含“连接终点不存在: missing_output” | 高 |
| M3-006 | 循环连接 | `Input -> ReLU -> Output -> ReLU` | 调用 `validate_model_graph` | `valid=False`，错误提示模型连接中存在环 | 与预期一致：返回 `valid=False`，错误信息包含“存在环” | 高 |
| M3-007 | Conv2D 参数缺失 | `Conv2D` 缺少 `out_channels` | 调用 `validate_model_graph` | `valid=False`，错误提示 `out_channels` 必须是正整数 | 与预期一致：返回 `valid=False`，错误信息包含“out_channels 必须是正整数” | 高 |
| M3-008 | Conv2D 维度推导 | 输入 `[3,32,32]`，`out_channels=16`，`kernel_size=5`，`stride=1`，`padding=0` | 调用 `infer_layer_shape` | 输出维度为 `[16,28,28]` | 与预期一致：实际输出 `[16,28,28]` | 高 |
| M3-009 | Pooling 维度推导 | 输入 `[16,28,28]`，`kernel_size=2`，`stride=2`，`padding=0` | 调用 `infer_layer_shape` | 输出维度为 `[16,14,14]` | 与预期一致：实际输出 `[16,14,14]` | 高 |
| M3-010 | Flatten 维度推导 | 输入 `[8,14,14]` | 调用 `infer_flatten_shape` | 输出维度为 `[1568]` | 与预期一致：实际输出 `[1568]` | 高 |
| M3-011 | Linear 维度不匹配 | 输入 `[1,28,28]` 直接连接 `Linear(in_features=10,out_features=3)` | 调用 `validate_model_graph` | `valid=False`，错误提示 Linear 输入维度与 `in_features` 不匹配 | 与预期一致：返回 `valid=False`，错误信息包含 `Linear` 和 `in_features` 或“维度” | 高 |
| M3-012 | `/validate` 接口正常流程 | 向接口提交合法 CNN 模型图 | 使用 `TestClient` 请求 `POST /validate` | HTTP 200，响应中 `valid=True`，包含 `message` 和各层 `shapes` | 与预期一致：HTTP 200，响应 `valid=True`、`errors=[]`、`message=结构校验通过`，包含各层 `shapes` | 高 |
| M3-013 | `/validate` 接口业务校验失败 | 向接口提交缺少 `Output` 的模型图 | 使用 `TestClient` 请求 `POST /validate` | HTTP 200，响应中 `valid=False`，错误包含“模型缺少必要节点: Output” | 与预期一致：HTTP 200，响应 `valid=False`，`errors` 包含“模型缺少必要节点: Output” | 高 |
| M3-014 | `/validate` 接口请求体格式错误 | `layers` 传入字符串而不是数组 | 使用 `TestClient` 请求 `POST /validate` | HTTP 422，请求体 schema 校验失败 | 与预期一致：HTTP 422，请求体 schema 校验失败 | 中 |

## 6. 预期结果

- 合法模型图应返回校验通过，并包含所有层的 `input_shape`、`output_shape` 和状态信息。
- 缺少必要节点、断裂连接、循环连接、参数缺失或参数非法时，应返回 `valid=False` 和可读错误信息。
- `Conv2D`、`Pooling`、`Flatten` 应按公式或展平规则正确推导输出维度。
- `Linear` 应检查输入展平维度是否与 `in_features` 一致；不一致时应返回错误。
- `/validate` 接口应将 `ModelRequest.model` 转成普通字典后调用 `validate_model_graph`，并返回统一校验结果。

## 7. 异常情况考虑

- 请求体不是合法模型图结构时，应返回校验失败或请求体验证失败。
- 图中存在不存在的连接起点或终点时，应定位到具体节点 id。
- 图中存在循环连接时，应阻止后续维度推导，避免拓扑排序结果错误。
- 层参数缺失、类型错误或取值越界时，应返回明确的参数错误。
- 维度无法推导或层之间维度不匹配时，应返回失败结果，而不是静默生成错误维度。
