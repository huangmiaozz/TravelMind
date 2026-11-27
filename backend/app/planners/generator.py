from datetime import date, datetime, time, timedelta

from app.planners.models import (
    DayPlan,
    MealBlock,
    PlannedItem,
    PlannedLeg,
    PlanningCandidate,
    PlanningPreferences,
    PlanningWeather,
)
from app.planners.opening_filter import is_closed_on, visit_window
from app.planners.routing import RouteProvider
from app.planners.scorer import rank_candidates
from app.planners.transport_selector import (
    TransportOption,
    build_transport_options,
    enrich_transit_walk_segments,
)

# 所有候选路线都失败时，为继续排程使用的保守回退耗时。它不是真实路线。
FALLBACK_LEG_SECONDS = 15 * 60

# 固定用餐窗口；午餐 120 分钟包含去餐厅、用餐和返回/去下一景点。
LUNCH_START = time(12, 0)
LUNCH_END = time(14, 0)
DINNER_START = time(18, 0)
DINNER_END = time(19, 30)


def _meal_blocks(travel_date: date, day_start: datetime, day_end: datetime) -> list[MealBlock]:
    blocks: list[MealBlock] = []
    for meal_type, start, end in (
        ("lunch", LUNCH_START, LUNCH_END),
        ("dinner", DINNER_START, DINNER_END),
    ):
        start_dt = datetime.combine(travel_date, start)
        end_dt = datetime.combine(travel_date, end)
        if start_dt >= day_start and end_dt <= day_end:
            blocks.append(
                MealBlock(
                    meal_type=meal_type,
                    start_time=start,
                    end_time=end,
                    duration_minutes=int((end_dt - start_dt).total_seconds() // 60),
                )
            )
    return blocks


def _shift_out_of_meals(
    start: datetime,
    end: datetime,
    travel_date: date,
    meals: list[MealBlock],
) -> tuple[datetime, datetime]:
    """景点访问不能和用餐时间重叠；重叠时整体顺延到用餐结束。"""
    duration = end - start
    for meal in meals:
        meal_start = datetime.combine(travel_date, meal.start_time)
        meal_end = datetime.combine(travel_date, meal.end_time)
        if start < meal_end and end > meal_start:
            start = meal_end
            end = start + duration
    return start, end


def _fit_visit(
    travel_date: date,
    candidate: PlanningCandidate,
    arrival: datetime,
    day_end: datetime,
    meals: list[MealBlock],
) -> tuple[datetime, datetime, object] | None:
    """把到达时间放进开放窗口和用餐窗口；放不下返回 None。"""
    window = visit_window(candidate, travel_date)
    start = arrival
    if (
        window.known
        and window.open_time is not None
        and start.time() < window.open_time
    ):
        start = datetime.combine(travel_date, window.open_time)

    end_time = start + timedelta(minutes=candidate.visit_minutes)
    start, end_time = _shift_out_of_meals(
        start, end_time, travel_date, meals
    )
    if (
        window.known
        and window.close_time is not None
        and end_time.time() > window.close_time
    ):
        return None
    if end_time > day_end:
        return None
    return start, end_time, window


def generate_day_plan(
    travel_date: date,
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool | None = None,
    *,
    weather: PlanningWeather | None = None,
    route_provider: RouteProvider | None = None,
    city: str | None = None,
    transport_preference: str = "auto",
) -> DayPlan:
    """按评分顺序把候选排进一天的时间表。

    交通方式由 `transport_selector` 给出候选并按评分排序；本函数只负责
    逐条尝试，检查当天时间窗和累计步行上限，选第一条真正可行的。

    ``weather`` 为 None 表示天气未知，评分按中性处理，不能把未知天气当作适宜。
    ``route_provider`` 为 None 时保持旧行为：不查询路线、不计算步行距离。
    """
    suitability = weather_suitable
    if suitability is None and weather is not None:
        suitability = weather.suitable

    ranked = rank_candidates(candidates, preferences, suitability)
    current = datetime.combine(travel_date, preferences.daily_start)
    day_end = datetime.combine(travel_date, preferences.daily_end)
    meals = _meal_blocks(travel_date, current, day_end)
    max_walk_m = (
        preferences.max_walk_km * 1000
        if preferences.max_walk_km is not None
        else None
    )

    items: list[PlannedItem] = []
    legs: list[PlannedLeg] = []
    total_cost = 0.0
    walk_m = 0.0
    walk_unknown = route_provider is None
    previous: PlanningCandidate | None = None

    for scored in ranked:
        if len(items) >= preferences.max_daily_items:
            break

        candidate = scored.candidate
        if is_closed_on(candidate, travel_date):
            continue

        options: list[TransportOption] = []
        can_route = (
            previous is not None
            and route_provider is not None
            and previous.latitude is not None
            and previous.longitude is not None
            and candidate.latitude is not None
            and candidate.longitude is not None
        )
        if can_route:
            options = build_transport_options(
                route_provider,
                (previous.longitude, previous.latitude),
                (candidate.longitude, candidate.latitude),
                preference=transport_preference,
                weather=weather,
                city=city,
                daily_budget=preferences.budget_total,
                max_walk_m=max_walk_m,
                origin_name=getattr(previous, "name", None),
                destination_name=getattr(candidate, "name", None),
            )

        selected: TransportOption | None = None
        fitted = None
        fallback_used = False

        if previous is not None and route_provider is not None:
            for option in options:
                if option.status != "ok" or option.duration_s is None:
                    continue
                walking_m = option.walking_distance_m
                if (
                    max_walk_m is not None
                    and walking_m is not None
                    and walk_m + walking_m > max_walk_m
                ):
                    continue
                arrival = current + timedelta(seconds=option.duration_s)
                fitted = _fit_visit(travel_date, candidate, arrival, day_end, meals)
                if fitted is not None:
                    selected = option
                    break

            # 所有方式都查不到：允许带标记的保守回退，但绝不伪造距离。
            if selected is None and not options:
                arrival = current + timedelta(seconds=FALLBACK_LEG_SECONDS)
                fitted = _fit_visit(travel_date, candidate, arrival, day_end, meals)
                fallback_used = fitted is not None
            elif selected is None:
                # 有路线，但都超出步行/时间约束：换下一个候选景点。
                continue
        else:
            # 当天第一个景点，或没有路线服务：不产生交通段。
            fitted = _fit_visit(travel_date, candidate, current, day_end, meals)

        if fitted is None:
            continue

        start, end_time, window = fitted
        leg: PlannedLeg | None = None
        if fallback_used:
            leg = PlannedLeg(
                from_poi_id=previous.poi_id if previous else candidate.poi_id,
                to_poi_id=candidate.poi_id,
                mode="walk" if transport_preference == "auto" else transport_preference,
                distance_m=None,
                duration_s=None,
                walking_distance_m=None,
                status="failed",
                is_estimate=True,
                fallback_duration_s=FALLBACK_LEG_SECONDS,
                error="all route queries failed",
                reason="路线不可用，使用保守回退耗时",
            )
            walk_unknown = True
        elif selected is not None:
            transit_segments = selected.segments
            if selected.mode == "transit" and route_provider is not None:
                transit_segments = enrich_transit_walk_segments(
                    route_provider, selected.segments, city=city
                )
            leg = PlannedLeg(
                from_poi_id=previous.poi_id if previous else candidate.poi_id,
                to_poi_id=candidate.poi_id,
                mode=selected.mode,
                distance_m=selected.distance_m,
                duration_s=selected.duration_s,
                walking_distance_m=selected.walking_distance_m,
                status=selected.status,
                source=selected.source,
                is_estimate=selected.is_estimate,
                error=selected.error,
                cost_amount=selected.cost_amount,
                cost_basis=selected.cost_basis,
                reason=selected.reason,
                transit_segments=transit_segments,
                walk_duration_s=selected.walk_duration_s,
                bike_duration_s=selected.bike_duration_s,
                bike_cost_amount=selected.bike_cost_amount,
            )
            if selected.walking_distance_m is None:
                walk_unknown = True
            else:
                walk_m += selected.walking_distance_m

        items.append(
            PlannedItem(
                poi_id=candidate.poi_id,
                name=candidate.name,
                start_time=start.time(),
                end_time=end_time.time(),
                estimated_cost=candidate.estimated_cost,
                score=scored.total_score,
                opening_known=window.known,
                opening_status=candidate.opening_status,
                ticket_price=(
                    candidate.ticket_price
                    if candidate.ticket_price is not None
                    else (candidate.estimated_cost or None)
                ),
                ticket_child_price=candidate.ticket_child_price,
                ticket_status=(
                    candidate.ticket_status
                    if candidate.ticket_price is not None
                    else ("estimated" if candidate.estimated_cost > 0 else "unknown")
                ),
                ticket_source=candidate.ticket_source,
                ticket_source_url=candidate.ticket_source_url,
                ticket_verified_at=candidate.ticket_verified_at,
                latitude=candidate.latitude,
                longitude=candidate.longitude,
            )
        )
        if leg is not None:
            legs.append(leg)
        previous = candidate
        total_cost += candidate.estimated_cost
        current = end_time + timedelta(
            minutes=30 if preferences.avoid_tight_schedule else 10
        )

    if max_walk_m is None:
        walk_constraint = "not_set"
    elif walk_unknown:
        walk_constraint = "unknown"
    elif walk_m > max_walk_m:
        walk_constraint = "violated"
    else:
        walk_constraint = "satisfied"

    walk_km = None
    if route_provider is not None and not walk_unknown:
        walk_km = round(walk_m / 1000, 2)

    return DayPlan(
        travel_date=travel_date,
        items=items,
        estimated_cost=total_cost,
        legs=legs,
        weather=weather,
        walk_km=walk_km,
        walk_constraint=walk_constraint,
        meals=meals if items else [],
    )
