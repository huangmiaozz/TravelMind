from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OpeningHourRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: str
    open_time: time | None
    close_time: time | None
    is_closed: bool
    effective_from: date | None
    effective_to: date | None
    source: str
    source_url: str | None
    confidence: Decimal | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_type: str
    price: Decimal
    currency: str
    price_desc: str | None
    effective_from: date | None
    effective_to: date | None
    source: str
    source_url: str | None
    confidence: Decimal | None
