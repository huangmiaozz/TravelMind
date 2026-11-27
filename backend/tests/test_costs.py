"""整趟费用拆分：门票人数计价与 confirmed/estimated/unknown 三态。"""

from datetime import date, time

from app.planners.models import DayPlan, PlannedItem, TripPlan
from app.schemas.plan import PlanCreateRequest
from app.services.costs import build_costs


def make_payload(**overrides) -> PlanCreateRequest:
    values = {
        "city": "北京",
        "start_date": date(2026, 11, 26),
        "days": 1,
        "adults": 2,
        "children": 1,
        "budget_total": 1000,
        "meal_budget_per_person_day": 100,
        "hotel_budget_per_room_night": 300,
    }
    values.update(overrides)
    return PlanCreateRequest(**values)


def make_item(
    name: str,
    *,
    price: float | None,
    status: str,
    child_price: float | None = None,
) -> PlannedItem:
    return PlannedItem(
        poi_id=1,
        name=name,
        start_time=time(9, 0),
        end_time=time(10, 0),
        estimated_cost=price or 0,
        score=1.0,
        ticket_price=price,
        ticket_child_price=child_price,
        ticket_status=status,
    )


def make_trip(items: list[PlannedItem]) -> TripPlan:
    return TripPlan(
        start_date=date(2026, 11, 26),
        days=[
            DayPlan(
                travel_date=date(2026, 11, 26),
                items=items,
                estimated_cost=sum(item.estimated_cost for item in items),
            )
        ],
        total_estimated_cost=sum(item.estimated_cost for item in items),
        budget_total=0,
        status="ok",
    )


def test_confirmed_ticket_is_multiplied_by_adults_and_children() -> None:
    costs = build_costs(
        make_trip([make_item("故宫", price=60, status="confirmed", child_price=30)]),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 150
    assert costs.tickets_confirmed_amount == 150
    assert costs.tickets_estimated_amount == 0
    assert costs.tickets_status == "confirmed"
    assert costs.budget_complete is True


def test_unknown_ticket_is_not_counted_as_zero_confirmed() -> None:
    costs = build_costs(
        make_trip([make_item("未知景点", price=None, status="unknown")]),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 0
    assert costs.tickets_status == "unknown"
    assert costs.tickets_unknown_count == 1
    assert costs.budget_complete is False
    assert "票价未核验" in costs.unknown_items[0]


def test_partial_ticket_status_when_some_items_are_unknown() -> None:
    costs = build_costs(
        make_trip(
            [
                make_item("已确认", price=20, status="confirmed"),
                make_item("待核", price=None, status="unknown"),
            ]
        ),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 60
    assert costs.tickets_status == "partial"
    assert costs.tickets_unknown_count == 1
    assert costs.budget_complete is False


def test_partial_status_survives_a_known_free_item() -> None:
    costs = build_costs(
        make_trip(
            [
                make_item("免费博物馆", price=0, status="confirmed"),
                make_item("待核景点", price=None, status="unknown"),
            ]
        ),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 0
    assert costs.tickets_status == "partial"
    assert costs.tickets_unknown_count == 1


def test_missing_child_ticket_is_marked_estimated() -> None:
    costs = build_costs(
        make_trip([make_item("只有成人票", price=50, status="confirmed")]),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 150
    assert costs.tickets_status == "estimated"
    assert costs.tickets_estimated_amount == 150
    assert any("儿童票价" in item for item in costs.unknown_items)


def test_free_ticket_does_not_require_child_price() -> None:
    costs = build_costs(
        make_trip([make_item("免费博物馆", price=0, status="confirmed")]),
        make_payload(),
        "北京",
    )

    assert costs.tickets_amount == 0
    assert costs.tickets_status == "confirmed"
    assert not any("儿童票价" in item for item in costs.unknown_items)
