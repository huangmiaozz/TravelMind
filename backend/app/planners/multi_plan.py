"""多日方案组合。

对同一趟旅行用几组不同的兴趣/费用权重各排一次，供用户比较。
方案**数量与分类仍是临时的固定四类**，尚未按「由可行结果决定」的最终规则调整；
这是已知偏差，不是目标状态。
"""

from dataclasses import dataclass, replace
from datetime import date

from app.planners.models import PlanningCandidate, PlanningPreferences, TripPlan
from app.planners.trip import plan_trip

# (方案类型, 兴趣权重, 费用权重)
STRATEGIES: tuple[tuple[str, float, float], ...] = (
    ("best_overall", 0.45, 0.20),
    ("cheapest", 0.20, 0.60),
    ("most_comfortable", 0.30, 0.15),
    ("best_interest_match", 0.70, 0.10),
)


@dataclass(frozen=True)
class PlanOption:
    plan_id: str
    plan_type: str
    score: float
    trip_plan: TripPlan


def _trip_score(trip: TripPlan, interest_weight: float, cost_weight: float) -> float:
    """方案总分 = 条目平均分 × 兴趣权重 + 整趟费用分 × 费用权重。

    费用分按**整趟累计费用 / 整趟预算**计算，超预算会降低费用评价，
    但不会因此把方案从结果里删掉。
    """
    items = [item for day in trip.days for item in day.items]
    average_item_score = (
        sum(item.score for item in items) / len(items) if items else 0.0
    )
    if trip.budget_total <= 0:
        cost_score = 1.0
    else:
        cost_score = 1.0 / (1.0 + trip.total_estimated_cost / trip.budget_total)
    return average_item_score * interest_weight + cost_score * cost_weight


def generate_plan_options(
    start_date: date,
    days: int,
    candidates: list[PlanningCandidate],
    base_preferences: PlanningPreferences,
) -> list[PlanOption]:
    options: list[PlanOption] = []
    for plan_type, interest_weight, cost_weight in STRATEGIES:
        preferences = replace(
            base_preferences,
            max_daily_items=max(
                1,
                base_preferences.max_daily_items
                - (1 if plan_type == "most_comfortable" else 0),
            ),
            avoid_tight_schedule=(
                plan_type == "most_comfortable"
                or base_preferences.avoid_tight_schedule
            ),
        )
        trip_plan = plan_trip(start_date, days, candidates, preferences)
        options.append(
            PlanOption(
                plan_id=plan_type,
                plan_type=plan_type,
                score=_trip_score(trip_plan, interest_weight, cost_weight),
                trip_plan=trip_plan,
            )
        )
    return sorted(options, key=lambda option: option.score, reverse=True)
