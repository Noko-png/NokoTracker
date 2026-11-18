import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, security
from app.database import Base, get_db
from app.routers import foods, inventory, product_units
from test_security import request


class InventoryFoodRulesTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        for router in (foods.router, inventory.router, product_units.router):
            self.app.include_router(router)
        security.install_security(self.app)

        def database():
            with Session(self.engine) as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        environment = patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)
        self.pack = self.call("POST", "/product-units", {"name": "Packung"}, status=201)
        self.kilogram = self.call("POST", "/product-units", {"name": "kg"}, status=201)
        self.food = self.call("POST", "/foods", {
            "name": "Mehl", "brand": "Marke", "category": "Backen", "product_unit_id": self.pack["id"],
            "serving_size": 500, "serving_unit": "g", "conversions": [{"quantity": 2, "unit": "Beutel"}],
            "calories_per_100g": 345, "protein_per_100g": 12, "carbs_per_100g": 68, "fat_per_100g": 1.2,
        }, status=201)

    def call(self, method, path, payload=None, *, status=200):
        actual, result = asyncio.run(request(self.app, method, path, payload, peer="127.0.0.1"))
        self.assertEqual(actual, status, result)
        return result

    def macro_values(self, value):
        return tuple(value[field] for field in (
            "calories_per_100g", "protein_per_100g", "carbs_per_100g", "fat_per_100g",
        ))

    def test_create_and_replace_use_food_nutrition_and_registered_conversion(self):
        item = self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": "Anderer Name", "brand": "Andere Marke", "unit": "Beutel",
            "product_unit_id": self.kilogram["id"], "quantity": 3,
            "serving_size": 999, "serving_unit": "kg", "calories_per_100g": 999,
            "protein_per_100g": 999, "carbs_per_100g": 999, "fat_per_100g": 999,
        }, status=201)
        self.assertEqual((item["name"], item["brand"], item["unit"]), ("Mehl", "Marke", "Beutel"))
        self.assertEqual((item["serving_size"], item["serving_unit"]), (250, "g"))
        self.assertIsNone(item["product_unit_id"])
        self.assertEqual(self.macro_values(item), self.macro_values(self.food))
        updated = self.call("PUT", f'/inventory/{item["id"]}', {
            "food_id": self.food["id"], "name": "Ueberschreiben", "unit": "g", "quantity": 700,
            "expected_updated_at": item["updated_at"], "serving_size": 1, "serving_unit": "kg",
            "calories_per_100g": 0, "protein_per_100g": 0, "carbs_per_100g": 0, "fat_per_100g": 0,
        })
        self.assertEqual((updated["serving_size"], updated["serving_unit"]), (1, "g"))
        self.assertEqual(self.macro_values(updated), self.macro_values(self.food))
        self.assertEqual(self.call("GET", f'/foods/{self.food["id"]}'), self.food)

    def test_only_food_units_and_same_factor_aliases_are_available(self):
        for unit, canonical, pair in (
            ("Packung", "Packung", (500, "g")), (" beutel ", "Beutel", (250, "g")),
            (" GRAMM ", "g", (1, "g")),
        ):
            with self.subTest(unit=unit):
                item = self.call("POST", "/inventory", {
                    "food_id": self.food["id"], "name": "Mehl", "unit": unit,
                }, status=201)
                self.assertEqual(item["unit"], canonical)
                self.assertEqual((item["serving_size"], item["serving_unit"]), pair)
        before = self.call("GET", "/inventory")
        for unit in ("kg", "mg", "ml", "Flasche", "Nicht eingerichtet"):
            with self.subTest(unit=unit):
                self.call("POST", "/inventory", {
                    "food_id": self.food["id"], "name": "Mehl", "unit": unit,
                }, status=422)
        self.assertEqual(self.call("GET", "/inventory"), before)
        self.assertEqual(len(self.call("GET", "/product-units")), 2)

    def test_unit_id_without_unit_is_validated_and_omitted_selection_uses_food_unit(self):
        selected = self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": "Mehl", "product_unit_id": self.pack["id"],
        }, status=201)
        self.assertEqual((selected["unit"], selected["product_unit_id"]), ("Packung", self.pack["id"]))
        self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": "Mehl", "product_unit_id": self.kilogram["id"],
        }, status=422)
        default = self.call("POST", "/inventory", {"food_id": self.food["id"], "name": "Mehl"}, status=201)
        self.assertEqual(default["unit"], "Packung")

    def test_name_match_uses_food_values_without_rewriting_food(self):
        item = self.call("POST", "/inventory", {
            "name": self.food["name"], "brand": self.food["brand"], "unit": "Beutel",
            "serving_size": 1, "serving_unit": "kg", "calories_per_100g": 123,
            "category": "Neue Kategorie", "expiry_days": 9,
        }, status=201)
        self.assertEqual(self.macro_values(item), self.macro_values(self.food))
        self.assertEqual(item["category"], self.food["category"])
        self.assertEqual(item["expiry_days"], 9)
        self.call("PUT", f'/inventory/{item["id"]}', {
            "name": self.food["name"], "brand": self.food["brand"], "unit": "Beutel",
            "expected_updated_at": item["updated_at"], "calories_per_100g": 77,
        })
        self.assertEqual(self.call("GET", f'/foods/{self.food["id"]}'), self.food)

    def test_historical_stock_can_keep_its_unit_and_trusted_saved_conversion(self):
        with Session(self.engine) as db:
            item = models.InventoryItem(
                name="Mehl", food_id=self.food["id"], unit="Altbeutel", quantity=4,
                serving_size=125, serving_unit="g",
            )
            db.add(item)
            db.commit()
            item_id = item.id
        saved = self.call("GET", f"/inventory/{item_id}")
        changed = self.call("PUT", f"/inventory/{item_id}", {
            "food_id": self.food["id"], "name": "Mehl", "unit": "altbeutel", "quantity": 3,
            "expected_updated_at": saved["updated_at"], "serving_size": 1, "serving_unit": "kg",
            "calories_per_100g": 999,
        })
        self.assertEqual((changed["unit"], changed["serving_size"], changed["serving_unit"]), ("Altbeutel", 125, "g"))
        self.assertEqual(self.macro_values(changed), self.macro_values(self.food))
        self.call("POST", "/inventory", {
            "food_id": self.food["id"], "name": "Mehl", "unit": "Altbeutel",
        }, status=422)
        self.call("PUT", f"/inventory/{item_id}", {
            "food_id": self.food["id"], "name": "Mehl", "unit": "kg", "expected_updated_at": changed["updated_at"],
        }, status=422)
        self.assertEqual(self.call("GET", f"/inventory/{item_id}"), changed)

    def test_manual_new_food_still_initializes_its_nutrition_and_unit(self):
        item = self.call("POST", "/inventory", {
            "name": "Manuelles Produkt", "unit": "Dose", "serving_size": 330,
            "serving_unit": "ml", "calories_per_100g": 42,
        }, status=201)
        food = self.call("GET", f'/foods/{item["food_id"]}')
        self.assertEqual((food["serving_size"], food["serving_unit"], food["calories_per_100g"]), (330, "ml", 42))
        self.assertEqual(item["product_unit"]["name"], "Dose")
