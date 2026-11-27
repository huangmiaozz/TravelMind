"""用餐区域推荐与时间闸门。

原则：
- 人气只参与排序；
- 实际路线时间决定候选是否有资格出现；
- 午餐 120 分钟包含往返，不再额外叠加路线时间。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from app.services.amap import RestaurantSuggestion
from app.services.coordinates import gcj02_to_wgs84, meters_between, wgs84_to_gcj02
from app.services.dining_areas import DiningArea, areas_for_city, find_area
from app.services.hotel_recommendations import gateways_for_poi
from app.services.restaurant_quality import filter_and_tag

# meal_type: (总预算, 最短用餐, 缓冲, 可分配交通)
MEAL_RULES = {
    "lunch": (120, 60, 10, 50),
    "dinner": (90, 45, 10, 35),
}
AREA_WALK_MINUTES = 5


@dataclass(frozen=True)
class AreaCandidate:
    area: DiningArea
    travel_minutes: int


def meal_budget(meal_type: str) -> tuple[int, int, int]:
    total, min_eat, buffer, travel = MEAL_RULES.get(
        meal_type, MEAL_RULES["lunch"]
    )
    return total, travel, min_eat


def _route_minutes(provider, origin: tuple[float, float], destination: tuple[float, float]) -> int | None:
    leg = provider.route(origin, destination, "drive")
    if leg.status != "ok" or leg.duration_s is None:
        return None
    return max(1, math.ceil(leg.duration_s / 60))


def meal_anchor(day: dict, meal_type: str) -> tuple[dict, dict | None]:
    items = day.get("items") or []
    if not items:
        raise ValueError("day has no items")
    meal = next(
        (
            block
            for block in day.get("meals") or []
            if block.get("meal_type") == meal_type
        ),
        None,
    )
    if meal is None:
        raise ValueError("meal block not found")

    anchor = items[0]
    anchor_index = 0
    for index, item in enumerate(items):
        if item.get("start_time", "") <= meal.get("start_time", ""):
            anchor = item
            anchor_index = index
    next_item = items[anchor_index + 1] if anchor_index + 1 < len(items) else None

    # 晚餐通常已经离开最后一个景点；八达岭这类远端景点应先回到城市门户，
    # 再在市区用餐，而不是继续推荐景区附近。
    if meal_type == "dinner":
        gateways = gateways_for_poi(str(anchor.get("name") or ""))
        if gateways:
            gateway = min(
                gateways,
                key=lambda item: item.duration_minutes + item.buffer_minutes,
            )
            lon_wgs, lat_wgs = gcj02_to_wgs84(*gateway.location)
            anchor = {
                "name": f"{gateway.name}（返程门户）",
                "longitude": lon_wgs,
                "latitude": lat_wgs,
                "start_time": anchor.get("start_time", ""),
            }
            next_item = None

    return anchor, next_item


def _point(item: dict) -> tuple[float, float] | None:
    lon = item.get("longitude")
    lat = item.get("latitude")
    if lon is None or lat is None:
        return None
    return wgs84_to_gcj02(float(lon), float(lat))


def area_candidates(
    provider,
    city: str,
    anchor: dict,
    next_item: dict | None,
    meal_type: str,
) -> tuple[list[AreaCandidate], int, int, int]:
    total, travel_budget, min_eat = meal_budget(meal_type)
    anchor_point = _point(anchor)
    next_point = _point(next_item) if next_item else None
    if anchor_point is None:
        return [], total, travel_budget, min_eat

    candidates: list[AreaCandidate] = []
    for area in areas_for_city(city):
        area_point = wgs84_to_gcj02(*area.center)
        to_area = _route_minutes(provider, anchor_point, area_point)
        if to_area is None:
            continue
        from_area = 0
        if next_point is not None:
            from_minutes = _route_minutes(provider, area_point, next_point)
            if from_minutes is None:
                continue
            from_area = from_minutes
        travel = to_area + from_area + AREA_WALK_MINUTES
        if travel <= travel_budget:
            candidates.append(AreaCandidate(area=area, travel_minutes=travel))

    candidates.sort(key=lambda item: (item.travel_minutes, -item.area.popularity))
    return candidates, total, travel_budget, min_eat


def area_restaurants(provider, area: DiningArea, city: str) -> list[RestaurantSuggestion]:
    center = wgs84_to_gcj02(*area.center)
    raw = provider.nearby_restaurants(
        center,
        city,
        radius=area.radius_m,
        limit=20,
        sortrule="weight",
        types="050000",
    )
    result = filter_and_tag(raw, city)
    result.sort(
        key=lambda item: (
            item.quality_tag is None,
            -(item.rating or 0),
            item.distance_m or 10**9,
        )
    )
    return result


def search_area_restaurants(
    provider,
    area: DiningArea,
    city: str,
    query: str,
) -> list[RestaurantSuggestion]:
    """用户主动搜索；结果必须仍落在当前区域内。"""
    raw = provider.search_restaurants(query, city, limit=20)
    result: list[RestaurantSuggestion] = []
    for item in raw:
        if item.location is None:
            # 搜索接口可能不返回坐标；保留结果但距离标未知。
            result.append(item)
            continue
        lon_wgs, lat_wgs = gcj02_to_wgs84(*item.location)
        distance = meters_between(
            area.center[0], area.center[1], lon_wgs, lat_wgs
        )
        if distance > area.radius_m:
            continue
        result.append(replace(item, distance_m=round(distance)))
    result = filter_and_tag(result, city)
    result.sort(
        key=lambda item: (
            item.quality_tag is None,
            -(item.rating or 0),
            item.distance_m or 10**9,
        )
    )
    return result


def nearby_restaurants(
    provider,
    city: str,
    anchor: dict,
    meal_type: str,
) -> list[tuple[RestaurantSuggestion, int]]:
    anchor_point = _point(anchor)
    if anchor_point is None:
        return []
    _, travel_budget, _ = meal_budget(meal_type)
    raw = provider.nearby_restaurants(
        anchor_point,
        city,
        radius=1500,
        limit=20,
        sortrule="distance",
        types="050000",
    )
    raw = filter_and_tag(raw, city)
    result: list[tuple[RestaurantSuggestion, int]] = []
    for restaurant in raw:
        if restaurant.location is None:
            # 搜索接口可能不返回坐标；Mock/缺坐标时保留，时间标 0 表示未知。
            result.append((restaurant, 0))
            continue
        lon_wgs, lat_wgs = gcj02_to_wgs84(*restaurant.location)
        if find_area(city, lon_wgs, lat_wgs) is not None:
            continue
        travel = _route_minutes(provider, anchor_point, restaurant.location)
        if travel is None or travel > travel_budget:
            continue
        result.append((restaurant, travel))
    result.sort(key=lambda pair: (pair[1], -(pair[0].rating or 0)))
    return result[:5]


def search_nearby_restaurants(
    provider,
    city: str,
    anchor: dict,
    meal_type: str,
    query: str,
) -> list[tuple[RestaurantSuggestion, int]]:
    """在“附近其他”里按关键字搜索，仍排除餐饮区域并过时间闸门。"""
    anchor_point = _point(anchor)
    if anchor_point is None:
        return []
    _, travel_budget, _ = meal_budget(meal_type)
    raw = provider.search_restaurants(query, city, limit=20)
    raw = filter_and_tag(raw, city)
    result: list[tuple[RestaurantSuggestion, int]] = []
    for restaurant in raw:
        if restaurant.location is None:
            # 搜索接口可能不返回坐标；Mock/缺坐标时保留，时间标 0 表示未知。
            result.append((restaurant, 0))
            continue
        lon_wgs, lat_wgs = gcj02_to_wgs84(*restaurant.location)
        if find_area(city, lon_wgs, lat_wgs) is not None:
            continue
        travel = _route_minutes(provider, anchor_point, restaurant.location)
        if travel is None or travel > travel_budget:
            continue
        result.append((restaurant, travel))
    result.sort(key=lambda pair: (pair[1], -(pair[0].rating or 0)))
    return result[:5]
