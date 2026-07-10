# 结构检查与维度推导模块测试说明

## 1. 测试目标

验证 M3 模块能在训练或导出前完成模型结构校验、参数合法性检查和张量维度推导，能按照前端模型图输入正确判断图结构合法性、识别异常输入，并推导各层输出维度；同时验证 `/validate` 接口能正确调用校验逻辑并返回结果。

## 2. 被测模块和负责代码路径

- `local_agent/runtime/validator.py`
- `local_agent/runtime/graph_utils.py`
- `local_agent/runtime/schemas.py`
- `local_agent/main.py` 中 `/validate` 接口
- `backend/main.py` 中 `/validate` 接口

## 3. 测试范围

- 必要节点检查：缺少 `Input`、缺少 `Output`
- 连接关系检查：孤立节点、连接断裂、循环连接
- 参数检查：参数缺失、参数类型或取值非法
- 维度推导：`Conv2D`、`Pooling`、`Flatten`、`Linear`、多输入 `add/concat` 合并
- `/validate` 接口：合法模型、业务校验失败模型、请求体 schema 错误

## 4. 不测试的内容

- `backend/schemas.py` 中模型结构相关数据类
- 前端画布交互、拖拽连线和页面渲染
- 模型训练、训练任务状态、训练结果查询
- PyTorch 代码导出逻辑
- M5/M6/M7 模块的测试职责
- 真实深度学习框架中的算子执行结果
- 未在当前模块中声明或支持的层类型行为

## 5. 测试用例表

| 用例编号 | 测试场景 | 输入数据 | 操作步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|
| M3-001 | 正常 CNN 图结构校验和维度推导 | `Input -> Conv2D -> Pooling -> Flatten -> Linear -> Output`，输入维度 `[1, 28, 28]` | 调用 `validate_model_graph` | `valid=True`，无错误；`Conv2D=[8,28,28]`，`Pooling=[8,14,14]`，`Flatten=[1568]`，`Linear=[10]` | 高 |
| M3-002 | 缺少 Input 节点 | 图中只有 `Linear -> Output` | 调用 `validate_model_graph` | `valid=False`，错误包含“模型缺少必要节点: Input” | 高 |
| M3-003 | 缺少 Output 节点 | 图中只有 `Input -> Flatten` | 调用 `validate_model_graph` | `valid=False`，错误包含“模型缺少必要节点: Output” | 高 |
| M3-004 | 孤立节点 | 图中存在未参与连接的 `ReLU` 节点 | 调用 `validate_model_graph` | `valid=False`，错误提示存在孤立节点或连接异常 | 高 |
| M3-005 | 连接断裂 | 连接终点指向不存在的节点 `missing_output` | 调用 `validate_model_graph` | `valid=False`，错误包含“连接终点不存在: missing_output” | 高 |
| M3-006 | 循环连接 | `Input -> ReLU -> Output -> ReLU` | 调用 `validate_model_graph` | `valid=False`，错误提示模型连接中存在环 | 高 |
| M3-007 | Conv2D 参数缺失 | `Conv2D` 缺少 `out_channels` | 调用 `validate_model_graph` | `valid=False`，错误提示 `out_channels` 必须是正整数 | 高 |
| M3-008 | Conv2D 维度推导 | 输入 `[3,32,32]`，`out_channels=16`，`kernel_size=5`，`stride=1`，`padding=0` | 调用 `infer_layer_shape` | 输出维度为 `[16,28,28]` | 高 |
| M3-009 | Pooling 维度推导 | 输入 `[16,28,28]`，`kernel_size=2`，`stride=2`，`padding=0` | 调用 `infer_layer_shape` | 输出维度为 `[16,14,14]` | 高 |
| M3-010 | Flatten 维度推导 | 输入 `[8,14,14]` | 调用 `infer_flatten_shape` | 输出维度为 `[1568]` | 高 |
| M3-011 | Linear 维度不匹配 | 输入 `[1,28,28]` 直接连接 `Linear(in_features=10,out_features=3)` | 调用 `validate_model_graph` | `valid=False`，错误提示 Linear 输入维度与 `in_features` 不匹配 | 高 |
| M3-012 | `/validate` 接口正常流程 | 向接口提交合法 CNN 模型图 | 使用 `TestClient` 请求 `POST /validate` | HTTP 200，响应中 `valid=True`，包含 `message` 和各层 `shapes` | 高 |
| M3-013 | `/validate` 接口业务校验失败 | 向接口提交缺少 `Output` 的模型图 | 使用 `TestClient` 请求 `POST /validate` | HTTP 200，响应中 `valid=False`，错误包含“模型缺少必要节点: Output” | 高 |
| M3-014 | `/validate` 接口请求体格式错误 | `layers` 传入字符串而不是数组 | 使用 `TestClient` 请求 `POST /validate` | HTTP 422，请求体 schema 校验失败 | 中 |
| M3-015 | add 合并输入维度不一致 | `Input([8,28,28])` 和 `Input([16,28,28])` 同时连接到 `ReLU(params.merge="add")`，再连接 `Output` | 调用 `validate_model_graph` | `valid=False`，错误提示 add 合并要求所有输入 shape 完全一致 | 高 |
| M3-016 | concat 合并非拼接维度不一致 | `Input([8,28,28])` 和 `Input([8,32,28])` 同时连接到 `ReLU(params.merge="concat", dim=1)`，再连接 `Output` | 调用 `validate_model_graph` | `valid=False`，错误提示 concat 合并要求除拼接维度外其它维度一致 | 高 |
| M3-017 | 合法 MLP 图结构校验和维度推导 | `Input([1,28,28]) -> Flatten -> Linear(64) -> ReLU -> Linear(10) -> Output` | 调用 `validate_model_graph` | `valid=True`，`Flatten=[784]`，`fc1=[64]`，`fc2=[10]` | 高 |
| M3-018 | 合法 concat 分支维度推导 | 两个 `Input([8,28,28])` 同时连接到 `ReLU(params.merge="concat", dim=0)` | 调用 `validate_model_graph` | `valid=True`，合并后 `merge.output_shape=[16,28,28]` | 高 |
| M3-019 | Conv2D kernel_size 过大 | `Input([1,4,4]) -> Conv2D(out_channels=8,kernel_size=5) -> Output` | 调用 `validate_model_graph` | `valid=False`，错误提示 shape、维度、输出尺寸或 Conv2D 相关信息 | 高 |
| M3-020 | Pooling kernel_size 过大 | `Input([8,2,2]) -> Pooling(kernel_size=3,stride=1) -> Output` | 调用 `validate_model_graph` | `valid=False`，错误提示 shape、维度、输出尺寸或 Pooling 相关信息 | 高 |
| M3-021 | Conv2D out_channels 非法 | `out_channels=0`、`-1`、`"8"` | 调用 `validate_model_graph` | `valid=False`，错误包含 `out_channels` 或“正整数” | 高 |
| M3-022 | Linear out_features 缺失或非法 | `params={}`、`out_features=0`、`-1`、`"10"` | 调用 `validate_model_graph` | `valid=False`，错误包含 `out_features` 或“正整数” | 高 |
| M3-023 | Dropout p 越界或类型非法 | `p=-0.1`、`1.1`、`"0.5"` | 调用 `validate_model_graph` | `valid=False`，错误包含 Dropout、p、概率或“0 到 1” | 中 |
| M3-024 | 云端 `backend.main` `/validate` 正常和业务失败 | 合法 CNN，以及缺少 `Output` 的模型图 | 使用 `TestClient(backend_app)` 请求 `POST /validate` | 合法模型 HTTP 200 且 `valid=True`；业务非法模型 HTTP 200 且 `valid=False`，不返回 500 | 高 |

## 6. 预期结果

- 合法模型图应返回校验通过，并包含所有层的 `input_shape`、`output_shape` 和状态信息。
- 缺少必要节点、断裂连接、循环连接、参数缺失或参数非法时，应返回 `valid=False` 和可读错误信息。
- `Conv2D`、`Pooling`、`Flatten` 应按公式或展平规则正确推导输出维度。
- `Linear` 应检查输入展平维度是否与 `in_features` 一致；不一致时应返回错误。
- 多输入节点使用 `params.merge="add"` 或 `"sum"` 时，应检查所有前驱输出 shape 完全一致；不一致时应返回错误。
- 多输入节点使用 `params.merge="concat"` 时，应检查所有前驱输出 shape 的维度数量一致，并且除拼接维度外其它维度完全一致。
- 卷积、池化窗口大于输入空间尺寸时，应返回 `valid=False`，避免继续使用非法输出尺寸。
- `Conv2D.out_channels`、`Linear.out_features`、`Dropout.p` 等参数非法时，应返回明确参数错误。
- `/validate` 接口应将请求中的模型图传给 `validate_model_graph`，并返回统一校验结果；业务校验失败不应返回 500。

## 7. 异常情况考虑

- 请求体不是合法模型图结构时，应返回校验失败或请求体验证失败。
- 图中存在不存在的连接起点或终点时，应定位到具体节点 id。
- 图中存在循环连接时，应阻止后续维度推导，避免拓扑排序结果错误。
- 层参数缺失、类型错误或取值越界时，应返回明确的参数错误。
- 卷积或池化公式得到非正输出尺寸时，应返回维度推导失败，而不是静默生成负数或零维度。
- 维度无法推导或层之间维度不匹配时，应返回失败结果，而不是静默生成错误维度。
- add 合并遇到不同 shape 的分支输入时，应阻止后续维度推导并返回可读错误信息。
- concat 合并遇到非拼接维度不同或维度数量不同的分支输入时，应阻止后续维度推导并返回可读错误信息。
- `backend.main` 在当前环境依赖不可用时，对应接口测试允许跳过，并在测试输出中说明导入失败原因。

## 8. 测试运行命令

```bash
.venv\Scripts\python.exe -m pytest tests/M3_validator_shape/test_code -q -p no:cacheprovider
.venv\Scripts\python.exe -m compileall local_agent/runtime/validator.py local_agent/runtime/graph_utils.py local_agent/runtime/schemas.py
```
