"""把 v0.2 的跨城 ``trips`` 迁移到 v0.3 的单城市容器，并建立 ``plan_versions``。

课程项目没有引入 Alembic，这里用一个可重复执行的轻量迁移：

- 给 ``trips`` 增加 ``destination_city_id`` / ``destination_city_name`` / ``title``；
- 用旧的 ``to_city_id`` 回填目的地，保留旧列但去掉 NOT NULL，避免新代码插入失败；
- 创建 ``plan_versions`` 表。

不删除任何旧列或旧数据；迁移完成后旧行仍可只读查看。

用法::

    cd backend
    python -m scripts.migrate_v03_trips_plans
"""

from sqlalchemy import inspect, text

from app import models  # noqa: F401  确保所有表注册到 metadata
from app.db.session import engine
from app.models.trip import PlanVersion


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in inspect(conn).get_columns(table)}


def _nullable(conn, table: str, column: str) -> bool:
    for item in inspect(conn).get_columns(table):
        if item["name"] == column:
            return bool(item["nullable"])
    raise KeyError(f"{table}.{column} not found")


def migrate() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("v0.3 migration requires PostgreSQL (PostGIS)")

    with engine.begin() as conn:
        if "trips" not in inspect(conn).get_table_names():
            raise RuntimeError("trips table does not exist; run init_db first")

        columns = _columns(conn, "trips")

        # 天气接口只认 adcode；先补城市表，再快照到 Trip。
        if "amap_adcode" not in _columns(conn, "cities"):
            conn.execute(text("ALTER TABLE cities ADD COLUMN amap_adcode VARCHAR(16)"))
        conn.execute(
            text(
                "UPDATE cities SET amap_adcode = '110000' "
                "WHERE name = '北京' AND province = '北京市' "
                "AND amap_adcode IS NULL"
            )
        )

        for name, ddl in (
            ("destination_city_id", "INTEGER"),
            ("destination_city_name", "VARCHAR(128)"),
            ("destination_city_adcode", "VARCHAR(16)"),
            ("title", "VARCHAR(200)"),
        ):
            if name not in columns:
                conn.execute(text(f"ALTER TABLE trips ADD COLUMN {name} {ddl}"))

        # 旧 Trip 是跨城结构，目的地取 to_city_id；已有新值的行不覆盖。
        conn.execute(
            text(
                """
                UPDATE trips AS t
                SET destination_city_id = t.to_city_id,
                    destination_city_name = c.name,
                    destination_city_adcode = c.amap_adcode,
                    title = COALESCE(t.title, c.name || '旅行')
                FROM cities AS c
                WHERE t.destination_city_id IS NULL
                  AND c.id = t.to_city_id
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE trips AS t
                SET destination_city_adcode = c.amap_adcode
                FROM cities AS c
                WHERE t.destination_city_adcode IS NULL
                  AND c.id = t.destination_city_id
                """
            )
        )

        # 新代码不再写这些旧列；必须允许 NULL，否则 INSERT 会失败。
        for old_column in (
            "from_city_id",
            "to_city_id",
            "start_date",
            "end_date",
            "days_count",
            "adults_count",
            "children_count",
            "budget_total",
            "trip_status",
            "requirement_snapshot",
        ):
            if old_column in columns and not _nullable(conn, "trips", old_column):
                conn.execute(
                    text(
                        f"ALTER TABLE trips ALTER COLUMN {old_column} DROP NOT NULL"
                    )
                )

        missing = conn.execute(
            text(
                "SELECT count(*) FROM trips "
                "WHERE destination_city_id IS NULL "
                "OR destination_city_name IS NULL "
                "OR title IS NULL"
            )
        ).scalar_one()
        if missing == 0:
            for column in ("destination_city_id", "destination_city_name", "title"):
                if _nullable(conn, "trips", column):
                    conn.execute(
                        text(
                            f"ALTER TABLE trips ALTER COLUMN {column} SET NOT NULL"
                        )
                    )

        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_trips_destination_city_id "
                "ON trips (destination_city_id)"
            )
        )

        PlanVersion.__table__.create(bind=conn, checkfirst=True)

    print("v0.3 migration complete: trips updated, plan_versions ready")


if __name__ == "__main__":
    migrate()
