from app.services.amap import StaySuggestion
from app.services.hotel_recommendations import (
    classify_tier,
    commute_minutes,
    passes_quality,
    score_hotel,
)


def _hotel(name: str, location: tuple[float, float]) -> StaySuggestion:
    return StaySuggestion(
        name=name,
        address=None,
        business_area=None,
        stay_type="宾馆酒店",
        distance_m=0,
        cost_amount=None,
        rating=None,
        location=location,
    )


def test_badaling_uses_gateway_when_hotel_is_in_city() -> None:
    badaling = (116.0168, 40.3562)

    minutes = commute_minutes((116.3830, 39.9490), badaling, "八达岭长城")

    assert minutes < 120


def test_central_hotel_beats_badaling_hotel_for_two_day_trip() -> None:
    days = [
        [(116.3970, 39.9163, "故宫博物院")],
        [(116.0168, 40.3562, "八达岭长城")],
    ]
    central = _hotel("德胜门附近酒店", (116.3830, 39.9490))
    remote = _hotel("八达岭附近酒店", (116.0168, 40.3562))

    central_score = score_hotel(central, days)
    remote_score = score_hotel(remote, days)

    assert central_score is not None
    assert remote_score is not None
    assert central_score.score < remote_score.score


def test_quality_filter_rejects_low_rating_and_plain_guesthouse() -> None:
    low_rating = _hotel("某某酒店", (116.40, 39.90))
    low_rating = StaySuggestion(
        **{**low_rating.__dict__, "rating": 3.6}
    )
    guesthouse = _hotel("某某宾馆", (116.40, 39.90))
    guesthouse = StaySuggestion(
        **{**guesthouse.__dict__, "rating": 4.7}
    )
    known_chain = _hotel("汉庭酒店", (116.40, 39.90))

    assert passes_quality(low_rating, None) is False
    assert passes_quality(guesthouse, None) is False
    assert passes_quality(known_chain, None) is True


def test_quality_filter_respects_hotel_budget() -> None:
    hotel = _hotel("示例酒店", (116.40, 39.90))
    hotel = StaySuggestion(**{**hotel.__dict__, "rating": 4.5, "cost_amount": 800})

    assert passes_quality(hotel, 500) is False
    assert passes_quality(hotel, 1000) is True


def test_hotel_tier_classification() -> None:
    assert classify_tier(_hotel("全季酒店", (116.40, 39.90))) == "舒适型"
    assert classify_tier(_hotel("速8优选酒店", (116.40, 39.90))) == "经济型"
    assert classify_tier(_hotel("北京希尔顿酒店", (116.40, 39.90))) == "高档/精品"
    assert classify_tier(_hotel("某不知名酒店", (116.40, 39.90))) == "未知"
