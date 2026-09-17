from decimal import Decimal

from fastapi import APIRouter

from app.schemas.transport import (
    RouteCalculateRequest,
    RouteCalculateResponse,
    RouteSegment,
    RouteSummary,
    TransportSearchRequest,
    TransportSearchResponse,
)


router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("/calculate", response_model=RouteCalculateResponse)
def calculate_route(payload: RouteCalculateRequest) -> RouteCalculateResponse:
    # MVP 阶段仅提供明确标注的估算，不冒充高德真实路线数据。
    latitude_delta = payload.destination.lat - payload.origin.lat
    longitude_delta = payload.destination.lng - payload.origin.lng
    distance = Decimal(str(((latitude_delta**2 + longitude_delta**2) ** 0.5) * 111))
    speed_kmh = {"walk": 4, "public_transport": 25, "drive": 40}[payload.travel_mode]
    duration = max(1, round(float(distance) / speed_kmh * 60))
    return RouteCalculateResponse(
        route_summary=RouteSummary(
            distance_km=distance.quantize(Decimal("0.01")),
            duration_minutes=duration,
            mode=payload.travel_mode,
        ),
        segments=[
            RouteSegment(
                mode=payload.travel_mode,
                duration_minutes=duration,
                distance_km=distance.quantize(Decimal("0.01")),
            )
        ],
        source="Mock Data - straight-line estimate",
    )


@router.post("/search", response_model=TransportSearchResponse)
def search_transport(payload: TransportSearchRequest) -> TransportSearchResponse:
    result = calculate_route(
        RouteCalculateRequest(
            origin=payload.origin,
            destination=payload.destination,
            travel_mode=payload.travel_mode,
        )
    )
    return TransportSearchResponse(options=[result.route_summary], source=result.source)
