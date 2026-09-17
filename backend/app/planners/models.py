from dataclasses import dataclass, field
from datetime import date, time


@dataclass(frozen=True)
class PlanningPreferences:
    interests: dict[str, float] = field(default_factory=dict)
    budget_total: float = 0
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = 4
    avoid_tight_schedule: bool = True


@dataclass(frozen=True)
class PlanningCandidate:
    poi_id: int
    name: str
    category: str
    interest_tags: dict[str, float]
    estimated_cost: float
    visit_minutes: int
    confidence: float
    weather_sensitive: bool = False


@dataclass(frozen=True)
class CandidateScore:
    candidate: PlanningCandidate
    interest_score: float
    cost_score: float
    confidence_score: float
    weather_score: float
    total_score: float


@dataclass(frozen=True)
class PlannedItem:
    poi_id: int
    name: str
    start_time: time
    end_time: time
    estimated_cost: float
    score: float


@dataclass(frozen=True)
class DayPlan:
    travel_date: date
    items: list[PlannedItem]
    estimated_cost: float
