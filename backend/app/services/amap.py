"""高德 Web 服务适配层。

只负责“调用 + 解析 + 明确失败”，不做排程、不做评分、不拼假数据。
规划器拿到的是 ``RouteLeg`` / ``WeatherDay``；调用失败时返回
``status="failed"`` 且距离/耗时为 ``None``，由上层决定降级，绝不用
直线距离冒充真实路线。

坐标约定：入参为 GCJ-02 的 ``(经度, 纬度)``，与高德接口一致；
数据库里的 WGS84 坐标需先经 ``app.services.coordinates`` 转换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import httpx

from app.core.config import settings
from app.planners.models import TransitAlternative, TransitSegment

AMAP_BASE_URL = "https://restapi.amap.com"
ROUTE_SOURCE = "amap_web_service"

# mode -> 路径。公交需要 city/cityd，单独处理参数。
ROUTE_PATHS = {
    "walk": "/v3/direction/walking",
    "drive": "/v3/direction/driving",
    "bicycle": "/v4/direction/bicycling",
    "transit": "/v3/direction/transit/integrated",
}


@dataclass(frozen=True)
class RestaurantSuggestion:
    name: str
    address: str | None
    distance_m: int | None
    cost_amount: float | None
    rating: float | None
    location: tuple[float, float] | None


@dataclass(frozen=True)
class StaySuggestion:
    name: str
    address: str | None
    business_area: str | None
    stay_type: str | None
    distance_m: int | None
    cost_amount: float | None
    rating: float | None
    location: tuple[float, float] | None


@dataclass(frozen=True)
class RouteLeg:
    """一段真实路线结果；失败时距离/耗时为 None。"""

    mode: str
    distance_m: int | None
    duration_s: int | None
    walking_distance_m: int | None
    cost_amount: float | None
    cost_basis: str | None
    status: str
    source: str = ROUTE_SOURCE
    is_mock: bool = False
    error: str | None = None
    segments: tuple[TransitSegment, ...] = ()
    alternatives: tuple[TransitAlternative, ...] = ()

    @property
    def is_estimate(self) -> bool:
        """与规划器协议对齐；真实高德路线始终为 False。"""
        return self.is_mock


@dataclass(frozen=True)
class WeatherDay:
    """某一天的城市级预报。"""

    forecast_date: date
    condition: str
    temperature_min: float | None
    temperature_max: float | None
    precipitation: float | None
    risk_level: str
    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: str = ROUTE_SOURCE
    status: str = "known"


def _to_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _to_point(value: object) -> tuple[float, float] | None:
    try:
        lon, lat = str(value).split(",")
        return float(lon), float(lat)
    except (TypeError, ValueError):
        return None


def _is_campus_place(name: str, address: str | None, type_text: str) -> bool:
    """高德会把校内宾馆/食堂也归到住宿/餐饮；这里排除校园内部场所。"""
    text = f"{name} {type_text}"
    if any(
        word in text
        for word in (
            "大学",
            "学院",
            "校区",
            "学校",
            "学术交流中心",
            "专家楼",
            "培训中心",
            "党校",
        )
    ):
        return True
    address_text = address or ""
    return any(
        word in address_text
        for word in ("大学内", "学院内", "校区内", "学校内", "校园内")
    )


def _is_hotel(
    name: str, address: str | None, type_text: str, typecode: str
) -> bool:
    """过滤“住宿服务”大类里的招待所、青年旅舍、民宿、校内宾馆等非酒店。"""
    if _is_campus_place(name, address, type_text):
        return False
    text = f"{name} {type_text}"
    if any(
        word in text
        for word in ("招待所", "青年旅舍", "旅馆", "民宿", "客栈", "公寓")
    ):
        return False
    if "住宿" not in type_text and not typecode.startswith("100"):
        return False
    return (
        typecode.startswith("1001")
        or "宾馆酒店" in type_text
        or any(word in name for word in ("酒店", "宾馆", "饭店"))
    )


def _risk_from_condition(condition: str) -> str:
    """把天气现象映射成粗粒度风险；这是规划用的启发式，不是官方预警。"""
    if any(word in condition for word in ("暴雨", "大暴雨", "雷暴", "冰雹", "台风")):
        return "high"
    if any(word in condition for word in ("雨", "雪", "雷", "雾", "霾", "沙尘")):
        return "medium"
    return "low"


class AmapClient:
    """高德 Web 服务客户端。

    仅暴露 route / weather 两个能力；测试可注入 ``httpx.Client``，
    用 MockTransport 固定响应，不访问真实接口。
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = AMAP_BASE_URL,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        key = api_key if api_key is not None else settings.amap_api_key
        if not key:
            raise ValueError("AMAP_API_KEY is not configured")
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout, trust_env=False)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "AmapClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ---- 底层请求 ----

    def _get(self, path: str, params: dict[str, str]) -> tuple[dict | None, str | None]:
        try:
            response = self._client.get(
                self.base_url + path,
                params={**params, "key": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - 适配层要如实记录任何失败
            message = str(exc).replace(self.api_key, "***")
            return None, f"{type(exc).__name__}: {message[:120]}"
        if not isinstance(payload, dict):
            return None, "unexpected response: not a JSON object"
        return payload, None

    def _failed(self, mode: str, error: str) -> RouteLeg:
        return RouteLeg(
            mode=mode,
            distance_m=None,
            duration_s=None,
            walking_distance_m=None,
            cost_amount=None,
            cost_basis=None,
            status="failed",
            error=error,
        )

    # ---- 路线 ----

    def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "walk",
        *,
        city: str | None = None,
        cityd: str | None = None,
    ) -> RouteLeg:
        """查询一段真实路线。

        ``origin`` / ``destination`` 为 GCJ-02 的 (经度, 纬度)。
        公交必须提供 ``city`` 与 ``cityd``（城市名或 adcode 均可）。
        """
        path = ROUTE_PATHS.get(mode)
        if path is None:
            return self._failed(mode, f"unsupported transport mode: {mode}")

        params: dict[str, str] = {
            "origin": f"{origin[0]:.6f},{origin[1]:.6f}",
            "destination": f"{destination[0]:.6f},{destination[1]:.6f}",
        }
        if mode == "transit":
            if not city or not cityd:
                return self._failed(mode, "transit requires city and cityd")
            params["city"] = city
            params["cityd"] = cityd

        payload, error = self._get(path, params)
        if error is not None or payload is None:
            return self._failed(mode, error or "empty response")

        if mode == "bicycle":
            return self._parse_bicycle(payload)
        if mode == "transit":
            return self._parse_transit(payload)
        return self._parse_path(payload, mode)

    def _parse_path(self, payload: dict, mode: str) -> RouteLeg:
        if str(payload.get("status")) != "1":
            return self._failed(mode, self._business_error(payload))
        paths = (payload.get("route") or {}).get("paths") or []
        if not paths:
            return self._failed(mode, "no route paths")
        path = paths[0]
        distance = _to_int(path.get("distance"))
        duration = _to_int(path.get("duration"))
        if distance is None or duration is None:
            return self._failed(mode, "route path missing distance/duration")
        return RouteLeg(
            mode=mode,
            distance_m=distance,
            duration_s=duration,
            walking_distance_m=distance if mode == "walk" else None,
            cost_amount=None,
            cost_basis=None,
            status="ok",
        )

    def _parse_transit(self, payload: dict) -> RouteLeg:
        if str(payload.get("status")) != "1":
            return self._failed("transit", self._business_error(payload))
        transits = (payload.get("route") or {}).get("transits") or []
        if not transits:
            return self._failed("transit", "no transit routes")

        alternatives: list[TransitAlternative] = []
        for transit in transits:
            duration = _to_int(transit.get("duration"))
            if duration is None:
                continue
            distance = _to_int(transit.get("distance"))
            walking = _to_int(transit.get("walking_distance"))
            cost = _to_float(transit.get("cost"))
            alternatives.append(
                TransitAlternative(
                    distance_m=distance,
                    duration_s=duration,
                    walking_distance_m=walking,
                    cost_amount=cost,
                    segments=self._parse_transit_segments(transit),
                )
            )

        if not alternatives:
            return self._failed("transit", "transit route missing duration")

        primary = alternatives[0]
        return RouteLeg(
            mode="transit",
            distance_m=primary.distance_m,
            duration_s=primary.duration_s,
            walking_distance_m=primary.walking_distance_m,
            cost_amount=primary.cost_amount,
            cost_basis="per_person" if primary.cost_amount is not None else None,
            status="ok",
            segments=primary.segments,
            alternatives=tuple(alternatives),
        )

    @staticmethod
    def _parse_transit_segments(transit: dict) -> tuple[TransitSegment, ...]:
        """把公交方案拆成“步行接驳 / 公交 / 地铁”明细。"""
        segments: list[TransitSegment] = []
        for raw in transit.get("segments") or []:
            walking = raw.get("walking") or {}
            distance = _to_int(walking.get("distance"))
            duration = _to_int(walking.get("duration"))
            if distance or duration:
                segments.append(
                    TransitSegment(
                        mode="walk",
                        distance_m=distance,
                        duration_s=duration,
                        origin_location=_to_point(walking.get("origin")),
                        destination_location=_to_point(walking.get("destination")),
                    )
                )

            for busline in (raw.get("bus") or {}).get("buslines") or []:
                name = str(busline.get("name") or "") or None
                line_type = str(busline.get("type") or "") or None
                # 不能只看名称里有没有“地铁”：877 路的站名可能是“地铁北土城站”。
                # 以线路 type 为准；只有名称以“地铁”开头时才作为兜底。
                line_type_text = line_type or ""
                subway = "地铁" in line_type_text or "轨道" in line_type_text
                if not subway and name and name.startswith("地铁"):
                    subway = True
                departure = busline.get("departure_stop") or {}
                arrival = busline.get("arrival_stop") or {}
                segments.append(
                    TransitSegment(
                        mode="subway" if subway else "bus",
                        line_name=name,
                        line_type=line_type,
                        departure_stop=str(departure.get("name")) if departure.get("name") else None,
                        arrival_stop=str(arrival.get("name")) if arrival.get("name") else None,
                        departure_location=_to_point(departure.get("location")),
                        arrival_location=_to_point(arrival.get("location")),
                        via_stops=_to_int(busline.get("via_num")),
                        distance_m=_to_int(busline.get("distance")),
                        duration_s=_to_int(busline.get("duration")),
                    )
                )
        return tuple(segments)

    def _parse_bicycle(self, payload: dict) -> RouteLeg:
        if payload.get("errcode") not in (0, "0", None):
            return self._failed("bicycle", self._business_error(payload))
        paths = (payload.get("data") or {}).get("paths") or []
        if not paths:
            return self._failed("bicycle", "no bicycle paths")
        path = paths[0]
        distance = _to_int(path.get("distance"))
        duration = _to_int(path.get("duration"))
        if distance is None or duration is None:
            return self._failed("bicycle", "bicycle path missing distance/duration")
        return RouteLeg(
            mode="bicycle",
            distance_m=distance,
            duration_s=duration,
            walking_distance_m=None,
            cost_amount=None,
            cost_basis=None,
            status="ok",
        )

    @staticmethod
    def _business_error(payload: dict) -> str:
        info = payload.get("info") or payload.get("errmsg") or "unknown error"
        code = payload.get("infocode") or payload.get("errcode")
        return f"{info} ({code})" if code is not None else str(info)

    # ---- 天气 ----

    def weather(self, city_adcode: str) -> list[WeatherDay]:
        """取城市预报；失败或无 casts 时返回空列表，由上层标 unknown。"""
        payload, error = self._get(
            "/v3/weather/weatherInfo",
            {"city": city_adcode, "extensions": "all"},
        )
        if error is not None or payload is None:
            return []
        if str(payload.get("status")) != "1":
            return []
        forecasts = payload.get("forecasts") or []
        if not forecasts:
            return []
        casts = forecasts[0].get("casts") or []
        days: list[WeatherDay] = []
        for cast in casts:
            raw_date = cast.get("date")
            if not raw_date:
                continue
            try:
                forecast_date = date.fromisoformat(str(raw_date))
            except ValueError:
                continue
            condition = str(cast.get("dayweather") or cast.get("nightweather") or "未知")
            days.append(
                WeatherDay(
                    forecast_date=forecast_date,
                    condition=condition,
                    temperature_min=_to_float(cast.get("nighttemp")),
                    temperature_max=_to_float(cast.get("daytemp")),
                    precipitation=None,
                    risk_level=_risk_from_condition(condition),
                )
            )
        return days

    def weather_by_date(
        self, city_adcode: str, dates: list[date]
    ) -> dict[date, WeatherDay]:
        """只返回请求日期中真正有预报的那些天；缺失日期由上层标 unknown。"""
        wanted = set(dates)
        return {
            day.forecast_date: day
            for day in self.weather(city_adcode)
            if day.forecast_date in wanted
        }

    # ---- 用餐推荐 ----

    def nearby_restaurants(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 800,
        limit: int = 5,
    ) -> list[RestaurantSuggestion]:
        """按 GCJ-02 坐标查附近餐厅；失败返回空列表，由上层降级。"""
        payload, error = self._get(
            "/v3/place/around",
            {
                "location": f"{location[0]:.6f},{location[1]:.6f}",
                "radius": str(radius),
                "types": "050000",
                "city": city,
                "offset": "10",
                "page": "1",
                "extensions": "all",
            },
        )
        if error is not None or payload is None:
            return []
        if str(payload.get("status")) != "1":
            return []

        result: list[RestaurantSuggestion] = []
        for poi in payload.get("pois") or []:
            name = str(poi.get("name") or "未命名餐厅")
            address = str(poi.get("address")) if poi.get("address") else None
            type_text = str(poi.get("type") or "")
            if "食堂" in name or _is_campus_place(name, address, type_text):
                continue
            biz = poi.get("biz_ext") or {}
            result.append(
                RestaurantSuggestion(
                    name=name,
                    address=address,
                    distance_m=_to_int(poi.get("distance")),
                    cost_amount=_to_float(biz.get("cost")),
                    rating=_to_float(biz.get("rating")),
                    location=_to_point(poi.get("location")),
                )
            )
            if len(result) >= limit:
                break
        return result

    def nearby_hotels(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 3000,
        limit: int = 8,
    ) -> list[StaySuggestion]:
        """按 GCJ-02 坐标查附近酒店。

        `100000` 是“住宿服务”大类，包含招待所、青年旅舍等；这里只保留
        宾馆/酒店/饭店，过滤明显不是酒店的住宿类型。
        """
        payload, error = self._get(
            "/v3/place/around",
            {
                "location": f"{location[0]:.6f},{location[1]:.6f}",
                "radius": str(radius),
                "types": "100000",
                "city": city,
                "offset": "20",
                "page": "1",
                "extensions": "all",
            },
        )
        if error is not None or payload is None:
            return []
        if str(payload.get("status")) != "1":
            return []

        result: list[StaySuggestion] = []
        for poi in payload.get("pois") or []:
            name = str(poi.get("name") or "")
            address = str(poi.get("address")) if poi.get("address") else None
            type_text = str(poi.get("type") or "")
            typecode = str(poi.get("typecode") or "")
            if not _is_hotel(name, address, type_text, typecode):
                continue
            biz = poi.get("biz_ext") or {}
            result.append(
                StaySuggestion(
                    name=name or "未命名住宿",
                    address=address,
                    business_area=str(poi.get("business_area")) if poi.get("business_area") else None,
                    stay_type=type_text or None,
                    distance_m=_to_int(poi.get("distance")),
                    cost_amount=_to_float(biz.get("cost")),
                    rating=_to_float(biz.get("rating")),
                    location=_to_point(poi.get("location")),
                )
            )
            if len(result) >= limit:
                break
        return result
