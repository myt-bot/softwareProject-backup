"""存储层单元测试。

测试 backend/storage.py 中所有 CRUD 操作的正常路径和边界条件。
存储层已迁移至数据库（生产 MySQL），测试使用独立的临时 SQLite 库隔离数据，
表结构与约束（邮箱唯一、同用户项目名唯一、外键级联）由同一份定义生成。
"""

import sys
import tempfile
import unittest
from pathlib import Path

# 确保 backend 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage


class TestStorageCRUD(unittest.TestCase):
    """测试数据库存储的 CRUD 操作。"""

    def setUp(self):
        """每个测试前把存储切换到临时目录下的独立 SQLite 库。"""
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp_dir.name)
        self._db_url = f"sqlite:///{self._data_dir / 'test.db'}"
        storage.configure_database(self._db_url)

    def tearDown(self):
        """每个测试后释放引擎并清理临时目录。"""
        storage.dispose_database()
        self._tmp_dir.cleanup()

    def _seed_user(self, user_id, email=None):
        """插入一个满足项目外键依赖的最小用户记录。"""
        storage.save_user({
            "id": user_id,
            "username": f"owner_{user_id}",
            "email": email or f"{user_id}@seed.com",
        })

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
        self._seed_user("u1")
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
        # 嵌套模型图（JSON 列）应完整往返
        self.assertEqual(result["model_graph"], {"layers": [], "connections": []})

    def test_get_nonexistent_project(self):
        """测试获取不存在的项目返回 None。"""
        result = storage.get_project("nonexistent")
        self.assertIsNone(result)

    def test_list_projects_by_user(self):
        """测试按用户过滤项目。"""
        self._seed_user("u1")
        self._seed_user("u2")
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
        self._seed_user("u1")
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "old",
            "model_graph": {"layers": [], "connections": []},
        })
        result = storage.update_project("p1", {"name": "new"})
        self.assertEqual(result["name"], "new")

    def test_delete_project(self):
        """测试删除项目。"""
        self._seed_user("u1")
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "proj1",
            "model_graph": {"layers": [], "connections": []},
        })
        self.assertTrue(storage.project_exists("p1"))
        storage.delete_project("p1")
        self.assertFalse(storage.project_exists("p1"))

    def test_delete_projects_by_user(self):
        """测试按用户删除所有项目。"""
        self._seed_user("u1")
        self._seed_user("u2")
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

    def test_data_persists_across_reconnect(self):
        """测试数据落库后，重建连接仍能读到（持久化验证）。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "a@a.com"})
        # 释放引擎再重连同一个库，模拟服务重启
        storage.dispose_database()
        storage.configure_database(self._db_url)
        result = storage.get_user("u1")
        self.assertIsNotNone(result)
        self.assertEqual(result["username"], "alice")

    # --- 数据库约束测试（并发兜底，业务层预检查之外的最后防线） ---

    def test_duplicate_email_rejected_by_db(self):
        """测试邮箱唯一约束：重复邮箱直接被数据库拒绝。"""
        storage.save_user({"id": "u1", "username": "alice", "email": "same@test.com"})
        with self.assertRaises(ValueError):
            storage.save_user({"id": "u2", "username": "bob", "email": "same@test.com"})

    def test_duplicate_project_name_rejected_by_db(self):
        """测试同用户下项目名唯一约束。"""
        self._seed_user("u1")
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "same_name",
            "model_graph": {"layers": [], "connections": []},
        })
        with self.assertRaises(ValueError):
            storage.save_project({
                "id": "p2", "user_id": "u1", "name": "same_name",
                "model_graph": {"layers": [], "connections": []},
            })

    def test_same_project_name_allowed_for_different_users(self):
        """测试不同用户可以使用相同的项目名。"""
        self._seed_user("u1")
        self._seed_user("u2")
        storage.save_project({
            "id": "p1", "user_id": "u1", "name": "same_name",
            "model_graph": {"layers": [], "connections": []},
        })
        storage.save_project({
            "id": "p2", "user_id": "u2", "name": "same_name",
            "model_graph": {"layers": [], "connections": []},
        })
        self.assertEqual(len(storage.list_projects()), 2)

    def test_project_with_nonexistent_user_rejected_by_db(self):
        """测试外键约束：所属用户不存在的项目被数据库拒绝。"""
        with self.assertRaises(ValueError):
            storage.save_project({
                "id": "p1", "user_id": "no_such_user", "name": "orphan",
                "model_graph": {"layers": [], "connections": []},
            })

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
                    try:
                        storage.save_user({
                            "id": f"u{i}",
                            "username": f"user_{i}",
                            "email": f"user{i}@test.com",
                        })
                    except ValueError:
                        # 多个 writer 线程写同一批 id/邮箱时，
                        # 唯一约束拒绝后写者属于正常兜底行为
                        pass
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
