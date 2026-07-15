from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/product-groups", tags=["product-groups"])


def get_product_group_or_404(db: Session, group_id: int) -> models.ProductGroup:
    product_group = crud.get(db, models.ProductGroup, group_id)
    if product_group is None:
        raise HTTPException(status_code=404, detail="Product group not found")
    return product_group


@router.post("", response_model=schemas.ProductGroupRead, status_code=status.HTTP_201_CREATED)
def create_product_group(
    group_in: schemas.ProductGroupCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.create(db, models.ProductGroup, group_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product group already exists") from exc


@router.get("", response_model=list[schemas.ProductGroupRead])
def list_product_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.ProductGroup, skip=skip, limit=limit)


@router.get("/{group_id}", response_model=schemas.ProductGroupRead)
def read_product_group(group_id: int, db: Session = Depends(get_db)):
    return get_product_group_or_404(db, group_id)


@router.patch("/{group_id}", response_model=schemas.ProductGroupRead)
def update_product_group(
    group_id: int,
    group_in: schemas.ProductGroupUpdate,
    db: Session = Depends(get_db),
):
    product_group = get_product_group_or_404(db, group_id)
    try:
        return crud.update(db, product_group, group_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Product group could not be updated") from exc


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_group(group_id: int, db: Session = Depends(get_db)):
    product_group = get_product_group_or_404(db, group_id)
    for food in product_group.foods:
        food.product_group_id = None
    for item in product_group.inventory_items:
        item.product_group_id = None
    crud.delete(db, product_group)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
