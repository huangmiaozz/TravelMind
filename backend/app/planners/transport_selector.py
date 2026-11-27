"""景点之间的交通方式决策。

本模块只负责“给定 A→B 和上下文，列出可行方式并排序”，不负责景点顺序。
规划器拿到排好序的候选后，再按当天时间窗和剩余步行额度逐条尝试。

首版候选：
- walk：始终查询，作为兜底；
- transit：距离较远、步行太久或用户偏好公交时查询；
- bicycle：1–5 km 且天气不差时查询；
- taxi：驾车路线 + 里程估价，步行太久或公交不可用时查询；
- drive：只有用户明确选择自驾倾向时才查询。

费用口径：
- 步行 0 元；
- 公交用高德返回票价（每人）；
- 骑行按次估算（每人，标记 estimate）；
- 打车按“起步价 + 里程”估算（每车，标记 estimate）；
- 自驾费用未知，不用 0 冒充。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.planners.models import PlanningWeather, TransitSegment
from app.planners.routing import RouteProvider
from app.services.coordinates import meters_between, wgs84_to_gcj02
from app.services.hotel_recommendations import gateways_for_poi

TRANSIT_QUERY_DISTANCE_M = 1500
WALK_LONG_DURATION_S = 20 * 60
TAXI_TRIGGER_WALK_S = 35 * 60
MIN_BIKE_DISPLAY_M = 300
TAXI_BASE_YUAN = 10.0
TAXI_PER_KM_YUAN = 2.5
BIKE_FLAT_YUAN = 2.0


@dataclass(frozen=True)
class TransportOption:
    mode: str
    distance_m: int | None
    duration_s: int | None
    walking_distance_m: int | None
    cost_amount: float | None
    cost_basis: str
    status: str
    source: str | None
    is_estimate: bool
    error: str | None = None
    reason: str = ""
    segments: tuple[TransitSegment, ...] = ()
    # 步行/骑行合并为一个主动出行选项；排程用步行耗时作为上限。
    walk_duration_s: int | None = None
    bike_duration_s: int | None = None
    bike_cost_amount: float | None = None


def _weather_penalty(mode: str, weather: PlanningWeather | None) -> float:
    if mode not in ("walk", "bicycle", "active"):
        return 0.0
    if weather is None:
        return 0.3
    if weather.risk_level == "high":
        return 1.0
    if weather.risk_level == "medium":
        return 0.6
    return 0.0


def _preference_penalty(mode: str, preference: str) -> float:
    if preference == "auto":
        return 0.0
    if mode == "active":
        return 0.0 if preference in ("walk", "bicycle") else 0.35
    if preference in ("walk", "transit", "bicycle", "drive", "taxi"):
        return 0.0 if mode == preference else 0.35
    return 0.0


def _normalized(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return min(1.0, max(0.0, value / cap))


def score_option(
    option: TransportOption,
    *,
    preference: str,
    weather: PlanningWeather | None,
    max_walk_m: float | None,
    daily_budget: float,
) -> float:
    """越低越优先；硬约束不在这里处理，由规划器逐条试。"""
    if option.status != "ok" or option.duration_s is None:
        return 10.0

    time_score = _normalized(option.duration_s, 30 * 60)
    # 每段费用归一化上限压到 10–20 元，避免高预算时打车仅凭“相对总预算很便宜”胜出。
    cost_cap = max(10.0, min(20.0, daily_budget / 100.0))
    cost_score = (
        0.5
        if option.cost_amount is None
        else _normalized(option.cost_amount, cost_cap)
    )
    walk_score = (
        0.5
        if option.walking_distance_m is None
        else _normalized(
            option.walking_distance_m,
            max_walk_m if max_walk_m is not None else 3000,
        )
    )
    # 公共交通内部优先地铁：纯公交方案小幅降权，含地铁方案小幅加权。
    # 公共交通内部以最快为主，地铁只做很小的同分偏好。
    transit_bonus = 0.0
    if option.mode == "transit" and option.segments:
        has_subway = any(
            segment.mode == "subway" for segment in option.segments
        )
        has_rail = any(
            segment.mode == "train" for segment in option.segments
        )
        transit_bonus = -0.03 if has_subway else 0.03
        if has_rail:
            # 京张高铁是八达岭的门户方案，避免被更慢的 877 压下去。
            transit_bonus -= 0.15
    return (
        time_score * 0.30
        + cost_score * 0.30
        + walk_score * 0.20
        + _weather_penalty(option.mode, weather) * 0.10
        + _preference_penalty(option.mode, preference) * 0.10
        + transit_bonus
    )


def _to_option(mode: str, raw, *, cost=None, cost_basis="unknown", is_estimate=False, reason="") -> TransportOption:
    return TransportOption(
        mode=mode,
        distance_m=raw.distance_m,
        duration_s=raw.duration_s,
        walking_distance_m=(
            raw.walking_distance_m
            if mode in ("walk", "transit")
            else (None if mode == "drive" else 0)
        ),
        cost_amount=cost,
        cost_basis=cost_basis,
        status=raw.status,
        source=raw.source,
        is_estimate=is_estimate,
        error=raw.error,
        reason=reason,
        segments=getattr(raw, "segments", ()) if mode == "transit" else (),
    )


RAIL_FARE_YUAN = 25.0


def _gateway_options(
    provider: RouteProvider,
    origin_gcj: tuple[float, float],
    destination_gcj: tuple[float, float],
    *,
    origin_name: str | None,
    destination_name: str | None,
    city: str | None,
) -> list[TransportOption]:
    """给八达岭这类特殊景点补一条“门户 + 高铁”方案。

    高德公交接口通常不返回京张高铁，所以这里用人工维护的门户耗时和票价拼一条
    可选方案，交给统一评分比较。它是估算，不伪装成高德实时路线。
    """
    if city is None:
        return []
    options: list[TransportOption] = []

    def append_leg(leg, gateway, *, reverse: bool) -> None:
        if leg.status != "ok" or leg.duration_s is None:
            return
        rail_seconds = (gateway.duration_minutes + gateway.buffer_minutes) * 60
        is_rail = gateway.mode == "rail"
        line_name = "京张高铁" if is_rail else "877 路"
        line_type = "高铁" if is_rail else "公交"
        terminal = "八达岭长城站" if is_rail else "八达岭"
        rail_segment = TransitSegment(
            mode="train" if is_rail else "bus",
            line_name=line_name,
            line_type=line_type,
            departure_stop=terminal if reverse else gateway.name,
            arrival_stop=gateway.name if reverse else terminal,
            duration_s=rail_seconds,
        )
        segments = (
            (rail_segment,) + leg.segments
            if reverse
            else leg.segments + (rail_segment,)
        )
        cost = (leg.cost_amount or 0.0) + RAIL_FARE_YUAN
        options.append(
            TransportOption(
                mode="transit",
                distance_m=leg.distance_m,
                duration_s=leg.duration_s + rail_seconds,
                walking_distance_m=leg.walking_distance_m,
                cost_amount=round(cost, 2),
                cost_basis="per_person",
                status="ok",
                source="amap+gateway",
                is_estimate=True,
                reason=f"{gateway.name} + {line_name}（门户方案）",
                segments=segments,
            )
        )

    if destination_name:
        for gateway in gateways_for_poi(destination_name):
            leg = provider.route(
                origin_gcj,
                gateway.location,
                "transit",
                city=city,
                cityd=city,
            )
            append_leg(leg, gateway, reverse=False)
    if origin_name:
        for gateway in gateways_for_poi(origin_name):
            leg = provider.route(
                gateway.location,
                destination_gcj,
                "transit",
                city=city,
                cityd=city,
            )
            append_leg(leg, gateway, reverse=True)
    return options


def build_transport_options(
    provider: RouteProvider,
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    preference: str,
    weather: PlanningWeather | None,
    city: str | None,
    daily_budget: float,
    max_walk_m: float | None,
    origin_name: str | None = None,
    destination_name: str | None = None,
) -> list[TransportOption]:
    """查询候选并返回按评分从低到高排序的列表。"""
    straight_m = meters_between(
        origin[0], origin[1], destination[0], destination[1]
    )
    origin_gcj = wgs84_to_gcj02(*origin)
    destination_gcj = wgs84_to_gcj02(*destination)
    options: list[TransportOption] = []

    def query(mode: str):
        return provider.route(
            origin_gcj,
            destination_gcj,
            mode,
            city=city,
            cityd=city,
        )

    walk = query("walk")
    bicycle = None
    walk_distance = walk.distance_m or straight_m
    if walk_distance >= MIN_BIKE_DISPLAY_M:
        # 骑行不再参与“选哪种方式”，只为页面提供与步行并列的骑行耗时。
        bicycle = query("bicycle")

    walk_ok = walk.status == "ok" and walk.duration_s is not None
    bike_ok = (
        bicycle is not None
        and bicycle.status == "ok"
        and bicycle.duration_s is not None
    )
    if walk_ok or bike_ok:
        # 骑行并入“主动出行”：排程时间用步行耗时做上限，页面同时给出两种耗时。
        duration = walk.duration_s if walk_ok else bicycle.duration_s
        distance = walk.distance_m if walk_ok else bicycle.distance_m
        walking_distance = walk.distance_m if walk_ok else None
        options.append(
            TransportOption(
                mode="active",
                distance_m=distance,
                duration_s=duration,
                walking_distance_m=walking_distance,
                cost_amount=0.0 if walk_ok else BIKE_FLAT_YUAN,
                cost_basis="per_person",
                status="ok",
                source=walk.source if walk_ok else bicycle.source,
                is_estimate=False,
                reason=(
                    "步行/骑行可选，排程按步行耗时"
                    if walk_ok and bike_ok
                    else ("步行，费用 0" if walk_ok else "步行不可用，按骑行耗时")
                ),
                walk_duration_s=walk.duration_s if walk_ok else None,
                bike_duration_s=bicycle.duration_s if bike_ok else None,
                bike_cost_amount=BIKE_FLAT_YUAN if bike_ok else None,
            )
        )

    need_transit = (
        preference == "transit"
        or (preference == "auto" and straight_m >= TRANSIT_QUERY_DISTANCE_M)
        or (
            preference in ("walk", "auto")
            and walk.duration_s is not None
            and walk.duration_s > WALK_LONG_DURATION_S
        )
        or walk.status != "ok"
    )
    transit_ok = False
    if need_transit:
        transit = query("transit")
        if transit.status == "ok" and transit.duration_s is not None:
            transit_ok = True
            alternatives = getattr(transit, "alternatives", ())
            valid_alternatives = [
                item for item in alternatives if item.duration_s is not None
            ]
            if valid_alternatives:
                # 高德已按“最快捷”返回多方案；这里只取耗时最短的一条，
                # 避免费用/步行权重把更慢的公交方案顶到前面。
                fastest = min(
                    valid_alternatives,
                    key=lambda item: item.duration_s,
                )
                options.append(
                    TransportOption(
                        mode="transit",
                        distance_m=fastest.distance_m,
                        duration_s=fastest.duration_s,
                        walking_distance_m=fastest.walking_distance_m,
                        cost_amount=fastest.cost_amount,
                        cost_basis=(
                            "per_person"
                            if fastest.cost_amount is not None
                            else "unknown"
                        ),
                        status="ok",
                        source=transit.source,
                        is_estimate=False,
                        reason="公共交通最快方案",
                        segments=fastest.segments,
                    )
                )
            else:
                options.append(
                    _to_option(
                        "transit",
                        transit,
                        cost=transit.cost_amount,
                        cost_basis="per_person" if transit.cost_amount is not None else "unknown",
                        reason="公交/地铁，票价来自高德" if transit.cost_amount is not None else "公交/地铁，票价未知",
                    )
                )

    if origin_name or destination_name:
        gateway_options = _gateway_options(
            provider,
            origin_gcj,
            destination_gcj,
            origin_name=origin_name,
            destination_name=destination_name,
            city=city,
        )
        if gateway_options:
            options.extend(gateway_options)
            transit_ok = True

    need_taxi = (
        preference == "taxi"
        or (
            preference == "auto"
            and (
                walk.duration_s is None
                or walk.duration_s > TAXI_TRIGGER_WALK_S
                or not transit_ok
            )
        )
    )
    if need_taxi:
        drive = query("drive")
        if drive.status == "ok" and drive.duration_s is not None:
            km = (drive.distance_m or 0) / 1000
            taxi_cost = round(TAXI_BASE_YUAN + TAXI_PER_KM_YUAN * km, 2)
            options.append(
                _to_option(
                    "taxi",
                    drive,
                    cost=taxi_cost,
                    cost_basis="per_vehicle",
                    is_estimate=True,
                    reason="打车，费用按里程估算",
                )
            )

    if preference == "drive":
        drive = query("drive")
        if drive.status == "ok" and drive.duration_s is not None:
            options.append(
                _to_option(
                    "drive",
                    drive,
                    cost=None,
                    cost_basis="unknown",
                    reason="自驾，油费/停车费未建模",
                )
            )

    return sorted(
        options,
        key=lambda option: score_option(
            option,
            preference=preference,
            weather=weather,
            max_walk_m=max_walk_m,
            daily_budget=daily_budget,
        ),
    )


def enrich_transit_walk_segments(
    provider: RouteProvider,
    segments: tuple[TransitSegment, ...],
    *,
    city: str | None = None,
) -> tuple[TransitSegment, ...]:
    """给公交方案里的接驳步行补一个骑行耗时，供页面并列展示。

    只影响展示，不改变排程；低于 300 米或缺少坐标的步行段跳过。
    """
    enriched: list[TransitSegment] = []
    for segment in segments:
        if (
            segment.mode == "walk"
            and (segment.distance_m or 0) >= MIN_BIKE_DISPLAY_M
            and segment.origin_location is not None
            and segment.destination_location is not None
        ):
            try:
                bike = provider.route(
                    segment.origin_location,
                    segment.destination_location,
                    "bicycle",
                    city=city,
                    cityd=city,
                )
            except Exception:  # noqa: BLE001 - 展示失败不能影响方案
                bike = None
            if (
                bike is not None
                and bike.status == "ok"
                and bike.duration_s is not None
            ):
                segment = replace(
                    segment,
                    bike_distance_m=bike.distance_m,
                    bike_duration_s=bike.duration_s,
                )
        enriched.append(segment)
    return tuple(enriched)
