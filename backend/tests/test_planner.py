from datetime import date, time

from app.planners.generator import generate_day_plan
from app.planners.models import PlanningCandidate, PlanningPreferences
from app.planners.scorer import rank_candidates, score_candidate
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


def test_rank_candidates_treats_budget_as_a_soft_preference() -> None:
    preferences = PlanningPreferences(budget_total=100)
    candidates = [
        PlanningCandidate(1, "预算内景点", "scenic", {}, 100, 60, 0.9),
        PlanningCandidate(2, "超预算景点", "scenic", {}, 200, 60, 0.9),
    ]

    ranked = rank_candidates(candidates, preferences)
    scores_by_id = {item.candidate.poi_id: item for item in ranked}

    assert len(ranked) == 2
    assert scores_by_id[2].cost_score > 0
    assert scores_by_id[1].total_score > scores_by_id[2].total_score


def test_generate_day_plan_respects_time_and_item_limits() -> None:
    preferences = PlanningPreferences(
        interests={"history": 1.0},
        daily_start=time(9, 0),
        daily_end=time(17, 0),
        max_daily_items=2,
    )
    candidates = [
        PlanningCandidate(index, f"景点 {index}", "historical", {"history": 1.0}, 20, 90, 0.9)
        for index in range(1, 4)
    ]

    plan = generate_day_plan(date(2026, 10, 12), candidates, preferences)

    assert len(plan.items) == 2
    assert plan.items[0].start_time == time(9, 0)
    assert plan.items[-1].end_time <= time(17, 0)
    assert plan.estimated_cost == 40


def test_meal_blocks_are_reserved_and_not_overlapped() -> None:
    preferences = PlanningPreferences(
        interests={"history": 1.0},
        daily_start=time(9, 0),
        daily_end=time(20, 0),
        max_daily_items=3,
    )
    candidates = [
        PlanningCandidate(
            index,
            f"景点 {index}",
            "historical",
            {"history": 1.0},
            20,
            120,
            0.9,
        )
        for index in range(1, 5)
    ]

    plan = generate_day_plan(date(2026, 10, 12), candidates, preferences)

    assert [meal.meal_type for meal in plan.meals] == ["lunch", "dinner"]
    assert plan.meals[0].start_time == time(12, 0)
    assert plan.meals[0].end_time == time(14, 0)
    assert plan.meals[1].start_time == time(18, 0)
    assert plan.meals[1].end_time == time(19, 30)
    for item in plan.items:
        for meal in plan.meals:
            assert not (
                item.start_time < meal.end_time
                and item.end_time > meal.start_time
            )


def test_unknown_weather_scores_neutral_for_weather_sensitive_candidate() -> None:
    candidate = PlanningCandidate(
        1, "户外景点", "scenic", {}, 20, 60, 0.9, weather_sensitive=True
    )
    preferences = PlanningPreferences()

    unknown = score_candidate(candidate, preferences, None)
    suitable = score_candidate(candidate, preferences, True)
    unsuitable = score_candidate(candidate, preferences, False)

    assert unknown.weather_score == 0.5
    assert unsuitable.weather_score < unknown.weather_score < suitable.weather_score


def test_weather_unknown_does_not_affect_weather_insensitive_candidate() -> None:
    candidate = PlanningCandidate(1, "博物馆", "museum", {}, 20, 60, 0.9)
    preferences = PlanningPreferences()

    assert score_candidate(candidate, preferences, None).weather_score == 1.0


def test_generate_plan_options_returns_multi_day_strategies() -> None:
    preferences = PlanningPreferences(interests={"history": 1.0}, budget_total=100)
    candidates = [PlanningCandidate(1, "历史景点", "historical", {"history": 1.0}, 20, 60, 0.9)]

    options = generate_plan_options(date(2026, 10, 12), 2, candidates, preferences)

    assert {option.plan_type for option in options} == {
        "best_overall",
        "cheapest",
        "most_comfortable",
        "best_interest_match",
    }
    assert all(len(option.trip_plan.days) == 2 for option in options)
    assert [option.score for option in options] == sorted(
        (option.score for option in options), reverse=True
    )
