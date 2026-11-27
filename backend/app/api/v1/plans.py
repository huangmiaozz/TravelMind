from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import date
from statistics import median

from app.api.v1.planner import (
    load_planner_context,
    planning_notes,
    trip_response,
)
from app.db.session import get_db
from app.models.trip import PlanVersion, Trip
from app.planners.trip import plan_trip
from app.schemas.plan import (
    MealAreaList,
    MealAreaSuggestion,
    MealSuggestion,
    MealSuggestionList,
    PlanCreateRequest,
    PlanDetail,
    PlanSelections,
    PlanVersionList,
    PlanVersionSummary,
    StaySuggestion,
    StaySuggestionList,
)
from app.services.costs import build_costs
from app.services.dining_areas import get_area
from app.services.hotel_recommendations import (
    passes_quality,
    pick_diverse,
    score_hotel,
)
from app.services.meal_recommendations import (
    area_candidates,
    area_restaurants,
    meal_anchor,
    meal_budget,
    nearby_restaurants,
    search_area_restaurants,
    search_nearby_restaurants,
)
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
from app.services.coordinates import wgs84_to_gcj02
from app.services.rollinggo import RollingGoHotelClient
from app.services.selection_costs import recalculate_selection_costs
from app.services.static_map import StaticMapError, fetch_static_map


router = APIRouter(tags=["plans"])

# 方案生成后 plan_json 不再变化，按 (plan_id, day_index) 缓存静态图即可。
_MAP_CACHE: dict[tuple[int, int], bytes] = {}
_rollinggo = RollingGoHotelClient()


def _enrich_stay_prices(
    items: list[StaySuggestion], version: PlanVersion
) -> list[StaySuggestion]:
    """用 RollingGo 补酒店实时价；失败/名称不匹配时保留 unknown。"""
    if not items or not _rollinggo.configured:
        return items
    check_in = version.start_date
    if check_in < date.today():
        # RollingGo 对过去日期可能回退到未来默认日期，不能拿它冒充本方案房价。
        return items
    request = version.request_json or {}
    nights = max(1, int(request.get("nights") or (version.days_count - 1) or 1))
    adults = max(1, int(request.get("adults") or 1))
    children = max(0, int(request.get("children") or 0))
    rooms = max(1, int(request.get("rooms") or 1))
    hotel_budget = request.get("hotel_budget_per_room_night")
    budget = float(hotel_budget) if hotel_budget is not None else None
    enriched: list[StaySuggestion] = []
    for item in items:
        try:
            price = _rollinggo.price_for_hotel(
                item.name,
                address=item.address,
                check_in=check_in,
                nights=nights,
                adults=adults,
                children=children,
                rooms=rooms,
            )
        except Exception:
            price = None
        if price is None:
            enriched.append(item)
            continue
        enriched.append(
            item.model_copy(
                update={
                    "cost_amount": price.amount,
                    "over_budget": (
                        price.amount is not None
                        and budget is not None
                        and price.amount > budget
                    ),
                    "price_status": price.status,
                    "price_source": price.source,
                    "price_checked_at": price.checked_at,
                    "price_note": price.note,
                }
            )
        )
    return enriched


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


@router.post(
    "/plans/{plan_id}/costs/recalculate",
    response_model=PlanDetail,
)
def recalculate_costs(plan_id: int, db: Session = Depends(get_db)) -> PlanDetail:
    """按已选餐厅/酒店重算费用，并把结果挂到当前版本的 selection_json。"""
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    costs = recalculate_selection_costs(version)
    selection = dict(version.selection_json or {})
    selection["costs"] = costs.model_dump(mode="json")
    selection["totals"] = {
        "total_estimated_cost": costs.total_estimated,
        "budget_difference": costs.budget_difference,
        "over_budget": (
            costs.budget_total > 0 and costs.total_estimated > costs.budget_total
        ),
    }
    version.selection_json = selection
    db.commit()
    db.refresh(version)
    return version_detail(version)


@router.get(
    "/plans/{plan_id}/selections",
    response_model=PlanSelections,
)
def get_plan_selections(
    plan_id: int, db: Session = Depends(get_db)
) -> PlanSelections:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    return PlanSelections(**(version.selection_json or {}))


@router.put(
    "/plans/{plan_id}/selections",
    response_model=PlanSelections,
)
def save_plan_selections(
    plan_id: int,
    payload: PlanSelections,
    db: Session = Depends(get_db),
) -> PlanSelections:
    version = db.get(PlanVersion, plan_id)
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan version not found"
        )
    version.selection_json = payload.model_dump(mode="json")
    db.commit()
    db.refresh(version)
    return payload


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas",
    response_model=MealAreaList,
)
def meal_areas(
    plan_id: int,
    day_index: int,
    meal_type: str,
    db: Session = Depends(get_db),
    provider: CachedAmapProvider | None = Depends(get_planning_provider),
) -> MealAreaList:
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
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )
    try:
        anchor, next_item = meal_anchor(days[day_index - 1], meal_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    candidates, total, travel_budget, min_eat = area_candidates(
        provider,
        version.plan_json.get("city", ""),
        anchor,
        next_item,
        meal_type,
    )
    return MealAreaList(
        items=[
            MealAreaSuggestion(
                id=item.area.id,
                name=item.area.name,
                popularity=item.area.popularity,
                travel_minutes=item.travel_minutes,
                note="含区域步行 5 分钟",
                area_type=item.area.area_type,
                weather_friendly=item.area.weather_friendly,
            )
            for item in candidates
        ],
        meal_budget_minutes=total,
        travel_budget_minutes=travel_budget,
        min_eat_minutes=min_eat,
        total=len(candidates),
    )


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas/{area_id}/restaurants",
    response_model=MealSuggestionList,
)
def meal_area_restaurants(
    plan_id: int,
    day_index: int,
    meal_type: str,
    area_id: str,
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
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )
    area = get_area(version.plan_json.get("city", ""), area_id)
    if area is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dining area not found"
        )
    restaurants = area_restaurants(
        provider, area, version.plan_json.get("city", "")
    )
    return MealSuggestionList(
        items=[
            MealSuggestion(
                name=item.name,
                address=item.address,
                distance_m=item.distance_m,
                cost_amount=item.cost_amount,
                rating=item.rating,
                area_id=area.id,
                area_name=area.name,
                quality_tag=item.quality_tag,
            )
            for item in restaurants
        ],
        total=len(restaurants),
    )


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas/{area_id}/restaurants/search",
    response_model=MealSuggestionList,
)
def search_meal_area_restaurants(
    plan_id: int,
    day_index: int,
    meal_type: str,
    area_id: str,
    q: str = Query(min_length=1, max_length=50),
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
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )
    area = get_area(version.plan_json.get("city", ""), area_id)
    if area is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dining area not found"
        )
    restaurants = search_area_restaurants(
        provider,
        area,
        version.plan_json.get("city", ""),
        q,
    )
    return MealSuggestionList(
        items=[
            MealSuggestion(
                name=item.name,
                address=item.address,
                distance_m=item.distance_m,
                cost_amount=item.cost_amount,
                rating=item.rating,
                area_id=area.id,
                area_name=area.name,
                quality_tag=item.quality_tag,
            )
            for item in restaurants
        ],
        total=len(restaurants),
    )


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/nearby",
    response_model=MealSuggestionList,
)
def meal_nearby(
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
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )
    try:
        anchor, _ = meal_anchor(days[day_index - 1], meal_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    restaurants = nearby_restaurants(
        provider,
        version.plan_json.get("city", ""),
        anchor,
        meal_type,
    )
    return MealSuggestionList(
        items=[
            MealSuggestion(
                name=item.name,
                address=item.address,
                distance_m=item.distance_m,
                cost_amount=item.cost_amount,
                rating=item.rating,
                travel_minutes=travel,
                quality_tag=item.quality_tag,
            )
            for item, travel in restaurants
        ],
        total=len(restaurants),
    )


@router.get(
    "/plans/{plan_id}/days/{day_index}/meals/{meal_type}/nearby/search",
    response_model=MealSuggestionList,
)
def search_meal_nearby(
    plan_id: int,
    day_index: int,
    meal_type: str,
    q: str = Query(min_length=1, max_length=50),
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
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Amap provider is not configured",
        )
    try:
        anchor, _ = meal_anchor(days[day_index - 1], meal_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    restaurants = search_nearby_restaurants(
        provider,
        version.plan_json.get("city", ""),
        anchor,
        meal_type,
        q,
    )
    return MealSuggestionList(
        items=[
            MealSuggestion(
                name=item.name,
                address=item.address,
                distance_m=item.distance_m,
                cost_amount=item.cost_amount,
                rating=item.rating,
                travel_minutes=travel,
                quality_tag=item.quality_tag,
            )
            for item, travel in restaurants
        ],
        total=len(restaurants),
    )


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

    day_items: list[list[tuple[float, float, str]]] = []
    for day in version.plan_json.get("days") or []:
        items: list[tuple[float, float, str]] = []
        for item in day.get("items") or []:
            if item.get("longitude") is None or item.get("latitude") is None:
                continue
            items.append(
                (
                    float(item["longitude"]),
                    float(item["latitude"]),
                    str(item.get("name") or ""),
                )
            )
        if items:
            day_items.append(items)
    coords = [(lon, lat) for items in day_items for lon, lat, _ in items]
    if not coords:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attraction coordinates for stay suggestions",
        )

    # 中位数比平均值更稳：八达岭这种远端景点不会把搜索中心拖到郊区。
    center_lon = median(point[0] for point in coords)
    center_lat = median(point[1] for point in coords)
    hotels = provider.nearby_hotels(
        wgs84_to_gcj02(center_lon, center_lat),
        version.plan_json.get("city", ""),
        radius=5000,
        limit=25,
        sortrule="weight",
    )

    scored = [
        value
        for hotel in hotels
        if (value := score_hotel(hotel, day_items)) is not None
    ]
    hotel_budget = (version.request_json or {}).get(
        "hotel_budget_per_room_night"
    )
    filtered = [
        value
        for value in scored
        if passes_quality(value.hotel, hotel_budget)
    ]
    # 字段缺失时不把整页清空：先尝试质量过滤，没有结果再回退。
    preferred_tier = [value for value in filtered if value.tier != "经济型"]
    ranked = preferred_tier if len(preferred_tier) >= 3 else filtered
    if not ranked:
        ranked = scored
    ranked.sort(key=lambda item: item.score)
    ranked = pick_diverse(ranked[:20], limit=5, per_area=2)
    items = [
        StaySuggestion(
            name=scored.hotel.name,
            address=scored.hotel.address,
            business_area=scored.hotel.business_area,
            stay_type=scored.hotel.stay_type,
            distance_m=scored.hotel.distance_m,
            avg_commute_minutes=scored.avg_commute_minutes,
            max_commute_minutes=scored.max_commute_minutes,
            day_commutes=list(scored.day_commutes),
            tier=scored.tier,
            cost_amount=scored.hotel.cost_amount,
            rating=scored.hotel.rating,
        )
        for scored in ranked[:5]
    ]
    items = _enrich_stay_prices(items, version)
    return StaySuggestionList(items=items, total=len(items))


@router.get(
    "/plans/{plan_id}/stays/search",
    response_model=StaySuggestionList,
)
def search_stays(
    plan_id: int,
    q: str = Query(min_length=1, max_length=50),
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
    day_items: list[list[tuple[float, float, str]]] = []
    for day in version.plan_json.get("days") or []:
        items: list[tuple[float, float, str]] = []
        for item in day.get("items") or []:
            if item.get("longitude") is None or item.get("latitude") is None:
                continue
            items.append(
                (
                    float(item["longitude"]),
                    float(item["latitude"]),
                    str(item.get("name") or ""),
                )
            )
        if items:
            day_items.append(items)
    if not day_items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No attraction coordinates for stay search",
        )

    hotels = provider.search_hotels(
        q, version.plan_json.get("city", ""), limit=10
    )
    scored = [
        value
        for hotel in hotels
        if (value := score_hotel(hotel, day_items)) is not None
    ]
    scored.sort(key=lambda item: item.score)
    items = [
        StaySuggestion(
            name=value.hotel.name,
            address=value.hotel.address,
            business_area=value.hotel.business_area,
            stay_type=value.hotel.stay_type,
            distance_m=value.hotel.distance_m,
            avg_commute_minutes=value.avg_commute_minutes,
            max_commute_minutes=value.max_commute_minutes,
            day_commutes=list(value.day_commutes),
            tier=value.tier,
            cost_amount=value.hotel.cost_amount,
            rating=value.hotel.rating,
        )
        for value in scored[:8]
    ]
    items = _enrich_stay_prices(items, version)
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
