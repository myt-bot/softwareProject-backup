"""用户管理模块。

提供用户的创建、查询、更新、删除等操作。
当前使用本地 JSON 文件存储，后续可替换为数据库。
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .storage import (
    delete_user as _storage_delete_user,
    get_user as _storage_get_user,
    list_users as _storage_list_users,
    save_user as _storage_save_user,
    update_user as _storage_update_user,
    user_exists,
)


# ============================================================
# 常量
# ============================================================

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff]{2,20}$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ============================================================
# 用户数据校验
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


def _generate_user_id() -> str:
    """生成用户唯一标识。"""
    return f"user_{uuid4().hex[:12]}"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.utcnow().isoformat()


# ============================================================
# 业务逻辑
# ============================================================

def create_user(username: str, email: str) -> Dict[str, Any]:
    """创建新用户。

    参数：
        username：用户名，2-20 个字符，支持中英文、数字和下划线。
        email：用户邮箱，需符合基本邮箱格式。

    返回：
        创建成功的用户字典，包含 id、username、email、created_at。

    异常：
        ValueError：用户名或邮箱不合法，或用户名已存在。
    """
    # 校验
    username_error = _validate_username(username)
    if username_error:
        raise ValueError(f"用户名不合法: {username_error}")

    email_error = _validate_email(email)
    if email_error:
        raise ValueError(f"邮箱不合法: {email_error}")

    # 检查用户名唯一性
    existing = _storage_list_users({"username": username})
    if existing:
        raise ValueError(f"用户名 '{username}' 已被使用")

    # 创建
    user = {
        "id": _generate_user_id(),
        "username": username.strip(),
        "email": email.strip().lower(),
        "created_at": _now_iso(),
    }
    return _storage_save_user(user)


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取用户信息。

    参数：
        user_id：用户唯一标识。

    返回：
        用户字典；不存在时返回 None。

    异常：
        ValueError：user_id 为空。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")
    return _storage_get_user(user_id)


def list_users() -> List[Dict[str, Any]]:
    """获取所有用户列表。

    返回：
        用户字典列表。
    """
    return _storage_list_users()


def update_user(user_id: str, username: Optional[str] = None, email: Optional[str] = None) -> Dict[str, Any]:
    """更新用户信息。

    参数：
        user_id：用户唯一标识。
        username：新的用户名（可选）。
        email：新的邮箱（可选）。

    返回：
        更新后的用户字典。

    异常：
        ValueError：用户不存在、参数不合法或用户名冲突。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")

    if not user_exists(user_id):
        raise ValueError(f"用户 '{user_id}' 不存在")

    if username is None and email is None:
        raise ValueError("至少需要提供一个要更新的字段")

    updates = {}

    if username is not None:
        error = _validate_username(username)
        if error:
            raise ValueError(f"用户名不合法: {error}")
        existing = _storage_list_users({"username": username})
        if existing and existing[0]["id"] != user_id:
            raise ValueError(f"用户名 '{username}' 已被使用")
        updates["username"] = username.strip()

    if email is not None:
        error = _validate_email(email)
        if error:
            raise ValueError(f"邮箱不合法: {error}")
        updates["email"] = email.strip().lower()

    result = _storage_update_user(user_id, updates)
    if result is None:
        raise RuntimeError(f"更新用户 '{user_id}' 失败")
    return result


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


# ============================================================
# 批量查询
# ============================================================

def get_users_by_ids(user_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """批量按 id 获取用户信息。

    参数：
        user_ids：用户 id 列表。

    返回：
        {user_id: user_dict} 映射，不存在的 id 不会出现在结果中。
    """
    if not isinstance(user_ids, list):
        raise ValueError("user_ids 必须是列表")
    all_users = _storage_list_users()
    user_map = {u["id"]: u for u in all_users}
    return {uid: user_map[uid] for uid in user_ids if uid in user_map}
