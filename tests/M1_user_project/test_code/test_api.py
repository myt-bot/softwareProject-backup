"""API 接口集成测试（M1）。

使用 FastAPI TestClient 测试用户、项目、认证相关的 HTTP 接口。
覆盖：/auth/* 路由测试、权限校验测试、stub 路由 501 测试。
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage


# 测试用的合法模型图
VALID_MODEL = {
    "layers": [
        {
            "id": "input_1",
            "type": "Input",
            "name": "输入层",
            "params": {"shape": [1, 28, 28]},
        },
        {
            "id": "output_1",
            "type": "Output",
            "name": "输出层",
            "params": {},
        },
    ],
    "connections": [
        {"source": "input_1", "target": "output_1"},
    ],
}


class TestUserAPI(unittest.TestCase):
    """用户管理接口测试。

    用户管理接口（/users 系列）已收敛为需要登录的账号管理接口：
    - 创建用户需要登录；
    - 列表只返回本人；
    - 查看 / 修改 / 删除单个用户仅限本人（越权返回 403，未登录返回 401）。
    面向普通用户的自助注册走 /auth/register。
    """

    _tmp_dir = None
    _data_dir = None
    _token = None
    _user_id = None
    _other_token = None
    _other_user_id = None

    @classmethod
    def setUpClass(cls):
        """把存储切换到独立的临时 SQLite 库，并注册两名测试用户。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage.configure_database(f"sqlite:///{cls._data_dir / 'test.db'}")

        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

        cls._token, cls._user_id = cls._register("main_user", "main_user@test.com")
        cls._other_token, cls._other_user_id = cls._register("other_user", "other_user@test.com")

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp_dir.cleanup()

    @classmethod
    def _register(cls, username, email, password="testpass123"):
        """注册一个用户并返回 (token, user_id)。"""
        resp = cls.client.post("/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        return body["access_token"], body["user"]["id"]

    def _auth_headers(self, token=None):
        """生成带 Authorization 头的字典。"""
        t = token if token is not None else self._token
        return {"Authorization": f"Bearer {t}"}

    # ========== 创建用户 ==========

    def test_create_user_success(self):
        """POST /users 已登录时正常创建。"""
        resp = self.client.post("/users", json={
            "username": "apiuser",
            "email": "api@test.com",
            "password": "testpass123",
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["username"], "apiuser")
        self.assertNotIn("password_hash", data["data"])

    def test_create_user_no_auth(self):
        """POST /users 未登录返回 401（缺陷 1 修复）。"""
        resp = self.client.post("/users", json={
            "username": "anon",
            "email": "anon@test.com",
            "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 401)

    def test_create_user_invalid_email(self):
        """POST /users 非法邮箱返回 400。"""
        resp = self.client.post("/users", json={
            "username": "apiuser",
            "email": "bad-email",
            "password": "testpass123",
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_create_user_duplicate(self):
        """POST /users 重复邮箱返回 400。"""
        self.client.post("/users", json={
            "username": "u1", "email": "dup@test.com", "password": "testpass123",
        }, headers=self._auth_headers())
        resp = self.client.post("/users", json={
            "username": "u2", "email": "dup@test.com", "password": "testpass123",
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_create_user_missing_field(self):
        """POST /users 缺少必填字段返回 422。"""
        resp = self.client.post("/users", json={"username": "test"},
                                headers=self._auth_headers())
        self.assertEqual(resp.status_code, 422)

    # ========== 获取用户列表 ==========

    def test_list_users_self_only(self):
        """GET /users 已登录时只返回本人记录。"""
        resp = self.client.get("/users", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["data"][0]["id"], self._user_id)

    def test_list_users_no_auth(self):
        """GET /users 未登录返回 401（缺陷 2 修复）。"""
        resp = self.client.get("/users")
        self.assertEqual(resp.status_code, 401)

    # ========== 获取单个用户 ==========

    def test_get_user_self(self):
        """GET /users/{id} 获取本人信息。"""
        resp = self.client.get(f"/users/{self._user_id}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["id"], self._user_id)

    def test_get_user_other_forbidden(self):
        """GET /users/{id} 查看他人账号返回 403（缺陷 2 修复）。"""
        resp = self.client.get(f"/users/{self._other_user_id}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)

    def test_get_user_no_auth(self):
        """GET /users/{id} 未登录返回 401。"""
        resp = self.client.get(f"/users/{self._user_id}")
        self.assertEqual(resp.status_code, 401)

    # ========== 更新用户 ==========

    def test_update_user_self(self):
        """PUT /users/{id} 修改本人信息成功。"""
        token, user_id = self._register("upd_self", "upd_self@test.com")
        resp = self.client.put(f"/users/{user_id}", json={"username": "updated"},
                               headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "updated")

    def test_update_user_other_forbidden(self):
        """PUT /users/{id} 修改他人账号返回 403（缺陷 1 修复）。"""
        resp = self.client.put(f"/users/{self._other_user_id}", json={"username": "hacked"},
                               headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)

    def test_update_user_no_auth(self):
        """PUT /users/{id} 未登录返回 401（缺陷 1 修复）。"""
        resp = self.client.put(f"/users/{self._user_id}", json={"username": "x"})
        self.assertEqual(resp.status_code, 401)

    # ========== 删除用户 ==========

    def test_delete_user_self(self):
        """DELETE /users/{id} 删除本人账号成功。"""
        token, user_id = self._register("del_self", "del_self@test.com")
        resp = self.client.delete(f"/users/{user_id}", headers=self._auth_headers(token))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("已删除", resp.json()["message"])

    def test_delete_user_other_forbidden(self):
        """DELETE /users/{id} 删除他人账号返回 403（缺陷 1 修复）。"""
        resp = self.client.delete(f"/users/{self._other_user_id}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)

    def test_delete_user_no_auth(self):
        """DELETE /users/{id} 未登录返回 401（缺陷 1 修复）。"""
        resp = self.client.delete(f"/users/{self._user_id}")
        self.assertEqual(resp.status_code, 401)


class TestAuthAPI(unittest.TestCase):
    """认证接口测试（M1）。"""

    _tmp_dir = None
    _data_dir = None

    @classmethod
    def setUpClass(cls):
        """把存储切换到独立的临时 SQLite 库。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage.configure_database(f"sqlite:///{cls._data_dir / 'test.db'}")

        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp_dir.cleanup()

    # ========== 注册 ==========

    def test_register_success(self):
        """POST /auth/register 正常注册（含确认密码），返回 JWT。"""
        resp = self.client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@test.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "newuser")

    def test_register_duplicate_email(self):
        """POST /auth/register 重复邮箱返回 400（邮箱必须唯一）。"""
        self.client.post("/auth/register", json={
            "username": "u1", "email": "dup@test.com",
            "password": "testpass123", "confirm_password": "testpass123",
        })
        resp = self.client.post("/auth/register", json={
            "username": "u2", "email": "dup@test.com",
            "password": "testpass123", "confirm_password": "testpass123",
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_weak_password(self):
        """POST /auth/register 弱密码返回 400。"""
        resp = self.client.post("/auth/register", json={
            "username": "test", "email": "t@test.com",
            "password": "short", "confirm_password": "short",
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_password_mismatch(self):
        """POST /auth/register 两次输入的密码不一致返回 400。"""
        resp = self.client.post("/auth/register", json={
            "username": "mismatch",
            "email": "mismatch@test.com",
            "password": "testpass123",
            "confirm_password": "testpass456",
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("不一致", resp.json()["message"])

    def test_register_missing_confirm_password(self):
        """POST /auth/register 缺少确认密码字段返回 422。"""
        resp = self.client.post("/auth/register", json={
            "username": "noconfirm",
            "email": "noconfirm@test.com",
            "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 422)

    # ========== 登录 ==========

    def test_login_success(self):
        """POST /auth/login 正确凭据（邮箱+密码）返回 JWT。"""
        self.client.post("/auth/register", json={
            "username": "loginuser", "email": "login@test.com",
            "password": "testpass123", "confirm_password": "testpass123",
        })
        resp = self.client.post("/auth/login", json={
            "email": "login@test.com", "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["username"], "loginuser")

    def test_login_wrong_password(self):
        """POST /auth/login 错误密码返回 401。"""
        self.client.post("/auth/register", json={
            "username": "loginuser2", "email": "l2@test.com",
            "password": "testpass123", "confirm_password": "testpass123",
        })
        resp = self.client.post("/auth/login", json={
            "email": "l2@test.com", "password": "wrongpassword",
        })
        self.assertEqual(resp.status_code, 401)

    def test_login_nonexistent_user(self):
        """POST /auth/login 邮箱未注册返回 404。"""
        resp = self.client.post("/auth/login", json={
            "email": "no@test.com", "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertEqual(data.get("code"), "NOT_REGISTERED")

    # ========== 获取当前用户 ==========

    def test_get_me_success(self):
        """GET /auth/me 正确 token 返回用户信息。"""
        register_resp = self.client.post("/auth/register", json={
            "username": "meuser", "email": "me@test.com",
            "password": "testpass123", "confirm_password": "testpass123",
        })
        token = register_resp.json()["access_token"]

        resp = self.client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "meuser")

    def test_get_me_no_token(self):
        """GET /auth/me 缺少 token 返回 401。"""
        resp = self.client.get("/auth/me")
        self.assertEqual(resp.status_code, 401)

    def test_get_me_invalid_token(self):
        """GET /auth/me 无效 token 返回 401。"""
        resp = self.client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"},
        )
        self.assertEqual(resp.status_code, 401)


class TestProjectAPI(unittest.TestCase):
    """项目管理接口测试。"""

    _tmp_dir = None
    _data_dir = None
    _token = None
    _user_id = None
    _other_token = None
    _other_user_id = None

    @classmethod
    def setUpClass(cls):
        """把存储切换到独立 SQLite 库，注册测试用户并获取 JWT。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage.configure_database(f"sqlite:///{cls._data_dir / 'test.db'}")

        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

        # 注册主用户
        resp = cls.client.post("/auth/register", json={
            "username": "proj_owner",
            "email": "owner@test.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        })
        cls._token = resp.json()["access_token"]
        cls._user_id = resp.json()["user"]["id"]

        # 注册第二个用户（用于权限测试）
        resp2 = cls.client.post("/auth/register", json={
            "username": "other_owner",
            "email": "other@test.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        })
        cls._other_token = resp2.json()["access_token"]
        cls._other_user_id = resp2.json()["user"]["id"]

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp_dir.cleanup()

    def _auth_headers(self, token=None):
        """生成带 Authorization 头的字典。"""
        t = token if token is not None else self._token
        return {"Authorization": f"Bearer {t}"}

    # ========== 创建项目 ==========

    def test_create_project_success(self):
        """POST /projects 正常创建（需要登录）。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "test_proj",
            "model_graph": VALID_MODEL,
            "description": "测试项目",
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["data"]["name"], "test_proj")

    def test_create_project_no_auth(self):
        """POST /projects 无 token 返回 401。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "test_proj",
            "model_graph": VALID_MODEL,
        })
        self.assertEqual(resp.status_code, 401)

    def test_create_project_cross_user_rejected(self):
        """POST /projects 用 A 的 token 以 B 的身份创建返回 403。"""
        resp = self.client.post("/projects", json={
            "user_id": self._other_user_id,
            "name": "stolen",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)

    def test_create_project_invalid_user(self):
        """POST /projects 用 A 的 token 以不存在的用户创建返回 403（用户不匹配先于存在性检查）。"""
        resp = self.client.post("/projects", json={
            "user_id": "user_nonexistent",
            "name": "test_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 403)

    def test_create_project_empty_name(self):
        """POST /projects 空名称返回 400。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_create_project_missing_field(self):
        """POST /projects 缺少必填字段返回 422。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "test_proj",
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 422)

    # ========== 获取项目列表 ==========

    def test_list_projects(self):
        """GET /projects 已登录时只返回本人项目。"""
        resp = self.client.get("/projects", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("data", body)
        # 强制按 token 过滤，返回的项目应全部属于当前用户
        for project in body["data"]:
            self.assertEqual(project["user_id"], self._user_id)

    def test_list_projects_no_auth(self):
        """GET /projects 未登录返回 401（缺陷 2 修复）。"""
        resp = self.client.get("/projects")
        self.assertEqual(resp.status_code, 401)

    # ========== 获取单个项目 ==========

    def test_get_project_exists(self):
        """GET /projects/{id} 获取本人项目。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "fetch_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.get(f"/projects/{proj_id}", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "fetch_proj")

    def test_get_project_not_found(self):
        """GET /projects/{id} 不存在返回 404。"""
        resp = self.client.get("/projects/proj_nonexistent", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 404)

    def test_get_project_no_auth(self):
        """GET /projects/{id} 未登录返回 401（缺陷 2 修复）。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "noauth_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.get(f"/projects/{proj_id}")
        self.assertEqual(resp.status_code, 401)

    def test_get_project_wrong_owner_rejected(self):
        """GET /projects/{id} 访问他人项目返回 403（缺陷 2 修复）。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "private_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.get(f"/projects/{proj_id}",
                               headers=self._auth_headers(self._other_token))
        self.assertEqual(resp.status_code, 403)

    # ========== 更新项目 ==========

    def test_update_project_success(self):
        """PUT /projects/{id} 正常更新（所有者）。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "update_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.put(f"/projects/{proj_id}", json={"name": "renamed_proj"},
                               headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "renamed_proj")

    def test_update_project_not_found(self):
        """PUT /projects/{id} 不存在返回 400。"""
        resp = self.client.put("/projects/proj_nonexistent", json={"name": "x"},
                               headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_update_project_wrong_owner_rejected(self):
        """PUT /projects/{id} 非所有者返回 403。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "owner_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        # 用另一个用户的 token 尝试修改
        resp = self.client.put(f"/projects/{proj_id}", json={"name": "hacked"},
                               headers=self._auth_headers(self._other_token))
        self.assertEqual(resp.status_code, 403)

    # ========== 删除项目 ==========

    def test_delete_project_success(self):
        """DELETE /projects/{id} 正常删除（所有者）。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "delete_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.delete(f"/projects/{proj_id}",
                                  headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("已删除", resp.json()["message"])

    def test_delete_project_not_found(self):
        """DELETE /projects/{id} 不存在返回 400。"""
        resp = self.client.delete("/projects/proj_nonexistent",
                                  headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_delete_project_wrong_owner_rejected(self):
        """DELETE /projects/{id} 非所有者返回 403。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "owner_del",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.delete(f"/projects/{proj_id}",
                                  headers=self._auth_headers(self._other_token))
        self.assertEqual(resp.status_code, 403)

    # ========== 健壮性与安全（缺陷④：超大数据体 / 畸形结构 / 注入样式输入）==========

    def test_oversized_project_name_rejected(self):
        """项目名称超过 100 字符返回 400，不写入存储。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "n" * 101,
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_oversized_description_rejected(self):
        """项目描述超过 500 字符返回 400。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "desc_limit_proj",
            "model_graph": VALID_MODEL,
            "description": "d" * 501,
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_malformed_model_graph_rejected(self):
        """model_graph 缺少 layers 字段返回 422（请求体结构校验）。"""
        resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "malformed_proj",
            "model_graph": {"connections": []},
        }, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 422)

    def test_injection_like_name_stored_literally(self):
        """注入样式的项目名被当作普通字符串原样存储，不被执行（参数化查询）。"""
        payload_name = "Rob'); DROP TABLE projects;--"
        create = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": payload_name,
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(create.status_code, 200)
        proj_id = create.json()["data"]["id"]

        # 读回校验：名称原样保存
        detail = self.client.get(f"/projects/{proj_id}", headers=self._auth_headers())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["name"], payload_name)

        # 后续正常创建仍可用，证明 projects 表未被破坏
        ok = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "after_injection_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        self.assertEqual(ok.status_code, 200)


class TestInfraRoutes(unittest.TestCase):
    """基础设施路由测试。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    def test_health_returns_ok(self):
        """GET /health 返回 200 和状态信息。"""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_agent_status_reports_offline_without_connection(self):
        """GET /agents/status 在本机 Agent 未连接时返回离线状态。"""
        resp = self.client.get("/agents/status", params={"user_id": "infra_test_user"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["type"], "agent_status")
        self.assertFalse(data["online"])

    def test_train_creates_job(self):
        """POST /train 传入合法模型结构返回 200 和训练任务信息。"""
        valid_model = {
            "layers": [
                {"id": "in", "type": "Input", "params": {"shape": [1, 28, 28]}},
                {"id": "flat", "type": "Flatten", "params": {}},
                {"id": "fc", "type": "Linear", "params": {"out_features": 10}},
                {"id": "out", "type": "Output", "params": {}},
            ],
            "connections": [
                {"source": "in", "target": "flat"},
                {"source": "flat", "target": "fc"},
                {"source": "fc", "target": "out"},
            ],
        }
        resp = self.client.post("/train", params={"user_id": "infra_test_user"}, json={
            "model": valid_model,
            "train_config": {
                "dataset_name": "MNIST",
                "epochs": 1,
                "batch_size": 64,
                "rate": 0.001,
                "device": "cpu",
                "loss_fn": "cross_entropy",
                "optimizer": "sgd",
            },
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("job_id", data)
        self.assertTrue(data["job_id"].startswith("job_"))
        self.assertEqual(data["job_status"], "no_agent")
        self.assertEqual(data["agent_status"], "offline")


if __name__ == "__main__":
    unittest.main()
