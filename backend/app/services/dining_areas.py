"""城市餐饮区域（课程 Demo 用人工整理的先验数据）。

区域不是高德官方榜单；它用于把“景点附近搜索”升级为“区域级推荐”。
热度是人工先验，只决定排序，不参与时间可行性判断。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.services.coordinates import meters_between

_DATA_PATH = Path(__file__).resolve().parent.parent / "db" / "dining_areas.json"


@dataclass(frozen=True)
class DiningArea:
    id: str
    name: str
    aliases: tuple[str, ...]
    center: tuple[float, float]
    radius_m: int
    popularity: float
    area_type: str = "food_street"
    weather_friendly: bool = False

    def contains(self, lon: float, lat: float) -> bool:
        return (
            meters_between(self.center[0], self.center[1], lon, lat)
            <= self.radius_m
        )


@lru_cache(maxsize=1)
def _raw_areas() -> dict[str, tuple[DiningArea, ...]]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    result: dict[str, tuple[DiningArea, ...]] = {}
    for city, rows in payload.items():
        result[city] = tuple(
            DiningArea(
                id=str(row["id"]),
                name=str(row["name"]),
                aliases=tuple(str(alias) for alias in row.get("aliases", [])),
                center=(float(row["center"][0]), float(row["center"][1])),
                radius_m=int(row["radius_m"]),
                popularity=float(row["popularity"]),
                area_type=str(row.get("type", "food_street")),
                weather_friendly=bool(row.get("weather_friendly", False)),
            )
            for row in rows
        )
    return result


def areas_for_city(city: str) -> tuple[DiningArea, ...]:
    return _raw_areas().get(city, ())


def get_area(city: str, area_id: str) -> DiningArea | None:
    return next(
        (area for area in areas_for_city(city) if area.id == area_id),
        None,
    )


def find_area(city: str, lon: float, lat: float) -> DiningArea | None:
    return next(
        (area for area in areas_for_city(city) if area.contains(lon, lat)),
        None,
    )
