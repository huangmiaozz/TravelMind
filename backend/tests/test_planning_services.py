from app.services.amap import RouteLeg
from app.services.planning_services import CachedAmapProvider


class CountingClient:
    def __init__(self) -> None:
        self.calls = 0

    def route(self, *args, **kwargs) -> RouteLeg:
        self.calls += 1
        return RouteLeg(
            mode=kwargs.get("mode", "walk"),
            distance_m=1000,
            duration_s=700,
            walking_distance_m=1000,
            cost_amount=0.0,
            cost_basis="per_person",
            status="ok",
            source="amap_web_service",
        )

    def close(self) -> None:
        return None


def test_cache_mode_reuses_route_across_providers() -> None:
    client = CountingClient()
    first = CachedAmapProvider(client, min_interval_s=0, mode="cache")
    origin, destination = (121.123456, 31.123456), (121.223456, 31.223456)

    step_one = first.route(origin, destination, "walk", city="测试市")
    second = CachedAmapProvider(client, min_interval_s=0, mode="cache")
    step_two = second.route(origin, destination, "walk", city="测试市")

    assert step_one.distance_m == 1000
    assert step_two.distance_m == 1000
    assert client.calls == 1


def test_live_mode_does_not_read_cache() -> None:
    client = CountingClient()
    origin, destination = (122.123456, 32.123456), (122.223456, 32.223456)
    provider = CachedAmapProvider(client, min_interval_s=0, mode="live")

    provider.route(origin, destination, "walk", city="测试市")
    provider.route(origin, destination, "walk", city="测试市")

    assert client.calls == 1
