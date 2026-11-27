"""酒店推荐的通勤模型。

普通景点用“酒店 → 景点”的估算时间；八达岭这类特殊景点用
“酒店 → 门户站 → 景点”的最小值。这里用直线距离估算接驳时间，
门户到景区的固定耗时来自人工维护数据，不伪装成实时路线。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.services.amap import StaySuggestion
from app.services.coordinates import gcj02_to_wgs84, meters_between

_DATA_PATH = Path(__file__).resolve().parent.parent / "db" / "access_gateways.json"
_CITY_SPEED_KMH = 22.0

# 常见连锁/品牌词只用于“无评分时兜底”，不代替真实评分。
_KNOWN_CHAINS = (
    "如家",
    "汉庭",
    "全季",
    "桔子",
    "亚朵",
    "维也纳",
    "锦江",
    "7天",
    "速8",
    "宜必思",
    "希尔顿",
    "万豪",
    "洲际",
    "假日",
    "智选",
    "喜来登",
    "香格里拉",
    "凯悦",
    "威斯汀",
    "丽思卡尔顿",
    "索菲特",
    "诺富特",
    "美居",
    "秋果",
    "ZMAX",
    "M酒店",
    "无印良品",
    "丽枫",
    "白玉兰",
    "锦江之星",
    "城市便捷",
    "格林豪泰",
    "布丁",
    "海友",
    "怡莱",
    "星程",
    "美仑",
    "漫心",
    "欢朋",
    "喆啡",
)

_ECONOMY_BRANDS = (
    "速8",
    "7天",
    "布丁",
    "海友",
    "99优选",
    "格林豪泰",
    "城市便捷",
    "如家",
)
_COMFORT_BRANDS = (
    "全季",
    "桔子",
    "亚朵",
    "维也纳",
    "锦江之星",
    "丽枫",
    "秋果",
    "宜必思",
    "智选",
    "美居",
    "诺富特",
)
_HIGH_BRANDS = (
    "希尔顿",
    "万豪",
    "洲际",
    "凯悦",
    "香格里拉",
    "威斯汀",
    "丽思卡尔顿",
    "索菲特",
    "瑞吉",
    "W酒店",
    "Club Med",
)


def classify_tier(hotel: StaySuggestion) -> str:
    text = f"{hotel.name} {hotel.stay_type or ''}"
    if any(brand.lower() in text.lower() for brand in _HIGH_BRANDS):
        return "高档/精品"
    if "五星" in text or "四星" in text or "豪华" in text:
        return "高档/精品"
    if any(brand.lower() in text.lower() for brand in _COMFORT_BRANDS):
        return "舒适型"
    if any(brand.lower() in text.lower() for brand in _ECONOMY_BRANDS):
        return "经济型"
    if "经济型" in text:
        return "经济型"
    if "三星" in text:
        return "舒适型"
    return "未知"


def is_known_chain(name: str) -> bool:
    return any(chain.lower() in name.lower() for chain in _KNOWN_CHAINS)


def passes_quality(
    hotel: StaySuggestion, hotel_budget: float | None
) -> bool:
    """质量过滤：评分、预算、纯宾馆。

    评分缺失时只放行常见连锁；如果过滤后为空，上层会回退到未过滤结果，
    避免因为高德字段缺失把整页清空。
    """
    if hotel_budget is not None and hotel.cost_amount is not None:
        if hotel.cost_amount > hotel_budget:
            return False
    if hotel.rating is not None and hotel.rating < 4.0:
        return False
    if hotel.rating is None and not is_known_chain(hotel.name):
        return False
    if "宾馆" in hotel.name and not is_known_chain(hotel.name):
        if "酒店" not in hotel.name and "饭店" not in hotel.name:
            return False
    return True


@dataclass(frozen=True)
class AccessGateway:
    name: str
    location: tuple[float, float]
    mode: str
    duration_minutes: int
    buffer_minutes: int
    note: str | None = None


@lru_cache(maxsize=1)
def _gateways() -> dict[str, tuple[AccessGateway, ...]]:
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    result: dict[str, tuple[AccessGateway, ...]] = {}
    for poi_name, rows in payload.items():
        result[poi_name] = tuple(
            AccessGateway(
                name=str(row["name"]),
                location=(
                    float(row["location_gcj02"][0]),
                    float(row["location_gcj02"][1]),
                ),
                mode=str(row["mode"]),
                duration_minutes=int(row["duration_minutes"]),
                buffer_minutes=int(row["buffer_minutes"]),
                note=str(row["note"]) if row.get("note") else None,
            )
            for row in rows
        )
    return result


def gateways_for_poi(poi_name: str) -> tuple[AccessGateway, ...]:
    return _gateways().get(poi_name, ())


def _minutes(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return meters_between(lon1, lat1, lon2, lat2) / 1000 / _CITY_SPEED_KMH * 60


def commute_minutes(
    hotel: tuple[float, float],
    poi: tuple[float, float],
    poi_name: str,
) -> float:
    """酒店到景点的有效通勤；特殊景点取直达与门户方案的最小值。"""
    direct = _minutes(hotel[0], hotel[1], poi[0], poi[1])
    for gateway in gateways_for_poi(poi_name):
        gateway_wgs = gcj02_to_wgs84(*gateway.location)
        via_gateway = (
            _minutes(hotel[0], hotel[1], gateway_wgs[0], gateway_wgs[1])
            + gateway.duration_minutes
            + gateway.buffer_minutes
        )
        direct = min(direct, via_gateway)
    return direct


@dataclass(frozen=True)
class HotelCommute:
    hotel: StaySuggestion
    avg_commute_minutes: float
    max_commute_minutes: float
    day_commutes: tuple[float, ...]
    tier: str
    score: float


def score_hotel(hotel: StaySuggestion, days: list[list[tuple[float, float, str]]]) -> HotelCommute | None:
    if hotel.location is None:
        return None
    hotel_wgs = gcj02_to_wgs84(*hotel.location)
    day_commutes: list[float] = []
    for items in days:
        if not items:
            continue
        first = items[0]
        last = items[-1]
        to_first = commute_minutes(hotel_wgs, (first[0], first[1]), first[2])
        from_last = commute_minutes(hotel_wgs, (last[0], last[1]), last[2])
        day_commutes.append(to_first + from_last)
    if not day_commutes:
        return None
    average = sum(day_commutes) / len(day_commutes)
    maximum = max(day_commutes)
    tier = classify_tier(hotel)
    # 平均通勤重要，但“某一天特别远”也要惩罚；未知价格/经济型降权。
    score = average * 0.7 + maximum * 0.3
    if hotel.cost_amount is None:
        score += 6
    if tier == "经济型":
        score += 8
    return HotelCommute(
        hotel=hotel,
        avg_commute_minutes=round(average),
        max_commute_minutes=round(maximum),
        day_commutes=tuple(round(value) for value in day_commutes),
        tier=tier,
        score=score,
    )


def pick_diverse(
    ranked: list[HotelCommute],
    *,
    limit: int = 5,
    per_area: int = 2,
) -> list[HotelCommute]:
    """限制同一商圈最多 N 家，避免五家全挤在一片。"""
    selected: list[HotelCommute] = []
    counts: dict[str, int] = {}
    for item in ranked:
        area = item.hotel.business_area or "未知区域"
        if counts.get(area, 0) >= per_area:
            continue
        selected.append(item)
        counts[area] = counts.get(area, 0) + 1
        if len(selected) >= limit:
            return selected
    selected_ids = {id(item) for item in selected}
    for item in ranked:
        if id(item) in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected
