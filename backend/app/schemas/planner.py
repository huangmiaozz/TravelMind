"""规划接口的请求 / 响应契约（2026-10-30 冻结）。

约定要点：

- **多日表示**：请求只给 ``start_date`` 和 ``days``，服务端按连续日期展开；
  响应逐日返回 ``days[].travel_date``，不依赖客户端再算日期。
- **兴趣刻度**：请求使用 0–100 的滑动条值，进入规划器前归一化为 0–1。
- **预算语义**：``budget_total`` 是整趟旅行的软约束，0 表示未设置；
  响应给出 ``total_estimated_cost``、``budget_difference`` 和 ``over_budget``，
  超预算方案照常返回。
- **无解表示**：``status`` 为 ``ok`` / ``partial`` / ``empty``，
  不用 HTTP 错误表达「排不出行程」；只有城市不存在或没有 POI 才返回 404。
- **未知项**：``weather_known=False`` 表示天气未知，``notes`` 列出未执行或未接入的
  约束（如真实路线、步行距离），不能把未知描述成已优化。
"""

from datetime import date, time

from pydantic import BaseModel, Field, field_validator, model_validator

from app.planners.models import TripStatus, WalkConstraint
from app.planners.trip import MAX_TRIP_DAYS


class PlannerPlanRequest(BaseModel):
    """多日规划请求。"""

    city: str = Field(min_length=1, description="目的地城市名，例如「北京」")
    start_date: date = Field(description="行程第一天")
    days: int = Field(
        default=1, ge=1, le=MAX_TRIP_DAYS, description="连续旅行天数"
    )
    interests: dict[str, float] = Field(
        default_factory=dict,
        description="兴趣类别权重，0–100；进入规划器时归一化为 0–1",
    )
    budget_total: float = Field(
        default=0, ge=0, description="整趟旅行总预算；0 表示未设置"
    )
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = Field(default=4, ge=1, le=20)
    avoid_tight_schedule: bool = True
    # 每天最大步行距离（公里）；None 表示不限制。
    # 当前尚未接入真实路线，该约束未被执行，响应 notes 会明确说明。
    max_walk_km: float | None = Field(default=None, gt=0)

    @field_validator("interests")
    @classmethod
    def _validate_interests(cls, value: dict[str, float]) -> dict[str, float]:
        for tag, weight in value.items():
            if not 0 <= weight <= 100:
                raise ValueError(
                    f"interest weight for {tag!r} must be between 0 and 100"
                )
        return value

    @model_validator(mode="after")
    def _validate_daily_window(self) -> "PlannerPlanRequest":
        if self.daily_end <= self.daily_start:
            raise ValueError("daily_end must be later than daily_start")
        return self


class PlannedItemResponse(BaseModel):
    poi_id: int
    name: str
    start_time: time
    end_time: time
    estimated_cost: float
    score: float
    # False 表示该景点的开放时间未知，用户需自行核实。
    opening_known: bool
    opening_status: str = "unknown"
    # 当天游览顺序，从 1 开始；静态地图按这个编号标注。
    order: int = 0
    # 门票单价与核验状态；费用汇总按人数乘单价，未知不能按 0 元确认。
    ticket_price: float | None = None
    ticket_child_price: float | None = None
    ticket_status: str = "unknown"
    ticket_source: str | None = None
    ticket_source_url: str | None = None
    ticket_verified_at: str | None = None
    # WGS84 坐标；旧版本 plan_json 可能没有，前端/地图要允许为空。
    latitude: float | None = None
    longitude: float | None = None


class TransitSegmentResponse(BaseModel):
    mode: str
    line_name: str | None = None
    line_type: str | None = None
    departure_stop: str | None = None
    arrival_stop: str | None = None
    via_stops: int | None = None
    distance_m: int | None = None
    duration_s: int | None = None
    bike_distance_m: int | None = None
    bike_duration_s: int | None = None


class RouteLegResponse(BaseModel):
    from_poi_id: int
    to_poi_id: int
    mode: str
    distance_m: int | None
    duration_s: int | None
    walking_distance_m: int | None
    status: str
    source: str | None = None
    is_estimate: bool = False
    fallback_duration_s: int | None = None
    error: str | None = None
    cost_amount: float | None = None
    cost_basis: str | None = None
    reason: str | None = None
    segments: list[TransitSegmentResponse] = Field(default_factory=list)
    walk_duration_s: int | None = None
    bike_duration_s: int | None = None
    bike_cost_amount: float | None = None


class WeatherResponse(BaseModel):
    status: str = "known"
    condition: str | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    precipitation: float | None = None
    risk_level: str | None = None
    source: str | None = None


class MealBlockResponse(BaseModel):
    meal_type: str
    start_time: time
    end_time: time
    duration_minutes: int


class DayPlanResponse(BaseModel):
    travel_date: date
    items: list[PlannedItemResponse] = Field(default_factory=list)
    estimated_cost: float
    legs: list[RouteLegResponse] = Field(default_factory=list)
    weather: WeatherResponse | None = None
    walk_km: float | None = None
    walk_constraint: WalkConstraint = "not_set"
    meals: list[MealBlockResponse] = Field(default_factory=list)


class CostBreakdownResponse(BaseModel):
    tickets_amount: float
    tickets_status: str
    tickets_confirmed_amount: float = 0
    tickets_estimated_amount: float = 0
    tickets_unknown_count: int = 0
    transport_amount: float
    transport_status: str
    meals_amount: float
    meals_status: str
    lodging_amount: float
    lodging_status: str
    total_estimated: float
    budget_total: float
    budget_difference: float
    budget_complete: bool
    unknown_items: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class TripPlanResponse(BaseModel):
    city: str
    start_date: date
    days: list[DayPlanResponse] = Field(default_factory=list)
    total_estimated_cost: float
    budget_total: float
    budget_difference: float = Field(
        description="budget_total - total_estimated_cost；为负表示超出预算，未设置预算时为 0"
    )
    over_budget: bool
    status: TripStatus
    weather_known: bool
    notes: list[str] = Field(default_factory=list)
    source: str
    costs: CostBreakdownResponse | None = None


class PlanOptionResponse(TripPlanResponse):
    plan_id: str
    plan_type: str
    score: float


class PlannerOptionsResponse(BaseModel):
    plans: list[PlanOptionResponse]
    source: str
