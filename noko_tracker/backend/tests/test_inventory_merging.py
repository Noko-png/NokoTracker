import asyncio
import os
import unittest
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, security
from app.database import Base, get_db
from app.routers import foods, inventory, meals, product_units
from app.services import nutrition_service
from app.services.inventory_stock import add_or_merge_inventory
from test_security import request


class InventoryMergingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        for router in (foods.router, inventory.router, meals.router, product_units.router):
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

    def test_grams_then_kilograms_keep_first_id_and_grams(self):
        first = self.store(1000, "g")
        merged = self.store(1, "kg")
        self.assertEqual((merged["id"], merged["quantity"], merged["unit"]), (first["id"], 2000, "g"))
        self.assertEqual(merged["product_unit_id"], self.gram["id"])
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
            **current, "quantity": 750, "expected_updated_at": current["updated_at"],
        })
        self.assertEqual((counted["id"], counted["quantity"], counted["unit"]), (first["id"], 750, "g"))
        added = self.call("POST", f'/inventory/{first["id"]}/increase', {"amount": 250})
        self.assertEqual(added["quantity"], 1000)
        taken = self.call("POST", f'/inventory/{first["id"]}/decrease', {"amount": 100})
        self.assertEqual(taken["quantity"], 900)
        self.call("POST", f'/inventory/{first["id"]}/decrease', {"amount": 901}, status=422)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 900)
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_equal_names_do_not_merge_different_foods(self):
        first = self.store(1000, "g")
        other = self.call("POST", "/foods", {
            "name": self.food["name"], "brand": "Andere Marke", "product_unit_id": self.kilogram["id"],
            "serving_size": 1000, "serving_unit": "g",
        }, status=201)
        second = self.store(1, "kg", food_id=other["id"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1000)

    def test_converted_equivalent_price_notes_and_barcode_aliases_preserve_first_details(self):
        first = self.store(1000, "g", price=.004, minimum_quantity=25,
                           barcode="0012345678905", notes="Erster Zugang", storage_location="Vorrat")
        merged = self.store(1, "kg", price=4, minimum_quantity=99,
                            barcode="4012345678901", notes="REWE-Bon", storage_location="Vorrat")
        self.assertEqual((merged["id"], merged["quantity"], merged["price"], merged["minimum_quantity"]),
                         (first["id"], 2000, .004, 25))
        self.assertEqual(merged["barcode"], first["barcode"])
        self.assertEqual(merged["notes"], "Erster Zugang\n\nREWE-Bon")
        repeated_note = self.store(.5, "kg", price=4, notes="REWE-Bon", storage_location="Vorrat")
        self.assertEqual((repeated_note["quantity"], repeated_note["notes"]), (2500, merged["notes"]))
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
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1000)

    def test_explicit_food_conversion_merges_but_mass_and_volume_stay_separate(self):
        first = self.store(1000, "g")
        merged = self.store(1, "Beutel")
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 1500))
        liquid = self.store(1000, "ml")
        self.assertNotEqual(liquid["id"], first["id"])
        self.assertEqual(liquid["quantity"], 1000)

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
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 1900))
        self.call("DELETE", f'/meals/logs/{meal["id"]}', status=204)
        final = self.call("GET", f'/inventory/{first["id"]}')
        self.assertEqual((final["quantity"], final["unit"]), (2000, "g"))
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
        self.assertEqual((merged["id"], merged["quantity"]), (first["id"], 2000))
        self.assertEqual(self.call("GET", f"/inventory/{later_id}")["quantity"], 3)

    def test_conversion_overflow_does_not_change_existing_quantity(self):
        first = self.store(1000, "g")
        self.call("POST", "/inventory", {
            "name": "Mehl", "food_id": self.food["id"], "quantity": 1e308, "unit": "kg",
            "purchase_date": "2026-11-18",
        }, status=422)
        self.assertEqual(self.call("GET", f'/inventory/{first["id"]}')["quantity"], 1000)

    def test_zero_quantity_keeps_each_requested_unit_in_its_own_empty_row(self):
        for unit in ("g", "kg", "Beutel"):
            with self.subTest(unit=unit):
                item = self.store(0, unit)
                self.assertEqual((item["quantity"], item["unit"]), (0, unit))
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
