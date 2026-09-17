from datetime import date

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TripCreate(BaseModel):
    user_id: int = Field(gt=0)
    from_city_id: int = Field(gt=0)
    to_city_id: int = Field(gt=0)
    start_date: date
    end_date: date
    days_count: int = Field(gt=0)
    adults_count: int = Field(default=1, ge=1)
    children_count: int = Field(default=0, ge=0)
    budget_total: float = Field(default=0, ge=0)
    requirement_snapshot: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_date_range(self) -> "TripCreate":
        actual_days = (self.end_date - self.start_date).days
        if actual_days <= 0:
            raise ValueError("end_date must be after start_date")
        if self.days_count != actual_days:
            raise ValueError("days_count must equal the date range length")
        return self


class TripRead(TripCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_status: str


class TripUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    days_count: int | None = Field(default=None, gt=0)
    adults_count: int | None = Field(default=None, ge=1)
    children_count: int | None = Field(default=None, ge=0)
    budget_total: float | None = Field(default=None, ge=0)
    trip_status: Literal["draft", "planning", "ready", "completed", "cancelled"] | None = None
    requirement_snapshot: dict | None = None

    @model_validator(mode="after")
    def validate_partial_date_range(self) -> "TripUpdate":
        date_fields = (self.start_date, self.end_date, self.days_count)
        if any(value is not None for value in date_fields) and not all(
            value is not None for value in date_fields
        ):
            raise ValueError("start_date, end_date and days_count must be updated together")
        if self.start_date is not None and self.end_date is not None:
            if self.end_date <= self.start_date:
                raise ValueError("end_date must be after start_date")
            if self.days_count != (self.end_date - self.start_date).days:
                raise ValueError("days_count must equal the date range length")
        return self


class TripList(BaseModel):
    items: list[TripRead]
    total: int
