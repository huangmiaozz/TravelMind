from app.planners.models import CandidateScore, PlanningCandidate, PlanningPreferences


def weather_component(
    candidate: PlanningCandidate, weather_suitable: bool | None
) -> float:
    """天气适宜性得分。

    ``weather_suitable is None`` 表示**天气未知**（尚未接入天气服务）。
    此时对天气敏感的景点给中性分 0.5，既不当成适宜（1.0）也不当成不适宜（0.0），
    避免在没有任何天气数据时声称已经按天气优化。
    """
    if not candidate.weather_sensitive:
        return 1.0
    if weather_suitable is None:
        return 0.5
    return 1.0 if weather_suitable else 0.0


def score_candidate(
    candidate: PlanningCandidate,
    preferences: PlanningPreferences,
    weather_suitable: bool | None = None,
) -> CandidateScore:
    interest_score = sum(
        preferences.interests.get(tag, 0) * weight
        for tag, weight in candidate.interest_tags.items()
    )
    interest_score = min(1.0, interest_score)

    if preferences.budget_total <= 0:
        cost_score = 1.0
    else:
        cost_score = 1.0 / (
            1.0 + candidate.estimated_cost / preferences.budget_total
        )

    confidence_score = max(0.0, min(1.0, candidate.confidence))
    suitability = weather_component(candidate, weather_suitable)
    total_score = (
        interest_score * 0.45
        + cost_score * 0.2
        + confidence_score * 0.2
        + suitability * 0.15
    )
    return CandidateScore(
        candidate=candidate,
        interest_score=interest_score,
        cost_score=cost_score,
        confidence_score=confidence_score,
        weather_score=suitability,
        total_score=total_score,
    )


def rank_candidates(
    candidates: list[PlanningCandidate],
    preferences: PlanningPreferences,
    weather_suitable: bool | None = None,
) -> list[CandidateScore]:
    ranked = [
        score_candidate(candidate, preferences, weather_suitable)
        for candidate in candidates
    ]
    return sorted(ranked, key=lambda item: item.total_score, reverse=True)
