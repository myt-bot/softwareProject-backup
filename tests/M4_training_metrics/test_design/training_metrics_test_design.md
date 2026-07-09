# 训练与指标模块测试说明

## 1. 测试目标

验证训练模块能否按前端提交的模型图与训练配置，正确完成训练配置校验、CPU/GPU 设备选择、训练任务创建、训练执行、状态查询、结果查询，以及 loss/accuracy 指标的返回格式；同时验证云端 `/train` 中转接口在有/无本机 Agent 时的任务登记与进度中转行为，并确认结构非法（未通过 Validate）的模型图无法正常训练。

## 2. 被测模块和负责代码路径

- `local_agent/runtime/trainer.py`（对应任务分工中的 `backend/trainer.py`）：训练任务创建、执行、状态/结果查询、训练配置驱动的损失函数与优化器构建、数据准备、逐轮训练与评估、产物保存。
- `local_agent/runtime/model_builder.py`（对应 `backend/model_builder.py`）：由模型图构建可执行 PyTorch 模型，供训练使用。
- `local_agent/runtime/device.py`：CPU/GPU 设备检测与选择（`get_available_devices`、`is_cuda_available`、`resolve_device`）。
- `local_agent/runtime/schemas.py`：训练配置 `TrainConfig` 的字段校验（`check_*`）。
- `local_agent/runtime/validator.py`：模型结构校验（用于验证「未通过 Validate 不允许训练」）。
- `backend/cloud_training.py` 中 `/train`、`/train/{job_id}/status`、`/train/{job_id}/result` 接口（由 `backend/main.py` 通过 `include_router` 挂载）：云端训练任务登记、状态查询与结果查询中转。

> 说明：任务分工中写的 `backend/trainer.py`、`backend/model_builder.py` 在当前代码库中实际位于 `local_agent/runtime/` 下（云端只做中转，真实 PyTorch 训练在本机 Agent 运行时执行）；`/train` 系列接口是 `backend/cloud_training.py` 中的云端中转接口。前端训练面板逻辑实际在 `frontend/src/actions.ts`、`monitor.ts`、`store.ts` 中（Vue + TypeScript），非 `app.js`，属于前端交互，不在本单元测试范围内。

## 3. 测试范围

- 训练配置合法：默认合法配置通过 `TrainConfig.check_all()`。
- 训练配置非法：`epochs`/`batch_size` 非正、`rate` 非正、`dataset_name`/`device`/`loss_fn`/`optimizer` 为空字符串。
- CPU/GPU 选择：可用设备列表、`resolve_device` 对 `cpu`/`cuda`/`gpu`/`auto`/`None` 的处理与无 GPU 回退。
- 训练任务创建：`create_training_job` 登记为 `pending` 并返回 `job_id`。
- 训练执行与状态查询：训练完成后状态、逐轮 metrics、进度百分比与状态字段。
- 训练完成：结果查询返回最终 loss/accuracy、设备、产物路径，产物写入磁盘。
- 训练失败：训练过程中抛出异常时任务标记为 `failed` 并记录错误信息。
- loss/accuracy 返回格式：train/eval 每轮均含 float 的 loss 与 accuracy，最终结果为 float。
- 未通过 Validate 不允许训练：非法模型图 `valid=False`；直接用非法模型图训练会导致训练失败。
- 云端 `/train` 中转接口：无 Agent 时返回 `no_agent`/`offline`；状态/结果查询字段；越权用户查询返回 404；Agent 回传进度后状态与结果的更新。

## 4. 不测试的内容

- 前端画布交互、训练面板渲染与 WebSocket 实时曲线绘制。
- 真实数据集（MNIST 等）的下载与磁盘 I/O：测试中用合成 TensorDataset 替换 `prepare_dataset`，避免依赖数据集下载。
- 真实 GPU 上的训练：环境无 CUDA，GPU 分支通过打桩 `is_cuda_available` 验证选择逻辑。
- JWT 鉴权、WebSocket 握手与 Agent 下发/连接细节。
- 训练取消（`/cancel`、`stop_training_job`）的完整流程，仅涉及状态机的必要部分。
- 代码导出、模板、用户/项目管理等其它模块。

## 5. 测试用例表

| 用例编号 | 测试场景 | 输入数据 | 操作步骤 | 预期结果 | 实际输出结果 | 优先级 |
|---|---|---|---|---|---|---|
| M4-001 | 训练配置合法 | 默认 `TrainConfig()` | 调用 `check_all()` | 返回空列表，无错误 | 与预期一致：返回 `[]` | 高 |
| M4-002 | epochs/batch_size 非正 | `epochs=0`、`batch_size=-1` | 调用 `check_all()` | 错误包含 “epochs 必须是正整数”“batch_size 必须是正整数” | 与预期一致 | 高 |
| M4-003 | 学习率非正 | `rate=0` | 调用 `check_all()` | 错误包含 “rate 必须是正数” | 与预期一致 | 高 |
| M4-004 | 字符串字段为空 | `dataset_name`/`device`/`loss_fn`/`optimizer` 置空 | 调用 `check_all()` | 每个空字段均产生对应“必须是非空字符串”错误 | 与预期一致 | 中 |
| M4-005 | 可用设备列表 | 无 | 调用 `get_available_devices()` | 恒包含 `cpu`；CUDA 可用时含 `cuda` | 与预期一致：含 `cpu` | 高 |
| M4-006 | 选择 CPU | `resolve_device("cpu")` | 调用 `resolve_device` | 返回 `torch.device("cpu")` | 与预期一致 | 高 |
| M4-007 | GPU/auto 回退 | 打桩 `is_cuda_available` 为 True/False，`device` 取 cuda/gpu/auto | 调用 `resolve_device` | 无 CUDA 时均回退 CPU；有 CUDA 时返回 cuda | 与预期一致 | 高 |
| M4-008 | 未指定设备默认 CPU | `resolve_device(None)` | 调用 `resolve_device` | 返回 `cpu` | 与预期一致 | 中 |
| M4-009 | 训练任务创建 | 合法模型图 + `epochs=2` | 调用 `create_training_job` | 返回含 `job_id`，状态为 `pending`，`total_epochs=2`，任务登记入 `TRANING_JOBS` | 与预期一致 | 高 |
| M4-010 | 训练完成并记录逐轮指标 | 合成数据 + `epochs=2` | 打桩 `prepare_dataset` 后 `run_training_job` | 状态 `completed`，`metrics` 长度等于 epochs，每轮含 `train`/`eval` | 与预期一致 | 高 |
| M4-011 | 完成后状态查询 | 已完成任务 | 调用 `get_job_status` | 含 `job_id`/`status`/`current_epoch`/`total_epochs`/`progress`/`metrics` 等字段，`progress=1.0` | 与预期一致 | 高 |
| M4-012 | loss/accuracy 返回格式 | 已完成任务 | 调用 `get_job_result` | 最终 `loss`/`accuracy` 为 float；每轮 train/eval 的 loss/accuracy 均为 float | 与预期一致 | 高 |
| M4-013 | 训练产物写入磁盘 | 指定临时 `artifacts_dir` | 训练完成后检查产物 | 生成 `model.pt` 与 `metrics.json`，结果含 `artifacts` 路径 | 与预期一致 | 中 |
| M4-014 | 查询不存在的任务 | 不存在的 `job_id` | 调用 `get_job_status` | 抛出 `ValueError` | 与预期一致 | 中 |
| M4-015 | 训练失败记录错误 | 打桩 `prepare_dataset` 抛异常 | 调用 `run_training_job` | 抛出异常；任务状态 `failed`，`error` 被记录 | 与预期一致 | 高 |
| M4-016 | 结构非法模型图校验 | 缺少 Output 的模型图 | 调用 `validate_model_graph` | `valid=False`，含缺少必要节点错误 | 与预期一致 | 高 |
| M4-017 | 结构合法模型图校验 | 合法 CNN 模型图 | 调用 `validate_model_graph` | `valid=True`，可进入训练 | 与预期一致 | 高 |
| M4-018 | 未通过 Validate 不允许训练 | 未校验的非法模型图直接训练 | `create_training_job` + `run_training_job` | 构建模型失败导致训练 `failed`（说明必须先通过校验） | 与预期一致 | 高 |
| M4-019 | 无 Agent 时创建任务 | `/train` 无在线 Agent | `POST /train?user_id=...` | 返回 `job_status=no_agent`、`agent_status=offline`，任务登记 | 与预期一致 | 高 |
| M4-020 | 状态查询字段 | 已登记任务 | `GET /train/{job_id}/status` | 返回 `job_id`/`status`/`current_epoch`/`total_epochs`/`progress`/`metrics` 等字段 | 与预期一致 | 高 |
| M4-021 | 越权用户查询状态 | 用他人 `user_id` 查询 | `GET /train/{job_id}/status` | 返回 HTTP 404 | 与预期一致 | 中 |
| M4-022 | 完成前结果查询 | 尚未回传结果的任务 | `GET /train/{job_id}/result` | `loss`/`accuracy` 为 None | 与预期一致 | 中 |
| M4-023 | Agent 回传进度中转 | 模拟 `training_result` 回传 | `handle_agent_training_update` 后查询 status/result | 状态更新，result 反映回传的 loss/accuracy/device | 与预期一致 | 高 |

## 6. 预期结果

- 合法训练配置应无任何校验错误；非法配置应返回可读的中文错误信息，并覆盖 epochs、batch_size、rate 及各字符串字段。
- 设备选择：`get_available_devices` 恒含 cpu；`resolve_device` 在无 CUDA 时对 cuda/gpu/auto 一律回退 cpu，在有 CUDA 时对 cuda/gpu/auto 选择 cuda，未指定或 cpu 时用 cpu。
- 训练任务创建后立即登记为 pending 并返回可用 `job_id`。
- 训练完成后状态为 completed，逐轮 metrics 数量与 epochs 一致，进度为 1.0，各字段齐全。
- 结果查询返回的 loss、accuracy 为浮点数；每轮 train/eval 均含 float 的 loss 与 accuracy；产物写入磁盘并返回路径。
- 训练执行过程中出现异常时，任务状态置为 failed 且记录错误信息，而不是静默成功。
- 结构非法的模型图在校验阶段返回 `valid=False`；若跳过校验直接训练，构建模型会失败并使任务进入 failed，从而保证「未通过 Validate 不允许训练」。
- 云端 `/train` 接口在无 Agent 时返回 no_agent/offline 并仍登记任务；状态/结果查询返回既定字段；越权用户查询返回 404；Agent 回传结果后状态与最终指标被正确中转。

## 7. 异常情况考虑

- 查询不存在的 `job_id` 时应抛出 `ValueError`（本机训练侧）或返回 404（云端中转侧）。
- 数据准备或模型构建失败时，应捕获异常、标记任务 failed 并保留错误信息，避免污染其它任务状态。
- 无 GPU 环境下请求 cuda/gpu 不应报错，而应安全回退到 CPU。
- 训练配置字段类型错误或取值越界时，应返回明确的字段级错误，而非在训练中途崩溃。
- 云端接口在任务归属用户不匹配时不得泄露任务信息，应统一返回 404。
- 测试通过打桩 `prepare_dataset`（合成数据）与 `is_cuda_available` 保证可重复、不依赖真实数据集下载与 GPU 硬件。

## 8. 运行方式

测试基于 Python 标准库 `unittest`（环境未安装 pytest）。在项目根目录 `softwareProject/` 下执行：

```
python -m unittest tests.M4_training_metrics.test_code.test_training_metrics -v
```

依赖：`torch`、`torchvision`、`fastapi`、`python-jose`（`backend.security` 需要）。云端接口用例 `CloudTrainingApiTests` 直接调用 `backend/cloud_training.py` 中的接口函数（`create_cloud_training_job`、`get_cloud_training_status`、`get_cloud_training_result`、`handle_agent_training_update`），并只单独导入 `backend.cloud_training` 与 `backend.schemas`，从而绕开 `backend.main` 中 `sqlalchemy` 等未安装依赖，也无需 `httpx`/`TestClient`。异步接口通过 `asyncio.run` 调用。
