import unittest
import subprocess
import sys
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.routers import calendar, training
from app.security import Principal
from app.services.calendar_schedule import recurrence_starts


class TrainingCalendarTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        user = models.User(username="Training", password="!")
        other = models.User(username="Other", password="!")
        self.db.add_all([user, other])
        self.db.commit()
        self.user_id, self.other_id = user.id, other.id
        self.plan = training.create_training_plan(schemas.TrainingPlanCreate(
            name="Ganzkoerper", user_id=user.id,
            exercises=[schemas.TrainingExerciseCreate(name="Kniebeuge")],
        ), self.db)
        self.entry = calendar.create_event(schemas.CalendarEventCreate(
            title="Training", start_at=self.at(9), end_at=self.at(9, 19),
            recurrence_frequency="cycle", cycle_training_days=2, cycle_rest_days=1,
            training_plan_id=self.plan.id, user_id=user.id,
        ), self.db)

    @staticmethod
    def at(day, hour=18):
        return datetime(2026, 11, day, hour)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def days(self):
        return [value.day for value in recurrence_starts(self.entry, self.at(20))]

    def skip(self, day):
        return calendar.skip_training_occurrence(self.entry.id,
            schemas.CalendarEventExclusionRequest(occurrence_start_at=self.at(day)), self.db)

    def log(self, day, **overrides):
        values = dict(plan_id=self.plan.id, user_id=self.user_id, trained_at=self.at(day),
            calendar_event_id=self.entry.id, calendar_occurrence_start_at=self.at(day),
            sets=[schemas.TrainingSessionSetCreate(exercise_id=self.plan.exercises[0].id, weight_kg=60, reps=10)])
        values.update(overrides)
        return training.create_training_session(schemas.TrainingSessionCreate(**values), self.db)

    def test_cycle_and_repeated_pause_preserve_training_sequence(self):
        self.assertEqual(self.days(), [9, 10, 12, 13, 15, 16, 18, 19])
        self.skip(10)
        self.assertEqual(self.days(), [9, 11, 13, 14, 16, 17, 19, 20])
        self.skip(11)
        self.assertEqual(self.days(), [9, 12, 14, 15, 17, 18, 20])
        self.assertEqual(schemas.CalendarEventRead.model_validate(self.entry).training_plan.id, self.plan.id)

    def test_skip_before_an_existing_future_pause_and_reverse_undo(self):
        self.skip(15)
        self.skip(10)
        self.assertEqual(self.days(), [9, 11, 13, 14, 17, 18, 20])
        with self.assertRaises(HTTPException):
            calendar.undo_training_skip(self.entry.id, self.entry.shifts[0].id, self.db)
        calendar.undo_training_skip(self.entry.id, self.entry.shifts[-1].id, self.db)
        self.assertEqual(self.days(), [9, 10, 12, 13, 16, 17, 19, 20])
        calendar.undo_training_skip(self.entry.id, self.entry.shifts[-1].id, self.db)
        self.assertEqual(self.days(), [9, 10, 12, 13, 15, 16, 18, 19])

    def test_skip_rejects_rest_day_and_already_shifted_date(self):
        for day in (8, 11):
            with self.assertRaises(HTTPException):
                self.skip(day)
        self.skip(10)
        with self.assertRaises(HTTPException):
            self.skip(10)
        self.assertEqual(len(self.entry.shifts), 1)

    def test_exclusions_move_with_pause_and_undo(self):
        calendar.exclude_event_occurrence(self.entry.id,
            schemas.CalendarEventExclusionRequest(occurrence_start_at=self.at(13)), self.db)
        self.skip(10)
        self.assertEqual(self.entry.exclusions[0].occurrence_start_at, self.at(14))
        calendar.undo_training_skip(self.entry.id, self.entry.shifts[-1].id, self.db)
        self.assertEqual(self.entry.exclusions[0].occurrence_start_at, self.at(13))

    def test_adjacent_exclusions_do_not_collide_during_skip_or_undo(self):
        for day in (12, 13):
            calendar.exclude_event_occurrence(self.entry.id,
                schemas.CalendarEventExclusionRequest(occurrence_start_at=self.at(day)), self.db)
        self.skip(10)
        self.assertEqual([item.occurrence_start_at for item in self.entry.exclusions], [self.at(13), self.at(14)])
        calendar.undo_training_skip(self.entry.id, self.entry.shifts[-1].id, self.db)
        self.assertEqual([item.occurrence_start_at for item in self.entry.exclusions], [self.at(12), self.at(13)])

    def test_linked_log_blocks_duplicate_skip_undo_and_exclusion(self):
        self.skip(10)
        logged = self.log(11)
        self.assertEqual(schemas.TrainingSessionRead.model_validate(logged).calendar_event_id, self.entry.id)
        with self.assertRaises(HTTPException) as duplicate:
            self.log(11)
        self.assertEqual(duplicate.exception.status_code, 409)
        for operation in (
            lambda: self.skip(11),
            lambda: self.skip(9),
            lambda: calendar.undo_training_skip(self.entry.id, self.entry.shifts[-1].id, self.db),
            lambda: calendar.exclude_event_occurrence(self.entry.id,
                schemas.CalendarEventExclusionRequest(occurrence_start_at=self.at(11)), self.db),
        ):
            with self.assertRaises(HTTPException):
                operation()
        self.skip(13)  # A pause after the logged training remains possible.

    def test_linked_log_validates_plan_profile_and_real_occurrence(self):
        for overrides in (
            {"user_id": self.other_id},
            {"calendar_occurrence_start_at": self.at(11)},
            {"calendar_occurrence_start_at": None},
        ):
            with self.assertRaises(HTTPException):
                self.log(9, **overrides)
        other_plan = training.create_training_plan(schemas.TrainingPlanCreate(name="Other", user_id=self.user_id), self.db)
        with self.assertRaises(HTTPException):
            self.log(9, plan_id=other_plan.id)
        self.assertEqual(self.db.query(models.TrainingSession).count(), 0)

    def test_session_update_preserves_link_and_invalid_update_leaves_original(self):
        logged = self.log(9)
        training.update_training_session(logged.id, schemas.TrainingSessionUpdate(notes="Gut"), self.db)
        self.assertEqual(logged.calendar_event_id, self.entry.id)
        with self.assertRaises(HTTPException):
            training.update_training_session(logged.id, schemas.TrainingSessionUpdate(user_id=self.other_id), self.db)
        self.assertEqual(logged.user_id, self.user_id)
        training.update_training_session(logged.id, schemas.TrainingSessionUpdate(calendar_event_id=None), self.db)
        self.assertIsNone(logged.calendar_event_id)
        self.assertIsNone(logged.calendar_occurrence_start_at)

    def test_schedule_edits_blocked_after_pauses_but_title_edit_allowed(self):
        self.skip(10)
        with self.assertRaises(HTTPException):
            calendar.update_event(self.entry.id, schemas.CalendarEventUpdate(cycle_rest_days=2), self.db)
        calendar.update_event(self.entry.id, schemas.CalendarEventUpdate(title="Neuer Titel"), self.db)
        self.assertEqual(self.entry.title, "Neuer Titel")

    def test_partial_date_update_validates_merged_event(self):
        with self.assertRaises(HTTPException):
            calendar.update_event(self.entry.id, schemas.CalendarEventUpdate(start_at=self.at(10)), self.db)
        self.assertEqual(self.entry.start_at, self.at(9))

    def test_series_end_applies_after_shifting(self):
        calendar.update_event(self.entry.id, schemas.CalendarEventUpdate(recurrence_until=self.at(13)), self.db)
        self.skip(10)
        self.assertEqual(self.days(), [9, 11, 13])

    def test_other_profile_cannot_pause_or_link_foreign_training_plan(self):
        self.db.info["principal"] = Principal(self.other_id, False)
        with self.assertRaises(HTTPException):
            self.skip(10)
        self.db.info.clear()
        with self.assertRaises(HTTPException):
            calendar.create_event(schemas.CalendarEventCreate(title="Falsch", start_at=self.at(9),
                training_plan_id=self.plan.id, user_id=self.other_id), self.db)

    def test_deleting_calendar_preserves_logged_training(self):
        logged = self.log(9)
        calendar.delete_event(self.entry.id, self.db)
        self.db.refresh(logged)
        self.assertIsNone(logged.calendar_event_id)
        self.assertIsNone(logged.calendar_occurrence_start_at)
        self.assertEqual(len(logged.sets), 1)

    def test_deleting_plan_unlinks_calendar(self):
        training.delete_training_plan(self.plan.id, self.db)
        self.db.refresh(self.entry)
        self.assertIsNone(self.entry.training_plan_id)


class TrainingCalendarMigrationTest(unittest.TestCase):
    def test_startup_migrates_existing_database_and_is_repeatable(self):
        script = '''
from sqlalchemy import create_engine, inspect, text
from app import database
database.engine = create_engine("sqlite://")
database.SessionLocal.configure(bind=database.engine)
with database.engine.begin() as connection:
    connection.exec_driver_sql("""CREATE TABLE calendar_events (
        id INTEGER PRIMARY KEY, title VARCHAR(200) NOT NULL, description TEXT,
        start_at DATETIME NOT NULL, end_at DATETIME, location VARCHAR(255),
        entry_type VARCHAR(32) NOT NULL DEFAULT 'event', all_day BOOLEAN NOT NULL DEFAULT 0,
        is_completed BOOLEAN NOT NULL DEFAULT 0, recurrence_frequency VARCHAR(32) NOT NULL DEFAULT 'none',
        recurrence_interval INTEGER NOT NULL DEFAULT 1, recurrence_until DATETIME, user_id INTEGER,
        group_id INTEGER, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""")
    connection.exec_driver_sql("""INSERT INTO calendar_events
        (title,start_at,created_at,updated_at) VALUES ('Alt','2026-11-09 18:00:00',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")
    connection.exec_driver_sql("""CREATE TABLE training_sessions (
        id INTEGER PRIMARY KEY, trained_at DATETIME NOT NULL, notes TEXT,
        user_id INTEGER, plan_id INTEGER NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""")
from app.main import migrate_sqlite_calendar_schema
from app import models, schemas
migrate_sqlite_calendar_schema()
with database.SessionLocal() as db:
    entry = db.query(models.CalendarEvent).one()
    assert (entry.title, entry.cycle_training_days, entry.cycle_rest_days, entry.training_plan_id) == ('Alt',2,1,None)
    assert schemas.CalendarEventRead.model_validate(entry).shifts == []
inspector = inspect(database.engine)
assert 'calendar_event_shifts' in inspector.get_table_names()
columns = {item['name'] for item in inspector.get_columns('training_sessions')}
assert {'calendar_event_id','calendar_occurrence_start_at'} <= columns
assert any(item['name'] == 'uq_training_calendar_occurrence' for item in inspector.get_indexes('training_sessions'))
'''
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
