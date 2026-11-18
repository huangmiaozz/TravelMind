"""交通方式候选与评分的单元测试。"""

from datetime import date

from app.planners.models import (
    PlanningWeather,
    TransitAlternative,
    TransitSegment,
)
from app.planners.transport_selector import (
    TransportOption,
    build_transport_options,
    score_option,
)
from app.services.amap import RouteLeg

DAY = date(2026, 11, 18)
A = (116.40, 39.90)
B = (116.43, 39.92)


def weather(risk: str = "low") -> PlanningWeather:
    return PlanningWeather(
        forecast_date=DAY,
        condition="晴" if risk == "low" else "小雨",
        temperature_min=16,
        temperature_max=24,
        precipitation=0,
        risk_level=risk,
        source="amap_web_service",
    )


def leg(
    mode: str,
    *,
    distance_m: int,
    duration_s: int,
    walking_m: int | None = None,
    cost: float | None = None,
) -> RouteLeg:
    return RouteLeg(
        mode=mode,
        distance_m=distance_m,
        duration_s=duration_s,
        walking_distance_m=walking_m,
        cost_amount=cost,
        cost_basis="per_person" if cost is not None else None,
        status="ok",
    )


class FakeProvider:
    def __init__(self, legs: dict[str, RouteLeg]) -> None:
        self.legs = legs
        self.calls: list[str] = []

    def route(self, origin, destination, mode="walk", *, city=None, cityd=None):
        self.calls.append(mode)
        return self.legs.get(mode, RouteLeg(
            mode=mode,
            distance_m=None,
            duration_s=None,
            walking_distance_m=None,
            cost_amount=None,
            cost_basis=None,
            status="failed",
            error="no route",
        ))


def test_auto_compares_walk_transit_and_taxi_by_cost_and_time() -> None:
    provider = FakeProvider(
        {
            "walk": leg("walk", distance_m=4200, duration_s=2400),
            "transit": leg(
                "transit", distance_m=3800, duration_s=1500, walking_m=300, cost=2
            ),
            "drive": leg("drive", distance_m=3600, duration_s=600),
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="auto",
        weather=weather("medium"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )

    assert options[0].mode == "transit"
    assert {option.mode for option in options} == {"active", "transit", "taxi"}
    assert all(call in {"walk", "transit", "drive", "bicycle"} for call in provider.calls)


def test_bicycle_time_is_still_reported_in_medium_weather() -> None:
    provider = FakeProvider(
        {
            "walk": leg("walk", distance_m=4200, duration_s=3000),
            "transit": leg(
                "transit", distance_m=3800, duration_s=1200, walking_m=200, cost=2
            ),
            "bicycle": leg("bicycle", distance_m=4000, duration_s=900),
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="auto",
        weather=weather("medium"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )
    active = next(option for option in options if option.mode == "active")

    assert "bicycle" in provider.calls
    assert active.bike_duration_s == 900


def test_transit_failure_falls_back_to_taxi() -> None:
    provider = FakeProvider(
        {
            "walk": leg("walk", distance_m=6000, duration_s=4000),
            "drive": leg("drive", distance_m=5500, duration_s=900),
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="auto",
        weather=weather("low"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )

    assert "transit" not in {option.mode for option in options}
    assert "taxi" in {option.mode for option in options}


def test_explicit_walk_still_uses_transit_when_walking_fails() -> None:
    provider = FakeProvider(
        {
            "transit": leg(
                "transit", distance_m=3000, duration_s=1200, walking_m=200, cost=2
            )
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="walk",
        weather=weather("low"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )

    assert any(option.mode == "transit" for option in options)


def test_selector_compares_all_transit_alternatives() -> None:
    slow = TransitAlternative(
        distance_m=5000,
        duration_s=1800,
        walking_distance_m=800,
        cost_amount=2,
        segments=(TransitSegment(mode="bus", line_name="66路"),),
    )
    fast = TransitAlternative(
        distance_m=5200,
        duration_s=600,
        walking_distance_m=100,
        cost_amount=4,
        segments=(TransitSegment(mode="subway", line_name="地铁1号线"),),
    )
    provider = FakeProvider(
        {
            "walk": leg("walk", distance_m=4200, duration_s=3000),
            "transit": RouteLeg(
                mode="transit",
                distance_m=slow.distance_m,
                duration_s=slow.duration_s,
                walking_distance_m=slow.walking_distance_m,
                cost_amount=slow.cost_amount,
                cost_basis="per_person",
                status="ok",
                segments=slow.segments,
                alternatives=(slow, fast),
            ),
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="transit",
        weather=weather("low"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )
    transit_options = [option for option in options if option.mode == "transit"]

    assert len(transit_options) == 2
    assert options[0].segments[0].line_name == "地铁1号线"


def test_active_option_uses_walk_time_and_reports_bike_time() -> None:
    provider = FakeProvider(
        {
            "walk": leg("walk", distance_m=3400, duration_s=1200),
            "bicycle": leg("bicycle", distance_m=3300, duration_s=400),
        }
    )

    options = build_transport_options(
        provider,
        A,
        B,
        preference="auto",
        weather=weather("low"),
        city="福州",
        daily_budget=1000,
        max_walk_m=5000,
    )
    active = next(option for option in options if option.mode == "active")

    assert active.duration_s == 1200
    assert active.walk_duration_s == 1200
    assert active.bike_duration_s == 400
    assert active.bike_cost_amount == 2.0


def test_taxi_cost_is_penalized_against_transit_on_equal_time() -> None:
    transit = TransportOption(
        mode="transit",
        distance_m=3000,
        duration_s=1200,
        walking_distance_m=200,
        cost_amount=2,
        cost_basis="per_person",
        status="ok",
        source="amap_web_service",
        is_estimate=False,
    )
    taxi = TransportOption(
        mode="taxi",
        distance_m=3000,
        duration_s=1200,
        walking_distance_m=0,
        cost_amount=18,
        cost_basis="per_vehicle",
        status="ok",
        source="amap_web_service",
        is_estimate=True,
    )

    kwargs = dict(
        preference="auto",
        weather=weather("low"),
        max_walk_m=5000,
        daily_budget=1000,
    )

    assert score_option(transit, **kwargs) < score_option(taxi, **kwargs)
