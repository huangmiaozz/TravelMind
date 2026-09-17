from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    hotel_type: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    source: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    offers: Mapped[list["HotelOffer"]] = relationship(
        back_populates="hotel", cascade="all, delete-orphan"
    )


class HotelOffer(Base):
    __tablename__ = "hotel_offers"
    __table_args__ = (
        UniqueConstraint("hotel_id", "valid_date", "room_type", name="uq_hotel_offer_date_room"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id"), index=True)
    valid_date: Mapped[date] = mapped_column(Date, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(16), default="CNY", nullable=False)
    room_type: Mapped[str | None] = mapped_column(String(64))
    booking_channel: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    hotel: Mapped["Hotel"] = relationship(back_populates="offers")
