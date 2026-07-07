"""模板接口集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage


_tmp_dir = tempfile.TemporaryDirectory()
_data_dir = Path(_tmp_dir.name)
storage._STORAGE_DIR = _data_dir
storage._USERS_FILE = _data_dir / "users.json"
storage._PROJECTS_FILE = _data_dir / "projects.json"

from local_agent.runtime.validator import validate_model_graph


try:
    from fastapi.testclient import TestClient
    from backend.main import app
except ModuleNotFoundError as exc:
    TestClient = None
    app = None
    SKIP_REASON = f"缺少依赖，跳过模板接口集成测试: {exc}"
else:
    SKIP_REASON = None


client = TestClient(app) if TestClient else None


class TemplateApiIntegrationTests(unittest.TestCase):
    """测试模板相关 HTTP 接口和项目创建链路。"""

    @classmethod
    def tearDownClass(cls):
        _tmp_dir.cleanup()

    def setUp(self):
        if SKIP_REASON:
            self.skipTest(SKIP_REASON)

    def create_user(self, username="template_owner"):
        self.assertLessEqual(len(username), 20, "测试用户名不能超过 auth 模块限制的 20 个字符")
        response = client.post("/users", json={
            "username": username,
            "email": f"{username}@test.com",
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["data"]

    def test_list_project_templates_endpoint(self):
        response = client.get("/projects/templates")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("ok", body["status"])
        self.assertEqual(11, body["count"])
        keys = {template["key"] for template in body["data"]}
        self.assertIn("mlp", keys)
        self.assertIn("transformer_encoder_tiny", keys)
        self.assertIn("gcn_tiny", keys)

    def test_template_route_is_not_captured_by_project_id_route(self):
        response = client.get("/projects/templates")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("ok", body["status"])
        self.assertIn("data", body)

    def test_get_project_template_endpoint_returns_valid_model_graph(self):
        response = client.get("/projects/templates/mlp")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("ok", body["status"])
        self.assertIn("model", body)

        validation = validate_model_graph(body["model"])
        self.assertTrue(validation["valid"], validation["errors"])

    def test_get_project_template_endpoint_returns_404_for_unknown_template(self):
        response = client.get("/projects/templates/not_exists")

        self.assertEqual(404, response.status_code)
        body = response.json()
        self.assertEqual("error", body["status"])
        self.assertIn("available_templates", body)

    def test_create_project_from_template_saves_project_and_model_graph(self):
        user = self.create_user("template_save_user")

        response = client.post("/projects/from-template", json={
            "user_id": user["id"],
            "template_name": "mlp",
            "name": "MLP Template Project",
            "description": "created from template integration test",
        })

        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("ok", body["status"])
        self.assertEqual("mlp", body["template"])
        self.assertEqual("MLP Template Project", body["data"]["name"])

        project_id = body["data"]["id"]
        get_response = client.get(f"/projects/{project_id}")
        self.assertEqual(200, get_response.status_code)

        project = get_response.json()["data"]
        self.assertEqual(project_id, project["id"])
        self.assertEqual(user["id"], project["user_id"])
        self.assertEqual("MLP Template Project", project["name"])

        validation = validate_model_graph(project["model_graph"])
        self.assertTrue(validation["valid"], validation["errors"])

    def test_create_project_from_template_uses_default_name_and_description(self):
        user = self.create_user("tmpl_default")

        response = client.post("/projects/from-template", json={
            "user_id": user["id"],
            "template_name": "transformer_encoder_tiny",
        })

        self.assertEqual(200, response.status_code, response.text)
        project = response.json()["data"]
        self.assertEqual("Transformer Encoder Tiny Project", project["name"])
        self.assertIn("Transformer", project["description"])
        self.assertTrue(validate_model_graph(project["model_graph"])["valid"])

    def test_create_project_from_template_rejects_unknown_template(self):
        user = self.create_user("tmpl_unknown")

        response = client.post("/projects/from-template", json={
            "user_id": user["id"],
            "template_name": "not_exists",
            "name": "Bad Template Project",
        })

        self.assertEqual(404, response.status_code)
        body = response.json()
        self.assertEqual("error", body["status"])
        self.assertIn("available_templates", body)

    def test_create_project_from_template_rejects_unknown_user(self):
        response = client.post("/projects/from-template", json={
            "user_id": "user_not_exists",
            "template_name": "mlp",
            "name": "No User Project",
        })

        self.assertEqual(400, response.status_code)
        body = response.json()
        self.assertEqual("error", body["status"])
        self.assertIn("不存在", body["message"])

    def test_created_template_project_appears_in_project_list(self):
        user = self.create_user("template_list_user")
        create_response = client.post("/projects/from-template", json={
            "user_id": user["id"],
            "template_name": "gcn_tiny",
            "name": "GCN Template Project",
        })
        self.assertEqual(200, create_response.status_code, create_response.text)

        list_response = client.get(f"/projects?user_id={user['id']}")
        self.assertEqual(200, list_response.status_code)
        body = list_response.json()
        self.assertEqual("ok", body["status"])
        self.assertEqual(1, body["count"])
        self.assertEqual("GCN Template Project", body["data"][0]["name"])
        self.assertTrue(validate_model_graph(body["data"][0]["model_graph"])["valid"])


if __name__ == "__main__":
    unittest.main()

