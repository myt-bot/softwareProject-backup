# 代码导出模块测试说明

## 1. 测试目标

验证 `local_agent/runtime/code_exporter.py` 能够根据前端模型 JSON 生成可运行的 PyTorch Python 文件或 Jupyter Notebook 文件；同时验证导出结果会包含 JSON 中的训练配置和数据集信息，并能生成数据集加载、训练与评估代码。导出前会复用结构校验逻辑，非法模型不能正常导出代码。

## 2. 被测模块和负责代码路径

- `local_agent/runtime/code_exporter.py`
- `local_agent/agent_client.py` 中 `agent_request/export` 分发逻辑
- `frontend/src/actions.ts` 中导出请求参数与下载文件名处理
- `frontend/src/components/ExportModal.vue` 中导出格式选择界面

## 3. 测试范围

- Python 源码导出：生成 `nn.Module` 类、`__init__` 层定义、`forward` 方法和最小运行入口。
- 数据集与训练配置导出：从模型 JSON 的 `train_config` 或导出 payload 中读取 `dataset_name`、`epochs`、`batch_size`、`rate`、`device`、`loss_fn`、`optimizer` 等字段。
- Python 源码训练能力：生成 `TRAIN_CONFIG`、`DATASET_SPECS`、`prepare_dataloaders`、`train_one_epoch`、`evaluate`、`run_training` 和 `--train` 命令行入口。
- 真实数据集维度适配：DataLoader transform 会根据模型 JSON 的 `Input.shape` 自动处理图像 Resize、通道数转换、Flatten 或二维 reshape。
- Notebook 导出：生成符合 Jupyter Notebook v4 结构的 `.ipynb` JSON，并按教学阅读顺序拆分为多个 markdown/code cell，包含数据集配置、数据集加载和训练入口章节。
- 多类型合法模型导出：CNN、MLP、LSTM、Add 分支模型、Concat 分支模型。
- 导出格式分发：`py` 返回 Python 源码，`ipynb` 返回 Notebook JSON，不支持的格式返回明确错误。
- 前端导出契约：导出弹窗提供 `.py` 和 `.ipynb` 选择，导出请求携带当前模型图、导出格式和训练配置。
- 生成代码执行：将导出的 `.py` 文件写入 `test_result` 目录，并通过 Python 子进程实际运行。
- 非法模型拒绝导出：缺少 `Output`、连接断裂、`Linear in_features` 维度不匹配。

## 4. 不测试的内容

- 前端浏览器真实点击、弹窗渲染和下载行为。
- 本机 Agent 与云端 WebSocket 的真实网络传输。
- 模型训练、反向传播、优化器和数据集加载。
- Jupyter 前端打开 Notebook 后的交互体验。
- 未在当前 validator/model_builder 中支持的层类型。

## 5. 测试用例表

| 用例编号 | 测试场景 | 输入数据 | 操作步骤 | 预期结果 | 实际输出结果 | 优先级 |
|---|---|---|---|---|---|---|
| M6-001 | CNN 模型导出 Python 并运行 | `Input -> Conv2D -> ReLU -> Pooling -> Flatten -> Linear -> Output`，输入 `[1,28,28]`，JSON 中包含 `train_config.dataset_name=MNIST` | 调用 `export_to_pytorch`，写入 `test_result/M6CnnModel.py`，执行生成文件 | 生成代码包含 `Conv2d`、`Linear(in_features=1568)`、`TRAIN_CONFIG`、`prepare_dataloaders`、`run_training` 和 `--train` 入口；运行输出 dataset 为 MNIST，shape 为 `(1, 10)` | 与预期一致：生成文件可运行，输出 dataset 和 `(1, 10)` | 高 |
| M6-002 | MLP 模型导出 Python 并运行 | `Input([784]) -> Linear -> ReLU -> Dropout -> Linear -> Output` | 调用 `export_to_pytorch`，写入 `test_result/M6MlpModel.py`，执行生成文件 | 生成代码包含 `Dropout(p=0.25)` 和全连接层，运行输出 shape 为 `(1, 10)` | 与预期一致：生成文件可运行，输出 `(1, 10)` | 高 |
| M6-003 | LSTM 模型导出 Python 并运行 | `Input([12,8]) -> LSTM(bidirectional=True) -> Linear -> Output` | 调用 `export_to_pytorch`，写入 `test_result/M6LstmModel.py`，执行生成文件 | 生成代码包含 `LSTMLayer`，双向 LSTM 输出维度进入 `Linear(in_features=32)`，运行输出 `(1, 4)` | 与预期一致：生成文件可运行，输出 `(1, 4)` | 高 |
| M6-004 | Add 分支模型导出 Python 并运行 | 一个输入分成左右两个 `Linear(out=4)`，在 `ReLU(params.merge="add")` 合并后输出 | 调用 `export_to_pytorch`，写入 `test_result/M6AddBranchModel.py`，执行生成文件 | `forward` 中生成逐元素相加逻辑，运行输出 shape 为 `(1, 4)` | 与预期一致：生成文件可运行，输出 `(1, 4)` | 高 |
| M6-005 | Notebook 导出 | 合法 CNN 模型图，JSON 中包含 MNIST 训练配置 | 调用 `export_model_code(..., "ipynb")`，写入 `test_result/M6NotebookModel.ipynb`，解析 JSON，并顺序执行所有 code cell | Notebook `nbformat=4`；包含多个 markdown/code cell；最大级标题为模型名；包含“依赖导入、数据集与训练配置、数据集加载、模型主体、结构与维度总览、训练与评估函数、逐层模块说明、前向传播试运行、使用真实数据集训练”等分区；每个模块说明包含“功能”和“维度”小标题；所有 code cell 可顺序执行 | 与预期一致：`.ipynb` 可解析、结构分层完整、代码块可执行 | 高 |
| M6-006 | 不同架构 Notebook 导出成功 | CIFAR10 + MLP，`Input([3072]) -> Linear -> ReLU -> Linear -> Output` | 调用 `export_model_code(..., "ipynb")`，写入 `test_result/M6CifarMlpNotebook.ipynb`，顺序执行 code cell，并对 CIFAR PIL 样本执行导出的 transform | Notebook 可执行；生成 MLP 模型；`build_dataset_transform("CIFAR10", MODEL_INPUTS)` 将 RGB 32x32 图像转为 shape `[3072]` | 与预期一致：不同架构 Notebook 成功，transform 输出 `(3072,)`，模型输出 `(1,10)` | 高 |
| M6-007 | CIFAR 图像适配灰度 CNN 输入 | CIFAR10 数据集配置，模型输入为 `[1,28,28]` | 导出 Python，执行其中的 `build_dataset_transform("CIFAR10", MODEL_INPUTS)`，对 RGB 32x32 图像做转换 | transform 自动执行 Resize 和通道转换，输出 tensor shape 为 `[1,28,28]` | 与预期一致：输出 `(1,28,28)`，避免真实数据集维度不匹配 | 高 |
| M6-008 | 缺少 Output 的模型不能导出 | CNN 模型移除 `Output` 节点和末端连接 | 调用 `export_to_pytorch` | 抛出 `ValueError`，错误包含“模型缺少必要节点: Output” | 与预期一致：导出被阻止 | 高 |
| M6-009 | 连接断裂的模型不能导出 | 末端连接指向不存在的 `missing_output` | 调用 `export_to_pytorch` | 抛出 `ValueError`，错误包含“连接终点不存在: missing_output” | 与预期一致：导出被阻止 | 高 |
| M6-010 | Linear 维度不匹配的模型不能导出 | `Input([1,28,28]) -> Linear(in_features=10,out_features=3) -> Output` | 调用 `export_to_pytorch` | 抛出 `ValueError`，错误包含“Linear 输入维度与 in_features 不匹配” | 与预期一致：导出被阻止 | 高 |
| M6-011 | Concat 分支模型导出 Python 并运行 | 一个输入分成左右两个 `Linear(out=3/5)`，在 `ReLU(params.merge="concat", dim=1)` 合并后接 `Linear(out=2)` | 调用 `export_to_pytorch`，写入 `test_result/M6ConcatBranchModel.py`，执行生成文件 | `forward` 中生成 `torch.cat(..., dim=1)`；合并后 `Linear(in_features=8,out_features=2)`；运行输出 shape 为 `(1, 2)` | 与预期一致：生成文件可运行，输出 `(1, 2)` | 高 |
| M6-012 | Python 格式分发 | 合法 CNN 模型图，导出格式 `py` | 调用 `export_model_code(..., "py")` | 返回 Python 源码字符串，包含模型类和 `TRAIN_CONFIG`，不包含 Notebook `nbformat` 字段 | 与预期一致：返回 Python 源码 | 中 |
| M6-013 | 不支持格式拒绝导出 | 合法 CNN 模型图，导出格式 `markdown` | 调用 `export_model_code(..., "markdown")` | 抛出 `ValueError`，错误包含“不支持的导出格式: markdown” | 与预期一致：非法格式被拒绝 | 中 |
| M6-014 | 显式训练配置覆盖图内配置 | CNN 图内包含 MNIST 配置，调用导出时显式传入 CIFAR100、epochs、batch_size、学习率、设备、损失函数、优化器和路径配置 | 调用 `export_model_code(..., "py", train_config=...)` | 导出的 `TRAIN_CONFIG` 使用显式配置，包含数据集、batch size、epoch、学习率、优化器、损失函数、数据目录和产物目录 | 与预期一致：显式训练配置写入导出源码 | 高 |
| M6-015 | 前端导出弹窗与请求契约 | `ExportModal.vue` 和 `actions.ts` 源码 | 静态读取前端源码，检查格式切换按钮、下载文案、Agent 导出请求 payload 和下载 MIME 类型 | 前端提供 `.py`/`.ipynb` 选择；请求携带 `model`、`class_name`、`format`、`train_config`；下载时按格式设置文件类型和文件名 | 与预期一致：前端导出交互契约完整 | 中 |

## 6. 预期结果

- 合法模型应生成完整、可读、可运行的 PyTorch 代码。
- 导出代码应包含模型 JSON 中的数据集和训练配置，不能只导出模型空壳。
- 导出的 Python 文件应包含 torchvision 数据集加载逻辑，以及可通过 `--train` 启动真实数据集训练的入口。
- 导出的 DataLoader transform 应以模型 JSON 的输入维度为准，对真实数据集样本做必要的 Resize、灰度/RGB 通道转换、Flatten 或二维 reshape。
- 生成的 Python 文件应写入 `tests/M6_code_export/test_code/test_result`，并可由 Python 子进程直接运行。
- 导出的 Python 源码应包含模型类、必要辅助层、`forward` 方法和最小 smoke test 入口。
- 导出的 Notebook 应是合法 JSON，符合 Jupyter Notebook v4 基本结构，并按功能拆分代码块，包含数据集配置、DataLoader、训练/评估和真实数据集训练入口。
- Notebook 顶部应使用模型名作为最大级标题；各功能区和逐层模块应有 markdown 说明，模块说明中应包含“功能”和“维度”等小标题。
- Notebook 除模型类代码外，还应包含结构/维度概览和逐层解释代码，帮助用户理解输入输出维度和关键参数。
- 非法模型在导出前应被结构校验拦截，并返回可读错误；不能静默生成错误代码。

## 7. 异常情况考虑

- 缺少必要节点时，导出应失败，避免生成无法调用的模型类。
- 连接指向不存在节点时，导出应失败，避免生成错误的 `forward` 数据流。
- 维度推导失败或 `Linear in_features` 与实际输入不一致时，导出应失败。
- 多分支合并应按 `params.merge` 生成对应代码；`add` 要生成逐元素相加逻辑，`concat` 要生成 `torch.cat`，并通过运行生成文件验证输出 shape。
- 前端导出弹窗和动作代码应保持 `.py`、`.ipynb` 两种格式选择，并把训练配置随导出请求发送给本机 Agent。
- Notebook 导出不只检查字符串存在，还要验证整体 JSON 可解析。
- 数据集默认维度与模型输入维度不一致时，不能直接把原始数据喂给模型；应由导出代码自动适配，或在无法适配时给出明确错误。
- 生成文件运行失败时，测试应暴露标准输出和错误输出，便于定位导出代码问题。

## 8. 成员五测试计划覆盖矩阵

| 测试计划编号 | 对应自动化/文档用例 | 当前覆盖方式 | 最近执行结果 |
|---|---|---|---|
| TC5-01 CNN 模型 Python 导出 | M6-001 | 导出 `.py`，检查 Conv2D/Linear/训练入口并运行生成文件 | 通过 |
| TC5-02 MLP 模型 Python 导出 | M6-002 | 导出 `.py`，检查 Dropout/Linear 并运行生成文件 | 通过 |
| TC5-03 分支模型导出 | M6-004、M6-011 | 分别验证 add 分支和 concat 分支导出代码及运行输出 | 通过 |
| TC5-04 导出代码运行验证 | M6-001、M6-002、M6-003、M6-004、M6-011 | 使用 Python 子进程运行生成文件并检查输出 shape | 通过 |
| TC5-05 Notebook 导出 | M6-005、M6-006 | 解析 Notebook JSON，检查 `nbformat=4`，顺序执行 code cell | 通过 |
| TC5-06 训练配置导出 | M6-001、M6-005、M6-014 | 检查 `TRAIN_CONFIG`、DataLoader、训练/评估函数，以及显式配置覆盖 | 通过 |
| TC5-07 非法模型拒绝导出 | M6-008 | 缺少 Output 时抛出可读错误 | 通过 |
| TC5-08 连接断裂模型拒绝导出 | M6-009 | 连接指向不存在节点时抛出可读错误 | 通过 |
| TC5-09 维度不匹配模型拒绝导出 | M6-010 | Linear 输入维度不匹配时抛出可读错误 | 通过 |
| TC5-10 模板列表完整性 | M7-001、M7-016 | 单元测试和接口测试均检查 11 个模板 | 通过 |
| TC5-11 模板合法性验证 | M7-002、M7-018、M7-020、M7-024 | 对模板生成图和接口/项目链路中的模型图执行结构校验 | 通过 |
| TC5-12 模板别名验证 | M7-003 | 检查 `linear`、`cnn`、`transformer`、`self_attention`、`gcn` 别名 | 通过 |
| TC5-13 未知模板处理 | M7-004、M7-019、M7-022 | 未知模板函数调用、详情接口、创建项目接口均返回错误 | 通过 |
| TC5-14 基于模板创建项目 | M7-020、M7-021、M7-024 | 创建模板项目、默认名称描述、项目列表回查和结构校验 | 通过 |
| TC5-15 前端导出弹窗交互 | M6-015 | 静态检查 `.py`/`.ipynb` 控件、导出请求 payload、下载 MIME 类型和文件名处理 | 通过 |
