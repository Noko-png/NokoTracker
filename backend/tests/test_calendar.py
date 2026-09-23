import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.routers import calendar


class CalendarSuppressionTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.work_group = calendar.create_group(
            schemas.CalendarGroupCreate(name="Arbeit"), self.db
        )
        self.holiday_group = calendar.create_group(
            schemas.CalendarGroupCreate(
                name="Urlaub", suppresses_group_ids=[self.work_group.id]
            ),
            self.db,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create_work(self, frequency="weekdays"):
        return calendar.create_event(
            schemas.CalendarEventCreate(
                title="Arbeit",
                start_at=datetime(2026, 9, 21, 6),
                end_at=datetime(2026, 9, 21, 15),
                recurrence_frequency=frequency,
                group_id=self.work_group.id,
            ),
            self.db,
        )

    def create_holiday(self):
        return calendar.create_event(
            schemas.CalendarEventCreate(
                title="Urlaub",
                start_at=datetime(2026, 9, 21, 6),
                end_at=datetime(2026, 9, 21, 10),
                group_id=self.holiday_group.id,
            ),
            self.db,
        )

    def assert_work_preserved(self, work):
        self.db.expire_all()
        self.assertEqual(work.start_at, datetime(2026, 9, 21, 6))
        self.assertEqual(work.end_at, datetime(2026, 9, 21, 15))
        self.assertEqual(work.exclusions, [])
        self.assertEqual(
            self.db.query(models.CalendarEvent)
            .filter(models.CalendarEvent.group_id == self.work_group.id)
            .count(),
            1,
        )

    def test_creating_suppression_preserves_original_events(self):
        for frequency in ("none", "weekdays"):
            with self.subTest(frequency=frequency):
                work = self.create_work(frequency)
                holiday = self.create_holiday()
                self.assert_work_preserved(work)
                calendar.delete_event(holiday.id, self.db)
                calendar.delete_event(work.id, self.db)

    def test_moving_and_deleting_suppression_leaves_no_stale_exclusions(self):
        work = self.create_work()
        holiday = self.create_holiday()
        calendar.update_event(
            holiday.id,
            schemas.CalendarEventUpdate(
                start_at=datetime(2026, 9, 22, 6),
                end_at=datetime(2026, 9, 22, 10),
            ),
            self.db,
        )
        self.assert_work_preserved(work)
        calendar.delete_event(holiday.id, self.db)
        self.assert_work_preserved(work)

    def test_explicitly_deleted_occurrences_are_still_preserved(self):
        work = self.create_work()
        excluded_start = datetime(2026, 9, 23, 6)
        calendar.exclude_event_occurrence(
            work.id,
            schemas.CalendarEventExclusionRequest(occurrence_start_at=excluded_start),
            self.db,
        )
        holiday = self.create_holiday()
        calendar.delete_event(holiday.id, self.db)
        self.db.expire_all()
        self.assertEqual(
            [item.occurrence_start_at for item in work.exclusions], [excluded_start]
        )


if __name__ == "__main__":
    unittest.main()
