from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.planners.generator import generate_day_plan
from app.planners.models import DayPlan, PlanningCandidate, PlanningPreferences
from app.planners.multi_plan import generate_plan_options
from app.schemas.planner import (
    DayPlanResponse,
    PlanOptionResponse,
    PlannerOptionsResponse,
    PlannerPlanRequest,
    PlannedItemResponse,
)
from app.services.candidates import CityNotFoundError, candidates_for_city


router = APIRouter(prefix="/planner", tags=["planner"])


def _load_context(
    db: Session, payload: PlannerPlanRequest
) -> tuple[list[PlanningCandidate], PlanningPreferences]:
    """按目的地检索候选 POI 并组装偏好设置，三个端点共用。"""
    try:
        candidates = candidates_for_city(db, payload.city)
    except CityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no POI available for city: {payload.city}",
        )

    preferences = PlanningPreferences(
        interests=payload.interests,
        budget_total=payload.budget_total,
        daily_start=payload.daily_start,
        daily_end=payload.daily_end,
        max_daily_items=payload.max_daily_items,
        avoid_tight_schedule=payload.avoid_tight_schedule,
        max_walk_km=payload.max_walk_km,
    )
    return candidates, preferences


def _to_response(plan: DayPlan, source: str) -> DayPlanResponse:
    return DayPlanResponse(
        travel_date=plan.travel_date,
        items=[PlannedItemResponse(**item.__dict__) for item in plan.items],
        estimated_cost=plan.estimated_cost,
        source=source,
    )


@router.post("/generate", response_model=DayPlanResponse)
def generate_plan(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> DayPlanResponse:
    candidates, preferences = _load_context(db, payload)
    plan = generate_day_plan(payload.travel_date, candidates, preferences)
    return _to_response(plan, "Rule-based weighted planner")


@router.post("/generate-options", response_model=PlannerOptionsResponse)
def generate_plan_options_endpoint(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> PlannerOptionsResponse:
    candidates, preferences = _load_context(db, payload)
    options = generate_plan_options(payload.travel_date, candidates, preferences)
    return PlannerOptionsResponse(
        plans=[
            PlanOptionResponse(
                plan_id=option.plan_id,
                plan_type=option.plan_type,
                score=option.score,
                travel_date=option.day_plan.travel_date,
                items=[
                    PlannedItemResponse(**item.__dict__)
                    for item in option.day_plan.items
                ],
                estimated_cost=option.day_plan.estimated_cost,
                source="Rule-based weighted planner",
            )
            for option in options
        ],
        source="Rule-based weighted planner",
    )


@router.post("/replan", response_model=DayPlanResponse)
def replan(
    payload: PlannerPlanRequest, db: Session = Depends(get_db)
) -> DayPlanResponse:
    candidates, preferences = _load_context(db, payload)
    plan = generate_day_plan(payload.travel_date, candidates, preferences)
    return _to_response(plan, "Rule-based replan")
