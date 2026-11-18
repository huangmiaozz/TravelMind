"""规划请求 / 响应契约的校验测试。

对应 PROJECT_PLAN「先冻结请求/响应契约与规则」：多日日期表示、
每日时间窗、兴趣刻度与预算语义都必须由 schema 固定下来。
"""

from datetime import date, time

import pytest
from pydantic import ValidationError

from app.planners.trip import MAX_TRIP_DAYS
from app.schemas.planner import DayPlanResponse, PlannerPlanRequest, TripPlanResponse


def make_request(**overrides: object) -> PlannerPlanRequest:
    payload: dict[str, object] = {
        "city": "北京",
        "start_date": date(2026, 10, 12),
    }
    payload.update(overrides)
    return PlannerPlanRequest(**payload)


def test_defaults_to_single_day_without_budget() -> None:
    request = make_request()

    assert request.days == 1
    assert request.budget_total == 0
    assert request.interests == {}
    assert request.daily_start < request.daily_end


def test_accepts_multi_day_request_at_upper_bound() -> None:
    request = make_request(days=MAX_TRIP_DAYS)

    assert request.days == MAX_TRIP_DAYS


@pytest.mark.parametrize("days", [0, -1, MAX_TRIP_DAYS + 1])
def test_rejects_days_out_of_range(days: int) -> None:
    with pytest.raises(ValidationError):
        make_request(days=days)


@pytest.mark.parametrize(
    ("daily_start", "daily_end"),
    [(time(10, 0), time(10, 0)), (time(12, 0), time(9, 0))],
)
def test_rejects_empty_or_reversed_daily_window(
    daily_start: time, daily_end: time
) -> None:
    with pytest.raises(ValidationError):
        make_request(daily_start=daily_start, daily_end=daily_end)


@pytest.mark.parametrize("weight", [-1, 101, 100.5])
def test_rejects_interest_weight_out_of_0_100(weight: float) -> None:
    with pytest.raises(ValidationError):
        make_request(interests={"history": weight})


def test_accepts_interest_weight_bounds() -> None:
    request = make_request(interests={"history": 0, "food": 100})

    assert request.interests == {"history": 0, "food": 100}


def test_rejects_non_positive_max_walk() -> None:
    with pytest.raises(ValidationError):
        make_request(max_walk_km=0)


def test_trip_response_requires_explicit_status_and_weather_flags() -> None:
    response = TripPlanResponse(
        city="北京",
        start_date=date(2026, 10, 12),
        days=[DayPlanResponse(travel_date=date(2026, 10, 12), estimated_cost=0)],
        total_estimated_cost=0,
        budget_total=0,
        budget_difference=0,
        over_budget=False,
        status="empty",
        weather_known=False,
        notes=["天气未知"],
        source="test",
    )

    assert response.status == "empty"
    assert response.weather_known is False
    assert response.days[0].items == []
