"""用户管理模块（M1）。

提供用户的注册、登录、查询、更新、删除等操作。
当前使用本地 JSON 文件存储，后续可替换为数据库。

安全特性：
- 密码使用 bcrypt 哈希存储，永不返回明文或哈希值
- JWT 令牌认证，默认 60 分钟过期
- 用户注册时自动校验密码复杂度

业务规则：
- 用户名可以重复，邮箱必须唯一（注册和登录都以邮箱为核心标识）
- 注册成功后可直接登录（由 API 层颁发 JWT）
- 登录时若邮箱未注册，提示用户先注册

已知限制：当前未实现分页，list_users() 一次性返回全部用户数据。
"""

import re
from typing import Any, Dict, List, Optional

from .storage import (
    delete_user as _storage_delete_user,
    get_user as _storage_get_user,
    list_users as _storage_list_users,
    save_user as _storage_save_user,
    update_user as _storage_update_user,
    user_exists,
)
from datetime import datetime, timezone
from uuid import uuid4


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def generate_user_id() -> str:
    """生成用户唯一标识，前缀为 user_。"""
    return f"user_{uuid4().hex[:12]}"


# ============================================================
# 常量
# ============================================================

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_一-鿿]{2,20}$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# 密码规则：8-128 字符，至少包含一个字母和一个数字
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
PASSWORD_HAS_LETTER = re.compile(r"[a-zA-Z]")
PASSWORD_HAS_DIGIT = re.compile(r"\d")


# ============================================================
# 数据校验
# ============================================================

def _validate_username(username: str) -> Optional[str]:
    """校验用户名，合法返回 None，非法返回错误信息。"""
    if not username or not isinstance(username, str):
        return "用户名不能为空"
    username = username.strip()
    if not username:
        return "用户名不能为空"
    if not USERNAME_PATTERN.match(username):
        return "用户名需为 2-20 个字符，支持中英文、数字和下划线"
    return None


def _validate_email(email: str) -> Optional[str]:
    """校验邮箱，合法返回 None，非法返回错误信息。"""
    if not email or not isinstance(email, str):
        return "邮箱不能为空"
    email = email.strip().lower()
    if not email:
        return "邮箱不能为空"
    if not EMAIL_PATTERN.match(email):
        return "邮箱格式不合法"
    return None


def _validate_password(password: str) -> Optional[str]:
    """校验密码强度，合法返回 None，非法返回错误信息。

    规则：8-128 字符，至少包含一个字母和一个数字。
    """
    if not password or not isinstance(password, str):
        return "密码不能为空"
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"密码不能少于 {PASSWORD_MIN_LENGTH} 个字符"
    if len(password) > PASSWORD_MAX_LENGTH:
        return f"密码不能超过 {PASSWORD_MAX_LENGTH} 个字符"
    if not PASSWORD_HAS_LETTER.search(password):
        return "密码必须包含至少一个字母"
    if not PASSWORD_HAS_DIGIT.search(password):
        return "密码必须包含至少一个数字"
    return None


def _sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """去除用户字典中的敏感字段（password_hash），返回安全的副本。"""
    safe = {k: v for k, v in user.items() if k != "password_hash"}
    return safe


# ============================================================
# 业务逻辑
# ============================================================

def register_user(
    username: str,
    email: str,
    password: str,
    confirm_password: Optional[str] = None,
) -> Dict[str, Any]:
    """注册新用户（含密码哈希）。

    参数：
        username：用户名，2-20 个字符，支持中英文、数字和下划线（可重复）。
        email：用户邮箱，需符合基本邮箱格式（必须唯一）。
        password：明文密码，8-128 字符，至少含一个字母和一个数字。
        confirm_password：确认密码，需与 password 完全一致；传 None 时跳过
            该项校验（供内部创建用户等无确认密码的场景使用）。

    返回：
        创建成功的用户字典（不含 password_hash），包含 id、username、email、created_at。

    异常：
        ValueError：参数不合法、两次密码不一致或邮箱已被注册。
    """
    from .security import hash_password as _hash_password

    # 校验
    username_error = _validate_username(username)
    if username_error:
        raise ValueError(f"用户名不合法: {username_error}")

    email_error = _validate_email(email)
    if email_error:
        raise ValueError(f"邮箱不合法: {email_error}")

    password_error = _validate_password(password)
    if password_error:
        raise ValueError(f"密码不合法: {password_error}")

    if confirm_password is not None and confirm_password != password:
        raise ValueError("确认密码不合法: 两次输入的密码不一致")

    # 检查邮箱唯一性（邮箱是用户唯一标识）
    email_clean = email.strip().lower()
    existing = _storage_list_users({"email": email_clean})
    if existing:
        raise ValueError(f"邮箱 '{email_clean}' 已被注册")

    # 创建
    now = now_iso()
    user = {
        "id": generate_user_id(),
        "username": username.strip(),
        "email": email_clean,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    saved = _storage_save_user(user)
    return _sanitize_user(saved)



def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """按邮箱查找用户（邮箱唯一）。

    参数：
        email：用户邮箱。

    返回：
        用户字典（不含 password_hash）；不存在时返回 None。
    """
    if not email or not isinstance(email, str):
        return None
    email_clean = email.strip().lower()
    existing = _storage_list_users({"email": email_clean})
    if not existing:
        return None
    return _sanitize_user(existing[0])


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """验证用户凭据，成功返回用户信息，失败返回 None。

    以邮箱作为唯一标识查找用户，校验密码。

    参数：
        email：用户邮箱（唯一标识）。
        password：明文密码。

    返回：
        用户字典（不含 password_hash）；邮箱不存在或密码错误时返回 None。
    """
    from .security import verify_password as _verify_password

    if not email or not password:
        return None

    # 按邮箱（唯一标识）查找
    email_clean = email.strip().lower()
    existing = _storage_list_users({"email": email_clean})
    if not existing:
        return None

    user = existing[0]

    # 兼容旧数据（无 password_hash 字段的用户）
    stored_hash = user.get("password_hash")
    if not stored_hash:
        return None

    if not _verify_password(password, stored_hash):
        return None

    return _sanitize_user(user)


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取用户信息。

    参数：
        user_id：用户唯一标识。

    返回：
        用户字典（不含 password_hash）；不存在时返回 None。

    异常：
        ValueError：user_id 为空。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")
    user = _storage_get_user(user_id)
    if user is None:
        return None
    return _sanitize_user(user)


def list_users() -> List[Dict[str, Any]]:
    """获取所有用户列表。

    返回：
        用户字典列表（不含 password_hash）。
    """
    users = _storage_list_users()
    return [_sanitize_user(u) for u in users]


def update_user(
    user_id: str,
    username: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """更新用户信息。

    参数：
        user_id：用户唯一标识。
        username：新的用户名（可选）。
        email：新的邮箱（可选，需保证唯一）。
        password：新的明文密码（可选）。

    返回：
        更新后的用户字典（不含 password_hash）。

    异常：
        ValueError：用户不存在、参数不合法或邮箱冲突。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")

    if not user_exists(user_id):
        raise ValueError(f"用户 '{user_id}' 不存在")

    if username is None and email is None and password is None:
        raise ValueError("至少需要提供一个要更新的字段")

    updates = {}

    if username is not None:
        error = _validate_username(username)
        if error:
            raise ValueError(f"用户名不合法: {error}")
        updates["username"] = username.strip()

    if email is not None:
        error = _validate_email(email)
        if error:
            raise ValueError(f"邮箱不合法: {error}")
        email_clean = email.strip().lower()
        # 检查邮箱唯一性（排除自身）
        existing = _storage_list_users({"email": email_clean})
        if existing and existing[0]["id"] != user_id:
            raise ValueError(f"邮箱 '{email_clean}' 已被使用")
        updates["email"] = email_clean

    if password is not None:
        from .security import hash_password as _hash_password

        error = _validate_password(password)
        if error:
            raise ValueError(f"密码不合法: {error}")
        updates["password_hash"] = _hash_password(password)

    updates["updated_at"] = now_iso()

    result = _storage_update_user(user_id, updates)
    if result is None:
        raise RuntimeError(f"更新用户 '{user_id}' 失败")
    return _sanitize_user(result)


def delete_user(user_id: str) -> bool:
    """删除用户及其关联的所有项目。

    参数：
        user_id：用户唯一标识。

    返回：
        删除成功返回 True。

    异常：
        ValueError：user_id 为空或用户不存在。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")

    if not user_exists(user_id):
        raise ValueError(f"用户 '{user_id}' 不存在")

    from .storage import delete_projects_by_user as _delete_projects

    _delete_projects(user_id)
    return _storage_delete_user(user_id)


