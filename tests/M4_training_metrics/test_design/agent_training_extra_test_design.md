# 本机 Agent、训练取消与模型构建补充测试说明

## 1. 测试目标

在已有《训练与指标模块测试说明》（对应 `test_training_metrics.py`）的基础上，补齐人员 4 职责范围内此前未被覆盖的部分：本机 Agent 的 HTTP 健康检查与设备接口、Agent 客户端对云端指令的分发与回执、训练取消链路（本机 `stop_training_job` 与云端取消中转）、由模型图构建可执行 PyTorch 模型的正确性，以及内置数据集配置与模型输入维度的匹配。目标是验证「设备检测—任务下发—训练执行—取消—结果回传」这一训练闭环中，原设计文档标注为「不测试」的环节也能被自动化用例覆盖。

## 2. 被测模块和负责代码路径

- `local_agent/main.py`：本机 Agent 的 FastAPI 接口 `/health`（`health_check`）、`/devices`（`list_devices`）、`/validate`（`validate_model`）。
- `local_agent/agent_client.py`：云端指令处理 `handle_cloud_command`（`start_training`、`cancel_training`、`ping`、未知指令）、请求-响应类指令 `_handle_agent_request`（`devices`、`validate`、未知 action）、注册消息 `build_agent_hello_message`、进度回传 `send_training_update`。
- `local_agent/runtime/trainer.py`：训练取消状态机 `stop_training_job`，以及数据集准备阶段取消后 `run_training_job` 的收尾；数据集配置 `DATASET_SPECS`、别名解析 `_resolve_dataset_key`、输入转换 `_build_dataset_transform`。
- `local_agent/runtime/model_builder.py`：`build_model` 构建可执行图模型、`create_layer` 按层类型创建 PyTorch 层、`extract_model_summary` 模型结构摘要。
- `backend/cloud_training.py`：取消中转 `cancel_cloud_training_job`、Agent 在线状态查询 `get_agent_status`、进度回传处理 `handle_agent_training_update`（未知任务忽略）。

> 说明：本文件与 `test_training_metrics.py` 互补，不重复其已覆盖的训练配置校验、设备选择、训练执行/状态/结果、训练失败与云端 `/train` 创建、状态、结果中转等用例。原设计文档在「4. 不测试的内容」中列出的 Agent 健康检查/设备接口、WebSocket 指令处理、训练取消与数据集配置，正是本文件补充的范围。WebSocket 握手、真实连接与真实数据集下载仍不在测试范围内，改为直接调用路由处理函数与打桩线程/数据集。

## 3. 测试范围

- Agent HTTP 接口：`/health` 返回状态、服务名与设备摘要；`/devices` 返回展开的设备摘要；`/validate` 对合法/非法模型图分别返回 `valid=True`/`valid=False`。
- Agent 指令处理：`ping` 回 `pong`；未知指令回 `accepted=False`；`start_training` 创建本机任务并登记云端→本机 id 映射，创建失败时回 `accepted=False` 并回传 `failed`；`cancel_training` 记录取消并调用 `stop_training_job`。
- Agent 请求-响应：`devices` 返回设备摘要；`validate` 返回校验结果；未知 action 回 `ok=False`；`hello` 消息含元数据且不含令牌；事件循环未就绪时 `send_training_update` 不抛异常。
- 训练取消：`stop_training_job` 对 pending 任务置取消并转 `cancelling`，对已结束任务为空操作，对不存在任务抛 `ValueError`；数据集准备阶段已取消时训练收尾为 `cancelled` 且无指标。
- 模型构建：CNN/MLP/双向 LSTM/add 分支/concat 分支模型前向输出维度正确；`create_layer` 生成正确的 `Conv2d`/`Linear`/`MaxPool2d`/`Dropout`；Input/Output 端口层不产生模块；`extract_model_summary` 逐层统计参数量。
- 数据集配置：内置数据集规格齐全；名称与别名（大小写、连字符、下划线）解析正确；未知/空名称抛 `ValueError`；CIFAR 使用三通道 `Normalize`、灰度集使用 `ToTensor`；MNIST/CIFAR 输入维度与对应模型匹配。
- 云端取消与状态：无 Agent 时取消直接标记 `cancelled`；越权用户取消返回 404；已结束任务取消为空操作；无 Agent 时 `get_agent_status` 返回 `online=False`；回传未知任务进度被忽略。

## 4. 不测试的内容

- WebSocket 握手、真实长连接、断线自动重连与心跳（`connect_to_cloud_server`、`_heartbeat_loop`）的网络行为。
- 真实数据集（MNIST/CIFAR 等）的下载与磁盘 I/O：数据集相关用例只验证配置、别名与转换，训练相关用例用合成数据打桩 `prepare_dataset`。
- 真实 GPU 上的训练与设备迁移：环境无 CUDA，仅验证设备摘要与选择逻辑。
- 后台训练线程内真实的逐轮训练循环（`_run_and_stream` 的完整流式上报）：Agent 指令用例把线程打桩为不启动真实训练，只验证指令分发与回执。
- 运行时下载/打包、Agent 应用分发（`runtime_manager`、`/agent/download` 等）与 JWT 鉴权细节。

## 5. 测试用例表

| 用例编号 | 测试场景 | 输入数据 | 操作步骤 | 预期结果 | 实际输出结果 | 优先级 |
|---|---|---|---|---|---|---|
| M4-024 | Agent 健康检查 | 无 | 调用 `health_check()` | `status=ok`、服务名正确、设备摘要含 cpu；无 GPU 时默认设备为 cpu | 与预期一致 | 高 |
| M4-025 | Agent 设备列表 | 无 | 调用 `list_devices()` | `status=ok`，展开的设备摘要含 cpu 与 `cuda_available` 布尔字段 | 与预期一致 | 高 |
| M4-026 | 本机校验合法图 | 合法 CNN 图 | 调用 `validate_model()` | `valid=True`，errors 为空 | 与预期一致 | 高 |
| M4-027 | 本机校验非法图 | 缺少 Output 的图 | 调用 `validate_model()` | `valid=False`，errors 非空 | 与预期一致 | 高 |
| M4-028 | ping 指令 | `{"type":"ping"}` | 调用 `handle_cloud_command` | 返回 `pong` | 与预期一致 | 中 |
| M4-029 | 未知指令 | 未知 type | 调用 `handle_cloud_command` | `command_ack` 且 `accepted=False` | 与预期一致 | 中 |
| M4-030 | 下发训练 | start_training + 合法图 | 打桩线程后调用 `handle_cloud_command` | 创建本机任务、登记 id 映射、回执 `accepted=True`、后台线程被启动 | 与预期一致 | 高 |
| M4-031 | 下发训练失败 | start_training + 缺 epochs | 调用 `handle_cloud_command` | 回执 `accepted=False`，并向云端回传一条 `failed` 结果 | 与预期一致 | 高 |
| M4-032 | 取消训练 | 已映射本机任务 | cancel_training 指令 | 记录取消、调用 `stop_training_job(local)`、回执 `accepted=True` | 与预期一致 | 高 |
| M4-033 | 取消未映射任务 | 无本机映射的云端任务 | cancel_training 指令 | 仍回执接受、记录取消、不调用 `stop_training_job` | 与预期一致 | 中 |
| M4-034 | 设备查询请求 | agent_request(devices) | 调用 `handle_cloud_command` | `agent_response` `ok=True`，data 含 cpu | 与预期一致 | 中 |
| M4-035 | 校验请求 | agent_request(validate) | 调用 `handle_cloud_command` | `ok=True`，data.valid 为 True | 与预期一致 | 中 |
| M4-036 | 未知请求 action | agent_request(未知 action) | 调用 `handle_cloud_command` | `ok=False` 且含 error | 与预期一致 | 中 |
| M4-037 | hello 注册消息 | agent_id/token/版本/设备摘要 | 调用 `build_agent_hello_message` | 含 type/agent_id/版本/设备摘要，且不含 token 明文 | 与预期一致 | 中 |
| M4-038 | 取消 pending 任务 | pending 任务 | 调用 `stop_training_job` | `cancelled=True`、状态转 `cancelling`、置 `cancel_requested` | 与预期一致 | 高 |
| M4-039 | 取消已结束任务 | completed 任务 | 调用 `stop_training_job` | `cancelled=False`，状态保持 completed | 与预期一致 | 中 |
| M4-040 | 取消不存在任务 | 不存在的 job_id | 调用 `stop_training_job` | 抛出 `ValueError` | 与预期一致 | 中 |
| M4-041 | 数据准备阶段取消 | 先取消再运行 | 打桩 `prepare_dataset` 后 `run_training_job` | 收尾状态 `cancelled`，无逐轮指标 | 与预期一致 | 高 |
| M4-042 | 构建 CNN 前向 | 合法 CNN 图 | `build_model` 后前向 `[2,1,28,28]` | 输出 `[2,10]` | 与预期一致 | 高 |
| M4-043 | 构建 MLP 前向 | MLP 图 | `build_model` 后前向 `[4,784]` | 输出 `[4,10]` | 与预期一致 | 高 |
| M4-044 | 构建 LSTM 前向 | 双向 LSTM 图 | `build_model` 后前向 `[3,12,8]` | 输出 `[3,4]` | 与预期一致 | 高 |
| M4-045 | add 分支合并 | add 分支图 | `build_model` 后前向 `[5,4]` | 输出 `[5,4]` | 与预期一致 | 高 |
| M4-046 | concat 分支合并 | concat 分支图（3+5=8） | `build_model` 后前向 `[6,4]` | 输出 `[6,2]` | 与预期一致 | 高 |
| M4-047 | 逐层创建 | Conv2D/Linear/Pooling/Dropout 配置 | 调用 `create_layer` | 生成对应 `Conv2d`/`Linear`/`MaxPool2d`/`Dropout` 且参数正确 | 与预期一致 | 高 |
| M4-048 | 端口层无模块 | Input/Output 配置 | 调用 `create_layer` | 返回 None | 与预期一致 | 中 |
| M4-049 | 模型结构摘要 | MLP 模型 | 调用 `extract_model_summary` | 逐层列出、可训练参数量 > 0 | 与预期一致（修复 `.get` 缺陷后） | 中 |
| M4-050 | 内置数据集规格 | 无 | 读取 `DATASET_SPECS` | 含 MNIST/FashionMNIST/CIFAR10 及数据集类 | 与预期一致 | 高 |
| M4-051 | 数据集别名解析 | 各种大小写/连字符/下划线 | 调用 `_resolve_dataset_key` | 均解析到标准 key | 与预期一致 | 高 |
| M4-052 | 未知数据集 | "ImageNet" | 调用 `_resolve_dataset_key` | 抛出 `ValueError` | 与预期一致 | 中 |
| M4-053 | 空数据集名 | "  " | 调用 `_resolve_dataset_key` | 抛出 `ValueError` | 与预期一致 | 中 |
| M4-054 | 数据集转换 | CIFAR10 / MNIST | 调用 `_build_dataset_transform` | CIFAR 含三通道 Normalize；MNIST 为 ToTensor | 与预期一致 | 中 |
| M4-055 | MNIST 维度匹配 | 合法 CNN + `[8,1,28,28]` | `build_model` 后前向 | 输出 `[8,10]` | 与预期一致 | 高 |
| M4-056 | CIFAR 维度匹配 | CIFAR CNN + `[4,3,32,32]` | `build_model` 后前向 | 输出 `[4,10]` | 与预期一致 | 高 |
| M4-057 | 无 Agent 取消 | 无在线 Agent 的任务 | `cancel_cloud_training_job` | `cancelled=True`，云端标记 `cancelled` | 与预期一致 | 高 |
| M4-058 | 越权取消 | 他人 user_id | `cancel_cloud_training_job` | 返回 HTTP 404 | 与预期一致 | 中 |
| M4-059 | 取消已结束任务 | completed 任务 | `cancel_cloud_training_job` | `cancelled=False`，保持 completed | 与预期一致 | 中 |
| M4-060 | Agent 离线状态 | 无在线 Agent | `get_agent_status` | `online=False` | 与预期一致 | 中 |
| M4-061 | 回传未知任务 | 不存在 job_id 的进度 | `handle_agent_training_update` | `accepted=False`、`status=ignored` | 与预期一致 | 中 |

## 6. 预期结果

- Agent HTTP 接口在无 GPU 环境下应返回一致的设备摘要（含 cpu、默认 cpu），并正确区分合法/非法模型图。
- Agent 指令处理应对每类指令返回结构固定的回执：训练下发成功登记 id 映射、失败回传 failed；取消无论是否已映射本机任务都回接受；请求-响应类正确返回数据或错误；hello 不泄露令牌。
- 训练取消应遵循状态机：仅对进行中/等待中的任务生效并转入取消态，对已结束任务空操作，对不存在任务抛错；数据准备阶段取消不产生指标。
- 由模型图构建的模型对 CNN、MLP、序列、分支（add/concat）均能前向跑通并输出预期维度；`create_layer` 生成正确的层与参数；结构摘要能统计参数量。
- 数据集配置与别名解析稳定，转换与输入维度和模型匹配；异常名称给出明确错误。
- 云端取消中转在有/无 Agent、越权、已结束等情形下返回既定字段；在线状态与未知任务回传处理正确。

## 7. 异常情况考虑

- 取消不存在任务（本机侧抛 `ValueError`）与越权取消（云端侧返回 404），保证不泄露他人任务信息。
- `create_training_job` 因非法配置抛错时，Agent 仍应回执 `accepted=False` 并向云端回传 failed，而非静默失败。
- 事件循环未就绪时 `send_training_update` 必须安全返回，避免后台线程崩溃。
- `extract_model_summary` 原实现对 `nn.ModuleDict` 误用 `.get()` 会抛 `AttributeError`；测试发现后已改为按键存在性访问（见第 8 节）。
- 数据集名称为空或不受支持时抛 `ValueError`，避免在训练中途才失败。
- 所有用例通过打桩 `prepare_dataset`、后台线程与直接调用路由/接口函数，保证可重复、不触网、不依赖 GPU 与 WebSocket。

## 8. 运行方式

测试基于 Python 标准库 `unittest`。在项目根目录 `softwareProject/` 下执行：

```
python -m unittest tests.M4_training_metrics.test_code.test_agent_training_extra -v
```

与原有 M4 用例一起运行：

```
python -m unittest tests.M4_training_metrics.test_code.test_training_metrics tests.M4_training_metrics.test_code.test_agent_training_extra -v
```

依赖：`torch`、`torchvision`、`fastapi`、`websockets`、`python-jose`（`backend.security` 需要）。Agent HTTP 用例直接调用 `local_agent/main.py` 的路由处理函数；云端用例直接调用 `backend/cloud_training.py` 的接口函数（异步接口用 `asyncio.run` 调用），均不依赖 `TestClient`/`httpx`，也不建立真实 WebSocket 连接。

> 缺陷修复记录：测试 M4-049 暴露 `local_agent/runtime/model_builder.py` 中 `extract_model_summary` 对 `nn.ModuleDict` 调用了不存在的 `.get()` 方法，导致该函数一经调用即抛 `AttributeError`。已改为先判断键是否存在再索引（`modules_by_id[layer_id] if layer_id in modules_by_id else None`），修复后 M4-049 通过。
