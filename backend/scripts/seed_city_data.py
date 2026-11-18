"""把抓取到的福州/北京 POI 快照写入数据库。

数据来自 ``scripts/fetch_city_pois.py``（高德 place/text），脚本只做幂等 upsert：
- 城市表补 adcode 和中心点；
- POI 补坐标、类别、兴趣标签、游玩时长、开放时间原文；
- 开放时间用现有解析器落成每周窗口；解析不出时保留原文并标未知。

票价暂不写入：高德 ``biz_ext.cost`` 不可靠，只有完成官方核验的景点才应写
Ticket。没有 Ticket 的景点在规划费用里仍是未知，不能当成 0 元已确认。

用法::

    cd backend
    python -m scripts.seed_city_data
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from geoalchemy2 import WKTElement
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.city import City
from app.models.poi import POI
from app.models.poi_detail import OpeningHour
from app.services.coordinates import gcj02_to_wgs84
from app.services.opening_hours import WEEKDAYS, parse_opening_hours

DATA_FILE = Path(__file__).resolve().parents[1] / "app" / "db" / "city_pois.json"
SOURCE = "Amap API (place/text) + manual category/tags"
SOURCE_URL = "https://lbs.amap.com/api/webservice/guide/api-advanced/search"


def wkt_point(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon:.6f} {lat:.6f})", srid=4326)


def upsert_city(db, name: str, province: str, adcode: str, center_gcj02) -> City:
    city = db.scalar(select(City).where(City.name == name, City.province == province))
    lon, lat = gcj02_to_wgs84(*center_gcj02)
    if city is None:
        city = City(
            name=name,
            province=province,
            country="CN",
            amap_adcode=adcode,
            geom=wkt_point(lon, lat),
        )
        db.add(city)
        db.flush()
    else:
        city.amap_adcode = adcode
        if city.geom is None:
            city.geom = wkt_point(lon, lat)
    return city


def upsert_poi(db, city: City, row: dict) -> POI:
    poi = db.scalar(
        select(POI).where(POI.city_id == city.id, POI.name == row["name"])
    )
    lon, lat = (float(value) for value in row["location_gcj02"].split(","))
    wgs_lon, wgs_lat = gcj02_to_wgs84(lon, lat)
    if poi is None:
        poi = POI(
            city_id=city.id,
            name=row["name"],
            poi_type=row.get("type") or "scenic",
            category=row["category"],
            description=f"{row['name']}，类别：{row['category']}。",
            geom=wkt_point(wgs_lon, wgs_lat),
            avg_cost=None,
            address=row.get("address"),
            source=SOURCE,
            source_url=SOURCE_URL,
            confidence=Decimal("0.70"),
            interest_tags=row["tags"],
            visit_minutes=row["visit_minutes"],
            opening_hours_raw=row.get("opening_hours_raw"),
        )
        db.add(poi)
        db.flush()
    else:
        poi.poi_type = row.get("type") or poi.poi_type
        poi.category = row["category"]
        poi.geom = wkt_point(wgs_lon, wgs_lat)
        poi.address = row.get("address")
        poi.interest_tags = row["tags"]
        poi.visit_minutes = row["visit_minutes"]
        poi.opening_hours_raw = row.get("opening_hours_raw")
        poi.source = SOURCE
        poi.source_url = SOURCE_URL

    if not poi.opening_hours:
        raw = row.get("opening_hours_raw")
        if raw:
            parsed = parse_opening_hours(raw)
            for day in WEEKDAYS:
                closed = day in parsed.closed_days
                db.add(
                    OpeningHour(
                        poi_id=poi.id,
                        day_of_week=day,
                        open_time=None if closed else parsed.open_time,
                        close_time=None if closed else parsed.close_time,
                        is_closed=closed,
                        source=SOURCE,
                        source_url=SOURCE_URL,
                        confidence=Decimal(str(parsed.confidence)),
                    )
                )
    return poi


def seed() -> None:
    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    provinces = {"北京": "北京市", "福州": "福建省"}
    with SessionLocal() as db:
        for city_name, spec in payload["cities"].items():
            city = upsert_city(
                db,
                city_name,
                provinces[city_name],
                spec["adcode"],
                tuple(spec["center_gcj02"]),
            )
            for row in spec["pois"]:
                upsert_poi(db, city, row)
            print(f"{city_name}: {len(spec['pois'])} POIs")

        # 旧种子里的“（演示）”POI 与真实景点重复，且票价是 Mock；有真实数据后移除。
        legacy = list(db.scalars(select(POI).where(POI.name.like("%（演示）"))))
        for poi in legacy:
            db.delete(poi)
        if legacy:
            print(f"removed {len(legacy)} legacy demo POIs")

        db.commit()
    print(f"seeded from {payload['source']} @ {payload['fetched_at']}")


if __name__ == "__main__":
    seed()
