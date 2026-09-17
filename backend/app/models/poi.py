from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class POI(Base):
    __tablename__ = "pois"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    poi_type: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str | None] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    avg_cost: Mapped[float | None] = mapped_column(Numeric(10, 2))
    address: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    city: Mapped["City"] = relationship(back_populates="pois")
    opening_hours: Mapped[list["OpeningHour"]] = relationship(
        back_populates="poi", cascade="all, delete-orphan"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="poi", cascade="all, delete-orphan"
    )
