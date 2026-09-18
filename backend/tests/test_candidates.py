"""数据整合层的单元测试。

覆盖 `app.services.candidates` 的纯装配逻辑 —— 这些函数不碰数据库，
可以直接构造模型实例来测。检索查询本身依赖 PostGIS，留待集成验证。
"""

from datetime import time
from decimal import Decimal

from app.models.poi import POI
from app.models.poi_detail import OpeningHour, Ticket
from app.planners.models import PlanningCandidate, PlanningPreferences
from app.services.candidates import (
    DEFAULT_VISIT_MINUTES,
    build_candidate,
    normalize_tags,
    opening_windows,
    ticket_cost,
)


def make_poi(**overrides) -> POI:
    """构造一个不落库的 POI 实例，用于测试装配逻辑。"""
    defaults: dict = {
        "id": 1,
        "city_id": 1,
        "name": "测试景点",
        "poi_type": "scenic",
        "category": "historical",
        "interest_tags": {"history": 1.0},
        "visit_minutes": 120,
        "confidence": Decimal("0.900"),
        "avg_cost": Decimal("50"),
    }
    defaults.update(overrides)
    return POI(**defaults)


# —— 门票价 ——


def test_ticket_cost_prefers_cheapest_ticket_over_fallback() -> None:
    tickets = [
        Ticket(ticket_type="adult", price=Decimal("60")),
        Ticket(ticket_type="student", price=Decimal("30")),
    ]

    assert ticket_cost(tickets, fallback=Decimal("99")) == 30.0


def test_ticket_cost_falls_back_to_avg_cost_without_tickets() -> None:
    assert ticket_cost([], fallback=Decimal("50")) == 50.0


def test_ticket_cost_is_zero_when_nothing_is_known() -> None:
    assert ticket_cost([], fallback=None) == 0.0


def test_ticket_cost_ignores_tickets_without_price() -> None:
    tickets = [Ticket(ticket_type="unknown", price=None)]

    assert ticket_cost(tickets, fallback=Decimal("12")) == 12.0


# —— 标签归一化 ——


def test_normalize_tags_converts_values_to_float() -> None:
    assert normalize_tags({"history": 1, "nature": Decimal("0.5")}) == {
        "history": 1.0,
        "nature": 0.5,
    }


def test_normalize_tags_skips_unconvertible_entries() -> None:
    assert normalize_tags({"history": 1.0, "broken": "abc"}) == {"history": 1.0}


def test_normalize_tags_handles_empty_input() -> None:
    assert normalize_tags(None) == {}
    assert normalize_tags({}) == {}


# —— 候选装配 ——


def test_build_candidate_carries_coordinates_and_category() -> None:
    candidate = build_candidate(make_poi(), latitude=39.9, longitude=116.4)

    assert candidate.category == "historical"
    assert candidate.latitude == 39.9
    assert candidate.longitude == 116.4


def test_build_candidate_falls_back_to_poi_type_without_category() -> None:
    candidate = build_candidate(
        make_poi(category=None, poi_type="museum"), latitude=0.0, longitude=0.0
    )

    assert candidate.category == "museum"


def test_build_candidate_falls_back_to_default_visit_minutes() -> None:
    candidate = build_candidate(
        make_poi(visit_minutes=None), latitude=0.0, longitude=0.0
    )

    assert candidate.visit_minutes == DEFAULT_VISIT_MINUTES


def test_build_candidate_keeps_confidence_as_float() -> None:
    candidate = build_candidate(
        make_poi(confidence=Decimal("0.100")), latitude=0.0, longitude=0.0
    )

    assert isinstance(candidate.confidence, float)
    assert candidate.confidence == 0.1


def test_build_candidate_defaults_confidence_to_zero() -> None:
    candidate = build_candidate(
        make_poi(confidence=None), latitude=0.0, longitude=0.0
    )

    assert candidate.confidence == 0.0


# —— 开放窗口 ——


def test_opening_windows_maps_rows() -> None:
    hours = [
        OpeningHour(day_of_week="mon", open_time=time(8, 30), close_time=time(17, 0)),
        OpeningHour(day_of_week="tue", is_closed=True),
    ]

    windows = opening_windows(hours)

    assert len(windows) == 2
    assert windows[0].day_of_week == "mon"
    assert windows[0].open_time == time(8, 30)
    assert windows[1].is_closed is True


def test_opening_windows_returns_empty_tuple_without_rows() -> None:
    assert opening_windows([]) == ()


# —— 兼容性回归 ——


def test_candidate_accepts_legacy_positional_arguments() -> None:
    """新增字段必须带默认值，否则既有按位置构造的调用会静默错位。"""
    candidate = PlanningCandidate(1, "景点", "historical", {"history": 1.0}, 60, 120, 0.95)

    assert candidate.weather_sensitive is False
    assert candidate.latitude is None
    assert candidate.longitude is None
    assert candidate.opening_windows == ()


def test_preferences_max_walk_defaults_to_unlimited() -> None:
    assert PlanningPreferences().max_walk_km is None
