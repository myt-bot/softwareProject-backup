# M1 用户与项目管理模块 —— 测试设计文档

> 编写者：甘淞文
> 日期：2026-06-30
> 更新：2026-07-16（新增安全模块测试 `test_security.py`；补充用户/项目接口鉴权、越权与健壮性用例；测试用例编号统一为 `M1-xxx` 顺序编号，与 M8 风格对齐）

---

## 一、测试概述

### 1.1 测试目标

验证「用户与项目管理模块」各层代码的正确性、稳定性和异常处理能力，覆盖：

- 数据库存储层的 CRUD 操作、数据库约束（唯一键/外键）与并发安全
- 用户管理业务逻辑的正常路径和异常路径（含注册确认密码校验）
- 项目管理业务逻辑的正常路径、异常路径和权限控制
- 安全模块：JWT 令牌签发/校验/过期/防篡改、bcrypt 密码哈希（`test_security.py`）
- FastAPI HTTP 接口的请求/响应正确性，以及接口鉴权与越权防护（登录校验、所有权/本人限制）

### 1.2 测试框架

- Python `unittest` 标准库（兼容 `pytest` 运行）
- FastAPI `TestClient`（API 集成测试）

### 1.3 测试隔离机制

生产环境存储层使用 MySQL（连接串由环境变量 `DATABASE_URL` 配置）。测试不依赖
MySQL 服务：每个测试类/用例通过 `storage.configure_database()` 将存储切换到
**临时目录下的独立 SQLite 库**，表结构与约束（邮箱唯一、同用户项目名唯一、
外键级联）由同一份 SQLAlchemy 定义生成，测试结束后 `storage.dispose_database()`
释放引擎并清理临时目录，用例之间数据完全隔离。

### 1.4 测试运行方式

```bash
# 运行全部测试（pytest 方式，推荐）
python -m pytest tests/M1_user_project/test_code/ -q

# 运行全部测试（unittest 入口）
python tests/M1_user_project/test_code/run_all.py

# 单独运行某个测试文件
python tests/M1_user_project/test_code/test_storage.py
python tests/M1_user_project/test_code/test_auth.py
python tests/M1_user_project/test_code/test_projects.py
python tests/M1_user_project/test_code/test_security.py
python tests/M1_user_project/test_code/test_api.py
```

---

## 二、测试文件结构

```
tests/M1_user_project/
├── test_code/
│   ├── __init__.py              # 包声明
│   ├── run_all.py               # 测试运行入口
│   ├── test_storage.py          # 数据库存储层单元测试（22 用例）
│   ├── test_auth.py             # 用户与认证模块单元测试（44 用例）
│   ├── test_projects.py         # 项目管理单元测试（31 用例）
│   ├── test_security.py         # 安全模块单元测试：JWT / 密码哈希（16 用例）
│   └── test_api.py              # API 集成测试（52 用例）
└── test_design/
    └── user_project_test_design.md   # 本文档
```

---

## 三、测试用例设计

> 编号规则：全模块统一采用 `M1-xxx` 顺序编号（存储 M1-001~022、认证 M1-023~066、
> 项目 M1-067~097、安全 M1-098~113、API M1-114~165），编号自带模块号，便于跨文档引用。

### 3.1 存储层测试（test_storage.py，M1-001 ~ M1-022，共 22 用例）

#### 用户/项目 CRUD

| 编号 | 测试用例 | 类型 | 说明 |
|------|----------|------|------|
| M1-001 | test_save_and_get_user | 正常 | 保存用户后能正确获取 |
| M1-002 | test_get_nonexistent_user | 边界 | 获取不存在的用户返回 None |
| M1-003 | test_list_users_empty | 边界 | 空用户列表 |
| M1-004 | test_list_users_with_filter | 正常 | 按字段过滤用户 |
| M1-005 | test_update_user | 正常 | 更新用户部分字段 |
| M1-006 | test_update_nonexistent_user | 异常 | 更新不存在用户返回 None |
| M1-007 | test_delete_user | 正常 | 删除用户成功 |
| M1-008 | test_delete_nonexistent_user | 异常 | 删除不存在用户返回 False |
| M1-009 | test_user_exists | 正常 | 用户存在性检查 |
| M1-010 | test_save_and_get_project | 正常 | 保存项目后能正确获取（含 JSON 模型图完整往返） |
| M1-011 | test_get_nonexistent_project | 边界 | 获取不存在的项目返回 None |
| M1-012 | test_list_projects_by_user | 正常 | 按用户过滤项目 |
| M1-013 | test_update_project | 正常 | 更新项目字段 |
| M1-014 | test_delete_project | 正常 | 删除项目成功 |
| M1-015 | test_delete_projects_by_user | 正常 | 按用户批量删除项目 |

#### 持久化与数据库约束（并发兜底）

| 编号 | 测试用例 | 类型 | 说明 |
|------|----------|------|------|
| M1-016 | test_data_persists_across_reconnect | 正常 | 数据落库后重建连接仍可读取（模拟服务重启） |
| M1-017 | test_duplicate_email_rejected_by_db | 约束 | 邮箱唯一约束：重复邮箱被数据库拒绝 → ValueError |
| M1-018 | test_duplicate_project_name_rejected_by_db | 约束 | 同用户下项目名唯一约束 → ValueError |
| M1-019 | test_same_project_name_allowed_for_different_users | 约束 | 不同用户可使用相同项目名 |
| M1-020 | test_project_with_nonexistent_user_rejected_by_db | 约束 | 外键约束：所属用户不存在的项目被拒绝 → ValueError |

#### 并发安全

| 编号 | 测试用例 | 类型 | 说明 |
|------|----------|------|------|
| M1-021 | test_concurrent_writes | 并发 | 20 线程并发写入不丢失数据（并发正确性以 MySQL 回归为准） |
| M1-022 | test_concurrent_read_write | 并发 | 多线程读写混合操作数据不损坏 |

### 3.2 认证模块测试（test_auth.py，M1-023 ~ M1-066，共 44 用例）

#### 正常路径

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-023 | test_create_user_success | 正常创建用户，检查 id 格式和字段完整性 |
| M1-024 | test_create_user_with_chinese_name | 中文用户名支持 |
| M1-025 | test_create_user_trims_whitespace | 用户名/邮箱自动去除首尾空格 |
| M1-026 | test_get_user_exists | 获取存在的用户 |
| M1-027 | test_get_user_not_exists | 获取不存在的用户返回 None |
| M1-028 | test_list_users | 列出所有用户 |
| M1-029 | test_list_users_empty | 空列表场景 |
| M1-030 | test_update_user_username | 仅更新用户名 |
| M1-031 | test_update_user_email | 仅更新邮箱 |
| M1-032 | test_update_user_password | 仅更新密码 |
| M1-033 | test_update_user_both | 同时更新用户名和邮箱 |
| M1-034 | test_delete_user_success | 正常删除用户 |
| M1-035 | test_register_user_success | register_user 正常注册 |
| M1-036 | test_authenticate_user_success | 邮箱+密码正确登录成功 |
| M1-037 | test_authenticate_user_wrong_password | 错误密码登录失败 |
| M1-038 | test_authenticate_user_nonexistent | 邮箱未注册登录失败 |
| M1-039 | test_authenticate_user_empty_credentials | 空邮箱/密码返回 None |
| M1-040 | test_authenticate_user_trims_whitespace | 邮箱首尾空格正确处理 |

#### 异常路径 —— 创建

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-041 | test_create_user_empty_username | 空用户名 → ValueError |
| M1-042 | test_create_user_none_username | None 用户名 → ValueError |
| M1-043 | test_create_user_too_short_username | 单字符用户名 → ValueError |
| M1-044 | test_create_user_too_long_username | 超长用户名 → ValueError |
| M1-045 | test_create_user_special_char_username | 特殊字符用户名 → ValueError |
| M1-046 | test_create_user_invalid_email | 非法邮箱 → ValueError |
| M1-047 | test_create_user_empty_email | 空邮箱 → ValueError |
| M1-048 | test_create_user_empty_password | 空密码 → ValueError |
| M1-049 | test_create_user_none_password | None 密码 → ValueError |
| M1-050 | test_create_user_short_password | 过短密码 → ValueError |
| M1-051 | test_create_user_password_no_letter | 无字母密码 → ValueError |
| M1-052 | test_create_user_password_no_digit | 无数字密码 → ValueError |
| M1-053 | test_create_user_duplicate_email | 重复邮箱 → ValueError（邮箱唯一） |
| M1-054 | test_create_user_duplicate_email_whitespace_bypass | 空格绕过邮箱唯一性检查 |
| M1-055 | test_create_user_duplicate_username_allowed | 相同用户名+不同邮箱注册成功（用户名可重复） |

#### 确认密码校验（注册增强）

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-056 | test_register_user_confirm_password_match | 确认密码一致时注册成功 |
| M1-057 | test_register_user_confirm_password_mismatch | 确认密码不一致 → ValueError（提示"两次输入的密码不一致"） |
| M1-058 | test_register_user_confirm_password_empty_mismatch | 确认密码为空字符串（与密码不一致）→ ValueError |
| M1-059 | test_register_user_without_confirm_password | 不传确认密码时跳过一致性校验（兼容内部创建用户场景） |

#### 异常路径 —— 获取/更新/删除

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-060 | test_get_user_empty_id | 空 id 获取 → ValueError |
| M1-061 | test_get_user_none_id | None id 获取 → ValueError |
| M1-062 | test_update_nonexistent_user | 更新不存在用户 → ValueError |
| M1-063 | test_update_user_no_fields | 无更新字段 → ValueError |
| M1-064 | test_update_user_duplicate_email | 更新为已存在邮箱 → ValueError |
| M1-065 | test_delete_nonexistent_user | 删除不存在用户 → ValueError |
| M1-066 | test_delete_user_empty_id | 空 id 删除 → ValueError |

### 3.3 项目管理测试（test_projects.py，M1-067 ~ M1-097，共 31 用例）

#### 正常路径

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-067 | test_create_project_success | 正常创建项目 |
| M1-068 | test_create_project_without_description | 不提供描述也能创建 |
| M1-069 | test_get_project_exists | 获取存在的项目 |
| M1-070 | test_get_project_not_exists | 获取不存在的项目返回 None |
| M1-071 | test_list_projects_all | 列出所有项目 |
| M1-072 | test_list_projects_by_user | 按用户过滤 |
| M1-073 | test_update_project_name | 更新名称 |
| M1-074 | test_update_project_model_graph | 更新模型图 |
| M1-075 | test_update_project_description | 更新描述 |
| M1-076 | test_delete_project_success | 正常删除 |
| M1-077 | test_create_project_with_current_user_id | 带 current_user_id 为自己创建项目 |

#### 权限控制

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-078 | test_create_project_cross_user_rejected | 用户 A 不能以用户 B 身份创建项目 → PermissionError |
| M1-079 | test_update_project_wrong_owner_rejected | 非所有者不能修改项目 → PermissionError |
| M1-080 | test_delete_project_wrong_owner_rejected | 非所有者不能删除项目 → PermissionError |

#### 异常路径 —— 创建

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-081 | test_create_project_invalid_user | 用户不存在 |
| M1-082 | test_create_project_empty_user_id | 空 user_id |
| M1-083 | test_create_project_empty_name | 空项目名 |
| M1-084 | test_create_project_none_name | None 项目名 |
| M1-085 | test_create_project_too_long_name | 超长名称 |
| M1-086 | test_create_project_duplicate_name | 同用户下重名 |
| M1-087 | test_create_project_none_model_graph | None 模型图 |
| M1-088 | test_create_project_invalid_model_graph_not_dict | 非字典模型图 |
| M1-089 | test_create_project_invalid_model_graph_no_layers | 缺少 layers |
| M1-090 | test_create_project_invalid_model_graph_layers_not_list | layers 非列表 |
| M1-091 | test_create_project_too_long_description | 超长描述 |

#### 异常路径 —— 获取/更新/删除

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-092 | test_get_project_empty_id | 空 project_id |
| M1-093 | test_update_nonexistent_project | 更新不存在项目 |
| M1-094 | test_update_project_no_fields | 无更新字段 |
| M1-095 | test_update_project_duplicate_name | 重名冲突 |
| M1-096 | test_delete_nonexistent_project | 删除不存在项目 |
| M1-097 | test_delete_project_empty_id | 空 id 删除 |

### 3.4 安全模块测试（test_security.py，M1-098 ~ M1-113，共 16 用例）

> 直接对 `backend/security.py` 的 JWT 令牌与 bcrypt 密码哈希逻辑做单元测试，
> 对应《测试计划》M1 用例 TC1-09~12。

#### 密码哈希与校验（bcrypt）

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-098 | test_hash_differs_from_plaintext | 哈希结果不等于明文 |
| M1-099 | test_hash_is_salted | 同一密码两次哈希结果不同（加盐） |
| M1-100 | test_hash_uses_bcrypt_scheme | 哈希串使用 bcrypt 方案标识（$2...） |
| M1-101 | test_verify_correct_password | 正确密码校验通过 |
| M1-102 | test_verify_wrong_password | 错误密码校验失败 |

#### JWT 签发与校验

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-103 | test_token_is_three_segments | 令牌为三段式（header.payload.signature） |
| M1-104 | test_verify_returns_matching_sub | 校验后 sub 与签发用户 id 一致 |
| M1-105 | test_payload_contains_exp_and_iat | payload 含过期时间 exp 与签发时间 iat |
| M1-106 | test_roundtrip_valid_token | 合法令牌签发再校验往返正常 |

#### JWT 过期与防篡改

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-107 | test_expired_token_rejected | 过期令牌校验返回 401 |
| M1-108 | test_tampered_token_rejected | 被篡改（签名段被改）令牌返回 401 |
| M1-109 | test_wrong_secret_token_rejected | 用其它密钥签发的令牌返回 401 |
| M1-110 | test_missing_sub_token_rejected | 缺少 sub 的令牌返回 401 |
| M1-111 | test_garbage_token_rejected | 非法字符串（非 JWT）返回 401 |

#### 令牌对应用户失效

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| M1-112 | test_valid_token_existing_user_returns_user | 有效令牌且用户存在时返回对应用户 |
| M1-113 | test_valid_token_deleted_user_rejected | 令牌有效但用户已被删除时返回 401 |

### 3.5 API 集成测试（test_api.py，M1-114 ~ M1-165，共 52 用例）

> 缺陷修复后，用户增删改（`/users`）需登录且仅限本人；只读接口与项目接口增加了
> 未登录（401）、越权（403）与健壮性（超大输入/畸形结构/注入样式）用例。

#### 用户接口（含鉴权与越权）

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /users | M1-114 | test_create_user_success（需登录） |
| POST | /users | M1-115 | test_create_user_no_auth（未登录 → 401） |
| POST | /users | M1-116 | test_create_user_invalid_email |
| POST | /users | M1-117 | test_create_user_duplicate |
| POST | /users | M1-118 | test_create_user_missing_field |
| GET | /users | M1-119 | test_list_users_self_only（只返回本人） |
| GET | /users | M1-120 | test_list_users_no_auth（未登录 → 401） |
| GET | /users/{id} | M1-121 | test_get_user_self |
| GET | /users/{id} | M1-122 | test_get_user_other_forbidden（越权 → 403） |
| GET | /users/{id} | M1-123 | test_get_user_no_auth（未登录 → 401） |
| PUT | /users/{id} | M1-124 | test_update_user_self |
| PUT | /users/{id} | M1-125 | test_update_user_other_forbidden（越权 → 403） |
| PUT | /users/{id} | M1-126 | test_update_user_no_auth（未登录 → 401） |
| DELETE | /users/{id} | M1-127 | test_delete_user_self |
| DELETE | /users/{id} | M1-128 | test_delete_user_other_forbidden（越权 → 403） |
| DELETE | /users/{id} | M1-129 | test_delete_user_no_auth（未登录 → 401） |

#### 认证接口

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /auth/register | M1-130 | test_register_success（含 confirm_password） |
| POST | /auth/register | M1-131 | test_register_duplicate_email |
| POST | /auth/register | M1-132 | test_register_weak_password |
| POST | /auth/register | M1-133 | test_register_password_mismatch（两次密码不一致 → 400） |
| POST | /auth/register | M1-134 | test_register_missing_confirm_password（缺少确认密码 → 422） |
| POST | /auth/login | M1-135 | test_login_success |
| POST | /auth/login | M1-136 | test_login_wrong_password |
| POST | /auth/login | M1-137 | test_login_nonexistent_user |
| GET | /auth/me | M1-138 | test_get_me_success |
| GET | /auth/me | M1-139 | test_get_me_no_token |
| GET | /auth/me | M1-140 | test_get_me_invalid_token |

#### 项目接口（含鉴权、越权与健壮性）

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /projects | M1-141 | test_create_project_success |
| POST | /projects | M1-142 | test_create_project_no_auth（未登录 → 401） |
| POST | /projects | M1-143 | test_create_project_cross_user_rejected（越权 → 403） |
| POST | /projects | M1-144 | test_create_project_invalid_user |
| POST | /projects | M1-145 | test_create_project_empty_name |
| POST | /projects | M1-146 | test_create_project_missing_field |
| GET | /projects | M1-147 | test_list_projects（按 token 过滤本人项目） |
| GET | /projects | M1-148 | test_list_projects_no_auth（未登录 → 401） |
| GET | /projects/{id} | M1-149 | test_get_project_exists |
| GET | /projects/{id} | M1-150 | test_get_project_not_found |
| GET | /projects/{id} | M1-151 | test_get_project_no_auth（未登录 → 401） |
| GET | /projects/{id} | M1-152 | test_get_project_wrong_owner_rejected（越权 → 403） |
| PUT | /projects/{id} | M1-153 | test_update_project_success |
| PUT | /projects/{id} | M1-154 | test_update_project_not_found |
| PUT | /projects/{id} | M1-155 | test_update_project_wrong_owner_rejected（越权 → 403） |
| DELETE | /projects/{id} | M1-156 | test_delete_project_success |
| DELETE | /projects/{id} | M1-157 | test_delete_project_not_found |
| DELETE | /projects/{id} | M1-158 | test_delete_project_wrong_owner_rejected（越权 → 403） |
| POST | /projects | M1-159 | test_oversized_project_name_rejected（名称 >100 → 400） |
| POST | /projects | M1-160 | test_oversized_description_rejected（描述 >500 → 400） |
| POST | /projects | M1-161 | test_malformed_model_graph_rejected（缺 layers → 422） |
| POST | /projects | M1-162 | test_injection_like_name_stored_literally（注入样式名原样存储，参数化查询防注入） |

#### 基础设施路由

| 方法 | 路径 | 编号 | 测试用例 | 备注 |
|------|------|------|----------|------|
| GET | /health | M1-163 | test_health_returns_ok | 通过 |
| GET | /devices | M1-164 | test_devices_returns_device_info | 已知失败：`/devices` 接口已下线（设备信息改由本机 Agent 经 WebSocket 上报），待改写 |
| POST | /train | M1-165 | test_train_creates_job | 已知失败：`/train` 请求 schema 已变更，待按新 schema 更新 |

---

## 四、覆盖率统计

| 模块 | 测试文件 | 用例数 | 结果 |
|------|----------|--------|------|
| storage.py | test_storage.py | 22 | ✅ 全通过 |
| auth.py | test_auth.py | 44 | ✅ 全通过 |
| projects.py | test_projects.py | 31 | ✅ 全通过 |
| security.py | test_security.py | 16 | ✅ 全通过 |
| main.py (M1 API) | test_api.py | 52 | 50 ✅ / 2 已知失败（M1-164、M1-165 接口演进，非本模块逻辑缺陷） |
| **合计** | | **165** | **163 通过 / 2 已知失败** |

> 说明：M1-164、M1-165 分别测 `/devices`、`/train`，这两个接口已随其它模块演进而变更/下线，
> 属"测试代码落后于接口演进"，与用户/项目管理逻辑无关，待对应用例改写。

---

## 五、异常覆盖矩阵

| 异常类型 | 场景数 | 覆盖模块 |
|----------|--------|----------|
| ValueError（参数不合法/密码不一致） | 30+ | auth, projects |
| 数据库唯一键约束（邮箱、同用户项目名） | 3 | storage（并发兜底，业务层预检查之外的最后防线） |
| 数据库外键约束（项目所属用户） | 1 | storage |
| 401 Unauthorized（登录失败、缺少/无效/过期/篡改令牌、未登录访问受保护接口） | 约 17 | security, API |
| 403 Forbidden（跨用户操作项目、越权查看/修改/删除他人账号与项目） | 7 | API |
| 404 Not Found（用户/项目不存在、邮箱未注册） | 3 | API |
| 422 Unprocessable（Pydantic 校验：缺必填字段/缺确认密码/畸形 model_graph） | 4 | API |
| 健壮性（超大名称/描述、注入样式输入、畸形结构） | 4 | API |
| JWT 与密码哈希安全（签发/校验/过期/防篡改/用户失效、bcrypt 加盐） | 16 | security |
| 并发写入冲突 | 2 | storage |

---

## 六、后续测试计划

1. ~~数据库迁移测试：从 JSON 迁移到数据库后回归测试~~（已完成：2026-07-06 迁移至 MySQL，全量回归通过）
2. **MySQL 方言全量回归**：当前测试基于 SQLite 隔离库，交付前将 `DATABASE_URL` 指向真实 MySQL 再跑一轮完整回归（并发用例 M1-021/M1-022、约束用例的方言差异以此为准）。
3. **性能测试**：大量用户/项目数据下的读写性能与分页需求评估（`list_projects` 目前未分页）。
4. **前端集成测试**：前端页面通过 API 完成用户注册（含确认密码）和项目保存的端到端流程（由 M8 集成测试覆盖）。
5. **安全测试**：~~JWT 签发/校验/过期/防篡改、密码哈希~~（已完成：`test_security.py`）；~~输入注入、超大数据体、畸形 JSON 结构基础用例~~（已完成：M1-159~M1-162）；剩余系统性渗透测试（更复杂的注入面、超大并发、登录限流/验证码）作为已知限制，后续按需补充。
