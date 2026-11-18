"""规划器与路线服务之间的最小协议。

规划器不直接依赖高德适配层；任何满足该协议的对象（真实客户端、缓存包装器、
测试固定响应）都可以注入。
"""

from __future__ import annotations

from typing import Protocol


class RouteResult(Protocol):
    mode: str
    distance_m: int | None
    duration_s: int | None
    walking_distance_m: int | None
    cost_amount: float | None
    cost_basis: str | None
    status: str
    source: str | None
    is_estimate: bool
    error: str | None
    segments: tuple = ()
    alternatives: tuple = ()


class RouteProvider(Protocol):
    def route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        mode: str = "walk",
        *,
        city: str | None = None,
        cityd: str | None = None,
    ) -> RouteResult: ...
