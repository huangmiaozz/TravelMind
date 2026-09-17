from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.poi_detail import OpeningHourRead, TicketRead


class POIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city_id: int
    name: str
    poi_type: str
    category: str | None
    description: str | None
    rating: Decimal | None
    avg_cost: Decimal | None
    address: str | None
    source: str
    source_url: str | None
    crawl_time: datetime | None
    confidence: Decimal | None


class POIList(BaseModel):
    items: list[POIRead]
    total: int


class POIDetail(POIRead):
    opening_hours: list[OpeningHourRead] = []
    tickets: list[TicketRead] = []
