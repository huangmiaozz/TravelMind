from app.services.amap import RouteLeg
from app.services.meal_recommendations import (
    area_candidates,
    meal_anchor,
    meal_budget,
)


class FakeProvider:
    def route(self, origin, destination, mode="walk", **kwargs) -> RouteLeg:
        # 东侧/三里屯方向故意设为不可接受，用来验证时间闸门。
        minutes = 60 if destination[0] > 116.42 else 8
        return RouteLeg(
            mode=mode,
            distance_m=3000,
            duration_s=minutes * 60,
            walking_distance_m=0,
            cost_amount=10.0,
            cost_basis="per_person",
            status="ok",
            source="mock",
        )


def _day() -> dict:
    return {
        "items": [
            {
                "name": "故宫",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
                "longitude": 116.397,
                "latitude": 39.916,
            }
        ],
        "meals": [
            {
                "meal_type": "lunch",
                "start_time": "12:00:00",
                "end_time": "14:00:00",
            }
        ],
    }


def test_lunch_budget_includes_travel() -> None:
    assert meal_budget("lunch") == (120, 50, 60)


def test_area_candidates_reject_areas_over_travel_budget() -> None:
    anchor, next_item = meal_anchor(_day(), "lunch")
    candidates, total, travel_budget, min_eat = area_candidates(
        FakeProvider(), "北京", anchor, next_item, "lunch"
    )

    assert total == 120
    assert travel_budget == 50
    assert min_eat == 60
    assert candidates
    assert all(item.travel_minutes <= 50 for item in candidates)
    assert all(item.area.id != "beijing-sanlitun" for item in candidates)


def test_badaling_dinner_returns_to_city_gateway() -> None:
    day = {
        "items": [
            {
                "name": "八达岭长城",
                "start_time": "09:00:00",
                "end_time": "12:00:00",
                "longitude": 116.0168,
                "latitude": 40.3562,
            }
        ],
        "meals": [
            {
                "meal_type": "dinner",
                "start_time": "18:00:00",
                "end_time": "19:30:00",
            }
        ],
    }

    anchor, next_item = meal_anchor(day, "dinner")

    assert "返程门户" in anchor["name"]
    assert next_item is None
