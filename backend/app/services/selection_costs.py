"""按用户已选餐厅/酒店重算费用。

生成时的 plan_json 保持只读；重算结果写入 selection_json 的 costs/totals，
读取方案时覆盖响应中的费用字段。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.trip import PlanVersion
from app.schemas.planner import CostBreakdownResponse
from app.services.costs import CITY_COST_DEFAULTS


def _share(meal_type: str) -> float:
    # 只计划午餐/晚餐；把日均餐饮预算按 55%/45% 分摊。
    return 0.55 if meal_type == "lunch" else 0.45


def recalculate_selection_costs(version: PlanVersion) -> CostBreakdownResponse:
    base = (version.plan_json or {}).get("costs") or {}
    request = version.request_json or {}
    selection = version.selection_json or {}
    city = str((version.plan_json or {}).get("city") or "")
    days = max(1, version.days_count)
    adults = max(1, int(request.get("adults") or 1))
    children = max(0, int(request.get("children") or 0))
    party = adults + children
    rooms = max(1, int(request.get("rooms") or 1))
    nights = max(0, int(request.get("nights") or max(0, days - 1)))

    meals_selected = selection.get("meals") or []
    stay = selection.get("stay") or {}
    unknown_items = [
        str(item) for item in (base.get("unknown_items") or [])
    ]

    if meals_selected:
        by_key = {
            (int(item.get("day_index") or 0), str(item.get("meal_type") or "")): item
            for item in meals_selected
        }
        daily_rate = request.get("meal_budget_per_person_day")
        if daily_rate is None:
            daily_rate = (CITY_COST_DEFAULTS.get(city) or {}).get("meal")
        meal_total = 0.0
        meal_missing = False
        for day in range(1, days + 1):
            for meal_type in ("lunch", "dinner"):
                chosen = by_key.get((day, meal_type))
                selected_cost = chosen.get("cost_amount") if chosen else None
                if selected_cost is not None:
                    meal_total += float(selected_cost) * party
                elif daily_rate is not None:
                    meal_total += float(daily_rate) * party * _share(meal_type)
                else:
                    meal_missing = True
        meals_amount = round(meal_total, 2)
        meals_status = "partial" if meal_missing else "estimated"
        unknown_items = [item for item in unknown_items if "餐饮" not in item]
        if meal_missing:
            unknown_items.append("部分餐次未选择且缺少餐饮预算参考")
    else:
        meals_amount = float(base.get("meals_amount") or 0)
        meals_status = str(base.get("meals_status") or "unknown")

    stay_cost = stay.get("cost_amount")
    if stay_cost is not None:
        lodging_amount = round(float(stay_cost) * rooms * nights, 2)
        # 只有 RollingGo 的实时报价才标“实时报价”；普通参考价仍是估算。
        lodging_status = (
            "quoted"
            if str(stay.get("price_source") or "") == "rollinggo"
            else "estimated"
        )
        unknown_items = [item for item in unknown_items if "住宿" not in item]
    else:
        lodging_amount = float(base.get("lodging_amount") or 0)
        lodging_status = str(base.get("lodging_status") or "unknown")

    tickets_amount = float(base.get("tickets_amount") or 0)
    transport_amount = float(base.get("transport_amount") or 0)
    total = round(
        tickets_amount + transport_amount + meals_amount + lodging_amount, 2
    )
    budget = round(float(base.get("budget_total") or version.budget_total), 2)
    difference = round(budget - total, 2) if budget > 0 else 0.0
    over_budget = budget > 0 and total > budget

    return CostBreakdownResponse(
        tickets_amount=tickets_amount,
        tickets_status=str(base.get("tickets_status") or "unknown"),
        tickets_confirmed_amount=float(base.get("tickets_confirmed_amount") or 0),
        tickets_estimated_amount=float(base.get("tickets_estimated_amount") or 0),
        tickets_unknown_count=int(base.get("tickets_unknown_count") or 0),
        transport_amount=transport_amount,
        transport_status=str(base.get("transport_status") or "unknown"),
        meals_amount=meals_amount,
        meals_status=meals_status,
        lodging_amount=lodging_amount,
        lodging_status=lodging_status,
        total_estimated=total,
        budget_total=budget,
        budget_difference=difference,
        budget_complete=not unknown_items,
        unknown_items=unknown_items,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
