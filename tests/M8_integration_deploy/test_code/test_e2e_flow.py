"""端到端业务流程集成测试（M8 · 人员 6）。

用 FastAPI TestClient 在进程内把「注册 → 登录 → 鉴权 → 建项目 → 查项目 →
结构校验 → 模板 → 基于模板建项目 → 下载本机训练应用」整条链路串起来，
验证前后端接口契约稳定、各模块协同正确。数据落在独立临时 SQLite，不污染真实库。

运行：
    python -m pytest tests/M8_integration_deploy/test_code/test_e2e_flow.py -q
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage


# 一个最小合法模型图：Input -> Output
VALID_MODEL = {
    "layers": [
        {"id": "input_1", "type": "Input", "name": "输入层", "params": {"shape": [1, 28, 28]}},
        {"id": "flatten_1", "type": "Flatten", "name": "展平层", "params": {}},
        {
            "id": "linear_1",
            "type": "Linear",
            "name": "全连接层",
            "params": {"in_features": 784, "out_features": 10},
        },
        {"id": "output_1", "type": "Output", "name": "输出层", "params": {}},
    ],
    "connections": [
        {"source": "input_1", "target": "flatten_1"},
        {"source": "flatten_1", "target": "linear_1"},
        {"source": "linear_1", "target": "output_1"},
    ],
}

# 一个非法模型图：缺少 Output
INVALID_MODEL = {
    "layers": [
        {"id": "input_1", "type": "Input", "params": {"shape": [1, 28, 28]}},
        {"id": "flatten_1", "type": "Flatten", "params": {}},
    ],
    "connections": [{"source": "input_1", "target": "flatten_1"}],
}


class EndToEndFlowTests(unittest.TestCase):
    """前端-后端接口契约层面的端到端链路测试。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        storage.configure_database(f"sqlite:///{Path(cls._tmp.name) / 'e2e.db'}")
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp.cleanup()

    def _register(self, suffix):
        """注册一个新用户，返回 (token, user)。"""
        resp = self.client.post("/auth/register", json={
            "username": f"e2e_{suffix}",
            "email": f"e2e_{suffix}@test.dev",
            "password": "passw0rd1",
            "confirm_password": "passw0rd1",
        })
        self.assertEqual(200, resp.status_code, resp.text)
        body = resp.json()
        self.assertIn("access_token", body)
        return body["access_token"], body["user"]

    # M8-001
    def test_health_ok(self):
        r = self.client.get("/health")
        self.assertEqual(200, r.status_code)
        self.assertEqual("ok", r.json()["status"])

    # M8-003
    def test_register_login_me(self):
        token, user = self._register("auth")
        login = self.client.post("/auth/login", json={
            "email": user["email"], "password": "passw0rd1",
        })
        self.assertEqual(200, login.status_code, login.text)
        self.assertIn("access_token", login.json())

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(200, me.status_code)
        self.assertEqual(user["id"], me.json()["data"]["id"])

    # M8-004
    def test_protected_endpoint_requires_token(self):
        anon = self.client.get("/auth/me")
        self.assertIn(anon.status_code, (401, 403))

    # M8-005
    def test_project_create_list_get(self):
        token, user = self._register("proj")
        headers = {"Authorization": f"Bearer {token}"}
        create = self.client.post("/projects", headers=headers, json={
            "user_id": user["id"],
            "name": "E2E 项目",
            "model_graph": VALID_MODEL,
            "description": "端到端测试项目",
        })
        self.assertEqual(200, create.status_code, create.text)
        pid = create.json()["data"]["id"]

        listing = self.client.get("/projects", headers=headers)
        self.assertEqual(200, listing.status_code)
        self.assertIn(pid, [p["id"] for p in listing.json()["data"]])

        detail = self.client.get(f"/projects/{pid}", headers=headers)
        self.assertEqual(200, detail.status_code)
        self.assertEqual("E2E 项目", detail.json()["data"]["name"])

    # M8-006
    def test_duplicate_project_name_rejected(self):
        token, user = self._register("dup")
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"user_id": user["id"], "name": "重名项目", "model_graph": VALID_MODEL}
        first = self.client.post("/projects", headers=headers, json=payload)
        self.assertEqual(200, first.status_code, first.text)
        second = self.client.post("/projects", headers=headers, json=payload)
        self.assertEqual(400, second.status_code)

    # M8-007 / M8-008
    def test_validate_valid_and_invalid(self):
        ok = self.client.post("/validate", json={"model": VALID_MODEL})
        self.assertEqual(200, ok.status_code)
        self.assertTrue(ok.json()["valid"])
        self.assertEqual([], ok.json()["errors"])

        bad = self.client.post("/validate", json={"model": INVALID_MODEL})
        self.assertEqual(200, bad.status_code)
        self.assertFalse(bad.json()["valid"])
        self.assertTrue(bad.json()["errors"])

    # M8-009
    def test_templates_list_has_eleven(self):
        r = self.client.get("/projects/templates")
        self.assertEqual(200, r.status_code)
        body = r.json()
        self.assertEqual(11, body["count"])
        self.assertEqual(11, len(body["data"]))

    # M8-010
    def test_create_from_template_and_validate(self):
        token, user = self._register("tmpl")
        created = self.client.post("/projects/from-template",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": user["id"], "template_name": "lenet"},
        )
        self.assertEqual(200, created.status_code, created.text)
        self.assertEqual("ok", created.json()["status"])

        tmpl = self.client.get("/projects/templates/lenet")
        self.assertEqual(200, tmpl.status_code)
        model = tmpl.json()["model"]
        checked = self.client.post("/validate", json={"model": model})
        self.assertEqual(200, checked.status_code)
        self.assertTrue(checked.json()["valid"], checked.json())

    # M8-011
    def test_agent_download_returns_zip(self):
        token, _ = self._register("dl")
        r = self.client.get("/agent/download", params={"token": token, "platform": "windows"})
        self.assertEqual(200, r.status_code)
        self.assertIn("zip", r.headers.get("content-type", "").lower())
        # 内容为一个可解析的 zip（无论是预构建完整包还是源码回退包）
        import io
        import zipfile
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(r.content)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
