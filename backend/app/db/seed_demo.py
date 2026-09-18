from datetime import date, time
from decimal import Decimal

from geoalchemy2 import WKTElement
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.city import City
from app.models.hotel import Hotel, HotelOffer
from app.models.poi import POI
from app.models.poi_detail import OpeningHour, Ticket
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.weather import Weather
from app.services.opening_hours import WEEKDAYS, parse_opening_hours


DEMO_SOURCE = "Mock Data (local demo)"
DEMO_SOURCE_URL = "about:blank"

# 名称、坐标、分类、开放时间原文来自高德；票价与参考消费仍是本地演示值。
# 因此 source 明确写成混合来源，而不是含糊地只写一个。
POI_SOURCE = "Amap API (place/text) + local demo values"
POI_SOURCE_URL = "https://lbs.amap.com/api/webservice/guide/api-advanced/search"
HOURS_SOURCE = "Amap API (biz_ext.opentime2) + rule parser"


def get_or_create_user(db):
    user = db.scalar(select(User).where(User.username == "demo_user"))
    if user is None:
        user = User(
            username="demo_user",
            email="demo@example.invalid",
            full_name="TravelMind Demo User",
        )
        db.add(user)
        db.flush()

    if user.preference is None:
        db.add(
            UserPreference(
                user_id=user.id,
                interests={"history": 0.9, "food": 0.7, "nature": 0.5},
                transport_preferences={"preferred_mode": "public_transport"},
                accommodation_preferences={"hotel_level": 3},
                custom_constraints={"max_walk_km": 15},
            )
        )
    return user


def get_or_create_city(db):
    city = db.scalar(
        select(City).where(City.name == "北京", City.province == "北京市")
    )
    if city is None:
        city = City(
            name="北京",
            province="北京市",
            country="CN",
            geom=WKTElement("POINT(116.4074 39.9042)", srid=4326),
        )
        db.add(city)
        db.flush()
    return city


def get_or_create_poi(db, city, *, name, category, tags, cost, minutes, point, opening_hours_raw):
    """建立一个演示 POI。

    开放时间不再写成统一的 8:30-17:00 —— 那是编造的数据。
    现在写入高德返回的**原文**，再由解析器推出结构化规则，
    解析的不确定性如实反映在 confidence 上。
    """
    poi = db.scalar(select(POI).where(POI.city_id == city.id, POI.name == name))
    if poi is None:
        poi = POI(
            city_id=city.id,
            name=name,
            poi_type="scenic",
            category=category,
            description=f"{name} 的本地演示记录。",
            geom=WKTElement(point, srid=4326),
            avg_cost=cost,
            address="北京市本地演示地址",
            source=POI_SOURCE,
            source_url=POI_SOURCE_URL,
            confidence=Decimal("0.70"),
            # 这两列是数据整合层的输入：兴趣标签参与加权评分，游玩时长参与排程。
            # 早先的种子脚本只把它们当局部变量返回、没有落库，规划器因而拿不到。
            interest_tags=tags,
            visit_minutes=minutes,
            opening_hours_raw=opening_hours_raw,
        )
        db.add(poi)
        db.flush()
    else:
        # 这几列是后加的。旧库中的记录可能为空，而种子脚本本就幂等，
        # 这里顺带补齐 —— 重跑一次即可修复历史数据。
        if not poi.interest_tags:
            poi.interest_tags = tags
        if poi.visit_minutes is None:
            poi.visit_minutes = minutes
        if not poi.opening_hours_raw:
            poi.opening_hours_raw = opening_hours_raw

    if not poi.opening_hours:
        # 由解析器决定每天开不开门、以及保守的开放边界。
        # 解析不出来时 open_time / close_time 留空（语义为"未知"，不过滤）。
        parsed = parse_opening_hours(opening_hours_raw)
        for day in WEEKDAYS:
            is_closed = day in parsed.closed_days
            db.add(
                OpeningHour(
                    poi_id=poi.id,
                    day_of_week=day,
                    open_time=None if is_closed else parsed.open_time,
                    close_time=None if is_closed else parsed.close_time,
                    is_closed=is_closed,
                    source=HOURS_SOURCE,
                    source_url=POI_SOURCE_URL,
                    confidence=Decimal(str(parsed.confidence)),
                )
            )
    if not poi.tickets:
        db.add(
            Ticket(
                poi_id=poi.id,
                ticket_type="adult",
                price=cost,
                currency="CNY",
                price_desc="本地演示价格，不代表真实票价",
                source=DEMO_SOURCE,
                source_url=DEMO_SOURCE_URL,
                confidence=Decimal("0.10"),
            )
        )
    return poi


def seed_demo_data() -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db)
        city = get_or_create_city(db)
        # 开放时间一律用高德返回的原文，不手工编造 ——
        # 下面三段是 2026-09-18 从 place/text（extensions=all）实取的 biz_ext.opentime2。
        # 三种写法完全不同（空格有无、分隔符、旺季淡季、全周开放），正好覆盖解析器的各类分支。
        poi_specs: list[dict] = [
            {
                "name": "故宫博物院（演示）",
                "category": "historical",
                "tags": {"history": 1.0, "culture": 0.9},
                "cost": Decimal("60"),
                "minutes": 150,
                "point": "POINT(116.3972 39.9163)",
                "opening_hours_raw": (
                    "旺季4月1日至10月31日 周二至周日 08:30-17:00 16:00停止检票，"
                    "淡季11月1日至3月31日 周二至周日 08:30-16:30 15:30停止检票，"
                    "周一全天关闭，节假日营业时间以官方通知为准"
                ),
            },
            {
                "name": "中国国家博物馆（演示）",
                "category": "museum",
                "tags": {"history": 0.9, "culture": 1.0},
                "cost": Decimal("0"),
                "minutes": 120,
                "point": "POINT(116.4074 39.9042)",
                "opening_hours_raw": (
                    "周一全天关闭(法定节假日除外)；"
                    "11月1日至次年5月31日周二至周日09:00-17:00(16:00停止入馆)；"
                    "6月1日至10月31日周二至周日09:00-17:30(16:30停止入馆)"
                ),
            },
            {
                "name": "北海公园（演示）",
                "category": "park",
                "tags": {"nature": 0.8, "photography": 0.7},
                "cost": Decimal("10"),
                "minutes": 90,
                "point": "POINT(116.3962 39.9255)",
                "opening_hours_raw": "周一至周日 06:00-21:00",
            },
        ]
        for spec in poi_specs:
            get_or_create_poi(db, city, **spec)

        weather = db.scalar(
            select(Weather).where(
                Weather.city_id == city.id,
                Weather.weather_date == date(2026, 10, 12),
            )
        )
        if weather is None:
            db.add(
                Weather(
                    city_id=city.id,
                    weather_date=date(2026, 10, 12),
                    temperature_min=Decimal("12"),
                    temperature_max=Decimal("22"),
                    precipitation=Decimal("0"),
                    weather_condition="sunny",
                    risk_level="low",
                    source=DEMO_SOURCE,
                    source_url=DEMO_SOURCE_URL,
                    confidence=Decimal("0.10"),
                )
            )

        hotel = db.scalar(
            select(Hotel).where(Hotel.city_id == city.id, Hotel.name == "TravelMind 演示酒店")
        )
        if hotel is None:
            hotel = Hotel(
                city_id=city.id,
                name="TravelMind 演示酒店",
                hotel_type="business",
                address="北京市本地演示地址",
                geom=WKTElement("POINT(116.4100 39.9100)", srid=4326),
                rating=Decimal("4.00"),
                source=DEMO_SOURCE,
                source_url=DEMO_SOURCE_URL,
                confidence=Decimal("0.10"),
            )
            db.add(hotel)
            db.flush()
        offer = db.scalar(
            select(HotelOffer).where(
                HotelOffer.hotel_id == hotel.id,
                HotelOffer.valid_date == date(2026, 10, 12),
                HotelOffer.room_type == "double",
            )
        )
        if offer is None:
            db.add(
                HotelOffer(
                    hotel_id=hotel.id,
                    valid_date=date(2026, 10, 12),
                    price=Decimal("520"),
                    currency="CNY",
                    room_type="double",
                    source=DEMO_SOURCE,
                    source_url=DEMO_SOURCE_URL,
                    confidence=Decimal("0.10"),
                )
            )

        db.commit()
        print(f"Seeded {DEMO_SOURCE}: user_id={user.id}, city_id={city.id}")


if __name__ == "__main__":
    seed_demo_data()
