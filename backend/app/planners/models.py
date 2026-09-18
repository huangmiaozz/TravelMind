from dataclasses import dataclass, field
from datetime import date, time


@dataclass(frozen=True)
class OpeningWindow:
    """某个 POI 在某一日的开放窗口。

    `is_closed` 为真表示该日不开放，此时 open_time / close_time 无意义。
    仅描述单日窗口；跨日营业或分时段（如午休闭馆）暂未建模。
    """

    day_of_week: str
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False


@dataclass(frozen=True)
class PlanningPreferences:
    interests: dict[str, float] = field(default_factory=dict)
    budget_total: float = 0
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = 4
    avoid_tight_schedule: bool = True
    # 每天最大步行距离（公里）；None 表示不限制。
    # 由数据整合层从用户约束传入，具体校验在第 2 步接入。
    max_walk_km: float | None = None


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
    # —— 以下由数据整合层填充，均带默认值，保证既有位置参数调用不受影响 ——
    # 坐标（WGS84）。为 None 表示库里缺几何信息，此时无法参与距离计算。
    latitude: float | None = None
    longitude: float | None = None
    # 该 POI 的每周开放窗口；为空表示未知（此时不应据此过滤）
    opening_windows: tuple[OpeningWindow, ...] = ()


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
