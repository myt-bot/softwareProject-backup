"""API 接口集成测试。

使用 FastAPI TestClient 测试用户与项目管理相关的 HTTP 接口。
编写者：甘淞文
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage

# 重定向存储到临时目录（必须在导入 app 之前）
_tmp_dir = tempfile.TemporaryDirectory()
_data_dir = Path(_tmp_dir.name)
storage._STORAGE_DIR = _data_dir
storage._USERS_FILE = _data_dir / "users.json"
storage._PROJECTS_FILE = _data_dir / "projects.json"

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


class TestUserAPI(unittest.TestCase):
    """用户管理接口测试。"""

    @classmethod
    def tearDownClass(cls):
        _tmp_dir.cleanup()

    # ========== 创建用户 ==========

    def test_create_user_success(self):
        """POST /users 正常创建。"""
        resp = client.post("/users", json={
            "username": "apiuser",
            "email": "api@test.com",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data"]["username"], "apiuser")

    def test_create_user_invalid_email(self):
        """POST /users 非法邮箱返回 400。"""
        resp = client.post("/users", json={
            "username": "apiuser",
            "email": "bad-email",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_user_duplicate(self):
        """POST /users 重复用户名返回 400。"""
        client.post("/users", json={"username": "dup", "email": "d1@test.com"})
        resp = client.post("/users", json={"username": "dup", "email": "d2@test.com"})
        self.assertEqual(resp.status_code, 400)

    def test_create_user_missing_field(self):
        """POST /users 缺少必填字段返回 422。"""
        resp = client.post("/users", json={"username": "test"})
        self.assertEqual(resp.status_code, 422)

    # ========== 获取用户列表 ==========

    def test_list_users(self):
        """GET /users 获取用户列表。"""
        resp = client.get("/users")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("data", data)
        self.assertIn("count", data)

    # ========== 获取单个用户 ==========

    def test_get_user_exists(self):
        """GET /users/{id} 获取存在的用户。"""
        create_resp = client.post("/users", json={
            "username": "fetchme",
            "email": "fetch@test.com",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/users/{user_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "fetchme")

    def test_get_user_not_found(self):
        """GET /users/{id} 不存在返回 404。"""
        resp = client.get("/users/user_nonexistent")
        self.assertEqual(resp.status_code, 404)

    # ========== 更新用户 ==========

    def test_update_user_success(self):
        """PUT /users/{id} 正常更新。"""
        create_resp = client.post("/users", json={
            "username": "update_me",
            "email": "old@test.com",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = client.put(f"/users/{user_id}", json={"username": "updated"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["username"], "updated")

    def test_update_user_not_found(self):
        """PUT /users/{id} 不存在返回 400。"""
        resp = client.put("/users/user_nonexistent", json={"username": "x"})
        self.assertEqual(resp.status_code, 400)

    # ========== 删除用户 ==========

    def test_delete_user_success(self):
        """DELETE /users/{id} 正常删除。"""
        create_resp = client.post("/users", json={
            "username": "delete_me",
            "email": "del@test.com",
        })
        user_id = create_resp.json()["data"]["id"]

        resp = client.delete(f"/users/{user_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("已删除", resp.json()["message"])

    def test_delete_user_not_found(self):
        """DELETE /users/{id} 不存在返回 400。"""
        resp = client.delete("/users/user_nonexistent")
        self.assertEqual(resp.status_code, 400)


class TestProjectAPI(unittest.TestCase):
    """项目管理接口测试。"""

    _user_id = None
    _valid_model = {
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

    @classmethod
    def setUpClass(cls):
        """创建测试用户。"""
        resp = client.post("/users", json={
            "username": "proj_owner",
            "email": "owner@test.com",
        })
        cls._user_id = resp.json()["data"]["id"]

    @classmethod
    def tearDownClass(cls):
        _tmp_dir.cleanup()

    # ========== 创建项目 ==========

    def test_create_project_success(self):
        """POST /projects 正常创建。"""
        resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "test_proj",
            "model_graph": self._valid_model,
            "description": "测试项目",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["data"]["name"], "test_proj")

    def test_create_project_invalid_user(self):
        """POST /projects 用户不存在返回 400。"""
        resp = client.post("/projects", json={
            "user_id": "user_nonexistent",
            "name": "test_proj",
            "model_graph": self._valid_model,
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_project_empty_name(self):
        """POST /projects 空名称返回 400。"""
        resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "",
            "model_graph": self._valid_model,
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_project_missing_field(self):
        """POST /projects 缺少必填字段返回 422。"""
        resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "test_proj",
        })
        self.assertEqual(resp.status_code, 422)

    # ========== 获取项目列表 ==========

    def test_list_projects(self):
        """GET /projects 获取项目列表。"""
        resp = client.get("/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("data", resp.json())

    def test_list_projects_by_user(self):
        """GET /projects?user_id=xxx 按用户过滤。"""
        resp = client.get(f"/projects?user_id={self._user_id}")
        self.assertEqual(resp.status_code, 200)

    # ========== 获取单个项目 ==========

    def test_get_project_exists(self):
        """GET /projects/{id} 获取存在的项目。"""
        create_resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "fetch_proj",
            "model_graph": self._valid_model,
        })
        proj_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/projects/{proj_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "fetch_proj")

    def test_get_project_not_found(self):
        """GET /projects/{id} 不存在返回 404。"""
        resp = client.get("/projects/proj_nonexistent")
        self.assertEqual(resp.status_code, 404)

    # ========== 更新项目 ==========

    def test_update_project_success(self):
        """PUT /projects/{id} 正常更新。"""
        create_resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "update_proj",
            "model_graph": self._valid_model,
        })
        proj_id = create_resp.json()["data"]["id"]

        resp = client.put(f"/projects/{proj_id}", json={"name": "renamed_proj"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["name"], "renamed_proj")

    def test_update_project_not_found(self):
        """PUT /projects/{id} 不存在返回 400。"""
        resp = client.put("/projects/proj_nonexistent", json={"name": "x"})
        self.assertEqual(resp.status_code, 400)

    # ========== 删除项目 ==========

    def test_delete_project_success(self):
        """DELETE /projects/{id} 正常删除。"""
        create_resp = client.post("/projects", json={
            "user_id": self._user_id,
            "name": "delete_proj",
            "model_graph": self._valid_model,
        })
        proj_id = create_resp.json()["data"]["id"]

        resp = client.delete(f"/projects/{proj_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("已删除", resp.json()["message"])

    def test_delete_project_not_found(self):
        """DELETE /projects/{id} 不存在返回 400。"""
        resp = client.delete("/projects/proj_nonexistent")
        self.assertEqual(resp.status_code, 400)

    # ========== 获取用户的项目 ==========

    def test_get_user_projects(self):
        """GET /users/{id}/projects 获取用户的项目列表。"""
        resp = client.get(f"/users/{self._user_id}/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("data", resp.json())


if __name__ == "__main__":
    unittest.main()
