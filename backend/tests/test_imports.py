import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.services import grocy_import_service as grocy
from app.services import receipt_import_service as receipt


class ImportDate(date):
    current = date(2026, 10, 28)

    @classmethod
    def today(cls):
        return cls.current


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="noko-import-test-")
        self.root = Path(self.directory.name).resolve()
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.directory.cleanup)
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.db.close)
        ImportDate.current = date(2026, 10, 28)
        self.date_patch = patch.object(grocy, "date", ImportDate)
        self.date_patch.start()
        self.addCleanup(self.date_patch.stop)
        self.write_csv("quantity_units.csv", ["id", "name"], [{"id": 1, "name": "g"}])
        self.write_csv("locations.csv", ["id", "name"], [
            {"id": 1, "name": "Vorrat"}, {"id": 2, "name": "Kuehlschrank"},
        ])
        self.write_csv("products.csv", ["id", "name", "qu_id_stock"], [
            {"id": 1, "name": "Testprodukt", "qu_id_stock": 1},
            {"id": 2, "name": "Andere Zutat", "qu_id_stock": 1},
        ])

    def write_csv(self, name, fields, rows):
        with (self.root / name).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def stock(self, best_before="2026-11-08", purchase="", amount=2):
        self.write_csv("stock_current_location_content.csv", [
            "product_id", "location_id", "amount", "best_before_date", "purchased_date",
        ], [{
            "product_id": 1, "location_id": 1, "amount": amount,
            "best_before_date": best_before, "purchased_date": purchase,
        }])

    def run_import(self, dry_run=False):
        result = grocy.import_grocy_csv_directory(self.db, str(self.root), dry_run)
        self.db.expire_all()
        return result

    def existing_recipe(self):
        self.run_import()
        food = self.db.query(models.Food).filter_by(name="Testprodukt").one()
        recipe = models.Recipe(name="Testrezept")
        recipe.ingredients.append(models.RecipeIngredient(food_id=food.id, quantity=100))
        self.db.add(recipe)
        self.db.commit()
        self.write_csv("recipes.csv", ["id", "name", "type"], [
            {"id": 1, "name": recipe.name, "type": "normal"},
        ])
        return recipe

    def test_repeated_stock_import_preserves_dates_and_updates_instead_of_adding(self):
        self.stock()
        self.run_import()
        item = self.db.query(models.InventoryItem).one()
        original_id = item.id
        for next_day in (date(2026, 10, 28), date(2026, 10, 29), date(2026, 11, 20)):
            with self.subTest(day=next_day):
                ImportDate.current = next_day
                self.stock(amount=3)
                result = self.run_import()
                item = self.db.query(models.InventoryItem).one()
                self.assertEqual(item.id, original_id)
                self.assertEqual(item.quantity, 3)
                self.assertEqual(item.expiry_date, date(2026, 11, 8))
                self.assertEqual(item.purchase_date, date(2026, 10, 28))
                self.assertEqual(result["imported"]["inventory_items"]["updated"], 1)

    def test_expired_stock_keeps_original_expiry_and_explains_missing_purchase_date(self):
        self.stock(best_before="2026-10-20")
        result = self.run_import()
        item = self.db.query(models.InventoryItem).one()
        self.assertEqual(item.expiry_date, date(2026, 10, 20))
        self.assertEqual(item.expiry_days, 0)
        self.assertTrue(any("Einlagerungsdatum auf 2026-10-20" in warning for warning in result["warnings"]))
        ImportDate.current = date(2026, 10, 29)
        self.run_import()
        self.assertEqual(self.db.query(models.InventoryItem).count(), 1)
        self.assertEqual(item.expiry_date, date(2026, 10, 20))

    def test_expired_stock_uses_supplied_purchase_date(self):
        self.stock(best_before="2026-10-20", purchase="2026-10-10")
        self.run_import()
        item = self.db.query(models.InventoryItem).one()
        self.assertEqual(item.purchase_date, date(2026, 10, 10))
        self.assertEqual(item.expiry_days, 10)
        self.assertEqual(item.expiry_date, date(2026, 10, 20))

    def test_stock_without_expiry_is_reused(self):
        self.stock(best_before="")
        self.run_import()
        ImportDate.current = date(2026, 10, 29)
        self.run_import()
        self.assertIsNone(self.db.query(models.InventoryItem).one().expiry_date)

    def test_different_locations_and_expiry_dates_remain_separate(self):
        self.write_csv("stock_current_location_content.csv", [
            "product_id", "location_id", "amount", "best_before_date",
        ], [
            {"product_id": 1, "location_id": 1, "amount": 2, "best_before_date": "2026-11-08"},
            {"product_id": 1, "location_id": 2, "amount": 3, "best_before_date": "2026-11-08"},
            {"product_id": 1, "location_id": 1, "amount": 4, "best_before_date": "2026-11-09"},
        ])
        self.run_import()
        ImportDate.current = date(2026, 10, 29)
        self.run_import()
        items = self.db.query(models.InventoryItem).all()
        self.assertEqual(len(items), 3)
        self.assertEqual(sum(item.quantity for item in items), 9)

    def test_missing_or_empty_ingredient_file_preserves_existing_recipe(self):
        recipe = self.existing_recipe()
        for empty_file in (False, True):
            with self.subTest(empty_file=empty_file):
                if empty_file:
                    self.write_csv("recipes_pos.csv", ["recipe_id", "product_id", "amount"], [])
                self.run_import()
                self.assertEqual(len(recipe.ingredients), 1)
                self.assertEqual(recipe.ingredients[0].quantity, 100)

    def test_incomplete_ingredient_references_preserve_the_entire_existing_list(self):
        recipe = self.existing_recipe()
        self.write_csv("recipes_pos.csv", ["recipe_id", "product_id", "amount"], [
            {"recipe_id": 1, "product_id": 2, "amount": 25},
            {"recipe_id": 1, "product_id": 999, "amount": 50},
        ])
        result = self.run_import()
        self.assertEqual(len(recipe.ingredients), 1)
        self.assertEqual(recipe.ingredients[0].quantity, 100)
        self.assertEqual(result["imported"]["recipe_ingredients"], {"created": 0, "updated": 0, "skipped": 2})

    def test_complete_ingredients_replace_once_and_dry_run_preserves_original(self):
        recipe = self.existing_recipe()
        self.write_csv("recipes_pos.csv", ["recipe_id", "product_id", "amount"], [
            {"recipe_id": 1, "product_id": 2, "amount": 25},
        ])
        self.stock()
        self.run_import(dry_run=True)
        self.assertEqual(recipe.ingredients[0].quantity, 100)
        self.assertEqual(self.db.query(models.InventoryItem).count(), 0)
        for _ in range(2):
            self.run_import()
            self.assertEqual(len(recipe.ingredients), 1)
            self.assertEqual(recipe.ingredients[0].food.name, "Andere Zutat")
            self.assertEqual(recipe.ingredients[0].quantity, 25)

    def test_receipt_uses_individual_expiry_including_zero_and_group_fallback(self):
        group = models.ProductGroup(name="Bon-Gruppe", default_expiry_days=7)
        food = models.Food(name="Bon-Lebensmittel", product_group=group)
        self.db.add(food)
        self.db.commit()
        for index, (days, group_days, expected) in enumerate([(14, 7, 14), (0, 7, 0), (None, 7, 7), (None, None, None)]):
            with self.subTest(days=days, group_days=group_days):
                food.expiry_days = days
                group.default_expiry_days = group_days
                self.db.commit()
                result = receipt.book_receipt_import(self.db, schemas.ReceiptImportBookRequest(
                    receipt_id=f"{index:064x}",
                    purchase_date=date(2026, 10, 28),
                    items=[schemas.ReceiptImportBookItem(
                        source_index=1, raw_name=food.name, name=food.name,
                        food_id=food.id, quantity=2, unit="g", unit_price=1.5,
                    )],
                ))
                self.assertEqual(result.inventory_items[0].expiry_days, expected)
                self.assertEqual(result.inventory_items[0].quantity, 2)
                self.assertEqual(result.inventory_items[0].price, 1.5)


if __name__ == "__main__":
    unittest.main()
