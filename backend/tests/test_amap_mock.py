from datetime import date

from app.services.amap_mock import MockAmapProvider
from app.services.planning_services import get_planning_provider


def test_mock_provider_never_returns_live_source() -> None:
    provider = MockAmapProvider()

    leg = provider.route((119.30, 26.08), (119.31, 26.09), "walk")
    transit = provider.route((119.30, 26.08), (119.31, 26.09), "transit")
    weather = provider.weather_by_date("350100", [date(2026, 11, 18)])

    assert leg.status == "ok"
    assert leg.source == "mock"
    assert leg.is_mock is True
    assert transit.source == "mock"
    assert transit.segments
    assert weather[date(2026, 11, 18)].source == "mock"


def test_mock_provider_returns_places() -> None:
    provider = MockAmapProvider()

    restaurants = provider.nearby_restaurants((119.30, 26.08), "福州")
    hotels = provider.nearby_hotels((119.30, 26.08), "福州")

    assert len(restaurants) == 3
    assert len(hotels) == 3
    assert all(hotel.stay_type for hotel in hotels)


def test_default_provider_is_mock() -> None:
    provider = next(get_planning_provider())
    try:
        assert isinstance(provider, MockAmapProvider)
    finally:
        if provider is not None:
            provider.close()
