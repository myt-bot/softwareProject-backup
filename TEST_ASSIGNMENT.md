# 六人测试分配方案

## 1. 系统概况

当前系统是一个 AI 赋能可视化深度学习模型构建平台，整体由三部分组成：

- 前端：Vue 3 + TypeScript + Vite，负责模型画布、参数编辑、项目操作、训练监控和导出交互。
- 云端后端：FastAPI，负责用户认证、项目管理、模板接口、结构校验、训练任务调度和 Agent 连接管理。
- 本机 Agent：Python + PyTorch，负责设备检测、模型构建、本地训练、训练进度回传和 PyTorch 代码导出。

结合现有代码和 `tests/` 目录，系统已有测试模块主要包括：

- M1：用户与项目管理
- M2：前端模型编辑器
- M3：结构校验与维度推导
- M6：代码导出
- M7：模型模板与文档

本次建议按功能边界、风险程度和端到端链路进行六人分工。

## 2. 六人测试分配

| 人员 | 负责模块 | 主要代码路径 | 测试重点 |
| --- | --- | --- | --- |
| 人员 1 | 用户、认证、项目管理 | `backend/auth.py`、`backend/security.py`、`backend/projects.py`、`backend/storage.py`、`backend/main.py` | 注册、登录、JWT、权限控制、用户 CRUD、项目 CRUD、同用户项目重名、跨用户越权、数据库约束 |
| 人员 2 | 前端模型编辑器 | `frontend/src/store.ts`、`frontend/src/canvas.ts`、`frontend/src/components/`、`frontend/src/styles.css` | 节点增删、拖拽、连线、删除连接、参数编辑、非法输入、ModelGraph 导出、右键菜单、画布缩放、多画布标签 |
| 人员 3 | 结构校验与维度推导 | `local_agent/runtime/validator.py`、`local_agent/runtime/graph_utils.py`、`local_agent/runtime/schemas.py`、`backend/main.py` | 缺少 Input/Output、孤立节点、断裂连接、循环连接、Conv2D/Pooling/Flatten/Linear 维度推导、add/concat 分支合并、非法参数 |
| 人员 4 | 本机 Agent、训练与设备 | `local_agent/main.py`、`local_agent/agent_client.py`、`local_agent/runtime/trainer.py`、`local_agent/runtime/model_builder.py`、`local_agent/runtime/device.py`、`backend/cloud_training.py` | CPU/GPU 检测、训练任务下发、WebSocket 连接、训练进度回传、取消训练、MNIST/CIFAR 数据集、模型构建正确性 |
| 人员 5 | 代码导出与模型模板 | `local_agent/runtime/code_exporter.py`、`backend/templates.py`、`frontend/src/components/ExportModal.vue`、`frontend/src/actions.ts` | Python 导出、Notebook 导出、导出代码可运行、非法模型拒绝导出、11 个内置模板合法性、模板创建项目链路 |
| 人员 6 | 系统集成、部署与回归 | `README.md`、`backend/env.py`、整体前后端接口、Nginx 配置、uvicorn 启动配置、SQLite 数据库文件 | 前端-后端-Agent 端到端流程、Nginx 反向代理、SQLite 数据持久化、uvicorn 服务运行、CORS、端口冲突、生产配置、冒烟测试、全量回归测试 |

## 3. 各人员详细测试任务

### 人员 1：用户、认证、项目管理

主要验证系统基础数据能力是否稳定。

重点测试内容：

- 用户注册成功、重复邮箱注册失败、弱密码失败、两次密码不一致失败。
- 登录成功、密码错误、邮箱未注册、无效 Token、缺少 Token。
- 用户信息查询、修改、删除。
- 项目创建、查询、更新、删除。
- 同一用户下项目名不可重复，不同用户可使用相同项目名。
- 非项目所有者不能修改或删除项目。
- 数据库存储层约束是否生效，包括唯一键、外键和级联删除。

建议运行：

```bash
python -m pytest tests/M1_user_project/test_code/ -q
```

### 人员 2：前端模型编辑器

主要验证用户在浏览器中能否稳定搭建模型图。

重点测试内容：

- 添加 Input、Conv2D、Pooling、Flatten、Linear、Dropout、Output 等节点。
- 删除节点时同步删除相关连接。
- 建立连接、删除连接、拒绝自连接和重复连接。
- 修改 Input shape、Conv2D 参数、Pooling 参数、Linear 参数、Dropout 参数。
- 参数为空、非法数字、非法 shape 时页面不崩溃并给出提示。
- 当前画布能正确导出为 `{ layers, connections }` 结构。
- Validate、Export、Train 按钮状态和接口调用行为正确。
- 浏览器手动验证拖拽、右键菜单、缩放和提示信息。

建议运行：

```bash
node tests/M2_model_editor/test_code/test_model_editor.js
```

### 人员 3：结构校验与维度推导

主要验证模型图在训练或导出前能被正确检查。

重点测试内容：

- 合法 CNN、MLP、分支模型能通过校验。
- 缺少 Input、缺少 Output、孤立节点、断裂连接、循环连接能被识别。
- Conv2D、Pooling、Flatten、Linear 的输出维度推导正确。
- Linear 输入维度不匹配时能给出明确错误。
- 多输入 add 合并要求 shape 完全一致。
- 多输入 concat 合并要求非拼接维度一致。
- `/validate` 接口响应格式稳定，业务失败返回 `valid=false`。

建议运行：

```bash
python -m pytest tests/M3_validator_shape/test_code/ -q
```

### 人员 4：本机 Agent、训练与设备

主要验证系统最关键的训练闭环。

重点测试内容：

- 本机 Agent 健康检查和设备列表接口。
- CPU 可用时能正常选择 CPU 训练。
- 有 CUDA 环境时能识别 GPU；无 GPU 时能降级或提示。
- 云端后端能识别 Agent 在线状态。
- 前端发起训练后，云端能创建训练任务并下发给 Agent。
- Agent 能构建模型、启动训练、回传 loss/accuracy/epoch 进度。
- 训练取消、训练失败、Agent 断连时状态处理正确。
- MNIST、FashionMNIST、CIFAR10 等数据集配置与模型输入维度匹配。

建议进行手工和集成测试：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
python local_agent/launcher.py --server http://127.0.0.1:8000 --token <JWT>
```

### 人员 5：代码导出与模型模板

主要验证模型能否导出为可学习、可运行的 PyTorch 代码。

重点测试内容：

- CNN、MLP、LSTM、分支模型可以导出 Python 文件。
- 导出的 `.py` 文件可以直接运行，输出 shape 正确。
- Notebook 导出符合 Jupyter Notebook v4 结构。
- 导出代码包含训练配置、数据集配置、DataLoader、训练与评估函数。
- 非法模型不能导出，错误信息可读。
- 11 个内置模板均能生成合法 ModelGraph。
- 模板别名可用，未知模板返回错误。
- 基于模板创建项目后，项目保存和查询链路正确。

建议运行：

```bash
python -m pytest tests/M6_code_export/test_code/ -q
python -m unittest tests/M7_templates_docs/test_code/test_templates_unit.py tests/M7_templates_docs/test_code/test_templates_integration.py
```

### 人员 6：系统集成、部署与回归

主要验证系统整体可交付性。

重点测试内容：

- 前端、后端、本机 Agent 三端能同时启动并完成完整业务流程。
- 注册登录、创建项目、搭建模型、结构校验、启动训练、查看监控、导出代码的端到端链路。
- `npm run build` 构建通过。
- Nginx 能正确托管前端静态文件，并将 API 与 WebSocket 请求反向代理到 uvicorn。
- uvicorn 后端服务能在生产配置下稳定运行，WebSocket 长连接不被错误中断。
- SQLite 数据库文件路径、读写权限、数据持久化和备份方式正确。
- 数据库环境变量、JWT 密钥、CORS、端口占用处理正确。
- 后端接口文档、README 启动命令和实际行为一致。
- 全量自动化测试回归。

建议运行：

```bash
cd frontend
npm run build
```

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

```bash
python -m pytest tests/ -q
```

## 4. 测试执行优先级

第一优先级：核心业务闭环。

- 注册/登录
- 创建项目
- 画布搭建模型
- 结构校验
- 启动训练
- 查看训练结果
- 导出 PyTorch 代码

第二优先级：异常路径。

- 非法模型结构
- 非法参数
- 后端未启动
- 本机 Agent 未连接
- Token 无效
- 无权限访问项目
- 数据库重名或约束冲突

第三优先级：部署与兼容性。

- Nginx 静态资源托管与反向代理
- uvicorn 生产启动参数
- SQLite 数据库文件读写与持久化
- 前端生产构建
- CPU/GPU 环境差异
- Windows 路径与端口占用问题

## 5. 各部分验收标准

### 人员 1：用户、认证、项目管理验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 用户注册 | 合法用户可注册成功；重复邮箱、弱密码、两次密码不一致均返回明确错误 |
| 用户登录 | 正确邮箱和密码可登录并返回 JWT；错误密码、未注册邮箱、无效 Token 均能正确拦截 |
| 权限控制 | 未登录用户不能创建、修改、删除项目；非项目所有者不能修改或删除他人项目 |
| 用户 CRUD | 用户创建、查询、更新、删除功能正常；非法 id、空字段、重复邮箱有明确错误 |
| 项目 CRUD | 项目创建、查询、更新、删除功能正常；同一用户项目名重复会失败 |
| 数据持久化 | 服务重启后用户和项目数据仍可读取 |
| 自动化测试 | `tests/M1_user_project/test_code/` 下测试全部通过 |

### 人员 2：前端模型编辑器验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 节点操作 | Input、Conv2D、Pooling、Flatten、Linear、Dropout、Output 等节点可正常添加、选中、删除 |
| 连线操作 | 合法连线可创建和删除；自连接、重复连接、连接不存在节点会被拒绝 |
| 参数编辑 | 右侧参数面板可正确修改节点参数，画布显示和导出的 ModelGraph 同步更新 |
| 非法输入 | 空参数、非法 shape、非数字输入不会导致页面崩溃，并有提示或保持原值 |
| ModelGraph 导出 | 导出结构稳定包含 `layers` 和 `connections`，字段符合后端约定 |
| 页面交互 | 拖拽、缩放、右键菜单、多画布切换、Toast 提示表现正常 |
| 接口按钮 | Validate、Export、Train 按钮状态正确，后端异常时页面不崩溃 |
| 自动化与手工测试 | `test_model_editor.js` 通过，关键浏览器交互完成手工验收 |

### 人员 3：结构校验与维度推导验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 合法模型 | CNN、MLP、基础分支模型校验返回 `valid=true`，无错误 |
| 必要节点检查 | 缺少 Input 或 Output 时返回 `valid=false`，错误信息明确指出缺失节点 |
| 图结构检查 | 孤立节点、断裂连接、循环连接均可被识别并返回可读错误 |
| 参数检查 | Conv2D、Pooling、Linear、Dropout 等非法参数会被拒绝 |
| 维度推导 | Conv2D、Pooling、Flatten、Linear 输出维度与预期一致 |
| 分支合并 | add 要求输入 shape 完全一致；concat 要求非拼接维度一致 |
| 接口验收 | `/validate` 对合法模型返回 200 且 `valid=true`；业务错误返回 200 且 `valid=false` |
| 自动化测试 | `tests/M3_validator_shape/test_code/` 下测试全部通过 |

### 人员 4：本机 Agent、训练与设备验收标准

| 验收项 | 通过标准 |
| --- | --- |
| Agent 启动 | 本机 Agent 可成功启动并连接云端后端 |
| 健康检查 | Agent 健康检查接口返回 `status=ok` 和设备摘要 |
| 设备检测 | CPU 始终可用；有 CUDA 时能识别 GPU；无 GPU 时能提示或降级到 CPU |
| 训练下发 | 前端发起训练后，云端能创建任务并下发给在线 Agent |
| 训练执行 | Agent 能根据 ModelGraph 构建 PyTorch 模型并完成至少一次小规模训练 |
| 进度回传 | loss、accuracy、epoch、任务状态能回传到云端和前端训练监控页 |
| 异常处理 | Agent 未连接、训练失败、取消训练、设备不可用时状态清晰且不阻塞系统 |
| 数据集适配 | MNIST/FashionMNIST/KMNIST/CIFAR10/CIFAR100 至少完成冒烟验证或配置验证 |

### 人员 5：代码导出与模型模板验收标准

| 验收项 | 通过标准 |
| --- | --- |
| Python 导出 | 合法 CNN、MLP、LSTM、分支模型可导出 `.py` 文件 |
| 导出代码运行 | 导出的 Python 文件能直接执行 smoke test，输出 shape 正确 |
| Notebook 导出 | 导出的 `.ipynb` 是合法 Jupyter Notebook v4 JSON，代码单元可顺序执行 |
| 训练配置导出 | 导出内容包含数据集、batch size、epoch、学习率、优化器、损失函数等配置 |
| 非法模型拒绝 | 缺 Output、连接断裂、维度不匹配等模型不能导出，并返回可读错误 |
| 模板列表 | 11 个内置模板均能出现在模板列表中，模板 key 与设计一致 |
| 模板合法性 | 每个模板生成的 ModelGraph 均可通过结构校验 |
| 模板项目链路 | 基于模板创建项目后，可以保存、查询，并再次通过结构校验 |
| 自动化测试 | M6 和 M7 相关自动化测试全部通过 |

### 人员 6：系统集成、部署与回归验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 前端构建 | `npm run build` 成功，生成生产静态资源 |
| uvicorn 服务 | 后端可通过 uvicorn 在生产参数下启动，健康检查接口返回正常 |
| Nginx 静态资源 | Nginx 能正确访问前端页面，刷新任意前端路由不出现 404 |
| Nginx 反向代理 | API 请求和 WebSocket 请求能正确转发到 uvicorn |
| SQLite 数据库 | SQLite 文件路径正确，进程有读写权限，重启后数据仍存在 |
| 端到端流程 | 注册登录、创建项目、搭建模型、校验、训练、监控、导出代码完整走通 |
| 配置安全 | JWT 密钥、数据库路径、前后端 API 地址、CORS、端口配置符合部署环境 |
| 回归测试 | 所有可运行的自动化测试完成回归，并记录失败原因或跳过原因 |
| 部署记录 | 形成 Nginx + SQLite + uvicorn 的部署验证记录，包括启动命令、访问地址、关键配置和验证结果 |

## 6. 统一交付物要求

每位测试人员需要提交以下内容：

- 测试用例表
- 测试执行记录
- 缺陷列表
- 复测结果
- 自动化测试输出或手工测试截图

人员 6 额外负责汇总：

- 总测试报告
- 端到端集成测试结果
- Nginx + SQLite + uvicorn 部署验证记录
- 遗留风险说明

## 7. 总结

该分配方案将系统按用户数据、前端编辑、结构校验、训练执行、代码导出、系统集成六个方向拆分。每个人都有明确边界，同时人员 6 负责把各模块串成完整交付链路，能够覆盖当前系统的主要功能、核心风险和部署验证需求。
