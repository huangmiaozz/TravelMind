from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.hotel import Hotel, HotelOffer
from app.schemas.hotel import HotelList


router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.get("/search", response_model=HotelList)
def search_hotels(
    city_id: int = Query(gt=0),
    check_in_date: date | None = None,
    check_out_date: date | None = None,
    max_price: float | None = Query(default=None, ge=0),
    rating_min: float | None = Query(default=None, ge=0, le=5),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> HotelList:
    query = select(Hotel).options(selectinload(Hotel.offers)).where(Hotel.city_id == city_id)
    count_query = select(func.count()).select_from(Hotel).where(Hotel.city_id == city_id)
    if rating_min is not None:
        query = query.where(Hotel.rating >= rating_min)
        count_query = count_query.where(Hotel.rating >= rating_min)

    if max_price is not None or check_in_date is not None:
        offer_filters = []
        if max_price is not None:
            offer_filters.append(HotelOffer.price <= max_price)
        if check_in_date is not None:
            offer_filters.append(HotelOffer.valid_date >= check_in_date)
        if check_out_date is not None:
            offer_filters.append(HotelOffer.valid_date < check_out_date)
        query = query.join(HotelOffer).where(and_(*offer_filters)).distinct()
        count_query = count_query.join(HotelOffer).where(and_(*offer_filters)).distinct()

    items = list(db.scalars(query.order_by(Hotel.rating.desc().nullslast()).offset(offset).limit(limit)).unique())
    total = len(list(db.scalars(count_query)))
    return HotelList(items=items, total=total)
