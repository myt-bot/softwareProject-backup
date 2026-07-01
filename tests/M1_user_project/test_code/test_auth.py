"""认证模块单元测试。

测试 backend/auth.py 中所有业务逻辑的正常路径和异常路径。
编写者：甘淞文
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage
import backend.auth as auth_mgr


class TestUserManager(unittest.TestCase):
    """测试用户管理 CRUD 操作的正常和异常路径。"""

    def setUp(self):
        """重定向存储到临时目录。"""
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp_dir.name)
        storage._STORAGE_DIR = self._data_dir
        storage._USERS_FILE = self._data_dir / "users.json"
        storage._PROJECTS_FILE = self._data_dir / "projects.json"

    def tearDown(self):
        self._tmp_dir.cleanup()
        storage._STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
        storage._USERS_FILE = storage._STORAGE_DIR / "users.json"
        storage._PROJECTS_FILE = storage._STORAGE_DIR / "projects.json"

    # ========== 正常路径 ==========

    def test_create_user_success(self):
        """测试正常创建用户。"""
        user = auth_mgr.create_user("testuser", "test@example.com")
        self.assertIn("id", user)
        self.assertTrue(user["id"].startswith("user_"))
        self.assertEqual(user["username"], "testuser")
        self.assertEqual(user["email"], "test@example.com")
        self.assertIn("created_at", user)

    def test_create_user_with_chinese_name(self):
        """测试中文用户名。"""
        user = auth_mgr.create_user("测试用户", "test@example.com")
        self.assertEqual(user["username"], "测试用户")

    def test_create_user_trims_whitespace(self):
        """测试用户名和邮箱自动去除首尾空格。"""
        user = auth_mgr.create_user("  alice  ", "  Alice@Example.COM  ")
        self.assertEqual(user["username"], "alice")
        self.assertEqual(user["email"], "alice@example.com")

    def test_get_user_exists(self):
        """测试获取存在的用户。"""
        created = auth_mgr.create_user("alice", "alice@test.com")
        fetched = auth_mgr.get_user(created["id"])
        self.assertEqual(fetched["username"], "alice")

    def test_get_user_not_exists(self):
        """测试获取不存在的用户返回 None。"""
        result = auth_mgr.get_user("user_nonexistent")
        self.assertIsNone(result)

    def test_list_users(self):
        """测试列出所有用户。"""
        auth_mgr.create_user("alice", "a@a.com")
        auth_mgr.create_user("bob", "b@b.com")
        users = auth_mgr.list_users()
        self.assertEqual(len(users), 2)

    def test_list_users_empty(self):
        """测试空用户列表。"""
        users = auth_mgr.list_users()
        self.assertEqual(users, [])

    def test_update_user_username(self):
        """测试更新用户名。"""
        created = auth_mgr.create_user("oldname", "old@test.com")
        updated = auth_mgr.update_user(created["id"], username="newname")
        self.assertEqual(updated["username"], "newname")
        self.assertEqual(updated["email"], "old@test.com")

    def test_update_user_email(self):
        """测试更新邮箱。"""
        created = auth_mgr.create_user("alice", "old@test.com")
        updated = auth_mgr.update_user(created["id"], email="new@test.com")
        self.assertEqual(updated["email"], "new@test.com")

    def test_update_user_both(self):
        """测试同时更新用户名和邮箱。"""
        created = auth_mgr.create_user("oldname", "old@test.com")
        updated = auth_mgr.update_user(created["id"], username="newname", email="new@test.com")
        self.assertEqual(updated["username"], "newname")
        self.assertEqual(updated["email"], "new@test.com")

    def test_delete_user_success(self):
        """测试删除用户。"""
        created = auth_mgr.create_user("alice", "a@a.com")
        result = auth_mgr.delete_user(created["id"])
        self.assertTrue(result)
        self.assertIsNone(auth_mgr.get_user(created["id"]))

    def test_get_users_by_ids(self):
        """测试批量获取用户。"""
        u1 = auth_mgr.create_user("alice", "a@a.com")
        u2 = auth_mgr.create_user("bob", "b@b.com")
        result = auth_mgr.get_users_by_ids([u1["id"], u2["id"], "nonexistent"])
        self.assertEqual(len(result), 2)
        self.assertIn(u1["id"], result)
        self.assertIn(u2["id"], result)

    # ========== 异常路径 —— 创建 ==========

    def test_create_user_empty_username(self):
        """测试空用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("", "test@test.com")

    def test_create_user_none_username(self):
        """测试 None 用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user(None, "test@test.com")

    def test_create_user_too_short_username(self):
        """测试过短的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("a", "test@test.com")

    def test_create_user_too_long_username(self):
        """测试过长的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("a" * 21, "test@test.com")

    def test_create_user_special_char_username(self):
        """测试含特殊字符的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("user@name", "test@test.com")

    def test_create_user_invalid_email(self):
        """测试非法邮箱抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("validname", "not-an-email")

    def test_create_user_empty_email(self):
        """测试空邮箱抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.create_user("validname", "")

    def test_create_user_duplicate_username(self):
        """测试重复用户名抛出异常。"""
        auth_mgr.create_user("alice", "a1@test.com")
        with self.assertRaises(ValueError):
            auth_mgr.create_user("alice", "a2@test.com")

    # ========== 异常路径 —— 获取 ==========

    def test_get_user_empty_id(self):
        """测试空 user_id 抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.get_user("")

    def test_get_user_none_id(self):
        """测试 None user_id 抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.get_user(None)

    # ========== 异常路径 —— 更新 ==========

    def test_update_nonexistent_user(self):
        """测试更新不存在的用户抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.update_user("user_nonexistent", username="newname")

    def test_update_user_no_fields(self):
        """测试更新时不提供任何字段抛出异常。"""
        created = auth_mgr.create_user("alice", "a@a.com")
        with self.assertRaises(ValueError):
            auth_mgr.update_user(created["id"])

    def test_update_user_duplicate_username(self):
        """测试更新为已存在的用户名抛出异常。"""
        auth_mgr.create_user("alice", "a@a.com")
        bob = auth_mgr.create_user("bob", "b@b.com")
        with self.assertRaises(ValueError):
            auth_mgr.update_user(bob["id"], username="alice")

    # ========== 异常路径 —— 删除 ==========

    def test_delete_nonexistent_user(self):
        """测试删除不存在的用户抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.delete_user("user_nonexistent")

    def test_delete_user_empty_id(self):
        """测试空 user_id 删除抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.delete_user("")

    # ========== 异常路径 —— 批量获取 ==========

    def test_get_users_by_ids_not_list(self):
        """测试传入非列表抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.get_users_by_ids("not_a_list")


if __name__ == "__main__":
    unittest.main()
