"""一次性迁移脚本：把 data/ 下的 JSON 数据导入 MySQL。

运行方式（在项目根目录）：
    python -m backend.migrate_json_to_mysql
    python -m backend.migrate_json_to_mysql --database-url mysql+pymysql://user:pass@host:3306/visual_dl?charset=utf8mb4

行为说明：
- 自动建表（已存在则跳过）。
- 逐条导入用户和项目；先导用户再导项目，满足外键依赖。
- 脏数据处理：重复邮箱/重复 id 的用户跳过并告警；user_id 不存在的孤儿项目
  跳过并告警；缺 password_hash 的旧用户照常导入（该账号无法登录，行为与迁移前一致）。
- 迁移后 JSON 文件保留作备份，不做删除。脚本可重复执行（已导入的记录会因
  主键/唯一键冲突被跳过）。
"""

import argparse
import json
import sys
from pathlib import Path

from backend import storage

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_json(file_path: Path) -> list:
    """读取 JSON 列表文件，不存在或损坏时返回空列表并告警。"""
    if not file_path.exists():
        print(f"[跳过] {file_path} 不存在")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"[告警] {file_path} JSON 解析失败，跳过：{exc}")
        return []
    if not isinstance(data, list):
        print(f"[告警] {file_path} 不是列表结构，跳过")
        return []
    return data


def migrate(database_url: str = None, data_dir: Path = DATA_DIR) -> dict:
    """执行迁移，返回统计信息字典。"""
    storage.configure_database(database_url)

    stats = {"users_ok": 0, "users_skip": 0, "projects_ok": 0, "projects_skip": 0}

    # --- 用户 ---
    for user in _load_json(data_dir / "users.json"):
        user_id = user.get("id", "<无id>")
        if storage.user_exists(user_id):
            print(f"[跳过] 用户 {user_id} 已存在")
            stats["users_skip"] += 1
            continue
        try:
            storage.save_user(user)
            stats["users_ok"] += 1
            print(f"[导入] 用户 {user_id} ({user.get('username')})")
        except ValueError as exc:
            print(f"[告警] 用户 {user_id} 导入失败，跳过：{exc}")
            stats["users_skip"] += 1

    # --- 项目 ---
    for project in _load_json(data_dir / "projects.json"):
        project_id = project.get("id", "<无id>")
        if storage.project_exists(project_id):
            print(f"[跳过] 项目 {project_id} 已存在")
            stats["projects_skip"] += 1
            continue
        if not storage.user_exists(project.get("user_id", "")):
            print(f"[告警] 项目 {project_id} 的所属用户 {project.get('user_id')} 不存在（孤儿项目），跳过")
            stats["projects_skip"] += 1
            continue
        try:
            storage.save_project(project)
            stats["projects_ok"] += 1
            print(f"[导入] 项目 {project_id} ({project.get('name')})")
        except ValueError as exc:
            print(f"[告警] 项目 {project_id} 导入失败，跳过：{exc}")
            stats["projects_skip"] += 1

    print(
        f"\n迁移完成：用户 导入 {stats['users_ok']} / 跳过 {stats['users_skip']}；"
        f"项目 导入 {stats['projects_ok']} / 跳过 {stats['projects_skip']}。"
        f"\n数据库现有用户 {len(storage.list_users())} 个、项目 {len(storage.list_projects())} 个。"
        f"\nJSON 文件保留在 {data_dir} 作为备份。"
    )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移 data/ 下的 JSON 数据到 MySQL")
    parser.add_argument(
        "--database-url",
        default=None,
        help="数据库连接串；缺省时读环境变量 DATABASE_URL 或使用开发默认值",
    )
    args = parser.parse_args()
    migrate(args.database_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
