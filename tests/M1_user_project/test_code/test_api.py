"""API 接口集成测试（M1）。

使用 FastAPI TestClient 测试用户、项目、认证相关的 HTTP 接口。
覆盖：/auth/* 路由测试、权限校验测试、stub 路由 501 测试。
编写者：甘淞文
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
    """用户管理接口测试。"""

    _tmp_dir = None
    _data_dir = None

    @classmethod
    def setUpClass(cls):
        """创建独立的临时目录并重定向存储（在导入 app 之前）。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage._STORAGE_DIR = cls._data_dir
        storage._USERS_FILE = cls._data_dir / "users.json"
        storage._PROJECTS_FILE = cls._data_dir / "projects.json"

        # 延迟导入，确保存储路径已重定向
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls._tmp_dir.cleanup()

    # ========== 创建用户 ==========

    def test_create_user_success(self):
        """POST /users 正常创建。"""
        resp = self.client.post("/users", json={
            "username": "apiuser",
            "email": "api@test.com",
            "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["username"], "apiuser")
        self.assertNotIn("password_hash", data["data"])

    def test_create_user_invalid_email(self):
        """POST /users 非法邮箱返回 400。"""
        resp = self.client.post("/users", json={
            "username": "apiuser",
            "email": "bad-email",
            "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_user_duplicate(self):
        """POST /users 重复邮箱返回 400。"""
        self.client.post("/users", json={
            "username": "u1", "email": "dup@test.com", "password": "testpass123",
        })
        resp = self.client.post("/users", json={
            "username": "u2", "email": "dup@test.com", "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_user_missing_field(self):
        """POST /users 缺少必填字段返回 422。"""
        resp = self.client.post("/users", json={"username": "test"})
        self.assertEqual(resp.status_code, 422)

    # ========== 获取用户列表 ==========

    def test_list_users(self):
        """GET /users 获取用户列表。"""
        resp = self.client.get("/users")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("data", data)
        self.assertIn("count", data)

    # ========== 获取单个用户 ==========

    def test_get_user_exists(self):
        """GET /users/{id} 获取存在的用户。"""
        create_resp = self.client.post("/users", json={
            "username": "fetchme",
            "email": "fetch@test.com",
            "password": "testpass123",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = self.client.get(f"/users/{user_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "fetchme")

    def test_get_user_not_found(self):
        """GET /users/{id} 不存在返回 404。"""
        resp = self.client.get("/users/user_nonexistent")
        self.assertEqual(resp.status_code, 404)

    # ========== 更新用户 ==========

    def test_update_user_success(self):
        """PUT /users/{id} 正常更新。"""
        create_resp = self.client.post("/users", json={
            "username": "update_me",
            "email": "old@test.com",
            "password": "testpass123",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = self.client.put(f"/users/{user_id}", json={"username": "updated"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "updated")

    def test_update_user_not_found(self):
        """PUT /users/{id} 不存在返回 400。"""
        resp = self.client.put("/users/user_nonexistent", json={"username": "x"})
        self.assertEqual(resp.status_code, 400)

    # ========== 删除用户 ==========

    def test_delete_user_success(self):
        """DELETE /users/{id} 正常删除。"""
        create_resp = self.client.post("/users", json={
            "username": "delete_me",
            "email": "del@test.com",
            "password": "testpass123",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = self.client.delete(f"/users/{user_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("已删除", resp.json()["message"])

    def test_delete_user_not_found(self):
        """DELETE /users/{id} 不存在返回 400。"""
        resp = self.client.delete("/users/user_nonexistent")
        self.assertEqual(resp.status_code, 400)


class TestAuthAPI(unittest.TestCase):
    """认证接口测试（M1）。"""

    _tmp_dir = None
    _data_dir = None

    @classmethod
    def setUpClass(cls):
        """创建独立的临时目录。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage._STORAGE_DIR = cls._data_dir
        storage._USERS_FILE = cls._data_dir / "users.json"
        storage._PROJECTS_FILE = cls._data_dir / "projects.json"

        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls._tmp_dir.cleanup()

    # ========== 注册 ==========

    def test_register_success(self):
        """POST /auth/register 正常注册，返回 JWT。"""
        resp = self.client.post("/auth/register", json={
            "username": "newuser",
            "email": "new@test.com",
            "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["user"]["username"], "newuser")

    def test_register_duplicate_email(self):
        """POST /auth/register 重复邮箱返回 400（邮箱必须唯一）。"""
        self.client.post("/auth/register", json={
            "username": "u1", "email": "dup@test.com", "password": "testpass123",
        })
        resp = self.client.post("/auth/register", json={
            "username": "u2", "email": "dup@test.com", "password": "testpass123",
        })
        self.assertEqual(resp.status_code, 400)

    def test_register_weak_password(self):
        """POST /auth/register 弱密码返回 400。"""
        resp = self.client.post("/auth/register", json={
            "username": "test", "email": "t@test.com", "password": "short",
        })
        self.assertEqual(resp.status_code, 400)

    # ========== 登录 ==========

    def test_login_success(self):
        """POST /auth/login 正确凭据（邮箱+密码）返回 JWT。"""
        self.client.post("/auth/register", json={
            "username": "loginuser", "email": "login@test.com", "password": "testpass123",
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
            "username": "loginuser2", "email": "l2@test.com", "password": "testpass123",
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
            "username": "meuser", "email": "me@test.com", "password": "testpass123",
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
        """创建临时目录，注册测试用户并获取 JWT。"""
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._data_dir = Path(cls._tmp_dir.name)
        storage._STORAGE_DIR = cls._data_dir
        storage._USERS_FILE = cls._data_dir / "users.json"
        storage._PROJECTS_FILE = cls._data_dir / "projects.json"

        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

        # 注册主用户
        resp = cls.client.post("/auth/register", json={
            "username": "proj_owner",
            "email": "owner@test.com",
            "password": "testpass123",
        })
        cls._token = resp.json()["access_token"]
        cls._user_id = resp.json()["user"]["id"]

        # 注册第二个用户（用于权限测试）
        resp2 = cls.client.post("/auth/register", json={
            "username": "other_owner",
            "email": "other@test.com",
            "password": "testpass123",
        })
        cls._other_token = resp2.json()["access_token"]
        cls._other_user_id = resp2.json()["user"]["id"]

    @classmethod
    def tearDownClass(cls):
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
        """GET /projects 获取项目列表。"""
        resp = self.client.get("/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("data", resp.json())

    def test_list_projects_by_user(self):
        """GET /projects?user_id=xxx 按用户过滤。"""
        resp = self.client.get(f"/projects?user_id={self._user_id}")
        self.assertEqual(resp.status_code, 200)

    # ========== 获取单个项目 ==========

    def test_get_project_exists(self):
        """GET /projects/{id} 获取存在的项目。"""
        create_resp = self.client.post("/projects", json={
            "user_id": self._user_id,
            "name": "fetch_proj",
            "model_graph": VALID_MODEL,
        }, headers=self._auth_headers())
        proj_id = create_resp.json()["data"]["id"]

        resp = self.client.get(f"/projects/{proj_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "fetch_proj")

    def test_get_project_not_found(self):
        """GET /projects/{id} 不存在返回 404。"""
        resp = self.client.get("/projects/proj_nonexistent")
        self.assertEqual(resp.status_code, 404)

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

    # ========== 获取用户的项目 ==========

    def test_get_user_projects(self):
        """GET /users/{id}/projects 获取用户的项目列表。"""
        resp = self.client.get(f"/users/{self._user_id}/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("data", resp.json())


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

    def test_devices_returns_501(self):
        """GET /devices 返回 501（尚未实现）。"""
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 501)

    def test_train_returns_501(self):
        """POST /train 返回 501（尚未实现）。"""
        valid_model = {
            "layers": [{"id": "in", "type": "Input", "params": {"shape": [1,28,28]}}],
            "connections": [],
        }
        resp = self.client.post("/train", json={
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
        self.assertEqual(resp.status_code, 501)


if __name__ == "__main__":
    unittest.main()
