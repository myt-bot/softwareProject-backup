"""存储层单元测试。

测试 backend/storage.py 中所有 CRUD 操作的正常路径和边界条件。
编写者：甘淞文
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 确保 backend 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage


class TestStorageCRUD(unittest.TestCase):
    """测试本地 JSON 存储的 CRUD 操作。"""

    def setUp(self):
        """每个测试前创建临时目录，并重定向存储路径。"""
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp_dir.name)

        # 重定向存储路径到临时目录
        storage._STORAGE_DIR = self._data_dir
        storage._USERS_FILE = self._data_dir / "users.json"
        storage._PROJECTS_FILE = self._data_dir / "projects.json"

    def tearDown(self):
        """每个测试后清理临时目录。"""
        self._tmp_dir.cleanup()
        # 恢复默认路径
        storage._STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
        storage._USERS_FILE = storage._STORAGE_DIR / "users.json"
        storage._PROJECTS_FILE = storage._STORAGE_DIR / "projects.json"

    # --- 用户存储测试 ---

    def test_save_and_get_user(self):
        """测试保存用户后能正确获取。"""
        user = {"id": "u1", "username": "test_user", "email": "test@test.com"}
        storage.save_user(user)
        result = storage.get_user("u1")
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "test_user")

    def test_get_nonexistent_user(self):
        """测试获取不存在的用户返回 None。"""
        result = storage.get_user("nonexistent")
        self.assertIsNone(result)

    def test_list_users_empty(self):
        """测试空用户列表。"""
        users = storage.list_users()
        self.assertEqual(users, [])

    def test_list_users_with_filter(self):
        """测试按字段过滤用户。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        storage.save_user({"id": "u2", "username": "bob", "email": "b@b.com"})
        result = storage.list_users({"username": "alice"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "u1")

    def test_update_user(self):
        """测试更新用户。"""
        storage.save_user({"id": "u1", "username": "old", "email": "old@old.com"})
        result = storage.update_user("u1", {"username": "new"})
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "new")
        self.assertEqual(result["email"], "old@old.com")

    def test_update_nonexistent_user(self):
        """测试更新不存在的用户返回 None。"""
        result = storage.update_user("nonexistent", {"username": "x"})
        self.assertIsNone(result)

    def test_delete_user(self):
        """测试删除用户。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        self.assertTrue(storage.user_exists("u1"))
        result = storage.delete_user("u1")
        self.assertTrue(result)
        self.assertFalse(storage.user_exists("u1"))

    def test_delete_nonexistent_user(self):
        """测试删除不存在的用户返回 False。"""
        result = storage.delete_user("nonexistent")
        self.assertFalse(result)

    def test_user_exists(self):
        """测试用户存在性检查。"""
        self.assertFalse(storage.user_exists("u1"))
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        self.assertTrue(storage.user_exists("u1"))

    # --- 项目存储测试 ---

    def test_save_and_get_project(self):
        """测试保存项目后能正确获取。"""
        project = {
            "id": "p1",
            "user_id": "u1",
            "name": "test_project",
            "model_graph": {"layers": [], "connections": []},
        }
        storage.save_project(project)
        result = storage.get_project("p1")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "test_project")

    def test_get_nonexistent_project(self):
        """测试获取不存在的项目返回 None。"""
        result = storage.get_project("nonexistent")
        self.assertIsNone(result)

    def test_list_projects_by_user(self):
        """测试按用户过滤项目。"""
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "proj1",
            "model_graph": {"layers": [], "connections": []},
        })
        storage.save_project({
            "id": "p2", "user_id": "u2", "name": "proj2",
            "model_graph": {"layers": [], "connections": []},
        })
        result = storage.list_projects({"user_id": "u1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "p1")

    def test_update_project(self):
        """测试更新项目。"""
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "old",
            "model_graph": {"layers": [], "connections": []},
        })
        result = storage.update_project("p1", {"name": "new"})
        self.assertEqual(result["name"], "new")

    def test_delete_project(self):
        """测试删除项目。"""
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "proj1",
            "model_graph": {"layers": [], "connections": []},
        })
        self.assertTrue(storage.project_exists("p1"))
        storage.delete_project("p1")
        self.assertFalse(storage.project_exists("p1"))

    def test_delete_projects_by_user(self):
        """测试按用户删除所有项目。"""
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "proj1",
            "model_graph": {"layers": [], "connections": []},
        })
        storage.save_project({
            "id": "p2", "user_id": "u1", "name": "proj2",
            "model_graph": {"layers": [], "connections": []},
        })
        storage.save_project({
            "id": "p3", "user_id": "u2", "name": "proj3",
            "model_graph": {"layers": [], "connections": []},
        })
        deleted = storage.delete_projects_by_user("u1")
        self.assertEqual(deleted, 2)
        self.assertIsNone(storage.get_project("p1"))
        self.assertIsNone(storage.get_project("p2"))
        self.assertIsNotNone(storage.get_project("p3"))

    # --- 数据持久化测试 ---

    def test_data_persists_on_disk(self):
        """测试数据正确写入磁盘 JSON 文件。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        with open(storage._USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["username"], "alice")

    # --- 原子写入测试 ---

    def test_atomic_write_does_not_leave_tmp_file(self):
        """测试原子写入后不残留 .tmp 文件。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        tmp_file = storage._USERS_FILE.with_suffix(".tmp")
        self.assertFalse(tmp_file.exists(), "原子写入后不应残留 .tmp 文件")

    # --- 并发安全测试 ---

    def test_concurrent_writes(self):
        """测试多线程写入不会损坏数据。"""
        import threading

        def write_user(index):
            storage.save_user({
                "id": f"u{index}",
                "username": f"user_{index}",
                "email": f"user{index}@test.com",
            })

        threads = [threading.Thread(target=write_user, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        users = storage.list_users()
        self.assertEqual(len(users), 20)

    def test_concurrent_read_write(self):
        """测试并发读+写混合操作不会损坏数据。"""
        import threading

        # 预写入一些数据
        for i in range(10):
            storage.save_user({
                "id": f"u{i}",
                "username": f"user_{i}",
                "email": f"user{i}@test.com",
            })

        errors = []

        def reader():
            try:
                for _ in range(50):
                    data = storage.list_users()
                    # 读取到的数据应该都是合法列表
                    if not isinstance(data, list):
                        errors.append("读取到非列表数据")
            except Exception as e:
                errors.append(f"读取异常: {e}")

        def writer():
            try:
                for i in range(10, 30):
                    storage.save_user({
                        "id": f"u{i}",
                        "username": f"user_{i}",
                        "email": f"user{i}@test.com",
                    })
            except Exception as e:
                errors.append(f"写入异常: {e}")

        threads = []
        for _ in range(4):
            threads.append(threading.Thread(target=reader))
            threads.append(threading.Thread(target=writer))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发读写出现异常: {errors}")
        users = storage.list_users()
        self.assertGreaterEqual(len(users), 10)


if __name__ == "__main__":
    unittest.main()
