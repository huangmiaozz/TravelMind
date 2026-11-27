"""高德 Mock 数据源。

用于本地反复调试 UI，不发起任何外部请求。所有返回值都标 ``source="mock"``，
规划结果会明确提示当前是 Mock 数据；不要把这些数值当成真实路线/价格。
"""

from __future__ import annotations

from datetime import date
from dataclasses import replace
from app.planners.models import TransitAlternative, TransitSegment
from app.services.amap import (
    RestaurantSuggestion,
    RouteLeg,
    StaySuggestion,
    WeatherDay,
)
from app.services.coordinates import meters_between

_SPEED_MPS = {"walk": 1.3, "bicycle": 4.2, "transit": 7.0, "drive": 11.0}
_DISTANCE_FACTOR = {"walk": 1.2, "bicycle": 1.25, "transit": 1.35, "drive": 1.3}
_CITY_CENTERS = {"北京": (116.397, 39.909), "福州": (119.296, 26.082)}


class MockAmapProvider:
    def close(self) -> None:
        return None

    def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "walk",
        *,
        city: str | None = None,
        cityd: str | None = None,
    ) -> RouteLeg:
        straight = meters_between(origin[0], origin[1], destination[0], destination[1])
        distance = max(100, int(straight * _DISTANCE_FACTOR.get(mode, 1.2)))
        duration = max(60, int(distance / _SPEED_MPS.get(mode, 1.3)))
        if mode == "transit":
            walk_in = 180
            walk_out = 160
            segments = (
                TransitSegment(mode="walk", distance_m=walk_in, duration_s=160),
                TransitSegment(
                    mode="bus",
                    line_name="演示公交 1 路",
                    line_type="普通公交线路",
                    departure_stop="演示起点站",
                    arrival_stop="演示终点站",
                    via_stops=4,
                    distance_m=max(100, distance - walk_in - walk_out),
                    duration_s=max(60, duration - 320),
                ),
                TransitSegment(mode="walk", distance_m=walk_out, duration_s=140),
            )
            alternative = TransitAlternative(
                distance_m=distance,
                duration_s=duration,
                walking_distance_m=walk_in + walk_out,
                cost_amount=2.0,
                segments=segments,
            )
            return RouteLeg(
                mode="transit",
                distance_m=distance,
                duration_s=duration,
                walking_distance_m=walk_in + walk_out,
                cost_amount=2.0,
                cost_basis="per_person",
                status="ok",
                source="mock",
                is_mock=True,
                segments=segments,
                alternatives=(alternative,),
            )

        cost = 0.0 if mode == "walk" else (2.0 if mode == "bicycle" else None)
        return RouteLeg(
            mode=mode,
            distance_m=distance,
            duration_s=duration,
            walking_distance_m=distance if mode == "walk" else 0,
            cost_amount=cost,
            cost_basis="per_person" if cost is not None else None,
            status="ok",
            source="mock",
            is_mock=True,
        )

    def weather_by_date(
        self, city_adcode: str, dates: list[date]
    ) -> dict[date, WeatherDay]:
        return {
            day: WeatherDay(
                forecast_date=day,
                condition="晴",
                temperature_min=17.0,
                temperature_max=26.0,
                precipitation=0.0,
                risk_level="low",
                source="mock",
            )
            for day in dates
        }

    def nearby_restaurants(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 800,
        limit: int = 5,
        sortrule: str = "distance",
        types: str = "050000",
    ) -> list[RestaurantSuggestion]:
        names = ["演示餐厅 A", "演示餐厅 B", "演示餐厅 C"]
        costs = [45.0, 60.0, 80.0]
        ratings = [4.6, 4.4, 4.2]
        return [
            RestaurantSuggestion(
                name=names[index],
                address="演示地址（Mock 数据）",
                distance_m=120 * (index + 1),
                cost_amount=costs[index],
                rating=ratings[index],
                location=location,
                poi_type="餐饮服务;中餐厅;中餐厅",
                typecode="050100",
            )
            for index in range(min(3, limit))
        ]

    def nearby_hotels(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 3000,
        limit: int = 8,
        sortrule: str = "distance",
    ) -> list[StaySuggestion]:
        names = ["演示酒店 A", "演示酒店 B", "演示酒店 C"]
        costs = [380.0, 450.0, 520.0]
        ratings = [4.6, 4.4, 4.2]
        return [
            StaySuggestion(
                name=names[index],
                address="演示地址（Mock 数据）",
                business_area="演示住宿区",
                stay_type="宾馆酒店;演示数据",
                distance_m=400 * (index + 1),
                cost_amount=costs[index],
                rating=ratings[index],
                location=location,
            )
            for index in range(min(3, limit))
        ]

    def search_hotels(
        self, keywords: str, city: str, *, limit: int = 10
    ) -> list[StaySuggestion]:
        return self.nearby_hotels(
            _CITY_CENTERS.get(city, (0.0, 0.0)), city, limit=limit
        )

    def search_restaurants(
        self, keywords: str, city: str, *, limit: int = 10
    ) -> list[RestaurantSuggestion]:
        items = self.nearby_restaurants(
            _CITY_CENTERS.get(city, (0.0, 0.0)), city, limit=limit
        )
        return [replace(item, location=None) for item in items]
