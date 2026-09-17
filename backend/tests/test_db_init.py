import pytest

from app.db import init_db


def test_sqlite_initialization_requires_postgis(monkeypatch) -> None:
    monkeypatch.setattr(init_db.engine.dialect, "name", "sqlite")

    with pytest.raises(RuntimeError, match="PostgreSQL with PostGIS"):
        init_db.init_db()
