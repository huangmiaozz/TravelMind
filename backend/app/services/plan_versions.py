"""方案版本的序列化与小工具。

模型保存的是 ``plan_json`` 快照；本模块负责把快照还原成 API 响应，并把
ORM 行转成列表摘要。这样 ``trips`` 和 ``plans`` 两个路由不需要重复字段映射。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.trip import PlanVersion
from app.schemas.plan import PlanCreateRequest, PlanDetail, PlanVersionSummary


def next_version_no(db: Session, trip_id: int) -> int:
    current = db.scalar(
        select(func.max(PlanVersion.version_no)).where(
            PlanVersion.trip_id == trip_id
        )
    )
    return (current or 0) + 1


def version_summary(version: PlanVersion) -> PlanVersionSummary:
    selection_totals = (version.selection_json or {}).get("totals") or {}
    total = float(selection_totals.get("total_estimated_cost", version.total_estimated_cost))
    difference = float(
        selection_totals.get("budget_difference", version.budget_difference)
    )
    over_budget = bool(selection_totals.get("over_budget", version.over_budget))
    return PlanVersionSummary(
        plan_id=version.id,
        version_no=version.version_no,
        status=version.status,
        start_date=version.start_date,
        days=version.days_count,
        adults=version.adults_count,
        children=version.children_count,
        budget_total=float(version.budget_total),
        total_estimated_cost=total,
        budget_difference=difference,
        over_budget=over_budget,
        weather_known=version.weather_known,
        generated_at=version.generated_at,
    )


def version_detail(version: PlanVersion) -> PlanDetail:
    payload = dict(version.plan_json or {})
    selection = version.selection_json or {}
    # 用户选餐/选酒店后重新计算的花费覆盖生成时快照，但不修改 plan_json 本身。
    if selection.get("costs"):
        payload["costs"] = selection["costs"]
    totals = selection.get("totals") or {}
    if totals:
        payload["total_estimated_cost"] = totals.get(
            "total_estimated_cost", payload.get("total_estimated_cost")
        )
        payload["budget_difference"] = totals.get(
            "budget_difference", payload.get("budget_difference")
        )
        payload["over_budget"] = totals.get(
            "over_budget", payload.get("over_budget")
        )
    payload.update(
        plan_id=version.id,
        trip_id=version.trip_id,
        version_no=version.version_no,
        days_count=version.days_count,
        generated_at=version.generated_at,
        request_snapshot=version.request_json or {},
        data_snapshot=version.data_snapshot or {},
    )
    return PlanDetail(**payload)


def request_snapshot(payload: PlanCreateRequest) -> dict:
    """保存完整请求，并把默认房间数/晚数落成明确值。"""
    snapshot = payload.model_dump(mode="json")
    snapshot["rooms"] = payload.resolved_rooms
    snapshot["nights"] = payload.resolved_nights
    return snapshot


def data_snapshot(
    *, weather_used: bool = False, route_used: bool = False
) -> dict:
    """记录生成方案时实际可追溯的数据版本。

    当前 POI 表没有独立的数据版本号；未接入的能力显式写 ``null``，避免编造
    一个看起来可复现的版本。
    """
    return {
        "planner": "rule-based-multi-day-v0.2",
        "poi_data_version": None,
        "weather_source": "amap_web_service" if weather_used else None,
        "route_source": "amap_web_service" if route_used else None,
    }
