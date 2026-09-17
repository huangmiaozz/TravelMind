from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class HotelOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    valid_date: date
    price: Decimal
    currency: str
    room_type: str | None
    booking_channel: str | None
    source: str
    source_url: str | None
    updated_at: datetime
    confidence: Decimal | None


class HotelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city_id: int
    name: str
    hotel_type: str | None
    address: str | None
    rating: Decimal | None
    source: str
    source_url: str | None
    confidence: Decimal | None
    offers: list[HotelOfferRead] = []


class HotelList(BaseModel):
    items: list[HotelRead]
    total: int
