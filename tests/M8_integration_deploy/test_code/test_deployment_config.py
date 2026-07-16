"""部署与配置回归测试（M8 · 人员 6）。

聚焦「可复现、不依赖真实 Nginx/生产机」的部署要素：CORS、JWT、SQLite 持久化、
.env 加载、前端构建配置与产物、README 与实际启动方式一致。

真正需要连真实环境的项（Nginx 反向代理、线上三端端到端、uvicorn 生产参数、
端口占用等）在测试设计文档的「手工部署验证」清单中人工执行并记录。

运行：
    python -m pytest tests/M8_integration_deploy/test_code/test_deployment_config.py -q
"""

import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import backend.storage as storage


class CorsConfigTests(unittest.TestCase):
    """CORS 跨域配置：允许开发前端源，拒绝未知源。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        storage.configure_database(f"sqlite:///{Path(cls._tmp.name) / 'cors.db'}")
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp.cleanup()

    # M8-002
    def test_allows_dev_frontend_origin(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            r = self.client.get("/health", headers={"Origin": origin})
            self.assertEqual(origin, r.headers.get("access-control-allow-origin"), origin)

    def test_rejects_unknown_origin(self):
        r = self.client.get("/health", headers={"Origin": "http://evil.example"})
        self.assertNotEqual("http://evil.example", r.headers.get("access-control-allow-origin"))


class JwtConfigTests(unittest.TestCase):
    """JWT 令牌签发 / 校验往返与防篡改。"""

    # M8-012
    def test_token_roundtrip(self):
        from backend.security import create_access_token, verify_access_token
        token = create_access_token("user_xyz")
        payload = verify_access_token(token)
        self.assertEqual("user_xyz", payload["sub"])

    # M8-013
    def test_tampered_token_rejected(self):
        from backend.security import create_access_token, verify_access_token
        token = create_access_token("user_xyz")
        with self.assertRaises(Exception):
            verify_access_token(token + "tamper")

    def test_secret_key_present(self):
        from backend.security import SECRET_KEY
        self.assertTrue(SECRET_KEY)


class SqlitePersistenceTests(unittest.TestCase):
    """SQLite 数据持久化：释放引擎再重连同一库，数据仍在（模拟服务重启）。"""

    # M8-014
    def test_data_persists_across_reconnect(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_url = f"sqlite:///{Path(tmp.name) / 'persist.db'}"

        storage.configure_database(db_url)
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        db_file = Path(tmp.name) / "persist.db"
        self.assertTrue(db_file.is_file(), "SQLite 库文件未落盘")

        storage.dispose_database()
        storage.configure_database(db_url)
        result = storage.get_user("u1")
        self.assertIsNotNone(result)
        self.assertEqual("alice", result["username"])
        storage.dispose_database()


class DotenvLoaderTests(unittest.TestCase):
    """.env 加载器可安全调用（缺文件时静默返回，不抛异常）。"""

    # M8-015
    def test_load_dotenv_does_not_raise(self):
        from backend.env import load_dotenv_if_present
        try:
            load_dotenv_if_present()
        except Exception as exc:  # noqa: BLE001
            self.fail(f"load_dotenv_if_present 抛出异常：{exc}")


class FrontendBuildTests(unittest.TestCase):
    """前端生产构建：构建脚本存在；若已构建则产物结构完整。"""

    FRONTEND = ROOT / "frontend"

    # M8-016
    def test_build_script_configured(self):
        import json
        pkg = json.loads((self.FRONTEND / "package.json").read_text(encoding="utf-8"))
        self.assertIn("build", pkg.get("scripts", {}), "package.json 缺少 build 脚本")
        self.assertTrue(
            any((self.FRONTEND / name).exists() for name in ("vite.config.ts", "vite.config.js")),
            "缺少 vite 配置",
        )

    def test_dist_output_sane_if_built(self):
        index = self.FRONTEND / "dist" / "index.html"
        if not index.is_file():
            self.skipTest("前端尚未构建（frontend/dist 不存在），请先运行 npm run build")
        html = index.read_text(encoding="utf-8")
        self.assertIn("/assets/", html)
        self.assertRegex(html, r"index-[A-Za-z0-9_-]+\.js")
        self.assertRegex(html, r"index-[A-Za-z0-9_-]+\.css")


class ReadmeConsistencyTests(unittest.TestCase):
    """README 启动命令与实际部署方式一致。"""

    # M8-017
    def test_readme_documents_start_commands(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("uvicorn", readme, "README 未记录 uvicorn 启动命令")
        self.assertIn("backend.main:app", readme, "README 未记录后端应用入口")
        self.assertRegex(readme, r"[Nn]ginx", "README 未记录 Nginx 部署")


class AgentDistributionTests(unittest.TestCase):
    """本机 Agent 长期令牌、运行时更新与公共发布包凭证安全。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.main import app
        cls.client = TestClient(app)

    # M8-019
    def test_long_lived_agent_token(self):
        from backend.security import create_access_token, verify_access_token

        login_token = create_access_token("agent_owner")
        response = self.client.get("/agent/token", params={"token": login_token})
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertGreater(body["expires_days"], 0)
        self.assertEqual("agent_owner", verify_access_token(body["token"])["sub"])

        rejected = self.client.get("/agent/token", params={"token": "invalid"})
        self.assertEqual(401, rejected.status_code)

    # M8-020
    def test_runtime_manifest_contract(self):
        response = self.client.get("/runtime/manifest")
        self.assertEqual(200, response.status_code, response.text)
        body = response.json()
        self.assertEqual("/runtime/download", body["download_url"])
        for field in ("version", "sha256", "size_bytes", "min_agent_version"):
            self.assertIn(field, body)
        self.assertRegex(body["sha256"], r"^[0-9a-f]{64}$")
        self.assertGreater(body["size_bytes"], 0)

    # M8-021
    def test_runtime_download_matches_manifest_hash(self):
        manifest = self.client.get("/runtime/manifest").json()
        response = self.client.get("/runtime/download")
        self.assertEqual(200, response.status_code, response.text)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.content)))
        self.assertEqual(manifest["size_bytes"], len(response.content))
        self.assertEqual(manifest["sha256"], hashlib.sha256(response.content).hexdigest())

    # M8-022
    def test_public_bundle_excludes_credentials_and_user_package_injects_token(self):
        from backend import cloud_training
        from tools import assemble_bundle

        self.assertIn("config.json", assemble_bundle.EXCLUDE_NAMES)
        self.assertTrue(assemble_bundle._excluded("config.json"))

        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "VisualDL-Agent.exe"
            artifact.write_bytes(b"agent-binary")
            package = cloud_training._build_app_package(
                artifact, "windows", "https://example.test", "agent-secret",
            )

        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            config_name = "VisualDL-Agent/config.json"
            self.assertIn(config_name, archive.namelist())
            config = json.loads(archive.read(config_name).decode("utf-8"))
        self.assertEqual("https://example.test", config["server_url"])
        self.assertEqual("agent-secret", config["token"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
