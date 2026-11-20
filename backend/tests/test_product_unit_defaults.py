import asyncio
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import security
from app.database import Base, get_db
from app.routers import foods, inventory, product_units
from test_security import request


class ProductUnitDefaultsTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        for router in (product_units.router, foods.router, inventory.router):
            self.app.include_router(router)
        security.install_security(self.app)

        def override_db():
            with Session(self.engine) as db:
                yield db

        self.app.dependency_overrides[get_db] = override_db
        environment = patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"})
        environment.start()
        self.addCleanup(environment.stop)

    def call(self, method, path, payload=None, *, status=200):
        actual_status, result = asyncio.run(request(self.app, method, path, payload, peer="127.0.0.1"))
        self.assertEqual(actual_status, status, result)
        return result

    def unit(self, name="Packung", quantity=250, target="g"):
        return self.call("POST", "/product-units", {
            "name": name, "default_conversion_quantity": quantity, "default_conversion_unit": target,
        }, status=201)

    def test_crud_normalizes_defaults_and_checks_merged_partial_updates(self):
        unit = self.unit(" Packung ", "1 1/2", " KG ")
        self.assertEqual((unit["name"], unit["default_conversion_quantity"], unit["default_conversion_unit"]),
                         ("Packung", 1.5, "kg"))
        path = f'/product-units/{unit["id"]}'
        renamed = self.call("PATCH", path, {"name": "Paket"})
        self.assertEqual(renamed["default_conversion_quantity"], 1.5)
        changed = self.call("PATCH", path, {"default_conversion_quantity": "1/2"})
        self.assertEqual((changed["default_conversion_quantity"], changed["default_conversion_unit"]), (.5, "kg"))
        changed = self.call("PATCH", path, {"default_conversion_unit": "G"})
        self.assertEqual((changed["default_conversion_quantity"], changed["default_conversion_unit"]), (.5, "g"))
        self.call("PATCH", path, {"default_conversion_quantity": None}, status=422)
        self.call("PATCH", path, {"name": None}, status=422)
        self.call("PATCH", path, {"name": "   "}, status=422)
        cleared = self.call("PATCH", path, {"default_conversion_quantity": None, "default_conversion_unit": None})
        self.assertIsNone(cleared["default_conversion_quantity"])
        self.assertIsNone(cleared["default_conversion_unit"])
        self.assertEqual(self.call("GET", path), cleared)
        self.assertEqual(self.call("GET", "/product-units"), [cleared])
        self.call("PATCH", path, {"default_conversion_unit": "g"}, status=422)

    def test_incomplete_nonfinite_and_unknown_default_conversions_are_rejected(self):
        for payload in (
            {"default_conversion_quantity": 250}, {"default_conversion_unit": "g"},
            {"default_conversion_quantity": 0, "default_conversion_unit": "g"},
            {"default_conversion_quantity": -1, "default_conversion_unit": "g"},
            {"default_conversion_quantity": "NaN", "default_conversion_unit": "g"},
            {"default_conversion_quantity": "Infinity", "default_conversion_unit": "g"},
            {"default_conversion_quantity": 1, "default_conversion_unit": "Packung"},
        ):
            with self.subTest(payload=payload):
                self.call("POST", "/product-units", {"name": "Test", **payload}, status=422)
        self.assertEqual(self.call("GET", "/product-units"), [])

    def test_new_foods_use_defaults_and_preserve_explicit_partial_conversion(self):
        unit = self.unit()
        for index, (overrides, expected) in enumerate((
            ({}, (250, "g")),
            ({"serving_size": 75, "serving_unit": "ml"}, (75, "ml")),
            ({"serving_size": 80}, (80, "g")),
            ({"serving_unit": "ml"}, (100, "ml")),
        )):
            with self.subTest(overrides=overrides):
                food = self.call("POST", "/foods", {
                    "name": f"Food {index}", "product_unit_id": unit["id"], **overrides,
                }, status=201)
                self.assertEqual((food["serving_size"], food["serving_unit"]), expected)

    def test_inventory_create_uses_defaults_and_preserves_existing_food_conversion(self):
        unit = self.unit()
        item = self.call("POST", "/inventory", {"name": "Neues Produkt", "unit": "Packung"}, status=201)
        self.assertEqual((item["serving_size"], item["serving_unit"]), (250, "g"))
        self.assertEqual(item["product_unit"]["default_conversion_quantity"], 250)
        food = self.call("POST", "/foods", {
            "name": "Bestehendes Produkt", "product_unit_id": unit["id"],
            "serving_size": 330, "serving_unit": "ml",
        }, status=201)
        for selection in ({"food_id": food["id"]}, {}):
            with self.subTest(selection=selection):
                linked = self.call("POST", "/inventory", {
                    "name": food["name"], "product_unit_id": unit["id"], **selection,
                }, status=201)
                self.assertEqual((linked["serving_size"], linked["serving_unit"]), (330, "ml"))
        self.assertEqual(self.call("GET", f'/foods/{food["id"]}')["serving_size"], 330)

    def test_manual_inventory_conversion_is_kept_when_replacing_linked_stock(self):
        unit = self.unit()
        item = self.call("POST", "/inventory", {
            "name": "Individuell", "product_unit_id": unit["id"], "serving_size": 400,
        }, status=201)
        self.assertEqual((item["serving_size"], item["serving_unit"]), (400, "g"))
        replaced = self.call("PUT", f'/inventory/{item["id"]}', {
            "name": item["name"], "food_id": item["food_id"], "product_unit_id": unit["id"],
            "expected_updated_at": item["updated_at"], "serving_size": 120, "serving_unit": "ml",
        })
        self.assertEqual((replaced["serving_size"], replaced["serving_unit"]), (400, "g"))

    def test_inventory_unit_must_be_registered_for_food_before_using_it(self):
        gram = self.unit("g", 1)
        bag = self.unit("Beutel", 500)
        food = self.call("POST", "/foods", {"name": "Mehl", "product_unit_id": gram["id"]}, status=201)
        self.call("POST", "/inventory", {
            "name": food["name"], "food_id": food["id"], "product_unit_id": bag["id"],
        }, status=422)
        self.call("PATCH", f'/foods/{food["id"]}', {
            "conversions": [{"quantity": .002, "unit": "Beutel"}],
        })
        for index, selection in enumerate(({"food_id": food["id"]}, {})):
            with self.subTest(selection=selection):
                item = self.call("POST", "/inventory", {
                    "name": food["name"], "product_unit_id": bag["id"], "quantity": 1, **selection,
                }, status=201)
                self.assertEqual((item["quantity"], item["unit"], item["product_unit_id"]), (500 * (index + 1), "g", gram["id"]))
                self.assertEqual((item["serving_size"], item["serving_unit"]), (1, "g"))
                saved_food = self.call("GET", f'/foods/{food["id"]}')
                self.assertEqual((saved_food["product_unit_id"], saved_food["serving_size"]), (gram["id"], 1))

    def test_editing_or_deleting_unit_does_not_change_existing_conversion(self):
        unit = self.unit()
        food = self.call("POST", "/foods", {"name": "Alt", "product_unit_id": unit["id"]}, status=201)
        item = self.call("POST", "/inventory", {
            "name": food["name"], "food_id": food["id"], "product_unit_id": unit["id"],
        }, status=201)
        self.call("PATCH", f'/product-units/{unit["id"]}', {"default_conversion_quantity": 500})
        self.call("PATCH", f'/foods/{food["id"]}', {"brand": "Marke"})
        self.assertEqual(self.call("GET", f'/foods/{food["id"]}')["serving_size"], 250)
        created = self.call("POST", "/foods", {"name": "Neu", "product_unit_id": unit["id"]}, status=201)
        self.assertEqual(created["serving_size"], 500)
        self.call("DELETE", f'/product-units/{unit["id"]}', status=204)
        for path in (f'/foods/{food["id"]}', f'/inventory/{item["id"]}'):
            value = self.call("GET", path)
            self.assertIsNone(value["product_unit_id"])
            self.assertEqual((value["serving_size"], value["serving_unit"]), (250, "g"))

    def test_legacy_unit_schema_migrates_at_startup_and_preserves_saved_defaults(self):
        script = '''
import sqlite3
from sqlalchemy import inspect
from app.database import DATABASE_PATH, SessionLocal, engine
with sqlite3.connect(DATABASE_PATH) as connection:
    connection.execute("CREATE TABLE product_units (id INTEGER PRIMARY KEY, name VARCHAR(32) NOT NULL UNIQUE, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)")
    connection.execute("INSERT INTO product_units VALUES (42, 'Altbestand', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
from app.main import migrate_sqlite_product_unit_schema
from app.models import ProductUnit
with SessionLocal() as session:
    unit = session.get(ProductUnit, 42)
    assert unit.default_conversion_quantity is None
    assert unit.default_conversion_unit is None
    unit.default_conversion_quantity = 330
    unit.default_conversion_unit = 'ml'
    session.commit()
migrate_sqlite_product_unit_schema()
with SessionLocal() as session:
    unit = session.get(ProductUnit, 42)
    assert (unit.name, unit.default_conversion_quantity, unit.default_conversion_unit) == ('Altbestand', 330, 'ml')
engine.dispose()
'''
        with tempfile.TemporaryDirectory(prefix="noko-unit-migration-") as directory:
            path = Path(directory) / "legacy.db"
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "DATABASE_URL": "sqlite:///" + path.as_posix()},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
