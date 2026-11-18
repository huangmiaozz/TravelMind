from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.planner import (
    load_planner_context,
    planning_notes,
    trip_response,
)
from app.db.session import get_db
from app.models.trip import PlanVersion, Trip
from app.planners.trip import plan_trip
from app.schemas.plan import (
    MealSuggestion,
    MealSuggestionList,
    PlanCreateRequest,
    PlanDetail,
    PlanVersionList,
    PlanVersionSummary,
    StaySuggestion,
    StaySuggestionList,
)
from app.services.costs import build_costs
from app.services.plan_versions import (
    data_snapshot,
    next_version_no,
    request_snapshot,
    version_detail,
    version_summary,
)
from app.services.planning_services import (
    CachedAmapProvider,
    get_planning_provider,
    weather_for_dates,
)
from app.services.coordinates import gcj02_to_wgs84, meters_between, wgs84_to_gcj02
from app.services.static_map import StaticMapError, fetch_static_map


router = APIRouter(tags=["plans"])

# 方案生成后 plan_json 不再变化，按 (plan_id, day_index) 缓存静态图即可。
_MAP_CACHE: dict[tuple[int, int], bytes] = {}


def _get_trip(db: Session, trip_id: int, *, lock: bool = False) -> Trip:
    query = select(Trip).where(Trip.id == trip_id)
    if lock:
        # 同一 Trip 的版本号串行分配，避免并发请求拿到同一个 version_no。
        query = query.with_for_update()
    trip = db.scalar(query)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
        )
    return trip


def _versions(db: Session, trip_id: int) -> list[PlanVersion]:
    return list(
        db.scalars(
            select(PlanVersion)
            .where(PlanVersion.trip_id == trip_id)
            .order_by(PlanVersion.version_no)
        )
    )


@router.post(
    "/trips/{trip_id}/plans",
    response_model=PlanDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_version(
    trip_id: int,
    payload: PlanCreateRequest,
    db: Session = Depends(get_db),
    provider: CachedAmapProvider | None = Depends(get_planning_provider),
) -> PlanDetail:
    trip = _get_trip(db, trip_id, lock=True)
    if payload.city.strip() != trip.destination_city_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "city does not match trip destination: "
                f"{payload.city!r} != {trip.destination_city_name!r}"
            ),
        )

    candidates, preferences = load_planner_context(db, payload)
    weather_by_date = weather_for_dates(
        provider,
        trip.destination_city_adcode,
        payload.start_date,
        payload.days,
    )
    generated = plan_trip(
        payload.start_date,
        payload.days,
        candidates,
        preferences,
        weather_by_date=weather_by_date,
        route_provider=provider,
        city=trip.destination_city_name,
        transport_preference=payload.transport_preference,
    )
    costs = build_costs(generated, payload, trip.destination_city_name)
    body = trip_response(
        generated,
        trip.destination_city_name,
        "Rule-based multi-day planner",
        planning_notes(payload, generated),
        costs=costs,
    )

    snapshot = data_snapshot(
        weather_used=any(day.weather is not None for day in generated.days),
        route_used=any(day.legs for day in generated.days),
    )
    if any(
        (day.weather is not None and day.weather.source == "mock")
        or any(leg.source == "mock" for leg in day.legs)
        for day in generated.days
    ):
        snapshot["weather_source"] = "mock"
        snapshot["route_source"] = "mock"

    version = PlanVersion(
        trip_id=trip.id,
        version_no=next_version_no(db, trip.id),
        status=generated.status,
        start_date=generated.start_date,
        days_count=payload.days,
        adults_count=payload.adults,
        children_count=payload.children,
        budget_total=payload.budget_total,
        total_estimated_cost=costs.total_estimated,
        budget_difference=costs.budget_difference,
        over_budget=(
            costs.budget_total > 0
            and costs.total_estimated > costs.budget_total
        ),
        weather_known=generated.weather_known,
        request_json=request_snapshot(payload),
        plan_json=body.model_dump(mode="json"),
        data_snapshot=snapshot,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version_detail(version)


@router.get("/trips/{trip_id}/plans", response_model=PlanVersionList)
def list_plan_versions(
    trip_id: int, db: Session = Depends(get_db)
) -> PlanVersionList:
    _get_trip(db, trip_id)
    versions = _versions(db, trip_id)
    items: list[PlanVersionSummary] = [
        version_summary(version) for version in versions
    ]
    return PlanVersionList(items=items, total=len(items))


@router.get("/plans/{plan_id}", response_model=PlanDetail)
def get_plan_version(
    plan_id: int, db: Session = Depends(get_db)
) -> PlanDetail:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    return version_detail(version)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan_version(
    plan_id: int, db: Session = Depends(get_db)
) -> None:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    db.delete(version)
    db.commit()


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/suggestions",
    response_model=MealSuggestionList,
)
def meal_suggestions(
    plan_id: int,
    day_index: int,
    meal_type: str,
    db: Session = Depends(get_db),
    provider: CachedAmapProvider | None = Depends(get_planning_provider),
) -> MealSuggestionList:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    days = (version.plan_json or {}).get("days") or []
    if day_index < 1 or day_index > len(days):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Day not found"
        )
    day = days[day_index - 1]
    meal = next(
        (item for item in day.get("meals") or [] if item.get("meal_type") == meal_type),
        None,
    )
    if meal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Meal block not found"
        )
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )

    items = day.get("items") or []
    anchor = items[0] if items else None
    for item in items:
        if item.get("start_time", "") <= meal.get("start_time", ""):
            anchor = item
    if anchor is None or anchor.get("latitude") is None or anchor.get("longitude") is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No anchor coordinates for this meal",
        )

    location = wgs84_to_gcj02(
        float(anchor["longitude"]), float(anchor["latitude"])
    )
    suggestions = provider.nearby_restaurants(
        location, version.plan_json.get("city", ""), limit=5
    )
    return MealSuggestionList(
        items=[
            MealSuggestion(
                name=item.name,
                address=item.address,
                distance_m=item.distance_m,
                cost_amount=item.cost_amount,
                rating=item.rating,
            )
            for item in suggestions
        ],
        total=len(suggestions),
    )
@router.get(
    "/plans/{plan_id}/stays/suggestions",
    response_model=StaySuggestionList,
)
def stay_suggestions(
    plan_id: int,
    db: Session = Depends(get_db),
    provider: CachedAmapProvider | None = Depends(get_planning_provider),
) -> StaySuggestionList:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )

    coords = [
        (float(item["longitude"]), float(item["latitude"]))
        for day in version.plan_json.get("days") or []
        for item in day.get("items") or []
        if item.get("longitude") is not None and item.get("latitude") is not None
    ]
    if not coords:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attraction coordinates for stay suggestions",
        )

    center_lon = sum(point[0] for point in coords) / len(coords)
    center_lat = sum(point[1] for point in coords) / len(coords)
    hotels = provider.nearby_hotels(
        wgs84_to_gcj02(center_lon, center_lat),
        version.plan_json.get("city", ""),
        limit=8,
    )

    ranked: list[tuple[float, StaySuggestion]] = []
    for hotel in hotels:
        if hotel.location is None:
            continue
        hotel_lon, hotel_lat = gcj02_to_wgs84(*hotel.location)
        avg_distance = sum(
            meters_between(hotel_lon, hotel_lat, lon, lat)
            for lon, lat in coords
        ) / len(coords)
        ranked.append(
            (
                avg_distance,
                StaySuggestion(
                    name=hotel.name,
                    address=hotel.address,
                    business_area=hotel.business_area,
                    stay_type=hotel.stay_type,
                    distance_m=hotel.distance_m,
                    avg_attraction_distance_m=round(avg_distance),
                    cost_amount=hotel.cost_amount,
                    rating=hotel.rating,
                ),
            )
        )

    ranked.sort(key=lambda pair: pair[0])
    items = [hotel for _, hotel in ranked[:5]]
    return StaySuggestionList(items=items, total=len(items))


@router.get("/plans/{plan_id}/days/{day_index}/map")
def plan_day_map(
    plan_id: int, day_index: int, db: Session = Depends(get_db)
) -> Response:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    days = (version.plan_json or {}).get("days") or []
    if day_index < 1 or day_index > len(days):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Day not found"
        )

    cache_key = (plan_id, day_index)
    if cache_key in _MAP_CACHE:
        return Response(
            content=_MAP_CACHE[cache_key],
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    points: list[tuple[float, float]] = []
    for item in days[day_index - 1].get("items") or []:
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if latitude is None or longitude is None:
            continue
        points.append(wgs84_to_gcj02(float(longitude), float(latitude)))

    if not points:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No coordinates available for this day",
        )

    try:
        image = fetch_static_map(points)
    except StaticMapError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"static map unavailable: {exc}",
        ) from exc

    if len(_MAP_CACHE) >= 128:
        _MAP_CACHE.clear()
    _MAP_CACHE[cache_key] = image
    return Response(
        content=image,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
