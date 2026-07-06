"""认证模块单元测试（M1）。

测试 backend/auth.py 中所有业务逻辑的正常路径和异常路径。
覆盖：注册、登录、密码强度校验、用户 CRUD。
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import backend.storage as storage
import backend.auth as auth_mgr

# 测试用合法密码
VALID_PASSWORD = "testpass123"


class TestUserManager(unittest.TestCase):
    """测试用户管理 CRUD 操作的正常和异常路径。"""

    def setUp(self):
        """把存储切换到临时目录下的独立 SQLite 库。"""
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._data_dir = Path(self._tmp_dir.name)
        storage.configure_database(f"sqlite:///{self._data_dir / 'test.db'}")

    def tearDown(self):
        storage.dispose_database()
        self._tmp_dir.cleanup()

    # ========== 正常路径 ==========

    def test_create_user_success(self):
        """测试正常创建用户。"""
        user = auth_mgr.register_user("testuser", "test@example.com", VALID_PASSWORD)
        self.assertIn("id", user)
        self.assertTrue(user["id"].startswith("user_"))
        self.assertEqual(user["username"], "testuser")
        self.assertEqual(user["email"], "test@example.com")
        self.assertIn("created_at", user)
        # 返回的用户不能包含 password_hash
        self.assertNotIn("password_hash", user)

    def test_create_user_with_chinese_name(self):
        """测试中文用户名。"""
        user = auth_mgr.register_user("测试用户", "test@example.com", VALID_PASSWORD)
        self.assertEqual(user["username"], "测试用户")

    def test_create_user_trims_whitespace(self):
        """测试用户名和邮箱自动去除首尾空格。"""
        user = auth_mgr.register_user("  alice  ", "  Alice@Example.COM  ", VALID_PASSWORD)
        self.assertEqual(user["username"], "alice")
        self.assertEqual(user["email"], "alice@example.com")

    def test_get_user_exists(self):
        """测试获取存在的用户。"""
        created = auth_mgr.register_user("alice", "alice@test.com", VALID_PASSWORD)
        fetched = auth_mgr.get_user(created["id"])
        self.assertEqual(fetched["username"], "alice")

    def test_get_user_not_exists(self):
        """测试获取不存在的用户返回 None。"""
        result = auth_mgr.get_user("user_nonexistent")
        self.assertIsNone(result)

    def test_list_users(self):
        """测试列出所有用户。"""
        auth_mgr.register_user("alice", "a@a.com", VALID_PASSWORD)
        auth_mgr.register_user("bob", "b@b.com", VALID_PASSWORD)
        users = auth_mgr.list_users()
        self.assertEqual(len(users), 2)

    def test_list_users_empty(self):
        """测试空用户列表。"""
        users = auth_mgr.list_users()
        self.assertEqual(users, [])

    def test_update_user_username(self):
        """测试更新用户名。"""
        created = auth_mgr.register_user("oldname", "old@test.com", VALID_PASSWORD)
        updated = auth_mgr.update_user(created["id"], username="newname")
        self.assertEqual(updated["username"], "newname")
        self.assertEqual(updated["email"], "old@test.com")

    def test_update_user_email(self):
        """测试更新邮箱。"""
        created = auth_mgr.register_user("alice", "old@test.com", VALID_PASSWORD)
        updated = auth_mgr.update_user(created["id"], email="new@test.com")
        self.assertEqual(updated["email"], "new@test.com")

    def test_update_user_password(self):
        """测试更新密码。"""
        created = auth_mgr.register_user("alice", "old@test.com", VALID_PASSWORD)
        updated = auth_mgr.update_user(created["id"], password="newpass456")
        self.assertIsNotNone(updated)
        self.assertNotIn("password_hash", updated)

    def test_update_user_both(self):
        """测试同时更新用户名和邮箱。"""
        created = auth_mgr.register_user("oldname", "old@test.com", VALID_PASSWORD)
        updated = auth_mgr.update_user(created["id"], username="newname", email="new@test.com")
        self.assertEqual(updated["username"], "newname")
        self.assertEqual(updated["email"], "new@test.com")

    def test_delete_user_success(self):
        """测试删除用户。"""
        created = auth_mgr.register_user("alice", "a@a.com", VALID_PASSWORD)
        result = auth_mgr.delete_user(created["id"])
        self.assertTrue(result)
        self.assertIsNone(auth_mgr.get_user(created["id"]))

    def test_register_user_success(self):
        """测试 register_user 正常注册。"""
        user = auth_mgr.register_user("newuser", "new@test.com", "mypass123")
        self.assertIn("id", user)
        self.assertEqual(user["username"], "newuser")
        self.assertNotIn("password_hash", user)

    def test_authenticate_user_success(self):
        """测试正确凭据登录成功。"""
        auth_mgr.register_user("loginuser", "login@test.com", "mypass123")
        user = auth_mgr.authenticate_user("login@test.com", "mypass123")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "loginuser")
        self.assertNotIn("password_hash", user)

    def test_authenticate_user_wrong_password(self):
        """测试错误密码登录失败。"""
        auth_mgr.register_user("loginuser", "login@test.com", "mypass123")
        user = auth_mgr.authenticate_user("login@test.com", "wrongpassword")
        self.assertIsNone(user)

    def test_authenticate_user_nonexistent(self):
        """测试不存在的用户（邮箱未注册）登录失败。"""
        user = auth_mgr.authenticate_user("no@test.com", "somepass")
        self.assertIsNone(user)

    def test_authenticate_user_empty_credentials(self):
        """测试空邮箱/密码返回 None。"""
        auth_mgr.register_user("loginuser", "login@test.com", "mypass123")
        self.assertIsNone(auth_mgr.authenticate_user("", "mypass123"))
        self.assertIsNone(auth_mgr.authenticate_user("login@test.com", ""))

    def test_authenticate_user_trims_whitespace(self):
        """测试登录时邮箱能正确处理首尾空格。"""
        auth_mgr.register_user("loginuser", "login@test.com", "mypass123")
        user = auth_mgr.authenticate_user("  login@test.com  ", "mypass123")
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "loginuser")

    # ========== 异常路径 —— 创建 ==========

    def test_create_user_empty_username(self):
        """测试空用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("", "test@test.com", VALID_PASSWORD)

    def test_create_user_none_username(self):
        """测试 None 用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user(None, "test@test.com", VALID_PASSWORD)

    def test_create_user_too_short_username(self):
        """测试过短的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("a", "test@test.com", VALID_PASSWORD)

    def test_create_user_too_long_username(self):
        """测试过长的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("a" * 21, "test@test.com", VALID_PASSWORD)

    def test_create_user_special_char_username(self):
        """测试含特殊字符的用户名抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("user@name", "test@test.com", VALID_PASSWORD)

    def test_create_user_invalid_email(self):
        """测试非法邮箱抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "not-an-email", VALID_PASSWORD)

    def test_create_user_empty_email(self):
        """测试空邮箱抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "", VALID_PASSWORD)

    def test_create_user_duplicate_email(self):
        """测试重复邮箱抛出异常（邮箱必须唯一）。"""
        auth_mgr.register_user("alice", "same@test.com", VALID_PASSWORD)
        with self.assertRaises(ValueError):
            auth_mgr.register_user("bob", "same@test.com", VALID_PASSWORD)

    def test_create_user_duplicate_username_allowed(self):
        """测试相同用户名可以使用不同邮箱注册（用户名可重复）。"""
        u1 = auth_mgr.register_user("alice", "a1@test.com", VALID_PASSWORD)
        u2 = auth_mgr.register_user("alice", "a2@test.com", VALID_PASSWORD)
        self.assertEqual(u1["username"], "alice")
        self.assertEqual(u2["username"], "alice")
        self.assertNotEqual(u1["id"], u2["id"])

    def test_create_user_duplicate_email_whitespace_bypass(self):
        """测试邮箱空格绕过唯一性检查。"""
        auth_mgr.register_user("alice", "same@test.com", VALID_PASSWORD)
        with self.assertRaises(ValueError):
            auth_mgr.register_user("bob", "  same@test.com  ", VALID_PASSWORD)

    # --- 密码校验 ---

    def test_create_user_empty_password(self):
        """测试空密码抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "test@test.com", "")

    def test_create_user_none_password(self):
        """测试 None 密码抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "test@test.com", None)

    def test_create_user_short_password(self):
        """测试过短密码抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "test@test.com", "ab1")

    def test_create_user_password_no_letter(self):
        """测试无字母密码抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "test@test.com", "12345678")

    def test_create_user_password_no_digit(self):
        """测试无数字密码抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user("validname", "test@test.com", "abcdefgh")

    # --- 确认密码校验 ---

    def test_register_user_confirm_password_match(self):
        """测试确认密码一致时注册成功。"""
        user = auth_mgr.register_user(
            "confirmuser", "confirm@test.com", VALID_PASSWORD,
            confirm_password=VALID_PASSWORD,
        )
        self.assertEqual(user["username"], "confirmuser")
        self.assertNotIn("password_hash", user)

    def test_register_user_confirm_password_mismatch(self):
        """测试确认密码不一致抛出异常。"""
        with self.assertRaises(ValueError) as ctx:
            auth_mgr.register_user(
                "confirmuser", "confirm@test.com", VALID_PASSWORD,
                confirm_password="different123",
            )
        self.assertIn("不一致", str(ctx.exception))

    def test_register_user_confirm_password_empty_mismatch(self):
        """测试确认密码为空字符串（与密码不一致）抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.register_user(
                "confirmuser", "confirm@test.com", VALID_PASSWORD,
                confirm_password="",
            )

    def test_register_user_without_confirm_password(self):
        """测试不传确认密码时跳过一致性校验（兼容内部创建用户场景）。"""
        user = auth_mgr.register_user("noconfirm", "noconfirm@test.com", VALID_PASSWORD)
        self.assertEqual(user["username"], "noconfirm")

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
        created = auth_mgr.register_user("alice", "a@a.com", VALID_PASSWORD)
        with self.assertRaises(ValueError):
            auth_mgr.update_user(created["id"])

    def test_update_user_duplicate_email(self):
        """测试更新为已存在的邮箱抛出异常。"""
        auth_mgr.register_user("alice", "a@a.com", VALID_PASSWORD)
        bob = auth_mgr.register_user("bob", "b@b.com", VALID_PASSWORD)
        with self.assertRaises(ValueError):
            auth_mgr.update_user(bob["id"], email="a@a.com")

    # ========== 异常路径 —— 删除 ==========

    def test_delete_nonexistent_user(self):
        """测试删除不存在的用户抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.delete_user("user_nonexistent")

    def test_delete_user_empty_id(self):
        """测试空 user_id 删除抛出异常。"""
        with self.assertRaises(ValueError):
            auth_mgr.delete_user("")


if __name__ == "__main__":
    unittest.main()
