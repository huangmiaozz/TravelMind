"""方案版本相关的 schema。

``PlanCreateRequest`` 在现有规划请求之上补齐 v0.3 的人数、节奏、交通偏好和
餐饮/住宿预算字段。当前规划器只使用其中的日期、天数、预算、兴趣、每日时间窗
和每日条目上限；其余字段先进入请求快照并随版本保存，避免以后加字段时旧版本
无法解释。
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.planners.models import TripStatus
from app.schemas.planner import PlannerPlanRequest, TripPlanResponse


class PlanCreateRequest(PlannerPlanRequest):
    adults: int = Field(default=1, ge=1, description="成人数，至少 1 人")
    children: int = Field(default=0, ge=0, description="儿童数")
    pace: int = Field(default=50, ge=0, le=100, description="0 最轻松，100 最充实")
    transport_preference: Literal[
        "auto", "walk", "transit", "drive", "bicycle"
    ] = "auto"
    meal_budget_per_person_day: float | None = Field(default=None, ge=0)
    hotel_budget_per_room_night: float | None = Field(default=None, ge=0)
    rooms: int | None = Field(default=None, ge=1)
    nights: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_nights(self) -> "PlanCreateRequest":
        if self.nights is not None and self.nights > self.days:
            raise ValueError("nights must not exceed days")
        return self

    @property
    def party_size(self) -> int:
        return self.adults + self.children

    @property
    def resolved_rooms(self) -> int:
        """默认每 2 人一间，至少 1 间。"""
        if self.rooms is not None:
            return self.rooms
        return max(1, (self.party_size + 1) // 2)

    @property
    def resolved_nights(self) -> int:
        """默认晚数 = 天数 - 1；1 天行程为 0 晚。"""
        if self.nights is not None:
            return self.nights
        return max(0, self.days - 1)


class PlanVersionSummary(BaseModel):
    plan_id: int
    version_no: int
    status: TripStatus
    start_date: date
    days: int
    adults: int
    children: int
    budget_total: float
    total_estimated_cost: float
    budget_difference: float
    over_budget: bool
    weather_known: bool
    generated_at: datetime


class PlanDetail(TripPlanResponse):
    plan_id: int
    trip_id: int
    version_no: int
    days_count: int
    generated_at: datetime
    request_snapshot: dict = Field(default_factory=dict)
    data_snapshot: dict = Field(default_factory=dict)


class PlanVersionList(BaseModel):
    items: list[PlanVersionSummary]
    total: int


class MealSuggestion(BaseModel):
    name: str
    address: str | None = None
    distance_m: int | None = None
    cost_amount: float | None = None
    rating: float | None = None


class MealSuggestionList(BaseModel):
    items: list[MealSuggestion]
    total: int


class StaySuggestion(BaseModel):
    name: str
    address: str | None = None
    business_area: str | None = None
    stay_type: str | None = None
    distance_m: int | None = None
    avg_attraction_distance_m: int | None = None
    cost_amount: float | None = None
    rating: float | None = None


class StaySuggestionList(BaseModel):
    items: list[StaySuggestion]
    total: int
