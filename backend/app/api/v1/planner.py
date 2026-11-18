from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.planners.models import PlanningCandidate, PlanningPreferences, TripPlan
from app.planners.multi_plan import generate_plan_options
from app.planners.trip import plan_trip
from app.schemas.planner import (
    CostBreakdownResponse,
    DayPlanResponse,
    PlannerOptionsResponse,
    PlannerPlanRequest,
    PlanOptionResponse,
    PlannedItemResponse,
    MealBlockResponse,
    RouteLegResponse,
    TransitSegmentResponse,
    TripPlanResponse,
    WeatherResponse,
)
from app.services.candidates import CityNotFoundError, candidates_for_city
from app.services.costs import CostBreakdown


router = APIRouter(prefix="/planner", tags=["planner"])


def load_planner_context(
    db: Session, payload: PlannerPlanRequest
) -> tuple[list[PlanningCandidate], PlanningPreferences]:
    """按目的地检索候选 POI 并组装偏好设置，三个端点共用。"""
    try:
        candidates = candidates_for_city(db, payload.city)
    except CityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no POI available for city: {payload.city}",
        )

    preferences = PlanningPreferences(
        # 接口使用 0–100 的滑动条刻度，规划器内部按 0–1 加权。
        interests={
            tag: weight / 100 for tag, weight in payload.interests.items()
        },
        budget_total=payload.budget_total,
        daily_start=payload.daily_start,
        daily_end=payload.daily_end,
        max_daily_items=payload.max_daily_items,
        avoid_tight_schedule=payload.avoid_tight_schedule,
        max_walk_km=payload.max_walk_km,
    )
    return candidates, preferences


def planning_notes(payload: PlannerPlanRequest, trip: TripPlan) -> list[str]:
    """如实列出当前没有接入、没有执行或需要用户确认的部分。"""
    notes: list[str] = []
    is_mock = any(
        (day.weather is not None and day.weather.source == "mock")
        or any(leg.source == "mock" for leg in day.legs)
        for day in trip.days
    )
    if is_mock:
        notes.append("当前使用 Mock 高德数据：路线/天气/餐厅/住宿未调用真实接口。")
    weather_days = sum(1 for day in trip.days if day.weather is not None)
    if weather_days == 0:
        notes.append("天气未知：未取得可靠预报，方案未按天气优化。")
    elif is_mock:
        notes.append("天气：Mock 晴天数据，未调用真实城市预报。")
    elif weather_days < len(trip.days):
        notes.append("部分日期天气未知：这些日期按中性评分，未声称已按天气优化。")
    else:
        notes.append("天气：已使用高德城市预报，超出预报范围的日期会标为未知。")

    legs = [leg for day in trip.days for leg in day.legs]
    if not legs:
        notes.append(
            "路线与步行距离：本次没有可计算的相邻路段，或尚未接入真实路线。"
        )
    else:
        failed = [leg for leg in legs if leg.status != "ok"]
        if is_mock:
            notes.append(f"路线：Mock 路线，共 {len(legs)} 段相邻路段，非真实路径/耗时。")
        else:
            notes.append(f"路线：已调用高德路线服务，共 {len(legs)} 段相邻路段。")
        if failed:
            notes.append(
                f"其中 {len(failed)} 段路线失败：距离/耗时为未知，"
                "排程使用了带标记的保守回退耗时。"
            )
    notes.append(
        "费用口径：已合计门票、市内交通、餐饮估算和住宿估算；"
        "门票票价未核验时不按 0 元确认，当前总费用不含门票。"
    )
    notes.append(
        "交通费用：公交票价和打车/骑行是估算值，已计入市内交通；"
        "实际支付以现场为准。"
    )
    adults = getattr(payload, "adults", 1)
    children = getattr(payload, "children", 0)
    if adults + children > 1:
        notes.append("门票尚未按同行人数放大：当前费用为单人门票参考值。")
    if payload.max_walk_km is not None:
        statuses = {day.walk_constraint for day in trip.days}
        if not legs:
            notes.append(
                f"每日最大步行距离（{payload.max_walk_km:g} km）："
                "本次没有相邻景点路段，未产生步行距离。"
            )
        elif "unknown" in statuses:
            notes.append(
                f"每日最大步行距离（{payload.max_walk_km:g} km）无法校验："
                "存在路线失败或缺少坐标。"
            )
        elif "violated" in statuses:
            notes.append(
                f"每日最大步行距离（{payload.max_walk_km:g} km）已被超出，"
                "方案不应视为满足该硬约束。"
            )
        elif is_mock:
            notes.append(
                f"每日最大步行距离（{payload.max_walk_km:g} km）"
                "按 Mock 路线累计，仅用于演示。"
            )
        else:
            notes.append(
                f"每日最大步行距离（{payload.max_walk_km:g} km）"
                "已按高德路线累计校验。"
            )
    if trip.budget_total <= 0:
        notes.append("未设置预算，不计算预算差额。")
    if trip.status == "partial":
        notes.append("部分日期没有可安排的景点：候选不足或当日闭馆。")
    elif trip.status == "empty":
        notes.append("没有可安排的景点：请调整日期、天数或目的地。")
    return notes


def trip_response(
    trip: TripPlan,
    city: str,
    source: str,
    notes: list[str],
    costs: CostBreakdown | None = None,
) -> TripPlanResponse:
    total = costs.total_estimated if costs is not None else trip.total_estimated_cost
    budget_total = costs.budget_total if costs is not None else trip.budget_total
    difference = (
        costs.budget_difference if costs is not None else trip.budget_difference
    )
    over_budget = budget_total > 0 and total > budget_total
    return TripPlanResponse(
        city=city,
        start_date=trip.start_date,
        days=[
            DayPlanResponse(
                travel_date=day.travel_date,
                items=[
                    PlannedItemResponse(**item.__dict__, order=index)
                    for index, item in enumerate(day.items, start=1)
                ],
                estimated_cost=day.estimated_cost,
                legs=[
                    RouteLegResponse(
                        **{
                            **leg.__dict__,
                            "segments": [
                                TransitSegmentResponse(**segment.__dict__)
                                for segment in leg.transit_segments
                            ],
                        }
                    )
                    for leg in day.legs
                ],
                weather=(
                    WeatherResponse(
                        status="known",
                        condition=day.weather.condition,
                        temperature_min=day.weather.temperature_min,
                        temperature_max=day.weather.temperature_max,
                        precipitation=day.weather.precipitation,
                        risk_level=day.weather.risk_level,
                        source=day.weather.source,
                    )
                    if day.weather is not None
                    else WeatherResponse(status="unknown")
                ),
                walk_km=day.walk_km,
                walk_constraint=day.walk_constraint,
                meals=[
                    MealBlockResponse(
                        meal_type=meal.meal_type,
                        start_time=meal.start_time,
                        end_time=meal.end_time,
                        duration_minutes=meal.duration_minutes,
                    )
                    for meal in day.meals
                ],
            )
            for day in trip.days
        ],
        total_estimated_cost=total,
        budget_total=budget_total,
        budget_difference=difference,
        over_budget=over_budget,
        status=trip.status,
        weather_known=trip.weather_known,
        notes=notes,
        source=source,
        costs=(
            CostBreakdownResponse(**costs.__dict__)
            if costs is not None
            else None
        ),
    )


@router.post("/generate", response_model=TripPlanResponse)
def generate_plan(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> TripPlanResponse:
    candidates, preferences = load_planner_context(db, payload)
    trip = plan_trip(payload.start_date, payload.days, candidates, preferences)
    return trip_response(
        trip,
        payload.city,
        "Rule-based multi-day planner",
        planning_notes(payload, trip),
    )


@router.post("/generate-options", response_model=PlannerOptionsResponse)
def generate_plan_options_endpoint(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> PlannerOptionsResponse:
    candidates, preferences = load_planner_context(db, payload)
    options = generate_plan_options(
        payload.start_date, payload.days, candidates, preferences
    )
    return PlannerOptionsResponse(
        plans=[
            PlanOptionResponse(
                **trip_response(
                    option.trip_plan,
                    payload.city,
                    "Rule-based multi-day planner",
                    planning_notes(payload, option.trip_plan),
                ).model_dump(),
                plan_id=option.plan_id,
                plan_type=option.plan_type,
                score=option.score,
            )
            for option in options
        ],
        source="Rule-based multi-day planner",
    )


@router.post("/replan", response_model=TripPlanResponse)
def replan(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> TripPlanResponse:
    candidates, preferences = load_planner_context(db, payload)
    trip = plan_trip(payload.start_date, payload.days, candidates, preferences)
    return trip_response(
        trip,
        payload.city,
        "Rule-based multi-day replan",
        planning_notes(payload, trip),
    )
