from fastapi import APIRouter

from app.planners.generator import generate_day_plan
from app.planners.multi_plan import generate_plan_options
from app.planners.models import PlanningCandidate, PlanningPreferences
from app.schemas.planner import (
    DayPlanResponse,
    PlanOptionResponse,
    PlannerGenerateRequest,
    PlannerOptionsResponse,
    PlannedItemResponse,
)


router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/generate", response_model=DayPlanResponse)
def generate_plan(payload: PlannerGenerateRequest) -> DayPlanResponse:
    preferences = PlanningPreferences(
        interests=payload.interests,
        budget_total=payload.budget_total,
        daily_start=payload.daily_start,
        daily_end=payload.daily_end,
        max_daily_items=payload.max_daily_items,
        avoid_tight_schedule=payload.avoid_tight_schedule,
    )
    candidates = [PlanningCandidate(**candidate.model_dump()) for candidate in payload.candidates]
    plan = generate_day_plan(payload.travel_date, candidates, preferences)
    return DayPlanResponse(
        travel_date=plan.travel_date,
        items=[PlannedItemResponse(**item.__dict__) for item in plan.items],
        estimated_cost=plan.estimated_cost,
        source="Rule-based weighted planner",
    )


@router.post("/generate-options", response_model=PlannerOptionsResponse)
def generate_plan_options_endpoint(payload: PlannerGenerateRequest) -> PlannerOptionsResponse:
    preferences = PlanningPreferences(
        interests=payload.interests,
        budget_total=payload.budget_total,
        daily_start=payload.daily_start,
        daily_end=payload.daily_end,
        max_daily_items=payload.max_daily_items,
        avoid_tight_schedule=payload.avoid_tight_schedule,
    )
    candidates = [PlanningCandidate(**candidate.model_dump()) for candidate in payload.candidates]
    options = generate_plan_options(payload.travel_date, candidates, preferences)
    return PlannerOptionsResponse(
        plans=[
            PlanOptionResponse(
                plan_id=option.plan_id,
                plan_type=option.plan_type,
                score=option.score,
                travel_date=option.day_plan.travel_date,
                items=[PlannedItemResponse(**item.__dict__) for item in option.day_plan.items],
                estimated_cost=option.day_plan.estimated_cost,
                source="Rule-based weighted planner",
            )
            for option in options
        ],
        source="Rule-based weighted planner",
    )


@router.post("/replan", response_model=DayPlanResponse)
def replan(payload: PlannerGenerateRequest) -> DayPlanResponse:
    result = generate_plan(payload)
    result.source = "Rule-based replan"
    return result
