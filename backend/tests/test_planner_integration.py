"""规划器接入路线/天气后的行为测试。

全部使用固定响应，不访问高德真实接口。
"""

from datetime import date, time

from app.planners.generator import generate_day_plan
from app.planners.models import (
    PlanningCandidate,
    PlanningPreferences,
    PlanningWeather,
)
from app.planners.trip import plan_trip
from app.services.amap import RouteLeg, WeatherDay
from app.services.planning_services import CachedAmapProvider

DAY = date(2026, 11, 20)


def make_candidate(
    poi_id: int,
    name: str,
    *,
    latitude: float,
    longitude: float,
    weather_sensitive: bool = False,
) -> PlanningCandidate:
    return PlanningCandidate(
        poi_id=poi_id,
        name=name,
        category="historical",
        interest_tags={"history": 1.0},
        estimated_cost=50,
        visit_minutes=60,
        confidence=0.9,
        weather_sensitive=weather_sensitive,
        latitude=latitude,
        longitude=longitude,
    )


def make_weather(risk_level: str = "low") -> PlanningWeather:
    return PlanningWeather(
        forecast_date=DAY,
        condition="晴" if risk_level == "low" else "大雨",
        temperature_min=15,
        temperature_max=22,
        precipitation=0,
        risk_level=risk_level,
        source="amap_web_service",
    )


class FakeRouteProvider:
    def __init__(self, legs: list[RouteLeg]) -> None:
        self._legs = list(legs)
        self.calls: list[tuple] = []

    def route(self, origin, destination, mode="walk", *, city=None, cityd=None):
        self.calls.append((origin, destination, mode, city, cityd))
        if len(self._legs) == 1:
            return self._legs[0]
        return self._legs.pop(0)


def ok_leg(distance_m: int, duration_s: int) -> RouteLeg:
    return RouteLeg(
        mode="walk",
        distance_m=distance_m,
        duration_s=duration_s,
        walking_distance_m=distance_m,
        cost_amount=None,
        cost_basis=None,
        status="ok",
    )


def failed_leg() -> RouteLeg:
    return RouteLeg(
        mode="walk",
        distance_m=None,
        duration_s=None,
        walking_distance_m=None,
        cost_amount=None,
        cost_basis=None,
        status="failed",
        error="timeout",
    )


def base_preferences(**overrides) -> PlanningPreferences:
    values = {
        "daily_start": time(9, 0),
        "daily_end": time(18, 0),
        "max_daily_items": 2,
        "avoid_tight_schedule": False,
        "max_walk_km": 5,
    }
    values.update(overrides)
    return PlanningPreferences(**values)


def test_route_duration_and_walking_are_applied_to_schedule() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.91, longitude=116.41)
    provider = FakeRouteProvider([ok_leg(800, 600)])

    plan = generate_day_plan(
        DAY,
        [a, b],
        base_preferences(),
        weather=make_weather(),
        route_provider=provider,
        city="北京",
    )

    assert [item.name for item in plan.items] == ["A", "B"]
    assert plan.items[0].start_time == time(9, 0)
    assert plan.items[0].end_time == time(10, 0)
    # 10:00 结束 + 10 分钟间隔 + 10 分钟真实步行
    assert plan.items[1].start_time == time(10, 20)
    assert len(plan.legs) == 1
    assert plan.legs[0].distance_m == 800
    assert plan.legs[0].duration_s == 600
    assert plan.walk_km == 0.8
    assert plan.walk_constraint == "satisfied"
    assert plan.weather is not None
    assert plan.weather.condition == "晴"
    assert provider.calls[0][2] == "walk"


def test_auto_mode_uses_transit_for_long_leg() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.98, longitude=116.50)
    provider = FakeRouteProvider(
        [
            ok_leg(12_000, 9_000),
            ok_leg(12_000, 4_000),
            RouteLeg(
                mode="transit",
                distance_m=12_000,
                duration_s=1_800,
                walking_distance_m=400,
                cost_amount=2.0,
                cost_basis="per_person",
                status="ok",
            ),
            ok_leg(12_000, 1_200),
        ]
    )

    plan = generate_day_plan(
        DAY,
        [a, b],
        base_preferences(max_walk_km=5),
        route_provider=provider,
        city="北京",
        transport_preference="auto",
    )

    assert plan.legs[0].mode == "transit"
    assert any(call[2] == "transit" for call in provider.calls)
    assert plan.walk_km == 0.4


def test_route_failure_uses_marked_fallback_and_unknown_walking() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.91, longitude=116.41)
    provider = FakeRouteProvider([failed_leg()])

    plan = generate_day_plan(
        DAY,
        [a, b],
        base_preferences(),
        route_provider=provider,
        city="北京",
    )

    assert len(plan.items) == 2
    # 10:00 + 10 分钟间隔 + 15 分钟保守回退
    assert plan.items[1].start_time == time(10, 25)
    assert plan.legs[0].status == "failed"
    assert plan.legs[0].distance_m is None
    assert plan.legs[0].duration_s is None
    assert plan.legs[0].fallback_duration_s == 900
    assert plan.legs[0].is_estimate is True
    assert plan.walk_km is None
    assert plan.walk_constraint == "unknown"


def test_max_walk_skips_candidate_over_the_limit() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.91, longitude=116.41)
    provider = FakeRouteProvider([ok_leg(800, 600)])

    plan = generate_day_plan(
        DAY,
        [a, b],
        base_preferences(max_walk_km=0.5),
        route_provider=provider,
        city="北京",
        transport_preference="walk",
    )

    assert [item.name for item in plan.items] == ["A"]
    assert plan.walk_constraint == "satisfied"


def test_failed_route_keeps_walk_km_unknown_without_limit() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.91, longitude=116.41)

    plan = generate_day_plan(
        DAY,
        [a, b],
        base_preferences(max_walk_km=None),
        route_provider=FakeRouteProvider([failed_leg()]),
        city="北京",
    )

    assert plan.walk_km is None
    assert plan.walk_constraint == "not_set"


def test_bad_weather_demotes_outdoor_candidate() -> None:
    outdoor = make_candidate(
        1, "户外", latitude=39.90, longitude=116.40, weather_sensitive=True
    )
    indoor = make_candidate(2, "室内", latitude=39.91, longitude=116.41)

    plan = generate_day_plan(
        DAY,
        [outdoor, indoor],
        base_preferences(max_daily_items=1),
        weather=make_weather(risk_level="high"),
    )

    assert [item.name for item in plan.items] == ["室内"]


def test_trip_marks_partial_weather_unknown() -> None:
    a = make_candidate(1, "A", latitude=39.90, longitude=116.40)
    b = make_candidate(2, "B", latitude=39.91, longitude=116.41)

    plan = plan_trip(
        DAY,
        2,
        [a, b],
        base_preferences(max_daily_items=1, max_walk_km=None),
        weather_by_date={DAY: make_weather()},
    )

    assert plan.weather_known is False
    assert plan.days[0].weather is not None
    assert plan.days[1].weather is None


class FakeAmapClient:
    def __init__(self) -> None:
        self.route_calls = 0
        self.weather_calls = 0
        self.closed = False

    def route(self, origin, destination, mode="walk", *, city=None, cityd=None):
        self.route_calls += 1
        return ok_leg(500, 300)

    def weather(self, city_adcode: str):
        self.weather_calls += 1
        return [
            WeatherDay(
                forecast_date=DAY,
                condition="多云",
                temperature_min=14,
                temperature_max=20,
                precipitation=0,
                risk_level="low",
            )
        ]

    def close(self) -> None:
        self.closed = True


def test_cached_provider_reuses_route_and_weather_results() -> None:
    client = FakeAmapClient()
    provider = CachedAmapProvider(client, min_interval_s=0)

    first = provider.route((116.40, 39.90), (116.41, 39.91))
    second = provider.route((116.40, 39.90), (116.41, 39.91))
    weather_first = provider.weather_by_date("110000", [DAY])
    weather_second = provider.weather_by_date("110000", [DAY])

    assert first is second
    assert weather_first is not None
    assert weather_second == weather_first
    assert client.route_calls == 1
    assert client.weather_calls == 1

    provider.close()
    assert client.closed is True


def test_cached_provider_throttles_distinct_calls() -> None:
    client = FakeAmapClient()
    sleeps: list[float] = []
    provider = CachedAmapProvider(
        client, min_interval_s=2.0, sleeper=sleeps.append
    )

    provider.route((116.40, 39.90), (116.41, 39.91))
    provider.route((116.42, 39.92), (116.43, 39.93))

    assert client.route_calls == 2
    assert len(sleeps) == 1
    assert sleeps[0] > 0
