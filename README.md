# AI 赋能可视化深度学习模型构建平台

## 项目简介

本项目是一个面向软件课设的可视化深度学习模型构建平台。

系统面向深度学习初学者、课程实验和小组项目场景，目标是让用户通过可视化方式搭建神经网络模型，并完成结构校验、张量维度推导、本地训练、CPU/GPU 切换、训练指标查看和 PyTorch 代码导出。

## 项目目标

- 支持用户通过可视化界面搭建 MLP、CNN 等基础模型。
- 支持模型结构检查和层级维度推导。
- 支持本地 PyTorch 训练。
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

### 后端

- Python
- FastAPI
- Pydantic
- PyTorch
- TorchVision
- NumPy

### 运行环境

- Python 3.10 或更高版本
- Node.js 20.19 或更高版本（前端 Vue 3 + TypeScript + Vite）
- CUDA GPU 可选
- 无 GPU 时自动使用 CPU

## 服务启动方法

前端页面和后端接口需要分别启动，并保持两个终端窗口都处于运行状态。

首次运行或提示缺少 `uvicorn`、`fastapi` 等依赖时，先在项目根目录安装依赖：

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

终端二：启动后端 FastAPI 服务。

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

前端默认访问 `http://127.0.0.1:8000` 上的后端接口。若 `5173` 或 `8000` 端口被占用，需要先关闭占用该端口的旧服务，或同步修改前端接口地址和启动端口。

## 项目目录结构

```text
project/
  backend/
    __init__.py         # 后端包声明
    main.py             # FastAPI 接口入口
    schemas.py          # 前后端数据结构定义
    device.py           # CPU/GPU 检测与选择
    model_builder.py    # 根据模型 JSON 构建 PyTorch 模型
    graph_model.py      # 支持 DAG 前向传播的 PyTorch 图模型
    validator.py        # 模型结构校验与维度推导
    trainer.py          # 本地训练流程
    code_exporter.py    # 导出 PyTorch 代码
    templates.py        # 内置模型模板
    graph_utils.py      # 模型图拓扑排序与前驱/后继映射
    storage.py          # 本地 JSON 文件存储层（M1）
    auth.py             # 用户管理与认证模块（M1）
    projects.py         # 项目管理模块（M1）
    security.py         # 密码哈希与 JWT 令牌（M1）
  frontend/
    index.html          # 前端页面入口（Vite）
    package.json        # 前端依赖与脚本
    vite.config.ts      # Vite 构建配置
    tsconfig.json       # TypeScript 配置
    src/
      main.ts           # 应用入口，挂载 Vue 根组件
      App.vue           # 根组件，组织页面整体布局
      store.ts          # 全局响应式状态与纯数据逻辑
      canvas.ts         # 画布交互引擎（拖拽/连线/SVG 绘制/缩放）
      actions.ts        # 后端交互动作（校验/保存/导出/训练）
      monitor.ts        # 训练监控页状态机与轮询
      types.ts          # 共享类型定义
      api/
        client.ts       # 后端接口调用封装
      components/       # Vue 组件
        TopBar.vue          # 顶栏与数据集下拉
        GuideStrip.vue      # 新手引导条
        LayerSidebar.vue    # 左侧组件库与模板
        CanvasBoard.vue     # 中间模型画布
        InspectorPanel.vue  # 右侧参数面板
        ActionBar.vue       # 底部操作栏与训练任务面板
        ExportModal.vue     # 导出代码弹窗
        HelpModal.vue       # 新手指南弹窗
        ContextMenus.vue    # 节点/连线右键菜单
        ToastContainer.vue  # 消息提示
        TrainingMonitor.vue # 训练监控页
        TmChart.vue         # 训练指标折线图
        ParamNumberField.vue # 数字参数输入框
      styles.css        # 页面样式
  tests/
    M1_user_project/
      test_code/        # M1 模块测试代码
      test_design/      # M1 模块测试设计文档
  requirements.txt      # Python 依赖
  README.md             # 项目开发文档
```

## 核心数据格式

前端通过 JSON 描述当前画布中的模型结构。后端根据该 JSON 完成结构校验、维度推导、模型构建、训练和代码导出。

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

后端训练模块目前支持以下 torchvision 内置数据集：

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

## 后端接口设计

| 方法   | 路径                      | 功能                   | 模块 |
| ------ | ------------------------- | ---------------------- | ---- |
| GET    | /health                   | 检查后端服务是否正常   | -    |
| GET    | /devices                  | 获取可用计算设备       | -    |
| POST   | /validate                 | 校验模型结构并推导维度 | -    |
| POST   | /train                    | 启动训练任务           | -    |
| GET    | /train/{job_id}/status    | 查询训练状态           | -    |
| GET    | /train/{job_id}/result    | 查询训练结果           | -    |
| POST   | /export/pytorch           | 导出 PyTorch 代码      | -    |
| POST   | /auth/register            | 注册新用户（自动登录） | M1   |
| POST   | /auth/login               | 用户登录（邮箱+密码）  | M1   |
| GET    | /auth/me                  | 获取当前登录用户信息   | M1   |
| POST   | /users                    | 创建用户               | M1   |
| GET    | /users                    | 获取所有用户列表       | M1   |
| GET    | /users/{user_id}          | 获取指定用户信息       | M1   |
| PUT    | /users/{user_id}          | 更新用户信息           | M1   |
| DELETE | /users/{user_id}          | 删除用户及关联项目     | M1   |
| GET    | /users/{user_id}/projects | 获取用户的所有项目     | M1   |
| POST   | /projects                 | 创建项目（保存模型）   | M1   |
| GET    | /projects                 | 获取项目列表           | M1   |
| GET    | /projects/{project_id}    | 获取指定项目详情       | M1   |
| PUT    | /projects/{project_id}    | 更新项目信息           | M1   |
| DELETE | /projects/{project_id}    | 删除项目               | M1   |

## 后端模块和函数说明

### backend/main.py

| 函数                  | 功能                                       |
| --------------------- | ------------------------------------------ |
| health_check          | 检查后端服务是否正常运行                   |
| list_devices          | 返回当前本机可用的计算设备                 |
| validate_model        | 校验模型结构，并推导每一层的张量维度变化   |
| start_training        | 根据用户选择的 CPU 或 GPU 启动本地训练任务 |
| get_training_status   | 返回指定训练任务的当前状态、日志和进度     |
| get_training_result   | 返回训练完成后的最终指标和相关产物信息     |
| export_pytorch_code   | 根据可视化模型结构生成 PyTorch 源代码      |
| register              | 注册新用户并返回 JWT 令牌（M1）            |
| login                 | 验证凭据后返回 JWT 令牌（M1）              |
| get_current_user_info | 获取当前登录用户信息（M1）                 |
| create_user           | 创建新用户（M1）                           |
| list_users            | 获取所有用户列表（M1）                     |
| get_user              | 获取指定用户信息（M1）                     |
| update_user           | 更新用户信息（M1）                         |
| delete_user           | 删除用户及关联项目（M1）                   |
| get_user_projects     | 获取用户的所有项目（M1）                   |
| create_project        | 创建项目/保存模型（M1）                    |
| list_projects         | 获取项目列表（M1）                         |
| get_project           | 获取指定项目详情（M1）                     |
| update_project        | 更新项目信息（M1）                         |
| delete_project        | 删除项目（M1）                             |

### backend/schemas.py

| 类                   | 功能                                         |
| -------------------- | -------------------------------------------- |
| LayerConfig          | 描述画布中的一个模型层节点以及它的可编辑参数 |
| ConnectionConfig     | 描述画布中两个层节点之间的连接关系           |
| ModelGraph           | 描述前端传给后端的完整模型图结构             |
| TrainConfig          | 描述训练超参数以及用户选择的计算设备         |
| ModelRequest         | 模型校验和维度推导接口的请求体               |
| TrainRequest         | 启动本地训练任务接口的请求体                 |
| CodeExportRequest    | 导出 PyTorch 代码接口的请求体                |
| UserCreateRequest    | 创建用户接口的请求体（M1）                   |
| UserUpdateRequest    | 更新用户接口的请求体（M1）                   |
| UserRegisterRequest  | 用户注册接口的请求体（M1）                   |
| UserLoginRequest     | 用户登录接口的请求体（M1）                   |
| TokenResponse        | 认证成功后的 JWT 令牌响应（M1）              |
| ProjectCreateRequest | 创建项目接口的请求体（M1）                   |
| ProjectUpdateRequest | 更新项目接口的请求体（M1）                   |

### backend/device.py

| 函数                  | 功能                                         |
| --------------------- | -------------------------------------------- |
| get_available_devices | 检测当前可用的计算设备，并返回给前端用于展示 |
| is_cuda_available     | 检查当前本机的 PyTorch 是否可以使用 CUDA GPU |
| resolve_device        | 根据用户选择决定训练实际使用的设备           |
| get_device_summary    | 返回适合在设置面板中展示的 CPU/GPU 信息      |

### backend/model_builder.py

| 函数                  | 功能                                                                   |
| --------------------- | ---------------------------------------------------------------------- |
| build_model           | 将已经通过校验的可视化模型图转换成支持 DAG 前向传播的 PyTorch 模型对象 |
| create_layer          | 根据一个可视化层配置创建对应的 PyTorch 层                              |
| order_layers          | 将画布中的模型节点排序为拓扑执行顺序                                   |
| extract_model_summary | 生成便于展示或调试的模型结构摘要                                       |

### backend/graph_model.py

| 类/函数              | 功能                                                      |
| -------------------- | --------------------------------------------------------- |
| ExecutableGraphModel | 支持有向无环图结构、拓扑执行和多输入合并的 PyTorch 模型类 |

### backend/validator.py

| 函数                    | 功能                                               |
| ----------------------- | -------------------------------------------------- |
| validate_model_graph    | 执行完整模型校验，并返回错误、警告和维度信息       |
| validate_required_nodes | 检查模型图中是否包含 Input、Output 等必要节点      |
| validate_connections    | 检查是否存在缺失、重复、非法或暂不支持的连接关系   |
| validate_layer_params   | 检查某一层的可编辑参数是否合法                     |
| infer_all_shapes        | 按执行顺序推导每一层的输入维度和输出维度           |
| infer_layer_shape       | 根据输入维度和层参数推导某一层的输出维度           |
| infer_conv2d_shape      | 根据通道数、卷积核、步长和填充推导 Conv2D 输出维度 |
| infer_pooling_shape     | 根据池化核、步长和填充推导池化层输出维度           |
| infer_flatten_shape     | 根据多维张量输入推导 Flatten 后的一维向量长度      |
| build_error_message     | 将校验错误转换成适合初学者阅读的解释文本           |

### backend/trainer.py

| 函数                    | 功能                                       |
| ----------------------- | ------------------------------------------ |
| create_training_job     | 在训练开始前创建并登记一个训练任务         |
| run_training_job        | 执行一个已登记训练任务的完整训练流程       |
| prepare_dataset         | 加载并预处理用户选择的内置数据集           |
| train_one_epoch         | 训练一个 epoch，并返回该轮训练指标         |
| evaluate_model          | 评估模型，并返回验证损失和准确率           |
| save_training_artifacts | 保存训练产生的模型权重、指标和日志         |
| get_job_status          | 返回训练任务的当前状态和进度               |
| get_job_result          | 返回已完成训练任务的最终指标和保存文件路径 |
| stop_training_job       | 请求取消一个正在运行的训练任务             |

### backend/code_exporter.py

| 函数                    | 功能                                          |
| ----------------------- | --------------------------------------------- |
| export_to_pytorch       | 根据可视化模型图生成完整的 PyTorch 模型源代码 |
| generate_imports        | 生成导出代码所需的 import 语句                |
| generate_model_class    | 生成导出模型对应的 nn.Module 类主体           |
| generate_layer_code     | 生成某一个 PyTorch 层的源代码                 |
| generate_forward_method | 生成导出 PyTorch 模型的 forward 方法          |
| format_python_code      | 在返回前端之前格式化生成的 Python 代码        |

### backend/templates.py

| 函数                    | 功能                                      |
| ----------------------- | ----------------------------------------- |
| get_available_templates | 返回前端可选择的模型模板，例如 MLP 和 CNN |
| create_mlp_template     | 创建适合初学者使用的 MLP 模板图           |
| create_cnn_template     | 创建适合图像分类任务的入门 CNN 模板图     |
| apply_template          | 返回用户选择的模板图，供前端加载到画布中  |

### backend/graph_utils.py

| 函数                    | 功能                           |
| ----------------------- | ------------------------------ |
| normalize_model_graph   | 将 JSON 字符串或字典统一成字典 |
| topological_sort_layers | 对模型层进行拓扑排序           |
| build_predecessor_map   | 构建每个节点的前驱映射         |
| build_successor_map     | 构建每个节点的后继映射         |

### backend/storage.py（M1）

| 函数                    | 功能                   |
| ----------------------- | ---------------------- |
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
| register_user     | 注册新用户，校验邮箱唯一性并哈希密码 |
| create_user       | 创建新用户（委托给 register_user）   |
| authenticate_user | 验证用户凭据（邮箱+密码）            |
| get_user_by_email | 按邮箱查找用户                       |
| get_user          | 按 id 获取用户信息                   |
| list_users        | 获取所有用户列表                     |
| update_user       | 更新用户信息（用户名/邮箱/密码）     |
| delete_user       | 删除用户及关联的所有项目             |
| get_users_by_ids  | 批量按 id 获取用户信息               |

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
| update_project    | 更新项目信息（名称/模型图/描述）       |
| delete_project    | 删除项目                               |
| get_user_projects | 获取指定用户的所有项目                 |

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
| handleValidateModel       | 将当前模型图发送到后端，并展示结构校验结果   |
| handleSaveProject         | 保存当前模型到项目                           |
| handleExportCode          | 向后端请求生成的 PyTorch 代码，并展示给用户  |
| handleStartTraining       | 将模型图和训练配置发送到后端，启动本地训练   |
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
| fetchDevices        | 向后端请求当前可用的 CPU/GPU 设备                |
| validateModel       | 将可视化模型图发送给后端，用于结构校验和维度推导 |
| startTraining       | 根据选择的数据集、超参数和设备启动本地训练任务   |
| fetchTrainingStatus | 查询训练任务的当前状态和进度                     |
| fetchTrainingResult | 查询已完成训练任务的最终指标和产物信息           |
| exportPytorchCode   | 向后端请求根据模型图生成的 PyTorch 模型代码      |

## 增量开发计划

### 第一阶段：基础训练闭环

- 固定 CNN 或 MLP 模型。
- 支持 MNIST、FashionMNIST、KMNIST、CIFAR10 和 CIFAR100 等内置数据集。
- 使用 CPU 完成本地训练。
- 返回 loss 和 accuracy。

### 第二阶段：CPU/GPU 切换

- 检测本机是否支持 CUDA。
- 前端展示 CPU/GPU 选项。
- 后端根据用户选择切换训练设备。
- GPU 不可用时给出提示或自动降级到 CPU。

### 第三阶段：模型 JSON 构建

- 前端生成统一的模型 JSON。
- 后端接收模型 JSON。
- 后端根据 JSON 构建 PyTorch 模型。

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
- 后端负责模型校验、维度推导、PyTorch 模型构建、训练和代码导出。
- 前后端之间统一使用 JSON 通信。
- 第一版模型构建器按有向无环图进行拓扑执行，支持顺序结构、基础分支汇合和多输入合并；暂不支持环形连接和自定义 Python 层。
- 用户只能选择系统内置层类型，不能直接提交任意 Python 代码。
- GPU 是否可用以后端检测结果为准，前端不能自行假设。
- 新增接口时需要同步更新 backend/main.py 和本 README。
- 新增函数时需要在本 README 中登记函数功能。
- 修改核心 JSON 数据格式时，需要同步更新前端、后端和本 README。

## AI 协作说明

后续使用 AI 辅助开发时，请优先阅读本 README，并遵守以下约定：

- 不要随意改变前后端 JSON 数据结构。
- 新增功能前先确认对应模块职责。
- 后端新增训练相关逻辑优先放在 backend/trainer.py。
- 后端新增模型构建逻辑优先放在 backend/model_builder.py，图模型执行逻辑优先放在 backend/graph_model.py。
- 后端新增维度推导和校验逻辑优先放在 backend/validator.py。
- 后端新增设备相关逻辑优先放在 backend/device.py。
- 后端新增代码导出逻辑优先放在 backend/code_exporter.py。
- 前端新增接口调用时优先封装到 frontend/src/api/client.ts，共享类型放在 frontend/src/types.ts。
- 前端新增页面区块时拆分为 frontend/src/components/ 下的 Vue 组件，跨组件状态放在 frontend/src/store.ts。
- 新增或修改函数后，需要同步更新本 README 中的函数说明。
