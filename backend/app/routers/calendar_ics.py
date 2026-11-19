from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import current_principal
from ..services.calendar_ics import export_calendar, imported_occurrences, parse_calendar
from .calendar import ensure_group_exists, ensure_user_exists


router = APIRouter(prefix="/calendar/ics", tags=["calendar"])


@router.post("/import", response_model=schemas.CalendarIcsImportResult, status_code=201)
def import_ics(request: schemas.CalendarIcsImportRequest, db: Session = Depends(get_db)):
    if not request.filename.lower().endswith(".ics") or len(request.content.encode("utf-8")) > 2_000_000:
        raise HTTPException(422, "Bitte eine .ics-Datei mit maximal 2 MB auswaehlen.")
    principal = db.info.get("principal") or current_principal.get()
    user_id = request.user_id
    if principal is not None and not principal.is_admin:
        if principal.user_id is None or user_id not in (None, principal.user_id):
            raise HTTPException(403, "ICS-Termine koennen nur im eigenen Namen importiert werden.")
        user_id = principal.user_id
    ensure_group_exists(db, request.group_id)
    ensure_user_exists(db, user_id)
    entries, warnings = parse_calendar(request.content, request.timezone)
    imported = updated = skipped = 0
    try:
        for entry in entries:
            duplicate = db.query(models.CalendarEvent).filter(
                models.CalendarEvent.ics_uid == entry["ics_uid"],
                models.CalendarEvent.user_id == user_id,
            ).first()
            if duplicate is not None:
                if not duplicate.is_ics or all(getattr(duplicate, key) == value for key, value in entry.items()):
                    skipped += 1
                    continue
                for key, value in entry.items():
                    setattr(duplicate, key, value)
                updated += 1
                continue
            db.add(models.CalendarEvent(**entry, user_id=user_id, group_id=request.group_id))
            db.flush()
            imported += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return schemas.CalendarIcsImportResult(imported_count=imported, updated_count=updated, skipped_count=skipped, warnings=warnings)


@router.get("/occurrences", response_model=list[schemas.CalendarEventRead])
def read_ics_occurrences(start: datetime, end: datetime, timezone: str = Query("Europe/Berlin", max_length=64), db: Session = Depends(get_db)):
    return imported_occurrences(db, start, end, timezone)


@router.get("/export")
def download_ics(start: datetime, end: datetime, timezone: str = Query("Europe/Berlin", max_length=64), db: Session = Depends(get_db)):
    content = export_calendar(db, start, end, timezone)
    return Response(content, media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="nokotracker-kalender.ics"'})
