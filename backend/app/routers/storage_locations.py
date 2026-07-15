from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/storage-locations", tags=["storage-locations"])


def get_storage_location_or_404(
    db: Session,
    location_id: int,
) -> models.StorageLocation:
    location = crud.get(db, models.StorageLocation, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Storage location not found")
    return location


def normalized_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Storage location name is required")
    return normalized


@router.post("", response_model=schemas.StorageLocationRead, status_code=status.HTTP_201_CREATED)
def create_storage_location(
    location_in: schemas.StorageLocationCreate,
    db: Session = Depends(get_db),
):
    try:
        location = models.StorageLocation(name=normalized_name(location_in.name))
        db.add(location)
        db.commit()
        db.refresh(location)
        return location
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Storage location already exists") from exc


@router.get("", response_model=list[schemas.StorageLocationRead])
def list_storage_locations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.StorageLocation, skip=skip, limit=limit)


@router.get("/{location_id}", response_model=schemas.StorageLocationRead)
def read_storage_location(location_id: int, db: Session = Depends(get_db)):
    return get_storage_location_or_404(db, location_id)


@router.patch("/{location_id}", response_model=schemas.StorageLocationRead)
def update_storage_location(
    location_id: int,
    location_in: schemas.StorageLocationUpdate,
    db: Session = Depends(get_db),
):
    location = get_storage_location_or_404(db, location_id)
    patch = location_in.model_dump(exclude_unset=True)
    if "name" not in patch:
        return location

    old_name = location.name
    location.name = normalized_name(patch["name"])
    try:
        db.add(location)
        db.flush()
        db.query(models.InventoryItem).filter(
            models.InventoryItem.storage_location == old_name,
        ).update({models.InventoryItem.storage_location: location.name})
        db.query(models.ProductGroup).filter(
            models.ProductGroup.default_storage_location == old_name,
        ).update({models.ProductGroup.default_storage_location: location.name})
        db.query(models.Food).filter(
            models.Food.storage_location == old_name,
        ).update({models.Food.storage_location: location.name})
        db.commit()
        db.refresh(location)
        return location
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Storage location could not be updated") from exc


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_location(location_id: int, db: Session = Depends(get_db)):
    location = get_storage_location_or_404(db, location_id)
    db.query(models.InventoryItem).filter(
        models.InventoryItem.storage_location == location.name,
    ).update({models.InventoryItem.storage_location: None})
    db.query(models.ProductGroup).filter(
        models.ProductGroup.default_storage_location == location.name,
    ).update({models.ProductGroup.default_storage_location: None})
    db.query(models.Food).filter(
        models.Food.storage_location == location.name,
    ).update({models.Food.storage_location: None})
    db.delete(location)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
