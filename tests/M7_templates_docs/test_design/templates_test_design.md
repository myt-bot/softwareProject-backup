# 模型模板模块测试说明

## 1. 测试目标

验证内置模型模板功能是否能稳定提供模板列表、生成合法 `ModelGraph`，并与结构校验、模型构建和项目接口形成完整链路。测试重点不是只看 `unittest` 输出的 `ok`，而是明确断言每条用例的实际业务返回值，例如 HTTP 状态码、响应体字段、模板数量和维度推导结果。

## 2. 被测模块和代码路径

- `backend/templates.py`
  - `get_available_templates`
  - `apply_template`
  - 各 `create_*_template` 模板生成函数
- `backend/validator.py`
  - 新增模板层类型的参数校验
  - 新增模板层类型的 shape 推导
- `backend/model_builder.py`
  - `create_layer`
  - 新增层对应的 PyTorch 模块构建
- `backend/main.py`
  - `GET /projects/templates`
  - `GET /projects/templates/{template_name}`
  - `POST /projects/from-template`

## 3. 测试范围

- 11 个模板完整性：
  - `linear_classifier`
  - `mlp`
  - `perceptron`
  - `lenet`
  - `resnet_tiny`
  - `lstm`
  - `seq2seq`
  - `transformer_encoder_tiny`
  - `self_attention_demo`
  - `vae`
  - `gcn_tiny`
- 模板别名和未知模板错误处理。
- 所有模板的 `validate_model_graph` 校验结果。
- LSTM、Seq2Seq、TransformerEncoder、SelfAttention、VAE、GraphConv 的 shape 推导。
- 新增层非法参数识别。
- `model_builder.create_layer` 对新增层的模块构建。
- 模板 API 到项目保存 API 的集成链路。
- `/projects/templates` 路由不被 `/projects/{project_id}` 错误捕获。

## 4. 测试用例表

| 用例编号 | 类型 | 测试场景                                  | 输入数据                                                           | 预期业务结果                                                                        | 当前自动化断言/实际结果                                                       | 判定     |
| -------- | ---- | ----------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------- |
| M7-001   | 单元 | 模板列表完整性                            | 调用`get_available_templates()`                                  | 返回 11 个模板，key 与设计清单完全一致                                              | 断言`len=11`，key 集合等于预期集合                                          | 通过     |
| M7-002   | 单元 | 所有模板均可生成并校验                    | 11 个模板 key                                                      | `apply_template` 返回 `status=ok`；`validate_model_graph` 返回 `valid=True` | 对每个模板断言`status=ok`、`valid=True`、`errors=[]`                    | 通过     |
| M7-003   | 单元 | 模板别名可用                              | `linear`、`cnn`、`transformer`、`self_attention`、`gcn`  | 别名返回对应模板模型图                                                              | 断言别名结果与目标 key 的`model` 相等                                       | 通过     |
| M7-004   | 单元 | 未知模板错误处理                          | `unknown_template`                                               | 返回`status=error`，包含 `available_templates`                                  | 断言响应中包含错误信息和 11 个可用模板 key                                    | 通过     |
| M7-005   | 单元 | LSTM 模板维度推导                         | `create_lstm_template()`                                         | `lstm` 输出 `[32]`，分类器输出 `[4]`                                          | 断言`shapes["lstm"]["output_shape"] == [32]`                                | 通过     |
| M7-006   | 单元 | Seq2Seq 模板维度推导                      | `create_seq2seq_template()`                                      | `seq2seq` 输出 `[6, 12]`                                                        | 断言`shapes["seq2seq"]["output_shape"] == [6, 12]`                          | 通过     |
| M7-007   | 单元 | Transformer Encoder 模板维度推导          | `create_transformer_encoder_tiny_template()`                     | `encoder` 输出 `[16,32]`，Flatten 输出 `[512]`                                | 断言两个 shape 均与预期一致                                                   | 通过     |
| M7-008   | 单元 | SelfAttention 模板维度推导                | `create_self_attention_demo_template()`                          | `attention` 输出 `[8,32]`，Flatten 输出 `[256]`                               | 断言两个 shape 均与预期一致                                                   | 通过     |
| M7-009   | 单元 | VAE 模板维度推导                          | `create_vae_template()`                                          | `vae` 输出 `[784]`                                                              | 断言输出 shape 为`[784]`                                                    | 通过     |
| M7-010   | 单元 | GCN 模板维度推导                          | `create_gcn_tiny_template()`                                     | `gcn1` 输出 `[20,32]`，`gcn2` 输出 `[20,7]`                                 | 断言两个 GraphConv 输出 shape 均与预期一致                                    | 通过     |
| M7-011   | 单元 | 新增层 shape helper                       | 7 组新增层输入 shape                                               | 分别返回预期 shape                                                                  | 断言每组`infer_layer_shape` 输出等于预期                                    | 通过     |
| M7-012   | 单元 | 注意力头数非法                            | `embed_dim=30`，`num_heads=8`                                  | `valid=False`，错误提示注意力维度与头数关系                                       | 断言`valid=False` 且错误信息包含“注意力维度”或 `num_heads`              | 通过     |
| M7-013   | 单元 | LSTM 布尔参数非法                         | `return_sequences="yes"`                                         | `valid=False`，错误提示布尔值非法                                                 | 断言错误包含`return_sequences` 和“布尔值”                                 | 通过     |
| M7-014   | 单元 | GraphConv 缺少`out_features`            | `params={}`                                                      | `valid=False`，错误提示 `out_features` 必须是正整数                             | 断言错误包含`out_features 必须是正整数`                                     | 通过     |
| M7-015   | 单元 | `model_builder.create_layer` 构建新增层 | 6 类新增层配置                                                     | 返回非空 PyTorch 模块且有`forward`                                                | 在安装`torch` 的环境中断言非空和 `hasattr(forward)`；缺 `torch` 时跳过  | 条件通过 |
| M7-016   | 集成 | 模板列表接口                              | `GET /projects/templates`                                        | HTTP 200；响应`status=ok`；`count=11`                                           | 断言`response.status_code == 200`、`count == 11`                          | 通过     |
| M7-017   | 集成 | 路由顺序检查                              | `GET /projects/templates`                                        | 不被`/projects/{project_id}` 捕获；返回模板列表                                   | 断言 HTTP 200 且响应包含`data`                                              | 通过     |
| M7-018   | 集成 | 模板详情接口                              | `GET /projects/templates/mlp`                                    | HTTP 200；`status=ok`；返回合法 `model`                                         | 断言 HTTP 200，并对返回`model` 再执行 `validate_model_graph(valid=True)`  | 通过     |
| M7-019   | 集成 | 未知模板详情接口                          | `GET /projects/templates/not_exists`                             | HTTP 404；响应`status=error`；包含 `available_templates`                        | 断言`response.status_code == 404`、`body["status"] == "error"`            | 通过     |
| M7-020   | 集成 | 基于模板创建项目完整链路                  | 先创建用户，再`POST /projects/from-template`，模板 `mlp`       | HTTP 200；项目保存成功；再查询项目成功；项目模型图校验通过                          | 断言创建项目 HTTP 200、查询项目 HTTP 200、`model_graph` 校验 `valid=True` | 通过     |
| M7-021   | 集成 | 默认项目名和描述                          | 模板`transformer_encoder_tiny`，不传 `name` 和 `description` | HTTP 200；项目名为`Transformer Encoder Tiny Project`；描述来自模板元信息          | 断言默认 name 和 description 符合预期                                         | 通过     |
| M7-022   | 集成 | 未知模板创建项目                          | 已存在用户，模板`not_exists`                                     | HTTP 404；响应`status=error`；包含 `available_templates`                        | 断言`response.status_code == 404` 和错误响应字段                            | 通过     |
| M7-023   | 集成 | 不存在用户创建模板项目                    | `user_id=user_not_exists`，模板 `mlp`                          | HTTP 400；响应`status=error`；提示用户不存在                                      | 断言 HTTP 400 且 message 包含“不存在”                                       | 通过     |
| M7-024   | 集成 | 创建后的模板项目出现在项目列表            | 创建 GCN 模板项目后请求`/projects?user_id=...`                   | HTTP 200；列表 count 为 1；项目名匹配；模型图合法                                   | 断言列表响应、项目名、模型校验结果                                            | 通过     |

## 5. 预期运行方式

在项目根目录运行：

```powershell
conda activate software
python -m unittest tests\M7_templates_docs\test_code\test_templates_unit.py tests\M7_templates_docs\test_code\test_templates_integration.py
```

如果使用未安装依赖的 Python 环境：

- 缺少 `torch` 时，`model_builder` 构建测试会跳过。
- 缺少 `fastapi` 时，接口集成测试会跳过。

在 `software` 环境中如果依赖完整，应看到全部测试通过，且不会出现用户名长度错误或 `create_layer` 参数数量错误。
