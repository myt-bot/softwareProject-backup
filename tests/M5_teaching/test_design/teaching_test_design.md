# M5 教学辅助核心测试设计

## 1. 测试对象与范围

本测试设计面向 `backend/teaching.py` 中独立的教学辅助知识核心，覆盖以下公开接口：

- `list_supported_layers()`
- `get_layer_teaching(layer_type)`
- `get_parameter_teaching(layer_type, param_name)`
- `get_error_suggestion(error_message, context=None)`
- `get_teaching_catalog()`
- `explain_model_graph(model_graph)`

测试重点是验证教学知识的结构稳定性、真实项目字段覆盖、异常输入兜底、返回对象隔离，以及不依赖 M3/M6/前端运行时。

## 2. 不在本模块测试范围内的内容

- 不测试 FastAPI 路由或任何后端接口接入。
- 不测试前端组件渲染、交互、InfoTip 展示或画布操作。
- 不测试 `local_agent/runtime/validator.py` 的结构校验正确性。
- 不测试 `local_agent/runtime/code_exporter.py` 的 Python/Notebook 导出逻辑。
- 不测试 PyTorch 模型构建、训练、数据集加载或设备选择。
- 不把 M5 的教学提醒当作正式合法性校验结果。

## 3. 测试环境

- 操作系统：Windows PowerShell 环境。
- Python：项目虚拟环境 `.\.venv\Scripts\python.exe`。
- 测试框架：`pytest`。
- 运行目录：项目仓库根目录。
- 依赖要求：M5 模块只允许使用 Python 标准库，当前测试通过 AST 检查导入来源。

## 4. 测试方法

- 使用 `pytest` 编写自动化单元测试。
- 使用 `parametrize` 批量覆盖层类型、参数、错误文本和异常输入。
- 对返回字段执行强断言，确保必需字段齐全且主要文本非空。
- 对返回列表和嵌套结构执行修改后复查，验证深拷贝或独立构造能力。
- 使用静态源码解析检查 `backend/teaching.py` 未引入第三方重依赖。

## 5. 测试分类

### 5.1 层教学说明

验证 15 种规范层名均可查询到 `known=True` 的教学说明，且字段完整：

- `Input`
- `Output`
- `Add`
- `Conv2D`
- `Pooling`
- `ReLU`
- `Flatten`
- `Linear`
- `Dropout`
- `LSTM`
- `Seq2Seq`
- `TransformerEncoder`
- `SelfAttention`
- `VAE`
- `GraphConv`

同时验证 `MaxPooling`、`maxpooling`、`pooling` 等别名映射到 `Pooling`。

### 5.2 参数教学说明

验证当前项目真实使用的参数均可查询，且字段完整、文本非空、常见错误列表非空。

覆盖参数包括基础层参数、进阶层参数和布尔参数，例如：

- `Input.shape`
- `Conv2D.out_channels/kernel_size/stride/padding`
- `Pooling.kernel_size/stride/padding`
- `Linear.in_features/out_features`
- `Dropout.p`
- `LSTM.hidden_size/num_layers/bidirectional/return_sequences`
- `Seq2Seq.hidden_size/output_size/target_length/num_layers`
- `TransformerEncoder.d_model/num_heads/num_layers/dim_feedforward/dropout`
- `SelfAttention.embed_dim/num_heads/dropout`
- `VAE.latent_dim/output_features`
- `GraphConv.out_features`

### 5.3 错误建议

验证 `get_error_suggestion()` 能根据当前 M3 和前端真实错误文本关键词，返回教学排查建议。

覆盖 16 类已知错误，以及无法匹配时的 `unknown_error` 兜底。

### 5.4 模型图教学概览

验证 `explain_model_graph()` 能解释当前项目 ModelGraph 结构：

- 顶层字段：`layers`、`connections`
- 层字段：`id`、`type`、`name`、`params`
- 连接字段：`source`、`target`

重点检查模型类型识别、层/连接计数、层类型统计、简单拓扑 flow、关键层、教学重点和初学者提醒。

### 5.5 异常输入与兜底

验证以下输入不会抛异常，并返回统一兜底结构：

- `None`
- 空字符串
- 数字
- 空字典
- 非字典模型图
- 缺失或类型错误的 `layers`
- 类型错误的 `connections`
- 非字典 layer 或 connection
- 未知层类型
- 陌生错误文本

### 5.6 深拷贝与依赖隔离

验证调用者修改返回对象后，再次查询不受污染：

- 层说明
- 参数说明
- 错误建议
- 教学目录
- 模型图概览
- 支持层列表

同时验证 `backend/teaching.py` 不导入 `torch`、`fastapi`、`sqlalchemy`、`code_exporter` 或 validator。

## 6. 主要测试用例表

| 用例编号 | 测试内容 | 输入 | 预期结果 |
| --- | --- | --- | --- |
| M5-T001 | 支持层列表 | 调用 `list_supported_layers()` | 返回 15 个规范层名，无重复，不含别名 |
| M5-T002 | 基础层说明 | 逐个查询 9 个基础层 | `known=True`，字段完整，文本非空 |
| M5-T003 | 进阶层说明 | 查询 LSTM、Seq2Seq、TransformerEncoder、SelfAttention、VAE、GraphConv | `known=True`，字段完整，教学说明非空 |
| M5-T004 | 层别名兼容 | `MaxPooling`、`maxpooling`、`pooling` | 均映射为 `Pooling` |
| M5-T005 | 未知层兜底 | `None`、空字符串、数字、未知层 | `known=False`，不抛异常 |
| M5-T006 | 基础参数说明 | 查询 Conv2D、Pooling、Linear、Dropout 等参数 | `known=True`，字段完整，建议非空 |
| M5-T007 | 进阶参数说明 | 查询 LSTM、Transformer、VAE、GraphConv 等真实参数 | `known=True`，字段完整 |
| M5-T008 | 布尔参数说明 | `LSTM.bidirectional`、`LSTM.return_sequences` | 说明开启/关闭影响，调大/调小字段写明不适用 |
| M5-T009 | 未知参数兜底 | 未知层、未知参数、非字符串参数 | `known=False`，不抛异常 |
| M5-T010 | 教学目录一致性 | `get_teaching_catalog()` | 目录内容与公开查询接口一致 |
| M5-T011 | 错误建议匹配 | 16 类真实错误文本 | 返回正确 `category`，建议非空 |
| M5-T012 | 错误建议兜底 | `None`、空字符串、数字、陌生错误 | `matched=False`，返回 `unknown_error` |
| M5-T013 | 错误建议深拷贝 | 修改 suggestions 和 related_layers | 再次查询不受影响 |
| M5-T014 | CNN 概览 | 合法 CNN ModelGraph | 识别为 `CNN`，统计与 flow 正确 |
| M5-T015 | MLP 概览 | 合法 MLP ModelGraph | 识别为 `MLP`，关键层和教学重点非空 |
| M5-T016 | 进阶模型概览 | LSTM、Transformer、VAE、GraphConv 图 | 分别识别为对应模型类型 |
| M5-T017 | Hybrid 概览 | 同时包含 CNN 和 SelfAttention | 识别为 `Hybrid` |
| M5-T018 | 无法排序兜底 | 带环连接的模型图 | 不崩溃，按原顺序返回 flow，并给出提醒 |
| M5-T019 | ModelGraph 异常输入 | None、空字典、非字典、字段类型错误 | `understood=False`，统一兜底 |
| M5-T020 | 模型概览深拷贝 | 修改返回的 summary、flow、counts | 再次调用不受影响 |
| M5-T021 | 轻量依赖 | AST 解析 `backend/teaching.py` | 只使用标准库导入，不依赖 M3/M6/前端/PyTorch |

## 7. 当前覆盖范围

- 层类型：15 种。
- 参数：当前前端、模板和 validator 中实际使用的基础层与进阶层参数。
- 错误类别：16 类真实错误 + `unknown_error`。
- 模型类型：`CNN`、`MLP`、`LSTM`、`Seq2Seq`、`Transformer`、`VAE`、`GNN`、`Hybrid`、`Unknown`。

## 8. 当前限制

- M5 只提供教学说明和建议，不判断模型是否合法。
- 错误建议基于错误文本关键词匹配，不替代 M3 validator。
- 模型图概览只做轻量数据流解释，不做 shape 推导。
- 未接入前端、API、M3、M6，也不影响现有业务行为。
- 对未知层和陌生错误只提供通用排查建议。

## 9. 回归测试命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/M5_teaching/test_code -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall backend/teaching.py tests/M5_teaching/test_code
git diff --check
git status --short
```
