from datetime import date, time

from pydantic import BaseModel, Field


class PlannerPlanRequest(BaseModel):
    """按目的地城市生成行程。

    候选 POI 由服务端依据 `city` 从数据库检索（见 `app.services.candidates`），
    客户端不再需要自行拼装坐标、开放时间与门票。
    """

    city: str = Field(min_length=1, description="目的地城市名，例如「北京」")
    travel_date: date
    interests: dict[str, float] = Field(default_factory=dict)
    budget_total: float = Field(default=0, ge=0)
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = Field(default=4, ge=1, le=20)
    avoid_tight_schedule: bool = True
    # 每天最大步行距离（公里）；None 表示不限制
    max_walk_km: float | None = Field(default=None, gt=0)


class PlannedItemResponse(BaseModel):
    poi_id: int
    name: str
    start_time: time
    end_time: time
    estimated_cost: float
    score: float


class DayPlanResponse(BaseModel):
    travel_date: date
    items: list[PlannedItemResponse] = Field(default_factory=list)
    estimated_cost: float
    source: str


class PlanOptionResponse(DayPlanResponse):
    plan_id: str
    plan_type: str
    score: float


class PlannerOptionsResponse(BaseModel):
    plans: list[PlanOptionResponse]
    source: str
