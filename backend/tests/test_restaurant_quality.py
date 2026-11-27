from app.services.amap import RestaurantSuggestion
from app.services.restaurant_quality import filter_and_tag, known_tag


def _restaurant(name: str, rating: float | None) -> RestaurantSuggestion:
    return RestaurantSuggestion(
        name=name,
        address=None,
        distance_m=100,
        cost_amount=None,
        rating=rating,
        location=None,
    )


def test_known_restaurant_is_tagged() -> None:
    assert known_tag("北京", "四季民福烤鸭店") == "本地精选"
    assert known_tag("北京", "海底捞火锅") == "连锁"
    assert known_tag("福州", "同利肉燕") == "本地精选"


def test_filter_drops_low_rating_and_keeps_known() -> None:
    items = [
        _restaurant("某不知名小店", 3.2),
        _restaurant("全聚德", 3.9),
        _restaurant("普通餐厅", 4.5),
        _restaurant("另一家餐厅", 4.2),
    ]

    result = filter_and_tag(items, "北京")

    names = {item.name for item in result}
    assert "某不知名小店" not in names
    assert "全聚德" in names
    assert "普通餐厅" in names
