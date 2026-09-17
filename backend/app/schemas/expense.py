from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ExpenseInput(BaseModel):
    expense_type: Literal["transport", "hotel", "ticket", "food", "city_transport", "other"]
    amount: Decimal = Field(ge=0)
    currency: str = "CNY"


class ExpenseBreakdown(BaseModel):
    transport: Decimal = 0
    hotel: Decimal = 0
    ticket: Decimal = 0
    food: Decimal = 0
    city_transport: Decimal = 0
    other: Decimal = 0
    total: Decimal = 0
