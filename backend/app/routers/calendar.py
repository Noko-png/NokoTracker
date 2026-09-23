from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/calendar/events", tags=["calendar"])
groups_router = APIRouter(prefix="/calendar/groups", tags=["calendar"])


def get_event_or_404(db: Session, event_id: int) -> models.CalendarEvent:
    event = crud.get(db, models.CalendarEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return event


def ensure_user_exists(db: Session, user_id: int | None) -> None:
    if user_id is not None and crud.get(db, models.User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")


def ensure_group_exists(db: Session, group_id: int | None) -> None:
    if group_id is not None and crud.get(db, models.CalendarGroup, group_id) is None:
        raise HTTPException(status_code=404, detail="Calendar group not found")


def ensure_suppressed_groups_exist(
    db: Session,
    group_ids: list[int] | None,
    own_group_id: int | None = None,
) -> None:
    for group_id in group_ids or []:
        if own_group_id is not None and group_id == own_group_id:
            raise HTTPException(status_code=422, detail="Calendar group cannot suppress itself")
        ensure_group_exists(db, group_id)


def get_group_or_404(db: Session, group_id: int) -> models.CalendarGroup:
    group = crud.get(db, models.CalendarGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Calendar group not found")
    return group


@router.post("", response_model=schemas.CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(event_in: schemas.CalendarEventCreate, db: Session = Depends(get_db)):
    ensure_user_exists(db, event_in.user_id)
    ensure_group_exists(db, event_in.group_id)
    try:
        return crud.create(db, models.CalendarEvent, event_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar event could not be created") from exc


@router.get("", response_model=list[schemas.CalendarEventRead])
def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.CalendarEvent, skip=skip, limit=limit)


@router.get("/{event_id}", response_model=schemas.CalendarEventRead)
def read_event(event_id: int, db: Session = Depends(get_db)):
    return get_event_or_404(db, event_id)


@router.patch("/{event_id}", response_model=schemas.CalendarEventRead)
def update_event(
    event_id: int,
    event_in: schemas.CalendarEventUpdate,
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    ensure_user_exists(db, event_in.user_id)
    ensure_group_exists(db, event_in.group_id)
    try:
        return crud.update(db, event, event_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar event could not be updated") from exc


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    crud.delete(db, event)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{event_id}/exclusions",
    response_model=schemas.CalendarEventExclusionRead,
    status_code=status.HTTP_201_CREATED,
)
def exclude_event_occurrence(
    event_id: int,
    exclusion_in: schemas.CalendarEventExclusionRequest,
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    if event.recurrence_frequency == "none":
        raise HTTPException(status_code=409, detail="Only recurring entries support exclusions")

    exclusion = schemas.CalendarEventExclusionCreate(
        event_id=event.id,
        occurrence_start_at=exclusion_in.occurrence_start_at,
    )
    try:
        return crud.create(db, models.CalendarEventExclusion, exclusion)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar occurrence is already excluded") from exc


@groups_router.post("", response_model=schemas.CalendarGroupRead, status_code=status.HTTP_201_CREATED)
def create_group(group_in: schemas.CalendarGroupCreate, db: Session = Depends(get_db)):
    ensure_user_exists(db, group_in.user_id)
    ensure_suppressed_groups_exist(db, group_in.suppresses_group_ids)
    try:
        return crud.create(db, models.CalendarGroup, group_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar group could not be created") from exc


@groups_router.get("", response_model=list[schemas.CalendarGroupRead])
def list_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.CalendarGroup, skip=skip, limit=limit)


@groups_router.patch("/{group_id}", response_model=schemas.CalendarGroupRead)
def update_group(
    group_id: int,
    group_in: schemas.CalendarGroupUpdate,
    db: Session = Depends(get_db),
):
    group = get_group_or_404(db, group_id)
    ensure_user_exists(db, group_in.user_id)
    ensure_suppressed_groups_exist(db, group_in.suppresses_group_ids, group.id)
    try:
        return crud.update(db, group, group_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar group could not be updated") from exc


@groups_router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = get_group_or_404(db, group_id)
    for other_group in db.query(models.CalendarGroup).all():
        suppressed_ids = other_group.suppresses_group_ids or []
        if group.id in suppressed_ids:
            other_group.suppresses_group_ids = [
                suppressed_id
                for suppressed_id in suppressed_ids
                if suppressed_id != group.id
            ]
            db.add(other_group)
    crud.delete(db, group)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
