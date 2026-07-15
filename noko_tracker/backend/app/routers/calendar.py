from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/calendar/events", tags=["calendar"])
groups_router = APIRouter(prefix="/calendar/groups", tags=["calendar"])

MAX_RECURRENCE_OCCURRENCES = 4000
MIN_EVENT_SEGMENT = timedelta(minutes=1)


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


def event_duration(event: models.CalendarEvent) -> timedelta:
    if event.all_day:
        start_day = event.start_at.replace(hour=0, minute=0, second=0, microsecond=0)
        end_at = event.end_at or event.start_at
        end_day = end_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_count = (end_day.date() - start_day.date()).days + 1
        return timedelta(days=max(day_count, 1))
    if event.end_at is not None and event.end_at >= event.start_at:
        duration = event.end_at - event.start_at
        return duration if duration.total_seconds() > 0 else timedelta(minutes=1)
    return timedelta(hours=1)


def interval_end(start_at: datetime, duration: timedelta) -> datetime:
    return start_at + duration


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


def subtract_intervals(
    target_start: datetime,
    target_end: datetime,
    blocked_intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    remaining = [(target_start, target_end)]
    for blocked_start, blocked_end in blocked_intervals:
        next_remaining: list[tuple[datetime, datetime]] = []
        for current_start, current_end in remaining:
            if not intervals_overlap(current_start, current_end, blocked_start, blocked_end):
                next_remaining.append((current_start, current_end))
                continue

            before_end = min(blocked_start, current_end)
            after_start = max(blocked_end, current_start)
            if before_end - current_start >= MIN_EVENT_SEGMENT:
                next_remaining.append((current_start, before_end))
            if current_end - after_start >= MIN_EVENT_SEGMENT:
                next_remaining.append((after_start, current_end))
        remaining = next_remaining
        if not remaining:
            break
    return remaining


def start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def exclusive_day_end(value: datetime) -> datetime:
    day_start = start_of_day(value)
    if value == day_start:
        return day_start
    return day_start + timedelta(days=1)


def normalize_suppression_intervals_for_target(
    target_event: models.CalendarEvent,
    target_start: datetime,
    target_end: datetime,
    blocked_intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    if not target_event.all_day:
        return blocked_intervals

    normalized: list[tuple[datetime, datetime]] = []
    for blocked_start, blocked_end in blocked_intervals:
        if not intervals_overlap(blocked_start, blocked_end, target_start, target_end):
            continue
        day_start = max(start_of_day(blocked_start), target_start)
        day_end = min(exclusive_day_end(blocked_end), target_end)
        if day_end - day_start >= MIN_EVENT_SEGMENT:
            normalized.append((day_start, day_end))
    return normalized


def stored_event_segment_end(
    source: models.CalendarEvent,
    segment_start: datetime,
    segment_end: datetime,
) -> datetime:
    if not source.all_day:
        return segment_end
    return max(segment_start, segment_end - timedelta(minutes=1))


def remaining_event_segments(
    target_event: models.CalendarEvent,
    target_start: datetime,
    target_end: datetime,
    blocked_intervals: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    normalized_blocked_intervals = normalize_suppression_intervals_for_target(
        target_event,
        target_start,
        target_end,
        blocked_intervals,
    )
    return subtract_intervals(target_start, target_end, normalized_blocked_intervals)


def clone_calendar_event_segment(
    source: models.CalendarEvent,
    start_at: datetime,
    end_at: datetime,
) -> models.CalendarEvent:
    return models.CalendarEvent(
        title=source.title,
        description=source.description,
        start_at=start_at,
        end_at=stored_event_segment_end(source, start_at, end_at),
        location=source.location,
        entry_type=source.entry_type,
        all_day=source.all_day,
        is_completed=source.is_completed,
        recurrence_frequency="none",
        recurrence_interval=1,
        recurrence_until=None,
        user_id=source.user_id,
        group_id=source.group_id,
    )


def add_recurrence_step(
    value: datetime,
    frequency: str,
    interval: int,
) -> datetime:
    interval = max(interval, 1)
    if frequency == "daily":
        return value + timedelta(days=interval)
    if frequency == "weekly":
        return value + timedelta(weeks=interval)
    if frequency == "monthly":
        month_index = value.month - 1 + interval
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(
            value.day,
            29 if month == 2 and year % 4 == 0 else
            28 if month == 2 else
            30 if month in {4, 6, 9, 11} else
            31,
        )
        return value.replace(year=year, month=month, day=day)
    if frequency == "yearly":
        try:
            return value.replace(year=value.year + interval)
        except ValueError:
            return value.replace(year=value.year + interval, month=2, day=28)
    return value + timedelta(days=1)


def event_occurrences_between(
    event: models.CalendarEvent,
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    duration = event_duration(event)
    frequency = event.recurrence_frequency or "none"
    excluded_starts = {exclusion.occurrence_start_at for exclusion in event.exclusions}

    if frequency == "none":
        occurrence_end = interval_end(event.start_at, duration)
        if intervals_overlap(event.start_at, occurrence_end, range_start, range_end):
            return [(event.start_at, occurrence_end)]
        return []

    occurrences: list[tuple[datetime, datetime]] = []
    occurrence_start = event.start_at
    recurrence_until = event.recurrence_until
    count = 0
    while count < MAX_RECURRENCE_OCCURRENCES and occurrence_start <= range_end:
        if recurrence_until is not None and occurrence_start > recurrence_until:
            break
        occurrence_end = interval_end(occurrence_start, duration)
        if (
            intervals_overlap(occurrence_start, occurrence_end, range_start, range_end)
            and occurrence_start not in excluded_starts
        ):
            occurrences.append((occurrence_start, occurrence_end))
        occurrence_start = add_recurrence_step(
            occurrence_start,
            frequency,
            event.recurrence_interval,
        )
        count += 1
    return occurrences


def suppression_intervals(event: models.CalendarEvent) -> list[tuple[datetime, datetime]]:
    duration = event_duration(event)
    return [(event.start_at, interval_end(event.start_at, duration))]


def apply_calendar_group_suppression(
    db: Session,
    source_event: models.CalendarEvent,
) -> None:
    if source_event.group_id is None or source_event.group is None:
        return

    suppressed_group_ids = [
        group_id
        for group_id in (source_event.group.suppresses_group_ids or [])
        if group_id != source_event.group_id
    ]
    if not suppressed_group_ids:
        return

    source_intervals = suppression_intervals(source_event)
    if not source_intervals:
        return

    range_start = min(start for start, _ in source_intervals)
    range_end = max(end for _, end in source_intervals)
    target_events = (
        db.query(models.CalendarEvent)
        .filter(models.CalendarEvent.group_id.in_(suppressed_group_ids))
        .filter(models.CalendarEvent.id != source_event.id)
        .all()
    )

    changed = False
    for target_event in target_events:
        target_occurrences = event_occurrences_between(target_event, range_start, range_end)
        for target_start, target_end in target_occurrences:
            overlapping_source_intervals = [
                (source_start, source_end)
                for source_start, source_end in source_intervals
                if intervals_overlap(source_start, source_end, target_start, target_end)
            ]
            if not overlapping_source_intervals:
                continue

            if target_event.recurrence_frequency == "none":
                remaining_segments = remaining_event_segments(
                    target_event,
                    target_start,
                    target_end,
                    overlapping_source_intervals,
                )
                if not remaining_segments:
                    db.delete(target_event)
                else:
                    first_start, first_end = remaining_segments[0]
                    target_event.start_at = first_start
                    target_event.end_at = stored_event_segment_end(
                        target_event,
                        first_start,
                        first_end,
                    )
                    db.add(target_event)
                    for segment_start, segment_end in remaining_segments[1:]:
                        db.add(
                            clone_calendar_event_segment(
                                target_event,
                                segment_start,
                                segment_end,
                            )
                        )
                changed = True
                break

            already_excluded = any(
                exclusion.occurrence_start_at == target_start
                for exclusion in target_event.exclusions
            )
            if not already_excluded:
                remaining_segments = remaining_event_segments(
                    target_event,
                    target_start,
                    target_end,
                    overlapping_source_intervals,
                )
                db.add(
                    models.CalendarEventExclusion(
                        event_id=target_event.id,
                        occurrence_start_at=target_start,
                    )
                )
                for segment_start, segment_end in remaining_segments:
                    db.add(
                        clone_calendar_event_segment(
                            target_event,
                            segment_start,
                            segment_end,
                        )
                    )
                changed = True

    if changed:
        db.commit()


@router.post("", response_model=schemas.CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(event_in: schemas.CalendarEventCreate, db: Session = Depends(get_db)):
    ensure_user_exists(db, event_in.user_id)
    ensure_group_exists(db, event_in.group_id)
    try:
        event = crud.create(db, models.CalendarEvent, event_in)
        apply_calendar_group_suppression(db, event)
        db.refresh(event)
        return event
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
        updated_event = crud.update(db, event, event_in)
        apply_calendar_group_suppression(db, updated_event)
        db.refresh(updated_event)
        return updated_event
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
