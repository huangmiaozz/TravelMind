"""餐厅质量标签与过滤。

高德 POI 里有大量本地小店和景区餐厅；这里用“评分 + 人工品牌清单”
做一层轻量筛选，不把高德权重当成口碑榜。
"""

from __future__ import annotations

import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from app.services.amap import RestaurantSuggestion

_DATA_PATH = Path(__file__).resolve().parent.parent / "db" / "restaurant_brands.json"


@lru_cache(maxsize=1)
def _brands() -> dict[str, dict[str, tuple[str, ...]]]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    return {
        city: {
            kind: tuple(str(name) for name in names)
            for kind, names in groups.items()
        }
        for city, groups in payload.items()
    }


def known_tag(city: str, name: str) -> str | None:
    for kind, names in _brands().get(city, {}).items():
        if any(brand in name for brand in names):
            return kind
    return None


def filter_and_tag(
    restaurants: list[RestaurantSuggestion],
    city: str,
) -> list[RestaurantSuggestion]:
    """给餐厅打标签，并过滤低评分；过滤后为空时回退到原列表。"""
    tagged = [
        replace(item, quality_tag=known_tag(city, item.name))
        for item in restaurants
    ]
    preferred = [
        item
        for item in tagged
        if item.quality_tag is not None
        or (item.rating is not None and item.rating >= 4.0)
    ]
    # 至少保留 3 家，避免高德字段缺失导致区域为空。
    return preferred if len(preferred) >= 3 else tagged
