from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    to_city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    days_count: Mapped[int] = mapped_column(Integer)
    adults_count: Mapped[int] = mapped_column(Integer, default=1)
    children_count: Mapped[int] = mapped_column(Integer, default=0)
    budget_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    trip_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    requirement_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    from_city: Mapped["City"] = relationship(
        back_populates="trips_from", foreign_keys=[from_city_id]
    )
    to_city: Mapped["City"] = relationship(back_populates="trips_to", foreign_keys=[to_city_id])
    days: Mapped[list["TripDay"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class TripDay(Base):
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "day_index", name="uq_trip_days_trip_index"),
        UniqueConstraint("trip_id", "travel_date", name="uq_trip_days_trip_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)
    travel_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="days")
    itinerary_items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="trip_day", cascade="all, delete-orphan"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (UniqueConstraint("trip_day_id", "sequence_no", name="uq_itinerary_day_sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_day_id: Mapped[int] = mapped_column(ForeignKey("trip_days.id"), index=True)
    poi_id: Mapped[int | None] = mapped_column(ForeignKey("pois.id"), index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    item_type: Mapped[str] = mapped_column(String(32))
    sequence_no: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip_day: Mapped["TripDay"] = relationship(back_populates="itinerary_items")
