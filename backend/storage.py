"""本地 JSON 文件存储层。

提供基于 JSON 文件的持久化存储能力，为后续切换为数据库存储预留统一接口。
所有写操作自动创建目录和文件，保证首次运行无需手动初始化。

已知限制：当前未实现分页，list_users() 和 list_projects() 一次性加载全部数据。
"""

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# 存储路径配置
# ============================================================

_STORAGE_DIR = Path(__file__).resolve().parent.parent / "data"
_USERS_FILE = _STORAGE_DIR / "users.json"
_PROJECTS_FILE = _STORAGE_DIR / "projects.json"

# 可重入锁，保护所有读写操作，防止并发导致数据损坏
_lock = threading.RLock()


# ============================================================
# 底层文件读写
# ============================================================

def _ensure_storage() -> None:
    """确保存储目录和 JSON 文件存在（线程安全）。"""
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        for file_path in (_USERS_FILE, _PROJECTS_FILE):
            if not file_path.exists():
                _write_json_unsafe(file_path, [])


def _read_json_unsafe(file_path: Path) -> List[Dict[str, Any]]:
    """从 JSON 文件读取数据列表（调用方需持有 _lock）。

    返回：
        数据列表；文件不存在或 JSON 格式异常时返回空列表。
        注意：PermissionError 等非文件不存在的 I/O 错误会向上抛出。
    """
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # JSON 格式损坏时返回空列表，后续写操作会覆盖修复
        return []


def _read_json(file_path: Path) -> List[Dict[str, Any]]:
    """从 JSON 文件读取数据列表（线程安全）。"""
    with _lock:
        return _read_json_unsafe(file_path)


def _write_json_unsafe(file_path: Path, data: List[Dict[str, Any]]) -> None:
    """原子写入：先写临时文件，再原子替换，防止崩溃损坏数据（调用方需持有 _lock）。"""
    tmp_path = file_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
    # os.replace 在 Windows 和 POSIX 上均为原子操作
    os.replace(tmp_path, file_path)


def _write_json(file_path: Path, data: List[Dict[str, Any]]) -> None:
    """将数据列表写入 JSON 文件（线程安全）。"""
    with _lock:
        _write_json_unsafe(file_path, data)


# ============================================================
# 通用 CRUD 操作
# ============================================================

def _create_item(
    file_path: Path,
    item: Dict[str, Any],
    item_type: str,
) -> Dict[str, Any]:
    """通用创建：向 JSON 文件中追加一条记录。"""
    _ensure_storage()
    with _lock:
        data = _read_json_unsafe(file_path)
        data.append(item)
        _write_json_unsafe(file_path, data)
    return item


def _get_item(
    file_path: Path,
    item_id: str,
    item_type: str,
) -> Optional[Dict[str, Any]]:
    """通用查询：按 id 获取单条记录（线程安全）。"""
    _ensure_storage()
    data = _read_json(file_path)
    for item in data:
        if item.get("id") == item_id:
            return item
    return None


def _list_items(
    file_path: Path,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """通用列表：获取全部记录，支持简单字段过滤（线程安全）。"""
    _ensure_storage()
    data = _read_json(file_path)
    if not filters:
        return data

    result = []
    for item in data:
        match = True
        for key, value in filters.items():
            if item.get(key) != value:
                match = False
                break
        if match:
            result.append(item)
    return result


def _update_item(
    file_path: Path,
    item_id: str,
    updates: Dict[str, Any],
    item_type: str,
) -> Optional[Dict[str, Any]]:
    """通用更新：按 id 更新记录的部分字段。"""
    _ensure_storage()
    with _lock:
        data = _read_json_unsafe(file_path)
        for item in data:
            if item.get("id") == item_id:
                item.update(updates)
                _write_json_unsafe(file_path, data)
                return item
    return None


def _delete_item(
    file_path: Path,
    item_id: str,
    item_type: str,
) -> bool:
    """通用删除：按 id 删除记录。"""
    _ensure_storage()
    with _lock:
        data = _read_json_unsafe(file_path)
        new_data = [item for item in data if item.get("id") != item_id]
        if len(new_data) == len(data):
            return False
        _write_json_unsafe(file_path, new_data)
        return True


def _exists(file_path: Path, item_id: str) -> bool:
    """检查指定 id 的记录是否存在（线程安全）。"""
    _ensure_storage()
    data = _read_json(file_path)
    return any(item.get("id") == item_id for item in data)


# ============================================================
# 对外暴露的存储函数（按实体划分）
# ============================================================

# --- 用户存储 ---

def save_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """保存新用户记录。"""
    return _create_item(_USERS_FILE, user, "user")


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取用户。"""
    return _get_item(_USERS_FILE, user_id, "user")


def list_users(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """列出所有用户，可按字段过滤。"""
    return _list_items(_USERS_FILE, filters)


def update_user(user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新用户信息。"""
    return _update_item(_USERS_FILE, user_id, updates, "user")


def delete_user(user_id: str) -> bool:
    """删除用户。"""
    return _delete_item(_USERS_FILE, user_id, "user")


def user_exists(user_id: str) -> bool:
    """检查用户是否存在。"""
    return _exists(_USERS_FILE, user_id)


# --- 项目存储 ---

def save_project(project: Dict[str, Any]) -> Dict[str, Any]:
    """保存新项目记录。"""
    return _create_item(_PROJECTS_FILE, project, "project")


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取项目。"""
    return _get_item(_PROJECTS_FILE, project_id, "project")


def list_projects(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """列出所有项目，可按字段过滤（如按 user_id 过滤）。"""
    return _list_items(_PROJECTS_FILE, filters)


def update_project(project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新项目信息。"""
    return _update_item(_PROJECTS_FILE, project_id, updates, "project")


def delete_project(project_id: str) -> bool:
    """删除项目。"""
    return _delete_item(_PROJECTS_FILE, project_id, "project")


def project_exists(project_id: str) -> bool:
    """检查项目是否存在。"""
    return _exists(_PROJECTS_FILE, project_id)


def delete_projects_by_user(user_id: str) -> int:
    """删除某个用户的所有项目，返回删除数量。"""
    _ensure_storage()
    with _lock:
        data = _read_json_unsafe(_PROJECTS_FILE)
        new_data = [p for p in data if p.get("user_id") != user_id]
        deleted_count = len(data) - len(new_data)
        if deleted_count > 0:
            _write_json_unsafe(_PROJECTS_FILE, new_data)
        return deleted_count
