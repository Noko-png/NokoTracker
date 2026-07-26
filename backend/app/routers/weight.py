from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/weight-entries", tags=["weight"])


def get_weight_entry_or_404(db: Session, entry_id: int) -> models.WeightEntry:
    entry = crud.get(db, models.WeightEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Weight entry not found")
    return entry


def ensure_user_exists(db: Session, user_id: int | None) -> None:
    if user_id is not None and crud.get(db, models.User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("", response_model=list[schemas.WeightEntryRead])
def list_weight_entries(
    user_id: int | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(models.WeightEntry)
    if user_id is not None:
        query = query.filter(models.WeightEntry.user_id == user_id)
    return (
        query.order_by(models.WeightEntry.measured_at.desc(), models.WeightEntry.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("", response_model=schemas.WeightEntryRead, status_code=status.HTTP_201_CREATED)
def create_weight_entry(
    entry_in: schemas.WeightEntryCreate,
    db: Session = Depends(get_db),
):
    ensure_user_exists(db, entry_in.user_id)
    return crud.create(db, models.WeightEntry, entry_in)


@router.patch("/{entry_id}", response_model=schemas.WeightEntryRead)
def update_weight_entry(
    entry_id: int,
    entry_in: schemas.WeightEntryUpdate,
    db: Session = Depends(get_db),
):
    entry = get_weight_entry_or_404(db, entry_id)
    ensure_user_exists(db, entry_in.user_id)
    return crud.update(db, entry, entry_in)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weight_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = get_weight_entry_or_404(db, entry_id)
    crud.delete(db, entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
