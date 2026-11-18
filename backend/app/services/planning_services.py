"""规划请求使用的路线/天气服务装配。

``AmapClient`` 只负责单次调用；本模块补上：

- 进程内、单次规划请求内的缓存：同一对景点只查一次路线，同一城市只查一次天气；
- 简单的调用间隔限制，避免一次规划瞬间打满 QPS；
- 失败降级：任何异常都回到“无数据”，由规划器标 unknown，不向上抛 500。

缓存是请求级的（每个请求新建 provider），不做跨用户长期缓存，避免把他人
行程或过期天气复用给当前用户。
"""

from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Iterator

from app.core.config import settings
from app.planners.models import PlanningWeather
from app.services.amap import AmapClient, RestaurantSuggestion, RouteLeg, StaySuggestion, WeatherDay
from app.services.amap_mock import MockAmapProvider

_GLOBAL_CACHE: dict[tuple, tuple[float, object]] = {}
_GLOBAL_CACHE_LOCK = threading.Lock()
_ROUTE_TTL_S = 24 * 60 * 60
_WEATHER_TTL_S = 30 * 60
_PLACE_TTL_S = 6 * 60 * 60


def _cache_get(key: tuple, ttl_s: int):
    with _GLOBAL_CACHE_LOCK:
        entry = _GLOBAL_CACHE.get(key)
        if entry is None:
            return None
        stored_at, value = entry
        if time.time() - stored_at > ttl_s:
            _GLOBAL_CACHE.pop(key, None)
            return None
        return value


def _cache_set(key: tuple, value: object) -> None:
    with _GLOBAL_CACHE_LOCK:
        _GLOBAL_CACHE[key] = (time.time(), value)


class CachedAmapProvider:
    """给高德客户端加请求级缓存和最小调用间隔。"""

    def __init__(
        self,
        client: AmapClient,
        *,
        min_interval_s: float = 0.05,
        sleeper=time.sleep,
        mode: str = "live",
    ) -> None:
        self._client = client
        self._mode = mode
        self._min_interval_s = max(0.0, min_interval_s)
        self._sleep = sleeper
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._route_cache: dict[tuple, RouteLeg] = {}
        self._weather_cache: dict[str, list[WeatherDay]] = {}
        self._restaurant_cache: dict[tuple, list[RestaurantSuggestion]] = {}
        self._stay_cache: dict[tuple, list[StaySuggestion]] = {}

    def close(self) -> None:
        self._client.close()

    def _throttle_locked(self) -> None:
        if self._min_interval_s <= 0:
            return
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "walk",
        *,
        city: str | None = None,
        cityd: str | None = None,
    ) -> RouteLeg:
        key = (
            round(origin[0], 6),
            round(origin[1], 6),
            round(destination[0], 6),
            round(destination[1], 6),
            mode,
            city,
            cityd,
        )
        global_key = ("route", *key)
        if self._mode == "cache":
            hit = _cache_get(global_key, _ROUTE_TTL_S)
            if hit is not None:
                return hit
        with self._lock:
            cached = self._route_cache.get(key)
            if cached is not None:
                return cached
            self._throttle_locked()
            leg = self._client.route(
                origin, destination, mode, city=city, cityd=cityd
            )
            self._route_cache[key] = leg
            if self._mode == "cache" and leg.status == "ok":
                _cache_set(global_key, leg)
            return leg

    def weather_by_date(
        self, city_adcode: str, dates: list[date]
    ) -> dict[date, WeatherDay]:
        global_key = ("weather", city_adcode)
        forecasts = None
        if self._mode == "cache":
            forecasts = _cache_get(global_key, _WEATHER_TTL_S)
        if forecasts is None:
            with self._lock:
                if city_adcode not in self._weather_cache:
                    self._throttle_locked()
                    self._weather_cache[city_adcode] = self._client.weather(city_adcode)
                forecasts = self._weather_cache[city_adcode]
            if self._mode == "cache" and forecasts:
                _cache_set(global_key, forecasts)

        wanted = set(dates)
        return {
            day.forecast_date: day
            for day in forecasts
            if day.forecast_date in wanted
        }

    def nearby_restaurants(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 800,
        limit: int = 5,
    ) -> list[RestaurantSuggestion]:
        key = (round(location[0], 6), round(location[1], 6), city, radius, limit)
        global_key = ("restaurants", *key)
        if self._mode == "cache":
            hit = _cache_get(global_key, _PLACE_TTL_S)
            if hit is not None:
                return hit
        with self._lock:
            cached = self._restaurant_cache.get(key)
            if cached is not None:
                return cached
            self._throttle_locked()
            result = self._client.nearby_restaurants(
                location, city, radius=radius, limit=limit
            )
            self._restaurant_cache[key] = result
            if self._mode == "cache" and result:
                _cache_set(global_key, result)
            return result

    def nearby_hotels(
        self,
        location: tuple[float, float],
        city: str,
        *,
        radius: int = 3000,
        limit: int = 8,
    ) -> list[StaySuggestion]:
        key = (round(location[0], 6), round(location[1], 6), city, radius, limit)
        global_key = ("hotels", *key)
        if self._mode == "cache":
            hit = _cache_get(global_key, _PLACE_TTL_S)
            if hit is not None:
                return hit
        with self._lock:
            cached = self._stay_cache.get(key)
            if cached is not None:
                return cached
            self._throttle_locked()
            result = self._client.nearby_hotels(
                location, city, radius=radius, limit=limit
            )
            self._stay_cache[key] = result
            if self._mode == "cache" and result:
                _cache_set(global_key, result)
            return result


AmapProvider = CachedAmapProvider | MockAmapProvider


def get_planning_provider() -> Iterator[AmapProvider | None]:
    """FastAPI 依赖：mock 用本地数据；cache/live 需要 Key，缺失时降级为 None。"""
    if settings.amap_mode == "mock":
        yield MockAmapProvider()
        return

    if not settings.amap_api_key:
        yield None
        return

    client = AmapClient()
    provider = CachedAmapProvider(client, mode=settings.amap_mode)
    try:
        yield provider
    finally:
        provider.close()


def weather_for_dates(
    provider: AmapProvider | None,
    city_adcode: str | None,
    start_date: date,
    days: int,
) -> dict[date, PlanningWeather]:
    """取指定日期范围内的天气；无 Key、无 adcode 或调用失败都返回空字典。"""
    if provider is None or not city_adcode:
        return {}

    wanted = [start_date + timedelta(days=offset) for offset in range(days)]
    try:
        raw = provider.weather_by_date(city_adcode, wanted)
    except Exception:  # noqa: BLE001 - 外部服务失败必须降级为 unknown
        return {}

    return {
        forecast_date: PlanningWeather(
            forecast_date=forecast_date,
            condition=day.condition,
            temperature_min=day.temperature_min,
            temperature_max=day.temperature_max,
            precipitation=day.precipitation,
            risk_level=day.risk_level,
            source=day.source,
        )
        for forecast_date, day in raw.items()
    }
