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
from app.routers import foods, inventory, product_units, shopping
from test_security import request


class MinimumStockTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        for router in (foods.router, inventory.router, product_units.router, shopping.router):
            self.app.include_router(router)
        security.install_security(self.app)

        def database():
            with Session(self.engine) as db:
                yield db

        self.app.dependency_overrides[get_db] = database
        environment = patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)
        self.unit = self.call("POST", "/product-units", {"name": "kg"}, status=201)
        self.food = self.create_food()

    def call(self, method, path, payload=None, *, status=200):
        actual, result = asyncio.run(request(self.app, method, path, payload, peer="127.0.0.1"))
        self.assertEqual(actual, status, result)
        return result

    def create_food(self, **values):
        return self.call("POST", "/foods", {
            "name": "Mehl", "minimum_quantity": 2, "product_unit_id": self.unit["id"],
            "serving_size": 1000, "serving_unit": "g", **values,
        }, status=201)

    def store(self, quantity, unit, **values):
        return self.call("POST", "/inventory", {
            "name": self.food["name"], "food_id": self.food["id"], "quantity": quantity, "unit": unit, **values,
        }, status=201)

    def warnings(self):
        return self.call("GET", "/inventory/warnings")["low_stock"]

    def generate(self):
        return self.call("POST", "/shopping-list/generate-from-low-stock", status=201)

    def test_food_without_any_stock_is_reported_and_can_be_purchased(self):
        warning, = self.warnings()
        self.assertEqual((warning["food_id"], warning["quantity"], warning["minimum_quantity"], warning["missing_quantity"], warning["unit"]),
                         (self.food["id"], 0, 2, 2, "kg"))
        self.assertIsNone(warning["inventory_item_id"])
        self.assertEqual(self.call("GET", "/inventory/low-stock"), [warning])
        purchase, = self.generate()
        self.assertEqual((purchase["food_id"], purchase["quantity"], purchase["unit"]), (self.food["id"], 2, "kg"))
        self.assertIsNone(purchase["inventory_item_id"])
        self.assertEqual(self.generate(), [])
        self.assertEqual(self.call("GET", "/inventory"), [])
        self.call("POST", "/shopping-list/import-to-inventory")
        self.assertEqual(self.warnings(), [])
        self.assertEqual(len(self.call("GET", "/inventory")), 1)

    def test_all_lots_are_converted_before_comparing_master_minimum(self):
        self.store(500, "g", minimum_quantity=999, purchase_date="2026-11-18")
        self.store(.75, "kg", minimum_quantity=0, purchase_date="2026-11-19")
        warning, = self.warnings()
        self.assertEqual((warning["quantity"], warning["minimum_quantity"], warning["missing_quantity"], warning["unit"]),
                         (1.25, 2, .75, "kg"))
        purchase, = self.generate()
        self.assertEqual((purchase["quantity"], purchase["unit"]), (.75, "kg"))
        self.call("POST", "/shopping-list/import-to-inventory")
        self.assertEqual(self.warnings(), [])

    def test_master_changes_take_effect_without_editing_existing_lots(self):
        item = self.store(1, "kg", minimum_quantity=99)
        self.call("PATCH", f'/foods/{self.food["id"]}', {"minimum_quantity": 1})
        self.assertEqual(self.warnings(), [])
        self.call("PATCH", f'/foods/{self.food["id"]}', {"minimum_quantity": 3})
        warning, = self.warnings()
        self.assertEqual((warning["quantity"], warning["minimum_quantity"], warning["missing_quantity"]), (1, 3, 2))
        self.assertEqual(self.call("GET", f'/inventory/{item["id"]}')["minimum_quantity"], 99)

    def test_purchase_from_stock_uses_total_shortage_in_selected_lot_unit(self):
        item = self.store(500, "g", minimum_quantity=0, purchase_date="2026-11-18")
        self.store(.75, "kg", purchase_date="2026-11-19")
        purchase = self.call("POST", f'/shopping-list/from-inventory/{item["id"]}', {}, status=201)
        self.assertEqual((purchase["quantity"], purchase["unit"]), (750, "g"))

    def test_zero_minimum_and_archived_foods_do_not_create_warnings(self):
        self.store(0, "kg", minimum_quantity=99)
        self.call("PATCH", f'/foods/{self.food["id"]}', {"minimum_quantity": 0})
        archived = self.create_food(name="Archivware")
        self.call("DELETE", f'/foods/{archived["id"]}?keep_reference=true', status=204)
        self.assertEqual(self.warnings(), [])
        self.assertEqual(self.generate(), [])

    def test_exact_threshold_across_lots_does_not_warn(self):
        self.call("PATCH", f'/foods/{self.food["id"]}', {"minimum_quantity": .3})
        self.store(.1, "kg", purchase_date="2026-11-18")
        self.store(200, "g", purchase_date="2026-11-19")
        self.assertEqual(self.warnings(), [])
        self.assertEqual(self.generate(), [])

    def test_custom_package_minimum_is_compared_to_physical_stock(self):
        package = self.call("POST", "/product-units", {"name": "Packung"}, status=201)
        self.call("PATCH", f'/foods/{self.food["id"]}', {
            "product_unit_id": package["id"], "serving_size": 500, "minimum_quantity": 3,
        })
        self.store(1000, "g")
        warning, = self.warnings()
        self.assertEqual((warning["quantity"], warning["missing_quantity"], warning["unit"]), (2, 1, "Packung"))
        purchase, = self.generate()
        self.assertEqual((purchase["quantity"], purchase["unit"]), (1, "Packung"))

    def test_food_without_primary_unit_uses_its_serving_unit(self):
        self.call("PATCH", f'/foods/{self.food["id"]}', {"product_unit_id": None, "minimum_quantity": 100})
        self.store(50, "g")
        warning, = self.warnings()
        self.assertEqual((warning["quantity"], warning["missing_quantity"], warning["unit"]), (50, 50, "g"))

    def test_same_name_with_different_brand_is_a_different_food(self):
        other = self.create_food(brand="Andere Marke")
        self.assertEqual({row["food_id"] for row in self.warnings()}, {self.food["id"], other["id"]})
        self.assertEqual({row["food_id"] for row in self.generate()}, {self.food["id"], other["id"]})

    def test_existing_open_purchase_in_another_unit_is_not_duplicated(self):
        self.call("POST", "/shopping-list", {
            "name": self.food["name"], "food_id": self.food["id"], "quantity": 2000, "unit": "g",
        }, status=201)
        self.assertEqual(self.generate(), [])
        self.assertEqual(len(self.call("GET", "/shopping-list")), 1)

    def test_checked_purchase_does_not_hide_the_shortage(self):
        self.call("POST", "/shopping-list", {
            "name": self.food["name"], "food_id": self.food["id"], "quantity": 2, "unit": "kg", "is_checked": True,
        }, status=201)
        purchase, = self.generate()
        self.assertFalse(purchase["is_checked"])
        self.assertEqual(purchase["quantity"], 2)
