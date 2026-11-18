"""多日行程规划测试。

对应 PROJECT_PLAN「实现真正的多日规划；每天累计费用并在整趟行程层面
核算预算差额，保持超预算方案可展示」。
"""

from datetime import date, time

import pytest

from app.planners.models import OpeningWindow, PlanningCandidate, PlanningPreferences
from app.planners.trip import MAX_TRIP_DAYS, plan_trip

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# 2026-10-12 是星期一
MONDAY = date(2026, 10, 12)
TUESDAY = date(2026, 10, 13)


def open_every_day(
    *, open_time: time = time(9, 0), close_time: time = time(18, 0)
) -> tuple[OpeningWindow, ...]:
    return tuple(
        OpeningWindow(day, open_time=open_time, close_time=close_time)
        for day in DAYS
    )


def make_candidate(
    index: int,
    *,
    cost: float = 20.0,
    visit_minutes: int = 60,
    opening_windows: tuple[OpeningWindow, ...] = (),
    weather_sensitive: bool = False,
) -> PlanningCandidate:
    return PlanningCandidate(
        poi_id=index,
        name=f"景点 {index}",
        category="historical",
        interest_tags={"history": 1.0},
        estimated_cost=cost,
        visit_minutes=visit_minutes,
        confidence=0.9,
        weather_sensitive=weather_sensitive,
        opening_windows=opening_windows,
    )


def preferences(**overrides: object) -> PlanningPreferences:
    base: dict[str, object] = {
        "interests": {"history": 1.0},
        "budget_total": 100,
        "daily_start": time(9, 0),
        "daily_end": time(18, 0),
        "max_daily_items": 2,
        "avoid_tight_schedule": False,
    }
    base.update(overrides)
    return PlanningPreferences(**base)  # type: ignore[arg-type]


def test_plans_consecutive_days_and_accumulates_cost() -> None:
    candidates = [
        make_candidate(index, opening_windows=open_every_day())
        for index in range(1, 5)
    ]

    trip = plan_trip(MONDAY, 2, candidates, preferences())

    assert [day.travel_date for day in trip.days] == [MONDAY, TUESDAY]
    assert all(len(day.items) == 2 for day in trip.days)
    assert [day.estimated_cost for day in trip.days] == [40, 40]
    assert trip.total_estimated_cost == 80
    assert trip.budget_difference == 20
    assert trip.over_budget is False
    assert trip.status == "ok"


def test_same_poi_is_not_scheduled_twice_across_days() -> None:
    candidates = [make_candidate(index, visit_minutes=30) for index in range(1, 5)]

    trip = plan_trip(MONDAY, 2, candidates, preferences(max_daily_items=2))

    scheduled = [item.poi_id for day in trip.days for item in day.items]
    assert len(scheduled) == 4
    assert len(set(scheduled)) == 4


def test_each_day_still_respects_daily_time_window() -> None:
    candidates = [make_candidate(index, visit_minutes=90) for index in range(1, 4)]
    prefs = preferences(daily_end=time(12, 0), max_daily_items=5)

    trip = plan_trip(MONDAY, 2, candidates, prefs)

    for day in trip.days:
        assert len(day.items) == 1
        assert day.items[0].end_time <= time(12, 0)


def test_each_day_still_respects_per_day_item_limit() -> None:
    candidates = [make_candidate(index, visit_minutes=30) for index in range(1, 7)]

    trip = plan_trip(MONDAY, 2, candidates, preferences(max_daily_items=2))

    assert [len(day.items) for day in trip.days] == [2, 2]


def test_over_budget_trip_is_still_returned_with_difference() -> None:
    candidates = [make_candidate(index, cost=60.0) for index in range(1, 3)]
    prefs = preferences(budget_total=100, max_daily_items=1)

    trip = plan_trip(MONDAY, 2, candidates, prefs)

    assert len([item for day in trip.days for item in day.items]) == 2
    assert trip.total_estimated_cost == 120
    assert trip.over_budget is True
    assert trip.budget_difference == -20
    assert trip.status == "ok"


def test_partial_trip_when_candidates_run_out() -> None:
    trip = plan_trip(MONDAY, 2, [make_candidate(1)], preferences(max_daily_items=5))

    assert [item.poi_id for item in trip.days[0].items] == [1]
    assert trip.days[1].items == []
    assert trip.status == "partial"


def test_empty_trip_when_every_candidate_is_closed() -> None:
    closed = tuple(OpeningWindow(day, is_closed=True) for day in DAYS)
    candidates = [
        make_candidate(index, opening_windows=closed) for index in range(1, 3)
    ]

    trip = plan_trip(MONDAY, 2, candidates, preferences())

    assert all(day.items == [] for day in trip.days)
    assert trip.status == "empty"
    assert trip.total_estimated_cost == 0
    assert trip.budget_difference == 100
    assert trip.over_budget is False


def test_unset_budget_does_not_produce_fake_difference() -> None:
    trip = plan_trip(MONDAY, 1, [make_candidate(1)], preferences(budget_total=0))

    assert trip.total_estimated_cost == 20
    assert trip.budget_difference == 0
    assert trip.over_budget is False


def test_unknown_weather_is_marked_unknown() -> None:
    trip = plan_trip(
        MONDAY, 1, [make_candidate(1, weather_sensitive=True)], preferences()
    )
    known = plan_trip(
        MONDAY,
        1,
        [make_candidate(1, weather_sensitive=True)],
        preferences(),
        weather_suitable=True,
    )

    assert trip.weather_known is False
    assert known.weather_known is True


@pytest.mark.parametrize("days", [0, -1, MAX_TRIP_DAYS + 1])
def test_rejects_out_of_range_days(days: int) -> None:
    with pytest.raises(ValueError):
        plan_trip(MONDAY, days, [], preferences())
