# M1 用户与项目管理模块 —— 测试设计文档

> 编写者：甘淞文
> 日期：2026-06-30

---

## 一、测试概述

### 1.1 测试目标

验证「用户与项目管理模块」各层代码的正确性、稳定性和异常处理能力，覆盖：

- 本地 JSON 存储层的 CRUD 操作与并发安全
- 用户管理业务逻辑的正常路径和异常路径
- 项目管理业务逻辑的正常路径和异常路径
- FastAPI HTTP 接口的请求/响应正确性

### 1.2 测试框架

- Python `unittest` 标准库
- FastAPI `TestClient`（API 集成测试）

### 1.3 测试运行方式

```bash
# 运行全部测试
python tests\M1_user_project\test_code\run_all.py

# 单独运行某个测试文件
python tests\M1_user_project\test_code\test_storage.py
python tests\M1_user_project\test_code\test_auth.py
python tests\M1_user_project\test_code\test_projects.py
python tests\M1_user_project\test_code\test_api.py
```

---

## 二、测试文件结构

```
tests/M1_user_project/
├── test_code/
│   ├── __init__.py              # 包声明
│   ├── run_all.py               # 测试运行入口
│   ├── test_storage.py          # 存储层单元测试（19 用例）
│   ├── test_auth.py     # 用户与认证模块单元测试（40 用例）
│   ├── test_projects.py  # 项目管理单元测试（31 用例）
│   └── test_api.py              # API 集成测试（39 用例）
└── test_design/
    └── 测试设计文档.md           # 本文档
```

---

## 三、测试用例设计

### 3.1 存储层测试（test_storage.py）

| 编号 | 测试用例 | 类型 | 说明 |
|------|----------|------|------|
| S01 | test_save_and_get_user | 正常 | 保存用户后能正确获取 |
| S02 | test_get_nonexistent_user | 边界 | 获取不存在的用户返回 None |
| S03 | test_list_users_empty | 边界 | 空用户列表 |
| S04 | test_list_users_with_filter | 正常 | 按字段过滤用户 |
| S05 | test_update_user | 正常 | 更新用户部分字段 |
| S06 | test_update_nonexistent_user | 异常 | 更新不存在用户返回 None |
| S07 | test_delete_user | 正常 | 删除用户成功 |
| S08 | test_delete_nonexistent_user | 异常 | 删除不存在用户返回 False |
| S09 | test_user_exists | 正常 | 用户存在性检查 |
| S10 | test_save_and_get_project | 正常 | 保存项目后能正确获取 |
| S11 | test_get_nonexistent_project | 边界 | 获取不存在的项目返回 None |
| S12 | test_list_projects_by_user | 正常 | 按用户过滤项目 |
| S13 | test_update_project | 正常 | 更新项目字段 |
| S14 | test_delete_project | 正常 | 删除项目成功 |
| S15 | test_delete_projects_by_user | 正常 | 按用户批量删除项目 |
| S16 | test_data_persists_on_disk | 正常 | 数据正确写入磁盘 JSON |
| S17 | test_concurrent_writes | 并发 | 20 线程并发写入不丢失数据 |

### 3.2 认证模块测试（test_auth.py）

#### 正常路径

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| U01 | test_create_user_success | 正常创建用户，检查 id 格式和字段完整性 |
| U02 | test_create_user_with_chinese_name | 中文用户名支持 |
| U03 | test_create_user_trims_whitespace | 用户名/邮箱自动去除首尾空格 |
| U04 | test_get_user_exists | 获取存在的用户 |
| U05 | test_get_user_not_exists | 获取不存在的用户返回 None |
| U06 | test_list_users | 列出所有用户 |
| U07 | test_list_users_empty | 空列表场景 |
| U08 | test_update_user_username | 仅更新用户名 |
| U09 | test_update_user_email | 仅更新邮箱 |
| U10 | test_update_user_password | 仅更新密码 |
| U11 | test_update_user_both | 同时更新用户名和邮箱 |
| U12 | test_delete_user_success | 正常删除用户 |
| U14 | test_register_user_success | register_user 正常注册 |
| U15 | test_authenticate_user_success | 邮箱+密码正确登录成功 |
| U16 | test_authenticate_user_wrong_password | 错误密码登录失败 |
| U17 | test_authenticate_user_nonexistent | 邮箱未注册登录失败 |
| U18 | test_authenticate_user_empty_credentials | 空邮箱/密码返回 None |
| U19 | test_authenticate_user_trims_whitespace | 邮箱首尾空格正确处理 |

#### 异常路径 —— 创建

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| U20 | test_create_user_empty_username | 空用户名 → ValueError |
| U21 | test_create_user_none_username | None 用户名 → ValueError |
| U22 | test_create_user_too_short_username | 单字符用户名 → ValueError |
| U23 | test_create_user_too_long_username | 超长用户名 → ValueError |
| U24 | test_create_user_special_char_username | 特殊字符用户名 → ValueError |
| U25 | test_create_user_invalid_email | 非法邮箱 → ValueError |
| U26 | test_create_user_empty_email | 空邮箱 → ValueError |
| U27 | test_create_user_empty_password | 空密码 → ValueError |
| U28 | test_create_user_none_password | None 密码 → ValueError |
| U29 | test_create_user_short_password | 过短密码 → ValueError |
| U30 | test_create_user_password_no_letter | 无字母密码 → ValueError |
| U31 | test_create_user_password_no_digit | 无数字密码 → ValueError |
| U32 | test_create_user_duplicate_email | 重复邮箱 → ValueError（邮箱唯一） |
| U33 | test_create_user_duplicate_email_whitespace_bypass | 空格绕过邮箱唯一性检查 |
| U34 | test_create_user_duplicate_username_allowed | 相同用户名+不同邮箱注册成功（用户名可重复） |

#### 异常路径 —— 获取/更新/删除

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| U35 | test_get_user_empty_id | 空 id 获取 → ValueError |
| U36 | test_get_user_none_id | None id 获取 → ValueError |
| U37 | test_update_nonexistent_user | 更新不存在用户 → ValueError |
| U38 | test_update_user_no_fields | 无更新字段 → ValueError |
| U39 | test_update_user_duplicate_email | 更新为已存在邮箱 → ValueError |
| U40 | test_delete_nonexistent_user | 删除不存在用户 → ValueError |
| U41 | test_delete_user_empty_id | 空 id 删除 → ValueError |

### 3.3 项目管理测试（test_projects.py）

#### 正常路径

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| P01 | test_create_project_success | 正常创建项目 |
| P02 | test_create_project_without_description | 不提供描述也能创建 |
| P03 | test_get_project_exists | 获取存在的项目 |
| P04 | test_get_project_not_exists | 获取不存在的项目返回 None |
| P05 | test_list_projects_all | 列出所有项目 |
| P06 | test_list_projects_by_user | 按用户过滤 |
| P07 | test_update_project_name | 更新名称 |
| P08 | test_update_project_model_graph | 更新模型图 |
| P09 | test_update_project_description | 更新描述 |
| P10 | test_delete_project_success | 正常删除 |

#### 异常路径 —— 创建

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| P12 | test_create_project_invalid_user | 用户不存在 |
| P13 | test_create_project_empty_user_id | 空 user_id |
| P14 | test_create_project_empty_name | 空项目名 |
| P15 | test_create_project_none_name | None 项目名 |
| P16 | test_create_project_too_long_name | 超长名称 |
| P17 | test_create_project_duplicate_name | 同用户下重名 |
| P18 | test_create_project_none_model_graph | None 模型图 |
| P19 | test_create_project_invalid_model_graph_not_dict | 非字典模型图 |
| P20 | test_create_project_invalid_model_graph_no_layers | 缺少 layers |
| P21 | test_create_project_invalid_model_graph_layers_not_list | layers 非列表 |
| P22 | test_create_project_too_long_description | 超长描述 |

#### 异常路径 —— 获取/更新/删除

| 编号 | 测试用例 | 说明 |
|------|----------|------|
| P23 | test_get_project_empty_id | 空 project_id |
| P24 | test_update_nonexistent_project | 更新不存在项目 |
| P25 | test_update_project_no_fields | 无更新字段 |
| P26 | test_update_project_duplicate_name | 重名冲突 |
| P27 | test_delete_nonexistent_project | 删除不存在项目 |
| P28 | test_delete_project_empty_id | 空 id 删除 |

### 3.4 API 集成测试（test_api.py）

#### 用户接口

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /users | A01 | test_create_user_success |
| POST | /users | A02 | test_create_user_invalid_email |
| POST | /users | A03 | test_create_user_duplicate |
| POST | /users | A04 | test_create_user_missing_field |
| GET | /users | A05 | test_list_users |
| GET | /users/{id} | A06 | test_get_user_exists |
| GET | /users/{id} | A07 | test_get_user_not_found |
| PUT | /users/{id} | A08 | test_update_user_success |
| PUT | /users/{id} | A09 | test_update_user_not_found |
| DELETE | /users/{id} | A10 | test_delete_user_success |
| DELETE | /users/{id} | A11 | test_delete_user_not_found |

#### 认证接口

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /auth/register | A12 | test_register_success |
| POST | /auth/register | A13 | test_register_duplicate_email |
| POST | /auth/register | A14 | test_register_weak_password |
| POST | /auth/login | A15 | test_login_success |
| POST | /auth/login | A16 | test_login_wrong_password |
| POST | /auth/login | A17 | test_login_nonexistent_user |
| GET | /auth/me | A18 | test_get_me_success |
| GET | /auth/me | A19 | test_get_me_no_token |
| GET | /auth/me | A20 | test_get_me_invalid_token |

#### 项目接口

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| POST | /projects | A21 | test_create_project_success |
| POST | /projects | A22 | test_create_project_no_auth |
| POST | /projects | A23 | test_create_project_cross_user_rejected |
| POST | /projects | A24 | test_create_project_invalid_user |
| POST | /projects | A25 | test_create_project_empty_name |
| POST | /projects | A26 | test_create_project_missing_field |
| GET | /projects | A27 | test_list_projects |
| GET | /projects?user_id= | A28 | test_list_projects_by_user |
| GET | /projects/{id} | A29 | test_get_project_exists |
| GET | /projects/{id} | A30 | test_get_project_not_found |
| PUT | /projects/{id} | A31 | test_update_project_success |
| PUT | /projects/{id} | A32 | test_update_project_not_found |
| PUT | /projects/{id} | A33 | test_update_project_wrong_owner_rejected |
| DELETE | /projects/{id} | A34 | test_delete_project_success |
| DELETE | /projects/{id} | A35 | test_delete_project_not_found |
| DELETE | /projects/{id} | A36 | test_delete_project_wrong_owner_rejected |
#### 基础设施路由

| 方法 | 路径 | 编号 | 测试用例 |
|------|------|------|----------|
| GET | /health | A38 | test_health_returns_ok |
| GET | /devices | A39 | test_devices_returns_device_info |
| POST | /train | A40 | test_train_creates_job |

---

## 四、覆盖率统计

| 模块 | 测试文件 | 用例数 | 全部通过 |
|------|----------|--------|----------|
| storage.py | test_storage.py | 19 | ✅ |
| auth.py | test_auth.py | 40 | ✅ |
| projects.py | test_projects.py | 31 | ✅ |
| main.py (M1 API) | test_api.py | 39 | ✅ |
| **合计** | | **129** | ✅ |

---

## 五、异常覆盖矩阵

| 异常类型 | 场景数 | 覆盖模块 |
|----------|--------|----------|
| ValueError（参数不合法） | 30+ | auth, projects |
| 401 Unauthorized | 4 | API（登录失败、缺少/无效 token） |
| 403 Forbidden | 3 | API（跨用户操作项目） |
| 404 Not Found | 3 | API（用户/项目不存在、邮箱未注册） |
| 422 Unprocessable | 2 | API（Pydantic 自动校验） |
| 并发写入冲突 | 2 | storage |
| 数据文件损坏恢复 | 隐蔽 | storage（JSONDecodeError 兜底） |

---

## 六、后续测试计划

1. **性能测试**：大量用户/项目数据下的读写性能
2. **数据库迁移测试**：从 JSON 迁移到数据库后回归测试
3. **前端集成测试**：前端页面通过 API 完成用户注册和项目保存的端到端流程
4. **安全测试**：输入注入、超大数据体、恶意 JSON 结构
