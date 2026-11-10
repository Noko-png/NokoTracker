"""Calendar recurrence in local wall-clock time, shared by skip and training links."""
from calendar import monthrange
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models


def local_time(value: datetime) -> datetime:
    # The calendar API stores local wall-clock timestamps, just like datetime-local.
    return value.replace(tzinfo=None)


def recurrence_starts(event: models.CalendarEvent, range_end: datetime):
    base = local_time(event.start_at)
    range_end = local_time(range_end)
    until = min(local_time(event.recurrence_until), range_end) if event.recurrence_until else range_end
    frequency = event.recurrence_frequency
    interval = event.recurrence_interval
    shifts = sorted(event.shifts, key=lambda shift: shift.id)
    index = 0
    while True:
        try:
            if frequency == "cycle":
                training_days = event.cycle_training_days
                cycle_days = training_days + event.cycle_rest_days
                start = base + timedelta(days=(index // training_days) * cycle_days + index % training_days)
                for shift in shifts:
                    if start >= local_time(shift.occurrence_start_at):
                        start += timedelta(days=shift.days)
            elif frequency in {"daily", "weekly", "weekdays", "weekends"}:
                days = index if frequency in {"weekdays", "weekends"} else index * interval * (7 if frequency == "weekly" else 1)
                start = base + timedelta(days=days)
            elif frequency in {"monthly", "yearly"}:
                months = base.year * 12 + base.month - 1 + index * interval * (12 if frequency == "yearly" else 1)
                year, month = divmod(months, 12)
                month += 1
                start = base.replace(year=year, month=month, day=min(base.day, monthrange(year, month)[1]))
            else:
                start = base
        except (OverflowError, ValueError):
            return
        if start > until:
            return
        matches = True
        if frequency in {"weekdays", "weekends"}:
            week_start = base.date() - timedelta(days=base.weekday())
            start_week = start.date() - timedelta(days=start.weekday())
            matches = ((start_week - week_start).days // 7) % interval == 0
            matches = matches and (start.weekday() < 5 if frequency == "weekdays" else start.weekday() >= 5)
        if matches:
            yield start
        if frequency == "none":
            return
        index += 1


def ensure_occurrence(event: models.CalendarEvent, value: datetime) -> datetime:
    target = local_time(value)
    if any(local_time(item.occurrence_start_at) == target for item in event.exclusions):
        raise HTTPException(409, "Dieser Trainingstermin wurde entfernt.")
    if target not in recurrence_starts(event, target):
        raise HTTPException(422, "Der Zeitpunkt gehoert nicht zu dieser Terminserie.")
    return target


def ensure_training_event(db: Session, event: models.CalendarEvent) -> models.TrainingPlan:
    plan = db.query(models.TrainingPlan).filter(models.TrainingPlan.id == event.training_plan_id).first()
    if not plan:
        raise HTTPException(404, "Der verknuepfte Trainingsplan ist nicht verfuegbar.")
    principal = db.info.get("principal")
    if principal and not principal.is_admin and plan.user_id != principal.user_id:
        raise HTTPException(403, "Dieser Trainingsplan gehoert zu einem anderen Profil.")
    return plan


def ensure_no_completed_from(db: Session, event: models.CalendarEvent, target: datetime):
    if db.query(models.TrainingSession).filter(
        models.TrainingSession.calendar_event_id == event.id,
        models.TrainingSession.calendar_occurrence_start_at >= target,
    ).first():
        raise HTTPException(409, "Bereits protokollierte Trainings duerfen nicht verschoben werden.")
