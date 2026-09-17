from datetime import date, time

from pydantic import BaseModel, Field


class PlannerCandidateInput(BaseModel):
    poi_id: int = Field(gt=0)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    interest_tags: dict[str, float] = Field(default_factory=dict)
    estimated_cost: float = Field(ge=0)
    visit_minutes: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    weather_sensitive: bool = False


class PlannerGenerateRequest(BaseModel):
    travel_date: date
    candidates: list[PlannerCandidateInput] = Field(min_length=1)
    interests: dict[str, float] = Field(default_factory=dict)
    budget_total: float = Field(default=0, ge=0)
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = Field(default=4, ge=1, le=20)
    avoid_tight_schedule: bool = True


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
