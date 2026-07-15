from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/product-units", tags=["product-units"])


def get_product_unit_or_404(db: Session, unit_id: int) -> models.ProductUnit:
    product_unit = crud.get(db, models.ProductUnit, unit_id)
    if product_unit is None:
        raise HTTPException(status_code=404, detail="Product unit not found")
    return product_unit


@router.post("", response_model=schemas.ProductUnitRead, status_code=status.HTTP_201_CREATED)
def create_product_unit(
    unit_in: schemas.ProductUnitCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.create(db, models.ProductUnit, unit_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product unit already exists") from exc


@router.get("", response_model=list[schemas.ProductUnitRead])
def list_product_units(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.ProductUnit, skip=skip, limit=limit)


@router.get("/{unit_id}", response_model=schemas.ProductUnitRead)
def read_product_unit(unit_id: int, db: Session = Depends(get_db)):
    return get_product_unit_or_404(db, unit_id)


@router.patch("/{unit_id}", response_model=schemas.ProductUnitRead)
def update_product_unit(
    unit_id: int,
    unit_in: schemas.ProductUnitUpdate,
    db: Session = Depends(get_db),
):
    product_unit = get_product_unit_or_404(db, unit_id)
    try:
        return crud.update(db, product_unit, unit_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product unit could not be updated") from exc


@router.delete("/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_unit(unit_id: int, db: Session = Depends(get_db)):
    product_unit = get_product_unit_or_404(db, unit_id)
    for food in product_unit.foods:
        food.product_unit_id = None
    for item in product_unit.inventory_items:
        item.product_unit_id = None
    crud.delete(db, product_unit)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
