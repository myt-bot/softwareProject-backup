"""项目管理模块。

提供深度学习项目的创建、查询、更新、删除等操作。
项目关联用户，包含模型图结构、项目名称和描述。
当前使用本地 JSON 文件存储，后续可替换为数据库。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .storage import (
    delete_project as _storage_delete_project,
    get_project as _storage_get_project,
    list_projects as _storage_list_projects,
    project_exists,
    save_project as _storage_save_project,
    update_project as _storage_update_project,
)
from .auth import user_exists


# ============================================================
# 常量
# ============================================================

PROJECT_NAME_MAX_LENGTH = 100
PROJECT_DESC_MAX_LENGTH = 500


# ============================================================
# 数据校验
# ============================================================

def _validate_project_name(name: str) -> Optional[str]:
    """校验项目名称。"""
    if not name or not isinstance(name, str):
        return "项目名称不能为空"
    name = name.strip()
    if not name:
        return "项目名称不能为空"
    if len(name) > PROJECT_NAME_MAX_LENGTH:
        return f"项目名称不能超过 {PROJECT_NAME_MAX_LENGTH} 个字符"
    return None


def _validate_project_description(description: Optional[str]) -> Optional[str]:
    """校验项目描述。"""
    if description is None:
        return None
    if not isinstance(description, str):
        return "项目描述必须是字符串"
    if len(description) > PROJECT_DESC_MAX_LENGTH:
        return f"项目描述不能超过 {PROJECT_DESC_MAX_LENGTH} 个字符"
    return None


def _validate_model_graph(model_graph: Dict[str, Any]) -> Optional[str]:
    """校验模型图基本结构。"""
    if model_graph is None:
        return "model_graph 不能为 None"

    if not isinstance(model_graph, dict):
        return "model_graph 必须是字典"

    layers = model_graph.get("layers")
    if layers is None:
        return "model_graph 必须包含 layers 字段"
    if not isinstance(layers, list):
        return "model_graph.layers 必须是列表"

    connections = model_graph.get("connections")
    if connections is not None and not isinstance(connections, list):
        return "model_graph.connections 必须是列表或为空"

    return None


def _generate_project_id() -> str:
    """生成项目唯一标识。"""
    return f"proj_{uuid4().hex[:12]}"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.utcnow().isoformat()


# ============================================================
# 业务逻辑
# ============================================================

def create_project(
    user_id: str,
    name: str,
    model_graph: Dict[str, Any],
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """创建新项目（保存模型）。

    参数：
        user_id：所属用户 id。
        name：项目名称。
        model_graph：模型图结构字典，包含 layers 和 connections。
        description：项目描述（可选）。

    返回：
        创建成功的项目字典。

    异常：
        ValueError：参数不合法或用户不存在。
    """
    # 校验用户
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")
    if not user_exists(user_id):
        raise ValueError(f"用户 '{user_id}' 不存在")

    # 校验项目名称
    name_error = _validate_project_name(name)
    if name_error:
        raise ValueError(f"项目名称不合法: {name_error}")

    # 校验描述
    desc_error = _validate_project_description(description)
    if desc_error:
        raise ValueError(f"项目描述不合法: {desc_error}")

    # 校验模型图
    graph_error = _validate_model_graph(model_graph)
    if graph_error:
        raise ValueError(f"模型图不合法: {graph_error}")

    # 检查同名项目
    existing = _storage_list_projects({"user_id": user_id, "name": name.strip()})
    if existing:
        raise ValueError(f"用户 '{user_id}' 下已存在同名项目 '{name}'")

    now = _now_iso()
    project = {
        "id": _generate_project_id(),
        "user_id": user_id,
        "name": name.strip(),
        "description": description.strip() if description else "",
        "model_graph": model_graph,
        "created_at": now,
        "updated_at": now,
    }
    return _storage_save_project(project)


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取项目详情。

    参数：
        project_id：项目唯一标识。

    返回：
        项目字典；不存在时返回 None。

    异常：
        ValueError：project_id 为空。
    """
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id 不能为空")
    return _storage_get_project(project_id)


def list_projects(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出项目，可按用户过滤。

    参数：
        user_id：可选，按所属用户过滤。

    返回：
        项目字典列表。
    """
    filters = {}
    if user_id:
        if not isinstance(user_id, str):
            raise ValueError("user_id 必须是字符串")
        filters["user_id"] = user_id
    return _storage_list_projects(filters)


def update_project(
    project_id: str,
    name: Optional[str] = None,
    model_graph: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """更新项目信息。

    参数：
        project_id：项目唯一标识。
        name：新的项目名称（可选）。
        model_graph：新的模型图结构（可选）。
        description：新的项目描述（可选）。

    返回：
        更新后的项目字典。

    异常：
        ValueError：项目不存在或参数不合法。
    """
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id 不能为空")

    project = _storage_get_project(project_id)
    if project is None:
        raise ValueError(f"项目 '{project_id}' 不存在")

    if name is None and model_graph is None and description is None:
        raise ValueError("至少需要提供一个要更新的字段")

    updates = {}

    if name is not None:
        name_error = _validate_project_name(name)
        if name_error:
            raise ValueError(f"项目名称不合法: {name_error}")
        name = name.strip()
        # 检查同用户下同名冲突
        existing = _storage_list_projects({"user_id": project["user_id"], "name": name})
        if existing and existing[0]["id"] != project_id:
            raise ValueError(f"项目名称 '{name}' 已被使用")
        updates["name"] = name

    if description is not None:
        desc_error = _validate_project_description(description)
        if desc_error:
            raise ValueError(f"项目描述不合法: {desc_error}")
        updates["description"] = description.strip() if description else ""

    if model_graph is not None:
        graph_error = _validate_model_graph(model_graph)
        if graph_error:
            raise ValueError(f"模型图不合法: {graph_error}")
        updates["model_graph"] = model_graph

    updates["updated_at"] = _now_iso()

    result = _storage_update_project(project_id, updates)
    if result is None:
        raise RuntimeError(f"更新项目 '{project_id}' 失败")
    return result


def delete_project(project_id: str) -> bool:
    """删除项目。

    参数：
        project_id：项目唯一标识。

    返回：
        删除成功返回 True。

    异常：
        ValueError：project_id 为空或项目不存在。
    """
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id 不能为空")

    if not project_exists(project_id):
        raise ValueError(f"项目 '{project_id}' 不存在")

    return _storage_delete_project(project_id)


def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    """获取指定用户的所有项目。

    参数：
        user_id：用户唯一标识。

    返回：
        项目字典列表。

    异常：
        ValueError：user_id 为空或用户不存在。
    """
    if not user_id or not isinstance(user_id, str):
        raise ValueError("user_id 不能为空")
    if not user_exists(user_id):
        raise ValueError(f"用户 '{user_id}' 不存在")
    return _storage_list_projects({"user_id": user_id})
