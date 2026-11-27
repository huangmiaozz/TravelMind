"""v0.4 方案选择迁移。

为既有 PostgreSQL 数据库补上 ``plan_versions.selection_json``，用于保存
用户选择的餐厅/住宿；不修改只读的 ``plan_json``。可重复执行。

用法::

    cd backend
    python -m scripts.migrate_v04_plan_selections
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


def migrate() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE plan_versions "
                "ADD COLUMN IF NOT EXISTS selection_json JSONB "
                "NOT NULL DEFAULT '{}'::jsonb"
            )
        )
    print("plan_versions: selection_json ready")


if __name__ == "__main__":
    migrate()
