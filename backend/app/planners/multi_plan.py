from dataclasses import dataclass
from datetime import date

from app.planners.generator import generate_day_plan
from app.planners.models import DayPlan, PlanningCandidate, PlanningPreferences


@dataclass(frozen=True)
class PlanOption:
    plan_id: str
    plan_type: str
    score: float
    day_plan: DayPlan


def generate_plan_options(
    travel_date: date,
    candidates: list[PlanningCandidate],
    base_preferences: PlanningPreferences,
) -> list[PlanOption]:
    strategies = [
        ("best_overall", 0.45, 0.20),
        ("cheapest", 0.20, 0.60),
        ("most_comfortable", 0.30, 0.15),
        ("best_interest_match", 0.70, 0.10),
    ]
    options: list[PlanOption] = []
    for plan_type, interest_weight, cost_weight in strategies:
        preferences = PlanningPreferences(
            interests=base_preferences.interests,
            budget_total=base_preferences.budget_total,
            daily_start=base_preferences.daily_start,
            daily_end=base_preferences.daily_end,
            max_daily_items=max(1, base_preferences.max_daily_items - (1 if plan_type == "most_comfortable" else 0)),
            avoid_tight_schedule=plan_type == "most_comfortable" or base_preferences.avoid_tight_schedule,
        )
        day_plan = generate_day_plan(travel_date, candidates, preferences)
        interest_total = sum(item.score for item in day_plan.items)
        normalized_interest = interest_total / len(day_plan.items) if day_plan.items else 0
        cost_score = 1 / (1 + day_plan.estimated_cost)
        score = normalized_interest * interest_weight + cost_score * cost_weight
        options.append(PlanOption(plan_type, plan_type, score, day_plan))
    return sorted(options, key=lambda option: option.score, reverse=True)
