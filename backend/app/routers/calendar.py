from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import ValidationError
from datetime import timedelta

from .. import crud, models, schemas
from ..database import get_db
from ..services.calendar_schedule import ensure_occurrence, ensure_training_event, ensure_no_completed_from, local_time


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


def validate_training_link(db: Session, event_in: schemas.CalendarEventBase) -> None:
    if event_in.training_plan_id is None:
        return
    plan = db.query(models.TrainingPlan).filter(models.TrainingPlan.id == event_in.training_plan_id).first()
    if plan is None:
        raise HTTPException(404, "Trainingsplan nicht gefunden.")
    if event_in.entry_type != "event":
        raise HTTPException(422, "Nur Kalendertermine koennen mit Trainingsplaenen verknuepft werden.")
    if event_in.user_id != plan.user_id:
        raise HTTPException(422, "Kalendertermin und Trainingsplan muessen zum gleichen Profil gehoeren.")


SCHEDULE_FIELDS = {
    "start_at", "end_at", "all_day", "entry_type", "recurrence_frequency", "recurrence_interval",
    "recurrence_until", "cycle_training_days", "cycle_rest_days", "training_plan_id", "user_id",
}


@router.post("", response_model=schemas.CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(event_in: schemas.CalendarEventCreate, db: Session = Depends(get_db)):
    ensure_user_exists(db, event_in.user_id)
    ensure_group_exists(db, event_in.group_id)
    validate_training_link(db, event_in)
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
    data = {name: getattr(event, name) for name in schemas.CalendarEventBase.model_fields}
    data.update(event_in.model_dump(exclude_unset=True))
    try:
        merged = schemas.CalendarEventBase.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    ensure_user_exists(db, merged.user_id)
    ensure_group_exists(db, merged.group_id)
    validate_training_link(db, merged)
    schedule_changed = any(getattr(event, name) != getattr(merged, name) for name in SCHEDULE_FIELDS)
    if schedule_changed and (event.shifts or event.training_sessions):
        raise HTTPException(409, "Diese Serie hat Pausentage oder protokollierte Trainings. Fuer einen neuen Rhythmus bitte eine neue Serie anlegen.")
    try:
        return crud.update(db, event, event_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar event could not be updated") from exc


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    if event.training_plan_id is not None:
        ensure_training_event(db, event)
    for training_session in event.training_sessions:
        training_session.calendar_occurrence_start_at = None
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
    if event.training_plan_id is not None:
        ensure_training_event(db, event)
        target = ensure_occurrence(event, exclusion_in.occurrence_start_at)
        if db.query(models.TrainingSession).filter(
            models.TrainingSession.calendar_event_id == event.id,
            models.TrainingSession.calendar_occurrence_start_at == target,
        ).first():
            raise HTTPException(409, "Ein protokolliertes Training kann nicht aus dem Kalender entfernt werden.")

    exclusion = schemas.CalendarEventExclusionCreate(
        event_id=event.id,
        occurrence_start_at=exclusion_in.occurrence_start_at,
    )
    try:
        return crud.create(db, models.CalendarEventExclusion, exclusion)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Calendar occurrence is already excluded") from exc


@router.post("/{event_id}/skip", response_model=schemas.CalendarEventRead)
def skip_training_occurrence(
    event_id: int,
    skip_in: schemas.CalendarEventExclusionRequest,
    db: Session = Depends(get_db),
):
    event = get_event_or_404(db, event_id)
    ensure_training_event(db, event)
    if event.recurrence_frequency != "cycle":
        raise HTTPException(409, "Zusaetzliche Pausentage sind nur fuer Trainingsrhythmen verfuegbar.")
    target = ensure_occurrence(event, skip_in.occurrence_start_at)
    ensure_no_completed_from(db, event, target)
    event.shifts.append(models.CalendarEventShift(occurrence_start_at=target, days=1))
    # Move later exclusions first so adjacent dates cannot temporarily collide
    # with the unique (event_id, occurrence_start_at) constraint.
    for exclusion in sorted(event.exclusions, key=lambda item: local_time(item.occurrence_start_at), reverse=True):
        if local_time(exclusion.occurrence_start_at) >= target:
            exclusion.occurrence_start_at = local_time(exclusion.occurrence_start_at) + timedelta(days=1)
            db.flush([exclusion])
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}/shifts/{shift_id}", response_model=schemas.CalendarEventRead)
def undo_training_skip(event_id: int, shift_id: int, db: Session = Depends(get_db)):
    event = get_event_or_404(db, event_id)
    ensure_training_event(db, event)
    shift = next((item for item in event.shifts if item.id == shift_id), None)
    if shift is None:
        raise HTTPException(404, "Pausentag nicht gefunden.")
    if shift.id != max(item.id for item in event.shifts):
        raise HTTPException(409, "Bitte zuerst den zuletzt eingefuegten Pausentag zuruecknehmen.")
    target = local_time(shift.occurrence_start_at)
    ensure_no_completed_from(db, event, target)
    for exclusion in sorted(event.exclusions, key=lambda item: local_time(item.occurrence_start_at)):
        if local_time(exclusion.occurrence_start_at) >= target + timedelta(days=shift.days):
            exclusion.occurrence_start_at = local_time(exclusion.occurrence_start_at) - timedelta(days=shift.days)
            db.flush([exclusion])
    event.shifts.remove(shift)
    db.commit()
    db.refresh(event)
    return event


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
