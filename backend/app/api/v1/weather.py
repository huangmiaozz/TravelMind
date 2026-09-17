from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.weather import Weather
from app.schemas.weather import WeatherList


router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=WeatherList)
def get_weather(
    city_id: int = Query(gt=0),
    weather_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> WeatherList:
    query = select(Weather).where(Weather.city_id == city_id).order_by(Weather.weather_date)
    if weather_date is not None:
        query = query.where(Weather.weather_date == weather_date)
    else:
        if start_date is not None:
            query = query.where(Weather.weather_date >= start_date)
        if end_date is not None:
            query = query.where(Weather.weather_date <= end_date)
    items = list(db.scalars(query))
    return WeatherList(items=items, total=len(items))
