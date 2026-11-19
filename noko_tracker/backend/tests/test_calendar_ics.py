import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import patch
from urllib.parse import urlencode

from fastapi import FastAPI
from icalendar import Calendar
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas, security
from app.database import Base, get_db
from app.routers import calendar, calendar_ics
from app.services.calendar_ics import export_calendar
from test_security import request


def ics(*components):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//DE", *components, "END:VCALENDAR", ""])


def event(uid="one@test", start="DTSTART;TZID=Europe/Berlin:20261024T100000", *properties):
    return "\r\n".join(["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20261001T080000Z", start, "SUMMARY:Testtermin", *properties, "END:VEVENT"])


class CalendarIcsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        self.app.include_router(calendar.router)
        self.app.include_router(calendar.groups_router)
        self.app.include_router(calendar_ics.router)
        security.install_security(self.app)

        def database():
            with Session(self.engine, autoflush=False) as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        environment = patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)

    def call(self, method, path, payload=None, status=200):
        actual, result = asyncio.run(request(self.app, method, path, payload, peer="127.0.0.1"))
        self.assertEqual(actual, status, result)
        return result

    def import_file(self, content, status=201, **values):
        return self.call("POST", "/calendar/ics/import", {"filename": "termine.ics", "content": content, **values}, status)

    def occurrences(self, start="2026-10-01T00:00:00", end="2026-11-01T00:00:00", timezone="Europe/Berlin", status=200):
        return self.call("GET", "/calendar/ics/occurrences?" + urlencode({"start": start, "end": end, "timezone": timezone}), status=status)

    def test_utc_dates_duration_text_escaping_and_folded_lines(self):
        self.import_file(ics(event("utc@test", "DTSTART:20261024T080000Z", "DURATION:PT90M",
                                   "DESCRIPTION:Zeile 1\\nZeile 2\\, mit Semikolon\\;",
                                   "LOCATION:Raum\\, Berlin", "X-TEST:lang\r\n er Wert")))
        row, = self.occurrences()
        self.assertEqual((row["start_at"], row["end_at"]), ("2026-10-24T10:00:00", "2026-10-24T11:30:00"))
        self.assertEqual(row["description"], "Zeile 1\nZeile 2, mit Semikolon;")
        self.assertEqual(row["location"], "Raum, Berlin")
        self.assertTrue(row["is_ics"])
        self.assertFalse(row["ics_is_series"])

    def test_all_day_end_is_exclusive_and_single_date_defaults_to_one_day(self):
        self.import_file(ics(event("holiday@test", "DTSTART;VALUE=DATE:20261024", "DTEND;VALUE=DATE:20261027"),
                             event("day@test", "DTSTART;VALUE=DATE:20261028")))
        rows = {row["ics_uid"]: row for row in self.occurrences()}
        self.assertEqual(rows["holiday@test"]["end_at"], "2026-10-26T23:59:59.999999")
        self.assertEqual(rows["day@test"]["end_at"], "2026-10-28T23:59:59.999999")
        self.assertTrue(all(row["all_day"] for row in rows.values()))

    def test_daily_series_stays_at_local_time_across_daylight_saving(self):
        self.import_file(ics(event("dst@test", "DTSTART;TZID=Europe/Berlin:20261024T100000", "RRULE:FREQ=DAILY;COUNT=4")))
        rows = self.occurrences()
        self.assertEqual([row["start_at"] for row in rows], [f"2026-10-{day}T10:00:00" for day in (24, 25, 26, 27)])
        self.assertTrue(all(row["ics_is_series"] for row in rows))
        utc = self.occurrences(timezone="UTC")
        self.assertEqual([row["start_at"][-8:] for row in utc], ["08:00:00", "09:00:00", "09:00:00", "09:00:00"])

    def test_rrule_exdate_rdate_and_changed_single_occurrence(self):
        self.import_file(ics(
            event("series@test", "DTSTART;TZID=Europe/Berlin:20261020T100000", "RRULE:FREQ=DAILY;COUNT=4",
                  "EXDATE;TZID=Europe/Berlin:20261021T100000", "RDATE;TZID=Europe/Berlin:20261026T100000"),
            event("series@test", "DTSTART;TZID=Europe/Berlin:20261022T130000", "RECURRENCE-ID;TZID=Europe/Berlin:20261022T100000"),
        ))
        rows = self.occurrences()
        self.assertEqual([row["start_at"] for row in rows], ["2026-10-20T10:00:00", "2026-10-22T13:00:00", "2026-10-23T10:00:00", "2026-10-26T10:00:00"])

    def test_complex_monthly_rule_uses_standard_byday_and_setpos(self):
        self.import_file(ics(event("monthly@test", "DTSTART;TZID=Europe/Berlin:20261013T100000",
                                   "RRULE:FREQ=MONTHLY;BYDAY=TU;BYSETPOS=2;COUNT=3")))
        rows = self.occurrences(end="2027-01-01T00:00:00")
        self.assertEqual([row["start_at"][:10] for row in rows], ["2026-10-13", "2026-11-10", "2026-12-08"])

    def test_floating_dates_use_import_timezone(self):
        self.import_file(ics(event("floating@test", "DTSTART:20261024T100000")), timezone="America/New_York")
        row, = self.occurrences()
        self.assertEqual(row["start_at"], "2026-10-24T16:00:00")

    def test_embedded_vtimezone_is_used(self):
        zone = "\r\n".join(["BEGIN:VTIMEZONE", "TZID:Test/Custom", "BEGIN:STANDARD", "DTSTART:19700101T000000",
                              "TZOFFSETFROM:+0230", "TZOFFSETTO:+0230", "END:STANDARD", "END:VTIMEZONE"])
        self.import_file(ics(zone, event("custom@test", "DTSTART;TZID=Test/Custom:20261024T100000")))
        row, = self.occurrences()
        self.assertEqual(row["start_at"], "2026-10-24T09:30:00")

    def test_cancelled_single_occurrence_is_omitted(self):
        cancelled = "\r\n".join(["BEGIN:VEVENT", "UID:cancel@test", "RECURRENCE-ID:20261025T100000Z", "STATUS:CANCELLED", "END:VEVENT"])
        self.import_file(ics(event("cancel@test", "DTSTART:20261024T100000Z", "RRULE:FREQ=DAILY;COUNT=3"), cancelled))
        self.assertEqual([row["start_at"][:10] for row in self.occurrences()], ["2026-10-24", "2026-10-26"])

    def test_worker_timeout_is_reported_as_validation_error(self):
        import subprocess
        with patch("app.services.calendar_ics.subprocess.run", side_effect=subprocess.TimeoutExpired("ics", 8)):
            self.import_file(ics(event()), status=422)
        self.assertEqual(self.call("GET", "/calendar/events"), [])

    def test_identical_uid_is_skipped_changed_uid_updates_same_row(self):
        content = ics(event())
        self.assertEqual(self.import_file(content)["imported_count"], 1)
        original, = self.call("GET", "/calendar/events")
        self.assertEqual(self.import_file(content)["skipped_count"], 1)
        changed = self.import_file(content.replace("SUMMARY:Testtermin", "SUMMARY:Geaendert"))
        self.assertEqual(changed["updated_count"], 1)
        updated, = self.call("GET", "/calendar/events")
        self.assertEqual((updated["id"], updated["title"]), (original["id"], "Geaendert"))

    def test_import_assigns_group_and_preserves_existing_native_events(self):
        group = self.call("POST", "/calendar/groups", {"name": "ICS"}, 201)
        original = self.call("POST", "/calendar/events", {"title": "Vorhanden", "start_at": "2026-10-24T11:00:00"}, 201)
        self.import_file(ics(event()), group_id=group["id"])
        rows = self.call("GET", "/calendar/events")
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]["is_ics"])
        self.assertEqual(rows[0]["id"], original["id"])
        self.assertEqual(rows[1]["group_id"], group["id"])

    def test_invalid_file_and_second_invalid_event_leave_no_partial_import(self):
        self.import_file("kein Kalender", status=422)
        self.import_file(ics(event(), event("invalid@test", "DTSTART:kaputt")), status=422)
        self.assertEqual(self.call("GET", "/calendar/events"), [])

    def test_invalid_file_extension_timezone_group_and_oversize_are_rejected(self):
        self.call("POST", "/calendar/ics/import", {"filename": "datei.txt", "content": ics(event())}, 422)
        self.import_file(ics(event()), timezone="Invalid/Zone", status=422)
        self.import_file(ics(event()), group_id=999, status=404)
        self.import_file("x" * 2_000_001, status=422)

    def test_unknown_tzid_and_missing_uid_are_rejected(self):
        self.import_file(ics(event("tz@test", "DTSTART;TZID=Invalid/Zone:20261024T100000")), status=422)
        self.import_file(ics(event().replace("UID:one@test\r\n", "")), status=422)

    def test_alarms_are_not_activated_and_no_external_urls_are_fetched(self):
        result = self.import_file(ics(event("alarm@test", "DTSTART:20261024T080000Z",
            "ATTACH:https://example.invalid/file", "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT15M", "DESCRIPTION:Alarm", "END:VALARM")))
        self.assertTrue(result["warnings"])
        with Session(self.engine) as db:
            self.assertNotIn("VALARM", db.query(models.CalendarEvent).one().ics_source)

    def test_series_exclusion_is_stable_when_display_timezone_changes(self):
        self.import_file(ics(event("exclude@test", "DTSTART;TZID=Europe/Berlin:20261024T100000", "RRULE:FREQ=DAILY;COUNT=3")))
        rows = self.occurrences()
        self.call("POST", f'/calendar/events/{rows[1]["id"]}/exclusions', {"occurrence_start_at": rows[1]["ics_occurrence_start_utc"]}, 201)
        self.assertEqual(len(self.occurrences()), 2)
        self.assertEqual([row["start_at"][:10] for row in self.occurrences(timezone="UTC")], ["2026-10-24", "2026-10-26"])

    def test_imported_series_cannot_be_silently_replaced_by_native_edit(self):
        self.import_file(ics(event()))
        row, = self.call("GET", "/calendar/events")
        self.call("PATCH", f'/calendar/events/{row["id"]}', {"title": "Andere Regeln"}, 409)
        self.assertEqual(self.call("GET", "/calendar/events")[0]["title"], "Testtermin")
        self.call("DELETE", f'/calendar/events/{row["id"]}', status=204)
        self.assertEqual(self.occurrences(), [])

    def test_requested_range_is_bounded_and_dense_series_fail_without_expanding_all(self):
        self.occurrences(end="2028-01-01T00:00:00", status=422)
        self.occurrences(end="2026-09-01T00:00:00", status=422)
        self.import_file(ics(event("dense@test", "DTSTART:20261024T100000Z", "RRULE:FREQ=SECONDLY")))
        self.occurrences(start="2026-10-24T12:00:00", end="2026-10-24T13:00:00", status=422)

    def test_export_is_parseable_utf8_and_uses_exclusive_date_end_and_utc(self):
        self.import_file(ics(event("holiday@test", "DTSTART;VALUE=DATE:20261024", "DTEND;VALUE=DATE:20261027")))
        self.call("POST", "/calendar/events", {"title": "Büro, Besprechung", "start_at": "2026-10-24T10:00:00", "end_at": "2026-10-24T11:00:00"}, 201)
        with Session(self.engine) as db:
            content = export_calendar(db, datetime(2026, 10, 1), datetime(2026, 11, 1), "Europe/Berlin")
        parsed = Calendar.from_ical(content)
        rows = parsed.walk("VEVENT")
        self.assertEqual(len(rows), 2)
        holiday, = [row for row in rows if str(row["UID"]) and not isinstance(row.decoded("DTSTART"), datetime)]
        self.assertEqual(str(holiday.decoded("DTEND")), "2026-10-27")
        appointment, = [row for row in rows if str(row["SUMMARY"]) == "Büro, Besprechung"]
        self.assertEqual(appointment.decoded("DTSTART").hour, 8)
        self.assertTrue(content.endswith(b"\r\n"))
        self.assertTrue(all("DTSTAMP" in row and "UID" in row for row in rows))

    def test_export_materializes_native_cycles_and_imported_series_with_exclusions(self):
        self.call("POST", "/calendar/events", {"title": "Rhythmus", "start_at": "2026-10-20T10:00:00", "recurrence_frequency": "cycle"}, 201)
        self.import_file(ics(event("series@test", "DTSTART:20261020T100000", "RRULE:FREQ=DAILY;COUNT=4", "EXDATE:20261021T100000")))
        with Session(self.engine) as db:
            first = export_calendar(db, datetime(2026, 10, 20), datetime(2026, 10, 24), "Europe/Berlin")
            second = export_calendar(db, datetime(2026, 10, 20), datetime(2026, 10, 24), "Europe/Berlin")
        rows = Calendar.from_ical(first).walk("VEVENT")
        self.assertEqual(len(rows), 6)
        self.assertEqual([str(row["UID"]) for row in rows], [str(row["UID"]) for row in Calendar.from_ical(second).walk("VEVENT")])
        self.assertTrue(all("RRULE" not in row for row in rows))

    def test_import_failure_rolls_back_earlier_records(self):
        from app.routers.calendar_ics import import_ics
        with Session(self.engine) as db, patch.object(db, "commit", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                import_ics(schemas.CalendarIcsImportRequest(filename="x.ics", content=ics(event())), db)
            self.assertEqual(db.query(models.CalendarEvent).count(), 0)

    def test_regular_profile_uid_matching_uses_effective_owner(self):
        from app.routers.calendar_ics import import_ics
        with Session(self.engine) as db:
            db.add_all([models.User(id=1, username="Alice"), models.User(id=2, username="Bob")])
            db.commit()
            db.info["principal"] = security.Principal(user_id=1, is_admin=False)
            payload = schemas.CalendarIcsImportRequest(filename="x.ics", content=ics(event()))
            self.assertEqual(import_ics(payload, db).imported_count, 1)
            self.assertEqual(import_ics(payload, db).skipped_count, 1)
            self.assertEqual(db.query(models.CalendarEvent).one().user_id, 1)
            with self.assertRaises(Exception) as caught:
                import_ics(payload.model_copy(update={"user_id": 2}), db)
            self.assertEqual(caught.exception.status_code, 403)

    def test_export_uids_are_distinct_when_profiles_import_the_same_source_uid(self):
        with Session(self.engine) as db:
            db.add_all([models.User(id=1, username="Alice"), models.User(id=2, username="Bob")])
            db.commit()
        self.import_file(ics(event()), user_id=1)
        self.import_file(ics(event()), user_id=2)
        with Session(self.engine) as db:
            content = export_calendar(db, datetime(2026, 10, 1), datetime(2026, 11, 1), "Europe/Berlin")
        rows = Calendar.from_ical(content).walk("VEVENT")
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({str(row["UID"]) for row in rows}), 2)
