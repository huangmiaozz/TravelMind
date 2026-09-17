from datetime import date, time

from app.planners.generator import generate_day_plan
from app.planners.models import PlanningCandidate, PlanningPreferences
from app.planners.scorer import rank_candidates
from app.planners.multi_plan import generate_plan_options


def test_rank_candidates_prefers_matching_interest() -> None:
    preferences = PlanningPreferences(interests={"history": 1.0})
    candidates = [
        PlanningCandidate(1, "历史景点", "historical", {"history": 1.0}, 60, 120, 0.95),
        PlanningCandidate(2, "购物中心", "shopping", {"shopping": 1.0}, 60, 120, 0.95),
    ]

    ranked = rank_candidates(candidates, preferences)

    assert ranked[0].candidate.poi_id == 1
    assert ranked[0].interest_score > ranked[1].interest_score


def test_generate_day_plan_respects_time_and_item_limits() -> None:
    preferences = PlanningPreferences(
        interests={"history": 1.0},
        daily_start=time(9, 0),
        daily_end=time(13, 0),
        max_daily_items=2,
    )
    candidates = [
        PlanningCandidate(index, f"景点 {index}", "historical", {"history": 1.0}, 20, 90, 0.9)
        for index in range(1, 4)
    ]

    plan = generate_day_plan(date(2026, 10, 12), candidates, preferences)

    assert len(plan.items) == 2
    assert plan.items[0].start_time == time(9, 0)
    assert plan.items[-1].end_time <= time(13, 0)
    assert plan.estimated_cost == 40


def test_generate_plan_options_returns_multiple_strategies() -> None:
    preferences = PlanningPreferences(interests={"history": 1.0}, budget_total=100)
    candidates = [PlanningCandidate(1, "历史景点", "historical", {"history": 1.0}, 20, 60, 0.9)]

    options = generate_plan_options(date(2026, 10, 12), candidates, preferences)

    assert {option.plan_type for option in options} == {
        "best_overall",
        "cheapest",
        "most_comfortable",
        "best_interest_match",
    }
