from app.db.base import Base
from app.db.session import engine
from app import models  # noqa: F401


def init_db() -> None:
    if engine.dialect.name == "sqlite":
        raise RuntimeError(
            "TravelMind spatial models require PostgreSQL with PostGIS; "
            "set DATABASE_URL before running database initialization."
        )
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
