from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.trip import PlanVersion, Trip
from app.planners.models import PlanningCandidate
from app.services.amap import RouteLeg, WeatherDay
from app.services.planning_services import get_planning_provider
from app.services.static_map import StaticMapError


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # 只建本组测试需要的表；City/POI 使用 PostGIS，留给集成环境。
    Base.metadata.create_all(
        bind=engine, tables=[Trip.__table__, PlanVersion.__table__]
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def _candidate(poi_id: int, name: str, cost: float) -> PlanningCandidate:
    return PlanningCandidate(
        poi_id=poi_id,
        name=name,
        category="historical",
        interest_tags={"history": 1.0},
        estimated_cost=cost,
        visit_minutes=60,
        confidence=0.9,
    )


class FakePlanningProvider:
    def __init__(self) -> None:
        self.route_calls = 0
        self.weather_calls = 0

    def route(self, origin, destination, mode="walk", *, city=None, cityd=None):
        self.route_calls += 1
        return RouteLeg(
            mode=mode,
            distance_m=800,
            duration_s=600,
            walking_distance_m=800,
            cost_amount=None,
            cost_basis=None,
            status="ok",
        )

    def weather_by_date(self, city_adcode: str, dates):
        self.weather_calls += 1
        return {
            day: WeatherDay(
                forecast_date=day,
                condition="多云",
                temperature_min=15,
                temperature_max=22,
                precipitation=0,
                risk_level="low",
            )
            for day in dates
        }


def _create_trip(client: TestClient, monkeypatch) -> dict:
    monkeypatch.setattr(
        "app.api.v1.trips.resolve_city",
        lambda db, name: SimpleNamespace(
            id=7, name="北京", amap_adcode="110000"
        ),
    )
    response = client.post(
        "/api/v1/trips", json={"city": "北京", "title": "北京两日"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _plan_payload(**overrides) -> dict:
    payload = {
        "city": "北京",
        "start_date": "2026-11-02",
        "days": 2,
        "adults": 2,
        "children": 1,
        "budget_total": 500,
        "interests": {"history": 80},
        "daily_start": "09:00",
        "daily_end": "18:00",
        "max_daily_items": 1,
        "meal_budget_per_person_day": 120,
        "hotel_budget_per_room_night": 450,
    }
    payload.update(overrides)
    return payload


def test_create_trip_and_list_it(client, monkeypatch) -> None:
    trip = _create_trip(client, monkeypatch)

    assert trip["destination_city_name"] == "北京"
    assert trip["title"] == "北京两日"
    assert trip["plan_count"] == 0
    assert trip["latest_plan"] is None

    listing = client.get("/api/v1/trips")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == trip["id"]


def test_trip_city_must_exist(client, monkeypatch) -> None:
    def missing(db, name):
        from app.services.candidates import CityNotFoundError

        raise CityNotFoundError(f"city not found: {name}")

    monkeypatch.setattr("app.api.v1.trips.resolve_city", missing)

    response = client.post("/api/v1/trips", json={"city": "不存在"})

    assert response.status_code == 404


def test_create_plan_version_persists_request_and_result(
    client, monkeypatch
) -> None:
    trip = _create_trip(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [
            _candidate(1, "景点一", 60),
            _candidate(2, "景点二", 80),
        ],
    )

    response = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload()
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version_no"] == 1
    assert body["trip_id"] == trip["id"]
    assert body["days_count"] == 2
    assert len(body["days"]) == 2
    assert body["status"] == "ok"
    assert body["total_estimated_cost"] == 2040
    assert body["budget_difference"] == -1540
    assert body["over_budget"] is True
    assert body["costs"]["tickets_amount"] == 420
    assert body["costs"]["tickets_status"] == "estimated"
    assert body["costs"]["tickets_estimated_amount"] == 420
    assert body["costs"]["tickets_unknown_count"] == 0
    assert body["costs"]["meals_amount"] == 720
    assert body["costs"]["lodging_amount"] == 900
    assert body["costs"]["budget_total"] == 500
    assert body["request_snapshot"]["rooms"] == 2
    assert body["request_snapshot"]["nights"] == 1
    assert any("2 名成人 + 1 名儿童" in note for note in body["notes"])
    assert not any("尚未按同行人数" in note for note in body["notes"])
    assert not any("总费用不含门票" in note for note in body["notes"])
    assert body["data_snapshot"]["poi_data_version"] is None
    assert body["data_snapshot"]["weather_source"] is None


def test_plan_selections_are_persisted_per_version(client, monkeypatch) -> None:
    trip = _create_trip(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [_candidate(1, "景点一", 60)],
    )
    plan = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload(days=1)
    ).json()

    empty = client.get(f"/api/v1/plans/{plan['plan_id']}/selections")
    assert empty.status_code == 200
    assert empty.json() == {"meals": [], "stay": None}

    payload = {
        "meals": [
            {
                "day_index": 1,
                "meal_type": "lunch",
                "name": "示例餐厅",
                "address": "示例路 1 号",
                "area_id": "qianmen",
                "travel_minutes": 12,
                "cost_amount": 50,
            }
        ],
        "stay": {
            "name": "示例酒店",
            "address": "示例路 2 号",
            "business_area": "前门",
            "tier": "舒适型",
            "cost_amount": 420,
            "price_status": "quoted",
            "price_source": "rollinggo",
            "price_checked_at": "2026-11-27T01:00:00+00:00",
            "price_note": "示例报价",
            "rating": 4.6,
        },
    }
    saved = client.put(
        f"/api/v1/plans/{plan['plan_id']}/selections", json=payload
    )
    assert saved.status_code == 200, saved.text
    assert saved.json() == payload

    loaded = client.get(f"/api/v1/plans/{plan['plan_id']}/selections")
    assert loaded.json() == payload


def test_recalculate_costs_uses_selected_meal_and_stay(client, monkeypatch) -> None:
    trip = _create_trip(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [
            _candidate(1, "景点一", 60),
            _candidate(2, "景点二", 80),
        ],
    )
    plan = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload()
    ).json()
    selections = {
        "meals": [
            {
                "day_index": 1,
                "meal_type": "lunch",
                "name": "示例餐厅",
                "address": "示例路",
                "area_id": "qianmen",
                "travel_minutes": 10,
                "cost_amount": 50,
            }
        ],
        "stay": {
            "name": "示例酒店",
            "address": "示例路 2 号",
            "business_area": "前门",
            "tier": "舒适型",
            "cost_amount": 300,
            "price_status": "quoted",
            "price_source": "rollinggo",
            "price_checked_at": "2026-11-27T01:00:00+00:00",
            "price_note": "示例报价",
            "rating": 4.5,
        },
    }
    assert (
        client.put(
            f"/api/v1/plans/{plan['plan_id']}/selections", json=selections
        ).status_code
        == 200
    )

    refreshed = client.post(
        f"/api/v1/plans/{plan['plan_id']}/costs/recalculate"
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()

    # 已选午餐 50×3 人；其余餐次按日均 120 元拆分；住宿 300×2 间×1 晚。
    assert body["costs"]["meals_amount"] == 672
    assert body["costs"]["lodging_amount"] == 600
    assert body["costs"]["lodging_status"] == "quoted"
    assert body["costs"]["updated_at"]
    assert body["costs"]["total_estimated"] == 1692
    assert body["total_estimated_cost"] == 1692
    assert body["budget_difference"] == -1192

    again = client.get(f"/api/v1/plans/{plan['plan_id']}").json()
    assert again["costs"]["meals_amount"] == 672
    summary = client.get(f"/api/v1/trips/{trip['id']}/plans").json()["items"][-1]
    assert summary["total_estimated_cost"] == 1692


def test_replanning_adds_a_version_without_overwriting_the_old_one(
    client, monkeypatch
) -> None:
    trip = _create_trip(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [
            _candidate(1, "景点一", 60),
            _candidate(2, "景点二", 80),
        ],
    )

    first = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload()
    ).json()
    second = client.post(
        f"/api/v1/trips/{trip['id']}/plans",
        json=_plan_payload(days=1, max_daily_items=1, budget_total=50),
    ).json()

    assert first["plan_id"] != second["plan_id"]
    assert first["version_no"] == 1
    assert second["version_no"] == 2
    assert second["total_estimated_cost"] == 540
    assert second["over_budget"] is True
    assert second["budget_difference"] == -490

    old = client.get(f"/api/v1/plans/{first['plan_id']}")
    assert old.status_code == 200
    assert old.json()["days_count"] == 2
    assert old.json()["total_estimated_cost"] == 2040

    versions = client.get(f"/api/v1/trips/{trip['id']}/plans")
    assert versions.status_code == 200
    assert versions.json()["total"] == 2
    assert [item["version_no"] for item in versions.json()["items"]] == [1, 2]

    detail = client.get(f"/api/v1/trips/{trip['id']}")
    assert detail.status_code == 200
    assert detail.json()["plan_count"] == 2
    assert detail.json()["latest_plan"]["version_no"] == 2


def test_plan_city_must_match_trip_destination(client, monkeypatch) -> None:
    trip = _create_trip(client, monkeypatch)

    response = client.post(
        f"/api/v1/trips/{trip['id']}/plans",
        json=_plan_payload(city="上海"),
    )

    assert response.status_code == 409
    assert "does not match" in response.text


def test_delete_plan_version_keeps_other_versions(client, monkeypatch) -> None:
    trip = _create_trip(client, monkeypatch)
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: [_candidate(1, "景点一", 60)],
    )

    first = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload(days=1)
    ).json()
    second = client.post(
        f"/api/v1/trips/{trip['id']}/plans", json=_plan_payload(days=1)
    ).json()

    deleted = client.delete(f"/api/v1/plans/{first['plan_id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/plans/{first['plan_id']}").status_code == 404
    assert client.get(f"/api/v1/plans/{second['plan_id']}").status_code == 200

    versions = client.get(f"/api/v1/trips/{trip['id']}/plans").json()
    assert versions["total"] == 1
    assert versions["items"][0]["version_no"] == 2


def test_plan_version_list_returns_404_for_unknown_trip(client) -> None:
    response = client.get("/api/v1/trips/999/plans")

    assert response.status_code == 404


def test_plan_version_uses_provider_routes_and_weather(
    client, monkeypatch
) -> None:
    trip = _create_trip(client, monkeypatch)
    candidates = [
        PlanningCandidate(
            poi_id=1,
            name="景点一",
            category="historical",
            interest_tags={"history": 1.0},
            estimated_cost=60,
            visit_minutes=60,
            confidence=0.9,
            latitude=39.90,
            longitude=116.40,
        ),
        PlanningCandidate(
            poi_id=2,
            name="景点二",
            category="historical",
            interest_tags={"history": 1.0},
            estimated_cost=80,
            visit_minutes=60,
            confidence=0.9,
            latitude=39.91,
            longitude=116.41,
        ),
    ]
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city",
        lambda db, city: candidates,
    )
    provider = FakePlanningProvider()
    app.dependency_overrides[get_planning_provider] = lambda: provider
    try:
        response = client.post(
            f"/api/v1/trips/{trip['id']}/plans",
            json=_plan_payload(
                days=1,
                max_daily_items=2,
                max_walk_km=5,
                transport_preference="walk",
            ),
        )
    finally:
        app.dependency_overrides[get_planning_provider] = lambda: None

    assert response.status_code == 201, response.text
    body = response.json()
    day = body["days"][0]
    assert len(day["items"]) == 2
    assert day["legs"][0]["distance_m"] == 800
    assert day["legs"][0]["status"] == "ok"
    assert day["weather"]["status"] == "known"
    assert day["weather"]["condition"] == "多云"
    assert day["walk_km"] == 0.8
    assert day["walk_constraint"] == "satisfied"
    assert body["data_snapshot"]["weather_source"] == "amap_web_service"
    assert body["data_snapshot"]["route_source"] == "amap_web_service"
    assert any("已调用高德路线服务" in note for note in body["notes"])
    assert provider.route_calls >= 1
    assert provider.weather_calls == 1

    stored = client.get(f"/api/v1/plans/{body['plan_id']}")
    assert stored.status_code == 200
    assert stored.json()["days"][0]["legs"][0]["distance_m"] == 800
    assert stored.json()["days"][0]["weather"]["condition"] == "多云"


def test_plan_day_map_returns_png_and_degrades_on_failure(
    client, monkeypatch
) -> None:
    from app.api.v1 import plans as plans_api

    trip = _create_trip(client, monkeypatch)
    candidates = [
        PlanningCandidate(
            poi_id=1,
            name="景点一",
            category="historical",
            interest_tags={"history": 1.0},
            estimated_cost=60,
            visit_minutes=60,
            confidence=0.9,
            latitude=39.90,
            longitude=116.40,
        ),
        PlanningCandidate(
            poi_id=2,
            name="景点二",
            category="historical",
            interest_tags={"history": 1.0},
            estimated_cost=80,
            visit_minutes=60,
            confidence=0.9,
            latitude=39.91,
            longitude=116.41,
        ),
    ]
    monkeypatch.setattr(
        "app.api.v1.planner.candidates_for_city", lambda db, city: candidates
    )
    app.dependency_overrides[get_planning_provider] = lambda: FakePlanningProvider()
    try:
        plan = client.post(
            f"/api/v1/trips/{trip['id']}/plans",
            json=_plan_payload(days=1, max_daily_items=2),
        ).json()
    finally:
        app.dependency_overrides[get_planning_provider] = lambda: None

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 16
    plans_api._MAP_CACHE.clear()
    monkeypatch.setattr(
        "app.api.v1.plans.fetch_static_map", lambda points: png
    )
    image = client.get(f"/api/v1/plans/{plan['plan_id']}/days/1/map")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == png

    def fail(points):
        raise StaticMapError("boom")

    monkeypatch.setattr("app.api.v1.plans.fetch_static_map", fail)
    plans_api._MAP_CACHE.clear()
    failed = client.get(f"/api/v1/plans/{plan['plan_id']}/days/1/map")
    assert failed.status_code == 502
