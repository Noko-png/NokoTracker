import asyncio
import io
import json
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
from app.routers import backups, meals, recipe_transfers


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

    def upload(self, content, **options):
        async def run():
            file = UploadFile(filename="restore.db", file=io.BytesIO(content))
            try:
                if options.get("mode") == "recipes":
                    return await recipe_transfers.import_recipes(file, recipe_ids=options.get("recipe_ids", "[]"))
                return await backups.import_database(file, **options)
            finally:
                await file.close()
        return asyncio.run(run())

    def preview(self, content, *, recipes=False):
        async def run():
            file = UploadFile(filename="preview.db", file=io.BytesIO(content))
            try:
                return await (recipe_transfers.preview_recipes(file) if recipes else backups.preview_database(file))
            finally:
                await file.close()
        return asyncio.run(run())

    def table_rows(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return {table: connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall() for table in Base.metadata.tables}

    def source_with_data(self):
        source = self.root / "source.db"
        self.seed_all_tables(self.create_database(source))
        return source

    def matching_profile(self):
        with Session(self.engine) as db:
            db.add(models.User(id=42, username="Test", password="!", home_assistant_user_id="trusted"))
            db.commit()

    def test_previews_are_separate_and_read_only(self):
        source = self.source_with_data()
        before = self.target.read_bytes()
        preview = self.preview(source.read_bytes())
        self.assertEqual({group.key for group in preview.groups}, set(backups.DATA_GROUPS))
        self.assertEqual(next(group.rows for group in preview.groups if group.key == "weight"), 1)
        self.assertNotIn("recipes", preview.model_dump())
        recipe_preview = self.preview(source.read_bytes(), recipes=True)
        self.assertEqual([(recipe.id, recipe.name) for recipe in recipe_preview.recipes], [(1, "Rezept")])
        self.assertNotIn("groups", recipe_preview.model_dump())
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.backup-*")))

    def test_weight_only_replaces_weight_and_maps_profiles_by_name_not_id(self):
        source = self.source_with_data()
        self.matching_profile()
        with Session(self.engine) as db:
            db.add(models.WeightEntry(user_id=42, weight_kg=99))
            db.add(models.WeightEntry(user_id=999, weight_kg=65))
            db.add(models.Recipe(name="Bleibt unveraendert"))
            db.commit()
        before = self.table_rows(self.target)
        result = self.upload(source.read_bytes(), mode="selected", groups='["weight"]')
        after = self.table_rows(self.target)
        for table in before.keys() - {"weight_entries"}:
            self.assertEqual(after[table], before[table], table)
        with Session(self.engine) as db:
            weight = db.query(models.WeightEntry).one()
            self.assertEqual((weight.user_id, weight.weight_kg), (42, 80))
            self.assertEqual(db.get(models.User, 42).home_assistant_user_id, "trusted")
        self.assertEqual(result.imported_tables, {"weight_entries": 1})
        self.assertEqual(self.table_rows(Path(result.backup_path)), before)

    def test_unknown_profile_aborts_instead_of_assigning_data_to_same_id(self):
        source = self.source_with_data()
        self.execute(self.target, "UPDATE users SET id=1")
        before = self.target.read_bytes()
        with self.assertRaises(HTTPException) as caught:
            self.upload(source.read_bytes(), mode="selected", groups='["weight"]')
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("Profil 'Test' fehlt", caught.exception.detail)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.backup-*")))

    def test_empty_selected_area_is_cleared_without_clearing_other_areas(self):
        source = self.root / "empty.db"
        self.create_database(source)
        self.seed_all_tables(self.engine)
        before = self.table_rows(self.target)
        self.upload(source.read_bytes(), mode="selected", groups='["weight"]')
        after = self.table_rows(self.target)
        self.assertEqual(after.pop("weight_entries"), [])
        before.pop("weight_entries")
        self.assertEqual(after, before)

    def test_independent_groups_remap_internal_ids_and_preserve_other_tables(self):
        source = self.source_with_data()
        self.seed_all_tables(self.engine)
        for group in ["calendar", "training", "shopping", "recipes", "foods"]:
            with self.subTest(group=group):
                before = self.table_rows(self.target)
                self.upload(source.read_bytes(), mode="selected", groups=json.dumps([group]))
                after = self.table_rows(self.target)
                for table in before.keys() - backups.DATA_GROUPS[group][1]:
                    self.assertEqual(after[table], before[table], table)
                with closing(sqlite3.connect(self.target)) as db:
                    self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                    if group == "calendar":
                        group_id = db.execute("SELECT id FROM calendar_groups WHERE name='Arbeit'").fetchone()[0]
                        suppresses = json.loads(db.execute("SELECT suppresses_group_ids FROM calendar_groups WHERE name='Urlaub'").fetchone()[0])
                        self.assertEqual(suppresses, [group_id])

    def test_inventory_and_meals_restore_booking_snapshots_with_remapped_ids(self):
        source = self.source_with_data()
        self.seed_all_tables(self.engine)
        before = self.table_rows(self.target)
        result = self.upload(source.read_bytes(), mode="selected", groups='["inventory","meals","shopping"]')
        after = self.table_rows(self.target)
        for table in before.keys() - backups.DATA_GROUPS["inventory"][1] - backups.DATA_GROUPS["meals"][1] - backups.DATA_GROUPS["shopping"][1]:
            self.assertEqual(after[table], before[table], table)
        with Session(self.engine) as db:
            meal = db.query(models.MealLog).filter(models.MealLog.food_id.is_not(None)).one()
            lot = db.query(models.InventoryItem).one()
            self.assertNotEqual(lot.id, 1)
            self.assertEqual(meal.inventory_booking.deductions[0]["inventory_item_id"], lot.id)
            meals.delete_meal_log(meal.id, db)
            self.assertEqual(db.query(models.InventoryItem).one().quantity, 2)
        self.assertTrue(Path(result.backup_path).exists())

    def test_replacing_referenced_data_is_rejected_atomically(self):
        source = self.root / "empty.db"
        self.create_database(source)
        self.seed_all_tables(self.engine)
        for group in ["inventory", "recipes", "foods"]:
            with self.subTest(group=group):
                before = self.target.read_bytes()
                with self.assertRaises(HTTPException) as caught:
                    self.upload(source.read_bytes(), mode="selected", groups=json.dumps([group]))
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(self.target.read_bytes(), before)

    def test_meals_without_inventory_keep_stock_unchanged_and_warn_about_legacy_bookings(self):
        source = self.source_with_data()
        self.seed_all_tables(self.engine)
        before = self.table_rows(self.target)
        result = self.upload(source.read_bytes(), mode="selected", groups='["meals"]')
        after = self.table_rows(self.target)
        self.assertEqual(after["inventory_items"], before["inventory_items"])
        self.assertEqual(after["meal_inventory_bookings"], [])
        self.assertTrue(any("Bestandsabbuchungen" in warning for warning in result.warnings))

    def test_recipe_export_contains_only_recipe_dependencies_and_can_be_added(self):
        source = self.source_with_data()
        self.execute(source, "UPDATE recipes SET created_by_user_id=1, prepared_food_id=1")
        with patch.object(backups, "sqlite_database_path", return_value=source):
            response = recipe_transfers.export_recipe(1)
        try:
            content = Path(response.path).read_bytes()
            preview = self.preview(content, recipes=True)
            with self.assertRaises(HTTPException) as caught:
                self.preview(content)
            self.assertIn("Gerichte", caught.exception.detail)
            rows = self.table_rows(Path(response.path))
            for table in ["users", "meal_logs", "weight_entries", "inventory_items", "calendar_events", "training_plans", "shopping_list_items"]:
                self.assertEqual(rows[table], [], table)
            self.assertEqual(len(rows["recipes"]), 1)
            self.assertEqual(len(rows["food_barcodes"]), 2)
            before = self.table_rows(self.target)
            # Even a same-name recipe is left untouched when adding a recipe.
            with Session(self.engine) as db:
                db.add(models.Recipe(name="Rezept", instructions="Original"))
                db.commit()
            original = self.table_rows(self.target)["recipes"]
            result = self.upload(content, mode="recipes", recipe_ids=json.dumps([preview.recipes[0].id]))
            with Session(self.engine) as db:
                recipes = db.query(models.Recipe).order_by(models.Recipe.id).all()
                self.assertEqual(len(recipes), 2)
                self.assertEqual(recipes[0].instructions, "Original")
                self.assertFalse(recipes[1].is_archived)
                self.assertFalse(recipes[1].ingredients[0].food.is_archived)
                self.assertIsNone(recipes[1].created_by_user_id)
                self.assertIsNone(recipes[1].prepared_food_id)
                self.assertEqual(recipes[1].ingredients[0].food.barcodes, ["0012345678905", "4012345678901"])
                self.assertEqual(recipes[1].ingredients[0].food.fiber_per_100g, 4.25)
                self.assertEqual(recipes[1].image_path, "data:image/png;base64,dGVzdA==")
            self.assertEqual(self.table_rows(self.target)["recipes"][:1], original)
            self.assertEqual(self.table_rows(self.target)["users"], before["users"])
            self.assertEqual(result.imported_count, 1)
            for mode, options in [("full", {}), ("selected", {"groups": '["weight"]'})]:
                current = self.target.read_bytes()
                with self.assertRaises(HTTPException):
                    self.upload(content, mode=mode, **options)
                self.assertEqual(self.target.read_bytes(), current)
        finally:
            asyncio.run(response.background())

    def test_selected_recipe_from_full_database_reuses_food_and_preserves_every_other_row(self):
        source = self.source_with_data()
        self.seed_all_tables(self.engine)
        before = self.table_rows(self.target)
        self.upload(source.read_bytes(), mode="recipes", recipe_ids='[1]')
        after = self.table_rows(self.target)
        for table in before.keys() - {"recipes", "recipe_ingredients"}:
            self.assertEqual(after[table], before[table], table)
        self.assertEqual(len(after["recipes"]), 2)
        self.assertEqual(len(after["recipe_ingredients"]), 2)

    def test_invalid_selection_and_unknown_recipe_leave_database_intact(self):
        source = self.source_with_data()
        for options in [
            {"mode": "selected"}, {"mode": "selected", "groups": '["invalid"]'},
            {"mode": "recipes"}, {"mode": "recipes", "recipe_ids": '[true]'},
            {"mode": "recipes", "recipe_ids": '[999]'}, {"mode": "selected", "groups": '"weight"'},
        ]:
            with self.subTest(options=options):
                before = self.target.read_bytes()
                with self.assertRaises(HTTPException) as caught:
                    self.upload(source.read_bytes(), **options)
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(self.target.read_bytes(), before)

    def test_all_groups_can_be_replaced_together_while_profiles_stay_local(self):
        source = self.source_with_data()
        self.matching_profile()
        before_users = self.table_rows(self.target)["users"]
        self.upload(source.read_bytes(), mode="selected", groups=json.dumps(list(backups.DATA_GROUPS)))
        self.assertEqual(self.table_rows(self.target)["users"], before_users)
        source_counts, _ = backups.validate_sqlite_database(source)
        target_counts, _ = backups.validate_sqlite_database(self.target)
        for table in source_counts.keys() - {"users"}:
            self.assertEqual(target_counts[table], source_counts[table], table)

    def test_imported_booking_can_recreate_deleted_lot_from_remapped_snapshot(self):
        source = self.source_with_data()
        self.execute(source, "UPDATE shopping_list_items SET inventory_item_id=NULL; DELETE FROM inventory_items;")
        self.matching_profile()
        # Colliding IDs belong to different foods in the two databases.
        with Session(self.engine) as db:
            db.add(models.Food(id=1, name="Bleibt bestehen"))
            db.commit()
        self.upload(source.read_bytes(), mode="selected", groups='["inventory","meals"]')
        with Session(self.engine) as db:
            meal = db.query(models.MealLog).filter(models.MealLog.food_id.is_not(None)).one()
            self.assertNotEqual(meal.food_id, 1)
            meals.delete_meal_log(meal.id, db)
            lot = db.query(models.InventoryItem).one()
            self.assertNotEqual(lot.food_id, 1)
            self.assertEqual(lot.food.name, "Lebensmittel")
            self.assertEqual(lot.quantity, 1)

    def test_conflicting_legacy_ean_aborts_recipe_addition_without_changing_data(self):
        source = self.source_with_data()
        with Session(self.engine) as db:
            db.add(models.Food(name="Anderes Produkt", barcode="0012345678905"))
            db.commit()
        before = self.target.read_bytes()
        with self.assertRaises(HTTPException) as caught:
            self.upload(source.read_bytes(), mode="recipes", recipe_ids='[1]')
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn("EAN", caught.exception.detail)
        self.assertEqual(self.target.read_bytes(), before)

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
                models.Food(id=1, name="Lebensmittel", barcode="0012345678905", product_group_id=1,
                            product_unit_id=1, expiry_days=14, is_archived=True,
                            fiber_per_100g=4.25, sugar_per_100g=12.6, caffeine_mg_per_100g=32.5),
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
                models.FoodBarcode(food_id=1, barcode="0012345678905"),
                models.FoodBarcode(food_id=1, barcode="4012345678901"),
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

    def test_older_backup_without_alias_table_keeps_legacy_ean(self):
        source = self.root / "legacy-barcodes.db"
        self.seed_all_tables(self.create_database(source))
        self.execute(source, "DROP TABLE food_barcodes;")
        self.upload(source.read_bytes())
        with Session(self.engine) as db:
            self.assertEqual(db.get(models.Food, 1).barcodes, ["0012345678905"])
            self.assertEqual(db.query(models.FoodBarcode).count(), 0)

    def test_older_backup_without_new_nutrients_uses_safe_defaults(self):
        source = self.root / "legacy-nutrients.db"
        self.seed_all_tables(self.create_database(source))
        self.execute(source, """
            ALTER TABLE foods DROP COLUMN fiber_per_100g;
            ALTER TABLE foods DROP COLUMN sugar_per_100g;
            ALTER TABLE foods DROP COLUMN caffeine_mg_per_100g;
        """)
        self.upload(source.read_bytes())
        with Session(self.engine) as db:
            food = db.get(models.Food, 1)
            self.assertEqual((food.fiber_per_100g, food.sugar_per_100g, food.caffeine_mg_per_100g), (0, 0, None))
            self.assertEqual(food.expiry_days, 14)
            self.assertEqual(food.barcodes, ["0012345678905", "4012345678901"])

    def source_with_training_calendar(self):
        source = self.source_with_data()
        self.execute(source, """
            UPDATE calendar_events SET recurrence_frequency='cycle', cycle_training_days=2,
                cycle_rest_days=1, training_plan_id=1 WHERE id=1;
            INSERT INTO calendar_event_shifts (id,event_id,occurrence_start_at,days)
                VALUES (1,1,'2026-10-29 06:00:00.000000',1);
            UPDATE training_sessions SET calendar_event_id=1,
                calendar_occurrence_start_at='2026-10-28 06:00:00.000000' WHERE id=1;
        """)
        return source

    def test_full_import_preserves_training_calendar_and_inserted_rest_days(self):
        source = self.source_with_training_calendar()
        expected = self.table_rows(source)
        self.upload(source.read_bytes())
        self.assertEqual(self.table_rows(self.target), expected)

    def test_training_calendar_partial_import_remaps_entire_linked_history(self):
        source = self.source_with_training_calendar()
        self.seed_all_tables(self.engine)
        self.upload(source.read_bytes(), mode="selected", groups='["training","calendar"]')
        with Session(self.engine) as db:
            event = db.query(models.CalendarEvent).filter_by(title="Serie").one()
            plan = db.query(models.TrainingPlan).one()
            session = db.query(models.TrainingSession).one()
            shift = db.query(models.CalendarEventShift).one()
            self.assertNotEqual(event.id, 1)
            self.assertNotEqual(plan.id, 1)
            self.assertEqual(event.training_plan_id, plan.id)
            self.assertEqual(session.plan_id, plan.id)
            self.assertEqual(session.calendar_event_id, event.id)
            self.assertEqual(shift.event_id, event.id)
            self.assertEqual(session.calendar_occurrence_start_at, datetime(2026, 10, 28, 6))
            self.assertEqual(shift.occurrence_start_at, datetime(2026, 10, 29, 6))
            self.assertEqual((event.cycle_training_days, event.cycle_rest_days), (2, 1))
            self.assertEqual(len(plan.exercises), 1)

    def test_linked_training_calendar_requires_both_groups_without_changing_current_data(self):
        source = self.source_with_training_calendar()
        self.matching_profile()
        for group in ("training", "calendar"):
            with self.subTest(group=group):
                before = self.target.read_bytes()
                with self.assertRaises(HTTPException) as caught:
                    self.upload(source.read_bytes(), mode="selected", groups=json.dumps([group]))
                self.assertEqual(caught.exception.status_code, 422)
                self.assertIn("beide Datenbereiche", caught.exception.detail)
                self.assertEqual(self.target.read_bytes(), before)

    def test_existing_training_calendar_cannot_be_broken_by_single_group_import(self):
        linked = self.source_with_training_calendar()
        self.upload(linked.read_bytes())
        empty = self.root / "empty-training-calendar.db"
        self.create_database(empty)
        for group in ("training", "calendar"):
            with self.subTest(group=group):
                before = self.target.read_bytes()
                with self.assertRaises(HTTPException) as caught:
                    self.upload(empty.read_bytes(), mode="selected", groups=json.dumps([group]))
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(self.target.read_bytes(), before)

    def test_older_calendar_backup_restores_without_training_links_or_pauses(self):
        source = self.source_with_data()
        with closing(sqlite3.connect(source)) as connection:
            connection.execute("DROP TABLE calendar_event_shifts")
            for table, omitted in backups.CALENDAR_OPTIONAL_COLUMNS.items():
                columns = [row for row in connection.execute(f'PRAGMA table_info("{table}")') if row[1] not in omitted]
                definition = ", ".join(f'"{row[1]}" {row[2]}' + (" PRIMARY KEY" if row[5] else "") for row in columns)
                names = ", ".join(f'"{row[1]}"' for row in columns)
                connection.execute(f'CREATE TABLE "legacy_{table}" ({definition})')
                connection.execute(f'INSERT INTO "legacy_{table}" SELECT {names} FROM "{table}"')
                connection.execute(f'DROP TABLE "{table}"')
                connection.execute(f'ALTER TABLE "legacy_{table}" RENAME TO "{table}"')
            connection.commit()
        for mode, options in (("full", {}), ("selected", {"groups": '["training","calendar"]'})):
            with self.subTest(mode=mode):
                self.upload(source.read_bytes(), mode=mode, **options)
                with Session(self.engine) as db:
                    event = db.query(models.CalendarEvent).filter_by(title="Serie").one()
                    session = db.query(models.TrainingSession).one()
                    self.assertEqual((event.cycle_training_days, event.cycle_rest_days), (2, 1))
                    self.assertIsNone(event.training_plan_id)
                    self.assertIsNone(session.calendar_event_id)
                    self.assertIsNone(session.calendar_occurrence_start_at)
                    self.assertEqual(db.query(models.CalendarEventShift).count(), 0)

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
            self.assertEqual(db.get(models.Food, 1).barcodes, ["0012345678905", "4012345678901"])

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
        self.assertTrue(all(count > 0 for table, count in result.imported_tables.items()
                            if table not in backups.CALENDAR_OPTIONAL_TABLES))
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
