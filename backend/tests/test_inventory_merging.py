import asyncio
import os
import unittest
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas, security
from app.database import Base, get_db
from app.routers import foods, inventory, meals, product_units, recipes, shopping
from app.services import nutrition_service
from app.services.inventory_stock import add_or_merge_inventory
from app.services.receipt_import_service import book_receipt_import
from test_security import request


LARGE_RECIPE_IMAGE = "data:image/png;base64," + "dGVz" * 256


class InventoryMergingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        for router in (foods.router, inventory.router, meals.router, product_units.router, recipes.router, shopping.router):
            self.app.include_router(router)
        security.install_security(self.app)

        def database():
            with Session(self.engine) as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        environment = patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)
        self.kilogram = self.call("POST", "/product-units", {"name": "kg"}, status=201)
        self.gram = self.call("POST", "/product-units", {"name": "g"}, status=201)
        self.food = self.call("POST", "/foods", {
            "name": "Mehl", "product_unit_id": self.kilogram["id"], "serving_size": 1000, "serving_unit": "g",
            "conversions": [{"quantity": 2, "unit": "Beutel"}, {"quantity": 1000, "unit": "ml"}],
        }, status=201)

    def call(self, method, path, payload=None, *, status=200):
        actual, result = asyncio.run(request(self.app, method, path, payload, peer="127.0.0.1"))
        self.assertEqual(actual, status, result)
        return result

    def store(self, quantity, unit, **fields):
        return self.call("POST", "/inventory", {
            "name": self.food["name"], "food_id": self.food["id"], "quantity": quantity, "unit": unit,
            "purchase_date": "2026-11-18", **fields,
        }, status=201)

    def test_grams_then_kilograms_use_primary_kilograms_and_keep_first_id(self):
        first = self.store(1000, "g")
        merged = self.store(1, "kg")
        self.assertEqual((first["quantity"], first["unit"]), (1, "kg"))
        self.assertEqual((merged["id"], merged["quantity"], merged["unit"]), (first["id"], 2, "kg"))
        self.assertEqual(merged["product_unit_id"], self.kilogram["id"])
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_kilograms_then_grams_keep_first_id_and_kilograms(self):
        first = self.store(1, "kg")
        merged = self.store(1000, "g")
        self.assertEqual((merged["id"], merged["quantity"], merged["unit"]), (first["id"], 2, "kg"))
        self.assertEqual(merged["product_unit_id"], self.kilogram["id"])
        self.assertEqual((merged["serving_size"], merged["serving_unit"]), (first["serving_size"], first["serving_unit"]))

    def test_stocktaking_is_absolute_and_quantity_changes_use_existing_row(self):
        first = self.store(1000, "g")
        self.store(1, "kg")
        current = self.call("GET", f'/inventory/{first["id"]}')
        counted = self.call("PUT", f'/inventory/{first["id"]}', {
            **current, "quantity": 750, "unit": "g", "expected_updated_at": current["updated_at"],
        })
        self.assertEqual((counted["id"], counted["quantity"], counted["unit"]), (first["id"], .75, "kg"))
        added = self.call("POST", f'/inventory/{first["id"]}/increase', {"amount": .25})
        self.assertEqual(added["quantity"], 1)
        taken = self.call("POST", f'/inventory/{first["id"]}/decrease', {"amount": .1})
        self.assertEqual(taken["quantity"], .9)
        self.call("POST", f'/inventory/{first["id"]}/decrease', {"amount": .901}, status=422)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], .9)
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_stock_underflow_and_confirmed_removal_do_not_overwrite_newer_stock(self):
        first = self.store(.9999999, "kg", storage_location="Kueche")
        reserve = self.store(1, "kg", storage_location="Vorrat")
        path = f'/inventory/{first["id"]}'
        failed = self.call("POST", f"{path}/decrease", {"amount": 1}, status=422)
        self.assertEqual(failed["detail"], "Quantity cannot fall below 0")
        self.assertEqual(self.call("GET", path), first)

        updated = self.call("POST", f"{path}/increase", {"amount": .1})
        self.call("DELETE", f'{path}?expected_updated_at={first["updated_at"]}', status=409)
        self.assertEqual(self.call("GET", path), updated)

        remaining = self.call("POST", f"{path}/decrease", {"amount": .1})
        self.call("POST", f"{path}/decrease", {"amount": 1}, status=422)
        self.call("DELETE", f'{path}?expected_updated_at={remaining["updated_at"]}', status=204)
        self.assertEqual(self.call("GET", "/inventory"), [reserve])
        self.assertEqual(self.call("GET", f'/foods/{self.food["id"]}'), self.food)

    def test_equal_names_do_not_merge_different_foods(self):
        first = self.store(1000, "g")
        other = self.call("POST", "/foods", {
            "name": self.food["name"], "brand": "Andere Marke", "product_unit_id": self.kilogram["id"],
            "serving_size": 1000, "serving_unit": "g",
        }, status=201)
        second = self.store(1, "kg", food_id=other["id"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1)

    def test_converted_equivalent_price_notes_and_barcode_aliases_preserve_first_details(self):
        first = self.store(1000, "g", price=.004, minimum_quantity=25,
                           barcode="0012345678905", notes="Erster Zugang", storage_location="Vorrat")
        merged = self.store(1, "kg", price=4, minimum_quantity=99,
                            barcode="4012345678901", notes="REWE-Bon", storage_location="Vorrat")
        self.assertEqual((merged["id"], merged["quantity"], merged["price"], merged["minimum_quantity"]),
                         (first["id"], 2, 4, .025))
        self.assertEqual(merged["quantity"] * merged["price"], 8)
        self.assertEqual(merged["barcode"], first["barcode"])
        self.assertEqual(merged["notes"], "Erster Zugang\n\nREWE-Bon")
        repeated_note = self.store(.5, "kg", price=4, notes="REWE-Bon", storage_location="Vorrat")
        self.assertEqual((repeated_note["quantity"], repeated_note["notes"]), (2.5, merged["notes"]))
        food = self.call("GET", f'/foods/{self.food["id"]}')
        self.assertEqual(set(food["barcodes"]), {"0012345678905", "4012345678901"})

    def test_distinct_lot_metadata_and_incompatible_prices_keep_separate_rows(self):
        first = self.store(1000, "g", price=.004)
        with Session(self.engine) as db:
            group = models.ProductGroup(name="Andere Gruppe")
            db.add(group)
            db.commit()
            group_id = group.id
        for fields in (
            {"purchase_date": "2026-11-19", "price": 4}, {"expiry_days": 7, "price": 4},
            {"storage_location": "Keller", "price": 4}, {"product_group_id": group_id, "price": 4},
            {"image_path": "data:image/png;base64,dGVzdA==", "price": 4}, {"price": 5}, {"price": None},
        ):
            with self.subTest(fields=fields):
                added = self.store(1, "kg", **fields)
                self.assertNotEqual(added["id"], first["id"])
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1)

    def test_explicit_food_conversion_merges_and_incompatible_dimensions_are_rejected(self):
        first = self.store(1000, "g")
        merged = self.store(1, "Beutel")
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 1.5))
        self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": "Mehl", "quantity": 1000, "unit": "ml",
        }, status=422)
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_changed_custom_pack_snapshot_is_not_merged_using_current_food_factor(self):
        pack = self.call("POST", "/product-units", {"name": "Packung"}, status=201)
        self.food = self.call("POST", "/foods", {
            "name": "Packware", "product_unit_id": pack["id"], "serving_size": 500, "serving_unit": "g",
        }, status=201)
        first = self.store(1, "Packung")
        self.call("PATCH", f'/foods/{self.food["id"]}', {"serving_size": 1000})
        second = self.store(1, "Packung")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["serving_size"], 500)

    def test_legacy_pack_factor_disagreement_preserves_total_stock_by_keeping_rows_separate(self):
        pack = self.call("POST", "/product-units", {"name": "Packung"}, status=201)
        self.food = self.call("POST", "/foods", {
            "name": "Altware", "product_unit_id": pack["id"], "serving_size": 100, "serving_unit": "g",
        }, status=201)
        with Session(self.engine) as db:
            legacy = models.InventoryItem(
                name="Altware", food_id=self.food["id"], quantity=1, unit="Packung",
                serving_size=500, serving_unit="g", purchase_date=date(2026, 11, 18),
            )
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
        added = self.store(100, "g")
        self.assertNotEqual(added["id"], legacy_id)
        with Session(self.engine) as db:
            available = sum(nutrition_service.food_amount_in_grams(row, row.quantity, row.unit)
                            for row in db.query(models.InventoryItem))
            self.assertEqual(available, 200)

    def test_merging_preserves_existing_meal_deduction_and_refund(self):
        first = self.store(1000, "g")
        meal = self.call("POST", "/meals/logs", {
            "food_id": self.food["id"], "quantity": 100, "unit": "g", "deduct_inventory": True,
            "booking_key": "inventory-merge-refund",
        }, status=201)
        merged = self.store(1, "kg")
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 1.9))
        self.call("DELETE", f'/meals/logs/{meal["id"]}', status=204)
        final = self.call("GET", f'/inventory/{first["id"]}')
        self.assertEqual((final["quantity"], final["unit"]), (2, "kg"))
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_oldest_compatible_row_is_used_without_consolidating_later_rows(self):
        first = self.store(1000, "g")
        with Session(self.engine) as db:
            later = models.InventoryItem(
                name="Alter Anzeigename", food_id=self.food["id"], quantity=3, unit="kg",
                serving_size=1000, serving_unit="g", purchase_date=date(2026, 11, 18),
            )
            db.add(later)
            db.commit()
            later_id = later.id
        merged = self.store(1, "kg")
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 2))
        self.assertEqual(self.call("GET", f"/inventory/{later_id}")["quantity"], 3)

    def test_conversion_overflow_does_not_change_existing_quantity(self):
        first = self.store(1000, "g")
        self.call("POST", "/inventory", {
            "name": "Mehl", "food_id": self.food["id"], "quantity": 1e308, "unit": "kg",
            "purchase_date": "2026-11-18",
        }, status=422)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1)

    def test_zero_quantity_also_uses_primary_unit(self):
        for unit in ("g", "kg", "Beutel"):
            with self.subTest(unit=unit):
                item = self.store(0, unit)
                self.assertEqual((item["quantity"], item["unit"]), (0, "kg"))
        self.assertEqual(len(self.call("GET", "/inventory")), 3)

    def test_non_finite_quantity_is_rejected_before_inserting_any_stock(self):
        self.call("POST", "/inventory", {
            "name": "Mehl", "food_id": self.food["id"], "quantity": "Infinity", "unit": "kg",
        }, status=422)
        with Session(self.engine) as db:
            incoming = models.InventoryItem(
                name="Mehl", food_id=self.food["id"], quantity=float("inf"), unit="kg",
                serving_size=1000, serving_unit="g", purchase_date=date(2026, 11, 18),
            )
            with self.assertRaises(HTTPException) as caught:
                add_or_merge_inventory(db, incoming)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(db.query(models.InventoryItem).count(), 0)

    def can_food(self, serving_size=400, serving_unit="g"):
        can = self.call("POST", "/product-units", {"name": "Dose"}, status=201)
        self.food = self.call("POST", "/foods", {
            "name": "Dosentomaten", "product_unit_id": can["id"], "serving_size": serving_size,
            "serving_unit": serving_unit, "conversions": [{"quantity": 2, "unit": "Portion"}],
            "calories_per_100g": 40, "price": 2,
        }, status=201)
        return can

    def test_grams_and_fractional_amounts_are_saved_in_cans_with_unchanged_food_conversion(self):
        can = self.can_food()
        first = self.store(800, "g", price=.005)
        self.assertEqual((first["quantity"], first["unit"], first["product_unit_id"], first["price"]), (2, "Dose", can["id"], 2))
        partial = self.store(100, "g", price=.005)
        self.assertEqual((partial["id"], partial["quantity"], partial["unit"]), (first["id"], 2.25, "Dose"))
        self.assertEqual((partial["serving_size"], partial["serving_unit"]), (400, "g"))
        self.assertEqual(partial["quantity"] * partial["price"], 4.5)
        self.assertEqual(self.call("GET", f'/foods/{self.food["id"]}'), self.food)

    def test_stocktaking_in_grams_preserves_can_unit_and_stock_value(self):
        self.can_food()
        first = self.store(800, "g", price=.005)
        counted = self.call("PUT", f'/inventory/{first["id"]}', {
            "food_id": self.food["id"], "name": self.food["name"], "quantity": 300, "unit": "g", "price": .005,
            "minimum_quantity": 200, "expected_updated_at": first["updated_at"],
        })
        self.assertEqual((counted["quantity"], counted["unit"], counted["price"], counted["minimum_quantity"]), (.75, "Dose", 2, .5))
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_shopping_and_receipt_imports_also_store_can_units(self):
        self.can_food()
        first = self.store(800, "g")
        purchase = self.call("POST", "/shopping-list", {
            "name": self.food["name"], "food_id": self.food["id"], "quantity": 400, "unit": "g",
        }, status=201)
        self.call("POST", f'/shopping-list/{purchase["id"]}/check')
        self.call("POST", "/shopping-list/import-to-inventory", {"purchase_date": "2026-11-18"})
        with Session(self.engine) as db:
            result = book_receipt_import(db, schemas.ReceiptImportBookRequest(purchase_date=date(2026, 11, 18), items=[
                schemas.ReceiptImportBookItem(source_index=0, raw_name="Tomaten", name=self.food["name"],
                                             food_id=self.food["id"], quantity=200, unit="g"),
            ]))
            self.assertEqual(result.booked_count, 1)
        row, = self.call("GET", "/inventory")
        self.assertEqual((row["id"], row["quantity"], row["unit"]), (first["id"], 3.5, "Dose"))

    def test_shopping_import_books_only_checked_purchases_and_asks_only_about_checked_unknowns(self):
        food_id = self.food["id"]
        purchased = self.call("POST", "/shopping-list", {
            "name": self.food["name"], "food_id": food_id, "quantity": .5, "unit": "kg",
        }, status=201)
        open_unknown = self.call("POST", "/shopping-list", {"name": "Noch zu kaufen"}, status=201)
        empty = self.call("POST", "/shopping-list/import-to-inventory", {"unknown_item_action": "create"})
        self.assertEqual(empty["imported_count"], 0)
        self.assertEqual(self.call("GET", "/inventory"), [])
        self.assertEqual(self.call("GET", "/shopping-list"), [purchased, open_unknown])

        self.call("POST", f'/shopping-list/{purchased["id"]}/check')
        open_known = self.call("POST", "/shopping-list", {
            "name": self.food["name"], "food_id": food_id, "quantity": 2, "unit": "kg",
        }, status=201)
        checked_unknown = self.call("POST", "/shopping-list", {
            "name": "Unbekannter Kauf", "is_checked": True,
        }, status=201)
        preview = self.call("POST", "/shopping-list/import-to-inventory")
        self.assertTrue(preview["requires_decision"])
        self.assertEqual(preview["unknown_items"], [checked_unknown])
        self.assertEqual(self.call("GET", "/inventory"), [])

        result = self.call("POST", "/shopping-list/import-to-inventory", {"unknown_item_action": "delete"})
        self.assertEqual(result["imported_count"], 1)
        self.assertEqual(result["deleted_shopping_item_ids"], [purchased["id"], checked_unknown["id"]])
        row, = self.call("GET", "/inventory")
        self.assertEqual((row["food_id"], row["quantity"], row["unit"]), (food_id, .5, "kg"))
        self.assertEqual(self.call("GET", "/shopping-list"), [open_unknown, open_known])
        self.assertEqual(self.call("POST", "/shopping-list/import-to-inventory")["imported_count"], 0)

    def test_recipe_and_tracker_deduct_grams_from_cans_and_refund_cans(self):
        self.can_food()
        first = self.store(800, "g")
        recipe = self.call("POST", "/recipes", {
            "name": "Tomatensauce", "servings": 1, "ingredients": [
                {"food_id": self.food["id"], "quantity": 100, "unit": "g"},
                {"food_id": self.food["id"], "quantity": .5, "unit": "Portion"},
            ],
        }, status=201)
        prepared = self.call("POST", f'/recipes/{recipe["id"]}/prepare', status=201)
        self.assertEqual(prepared["consumed"][0]["quantity"], 200)
        self.assertEqual(prepared["inventory_item"]["unit"], "Portion")
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1.5)
        meal = self.call("POST", "/meals/logs", {
            "food_id": self.food["id"], "quantity": 100, "unit": "g", "deduct_inventory": True,
            "booking_key": "standard-can-refund",
        }, status=201)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1.25)
        self.call("DELETE", f'/meals/logs/{meal["id"]}', status=204)
        final = self.call("GET", f'/inventory/{first["id"]}')
        self.assertEqual((final["quantity"], final["unit"], final["serving_size"], final["serving_unit"]), (1.5, "Dose", 400, "g"))
        with Session(self.engine) as db:
            row = db.get(models.InventoryItem, first["id"])
            self.assertEqual(nutrition_service.food_amount_in_grams(row, row.quantity, row.unit), 600)

    def test_prepared_portions_can_be_planned_across_seven_days_without_replacing_meals(self):
        self.store(1, "kg")
        recipe = self.call("POST", "/recipes", {
            "name": "Brot", "servings": 3,
            "ingredients": [{"food_id": self.food["id"], "quantity": 1, "unit": "kg"}],
        }, status=201)
        prepared = self.call("POST", f'/recipes/{recipe["id"]}/prepare', status=201)["inventory_item"]
        with Session(self.engine) as db:
            user = models.User(username="Mealprep")
            db.add(user)
            db.commit()
            user_id = user.id
        occupied = self.call("POST", "/meals/logs", {
            "food_id": self.food["id"], "user_id": user_id, "quantity": 1, "unit": "kg",
            "eaten_at": "2026-11-25T08:00:00", "meal_type": "Fruehstueck", "meal_source": "mealprep",
        }, status=201)

        path = "/meals/logs/plan-prepared"
        plan = {
            "recipe_id": recipe["id"], "inventory_item_id": prepared["id"], "user_id": user_id,
            "start_date": "2026-11-25",
        }
        breakfast = {"day": "2026-11-26", "meal_type": "breakfast"}
        lunch = {"day": "2026-11-25", "meal_type": "lunch"}
        dinner = {"day": "2026-12-01", "meal_type": "dinner"}
        self.call("POST", path, {**plan, "slots": [lunch, {**breakfast, "day": "2026-11-25"}]}, status=409)
        self.call("POST", path, {**plan, "slots": [lunch, lunch]}, status=422)
        self.call("POST", path, {**plan, "slots": [{**dinner, "day": "2026-12-02"}]}, status=422)
        self.call("POST", path, {**plan, "slots": [breakfast, lunch, dinner, {**dinner, "day": "2026-11-30"}]}, status=409)
        self.assertEqual(self.call("GET", "/meals/logs"), [occupied])

        selection = {**plan, "slots": [breakfast, lunch, dinner]}
        logs = self.call("POST", path, selection, status=201)
        self.assertEqual([(row["meal_type"], row["eaten_at"]) for row in logs], [
            ("Frühstück", "2026-11-26T08:00:00"),
            ("Mittagessen", "2026-11-25T12:30:00"),
            ("Abendessen", "2026-12-01T18:30:00"),
        ])
        for row in logs:
            self.assertEqual((row["food_id"], row["user_id"], row["quantity"], row["unit"]),
                             (prepared["food_id"], user_id, 1, "Portion"))
            self.assertEqual(row["meal_source"], "mealprep")
            self.assertTrue(row["planned_inventory_deduction"])
            self.assertIsNone(row["inventory_deducted_at"])
        self.call("POST", path, selection, status=409)
        self.assertEqual(self.call("GET", "/meals/logs"), [occupied, *logs])
        self.assertEqual(self.call("GET", f'/inventory/{prepared["id"]}')["quantity"], 3)

    def test_inventory_reads_an_existing_large_recipe_image(self):
        stored = self.store(1, "kg")
        with Session(self.engine) as db:
            row = db.get(models.InventoryItem, stored["id"])
            row.image_path = LARGE_RECIPE_IMAGE
            db.commit()

        item, = self.call("GET", "/inventory")
        self.assertEqual((item["id"], item["quantity"]), (stored["id"], 1))
        self.assertEqual(item["image_path"], LARGE_RECIPE_IMAGE)

    def test_large_recipe_image_survives_preparing_editing_and_refunding_stock(self):
        ingredient_stock = self.store(1, "kg")
        recipe = self.call("POST", "/recipes", {
            "name": "Gericht mit Bild", "servings": 2, "image_path": LARGE_RECIPE_IMAGE,
            "ingredients": [{"food_id": self.food["id"], "quantity": 400, "unit": "g"}],
        }, status=201)
        prepared = self.call("POST", f'/recipes/{recipe["id"]}/prepare', status=201)["inventory_item"]
        self.assertEqual(prepared["image_path"], LARGE_RECIPE_IMAGE)
        self.assertEqual((prepared["quantity"], prepared["unit"]), (2, "Portion"))
        self.assertEqual(self.call("GET", f'/inventory/{ingredient_stock["id"]}')["quantity"], .6)

        path = f'/inventory/{prepared["id"]}'
        edited = self.call("PUT", path, {
            **prepared, "notes": "Für später", "expected_updated_at": prepared["updated_at"],
        })
        self.assertEqual(edited["image_path"], LARGE_RECIPE_IMAGE)
        meal = self.call("POST", "/meals/logs", {
            "food_id": prepared["food_id"], "quantity": 1, "unit": "Portion",
            "deduct_inventory": True, "booking_key": "large-recipe-image",
        }, status=201)
        self.assertEqual(self.call("GET", path)["quantity"], 1)

        self.call("DELETE", path, status=204)
        self.call("DELETE", f'/meals/logs/{meal["id"]}', status=204)
        restored, = [row for row in self.call("GET", "/inventory") if row["food_id"] == prepared["food_id"]]
        self.assertEqual((restored["quantity"], restored["unit"], restored["notes"]), (1, "Portion", "Für später"))
        self.assertEqual(restored["image_path"], LARGE_RECIPE_IMAGE)

    def test_legacy_gram_lot_and_recorded_refund_are_converted_without_losing_stock(self):
        self.can_food()
        with Session(self.engine) as db:
            old = models.InventoryItem(name=self.food["name"], food_id=self.food["id"], quantity=800, unit="g",
                                       serving_size=1, serving_unit="g", price=.005, minimum_quantity=100,
                                       purchase_date=date(2026, 11, 18))
            db.add(old)
            db.commit()
            old_id = old.id
        meal = self.call("POST", "/meals/logs", {
            "food_id": self.food["id"], "quantity": 100, "unit": "g", "deduct_inventory": True,
            "booking_key": "legacy-gram-can-refund",
        }, status=201)
        merged = self.store(400, "g", price=.005)
        self.assertEqual((merged["id"], merged["quantity"], merged["unit"], merged["price"]), (old_id, 2.75, "Dose", 2))
        self.assertEqual(merged["minimum_quantity"], .25)
        self.call("DELETE", f'/meals/logs/{meal["id"]}', status=204)
        final, = self.call("GET", "/inventory")
        self.assertEqual((final["id"], final["quantity"], final["unit"], final["price"]), (old_id, 3, "Dose", 2))

    def test_count_based_food_conversion_is_preserved(self):
        self.can_food(serving_size=4, serving_unit="Stueck")
        first = self.store(8, "Stueck")
        self.assertEqual((first["quantity"], first["unit"], first["serving_size"], first["serving_unit"]), (2, "Dose", 4, "Stueck"))

    def test_zero_amount_uses_can_unit_and_unrepresentable_fraction_is_rejected(self):
        self.can_food()
        self.assertEqual(self.store(0, "g")["unit"], "Dose")
        self.call("PATCH", f'/foods/{self.food["id"]}', {"serving_size": 1e10})
        self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": self.food["name"], "quantity": 1e-10, "unit": "g",
        }, status=422)
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_merging_cannot_overflow_the_underlying_amount_in_grams(self):
        self.can_food()
        for _ in range(4):
            first = self.store(1e305, "Dose")
        self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": self.food["name"], "quantity": 1e305, "unit": "Dose",
            "purchase_date": "2026-11-18",
        }, status=422)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 4e305)
