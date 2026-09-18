from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.planners.models import PlanningCandidate
from app.services.candidates import CityNotFoundError


client = TestClient(app)


PLANNER_REQUEST = {
    "city": "北京",
    "travel_date": "2026-10-12",
    "interests": {"history": 1.0},
    "daily_start": "09:00:00",
    "daily_end": "13:00:00",
    "max_daily_items": 1,
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


def test_create_trip_validates_date_range_before_database_access() -> None:
    response = client.post(
        "/api/v1/trips",
        json={
            "user_id": 1,
            "from_city_id": 10,
            "to_city_id": 20,
            "start_date": "2026-10-12",
            "end_date": "2026-10-17",
            "days_count": 6,
        },
    )

    assert response.status_code == 422
    assert "days_count" in response.text


def test_trip_crud_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/trips" in paths
    assert "/api/v1/trips/{trip_id}" in paths


def test_trip_update_requires_complete_date_update() -> None:
    response = client.put(
        "/api/v1/trips/1",
        json={"start_date": "2026-10-12", "budget_total": 9000},
    )

    assert response.status_code == 422
    assert "updated together" in response.text


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


def test_planner_endpoint_returns_scheduled_items(monkeypatch) -> None:
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
    assert response.json()["items"][0]["name"] == "历史景点"
    assert response.json()["source"] == "Rule-based weighted planner"


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
