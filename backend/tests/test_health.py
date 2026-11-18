from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.planners.models import OpeningWindow, PlanningCandidate
from app.services.candidates import CityNotFoundError


client = TestClient(app)


PLANNER_REQUEST = {
    "city": "北京",
    "start_date": "2026-10-12",
    "days": 1,
    "budget_total": 100,
    "interests": {"history": 100},
    "daily_start": "09:00:00",
    "daily_end": "13:00:00",
    "max_daily_items": 1,
    "max_walk_km": 5,
}


HISTORY_CANDIDATE = PlanningCandidate(
    poi_id=1,
    name="历史景点",
    category="historical",
    interest_tags={"history": 1.0},
    estimated_cost=60,
    visit_minutes=120,
    confidence=0.98,
)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "travelmind-api",
    }


def test_trip_crud_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/trips" in paths
    assert "/api/v1/trips/{trip_id}" in paths
    assert "/api/v1/trips/{trip_id}/plans" in paths
    assert "/api/v1/plans/{plan_id}" in paths


def test_user_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}" in paths
    assert "/api/v1/users/{user_id}/preferences" in paths


def test_user_create_rejects_empty_username() -> None:
    response = client.post("/api/v1/users", json={"username": ""})

    assert response.status_code == 422
    assert "String should have at least 1 character" in response.text


def test_poi_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/pois/search" in paths
    assert "/api/v1/pois/{poi_id}" in paths


def test_poi_search_rejects_invalid_pagination() -> None:
    response = client.get("/api/v1/pois/search?limit=101")

    assert response.status_code == 422


def test_poi_detail_schema_includes_operational_data() -> None:
    schema = app.openapi()["components"]["schemas"]["POIDetail"]

    assert "opening_hours" in schema["properties"]
    assert "tickets" in schema["properties"]


def test_weather_route_requires_city() -> None:
    response = client.get("/api/v1/weather")

    assert response.status_code == 422


def test_hotel_search_requires_city() -> None:
    response = client.get("/api/v1/hotels/search")

    assert response.status_code == 422


def test_planner_and_route_paths_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/routes/calculate" in paths
    assert "/api/v1/planner/generate" in paths


def test_route_calculation_marks_estimate_as_mock_data() -> None:
    response = client.post(
        "/api/v1/routes/calculate",
        json={
            "origin": {"lat": 39.9, "lng": 116.39},
            "destination": {"lat": 39.91, "lng": 116.41},
            "travel_mode": "walk",
        },
    )

    assert response.status_code == 200
    assert response.json()["source"].startswith("Mock Data")


def test_planner_endpoint_returns_multi_day_contract(monkeypatch) -> None:
    """接口层只负责编排：候选检索被替换为固定数据，以隔离数据库依赖。

    真实的检索逻辑由 tests/test_candidates.py 单测覆盖，
    需要 PostGIS 的查询留待集成验证。
    """
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [HISTORY_CANDIDATE],
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post("/api/v1/planner/generate", json=PLANNER_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["weather_known"] is False
    assert body["days"][0]["travel_date"] == "2026-10-12"
    assert body["days"][0]["items"][0]["name"] == "历史景点"
    assert body["days"][0]["items"][0]["opening_known"] is False
    assert body["total_estimated_cost"] == 60
    assert body["budget_total"] == 100
    assert body["budget_difference"] == 40
    assert body["over_budget"] is False
    assert any("天气未知" in note for note in body["notes"])
    assert any("步行距离" in note for note in body["notes"])
    assert body["source"] == "Rule-based multi-day planner"


def test_planner_interest_scale_is_normalized_for_scorer(monkeypatch) -> None:
    """接口的 0–100 兴趣刻度必须归一化后才能交给评分器。"""
    from app.api.v1.planner import load_planner_context
    from app.schemas.planner import PlannerPlanRequest

    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [HISTORY_CANDIDATE],
    )
    payload = PlannerPlanRequest(
        city="北京",
        start_date="2026-10-12",
        interests={"history": 50},
    )

    _, preferences = load_planner_context(None, payload)

    assert preferences.interests == {"history": 0.5}


def test_planner_endpoint_marks_unset_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [HISTORY_CANDIDATE],
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post(
            "/api/v1/planner/generate",
            json={**PLANNER_REQUEST, "budget_total": 0},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    body = response.json()
    assert body["budget_total"] == 0
    assert body["budget_difference"] == 0
    assert body["over_budget"] is False
    assert any("未设置预算" in note for note in body["notes"])


def test_planner_endpoint_plans_multiple_days_and_flags_over_budget(
    monkeypatch,
) -> None:
    second = PlanningCandidate(
        poi_id=2,
        name="第二景点",
        category="historical",
        interest_tags={"history": 1.0},
        estimated_cost=80,
        visit_minutes=60,
        confidence=0.9,
    )
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [HISTORY_CANDIDATE, second],
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post(
            "/api/v1/planner/generate",
            json={**PLANNER_REQUEST, "days": 2, "budget_total": 100},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 2
    assert [day["items"][0]["name"] for day in body["days"]] == ["历史景点", "第二景点"]
    assert body["total_estimated_cost"] == 140
    assert body["budget_difference"] == -40
    assert body["over_budget"] is True
    assert body["status"] == "ok"


def test_planner_endpoint_returns_empty_status_instead_of_error(monkeypatch) -> None:
    closed = tuple(
        OpeningWindow(day, is_closed=True)
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    )
    closed_candidate = PlanningCandidate(
        poi_id=3,
        name="周一闭馆景点",
        category="museum",
        interest_tags={"history": 1.0},
        estimated_cost=0,
        visit_minutes=60,
        confidence=0.9,
        opening_windows=closed,
    )
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [closed_candidate],
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post(
            "/api/v1/planner/generate",
            json={**PLANNER_REQUEST, "days": 2},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty"
    assert body["days"][0]["items"] == []
    assert body["days"][1]["items"] == []
    assert body["total_estimated_cost"] == 0
    assert any("没有可安排的景点" in note for note in body["notes"])


def test_planner_options_endpoint_returns_multi_day_trips(monkeypatch) -> None:
    candidates = [
        PlanningCandidate(
            poi_id=index,
            name=f"景点 {index}",
            category="historical",
            interest_tags={"history": 1.0},
            estimated_cost=20,
            visit_minutes=30,
            confidence=0.9,
        )
        for index in range(1, 5)
    ]
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: candidates,
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post(
            "/api/v1/planner/generate-options",
            json={**PLANNER_REQUEST, "days": 2, "max_daily_items": 2},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    plans = response.json()["plans"]
    assert len(plans) == 4
    assert all(len(plan["days"]) == 2 for plan in plans)
    # 「最舒适」策略减少每日条目，所以整趟费用更低；其余策略排满两天。
    totals = {plan["plan_type"]: plan["total_estimated_cost"] for plan in plans}
    assert totals.pop("most_comfortable") == 40
    assert set(totals.values()) == {80}


def test_planner_endpoint_rejects_legacy_single_date_payload() -> None:
    """旧契约的 travel_date 不再被接受，避免两套日期语义并存。"""
    legacy = {
        key: value
        for key, value in PLANNER_REQUEST.items()
        if key != "start_date"
    }
    legacy["travel_date"] = "2026-10-12"

    response = client.post("/api/v1/planner/generate", json=legacy)

    assert response.status_code == 422
    assert "start_date" in response.text


def test_planner_endpoint_returns_404_for_unknown_city(monkeypatch) -> None:
    def raise_not_found(db, city):
        raise CityNotFoundError(f"city not found: {city}")

    monkeypatch.setattr("app.api.v1.planner.candidates_for_city", raise_not_found)
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post("/api/v1/planner/generate", json=PLANNER_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


def test_planner_endpoint_returns_404_when_city_has_no_poi(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city", lambda db, city: []
    )
    app.dependency_overrides[get_db] = lambda: None
    try:
        response = client.post("/api/v1/planner/generate", json=PLANNER_REQUEST)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


def test_multi_plan_and_expense_paths_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/planner/generate-options" in paths
    assert "/api/v1/expenses/estimate" in paths
    assert "/api/v1/routes/search" in paths
    assert "/api/v1/planner/replan" in paths


def test_expense_estimate_returns_breakdown() -> None:
    response = client.post(
        "/api/v1/expenses/estimate",
        json=[
            {"expense_type": "ticket", "amount": "60"},
            {"expense_type": "food", "amount": "80"},
        ],
    )

    assert response.status_code == 200
    assert response.json()["total"] == "140"


def test_transport_search_marks_external_data_as_mock() -> None:
    response = client.post(
        "/api/v1/routes/search",
        json={
            "origin": {"lat": 39.9, "lng": 116.39},
            "destination": {"lat": 39.91, "lng": 116.41},
        },
    )

    assert response.status_code == 200
    assert response.json()["source"].startswith("Mock Data")
