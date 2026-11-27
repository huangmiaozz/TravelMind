"""v0.4 票价核验字段迁移。

为既有 PostgreSQL 数据库补上 Ticket.status / applies_to / verified_at / raw_text。
可重复执行；SQLite 测试库由 SQLAlchemy 自动建表，不需要本脚本。

用法::

    cd backend
    python -m scripts.migrate_v04_ticket_status
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import engine


STATEMENTS = (
    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS applies_to VARCHAR(32)",
    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS verified_at DATE",
    "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS raw_text TEXT",
)


def migrate() -> None:
    with engine.begin() as connection:
        for statement in STATEMENTS:
            connection.execute(text(statement))
    print(f"tickets: applied {len(STATEMENTS)} column checks")


if __name__ == "__main__":
    migrate()
