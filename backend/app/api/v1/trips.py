from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.trip import Trip
from app.schemas.plan import PlanVersionSummary
from app.schemas.trip import TripCreate, TripDetail, TripList, TripRead, TripUpdate
from app.services.candidates import CityNotFoundError, resolve_city
from app.services.plan_versions import version_summary


router = APIRouter(prefix="/trips", tags=["trips"])


def _summaries(trip: Trip) -> list[PlanVersionSummary]:
    return [
        version_summary(version)
        for version in sorted(trip.plans, key=lambda item: item.version_no)
    ]


def _trip_read(trip: Trip) -> TripRead:
    summaries = _summaries(trip)
    return TripRead(
        id=trip.id,
        user_id=trip.user_id,
        destination_city_id=trip.destination_city_id,
        destination_city_name=trip.destination_city_name,
        destination_city_adcode=trip.destination_city_adcode,
        title=trip.title,
        created_at=trip.created_at,
        updated_at=trip.updated_at,
        plan_count=len(summaries),
        latest_plan=summaries[-1] if summaries else None,
    )


def _trip_detail(trip: Trip) -> TripDetail:
    summaries = _summaries(trip)
    return TripDetail(
        **_trip_read(trip).model_dump(),
        plans=summaries,
    )


@router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, db: Session = Depends(get_db)) -> TripRead:
    try:
        city = resolve_city(db, payload.city)
    except CityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    trip = Trip(
        user_id=payload.user_id,
        destination_city_id=city.id,
        destination_city_name=city.name,
        destination_city_adcode=getattr(city, "amap_adcode", None),
        title=payload.title or f"{city.name}旅行",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return _trip_read(trip)


@router.get("", response_model=TripList)
def list_trips(
    user_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
) -> TripList:
    query = (
        select(Trip)
        .options(selectinload(Trip.plans))
        .order_by(Trip.created_at.desc())
    )
    if user_id is not None:
        query = query.where(Trip.user_id == user_id)

    trips = list(db.scalars(query))
    return TripList(items=[_trip_read(trip) for trip in trips], total=len(trips))


@router.get("/{trip_id}", response_model=TripDetail)
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> TripDetail:
    trip = db.scalar(
        select(Trip)
        .options(selectinload(Trip.plans))
        .where(Trip.id == trip_id)
    )
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
        )
    return _trip_detail(trip)


@router.put("/{trip_id}", response_model=TripRead)
def update_trip(
    trip_id: int, payload: TripUpdate, db: Session = Depends(get_db)
) -> TripRead:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(trip, field, value)
    db.commit()
    db.refresh(trip)
    return _trip_read(trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, db: Session = Depends(get_db)) -> None:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found"
        )
    db.delete(trip)
    db.commit()
