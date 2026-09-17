from app.planners.models import CandidateScore, PlanningCandidate, PlanningPreferences


def score_candidate(
    candidate: PlanningCandidate,
    preferences: PlanningPreferences,
    weather_suitable: bool = True,
) -> CandidateScore:
    interest_score = sum(
        preferences.interests.get(tag, 0) * weight
        for tag, weight in candidate.interest_tags.items()
    )
    interest_score = min(1.0, interest_score)

    if preferences.budget_total <= 0:
        cost_score = 1.0
    else:
        cost_score = max(0.0, 1.0 - candidate.estimated_cost / preferences.budget_total)

    confidence_score = max(0.0, min(1.0, candidate.confidence))
    weather_score = 1.0 if weather_suitable or not candidate.weather_sensitive else 0.0
    total_score = (
        interest_score * 0.45
        + cost_score * 0.2
        + confidence_score * 0.2
        + weather_score * 0.15
    )
    return CandidateScore(
        candidate=candidate,
        interest_score=interest_score,
        cost_score=cost_score,
        confidence_score=confidence_score,
        weather_score=weather_score,
        total_score=total_score,
    )


def rank_candidates(
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool = True,
) -> list[CandidateScore]:
    ranked = [score_candidate(candidate, preferences, weather_suitable) for candidate in candidates]
    return sorted(ranked, key=lambda item: item.total_score, reverse=True)
