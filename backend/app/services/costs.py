"""整趟旅行的费用拆分。

当前只把“可计算的金额”相加；未知项不按 0 元确认，而是在 `unknown_items`
里列出，`budget_complete=False`。餐饮/住宿优先使用用户输入，否则使用城市
参考值；这些参考值是课程演示估算，不是官方实时价格。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.planners.models import TripPlan
from app.schemas.plan import PlanCreateRequest

# 课程演示用的城市级参考值，后续应由 CityCostProfile 核验替换。
CITY_COST_DEFAULTS = {
    "北京": {"meal": 150.0, "hotel": 500.0},
    "福州": {"meal": 100.0, "hotel": 300.0},
}


@dataclass(frozen=True)
class CostBreakdown:
    tickets_amount: float
    tickets_status: str
    transport_amount: float
    transport_status: str
    meals_amount: float
    meals_status: str
    lodging_amount: float
    lodging_status: str
    total_estimated: float
    budget_total: float
    budget_difference: float
    budget_complete: bool
    unknown_items: tuple[str, ...] = ()


def build_costs(
    trip: TripPlan, payload: PlanCreateRequest, city: str
) -> CostBreakdown:
    ticket_amount = round(
        sum(item.estimated_cost for day in trip.days for item in day.items), 2
    )
    ticket_status = "estimated" if ticket_amount > 0 else "unknown"

    transport_amount = 0.0
    transport_unknown = False
    for day in trip.days:
        for leg in day.legs:
            if leg.cost_amount is None:
                transport_unknown = True
            else:
                transport_amount += leg.cost_amount
    transport_status = "partial" if transport_unknown else "estimated"

    defaults = CITY_COST_DEFAULTS.get(city, {})
    meal_rate = payload.meal_budget_per_person_day
    if meal_rate is None:
        meal_rate = defaults.get("meal")
    meals_status = "estimated" if meal_rate is not None else "unknown"
    meals_amount = round(
        (meal_rate or 0) * payload.party_size * payload.days, 2
    )

    hotel_rate = payload.hotel_budget_per_room_night
    if hotel_rate is None:
        hotel_rate = defaults.get("hotel")
    lodging_status = "estimated" if hotel_rate is not None else "unknown"
    lodging_amount = round(
        (hotel_rate or 0) * payload.resolved_rooms * payload.resolved_nights, 2
    )

    total = round(
        ticket_amount + transport_amount + meals_amount + lodging_amount, 2
    )
    budget = round(payload.budget_total, 2)
    difference = round(budget - total, 2) if budget > 0 else 0.0

    unknown: list[str] = []
    if ticket_status == "unknown":
        unknown.append("门票票价未核验，未按 0 元确认")
    if transport_unknown:
        unknown.append("部分交通费用未知")
    if meals_status == "unknown":
        unknown.append("餐饮预算缺少城市参考值")
    if lodging_status == "unknown":
        unknown.append("住宿预算缺少城市参考值")

    return CostBreakdown(
        tickets_amount=ticket_amount,
        tickets_status=ticket_status,
        transport_amount=round(transport_amount, 2),
        transport_status=transport_status,
        meals_amount=meals_amount,
        meals_status=meals_status,
        lodging_amount=lodging_amount,
        lodging_status=lodging_status,
        total_estimated=total,
        budget_total=budget,
        budget_difference=difference,
        budget_complete=not unknown,
        unknown_items=tuple(unknown),
    )
