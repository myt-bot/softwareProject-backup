"""安全模块单元测试（M1）。

针对 backend/security.py 的 JWT 令牌与 bcrypt 密码哈希逻辑做直接单元测试，
对应《测试计划》M1 用例表：
    TC1-09 JWT 签发与校验
    TC1-10 JWT 过期与防篡改
    TC1-11 令牌对应用户已失效
    TC1-12 密码哈希与校验

与其它 M1 测试一致：需要用户存储的用例通过临时 SQLite 隔离数据，互不影响。
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

import backend.auth as auth
import backend.storage as storage
from backend.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_current_user,
    hash_password,
    verify_access_token,
    verify_password,
)


# ============================================================
# TC1-12 密码哈希与校验（bcrypt）
# ============================================================

class TestPasswordHashing(unittest.TestCase):
    """密码哈希与校验：哈希≠明文、加盐、正确/错误密码校验。"""

    PLAIN = "testpass123"

    def test_hash_differs_from_plaintext(self):
        """哈希结果不等于明文。"""
        hashed = hash_password(self.PLAIN)
        self.assertNotEqual(hashed, self.PLAIN)
        self.assertNotIn(self.PLAIN, hashed)

    def test_hash_is_salted(self):
        """同一密码两次哈希结果不同（加盐）。"""
        self.assertNotEqual(hash_password(self.PLAIN), hash_password(self.PLAIN))

    def test_hash_uses_bcrypt_scheme(self):
        """哈希串使用 bcrypt 方案标识（$2...）。"""
        self.assertTrue(hash_password(self.PLAIN).startswith("$2"))

    def test_verify_correct_password(self):
        """正确密码校验通过。"""
        hashed = hash_password(self.PLAIN)
        self.assertTrue(verify_password(self.PLAIN, hashed))

    def test_verify_wrong_password(self):
        """错误密码校验失败。"""
        hashed = hash_password(self.PLAIN)
        self.assertFalse(verify_password("wrong-password9", hashed))


# ============================================================
# TC1-09 JWT 签发与校验
# ============================================================

class TestJwtIssueAndVerify(unittest.TestCase):
    """JWT 签发与校验：三段式、sub 与用户 id 一致、含 exp/iat、可正常校验。"""

    USER_ID = "user_jwt_demo"

    def test_token_is_three_segments(self):
        """令牌为三段式（header.payload.signature）。"""
        token = create_access_token(self.USER_ID)
        self.assertEqual(len(token.split(".")), 3)

    def test_verify_returns_matching_sub(self):
        """校验后 payload 的 sub 与签发用户 id 一致。"""
        token = create_access_token(self.USER_ID)
        payload = verify_access_token(token)
        self.assertEqual(payload["sub"], self.USER_ID)

    def test_payload_contains_exp_and_iat(self):
        """payload 含过期时间 exp 与签发时间 iat。"""
        payload = verify_access_token(create_access_token(self.USER_ID))
        self.assertIn("exp", payload)
        self.assertIn("iat", payload)

    def test_roundtrip_valid_token(self):
        """签发再校验的往返流程正常，不抛异常。"""
        token = create_access_token(self.USER_ID)
        try:
            verify_access_token(token)
        except HTTPException:  # pragma: no cover - 正常路径不应抛出
            self.fail("合法令牌不应校验失败")


# ============================================================
# TC1-10 JWT 过期与防篡改
# ============================================================

class TestJwtExpiryAndTamper(unittest.TestCase):
    """过期 / 被篡改 / 改密钥 / 缺 sub 的令牌均应返回 401。"""

    USER_ID = "user_jwt_bad"

    def _assert_unauthorized(self, token):
        with self.assertRaises(HTTPException) as ctx:
            verify_access_token(token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_token_rejected(self):
        """过期令牌返回 401。"""
        expired = create_access_token(self.USER_ID, expires_minutes=-1)
        self._assert_unauthorized(expired)

    def test_tampered_token_rejected(self):
        """被篡改（签名段被改）的令牌返回 401。"""
        token = create_access_token(self.USER_ID)
        last = token[-1]
        tampered = token[:-1] + ("A" if last != "A" else "B")
        self._assert_unauthorized(tampered)

    def test_wrong_secret_token_rejected(self):
        """用其它密钥签发的令牌返回 401。"""
        forged = jwt.encode({"sub": self.USER_ID}, "another-secret-key", algorithm=ALGORITHM)
        self._assert_unauthorized(forged)

    def test_missing_sub_token_rejected(self):
        """缺少 sub 的令牌返回 401。"""
        no_sub = jwt.encode({"foo": "bar"}, SECRET_KEY, algorithm=ALGORITHM)
        self._assert_unauthorized(no_sub)

    def test_garbage_token_rejected(self):
        """非法字符串（非 JWT）返回 401。"""
        self._assert_unauthorized("not.a.valid.jwt")


# ============================================================
# TC1-11 令牌对应用户已失效
# ============================================================

class TestCurrentUserResolution(unittest.TestCase):
    """get_current_user：有效用户返回用户，用户已删除返回 401。"""

    _tmp_dir = None

    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        storage.configure_database(f"sqlite:///{Path(cls._tmp_dir.name) / 'sec.db'}")

    @classmethod
    def tearDownClass(cls):
        storage.dispose_database()
        cls._tmp_dir.cleanup()

    @staticmethod
    def _credentials(token):
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_valid_token_existing_user_returns_user(self):
        """有效令牌且用户存在时，返回对应用户。"""
        user = auth.register_user("sec_ok", "sec_ok@test.com", "testpass123")
        token = create_access_token(user["id"])
        resolved = get_current_user(self._credentials(token))
        self.assertEqual(resolved["id"], user["id"])
        self.assertNotIn("password_hash", resolved)

    def test_valid_token_deleted_user_rejected(self):
        """令牌有效但用户已被删除时返回 401。"""
        user = auth.register_user("sec_gone", "sec_gone@test.com", "testpass123")
        token = create_access_token(user["id"])
        auth.delete_user(user["id"])
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(self._credentials(token))
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
