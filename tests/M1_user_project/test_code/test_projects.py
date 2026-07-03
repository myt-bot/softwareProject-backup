"""项目管理模块单元测试（M1）。

测试 backend/projects.py 中所有业务逻辑的正常路径和异常路径。
覆盖：项目 CRUD、权限控制测试（current_user_id 参数）。
编写者：甘淞文
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage
import backend.auth as auth_mgr
import backend.projects as project_mgr


# 测试用的合法模型图
VALID_MODEL_GRAPH = {
    "layers": [
        {
            "id": "input_1",
            "type": "Input",
            "name": "输入层",
            "params": {"shape": [1, 28, 28]},
        },
        {
            "id": "conv_1",
            "type": "Conv2D",
            "name": "卷积层",
            "params": {"out_channels": 16, "kernel_size": 3, "stride": 1, "padding": 0},
        },
        {
            "id": "output_1",
            "type": "Output",
            "name": "输出层",
            "params": {},
        },
    ],
    "connections": [
        {"source": "input_1", "target": "conv_1"},
        {"source": "conv_1", "target": "output_1"},
    ],
}


class TestProjectManager(unittest.TestCase):
    """测试项目管理 CRUD 操作的正常和异常路径。"""

    def setUp(self):
        """重定向存储到临时目录并创建测试用户。"""
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp_dir.name)
        storage._STORAGE_DIR = self._data_dir
        storage._USERS_FILE = self._data_dir / "users.json"
        storage._PROJECTS_FILE = self._data_dir / "projects.json"

        # 创建测试用户
        self._user = auth_mgr.create_user("testuser", "test@example.com", "testpass123")
        self._user_id = self._user["id"]

        # 创建第二个用户（用于权限测试）
        self._other_user = auth_mgr.create_user("otheruser", "other@example.com", "testpass123")
        self._other_user_id = self._other_user["id"]

    def tearDown(self):
        self._tmp_dir.cleanup()
        storage._STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
        storage._USERS_FILE = storage._STORAGE_DIR / "users.json"
        storage._PROJECTS_FILE = storage._STORAGE_DIR / "projects.json"

    # ========== 正常路径 ==========

    def test_create_project_success(self):
        """测试正常创建项目。"""
        project = project_mgr.create_project(
            self._user_id, "my_cnn", VALID_MODEL_GRAPH, "CNN 模型"
        )
        self.assertIn("id", project)
        self.assertTrue(project["id"].startswith("proj_"))
        self.assertEqual(project["user_id"], self._user_id)
        self.assertEqual(project["name"], "my_cnn")
        self.assertEqual(project["description"], "CNN 模型")
        self.assertEqual(project["model_graph"], VALID_MODEL_GRAPH)
        self.assertIn("created_at", project)
        self.assertIn("updated_at", project)

    def test_create_project_without_description(self):
        """测试不提供描述也能创建项目。"""
        project = project_mgr.create_project(
            self._user_id, "minimal", VALID_MODEL_GRAPH
        )
        self.assertEqual(project["description"], "")

    def test_create_project_with_current_user_id(self):
        """测试带 current_user_id 的权限校验 — 自己创建自己的项目。"""
        project = project_mgr.create_project(
            self._user_id, "my_proj", VALID_MODEL_GRAPH,
            current_user_id=self._user_id,
        )
        self.assertEqual(project["user_id"], self._user_id)

    def test_get_project_exists(self):
        """测试获取存在的项目。"""
        created = project_mgr.create_project(
            self._user_id, "my_cnn", VALID_MODEL_GRAPH
        )
        fetched = project_mgr.get_project(created["id"])
        self.assertEqual(fetched["name"], "my_cnn")

    def test_get_project_not_exists(self):
        """测试获取不存在的项目返回 None。"""
        result = project_mgr.get_project("proj_nonexistent")
        self.assertIsNone(result)

    def test_list_projects_all(self):
        """测试列出所有项目。"""
        project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        project_mgr.create_project(self._user_id, "p2", VALID_MODEL_GRAPH)
        projects = project_mgr.list_projects()
        self.assertEqual(len(projects), 2)

    def test_list_projects_by_user(self):
        """测试按用户过滤项目。"""
        project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        project_mgr.create_project(self._other_user_id, "p2", VALID_MODEL_GRAPH)
        result = project_mgr.list_projects(user_id=self._user_id)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "p1")

    def test_update_project_name(self):
        """测试更新项目名称（有权限）。"""
        created = project_mgr.create_project(self._user_id, "old", VALID_MODEL_GRAPH)
        updated = project_mgr.update_project(
            created["id"], name="new", current_user_id=self._user_id
        )
        self.assertEqual(updated["name"], "new")

    def test_update_project_model_graph(self):
        """测试更新模型图。"""
        created = project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        new_graph = {"layers": [VALID_MODEL_GRAPH["layers"][0]], "connections": []}
        updated = project_mgr.update_project(
            created["id"], model_graph=new_graph, current_user_id=self._user_id
        )
        self.assertEqual(len(updated["model_graph"]["layers"]), 1)

    def test_update_project_description(self):
        """测试更新项目描述。"""
        created = project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        updated = project_mgr.update_project(
            created["id"], description="新描述", current_user_id=self._user_id
        )
        self.assertEqual(updated["description"], "新描述")

    def test_delete_project_success(self):
        """测试删除项目（有权限）。"""
        created = project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        result = project_mgr.delete_project(
            created["id"], current_user_id=self._user_id
        )
        self.assertTrue(result)
        self.assertIsNone(project_mgr.get_project(created["id"]))

    def test_get_user_projects(self):
        """测试获取用户的所有项目。"""
        project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        project_mgr.create_project(self._user_id, "p2", VALID_MODEL_GRAPH)
        projects = project_mgr.get_user_projects(self._user_id)
        self.assertEqual(len(projects), 2)

    # ========== 权限控制测试（M1） ==========

    def test_create_project_cross_user_rejected(self):
        """测试用户 A 不能以用户 B 的身份创建项目。"""
        with self.assertRaises(PermissionError):
            project_mgr.create_project(
                self._other_user_id, "stolen", VALID_MODEL_GRAPH,
                current_user_id=self._user_id,
            )

    def test_update_project_wrong_owner_rejected(self):
        """测试非所有者不能修改项目。"""
        created = project_mgr.create_project(self._user_id, "my_proj", VALID_MODEL_GRAPH)
        with self.assertRaises(PermissionError):
            project_mgr.update_project(
                created["id"], name="hacked",
                current_user_id=self._other_user_id,
            )

    def test_delete_project_wrong_owner_rejected(self):
        """测试非所有者不能删除项目。"""
        created = project_mgr.create_project(self._user_id, "my_proj", VALID_MODEL_GRAPH)
        with self.assertRaises(PermissionError):
            project_mgr.delete_project(
                created["id"], current_user_id=self._other_user_id,
            )

    # ========== 异常路径 —— 创建 ==========

    def test_create_project_invalid_user(self):
        """测试创建给不存在的用户抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project("user_nonexistent", "p1", VALID_MODEL_GRAPH)

    def test_create_project_empty_user_id(self):
        """测试空 user_id 抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project("", "p1", VALID_MODEL_GRAPH)

    def test_create_project_empty_name(self):
        """测试空项目名抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, "", VALID_MODEL_GRAPH)

    def test_create_project_none_name(self):
        """测试 None 项目名抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, None, VALID_MODEL_GRAPH)

    def test_create_project_too_long_name(self):
        """测试过长的项目名抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, "a" * 101, VALID_MODEL_GRAPH)

    def test_create_project_duplicate_name(self):
        """测试同用户下重复项目名抛出异常。"""
        project_mgr.create_project(self._user_id, "my_cnn", VALID_MODEL_GRAPH)
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, "my_cnn", VALID_MODEL_GRAPH)

    def test_create_project_none_model_graph(self):
        """测试 None 模型图抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, "p1", None)

    def test_create_project_invalid_model_graph_not_dict(self):
        """测试非字典模型图抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(self._user_id, "p1", "not_a_dict")

    def test_create_project_invalid_model_graph_no_layers(self):
        """测试缺少 layers 的模型图抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(
                self._user_id, "p1", {"connections": []}
            )

    def test_create_project_invalid_model_graph_layers_not_list(self):
        """测试 layers 非列表抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(
                self._user_id, "p1", {"layers": "not_a_list"}
            )

    def test_create_project_too_long_description(self):
        """测试过长的描述抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.create_project(
                self._user_id, "p1", VALID_MODEL_GRAPH, "x" * 501
            )

    # ========== 异常路径 —— 获取 ==========

    def test_get_project_empty_id(self):
        """测试空 project_id 抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.get_project("")

    # ========== 异常路径 —— 更新 ==========

    def test_update_nonexistent_project(self):
        """测试更新不存在的项目抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.update_project("proj_nonexistent", name="new")

    def test_update_project_no_fields(self):
        """测试更新不提供任何字段抛出异常。"""
        created = project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        with self.assertRaises(ValueError):
            project_mgr.update_project(created["id"])

    def test_update_project_duplicate_name(self):
        """测试更新为同用户下已存在的项目名抛出异常。"""
        project_mgr.create_project(self._user_id, "p1", VALID_MODEL_GRAPH)
        p2 = project_mgr.create_project(self._user_id, "p2", VALID_MODEL_GRAPH)
        with self.assertRaises(ValueError):
            project_mgr.update_project(p2["id"], name="p1")

    # ========== 异常路径 —— 删除 ==========

    def test_delete_nonexistent_project(self):
        """测试删除不存在的项目抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.delete_project("proj_nonexistent")

    def test_delete_project_empty_id(self):
        """测试空 id 删除抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.delete_project("")

    # ========== 异常路径 —— 获取用户项目 ==========

    def test_get_user_projects_nonexistent_user(self):
        """测试获取不存在用户的 project 抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.get_user_projects("user_nonexistent")

    def test_get_user_projects_empty_id(self):
        """测试空 user_id 抛出异常。"""
        with self.assertRaises(ValueError):
            project_mgr.get_user_projects("")


if __name__ == "__main__":
    unittest.main()
