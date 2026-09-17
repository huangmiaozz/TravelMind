from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TransportPlan(Base):
    __tablename__ = "transport_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id"), index=True)
    from_poi_id: Mapped[int | None] = mapped_column(ForeignKey("pois.id"))
    to_poi_id: Mapped[int | None] = mapped_column(ForeignKey("pois.id"))
    from_city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    to_city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    mode: Mapped[str] = mapped_column(String(32))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    source: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    options: Mapped[list["TransportOption"]] = relationship(
        back_populates="transport_plan", cascade="all, delete-orphan"
    )


class TransportOption(Base):
    __tablename__ = "transport_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    transport_plan_id: Mapped[int] = mapped_column(ForeignKey("transport_plans.id"), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    route_name: Mapped[str | None] = mapped_column(String(255))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transport_plan: Mapped["TransportPlan"] = relationship(back_populates="options")
