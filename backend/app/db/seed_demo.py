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


DEMO_SOURCE = "Mock Data (local demo)"
DEMO_SOURCE_URL = "about:blank"


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


def get_or_create_poi(db, city, name, category, tags, cost, minutes, point):
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
            source=DEMO_SOURCE,
            source_url=DEMO_SOURCE_URL,
            confidence=Decimal("0.10"),
        )
        db.add(poi)
        db.flush()

    if not poi.opening_hours:
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
            db.add(
                OpeningHour(
                    poi_id=poi.id,
                    day_of_week=day,
                    open_time=time(8, 30),
                    close_time=time(17, 0),
                    source=DEMO_SOURCE,
                    source_url=DEMO_SOURCE_URL,
                    confidence=Decimal("0.10"),
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
    return poi, tags, minutes


def seed_demo_data() -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db)
        city = get_or_create_city(db)
        poi_specs = [
            ("故宫博物院（演示）", "historical", {"history": 1.0, "culture": 0.9}, Decimal("60"), 150, "POINT(116.3972 39.9163)"),
            ("中国国家博物馆（演示）", "museum", {"history": 0.9, "culture": 1.0}, Decimal("0"), 120, "POINT(116.4074 39.9042)"),
            ("北海公园（演示）", "park", {"nature": 0.8, "photography": 0.7}, Decimal("10"), 90, "POINT(116.3962 39.9255)"),
        ]
        for spec in poi_specs:
            get_or_create_poi(db, city, *spec)

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
