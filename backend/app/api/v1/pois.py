from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.poi import POI
from app.schemas.poi import POIDetail, POIList, POIRead


router = APIRouter(prefix="/pois", tags=["pois"])


@router.get("/search", response_model=POIList)
def search_pois(
    city_id: int | None = Query(default=None, gt=0),
    keyword: str | None = Query(default=None, min_length=1),
    poi_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> POIList:
    filters = []
    if city_id is not None:
        filters.append(POI.city_id == city_id)
    if keyword is not None:
        filters.append(POI.name.ilike(f"%{keyword}%"))
    if poi_type is not None:
        filters.append(POI.poi_type == poi_type)
    if category is not None:
        filters.append(POI.category == category)

    query = select(POI).where(*filters).order_by(POI.id).offset(offset).limit(limit)
    count_query = select(func.count()).select_from(POI).where(*filters)
    return POIList(items=list(db.scalars(query)), total=db.scalar(count_query) or 0)


@router.get("/{poi_id}", response_model=POIDetail)
def get_poi(poi_id: int, db: Session = Depends(get_db)) -> POI:
    query = (
        select(POI)
        .options(selectinload(POI.opening_hours), selectinload(POI.tickets))
        .where(POI.id == poi_id)
    )
    poi = db.scalar(query)
    if poi is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POI not found")
    return poi
