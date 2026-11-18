from dataclasses import dataclass, field
from datetime import date, time
from typing import Literal

# 整趟行程的结果状态：
#   ok      —— 每一天都排到了至少一个景点
#   partial —— 部分日期没有可安排的景点
#   empty   —— 所有日期都没有可安排的景点（方案无解）
TripStatus = Literal["ok", "partial", "empty"]
WalkConstraint = Literal["satisfied", "violated", "unknown", "not_set"]


@dataclass(frozen=True)
class PlanningWeather:
    """规划器使用的某日天气；只表示“已知”的预报。

    未知天气不构造本对象，由调用方传 ``None``，评分按中性处理。
    """

    forecast_date: date
    condition: str
    temperature_min: float | None
    temperature_max: float | None
    precipitation: float | None
    risk_level: str
    source: str
    status: str = "known"

    @property
    def suitable(self) -> bool:
        # 只有低风险天气才视为适合户外；中高风险按不适宜处理。
        return self.risk_level == "low"


@dataclass(frozen=True)
class TransitSegment:
    """公共交通的一段：步行接驳、公交或地铁。

    站名、线路名来自高德；没有可靠数据时留空，不猜测。
    """

    mode: str
    line_name: str | None = None
    line_type: str | None = None
    departure_stop: str | None = None
    arrival_stop: str | None = None
    departure_location: tuple[float, float] | None = None
    arrival_location: tuple[float, float] | None = None
    origin_location: tuple[float, float] | None = None
    destination_location: tuple[float, float] | None = None
    via_stops: int | None = None
    distance_m: int | None = None
    duration_s: int | None = None
    bike_distance_m: int | None = None
    bike_duration_s: int | None = None


@dataclass(frozen=True)
class TransitAlternative:
    """高德一次公交查询返回的某一个完整方案。"""

    distance_m: int | None
    duration_s: int | None
    walking_distance_m: int | None
    cost_amount: float | None
    segments: tuple[TransitSegment, ...] = ()


@dataclass(frozen=True)
class MealBlock:
    """一天中固定预留的用餐时间块。"""

    meal_type: str
    start_time: time
    end_time: time
    duration_minutes: int


@dataclass(frozen=True)
class PlannedLeg:
    """相邻两个景点之间的一段真实路线。

    ``status="failed"`` 时距离/耗时为 ``None``；若为了继续排程使用了保守
    回退耗时，必须同时给出 ``fallback_duration_s`` 和 ``is_estimate=True``。
    """

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
    transit_segments: tuple[TransitSegment, ...] = ()
    walk_duration_s: int | None = None
    bike_duration_s: int | None = None
    bike_cost_amount: float | None = None


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
    # 兴趣权重 0–1；接口层把 0–100 的滑动条值归一化后传入。
    interests: dict[str, float] = field(default_factory=dict)
    budget_total: float = 0
    daily_start: time = time(8, 0)
    daily_end: time = time(22, 0)
    max_daily_items: int = 4
    avoid_tight_schedule: bool = True
    # 每天最大步行距离（公里）；None 表示不限制。
    # 尚未接入真实路线，该约束尚未执行；接口响应会在 notes 中标注。
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
    # 该条目访问时段的开放时间是**已知**还是未知。
    # 默认 False 是保守取值：没经过 `opening_filter` 判定的构造不应声称知道。
    opening_known: bool = False
    # WGS84 坐标，静态地图按 GCJ-02 转换后标注。
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class DayPlan:
    travel_date: date
    items: list[PlannedItem]
    estimated_cost: float
    legs: list[PlannedLeg] = field(default_factory=list)
    weather: PlanningWeather | None = None
    # 当天可核算的步行距离（公里）；有路线未知时为 None，不能按 0 计。
    walk_km: float | None = None
    walk_constraint: WalkConstraint = "not_set"
    meals: list[MealBlock] = field(default_factory=list)


@dataclass(frozen=True)
class TripPlan:
    """整趟多日行程。

    预算语义：``budget_total`` 是**整趟旅行**的软约束。规划时逐日安排，
    最后把逐日费用累加成 ``total_estimated_cost``；超预算只影响费用评价并
    提示差额，不淘汰方案。``budget_total <= 0`` 表示用户未设置预算，
    此时差额没有意义，统一返回 0。
    """

    start_date: date
    days: list[DayPlan]
    total_estimated_cost: float
    budget_total: float
    status: TripStatus
    # 天气是否**已知**。当前尚未接入天气服务，API 层应传 False，
    # 表示方案没有按天气优化，不能声称已考虑天气。
    weather_known: bool = False

    @property
    def over_budget(self) -> bool:
        return self.budget_total > 0 and self.total_estimated_cost > self.budget_total

    @property
    def budget_difference(self) -> float:
        """预算与全程预计费用的差额；为负表示超出预算。

        未设置预算（``budget_total <= 0``）时返回 0，避免把「没填预算」
        误显示成「超出全部费用」。
        """
        if self.budget_total <= 0:
            return 0.0
        return round(self.budget_total - self.total_estimated_cost, 2)
