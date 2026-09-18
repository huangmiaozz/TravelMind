from datetime import date, datetime, timedelta

from app.planners.models import DayPlan, PlannedItem, PlanningCandidate, PlanningPreferences
from app.planners.opening_filter import is_closed_on, visit_window
from app.planners.scorer import rank_candidates


def generate_day_plan(
    travel_date: date,
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool = True,
) -> DayPlan:
    """按评分顺序把候选排进一天的时间表。

    两道开放时间约束（需求 §11.1 / §11.2）：

      1. **当日闭馆的候选直接跳过** —— 再高分也排不进去。
      2. **访问必须落在开放时段内** —— 开门前到达就等到开门；
         若闭馆前来不及走完则**不排**，而不是把结束时间截断硬塞进去。

    开放时间未知时两条都不生效（理由见 `opening_filter`），
    只在 ``PlannedItem.opening_known`` 上如实标注为 False。
    """
    ranked = rank_candidates(candidates, preferences, weather_suitable)
    current = datetime.combine(travel_date, preferences.daily_start)
    day_end = datetime.combine(travel_date, preferences.daily_end)
    items: list[PlannedItem] = []
    total_cost = 0.0

    for scored in ranked:
        # 条目数已达上限 —— 后面的候选只会机会更小，可以停止
        if len(items) >= preferences.max_daily_items:
            break

        candidate = scored.candidate

        # §11.2 当日明确闭馆
        if is_closed_on(candidate, travel_date):
            continue

        window = visit_window(candidate, travel_date)

        # §11.1 开门前到达就等到开门，而不是提前进馆
        start = current
        if (
            window.known
            and window.open_time is not None
            and start.time() < window.open_time
        ):
            start = datetime.combine(travel_date, window.open_time)

        end_time = start + timedelta(minutes=candidate.visit_minutes)

        # §11.1 闭馆前来不及走完 —— 不排，也不截断结束时间
        if (
            window.known
            and window.close_time is not None
            and end_time.time() > window.close_time
        ):
            continue

        if end_time > day_end:
            continue

        items.append(
            PlannedItem(
                poi_id=candidate.poi_id,
                name=candidate.name,
                start_time=start.time(),
                end_time=end_time.time(),
                estimated_cost=candidate.estimated_cost,
                score=scored.total_score,
                opening_known=window.known,
            )
        )
        total_cost += candidate.estimated_cost
        current = end_time + timedelta(
            minutes=30 if preferences.avoid_tight_schedule else 10
        )

    return DayPlan(travel_date=travel_date, items=items, estimated_cost=total_cost)
