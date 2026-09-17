from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class RoutePoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteCalculateRequest(BaseModel):
    origin: RoutePoint
    destination: RoutePoint
    travel_mode: Literal["walk", "public_transport", "drive"] = "public_transport"


class RouteSegment(BaseModel):
    mode: str
    duration_minutes: int
    distance_km: Decimal


class RouteSummary(BaseModel):
    distance_km: Decimal
    duration_minutes: int
    mode: str


class RouteCalculateResponse(BaseModel):
    route_summary: RouteSummary
    segments: list[RouteSegment]
    source: str


class TransportSearchRequest(BaseModel):
    origin: RoutePoint
    destination: RoutePoint
    travel_mode: Literal["walk", "public_transport", "drive"] = "public_transport"


class TransportSearchResponse(BaseModel):
    options: list[RouteSummary]
    source: str
