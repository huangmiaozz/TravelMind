from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WeatherRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city_id: int
    weather_date: date
    temperature_min: Decimal | None
    temperature_max: Decimal | None
    precipitation: Decimal | None
    weather_condition: str | None
    risk_level: Literal["low", "medium", "high"]
    source: str
    source_url: str | None
    updated_at: datetime
    confidence: Decimal | None


class WeatherList(BaseModel):
    items: list[WeatherRead]
    total: int
