"""候选 POI 检索与数据整合。

这一层连接数据库与规划器：把散布在 `pois` / `opening_hours` / `tickets`
三张表里的内容装配成规划器可直接消费的 `PlanningCandidate`。

补上的是需求 8.1 核心流程里缺失的两步 ——「候选 POI 检索 → 数据整合」。
在此之前 `/planner/*` 要求调用方自己准备候选列表，意味着前端必须自行拼装
坐标、开放时间和门票，而这些数据在库里本来就有。

本层只负责「取数与整合」，不做筛选、算距离或评分 —— 那些属于规划器的职责。
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.city import City
from app.models.poi import POI
from app.models.poi_detail import OpeningHour, Ticket
from app.planners.models import OpeningWindow, PlanningCandidate

# 缺少 visit_minutes 时的回退游玩时长（分钟）
DEFAULT_VISIT_MINUTES = 90
# 单次检索上限，避免大城市的全量 POI 拖慢规划请求
DEFAULT_CANDIDATE_LIMIT = 200

# 天气敏感的粗略类别映射。高德没有可靠的“室内/户外”字段，这里只按明确的
# 类别/类型关键词判断；命中不了的按不敏感处理，避免凭空猜测。
_WEATHER_SENSITIVE_TOKENS = (
    "park",
    "scenic",
    "nature",
    "outdoor",
    "hiking",
    "beach",
    "garden",
    "公园",
    "风景",
    "景区",
    "户外",
    "海滩",
    "山",
    "湖",
)


class CityNotFoundError(LookupError):
    """目的地城市在库中不存在。"""


def find_city(db: Session, name: str) -> City | None:
    """按城市名精确匹配。

    同名不同省时取 id 最小的一条，保证结果可复现。
    """
    query = select(City).where(City.name == name.strip()).order_by(City.id).limit(1)
    return db.scalar(query)


def resolve_city(db: Session, name: str) -> City:
    """按名称取城市，找不到时抛 `CityNotFoundError`。"""
    city = find_city(db, name)
    if city is None:
        raise CityNotFoundError(f"city not found: {name}")
    return city


def load_candidates(
    db: Session,
    city_id: int,
    *,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[PlanningCandidate]:
    """检索指定城市的 POI 并整合为规划器候选。

    坐标通过 PostGIS 的 ST_X / ST_Y 在库内取出，避免在 Python 侧解析几何；
    开放时间与门票用 selectinload 预加载，避免逐条 POI 触发额外查询。
    """
    query = (
        select(
            POI,
            func.ST_Y(POI.geom).label("latitude"),
            func.ST_X(POI.geom).label("longitude"),
        )
        .where(POI.city_id == city_id)
        .options(selectinload(POI.opening_hours), selectinload(POI.tickets))
        .order_by(POI.id)
        .limit(limit)
    )
    return [
        build_candidate(poi, latitude=float(latitude), longitude=float(longitude))
        for poi, latitude, longitude in db.execute(query).all()
    ]


def candidates_for_city(
    db: Session,
    city_name: str,
    *,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[PlanningCandidate]:
    """按城市名取候选，供接口层直接调用。"""
    city = resolve_city(db, city_name)
    return load_candidates(db, city.id, limit=limit)


def build_candidate(poi: POI, *, latitude: float, longitude: float) -> PlanningCandidate:
    """把一条 POI 记录装配成规划器候选。

    纯函数，不依赖数据库会话，便于单测。
    """
    category = poi.category or poi.poi_type
    ticket = ticket_info(poi.tickets, fallback=poi.avg_cost)
    return PlanningCandidate(
        poi_id=poi.id,
        name=poi.name,
        category=category,
        interest_tags=normalize_tags(poi.interest_tags),
        estimated_cost=ticket.adult_price or 0.0,
        visit_minutes=poi.visit_minutes or DEFAULT_VISIT_MINUTES,
        confidence=float(poi.confidence) if poi.confidence is not None else 0.0,
        weather_sensitive=is_weather_sensitive(category, poi.poi_type),
        opening_status=opening_status(poi.opening_hours),
        ticket_price=ticket.adult_price,
        ticket_child_price=ticket.child_price,
        ticket_status=ticket.status,
        ticket_source=ticket.source,
        ticket_source_url=ticket.source_url,
        ticket_verified_at=ticket.verified_at,
        latitude=latitude,
        longitude=longitude,
        opening_windows=opening_windows(poi.opening_hours),
    )


def is_weather_sensitive(category: str | None, poi_type: str | None) -> bool:
    """按类别/类型关键词判断是否受天气影响；无法判断时返回 False。"""
    text = f"{category or ''} {poi_type or ''}".lower()
    return any(token in text for token in _WEATHER_SENSITIVE_TOKENS)


def normalize_tags(raw: dict | None) -> dict[str, float]:
    """把库中的 JSON 标签统一成 {str: float}，跳过无法转换的条目。

    标签值在库中可能是 int 或 Decimal，统一成 float 便于参与加权评分。
    """
    if not raw:
        return {}
    tags: dict[str, float] = {}
    for key, value in raw.items():
        try:
            tags[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return tags


@dataclass(frozen=True)
class TicketInfo:
    """从 Ticket 行提取的票价和可信度；金额为空表示未知。"""

    adult_price: float | None
    child_price: float | None
    status: str
    source: str | None = None
    source_url: str | None = None
    verified_at: str | None = None


_CHILD_TICKET_TOKENS = ("儿童", "学生", "半价", "优惠", "未成年", "老人")
_OFFICIAL_SOURCE_TOKENS = ("official", "官方", "官网", "gov")


def _is_child_ticket(ticket: Ticket) -> bool:
    text = f"{ticket.ticket_type or ''} {ticket.price_desc or ''}"
    return any(token in text for token in _CHILD_TICKET_TOKENS)


def _ticket_status(ticket: Ticket) -> str:
    explicit = (ticket.status or "").lower()
    if explicit in ("confirmed", "estimated", "unknown"):
        return explicit
    source = (ticket.source or "").lower()
    official = any(token in source for token in _OFFICIAL_SOURCE_TOKENS)
    if official or (
        ticket.confidence is not None and float(ticket.confidence) >= 0.9
    ):
        return "confirmed"
    return "estimated"


def ticket_info(
    tickets: list[Ticket], *, fallback: Decimal | float | None
) -> TicketInfo:
    """选成人/儿童票种并标注 confirmed/estimated。

    没有 Ticket 时用 POI 的 `avg_cost` 作为参考估算；两者都没有则返回
    未知金额，不能在费用汇总里按 0 元确认。
    """
    priced = [ticket for ticket in tickets if ticket.price is not None]
    adult_rows = [ticket for ticket in priced if not _is_child_ticket(ticket)]
    child_rows = [ticket for ticket in priced if _is_child_ticket(ticket)]
    adult = min(adult_rows, key=lambda item: float(item.price), default=None)
    child = min(child_rows, key=lambda item: float(item.price), default=None)

    if adult is None and fallback is not None:
        return TicketInfo(
            adult_price=float(fallback),
            child_price=None,
            status="estimated",
            source="poi_avg_cost",
        )
    if adult is None:
        return TicketInfo(
            adult_price=None,
            child_price=None,
            status="unknown",
        )

    if _ticket_status(adult) != "confirmed":
        verified = None
    elif adult.verified_at is not None:
        verified = adult.verified_at.isoformat()
    elif adult.updated_at is not None:
        verified = adult.updated_at.date().isoformat()
    else:
        verified = None
    status = _ticket_status(adult)
    if child is not None and _ticket_status(child) != "confirmed":
        # 成人已确认、儿童仍是估算时，整项按估算处理，避免把儿童价写成已核。
        status = "estimated"
    return TicketInfo(
        adult_price=float(adult.price),
        child_price=float(child.price) if child is not None else None,
        status=status,
        source=adult.source,
        source_url=adult.source_url,
        verified_at=verified if status == "confirmed" else None,
    )


def ticket_cost(tickets: list[Ticket], *, fallback: Decimal | float | None) -> float:
    """旧口径的参考门票价：取最低票种，没有票种时退回 POI 的参考消费。

    费用汇总使用 `ticket_info` 区分成人/儿童票和核验状态；此函数只为兼容
    既有调用方和测试保留。
    """
    prices = [float(ticket.price) for ticket in tickets if ticket.price is not None]
    if prices:
        return min(prices)
    if fallback is not None:
        return float(fallback)
    return 0.0


def opening_status(hours: list[OpeningHour]) -> str:
    """开放时间可信度：全部来自官方且置信度足够高才算 confirmed。"""
    if not hours:
        return "unknown"
    official = all(
        any(token in (hour.source or "").lower() for token in _OFFICIAL_SOURCE_TOKENS)
        and hour.confidence is not None
        and float(hour.confidence) >= 0.9
        for hour in hours
    )
    return "confirmed" if official else "estimated"


def opening_windows(hours: list[OpeningHour]) -> tuple[OpeningWindow, ...]:
    """把库中的开放时间行转成规划器可判定的窗口元组。"""
    return tuple(
        OpeningWindow(
            day_of_week=hour.day_of_week,
            open_time=hour.open_time,
            close_time=hour.close_time,
            is_closed=hour.is_closed,
        )
        for hour in hours
    )
