"""开放时间过滤与排程约束的测试。

覆盖项目计划要求的「排除明确闭馆、未知开放时间不误判为闭馆、
已知开放时间必须满足访问时段」。
"""

from datetime import date, time

from app.planners.generator import generate_day_plan
from app.planners.models import OpeningWindow, PlanningCandidate, PlanningPreferences
from app.planners.opening_filter import (
    filter_closed_on,
    is_closed_on,
    visit_window,
    weekday_key,
)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# 2026-10-12 是星期一；2026-10-18 是星期日。
MONDAY = date(2026, 10, 12)
SUNDAY = date(2026, 10, 18)


def every_day(**kwargs: object) -> tuple[OpeningWindow, ...]:
    """给一周七天都建同一条窗口，避免测试依赖具体星期。"""
    return tuple(OpeningWindow(day, **kwargs) for day in DAYS)  # type: ignore[arg-type]


def make_candidate(index: int, **overrides: object) -> PlanningCandidate:
    base: dict[str, object] = {
        "poi_id": index,
        "name": f"景点 {index}",
        "category": "historical",
        "interest_tags": {"history": 1.0},
        "estimated_cost": 20.0,
        "visit_minutes": 60,
        "confidence": 0.9,
    }
    base.update(overrides)
    return PlanningCandidate(**base)  # type: ignore[arg-type]


# ---------- 星期判定 ----------


def test_weekday_key_matches_calendar() -> None:
    assert weekday_key(MONDAY) == "mon"
    assert weekday_key(SUNDAY) == "sun"


def test_weekday_key_covers_all_seven_days() -> None:
    keys = {weekday_key(date(2026, 10, 12 + offset)) for offset in range(7)}
    assert keys == set(DAYS)


# ---------- 闭馆判定 ----------


def test_closed_on_its_own_weekday() -> None:
    candidate = make_candidate(1, opening_windows=(OpeningWindow("mon", is_closed=True),))
    assert is_closed_on(candidate, MONDAY) is True
    assert filter_closed_on([candidate], MONDAY) == []


def test_missing_opening_hours_never_filters() -> None:
    """本模块最关键的一条：未知开放时间不等于不开门。"""
    candidate = make_candidate(1)
    assert is_closed_on(candidate, MONDAY) is False
    assert filter_closed_on([candidate], MONDAY) == [candidate]


def test_closed_on_another_weekday_does_not_close_today() -> None:
    candidate = make_candidate(
        1, opening_windows=(OpeningWindow("tue", is_closed=True),)
    )
    assert is_closed_on(candidate, MONDAY) is False


def test_filter_keeps_unknown_and_removes_closed() -> None:
    closed = make_candidate(1, opening_windows=(OpeningWindow("mon", is_closed=True),))
    unknown = make_candidate(2)
    open_one = make_candidate(
        3,
        opening_windows=every_day(open_time=time(9, 0), close_time=time(17, 0)),
    )

    kept = filter_closed_on([closed, unknown, open_one], MONDAY)

    assert [candidate.poi_id for candidate in kept] == [2, 3]


# ---------- 访问区间 ----------


def test_visit_window_reports_known_bounds() -> None:
    candidate = make_candidate(
        1, opening_windows=every_day(open_time=time(8, 30), close_time=time(17, 0))
    )
    window = visit_window(candidate, MONDAY)
    assert window.known is True
    assert window.open_time == time(8, 30)
    assert window.close_time == time(17, 0)


def test_visit_window_unknown_when_times_are_missing() -> None:
    """只写了周几、没写时间 —— 语义是「未知」，不是「全天开放」。"""
    candidate = make_candidate(1, opening_windows=every_day())
    assert visit_window(candidate, MONDAY).known is False


def test_visit_window_unknown_without_rows() -> None:
    assert visit_window(make_candidate(1), MONDAY).known is False


# ---------- 排程约束 ----------


def test_closed_candidate_not_scheduled_even_if_top_ranked() -> None:
    closed = make_candidate(
        1,
        interest_tags={"history": 1.0},
        opening_windows=every_day(is_closed=True),
    )
    open_one = make_candidate(
        2,
        interest_tags={"history": 0.5},
        opening_windows=every_day(open_time=time(9, 0), close_time=time(18, 0)),
    )
    preferences = PlanningPreferences(interests={"history": 1.0}, max_daily_items=5)

    plan = generate_day_plan(MONDAY, [closed, open_one], preferences)

    assert [item.poi_id for item in plan.items] == [2]
    assert plan.estimated_cost == 20.0


def test_arrival_before_opening_waits_for_opening() -> None:
    candidate = make_candidate(
        1, opening_windows=every_day(open_time=time(10, 0), close_time=time(18, 0))
    )
    preferences = PlanningPreferences(
        interests={"history": 1.0}, daily_start=time(8, 0), daily_end=time(20, 0)
    )

    plan = generate_day_plan(MONDAY, [candidate], preferences)

    assert plan.items[0].start_time == time(10, 0)
    assert plan.items[0].end_time == time(11, 0)
    assert plan.items[0].opening_known is True


def test_candidate_skipped_when_it_cannot_finish_before_closing() -> None:
    """9:00 开门、11:00 关门，但需要游览 180 分钟 —— 排不进去就不排。"""
    candidate = make_candidate(
        1,
        visit_minutes=180,
        opening_windows=every_day(open_time=time(9, 0), close_time=time(11, 0)),
    )
    preferences = PlanningPreferences(
        interests={"history": 1.0}, daily_start=time(8, 0), daily_end=time(20, 0)
    )

    plan = generate_day_plan(MONDAY, [candidate], preferences)

    assert plan.items == []
    assert plan.estimated_cost == 0.0


def test_unknown_hours_still_scheduled_but_marked_unknown() -> None:
    """未知开放时间要放行，但要如实标注 —— 不冒充成已知。"""
    preferences = PlanningPreferences(
        interests={"history": 1.0}, daily_start=time(8, 0), daily_end=time(20, 0)
    )

    plan = generate_day_plan(MONDAY, [make_candidate(1)], preferences)

    assert plan.items[0].start_time == time(8, 0)
    assert plan.items[0].opening_known is False


def test_partially_known_day_keeps_open_and_unknown_candidates() -> None:
    """闭馆的排除、未知的保留 —— 两类不能混为一谈。"""
    closed = make_candidate(1, opening_windows=every_day(is_closed=True))
    unknown = make_candidate(2)
    preferences = PlanningPreferences(
        interests={"history": 1.0}, daily_start=time(8, 0), daily_end=time(20, 0), max_daily_items=5
    )

    plan = generate_day_plan(MONDAY, [closed, unknown], preferences)

    assert [item.poi_id for item in plan.items] == [2]
    assert plan.items[0].opening_known is False
