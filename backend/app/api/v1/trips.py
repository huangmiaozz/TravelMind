from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.trip import Trip
from app.schemas.trip import TripCreate, TripList, TripRead, TripUpdate


router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, db: Session = Depends(get_db)) -> Trip:
    trip = Trip(**payload.model_dump())
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("", response_model=TripList)
def list_trips(
    user_id: int | None = Query(default=None, gt=0),
    trip_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> TripList:
    query = select(Trip).order_by(Trip.created_at.desc())
    count_query = select(Trip.id)
    if user_id is not None:
        query = query.where(Trip.user_id == user_id)
        count_query = count_query.where(Trip.user_id == user_id)
    if trip_status is not None:
        query = query.where(Trip.trip_status == trip_status)
        count_query = count_query.where(Trip.trip_status == trip_status)

    items = list(db.scalars(query))
    total = len(list(db.scalars(count_query)))
    return TripList(items=items, total=total)


@router.get("/{trip_id}", response_model=TripRead)
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    return trip


@router.put("/{trip_id}", response_model=TripRead)
def update_trip(trip_id: int, payload: TripUpdate, db: Session = Depends(get_db)) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trip, field, value)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, db: Session = Depends(get_db)) -> None:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")
    db.delete(trip)
    db.commit()
