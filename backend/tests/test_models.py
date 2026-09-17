from datetime import date

import pytest
from pydantic import ValidationError

from app.db.base import Base
from app.models import (
    City,
    ItineraryItem,
    Hotel,
    HotelOffer,
    OpeningHour,
    POI,
    Ticket,
    Trip,
    TripDay,
    User,
    UserPreference,
    Weather,
    TransportOption,
    TransportPlan,
)
from app.schemas.trip import TripCreate


def test_core_tables_are_registered() -> None:
    assert {
        "users",
        "cities",
        "pois",
        "trips",
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


def test_trip_create_accepts_matching_date_range() -> None:
    trip = TripCreate(
        user_id=1,
        from_city_id=10,
        to_city_id=20,
        start_date=date(2026, 10, 12),
        end_date=date(2026, 10, 17),
        days_count=5,
    )

    assert trip.days_count == 5


def test_trip_create_rejects_mismatched_date_range() -> None:
    with pytest.raises(ValidationError, match="days_count"):
        TripCreate(
            user_id=1,
            from_city_id=10,
            to_city_id=20,
            start_date=date(2026, 10, 12),
            end_date=date(2026, 10, 17),
            days_count=6,
        )


def test_interest_weights_must_be_between_zero_and_one() -> None:
    from app.schemas.user_preference import UserPreferencePayload

    with pytest.raises(ValidationError, match="between 0 and 1"):
        UserPreferencePayload(interests={"history": 1.1})
