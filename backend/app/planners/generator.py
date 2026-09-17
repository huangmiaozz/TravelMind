from datetime import date, datetime, timedelta

from app.planners.models import DayPlan, PlannedItem, PlanningCandidate, PlanningPreferences
from app.planners.scorer import rank_candidates


def generate_day_plan(
    travel_date: date,
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool = True,
) -> DayPlan:
    ranked = rank_candidates(candidates, preferences, weather_suitable)
    current = datetime.combine(travel_date, preferences.daily_start)
    end = datetime.combine(travel_date, preferences.daily_end)
    items: list[PlannedItem] = []
    total_cost = 0.0

    for scored in ranked:
        candidate = scored.candidate
        next_time = current + timedelta(minutes=candidate.visit_minutes)
        if len(items) >= preferences.max_daily_items or next_time > end:
            continue
        items.append(
            PlannedItem(
                poi_id=candidate.poi_id,
                name=candidate.name,
                start_time=current.time(),
                end_time=next_time.time(),
                estimated_cost=candidate.estimated_cost,
                score=scored.total_score,
            )
        )
        total_cost += candidate.estimated_cost
        current = next_time + timedelta(minutes=30 if preferences.avoid_tight_schedule else 10)

    return DayPlan(travel_date=travel_date, items=items, estimated_cost=total_cost)
