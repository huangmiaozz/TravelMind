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
    tickets_confirmed_amount: float
    tickets_estimated_amount: float
    tickets_unknown_count: int
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
    ticket_confirmed = 0.0
    ticket_estimated = 0.0
    ticket_unknown = 0
    ticket_unknown_names: list[str] = []
    child_price_assumed = False
    ticket_confirmed_count = 0
    ticket_estimated_count = 0

    for day in trip.days:
        for item in day.items:
            price = item.ticket_price
            if price is None or item.ticket_status == "unknown":
                ticket_unknown += 1
                ticket_unknown_names.append(item.name)
                continue
            amount = price * payload.adults
            child_price = item.ticket_child_price
            item_child_assumed = False
            if payload.children:
                if child_price is None:
                    # 没有儿童票时按成人价保守估算，并在状态下标“估算”；
                    # 免费景点不需要再提示儿童票价缺失。
                    child_price = price
                    if price > 0:
                        child_price_assumed = True
                        item_child_assumed = True
                amount += child_price * payload.children
            if item.ticket_status == "confirmed" and not item_child_assumed:
                ticket_confirmed += amount
                ticket_confirmed_count += 1
            else:
                ticket_estimated += amount
                ticket_estimated_count += 1

    ticket_amount = round(ticket_confirmed + ticket_estimated, 2)
    if ticket_unknown:
        tickets_status = (
            "partial"
            if (ticket_confirmed_count or ticket_estimated_count)
            else "unknown"
        )
    elif ticket_estimated_count or child_price_assumed:
        tickets_status = "estimated"
    elif ticket_confirmed_count:
        tickets_status = "confirmed"
    else:
        tickets_status = "unknown"

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
    if ticket_unknown:
        names = "、".join(ticket_unknown_names[:5])
        suffix = f"（{names}）" if names else ""
        unknown.append(f"门票票价未核验，未按 0 元确认{suffix}")
    if child_price_assumed:
        unknown.append("儿童票价未核验，已按成人价估算")
    if transport_unknown:
        unknown.append("部分交通费用未知")
    if meals_status == "unknown":
        unknown.append("餐饮预算缺少城市参考值")
    if lodging_status == "unknown":
        unknown.append("住宿预算缺少城市参考值")

    return CostBreakdown(
        tickets_amount=ticket_amount,
        tickets_status=tickets_status,
        tickets_confirmed_amount=round(ticket_confirmed, 2),
        tickets_estimated_amount=round(ticket_estimated, 2),
        tickets_unknown_count=ticket_unknown,
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
