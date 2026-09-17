from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("name", "province", name="uq_cities_name_province"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    province: Mapped[str | None] = mapped_column(String(128), index=True)
    country: Mapped[str] = mapped_column(String(64), default="CN", nullable=False)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pois: Mapped[list["POI"]] = relationship(back_populates="city")
    trips_from: Mapped[list["Trip"]] = relationship(
        back_populates="from_city", foreign_keys="Trip.from_city_id"
    )
    trips_to: Mapped[list["Trip"]] = relationship(
        back_populates="to_city", foreign_keys="Trip.to_city_id"
    )
