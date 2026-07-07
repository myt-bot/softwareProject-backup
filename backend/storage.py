"""MySQL 数据库存储层（SQLAlchemy 实现）。

原本地 JSON 文件存储已迁移至 MySQL，对外接口（函数名、参数、返回值）与
JSON 版本完全一致，auth.py / projects.py 等上层业务无需任何改动。

连接配置：
- 优先读取环境变量 DATABASE_URL，例如：
  mysql+pymysql://user:pass@host:3306/visual_dl?charset=utf8mb4
- 未设置时使用开发环境默认值（本地 MySQL，生产部署必须通过环境变量覆盖）。

约束下沉（原先由业务层"先查后写"保证，现由数据库原子兜底）：
- users.email 唯一（邮箱是用户核心标识）
- projects (user_id, name) 唯一（同一用户下项目名不重复）
- projects.user_id 外键关联 users.id，删除用户级联删除其项目

时间字段约定：业务层传入/取回的 created_at、updated_at 均为 ISO 8601 字符串，
数据库内部存 DATETIME(6)（UTC）；本层负责两种表示之间的转换。

测试隔离：调用 configure_database(url) 可将存储切换到独立数据库
（如临时 SQLite 文件），用后 dispose_database() 释放。

历史数据迁移：见 backend/migrate_json_to_mysql.py。
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    select,
)
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from backend.env import load_dotenv_if_present

load_dotenv_if_present()


# ============================================================
# 连接配置
# ============================================================

# 开发环境默认连接串；生产环境必须通过环境变量 DATABASE_URL 覆盖
DEFAULT_DATABASE_URL = (
    "mysql+pymysql://root:devroot@127.0.0.1:3306/visual_dl?charset=utf8mb4"
)

# MySQL 用 DATETIME(6) 保留微秒，保证 ISO 字符串往返不丢精度
_TIMESTAMP = DateTime().with_variant(MYSQL_DATETIME(fsp=6), "mysql")


# ============================================================
# 表结构定义
# ============================================================

_metadata = MetaData()

_users_table = Table(
    "users",
    _metadata,
    Column("id", String(20), primary_key=True),
    Column("username", String(20), nullable=False),
    Column("email", String(255), nullable=False),
    # 可空：兼容迁移前未设置密码的旧用户（登录逻辑视为无法登录）
    Column("password_hash", String(255), nullable=True),
    Column("created_at", _TIMESTAMP, nullable=True),
    Column("updated_at", _TIMESTAMP, nullable=True),
    UniqueConstraint("email", name="uk_users_email"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)

_projects_table = Table(
    "projects",
    _metadata,
    Column("id", String(20), primary_key=True),
    Column(
        "user_id",
        String(20),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(100), nullable=False),
    Column("description", String(500), nullable=True),
    Column("model_graph", JSON, nullable=False),
    Column("created_at", _TIMESTAMP, nullable=True),
    Column("updated_at", _TIMESTAMP, nullable=True),
    UniqueConstraint("user_id", "name", name="uk_projects_user_name"),
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_bin",
)

# 唯一键冲突 / 外键违反时给上层的中文提示（作为业务层预检查之外的并发兜底）
_INTEGRITY_MESSAGES = {
    "user": "保存用户失败：邮箱已被注册或用户 ID 冲突",
    "project": "保存项目失败：同名项目已存在、项目 ID 冲突或所属用户不存在",
}


# ============================================================
# 引擎管理
# ============================================================

_engine: Optional[Engine] = None


def _make_engine(url: str) -> Engine:
    """按连接串创建引擎；SQLite（测试用）与 MySQL 分别调优。"""
    if url.startswith("sqlite"):
        kwargs: Dict[str, Any] = {
            "connect_args": {"check_same_thread": False, "timeout": 30},
        }
        # 内存库必须共享单一连接，否则每个连接各是一个空库
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        # SQLite 默认不启用外键约束，逐连接打开以对齐 MySQL 行为
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    # MySQL：pre_ping 剔除超时死连接，recycle 规避 wait_timeout
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def configure_database(url: Optional[str] = None) -> Engine:
    """初始化（或重建）数据库引擎并确保表存在。

    参数：
        url：数据库连接串；为 None 时读环境变量 DATABASE_URL，
             仍未设置则使用开发默认值。测试传入独立的 SQLite URL 实现数据隔离。

    返回：
        SQLAlchemy Engine。
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
    resolved = url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = _make_engine(resolved)
    _metadata.create_all(engine)
    _engine = engine
    return engine


def dispose_database() -> None:
    """释放当前引擎；下次访问存储时会按环境变量重新初始化。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def _get_engine() -> Engine:
    """获取当前引擎，未初始化时惰性创建。"""
    global _engine
    if _engine is None:
        configure_database()
    return _engine


# ============================================================
# ISO 字符串 <-> datetime 转换（数据库存 UTC naive datetime）
# ============================================================

def _iso_to_dt(value: Any) -> Optional[datetime]:
    """ISO 字符串转 UTC naive datetime；已是 datetime 或 None 时原样处理。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _dt_to_iso(value: Optional[datetime]) -> Optional[str]:
    """数据库取出的 naive datetime 视为 UTC，转回 ISO 字符串。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _to_db_values(table: Table, item: Dict[str, Any]) -> Dict[str, Any]:
    """业务字典转数据库列值：过滤未建模字段、转换时间字段。"""
    values = {}
    for key, value in item.items():
        if key not in table.c:
            continue
        if key in ("created_at", "updated_at"):
            values[key] = _iso_to_dt(value)
        else:
            values[key] = value
    return values


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """数据库行转业务字典，时间字段还原为 ISO 字符串。"""
    item = dict(row._mapping)
    for key in ("created_at", "updated_at"):
        if key in item:
            item[key] = _dt_to_iso(item[key])
    return item


# ============================================================
# 通用 CRUD 操作
# ============================================================

def _create_item(
    table: Table,
    item: Dict[str, Any],
    item_type: str,
) -> Dict[str, Any]:
    """通用创建：插入一条记录，唯一键/外键冲突转为 ValueError。"""
    engine = _get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(table.insert().values(**_to_db_values(table, item)))
    except IntegrityError as exc:
        raise ValueError(_INTEGRITY_MESSAGES[item_type]) from exc
    return item


def _get_item(table: Table, item_id: str) -> Optional[Dict[str, Any]]:
    """通用查询：按 id 获取单条记录。"""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(select(table).where(table.c.id == item_id)).first()
    return _row_to_dict(row) if row is not None else None


def _list_items(
    table: Table,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """通用列表：获取全部记录，支持简单字段等值过滤，按创建时间排序。"""
    stmt = select(table)
    if filters:
        for key, value in filters.items():
            if key not in table.c:
                # 过滤字段不存在时无匹配，与 JSON 版本行为一致
                return []
            stmt = stmt.where(table.c[key] == value)
    stmt = stmt.order_by(table.c.created_at, table.c.id)

    engine = _get_engine()
    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    return [_row_to_dict(row) for row in rows]


def _update_item(
    table: Table,
    item_id: str,
    updates: Dict[str, Any],
    item_type: str,
) -> Optional[Dict[str, Any]]:
    """通用更新：按 id 更新部分字段，记录不存在返回 None。"""
    values = _to_db_values(table, updates)
    if not values:
        return _get_item(table, item_id)

    engine = _get_engine()
    try:
        with engine.begin() as conn:
            result = conn.execute(
                table.update().where(table.c.id == item_id).values(**values)
            )
            if result.rowcount == 0:
                return None
    except IntegrityError as exc:
        raise ValueError(_INTEGRITY_MESSAGES[item_type]) from exc
    return _get_item(table, item_id)


def _delete_item(table: Table, item_id: str) -> bool:
    """通用删除：按 id 删除记录，返回是否删除成功。"""
    engine = _get_engine()
    with engine.begin() as conn:
        result = conn.execute(table.delete().where(table.c.id == item_id))
    return result.rowcount > 0


def _exists(table: Table, item_id: str) -> bool:
    """检查指定 id 的记录是否存在。"""
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            select(table.c.id).where(table.c.id == item_id)
        ).first()
    return row is not None


# ============================================================
# 对外暴露的存储函数（按实体划分，签名与 JSON 版本保持一致）
# ============================================================

# --- 用户存储 ---

def save_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """保存新用户记录。"""
    return _create_item(_users_table, user, "user")


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取用户。"""
    return _get_item(_users_table, user_id)


def list_users(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """列出所有用户，可按字段过滤。"""
    return _list_items(_users_table, filters)


def update_user(user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新用户信息。"""
    return _update_item(_users_table, user_id, updates, "user")


def delete_user(user_id: str) -> bool:
    """删除用户。"""
    return _delete_item(_users_table, user_id)


def user_exists(user_id: str) -> bool:
    """检查用户是否存在。"""
    return _exists(_users_table, user_id)


# --- 项目存储 ---

def save_project(project: Dict[str, Any]) -> Dict[str, Any]:
    """保存新项目记录。"""
    return _create_item(_projects_table, project, "project")


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取项目。"""
    return _get_item(_projects_table, project_id)


def list_projects(filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """列出所有项目，可按字段过滤（如按 user_id 过滤）。"""
    return _list_items(_projects_table, filters)


def update_project(project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新项目信息。"""
    return _update_item(_projects_table, project_id, updates, "project")


def delete_project(project_id: str) -> bool:
    """删除项目。"""
    return _delete_item(_projects_table, project_id)


def project_exists(project_id: str) -> bool:
    """检查项目是否存在。"""
    return _exists(_projects_table, project_id)


def delete_projects_by_user(user_id: str) -> int:
    """删除某个用户的所有项目，返回删除数量。"""
    engine = _get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            _projects_table.delete().where(_projects_table.c.user_id == user_id)
        )
    return result.rowcount
