"""多日行程规划。

在单日排程之上补齐三件当前规划还缺的事：

  1. 按日期连续生成 N 天，而不是只排一天。
  2. 同一个景点不跨日重复安排；已在前面日期用掉的候选不再进入后续日期。
  3. 把逐日费用累加成整趟费用，并给出预算差额与超额标记。

预算仍是**软约束**：超预算不会删除任何一天或任何一个景点，
只会在整趟结果上体现为 ``over_budget`` 和负的 ``budget_difference``。
"""

from dataclasses import replace
from datetime import date, timedelta

from app.planners.generator import generate_day_plan
from app.planners.models import (
    DayPlan,
    PlanningCandidate,
    PlanningPreferences,
    PlanningWeather,
    TripPlan,
)
from app.planners.routing import RouteProvider

# 单次请求允许的最大旅行天数，避免一次请求排出不合理的超长行程。
MAX_TRIP_DAYS = 30


def plan_trip(
    start_date: date,
    days: int,
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool | None = None,
    *,
    weather_by_date: dict[date, PlanningWeather] | None = None,
    route_provider: RouteProvider | None = None,
    city: str | None = None,
    transport_preference: str = "auto",
) -> TripPlan:
    """生成连续 ``days`` 天的行程。

    每天都会在「尚未安排」的候选集合中重新排序，因此同一景点不会在两天
    都被推荐。若候选不足，后面的日期就是空行程，整趟状态相应标记为
    ``partial`` 或 ``empty``，而不是抛异常。

    每日候选评分使用「平均每日预算」作为参考（``total / days``），
    仅用于排序；整趟是否超预算只看累计费用，不要求每天花费相同。
    ``weather_suitable`` 为 None 表示天气未知，交给单日排程按中性处理。
    ``weather_by_date`` 与 ``route_provider`` 是 v0.3 接入点；缺省时保持旧行为。
    """
    if days < 1:
        raise ValueError("days must be at least 1")
    if days > MAX_TRIP_DAYS:
        raise ValueError(f"days must not exceed {MAX_TRIP_DAYS}")

    daily_reference_budget = (
        preferences.budget_total / days if preferences.budget_total > 0 else 0.0
    )
    day_preferences = replace(preferences, budget_total=daily_reference_budget)

    scheduled: set[int] = set()
    day_plans: list[DayPlan] = []

    for offset in range(days):
        travel_date = start_date + timedelta(days=offset)
        remaining = [
            candidate
            for candidate in candidates
            if candidate.poi_id not in scheduled
        ]
        day_plan = generate_day_plan(
            travel_date,
            remaining,
            day_preferences,
            weather_suitable,
            weather=(weather_by_date or {}).get(travel_date),
            route_provider=route_provider,
            city=city,
            transport_preference=transport_preference,
        )
        scheduled.update(item.poi_id for item in day_plan.items)
        day_plans.append(day_plan)

    total_cost = sum(day_plan.estimated_cost for day_plan in day_plans)
    filled_days = sum(1 for day_plan in day_plans if day_plan.items)
    if filled_days == 0:
        status = "empty"
    elif filled_days < days:
        status = "partial"
    else:
        status = "ok"

    if weather_by_date is None:
        weather_known = weather_suitable is not None
    else:
        weather_known = all(
            (start_date + timedelta(days=offset)) in weather_by_date
            for offset in range(days)
        )

    return TripPlan(
        start_date=start_date,
        days=day_plans,
        total_estimated_cost=total_cost,
        budget_total=preferences.budget_total,
        status=status,
        weather_known=weather_known,
    )
