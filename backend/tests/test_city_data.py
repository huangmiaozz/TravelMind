"""城市 POI 快照的结构检查（不访问数据库/外网）。"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "app" / "db" / "city_pois.json"


def test_city_snapshot_has_enough_pois_and_required_fields() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))

    for city, spec in payload["cities"].items():
        assert len(spec["pois"]) >= 15, city
        assert spec["adcode"]
        names = [row["name"] for row in spec["pois"]]
        assert len(names) == len(set(names)), f"duplicate POI in {city}"
        for row in spec["pois"]:
            assert row["location_gcj02"]
            assert row["category"]
            assert row["tags"]
            assert row["visit_minutes"] > 0


def test_snapshot_declares_amap_source() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))

    assert payload["source"].startswith("Amap API")
    assert payload["fetched_at"]
