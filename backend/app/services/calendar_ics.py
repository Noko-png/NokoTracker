"""RFC 5545 file exchange. Imported recurrence sets retain their original rules."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from icalendar import Calendar, Event
import recurring_ical_events
from sqlalchemy.orm import Session

from .. import models, schemas
from .calendar_schedule import local_time, recurrence_starts


MAX_OCCURRENCES = 2000
MAX_EVENTS = 500


def localize_floating(component: Event, zone: ZoneInfo) -> None:
    def localized(value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=zone)
        if isinstance(value, tuple):
            parts = tuple(localized(part) for part in value)
            return value if all(before is after for before, after in zip(value, parts)) else parts
        return value

    for key in ("DTSTART", "DTEND", "RECURRENCE-ID", "RDATE", "EXDATE"):
        values = component.get(key, [])
        for value in values if isinstance(values, list) else [values]:
            dates = getattr(value, "dts", [value])
            changed = False
            for item in dates:
                before = item.dt
                after = localized(before)
                if after is not before:
                    item.dt = after
                    changed = True
            if changed:
                value.params["TZID"] = zone.key
    rules = component.get("RRULE", [])
    for rule in rules if isinstance(rules, list) else [rules]:
        if "UNTIL" in rule:
            rule["UNTIL"] = [localized(value).astimezone(timezone.utc) if isinstance(value, datetime) and value.tzinfo is None else value for value in rule["UNTIL"]]


def calendar_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, "Unbekannte Kalender-Zeitzone.") from exc


def local_datetime(value: date | datetime, zone: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(zone).replace(tzinfo=None) if value.tzinfo else value
    return datetime.combine(value, time.min)


def component_values(component: Event, zone: ZoneInfo) -> dict:
    start = component.decoded("DTSTART")
    if not isinstance(start, (date, datetime)):
        raise ValueError("DTSTART fehlt oder ist ungueltig.")
    if component["DTSTART"].params.get("TZID") and isinstance(start, datetime) and start.tzinfo is None:
        raise ValueError("Die Zeitzone von DTSTART kann nicht aufgeloest werden.")
    end = component.end
    all_day = not isinstance(start, datetime)
    if all_day != (not isinstance(end, datetime)) or end < start:
        raise ValueError("DTEND und DTSTART passen nicht zusammen.")
    if all_day and end <= start:
        raise ValueError("DTEND muss nach DTSTART liegen.")
    if "DTEND" in component and "DURATION" in component:
        raise ValueError("DTEND und DURATION duerfen nicht gemeinsam angegeben werden.")
    if len(str(component.get("DESCRIPTION", ""))) > 20_000:
        raise ValueError("Eine Terminbeschreibung darf maximal 20000 Zeichen enthalten.")
    end_at = local_datetime(end, zone)
    if all_day:
        # iCalendar DATE ends are exclusive; the existing UI uses inclusive days.
        end_at -= timedelta(microseconds=1)
    return dict(
        title=str(component.get("SUMMARY", "Ohne Titel")),
        description=str(component["DESCRIPTION"]) if "DESCRIPTION" in component else None,
        location=str(component["LOCATION"]) if "LOCATION" in component else None,
        start_at=local_datetime(start, zone), end_at=end_at, all_day=all_day,
    )


def _parse_calendar(content: str, timezone_name: str) -> tuple[list[dict], list[str]]:
    zone = calendar_zone(timezone_name)
    try:
        source = Calendar.from_ical(content.lstrip("\ufeff").encode("utf-8"))
        if source.name != "VCALENDAR" or str(source.get("VERSION")) != "2.0":
            raise ValueError("Eine VCALENDAR-Datei mit VERSION:2.0 wird benoetigt.")
        if any(component.errors for component in source.walk()):
            raise ValueError("Die ICS-Datei enthaelt ungueltige Eigenschaften.")
        grouped = defaultdict(list)
        warnings = []
        zones = [row for row in source.subcomponents if row.name == "VTIMEZONE"]
        components = [row for row in source.subcomponents if row.name == "VEVENT"]
        if not components or len(components) > MAX_EVENTS:
            raise ValueError(f"Die Datei muss zwischen 1 und {MAX_EVENTS} VEVENT-Eintraege enthalten.")
        if any(row.name not in {"VEVENT", "VTIMEZONE"} for row in source.subcomponents):
            warnings.append("Es werden nur Termine (VEVENT) importiert; andere Komponententypen werden ausgelassen.")
        if any(row.subcomponents for row in components):
            warnings.append("Erinnerungen werden nicht aktiviert. Anhaenge und externe Adressen werden nicht abgerufen.")
        for row in components:
            uid = str(row.get("UID", "")).strip()
            if not uid or len(uid) > 1024:
                raise ValueError("Jeder Termin benoetigt eine gueltige UID (maximal 1024 Zeichen).")
            if str(row.get("STATUS", "")).upper() == "CANCELLED" and "RECURRENCE-ID" in row and "DTSTART" not in row:
                # A cancelled override may omit DTSTART; the recurrence engine
                # still needs its original slot to suppress the occurrence.
                row.add("DTSTART", row.decoded("RECURRENCE-ID"))
            if str(row.get("STATUS", "")).upper() != "CANCELLED":
                component_values(row, zone)
            localize_floating(row, zone)
            row.subcomponents = []  # VALARM never schedules actions in NokoTracker.
            grouped[uid].append(row)
        result = []
        for uid, rows in grouped.items():
            masters = [row for row in rows if "RECURRENCE-ID" not in row]
            if len(masters) != 1:
                raise ValueError("Jede UID muss genau einen Basistermin enthalten; einzelne Serienausnahmen brauchen ihre Serie.")
            master = masters[0]
            if str(master.get("STATUS", "")).upper() == "CANCELLED" or str(source.get("METHOD", "")).upper() == "CANCEL":
                warnings.append(f"Abgesagter Termin ausgelassen: {str(master.get('SUMMARY', uid))[:200]}")
                continue
            calendar = Calendar()
            calendar.add("VERSION", "2.0")
            calendar.add("PRODID", "-//NokoTracker//iCalendar//DE")
            calendar.add("X-WR-TIMEZONE", timezone_name)
            for row in [*zones, *rows]:
                calendar.add_component(row)
            # Validate RRULE/RDATE/EXDATE and overrides before any database writes.
            recurring_ical_events.CalendarQuery(calendar)
            values = component_values(master, zone)
            schemas.CalendarEventCreate.model_validate(values)
            result.append(dict(**values, ics_uid=uid, ics_source=calendar.to_ical().decode("utf-8"), ics_timezone=timezone_name))
            if sum(len(entry["ics_source"].encode("utf-8")) for entry in result) > 8_000_000:
                raise ValueError("Die aufbereiteten ICS-Daten sind zu gross. Bitte die Datei aufteilen.")
        return result, warnings
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "ICS-Datei konnte nicht gelesen werden: " + str(exc)[:300]) from exc


def validate_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    start, end = local_time(start), local_time(end)
    if end <= start or end - start > timedelta(days=370):
        raise HTTPException(422, "Bitte einen Kalenderzeitraum zwischen 1 Sekunde und 370 Tagen waehlen.")
    return start, end


def _expand_records(events: list[dict], start: datetime, end: datetime, timezone_name: str) -> list[dict]:
    zone = calendar_zone(timezone_name)
    result = []
    for event in events:
        try:
            calendar = Calendar.from_ical(event["source"])
            exclusions = {datetime.fromisoformat(value) for value in event["exclusions"]}
            # Already localized floating values; bypass X-WR-TIMEZONE rewriting
            # so embedded VTIMEZONE definitions retain their original offsets.
            for row in recurring_ical_events.CalendarQuery(calendar).after(start.replace(tzinfo=zone)):
                if local_datetime(row.decoded("DTSTART"), zone) >= end:
                    break
                if str(row.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                values = component_values(row, zone)
                raw_start = row.decoded("DTSTART")
                original_zone = calendar_zone(event["timezone"] or "Europe/Berlin")
                stamp = raw_start if isinstance(raw_start, datetime) else datetime.combine(raw_start, time.min)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=original_zone)
                stamp = stamp.astimezone(timezone.utc)
                if values["start_at"] >= end:
                    break
                if stamp.replace(tzinfo=None) in exclusions or str(row.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                if len(result) >= MAX_OCCURRENCES:
                    raise HTTPException(422, "Zu viele ICS-Vorkommen. Bitte einen kuerzeren Zeitraum waehlen.")
                result.append({**values, "id": event["id"], "ics_occurrence_start_utc": stamp})
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, f"ICS-Termin '{event['title']}' konnte nicht berechnet werden.") from exc
    return result


def run_ics_worker(operation: str, data: dict):
    payload = json.dumps({"operation": operation, **data}, default=lambda value: value.isoformat()).encode("utf-8")
    if len(payload) > 20_000_000:
        raise HTTPException(422, "Zu viele ICS-Daten fuer eine Berechnung.")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.services.calendar_ics_worker"], input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8,
            cwd=Path(__file__).resolve().parents[2], env={**os.environ, "DATABASE_URL": "sqlite://"},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            raise ValueError("ICS-Verarbeitung abgebrochen.")
        response = json.loads(result.stdout)
        if "error" in response:
            raise HTTPException(422, response["error"])
        return response["result"]
    except HTTPException:
        raise
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        raise HTTPException(422, "ICS-Daten sind zu komplex oder ungueltig. Bitte die Datei oder den Zeitraum verkleinern.") from exc


def parse_calendar(content: str, timezone_name: str) -> tuple[list[dict], list[str]]:
    entries, warnings = run_ics_worker("parse", {"content": content, "timezone": timezone_name})
    for entry in entries:
        entry["start_at"] = datetime.fromisoformat(entry["start_at"])
        entry["end_at"] = datetime.fromisoformat(entry["end_at"])
    return entries, warnings


def imported_occurrences(db: Session, start: datetime, end: datetime, timezone_name: str) -> list[schemas.CalendarEventRead]:
    start, end = validate_range(start, end)
    calendar_zone(timezone_name)
    events = db.query(models.CalendarEvent).filter(models.CalendarEvent.ics_source.is_not(None)).order_by(models.CalendarEvent.id).all()
    if not events:
        return []
    records = [{"id": event.id, "title": event.title, "source": event.ics_source, "timezone": event.ics_timezone,
                "exclusions": [local_time(row.occurrence_start_at).isoformat() for row in event.exclusions]} for event in events]
    rows = run_ics_worker("expand", {"events": records, "start": start, "end": end, "timezone": timezone_name})
    by_id = {event.id: event for event in events}
    result = []
    for row in rows:
        for key in ("start_at", "end_at", "ics_occurrence_start_utc"):
            row[key] = datetime.fromisoformat(row[key])
        result.append(schemas.CalendarEventRead.model_validate(by_id[row.pop("id")]).model_copy(update={**row, "exclusions": []}))
    return result


def export_calendar(db: Session, start: datetime, end: datetime, timezone_name: str) -> bytes:
    start, end = validate_range(start, end)
    zone = calendar_zone(timezone_name)
    occurrences = imported_occurrences(db, start, end, timezone_name)
    events = db.query(models.CalendarEvent).filter(models.CalendarEvent.ics_source.is_(None), models.CalendarEvent.entry_type == "event").all()
    for event in events:
        duration = local_time(event.end_at) - local_time(event.start_at) if event.end_at else timedelta(hours=1)
        exclusions = {local_time(row.occurrence_start_at) for row in event.exclusions}
        for at in recurrence_starts(event, end):
            if at >= end:
                break
            until = at + duration
            if until <= start or at in exclusions:
                continue
            if len(occurrences) >= MAX_OCCURRENCES:
                raise HTTPException(422, "Zu viele Termine fuer diesen Export. Bitte einen kuerzeren Zeitraum waehlen.")
            occurrences.append(schemas.CalendarEventRead.model_validate(event).model_copy(update={"start_at": at, "end_at": until}))
    calendar = Calendar()
    calendar.add("PRODID", "-//NokoTracker//iCalendar//DE")
    calendar.add("VERSION", "2.0")
    calendar.add("CALSCALE", "GREGORIAN")
    for occurrence in occurrences:
        row = Event()
        identity = occurrence.ics_uid or f"{occurrence.id}:{occurrence.created_at.isoformat()}"
        uid = sha256(f"{identity}:{occurrence.id}:{occurrence.start_at.isoformat()}".encode()).hexdigest() + "@nokotracker"
        row.add("UID", uid)
        row.add("DTSTAMP", datetime.now(timezone.utc))
        row.add("SUMMARY", occurrence.title)
        if occurrence.description:
            row.add("DESCRIPTION", occurrence.description)
        if occurrence.location:
            row.add("LOCATION", occurrence.location)
        if occurrence.all_day:
            row.add("DTSTART", occurrence.start_at.date())
            row.add("DTEND", (occurrence.end_at or occurrence.start_at).date() + timedelta(days=1))
        else:
            row.add("DTSTART", occurrence.start_at.replace(tzinfo=zone).astimezone(timezone.utc))
            row.add("DTEND", (occurrence.end_at or occurrence.start_at).replace(tzinfo=zone).astimezone(timezone.utc))
        calendar.add_component(row)
    return calendar.to_ical()
