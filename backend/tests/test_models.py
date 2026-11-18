import pytest
from pydantic import ValidationError

from app.db.base import Base
from app.models import PlanVersion, Trip
from app.schemas.trip import TripCreate


def test_core_tables_are_registered() -> None:
    assert {
        "users",
        "cities",
        "pois",
        "trips",
        "plan_versions",
        "trip_days",
        "itinerary_items",
        "user_preferences",
        "opening_hours",
        "tickets",
        "weather",
        "hotels",
        "hotel_offers",
        "transport_plans",
        "transport_options",
    } <= set(Base.metadata.tables)


def test_trip_create_requires_a_city() -> None:
    with pytest.raises(ValidationError, match="city"):
        TripCreate(user_id=1, title="周末")


def test_trip_create_defaults_to_demo_user_and_accepts_title() -> None:
    trip = TripCreate(city="北京", title="北京两日")

    assert trip.user_id == 1
    assert trip.city == "北京"
    assert trip.title == "北京两日"


def test_trip_model_no_longer_requires_cross_city_dates() -> None:
    columns = set(Trip.__table__.columns.keys())

    assert {"destination_city_id", "destination_city_name", "title"} <= columns
    assert "from_city_id" not in columns
    assert "to_city_id" not in columns
    assert "end_date" not in columns


def test_plan_version_has_snapshot_and_summary_fields() -> None:
    columns = set(PlanVersion.__table__.columns.keys())

    assert {
        "trip_id",
        "version_no",
        "status",
        "start_date",
        "days_count",
        "request_json",
        "plan_json",
        "data_snapshot",
        "total_estimated_cost",
        "generated_at",
    } <= columns


def test_plan_version_unique_constraint_is_declared() -> None:
    names = {
        constraint.name for constraint in PlanVersion.__table__.constraints
    }

    assert "uq_plan_versions_trip_version" in names
