from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/users", tags=["users"])


def get_user_or_404(db: Session, user_id: int) -> models.User:
    user = crud.get(db, models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_username(db, user_in.username):
        raise HTTPException(status_code=409, detail="Username already exists")
    try:
        return crud.create(db, models.User, user_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User could not be created") from exc


@router.get("", response_model=list[schemas.UserRead])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.User, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=schemas.UserRead)
def read_user(user_id: int, db: Session = Depends(get_db)):
    return get_user_or_404(db, user_id)


@router.patch("/{user_id}", response_model=schemas.UserRead)
def update_user(user_id: int, user_in: schemas.UserUpdate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if (
        user_in.username
        and user_in.username != user.username
        and crud.get_user_by_username(db, user_in.username)
    ):
        raise HTTPException(status_code=409, detail="Username already exists")
    try:
        return crud.update(db, user, user_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User could not be updated") from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if db.query(models.User).count() <= 1:
        raise HTTPException(status_code=409, detail="At least one user must remain")
    try:
        crud.delete(db, user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User is still referenced") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
