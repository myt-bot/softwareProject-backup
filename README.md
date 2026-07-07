# AI 赋能可视化深度学习模型构建平台

## 项目简介

本项目是一个面向软件课设的可视化深度学习模型构建平台。

系统面向深度学习初学者、课程实验和小组项目场景，目标是让用户通过可视化方式搭建神经网络模型，并完成结构校验、张量维度推导、本机训练、CPU/GPU 切换、训练指标查看和 PyTorch 代码导出。

当前架构采用「云端中转 + 用户本机 Agent」方案：云端服务器只负责前端部署、用户/项目数据存储、训练任务调度和 Agent 连接管理；真正的模型校验、PyTorch 模型构建、训练执行、设备检测和训练产物保存都在用户本机 `local_agent` 中完成。

## 项目目标

- 支持用户通过可视化界面搭建 MLP、CNN 等基础模型。
- 支持模型结构检查和层级维度推导。
- 支持通过用户本机 Agent 执行 PyTorch 训练。
- 支持 CPU/GPU 运算切换。
- 支持展示 loss、accuracy 等训练指标。
- 支持导出 PyTorch 模型代码。
- 支持模型模板一键生成，降低初学者使用门槛。

## 计划技术栈

### 前端

- HTML
- CSS
- JavaScript
- 后续可选：Vue 或 React
- 后续可选图编辑库：Vue Flow、React Flow、AntV X6 或 jsPlumb

### 云端后端

- Python
- FastAPI
- Pydantic
- MySQL / SQLAlchemy
- WebSocket（用于与本机 Agent 通信）

### 本机 Agent

- Python
- FastAPI
- PyTorch
- TorchVision
- NumPy

### 运行环境

- Python 3.10 或更高版本
- Node.js 20.19 或更高版本（前端 Vue 3 + TypeScript + Vite）
- MySQL 8（后端存储；推荐直接用 Docker Compose 启动，见下文「Docker Compose 一键部署」）
- Docker（可选，用于一键部署云端后端与数据库）
- CUDA GPU 可选
- 无 GPU 时自动使用 CPU

## 服务启动方法

前端页面、云端后端接口和用户本机 Agent 需要分别启动。开发环境中通常保持三个终端窗口运行；生产部署时，云端只部署前端、云端后端和数据库，本机 Agent 由用户在自己的电脑上启动。

首次运行云端后端或本机 Agent 时，先在项目根目录安装 Python 依赖：

```bash
pip install -r requirements.txt
```

终端一：启动前端开发服务器（首次运行需要先安装 npm 依赖）。

```bash
cd frontend
npm install
npm run dev
```

启动后在浏览器访问：

```text
http://127.0.0.1:5173/
```

前端其他常用命令（均在 `frontend/` 目录下执行）：

```bash
npm run typecheck   # TypeScript 类型检查
npm run build       # 类型检查 + 生产构建（输出到 frontend/dist/）
npm run preview     # 预览生产构建产物
```

终端二：启动云端后端 FastAPI 服务。

云端后端存储使用 MySQL，启动后端前需保证 `DATABASE_URL` 环境变量（缺省为
`mysql+pymysql://root:devroot@127.0.0.1:3306/visual_dl`）指向的数据库可用。
最简单的方式是先用 Docker 只启动数据库：

```bash
docker compose up -d db
```

然后启动云端后端：

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

前端默认访问 `http://127.0.0.1:8000` 上的云端后端接口。若 `5173` 或 `8000` 端口被占用，需要先关闭占用该端口的旧服务，或同步修改前端接口地址和启动端口。

终端三：启动用户本机 Agent，连接云端并等待训练指令。

**首次使用（纯网页用户，本机没有 Agent 代码）**：登录后点击网页顶栏「本机训练
未连接」打开「本机训练 Agent」弹窗，点「下载本机 Agent」下载压缩包
（云端 `GET /agent/download` 返回，含完整 `local_agent` 源码、依赖清单和说明），
解压后按包内 `README.txt` 执行：

```bash
pip install -r requirements-agent.txt
python -m local_agent.main --server http://127.0.0.1:8000 --token <你的JWT令牌>
```

**开发环境（已 clone 仓库）**：可直接在项目根目录运行（令牌可在弹窗复制或从
浏览器 localStorage 的 `model-workshop-token` 取得）：

```bash
python -m local_agent.main --server http://127.0.0.1:8000 --token <你的JWT令牌>
```

本机 Agent 会：

1. 首次运行时通过 `local_agent/runtime_manager.py` 从云端 `/runtime/manifest` 与
   `/runtime/download` 下载训练运行时代码，做 SHA-256 校验后安装到
   `~/.visualdl_agent/runtime`（已实现）。
2. 主动用 WebSocket 连接云端 `/agents/ws`，注册为当前用户的在线训练节点。
3. 接收云端下发的训练/校验/设备/导出指令，在本机用 PyTorch 执行，并把进度与结果
   通过 WebSocket 实时回传给云端；云端再经 `/client/ws` 推送到浏览器。

Agent 连接成功后，网页顶栏会显示「本机训练已连接」，此时才能进行结构校验、训练与
代码导出（这些都需要本机的 PyTorch 运行时）。

## Docker Compose 一键部署（云端后端 + MySQL）

仓库提供了 `docker-compose.yml`，可一条命令同时启动 MySQL 数据库和云端后端 API，适合演示答辩、服务器部署和新成员快速上手。云端后端只负责用户、项目、数据库和训练任务中转，不在服务器上执行 PyTorch 训练。

### 首次启动

```bash
# （可选）自定义密码/密钥：复制环境变量模板并按需编辑；跳过则使用开发默认值
cp .env.example .env

# 构建镜像并启动全部云端服务（MySQL + 云端后端 API）
docker compose up -d --build

# （可选）把 data/ 下的历史 JSON 数据导入 MySQL（幂等脚本，可重复执行）
python -m backend.migrate_json_to_mysql
```

启动后：云端后端 API 在 `http://127.0.0.1:8000`，MySQL 在 `127.0.0.1:3306`（只绑定本机回环地址，不对外网暴露）。前端仍按上文方式用 npm 启动；训练功能需要用户本机 Agent 在线。

### 常用命令

| 命令 | 作用 |
| --- | --- |
| `docker compose ps` | 查看服务状态 |
| `docker compose logs -f api` | 跟踪后端日志 |
| `docker compose down` | 停止并删除容器（**数据卷保留，数据不丢**） |
| `docker compose down -v` | ⚠️ 连数据卷一起删除，数据库数据将清空 |
| `docker compose up -d --build` | 代码更新后重新构建镜像并启动 |

### 数据持久化与备份

MySQL 数据存放在命名数据卷 `softwareproject_mysql_data` 中（位于宿主机磁盘），
容器删除、重建、镜像升级均不影响数据；只有显式执行 `docker compose down -v`
或 `docker volume rm` 才会删除数据。

备份与恢复：

```bash
# 备份（在项目根目录执行）
docker exec vdl-mysql mysqldump -uroot -p密码 visual_dl > backup_$(date +%F).sql

# 恢复
docker exec -i vdl-mysql mysql -uroot -p密码 visual_dl < backup_2026-07-06.sql
```

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYSQL_ROOT_PASSWORD` | `devroot` | MySQL root 密码（生产部署必改） |
| `MYSQL_DATABASE` | `visual_dl` | 数据库名 |
| `JWT_SECRET_KEY` | 开发默认值 | JWT 签名密钥（生产部署必改） |
| `DATABASE_URL` | 指向本机 3306 | 后端数据库连接串；手动运行后端时可用它指向任意 MySQL |

在项目根目录创建 `.env`（参考 `.env.example`）即可覆盖默认值；`.env` 已被
`.gitignore` 忽略，不会提交到仓库。

### 端口说明与常见问题

- Docker 方式启动的后端与「服务启动方法」中手动 `uvicorn` 启动的后端**共用
  8000 端口，二者同一时间只能运行一个**。若 `docker compose up` 报
  `bind: address already in use`，先停掉手动启动的后端（包括其他项目副本里
  启动的）再执行。
- 只想用 Docker 跑数据库、后端仍在本机调试：`docker compose up -d db`。

## 项目目录结构

```text
project/
  backend/
    __init__.py         # 云端后端包声明
    main.py             # 云端 FastAPI 接口入口
    cloud_training.py   # 云端训练任务调度与本机 Agent 中转接口
    schemas.py          # 云端数据结构定义（用户/项目/训练中转）
    templates.py        # 内置模型模板
    storage.py          # MySQL 数据库存储层（SQLAlchemy，M1）
    migrate_json_to_mysql.py  # 一次性迁移脚本：JSON 历史数据导入 MySQL（M1）
    auth.py             # 用户管理与认证模块（M1）
    projects.py         # 项目管理模块（M1）
    security.py         # 密码哈希与 JWT 令牌（M1）
  local_agent/
    __init__.py         # 本机 Agent 包声明
    main.py             # 用户本机 Agent 入口
    agent_client.py     # 主动连接云端 WebSocket 的客户端
    runtime_manager.py  # 动态下载/更新 trainer-runtime 的管理器
    runtime/
      __init__.py       # 本机训练运行时包声明
      schemas.py        # 本机训练运行时数据结构
      device.py         # CPU/GPU 检测与选择
      model_builder.py  # 根据模型 JSON 构建 PyTorch 模型
      graph_model.py    # 支持 DAG 前向传播的 PyTorch 图模型
      graph_utils.py    # 模型图拓扑排序与前驱/后继映射
      validator.py      # 模型结构校验与维度推导
      trainer.py        # 本机训练流程
      code_exporter.py  # 导出 PyTorch 代码
  frontend/
    index.html          # 前端页面入口（Vite）
    package.json        # 前端依赖与脚本
    vite.config.ts      # Vite 构建配置
    tsconfig.json       # TypeScript 配置
    src/
      main.ts           # 应用入口，挂载 Vue 根组件
      App.vue           # 根组件，组织页面整体布局
      store.ts          # 全局响应式状态与纯数据逻辑（含本机 Agent 在线状态）
      auth.ts           # 登录状态管理（token 持久化与会话恢复，登录后建立 WebSocket）
      ws.ts             # 与云端的持久化 WebSocket（Agent 状态、训练进度推送、校验/导出请求-响应）
      canvas.ts         # 画布交互引擎（拖拽/连线/SVG 绘制/缩放）
      actions.ts        # 业务动作（校验/保存/导出/训练，经 WebSocket 转发到本机 Agent）
      monitor.ts        # 训练监控页状态机（进度由 WebSocket 推送驱动）
      types.ts          # 共享类型定义
      api/
        client.ts       # 云端 REST 接口与 WebSocket URL 封装
      components/       # Vue 组件
        TopBar.vue          # 顶栏与数据集下拉、本机 Agent 连接状态
        AgentModal.vue      # 本机训练 Agent 指引弹窗（启动命令、连接状态）
        DeviceSelector.vue  # 训练设备选择（CPU / GPU）
        StorageSettings.vue # 存储位置设置（数据集下载 / 结果保存目录）
        GuideStrip.vue      # 新手引导条
        LayerSidebar.vue    # 左侧组件库与模板
        CanvasBoard.vue     # 中间模型画布
        CanvasTabs.vue      # 多画布标签页（新建/切换/关闭画布）
        InspectorPanel.vue  # 右侧参数面板
        ActionBar.vue       # 底部操作栏与训练任务面板
        ExportModal.vue     # 导出代码弹窗
        HelpModal.vue       # 新手指南弹窗
        AuthPage.vue        # 登录 / 注册独立页（登录后才进入主界面）
        ContextMenus.vue    # 节点/连线右键菜单
        ToastContainer.vue  # 消息提示
        TrainingMonitor.vue # 训练监控页
        TmChart.vue         # 训练指标折线图
        ParamNumberField.vue # 数字参数输入框
      styles.css        # 页面样式
  tests/
    M1_user_project/
      test_code/        # M1 用户与项目管理模块测试代码
      test_design/      # M1 模块测试设计文档
    M2_model_editor/    # M2 模型编辑器模块测试
    M3_validator_shape/ # M3 结构校验与维度推导模块测试
    M7_templates_docs/  # M7 内置模板模块测试
  requirements.txt      # Python 依赖
  docker-compose.yml    # 一键部署编排：MySQL + 云端后端 API
  Dockerfile            # 云端后端 API 镜像构建配方
  .env.example          # 部署环境变量模板（复制为 .env 使用）
  README.md             # 项目开发文档
```

## 核心数据格式

前端通过 JSON 描述当前画布中的模型结构。云端后端负责保存项目、创建训练任务并把模型 JSON 与训练配置转发给用户本机 Agent；本机 Agent 根据该 JSON 完成结构校验、维度推导、PyTorch 模型构建、训练和代码导出。

示例：

```json
{
  "model": {
    "layers": [
      {
        "id": "input_1",
        "type": "Input",
        "name": "输入层",
        "params": {
          "shape": [1, 28, 28]
        }
      },
      {
        "id": "conv_1",
        "type": "Conv2D",
        "name": "卷积层1",
        "params": {
          "out_channels": 16,
          "kernel_size": 3,
          "stride": 1,
          "padding": 1
        }
      },
      {
        "id": "relu_1",
        "type": "ReLU",
        "name": "激活层",
        "params": {}
      }
    ],
    "connections": [
      {
        "source": "input_1",
        "target": "conv_1"
      },
      {
        "source": "conv_1",
        "target": "relu_1"
      }
    ]
  }
}
```

训练请求示例：

```json
{
  "model": {
    "layers": [],
    "connections": []
  },
  "train_config": {
    "dataset_name": "MNIST",
    "epochs": 5,
    "batch_size": 64,
    "rate": 0.001,
    "device": "cuda",
    "loss_fn": "cross_entropy",
    "optimizer": "sgd"
  }
}
```

## 当前支持的训练数据集

本机 Agent 训练运行时目前支持以下 torchvision 内置数据集：

| 数据集 | 输入形状 | 分类数 |
| ------ | -------- | ------ |
| MNIST | [1, 28, 28] | 10 |
| FashionMNIST | [1, 28, 28] | 10 |
| KMNIST | [1, 28, 28] | 10 |
| CIFAR10 | [3, 32, 32] | 10 |
| CIFAR100 | [3, 32, 32] | 100 |

## 当前计划支持的层类型

| 层类型  | 说明       | 主要参数                                         |
| ------- | ---------- | ------------------------------------------------ |
| Input   | 输入层     | shape                                            |
| Conv2D  | 二维卷积层 | out_channels, kernel_size, stride, padding       |
| ReLU    | 激活函数   | 无                                               |
| Pooling | 池化层     | kernel_size, stride, padding                     |
| Flatten | 展平层     | 无                                               |
| Linear  | 全连接层   | out_features                                     |
| Dropout | 随机失活层 | p                                                |
| Output  | 输出节点   | 无，分类数量由前置 Linear 层的 out_features 决定 |

除上述基础层外，结构校验器（M3）与内置模板（M7）现已支持进阶层类型：
LSTM、SelfAttention、TransformerEncoder、Seq2Seq、VAE、GraphConv。

## 云端与本机 Agent 接口设计

### 云端后端接口

| 方法   | 路径                      | 功能                   | 模块 |
| ------ | ------------------------- | ---------------------- | ---- |
| GET    | /health                   | 检查云端后端服务是否正常 | -    |
| POST   | /train                    | 创建云端训练任务，并下发给用户本机 Agent | 云端中转 |
| GET    | /train/{job_id}/status    | 查询云端记录的训练状态 | 云端中转 |
| GET    | /train/{job_id}/result    | 查询本机 Agent 回传的训练结果 | 云端中转 |
| POST   | /train/{job_id}/cancel    | 请求取消训练任务，并转发给本机 Agent | 云端中转 |
| GET    | /agents/status            | 查询某用户本机 Agent 的在线状态 | 云端中转 |
| WS     | /agents/ws                | 本机 Agent 主动连接云端的 WebSocket（下发指令 / 接收进度） | 云端中转 |
| WS     | /client/ws                | 浏览器持久化连接（推送 Agent 状态与训练进度、转发校验/导出请求） | 云端中转 |
| GET    | /agent/download           | 下载完整本机 Agent 程序 zip（首次使用的用户获取 Agent） | 云端中转 |
| GET    | /runtime/manifest         | 训练运行时版本元信息（供 Agent 判断是否需要下载） | 云端中转 |
| GET    | /runtime/download         | 下载训练运行时 zip 包（本机首次使用自动获取） | 云端中转 |
| POST   | /auth/register            | 注册新用户（自动登录） | M1   |
| POST   | /auth/login               | 用户登录（邮箱 + 密码） | M1   |
| GET    | /auth/me                  | 获取当前登录用户信息   | M1   |
| POST   | /users                    | 创建用户               | M1   |
| GET    | /users                    | 获取所有用户列表       | M1   |
| GET    | /users/{user_id}          | 获取指定用户信息       | M1   |
| PUT    | /users/{user_id}          | 更新用户信息           | M1   |
| DELETE | /users/{user_id}          | 删除用户及关联项目     | M1   |
| POST   | /projects                 | 创建项目（保存模型）   | M1   |
| GET    | /projects                 | 获取项目列表（支持 ?user_id= 按用户过滤） | M1 |
| GET    | /projects/templates       | 获取内置模型模板列表   | M7   |
| GET    | /projects/templates/{template_name} | 获取指定模板的完整模型图 | M7 |
| POST   | /projects/from-template   | 基于内置模板创建项目   | M7   |
| GET    | /projects/{project_id}    | 获取指定项目详情       | M1   |
| PUT    | /projects/{project_id}    | 更新项目信息           | M1   |
| DELETE | /projects/{project_id}    | 删除项目               | M1   |

### 本机 Agent 接口

| 方法 | 路径        | 功能 |
| ---- | ----------- | ---- |
| GET  | /health     | 检查本机 Agent 是否启动，并返回本机设备摘要 |
| GET  | /devices    | 获取用户本机可用 CPU/GPU 设备 |
| POST | /validate   | 在用户本机校验模型结构并推导维度 |

本机 Agent 通过主动连接云端的 WebSocket（`/agents/ws`）接收指令并回传进度：训练的
启动/取消/进度/结果，以及结构校验、设备查询、代码导出，都以 WebSocket 消息形式在
「浏览器 ↔ 云端 ↔ 本机 Agent」之间中转。上表的本机 HTTP 接口仅用于开发调试和本地
能力检查（`python -m local_agent.main` 启动的是 WebSocket 客户端，默认不对外提供
这些 HTTP 接口）。

## 云端后端模块和函数说明

### backend/main.py

| 函数                  | 功能                                       |
| --------------------- | ------------------------------------------ |
| health_check          | 检查云端后端服务是否正常运行                  |
| register              | 注册新用户并返回 JWT 令牌（M1）           |
| login                 | 验证凭据后返回 JWT 令牌（M1）             |
| get_current_user_info | 获取当前登录用户信息（M1）                |
| create_user           | 创建新用户（M1）                          |
| list_users            | 获取所有用户列表（M1）                    |
| get_user              | 获取指定用户信息（M1）                    |
| update_user           | 更新用户信息（M1）                        |
| delete_user           | 删除用户及关联项目（M1）                  |
| create_project        | 创建项目/保存模型（M1）                   |
| list_project_templates | 获取内置模型模板列表（M7）               |
| get_project_template  | 获取指定模板的完整模型图（M7）            |
| create_project_from_template | 基于内置模板创建项目（M7）          |
| list_projects         | 获取项目列表（M1）                        |
| get_project           | 获取指定项目详情（M1）                    |
| update_project        | 更新项目信息（M1）                        |
| delete_project        | 删除项目（M1）                            |

### backend/cloud_training.py

| 函数 | 功能 |
| --- | --- |
| create_cloud_training_job | 创建云端训练任务，并准备下发给用户本机 Agent |
| get_cloud_training_status | 查询云端记录的训练任务状态 |
| cancel_cloud_training_job | 请求取消训练任务，并转发给本机 Agent |
| get_cloud_training_result | 查询本机 Agent 回传的最终训练结果 |
| agent_websocket_endpoint | 接收本机 Agent 主动建立的 WebSocket 连接 |
| dispatch_training_job_to_agent | 将训练任务下发给用户在线的本机 Agent（待实现） |
| handle_agent_training_update | 处理本机 Agent 回传的训练进度或最终结果（待实现） |
| get_online_agent_for_user | 查询某个用户当前在线的本机 Agent（待实现） |

### backend/schemas.py

| 类 | 功能 |
| --- | --- |
| CloudModelGraph | 云端保存和转发的轻量模型图结构 |
| CloudTrainRequest | 云端训练中转接口请求体，包含模型图和训练配置字典 |
| UserCreateRequest | 创建用户接口的请求体（M1） |
| UserUpdateRequest | 更新用户接口的请求体（M1） |
| UserRegisterRequest | 用户注册接口的请求体，含 confirm_password 确认密码（M1） |
| UserLoginRequest | 用户登录接口的请求体（M1） |
| TokenResponse | 认证成功后的 JWT 令牌响应（M1） |
| ProjectCreateRequest | 创建项目接口的请求体（M1） |
| ProjectTemplateCreateRequest | 基于内置模板创建项目的请求体（M7） |
| ProjectUpdateRequest | 更新项目接口的请求体（M1） |

## 本机 Agent 模块和函数说明

### local_agent/main.py

| 函数 | 功能 |
| --- | --- |
| health_check | 返回本机 Agent 健康状态和设备摘要 |
| list_devices | 返回用户本机可用 CPU/GPU 设备 |
| validate_model | 在用户本机校验模型结构并推导维度 |
| start_agent | 启动本机 Agent，并主动连接云端服务器（待实现） |

### local_agent/agent_client.py

| 函数 | 功能 |
| --- | --- |
| connect_to_cloud_server | 连接云端 WebSocket，处理认证、心跳、重连和消息收发（待实现） |
| build_agent_hello_message | 构造 Agent 连接云端后的首条注册消息（待实现） |
| handle_cloud_command | 处理云端下发的训练、取消、运行时检查等指令（待实现） |
| start_local_training_job | 在用户本机启动 PyTorch 训练任务（待实现） |
| send_training_update | 向云端发送训练进度或最终结果（待实现） |

### local_agent/runtime_manager.py

| 函数 | 功能 |
| --- | --- |
| get_installed_runtime_version | 读取本机已安装的 trainer-runtime 版本（待实现） |
| fetch_runtime_manifest | 从云端获取最新兼容运行时元信息（待实现） |
| download_runtime_package | 下载并校验 trainer-runtime 压缩包（待实现） |
| install_runtime_package | 安装已下载的 trainer-runtime（待实现） |
| ensure_runtime_ready | 确保本机已有可用训练运行时（待实现） |

### local_agent/runtime/*.py

| 文件 | 功能 |
| --- | --- |
| schemas.py | 本机训练运行时数据结构，包括模型图、训练配置、校验请求、训练请求和代码导出请求 |
| device.py | CPU/GPU 检测与训练设备选择 |
| graph_utils.py | 模型图拓扑排序与前驱/后继映射 |
| graph_model.py | 支持 DAG 前向传播的 PyTorch 图模型 |
| model_builder.py | 根据模型 JSON 构建 PyTorch 模型 |
| validator.py | 模型结构校验与张量维度推导 |
| trainer.py | 本机 PyTorch 训练流程、指标计算和训练产物保存 |
| code_exporter.py | 根据可视化模型图生成 PyTorch 模型源代码 |

### backend/templates.py

| 函数                    | 功能                                      |
| ----------------------- | ----------------------------------------- |
| get_available_templates | 返回前端可选择的全部内置模板元信息（共 11 个） |
| create_*_template 系列  | 各内置模板的模型图构建函数：线性分类器、MLP、感知机、LeNet、ResNet-tiny、LSTM、Seq2Seq、Transformer 编码器、自注意力演示、VAE、GCN-tiny、CNN |
| apply_template          | 按模板名或别名返回模板图，供前端加载到画布中 |

### backend/storage.py（M1）

MySQL 数据库存储层（SQLAlchemy 实现）。连接串由环境变量 `DATABASE_URL` 配置；
邮箱唯一、同用户项目名唯一、用户-项目外键级联等业务约束由数据库层保证。
对外函数只进出普通字典，上层业务无需感知数据库细节。

| 函数                    | 功能                   |
| ----------------------- | ---------------------- |
| configure_database      | 初始化/切换数据库引擎并建表（测试传入独立 SQLite 实现隔离） |
| dispose_database        | 释放当前引擎，下次访问时按环境变量重新初始化 |
| save_user               | 保存新用户记录         |
| get_user                | 按 id 获取用户         |
| list_users              | 列出所有用户，支持过滤 |
| update_user             | 更新用户信息           |
| delete_user             | 删除用户               |
| user_exists             | 检查用户是否存在       |
| save_project            | 保存新项目记录         |
| get_project             | 按 id 获取项目         |
| list_projects           | 列出所有项目，支持过滤 |
| update_project          | 更新项目信息           |
| delete_project          | 删除项目               |
| project_exists          | 检查项目是否存在       |
| delete_projects_by_user | 按用户 id 批量删除项目 |

### backend/auth.py（M1）

| 函数              | 功能                                 |
| ----------------- | ------------------------------------ |
| register_user     | 注册新用户，校验邮箱唯一性、确认密码一致性并哈希密码 |
| authenticate_user | 验证用户凭据（邮箱+密码）            |
| get_user_by_email | 按邮箱查找用户                       |
| get_user          | 按 id 获取用户信息                   |
| list_users        | 获取所有用户列表                     |
| update_user       | 更新用户信息（用户名/邮箱/密码）     |
| delete_user       | 删除用户及关联的所有项目             |

### backend/security.py（M1）

| 函数                | 功能                                   |
| ------------------- | -------------------------------------- |
| hash_password       | 对明文密码进行 bcrypt 哈希             |
| verify_password     | 验证明文密码与 bcrypt 哈希是否匹配     |
| create_access_token | 为用户生成 JWT 访问令牌                |
| verify_access_token | 验证 JWT 令牌并返回解码 payload        |
| get_current_user    | FastAPI 依赖：从请求头提取当前登录用户 |

### backend/projects.py（M1）

| 函数              | 功能                                   |
| ----------------- | -------------------------------------- |
| create_project    | 创建新项目，校验用户存在性和模型图结构 |
| get_project       | 按 id 获取项目详情                     |
| list_projects     | 列出项目，支持按用户过滤               |
| update_project    | 更新项目信息（名称/模型图/描述），校验项目所有权 |
| delete_project    | 删除项目，校验项目所有权               |

## 前端模块和函数说明

前端使用 Vue 3（组合式 API + `<script setup>`）+ TypeScript + Vite 实现。

### frontend/src/store.ts

| 导出                           | 功能                                               |
| ------------------------------ | -------------------------------------------------- |
| store                          | 全局响应式状态（节点、连线、选中态、校验态等）     |
| ui / toasts / showToast        | 弹窗开关、消息提示队列                             |
| getCurrentModelGraph           | 将当前画布状态转换为后端需要的模型 JSON            |
| getTrainConfig                 | 生成训练配置（数据集、超参数）                     |
| updateNodeParam                | 更新节点参数并刷新节点摘要                         |
| resetValidationAfterGraphChange | 图结构变化后重置校验状态                          |

### frontend/src/canvas.ts

| 导出                 | 功能                                           |
| -------------------- | ---------------------------------------------- |
| drawLines            | 绘制节点间的贝塞尔连线（含交叉过桥、控制点）   |
| beginConnection 等   | 连线模式的进入、预览、完成与取消               |
| handleNodeMouseDown 等 | 节点拖拽                                     |
| handleZoomAction     | 画布缩放                                       |
| addNodeFromLayer     | 从组件库拖入新节点                             |
| applyTemplateGraph   | 将后端模板提供的模型 JSON 加载到可视化画布中   |

### frontend/src/actions.ts

| 导出                      | 功能                                         |
| ------------------------- | -------------------------------------------- |
| handleValidateModel       | 将当前模型图发送到本机 Agent，并展示结构校验结果 |
| handleSaveProject         | 保存当前模型到项目                           |
| handleExportCode          | 向本机 Agent 请求生成的 PyTorch 代码，并展示给用户 |
| handleStartTraining       | 将模型图和训练配置提交给云端任务中转，由本机 Agent 执行训练 |
| openCurrentTrainingMonitor | 打开训练监控页并对接实时轮询                |

### frontend/src/monitor.ts

| 导出                          | 功能                                             |
| ----------------------------- | ------------------------------------------------ |
| openTrainingMonitor           | 打开训练监控页（live 轮询 / demo 演示两种模式）  |
| activeSeries / computeResults | 训练指标序列与结果卡数值                         |
| handleRerun 等                | 重新训练、模拟完成、图例切换等交互               |

### frontend/src/api/client.ts

| 函数                | 功能                                             |
| ------------------- | ------------------------------------------------ |
| fetchHealth         | 调用后端健康检查接口，确认服务是否可访问         |
| fetchDevices        | 向本机 Agent 请求当前可用的 CPU/GPU 设备          |
| validateModel       | 将可视化模型图发送给本机 Agent，用于结构校验和维度推导 |
| startTraining       | 向云端创建训练任务，并由云端下发给本机 Agent 执行 |
| fetchTrainingStatus | 向云端查询训练任务的当前状态和进度               |
| fetchTrainingResult | 向云端查询本机 Agent 回传的最终指标和产物信息     |
| cancelTraining      | 请求停止进行中的训练任务                         |
| registerUser        | 注册新账号并获取 JWT 令牌                        |
| loginUser           | 邮箱密码登录并获取 JWT 令牌                      |
| fetchCurrentUser    | 通过令牌获取当前登录用户信息                     |
| setAuthToken        | 注入 JWT，之后所有请求自动携带 Authorization 头  |
| exportPytorchCode   | 向本机 Agent 请求根据模型图生成的 PyTorch 模型代码 |

## 增量开发计划

### 第一阶段：基础训练闭环

- 固定 CNN 或 MLP 模型。
- 支持 MNIST、FashionMNIST、KMNIST、CIFAR10 和 CIFAR100 等内置数据集。
- 使用 CPU 完成本地训练。
- 返回 loss 和 accuracy。

### 第二阶段：CPU/GPU 切换

- 检测本机是否支持 CUDA。
- 前端展示 CPU/GPU 选项。
- 本机 Agent 根据用户选择切换训练设备。
- GPU 不可用时给出提示或自动降级到 CPU。

### 第三阶段：模型 JSON 构建

- 前端生成统一的模型 JSON。
- 云端接收模型 JSON 并创建训练任务。
- 本机 Agent 根据 JSON 构建 PyTorch 模型。

### 第四阶段：结构校验与维度推导

- 校验连接是否合法。
- 校验层参数是否合法。
- 推导每层输入输出维度。
- 返回错误节点、错误原因和修改建议。

### 第五阶段：可视化画布

- 支持添加层。
- 支持连接层。
- 支持编辑参数。
- 支持删除节点。
- 支持高亮错误节点。

### 第六阶段：训练曲线与代码导出

- 展示 loss 曲线。
- 展示 accuracy 曲线。
- 导出 PyTorch 模型代码。
- 保存或展示训练结果摘要。

## 开发约定

- 前端不直接执行深度学习训练，只负责模型编辑、接口调用和结果展示。
- 云端后端负责用户、项目、数据库、训练任务调度和本机 Agent 连接管理。
- 本机 Agent 负责模型校验、维度推导、PyTorch 模型构建、训练、设备检测和代码导出。
- 前端、云端后端和本机 Agent 之间统一使用 JSON 通信；云端与 Agent 的任务通道优先使用 WebSocket。
- 第一版模型构建器按有向无环图进行拓扑执行，支持顺序结构、基础分支汇合和多输入合并；暂不支持环形连接和自定义 Python 层。
- 用户只能选择系统内置层类型，不能直接提交任意 Python 代码。
- GPU 是否可用以本机 Agent 检测结果为准，前端和云端后端不能自行假设。
- 新增云端接口时需要同步更新 backend/main.py 或 backend/cloud_training.py 和本 README。
- 新增本机 Agent 接口时需要同步更新 local_agent/main.py 或 local_agent/agent_client.py 和本 README。
- 新增函数时需要在本 README 中登记函数功能。
- 修改核心 JSON 数据格式时，需要同步更新前端、云端后端、本机 Agent 和本 README。

## AI 协作说明

后续使用 AI 辅助开发时，请优先阅读本 README，并遵守以下约定：

- 不要随意改变前端、云端后端和本机 Agent 之间的 JSON 数据结构。
- 新增功能前先确认对应模块职责。
- 云端新增训练调度、中转、Agent 连接相关逻辑优先放在 backend/cloud_training.py。
- 本机新增训练相关逻辑优先放在 local_agent/runtime/trainer.py。
- 本机新增模型构建逻辑优先放在 local_agent/runtime/model_builder.py，图模型执行逻辑优先放在 local_agent/runtime/graph_model.py。
- 本机新增维度推导和校验逻辑优先放在 local_agent/runtime/validator.py。
- 本机新增设备相关逻辑优先放在 local_agent/runtime/device.py。
- 本机新增代码导出逻辑优先放在 local_agent/runtime/code_exporter.py。
- 前端新增接口调用时优先封装到 frontend/src/api/client.ts，共享类型放在 frontend/src/types.ts。
- 前端新增页面区块时拆分为 frontend/src/components/ 下的 Vue 组件，跨组件状态放在 frontend/src/store.ts。
- 新增或修改函数后，需要同步更新本 README 中的函数说明。

