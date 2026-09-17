from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Weather(Base):
    __tablename__ = "weather"
    __table_args__ = (UniqueConstraint("city_id", "weather_date", name="uq_weather_city_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    weather_date: Mapped[date] = mapped_column(Date, index=True)
    temperature_min: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    temperature_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precipitation: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    weather_condition: Mapped[str | None] = mapped_column(String(64))
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    source: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    city: Mapped["City"] = relationship()
