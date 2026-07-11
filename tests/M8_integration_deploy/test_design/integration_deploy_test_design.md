# 系统集成、部署与回归模块测试说明（M8）

## 1. 测试目标

验证系统作为一个整体的**可交付性**：前端、云端后端、本机 Agent 三端接口契约稳定、
端到端业务链路走得通；生产部署要素（前端构建、uvicorn 服务、Nginx 反向代理、
SQLite 持久化、CORS、JWT、.env/端口等配置）正确；并对全量自动化测试做一次回归，
记录整体健康状况与失败原因。

## 2. 被测模块和负责代码路径

- `backend/main.py`（整体接口聚合：health / auth / users / projects / templates / validate）
- `backend/cloud_training.py`（Agent 连接与本机应用下载 `/agent/download`）
- `backend/env.py`（.env 加载）、`backend/security.py`（JWT）、`backend/storage.py`（SQLite 持久化）
- `frontend`（`npm run build` 生产构建产物）
- `README.md`（启动命令与部署说明）
- Nginx 反向代理配置、uvicorn 启动配置、SQLite 数据库文件（生产环境）

## 3. 测试范围

- 端到端业务链路：注册 → 登录 → 鉴权 → 建项目 → 查项目 → 结构校验 → 模板 → 基于模板建项目 → 下载本机训练应用。
- 接口契约：`/health`、`/auth/*`、`/projects*`、`/projects/templates*`、`/validate`、`/agent/download` 的状态码与响应结构。
- 部署与配置：CORS 允许/拒绝源、JWT 签发/校验/防篡改、SQLite 重连持久化、.env 加载、前端构建配置与产物、README 与实际启动方式一致。
- 全量回归：`pytest tests/` 汇总通过/失败/跳过。
- 手工验证：Nginx 静态托管与反向代理、WebSocket 长连接、三端联调、uvicorn 生产参数、端口占用、生产 JWT 密钥。

## 4. 不测试的内容

- 各功能模块的内部单元逻辑（属 M1–M7 各自职责：认证细节、画布交互、维度推导公式、训练算子、代码导出内容、模板内部结构）。
- 真实 GPU 训练的数值正确性与收敛性。
- 前端浏览器像素级 UI 与动画（属人员 2 手工验收）。
- 第三方库（FastAPI、SQLAlchemy、PyTorch）自身的正确性。

## 5. 自动化测试用例表

> 代码：`tests/M8_integration_deploy/test_code/test_e2e_flow.py`、`test_deployment_config.py`
> 执行环境：Python 3.12.3、pytest 9.1.1、进程内 FastAPI TestClient、独立临时 SQLite。

| 用例编号 | 测试场景               | 输入数据                                                     | 操作步骤                                                                                    | 预期结果                                                     | 实际输出结果                                                      | 优先级 |
| -------- | ---------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------- | ------ |
| M8-001   | 后端健康检查           | 无                                                           | `GET /health`                                                                             | HTTP 200，`status=ok`                                      | 与预期一致：200，`status=ok`                                    | 高     |
| M8-002   | CORS 允许开发前端源    | Origin=`http://localhost:5173` / `http://127.0.0.1:5173` | 带 Origin 请求`/health`                                                                   | 响应头`access-control-allow-origin` 等于该源               | 与预期一致：两源均被回显放行                                      | 高     |
| M8-003   | 注册→登录→鉴权链路   | 合法 username/email/password/confirm_password                | `POST /auth/register` → `POST /auth/login` → `GET /auth/me`（Bearer）               | 三步均 200；`/auth/me` 返回同一 user id                    | 与预期一致：均 200，user id 匹配                                  | 高     |
| M8-004   | 受保护接口需令牌       | 不带 Authorization                                           | `GET /auth/me`                                                                            | 401 或 403 拦截                                              | 与预期一致：被拦截（403）                                         | 高     |
| M8-005   | 建项目→列表→详情     | 合法 model_graph + Bearer                                    | `POST /projects` → `GET /projects?user_id` → `GET /projects/{id}`                   | 均 200；列表含新项目；详情名称正确                           | 与预期一致：均 200，项目可查                                      | 高     |
| M8-006   | 同用户项目重名失败     | 同名项目提交两次                                             | 连续`POST /projects`                                                                      | 第一次 200，第二次 400                                       | 与预期一致：第二次 400                                            | 高     |
| M8-007   | `/validate` 合法模型 | `Input→Output`，shape `[1,28,28]`                       | `POST /validate`                                                                          | 200，`valid=true`，`errors=[]`                           | 与预期一致：`valid=true`                                        | 高     |
| M8-008   | `/validate` 非法模型 | 缺少 Output 的图                                             | `POST /validate`                                                                          | 200，`valid=false`，`errors` 非空                        | 与预期一致：`valid=false` 且有错误                              | 高     |
| M8-009   | 模板列表数量           | 无                                                           | `GET /projects/templates`                                                                 | 200，`count=11` 且 `data` 长度 11                        | 与预期一致：11 个模板                                             | 中     |
| M8-010   | 基于模板建项目并校验   | `template_name=lenet`                                      | `POST /projects/from-template` → `GET /projects/templates/lenet` → `POST /validate` | 建项目 200；模板图`valid=true`                             | 与预期一致：建项目成功，模板图通过校验                            | 高     |
| M8-011   | 下载本机训练应用       | 登录令牌 +`platform=windows`                               | `GET /agent/download`                                                                     | 200，`Content-Type` 含 zip，内容为可解析 zip               | 与预期一致：返回可解析 zip                                        | 高     |
| M8-012   | JWT 签发/校验往返      | user id                                                      | `create_access_token` → `verify_access_token`                                          | 解出的`sub` 等于原 user id                                 | 与预期一致：`sub` 匹配                                          | 高     |
| M8-013   | 篡改令牌被拒           | 令牌尾部追加字符                                             | `verify_access_token`                                                                     | 抛出异常（校验失败）                                         | 与预期一致：抛异常                                                | 高     |
| M8-014   | SQLite 重连持久化      | 写入用户后释放引擎再重连同库                                 | `save_user` → `dispose` → `configure` → `get_user`                               | 数据仍在，库文件已落盘                                       | 与预期一致：重连后仍可读到用户                                    | 高     |
| M8-015   | .env 加载不崩溃        | 有/无 .env 文件                                              | 调用`load_dotenv_if_present()`                                                            | 正常返回、不抛异常                                           | 与预期一致：无异常                                                | 中     |
| M8-016   | 前端构建配置/产物      | 无                                                           | 检查`package.json` build 脚本、vite 配置；若已构建则校验 dist                             | 存在 build 脚本与 vite 配置；dist（若有）引用 hash 化 js/css | 与预期一致：配置齐全，dist 产物结构正确                           | 高     |
| M8-017   | README 与启动方式一致  | 无                                                           | 检索 README                                                                                 | 含`uvicorn`、`backend.main:app`、`Nginx`               | 与预期一致：均记录                                                | 中     |
| M8-018   | 全量自动化回归         | 无                                                           | `python -m pytest tests/ -q`                                                              | 汇总通过/失败/跳过（见第 8 节）                              | 255 passed / 6 failed（失败均为 M1、M7 既有过时用例，非 M8 引入） | 高     |

**自动化执行结论**：M8 自身 19 条用例（M8-001 ~ M8-017 对应）**全部通过**
（`19 passed`）。

## 6. 手工部署验证清单

| 编号 | 验证项               | 操作步骤                                                                                 | 预期结果                                     | 结果                                             |
| ---- | -------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| D-01 | Nginx 静态托管       | 浏览器访问`https://fk.kanzakiyui.com/`                                                 | 前端页面正常加载，刷新任意前端路由不 404     | 通过                                             |
| D-02 | Nginx API 反向代理   | `curl https://fk.kanzakiyui.com/health`                                                | 返回`{"status":"ok"}`                      | 通过（HTTP 200）                                 |
| D-03 | Nginx WebSocket 反代 | 前端客户端 WS`/client/ws`、Agent WS `/agents/ws`                                     | Upgrade 成功、长连接不被中断                 | 通过                                             |
| D-04 | uvicorn 生产参数     | `--host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=*`（systemd 常驻） | 服务 active，`request.base_url` 为真实域名 | 通过                                             |
| D-05 | 三端端到端           | 浏览器登录→搭模型→检查结构→（本机 Agent 在线）启动训练→看监控→导出代码              | 全链路走通                                   | 结构校验/导出：通过；训练需本机 Agent 在线时验证 |
| D-06 | SQLite 持久化        | 重启`visualdl` 服务后重新登录、查项目                                                  | 用户与项目数据仍在                           | 通过                                             |
| D-07 | 生产 JWT 密钥        | 检查`.env` 的 `JWT_SECRET_KEY` 非默认 `dev-secret-key-change-in-production`        | 使用独立强密钥                               | 需运维核对                                       |
| D-08 | 端口占用             | 部署前确认 8000 端口未被占用                                                             | uvicorn 正常绑定                             | 通过                                             |

## 7. 生产部署记录

| 项           | 值                                                                                                                                                           |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 访问地址     | `https://fk.kanzakiyui.com`（Nginx + certbot HTTPS）                                                                                                       |
| 前端产物     | `frontend/dist/` → 部署到 `/var/www/fk.kanzakiyui.com/`（`npm run build`）                                                                            |
| 后端启动     | `uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=*`（systemd 服务 `visualdl`，单进程以保证内存态注册表一致） |
| 反向代理     | Nginx location 正则转发`^/(health\|auth\|users\|projects\|train\|runtime\|agents\|agent\|client\|validate)` 到 uvicorn，并带 WebSocket Upgrade 头                   |
| 数据库       | SQLite（`DATABASE_URL` 或默认路径）；生产可通过环境变量切换                                                                                                |
| 关键环境变量 | `JWT_SECRET_KEY`、`DATABASE_URL`、`AGENT_DIST_DIR`（本机应用发布目录）                                                                                 |
| 本机应用发布 | `backend/agent_dist/<平台>/VisualDL-Agent.zip`，`/agent/download` 注入令牌后发放                                                                         |

## 8. 全量回归记录

执行：`python -m pytest tests/ -q`（torch 2.12.1 可用）。

- 总计：**255 passed，6 failed，29 subtests passed**（用时约 50s）。
- **M8 自身：全部通过。**
- 6 个失败**均非 M8 引入**，是既有模块中「测试代码落后于接口演进」导致，建议对应负责人更新：

| 失败用例                                                           | 所属 | 根因                                                                                  | 建议                 |
| ------------------------------------------------------------------ | ---- | ------------------------------------------------------------------------------------- | -------------------- |
| `test_api.py::TestInfraRoutes::test_devices_returns_device_info` | M1   | `GET /devices` 已返回 404——该接口已移除，设备信息改由本机 Agent 经 WebSocket 上报 | 删除/改写该用例      |
| `test_api.py::TestInfraRoutes::test_train_creates_job`           | M1   | `POST /train` 返回 422——训练请求 schema 已变更                                    | 按新 schema 更新用例 |
| `test_templates_integration.py`（4 项）                          | M7   | `create_user` 辅助函数未传 `password`/`confirm_password`，注册接口返回 422      | 更新测试辅助函数字段 |

> 说明：以上失败属 M1/M7 测试维护问题，不影响本次 M8 的集成与部署验收结论。

## 9. 预期结果

- 端到端业务链路各接口状态码与响应结构稳定、可复现。
- CORS 只放行开发前端源；JWT 可签发、可校验、篡改被拒。
- SQLite 数据在服务重启（引擎重连）后仍可读取。
- 前端可生产构建，产物为 hash 化静态资源；Nginx 能托管并反代 API/WS。
- README 启动命令与真实部署一致。
- 全量回归结果被完整记录，失败项有明确根因与归属。

## 10. 异常情况考虑

- 后端未启动：前端接口调用应失败但页面不崩溃（属人员 2 前端容错）。
- 本机 Agent 未连接：结构校验/导出仍可用（云端纯 Python），训练需提示先连 Agent。
- Token 无效/过期：受保护接口返回 401/403。
- 端口占用：uvicorn 启动失败需明确报错。
- 生产误用默认 JWT 密钥：安全隐患，D-07 专项核对。

## 11. 运行方式

```bash
# M8 自动化（端到端 + 部署配置）
python -m pytest tests/M8_integration_deploy/test_code/ -q

# 全量回归（等价入口）
python tests/M8_integration_deploy/test_code/run_regression.py
# 或
python -m pytest tests/ -q

# 前端生产构建
cd frontend && npm run build

# 后端生产启动
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```
