import asyncio
import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.database import Base
from app.routers import backups, meals


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="noko-backup-test-")
        self.root = Path(self.directory.name).resolve()
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.directory.cleanup)
        self.target = self.root / "current.db"
        self.engine = self.create_database(self.target)
        with Session(self.engine) as db:
            db.add(models.User(id=999, username="Original", password="!"))
            db.commit()
        named_temporary_file = tempfile.NamedTemporaryFile
        for mocked in (
            patch.object(backups, "sqlite_database_path", return_value=self.target),
            patch.object(backups, "engine", self.engine),
            patch.object(backups.tempfile, "NamedTemporaryFile", side_effect=lambda *args, **kwargs:
                         named_temporary_file(*args, dir=self.root, **kwargs)),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def create_database(self, path):
        engine = create_engine("sqlite:///" + path.as_posix())
        Base.metadata.create_all(engine)
        self.addCleanup(engine.dispose)
        return engine

    def snapshot(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return "\n".join(connection.iterdump())

    def execute(self, path, sql):
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(sql)
            connection.commit()

    def upload(self, content):
        async def run():
            file = UploadFile(filename="restore.db", file=io.BytesIO(content))
            try:
                return await backups.import_database(file)
            finally:
                await file.close()
        return asyncio.run(run())

    def seed_all_tables(self, engine):
        with Session(engine) as db:
            db.add_all([
                models.User(id=1, username="Test", password="!"),
                models.ProductGroup(id=1, name="Gruppe"),
                models.ProductUnit(id=1, name="g"),
                models.StorageLocation(id=1, name="Vorrat"),
            ])
            db.flush()
            db.add_all([
                models.CalendarGroup(id=1, name="Arbeit", user_id=1),
                models.CalendarGroup(id=2, name="Urlaub", suppresses_group_ids=[1]),
                models.Food(id=1, name="Lebensmittel", product_group_id=1,
                            product_unit_id=1, expiry_days=14, is_archived=True),
                models.TrainingPlan(id=1, name="Plan", user_id=1),
            ])
            db.flush()
            db.add_all([
                models.CalendarEvent(id=1, title="Serie", start_at=datetime(2026, 10, 28, 6),
                                     recurrence_frequency="weekly", recurrence_interval=2,
                                     group_id=1, user_id=1),
                models.CalendarEvent(id=2, title="ToDo", start_at=datetime(2026, 10, 28),
                                     entry_type="task", is_completed=True),
                models.FoodConversion(id=1, food_id=1, unit="Packung", quantity=500),
                models.InventoryItem(id=1, name="Lebensmittel", food_id=1, quantity=2,
                                     purchase_date=date(2026, 10, 28), expiry_days=14),
                models.Recipe(id=1, name="Rezept", is_archived=True,
                              image_path="data:image/png;base64,dGVzdA=="),
                models.TrainingExercise(id=1, plan_id=1, name="Uebung"),
                models.TrainingSession(id=1, plan_id=1, user_id=1),
                models.WeightEntry(id=1, user_id=1, weight_kg=80),
            ])
            db.flush()
            db.add_all([
                models.CalendarEventExclusion(id=1, event_id=1, occurrence_start_at=datetime(2026, 11, 11, 6)),
                models.RecipeIngredient(id=1, recipe_id=1, food_id=1, quantity=50),
                models.MealLog(id=1, food_id=1, user_id=1),
                models.MealLog(id=2, recipe_id=1, user_id=1, meal_source="mealprep",
                               planned_inventory_deduction=True),
                models.MealLog(id=3, quick_add_name="Schnelleintrag", quick_calories=100, user_id=1),
                models.TrainingSessionSet(id=1, session_id=1, exercise_id=1, weight_kg=50, reps=10),
                models.ShoppingListItem(id=1, name="Lebensmittel", food_id=1,
                                        inventory_item_id=1, quantity=3),
            ])
            db.commit()
            meals.deduct_meal_log_from_inventory(1, db)
            db.add(models.ReceiptBooking(receipt_id="b" * 64))
            db.commit()

    def test_older_backup_without_booking_tables_still_imports(self):
        source = self.root / "legacy.db"
        source_engine = self.create_database(source)
        self.seed_all_tables(source_engine)
        self.execute(source, "DROP TABLE meal_inventory_bookings; DROP TABLE receipt_bookings;")
        result = self.upload(source.read_bytes())
        self.assertTrue(any("Buchungsnachweise" in warning for warning in result.warnings))
        with Session(self.engine) as db:
            self.assertEqual(db.query(models.MealInventoryBooking).count(), 0)
            self.assertEqual(db.query(models.ReceiptBooking).count(), 0)
            self.assertIsNotNone(db.get(models.MealLog, 1).inventory_deducted_at)

    def test_restored_booking_can_refund_its_original_stock(self):
        source = self.root / "bookings.db"
        self.seed_all_tables(self.create_database(source))
        self.upload(source.read_bytes())
        with Session(self.engine) as db:
            self.assertEqual(db.get(models.InventoryItem, 1).quantity, 1)
            meals.delete_meal_log(1, db)
            self.assertEqual(db.get(models.InventoryItem, 1).quantity, 2)
            self.assertEqual(db.query(models.MealInventoryBooking).count(), 0)
            self.assertEqual(db.query(models.ReceiptBooking).one().receipt_id, "b" * 64)

    def test_export_import_preserves_all_tables_and_backs_up_previous_database(self):
        source = self.root / "source.db"
        source_engine = self.create_database(source)
        self.seed_all_tables(source_engine)
        expected = self.snapshot(source)
        previous = self.snapshot(self.target)
        with patch.object(backups, "sqlite_database_path", return_value=source):
            response = backups.export_database()
        exported = Path(response.path)
        try:
            self.assertEqual(self.snapshot(exported), expected)
            result = self.upload(exported.read_bytes())
        finally:
            asyncio.run(response.background())
        self.assertEqual(set(result.imported_tables), set(Base.metadata.tables))
        self.assertTrue(all(count > 0 for count in result.imported_tables.values()))
        self.assertEqual(result.training_rows, 4)
        self.assertEqual(result.warnings, [])
        self.assertEqual(self.snapshot(self.target), expected)
        self.assertEqual(self.snapshot(Path(result.backup_path)), previous)
        self.assertFalse(exported.exists())

    def test_trigger_and_view_are_rejected_without_touching_current_database(self):
        for statement in [
            "CREATE TRIGGER attack AFTER INSERT ON weight_entries BEGIN UPDATE users SET daily_calories=1; END",
            "CREATE VIEW attack AS SELECT * FROM users",
        ]:
            with self.subTest(statement=statement):
                source = self.root / "untrusted.db"
                if source.exists():
                    source.unlink()
                self.create_database(source).dispose()
                self.execute(source, statement)
                before = self.target.read_bytes()
                with self.assertRaises(HTTPException) as caught:
                    self.upload(source.read_bytes())
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(self.target.read_bytes(), before)

    def test_legacy_backup_is_restored_without_passwords_or_foreign_identity_bindings(self):
        source = self.root / "legacy.db"
        source_engine = self.create_database(source)
        with Session(source_engine) as db:
            db.add(models.User(id=7, username="Original", password="legacy-secret", home_assistant_user_id="attacker"))
            db.commit()
        self.execute(self.target, "UPDATE users SET home_assistant_user_id='trusted-ha-id'")
        self.upload(source.read_bytes())
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("SELECT username,password,home_assistant_user_id FROM users").fetchall(), [("Original", "!", "trusted-ha-id")])
        # Backups made before the HA binding column was introduced remain usable.
        source_engine.dispose()
        self.execute(source, "CREATE TABLE legacy_users AS SELECT id,username,password,theme,daily_calories,protein_percent,fat_percent,carbs_percent FROM users; DROP TABLE users; ALTER TABLE legacy_users RENAME TO users; CREATE UNIQUE INDEX legacy_user_id ON users(id)")
        self.upload(source.read_bytes())
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("SELECT home_assistant_user_id FROM users").fetchone()[0], "trusted-ha-id")

    def test_unrecognized_tables_are_not_installed(self):
        source = self.root / "extra.db"
        self.create_database(source).dispose()
        self.execute(source, "CREATE TABLE extra_data (value TEXT); INSERT INTO extra_data VALUES ('extra')")
        result = self.upload(source.read_bytes())
        self.assertTrue(result.warnings)
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='extra_data'").fetchone())

    def test_export_redacts_credentials_and_access_bindings(self):
        self.execute(self.target, "UPDATE users SET password='legacy-secret',home_assistant_user_id='private-binding'")
        response = backups.export_database()
        try:
            with closing(sqlite3.connect(response.path)) as connection:
                self.assertEqual(connection.execute("SELECT password,home_assistant_user_id FROM users").fetchone(), ("!", None))
            self.assertNotIn(b"legacy-secret", Path(response.path).read_bytes())
        finally:
            asyncio.run(response.background())

    def test_database_upload_size_limit_keeps_original_and_cleans_tempfile(self):
        before = self.target.read_bytes()
        with patch.object(backups, "MAX_DATABASE_BYTES", 4):
            with self.assertRaises(HTTPException) as caught:
                self.upload(b"more than four bytes")
        self.assertEqual(caught.exception.status_code, 413)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual([path.name for path in self.root.iterdir()], ["current.db"])

    def test_missing_tables_are_rejected_before_replacing_current_database(self):
        incomplete = self.root / "incomplete.db"
        statements = [f'CREATE TABLE "{table}" (id INTEGER)' for table in ["users", *backups.TRAINING_TABLES]]
        self.execute(incomplete, ";".join(statements))
        before = self.target.read_bytes()
        with self.assertRaises(HTTPException) as context:
            self.upload(incomplete.read_bytes())
        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("Fehlende Tabellen", context.exception.detail)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.backup-*")), [])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["current.db", "incomplete.db"])

    def test_missing_training_table_is_an_error_instead_of_a_warning(self):
        self.execute(self.target, "DROP TABLE training_session_sets")
        with self.assertRaisesRegex(ValueError, "Fehlende Tabellen: training_session_sets"):
            backups.validate_sqlite_database(self.target)

    def test_missing_columns_are_rejected(self):
        self.execute(self.target, "DROP TABLE users; CREATE TABLE users (id INTEGER PRIMARY KEY)")
        with self.assertRaisesRegex(ValueError, "Fehlende Spalten in users"):
            backups.validate_sqlite_database(self.target)

    def test_broken_references_are_rejected(self):
        with Session(self.engine) as db:
            db.add(models.CalendarEvent(title="Fehler", start_at=datetime(2026, 10, 28), user_id=999999))
            db.commit()
        with self.assertRaisesRegex(ValueError, "Datenverknuepfung"):
            backups.validate_sqlite_database(self.target)

    def test_broken_references_are_rejected_even_without_uploaded_foreign_keys(self):
        with closing(sqlite3.connect(self.target)) as connection:
            columns = connection.execute('PRAGMA table_info("calendar_events")').fetchall()
        definition = ", ".join(f'"{row[1]}" {row[2]}' + (" PRIMARY KEY" if row[5] else "") for row in columns)
        self.execute(self.target, f'DROP TABLE calendar_events; CREATE TABLE calendar_events ({definition})')
        with Session(self.engine) as db:
            db.add(models.CalendarEvent(title="Fehler", start_at=datetime(2026, 10, 28), user_id=999999))
            db.commit()
        with closing(sqlite3.connect(self.target)) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        with self.assertRaisesRegex(ValueError, "calendar_events.user_id"):
            backups.validate_sqlite_database(self.target)

    def test_non_sqlite_upload_is_rejected_and_current_data_stays_intact(self):
        before = self.target.read_bytes()
        with self.assertRaises(HTTPException) as context:
            self.upload(b"not a database")
        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(self.target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
