import json
import ssl
import unittest
from contextlib import contextmanager, nullcontext
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import database, models as m, schemas as s
from app.database import Base, get_db
from app.routers import foods, inventory, meals, recipes, shopping


A = "0012345678905"
B = "4012345678901"
C = "5012345678900"


class BarcodeTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        offline = patch.object(foods, "open_food_facts_product", return_value=None)
        offline.start()
        self.addCleanup(offline.stop)
        session = patch.object(foods, "barcode_db_session", return_value=nullcontext(self.db))
        session.start()
        self.addCleanup(session.stop)

    def food(self, **values):
        return foods.create_food(s.FoodCreate(**{
            "name": f"Produkt {self.db.query(m.Food).count()}",
            "calories_per_100g": 100, "barcodes": [A, B], **values,
        }), self.db)

    def stock(self, food, code=None, quantity=100):
        item = m.InventoryItem(name=food.name, food=food, barcode=code, quantity=quantity, unit="g")
        self.db.add(item)
        self.db.commit()
        return item

    def test_multiple_codes_preserve_leading_zeros_and_deduplicate(self):
        food = self.food(barcodes=[" 0012 3456-78905 ", B, A, ""])
        self.assertEqual(s.FoodRead.model_validate(food).barcodes, [A, B])
        self.assertEqual(food.barcode, A)
        self.assertEqual(self.db.query(m.FoodBarcode).count(), 2)
        for _ in range(2):
            foods.update_food(food.id, s.FoodUpdate(barcodes=[A, B]), self.db)
        self.assertEqual(self.db.query(m.FoodBarcode).count(), 2)

    def test_upgrade_keeps_legacy_code_without_backfill(self):
        self.db.add(m.Food(name="Altbestand", barcode=A, calories_per_100g=100))
        self.db.commit()
        m.FoodBarcode.__table__.drop(self.engine)
        Base.metadata.create_all(self.engine)
        food = self.db.query(m.Food).one()
        self.assertEqual(s.FoodRead.model_validate(food).barcodes, [A])
        self.assertEqual(foods.lookup_food_by_barcode(A).food.id, food.id)
        foods.update_food(food.id, s.FoodUpdate(barcodes=[A, B]), self.db)
        self.assertEqual(food.barcodes, [A, B])

    def test_legacy_clients_and_unrelated_edits_preserve_secondary_codes(self):
        food = foods.create_food(s.FoodCreate(name="Altclient", barcode=A), self.db)
        self.assertEqual(food.barcodes, [A])
        foods.update_food(food.id, s.FoodUpdate(barcodes=[A, B]), self.db)
        foods.update_food(food.id, s.FoodUpdate(expiry_days=14), self.db)
        self.assertEqual(food.barcodes, [A, B])
        foods.update_food(food.id, s.FoodUpdate(barcode=C), self.db)
        self.assertEqual(food.barcodes, [C, B])
        self.assertEqual(food.barcode, C)

    def test_all_codes_find_the_same_product_and_all_lots(self):
        food = self.food()
        lots = [self.stock(food, code) for code in (A, B, None)]
        unrelated = self.food(barcodes=[C])
        self.stock(unrelated, C)
        for code in (A, B):
            result = foods.lookup_food_by_barcode(code)
            self.assertEqual(result.food.id, food.id)
            self.assertEqual({item.id for item in result.inventory_items}, {item.id for item in lots})
            preview = foods.preview_food_by_barcode(code)
            self.assertEqual(preview["name"], food.name)
            self.assertEqual(preview["barcode"], code)
        self.assertEqual(self.db.query(m.Food).count(), 2)

    def test_removing_code_cannot_find_it_through_old_lots(self):
        food = self.food()
        item = self.stock(food, B)
        foods.update_food(food.id, s.FoodUpdate(barcodes=[A]), self.db)
        self.assertIsNone(item.barcode)
        self.assertEqual(item.food_id, food.id)
        self.assertEqual(item.quantity, 100)
        with self.assertRaises(HTTPException) as caught:
            foods.lookup_food_by_barcode(B)
        self.assertEqual(caught.exception.status_code, 404)
        foods.update_food(food.id, s.FoodUpdate(barcodes=[]), self.db)
        self.assertEqual(food.barcodes, [])
        self.assertIsNone(food.barcode)

    def test_conflicting_alias_or_legacy_code_rolls_back_edit(self):
        owner = self.food()
        other = self.food(barcodes=[C])
        legacy = m.Food(name="Altes Produkt", barcode="6012345678909")
        self.db.add(legacy)
        self.db.commit()
        for code in (A, B, legacy.barcode):
            with self.subTest(code=code), self.assertRaises(HTTPException) as caught:
                foods.update_food(other.id, s.FoodUpdate(name="Geaendert", barcodes=[C, code]), self.db)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertNotEqual(other.name, "Geaendert")
            self.assertEqual(other.barcodes, [C])
        self.assertEqual(owner.barcodes, [A, B])

    def test_invalid_code_rolls_back_the_whole_creation(self):
        for code in ("bad-code", "123", "1" * 129):
            with self.subTest(code=code), self.assertRaises(HTTPException) as caught:
                self.food(barcodes=[A, code])
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(self.db.query(m.Food).count(), 0)

    def test_ambiguous_legacy_codes_and_archived_products_are_not_selected(self):
        food = self.food()
        duplicate = m.Food(name="Alt-Duplikat", barcode=B)
        self.db.add(duplicate)
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            foods.lookup_food_by_barcode(B)
        self.assertEqual(caught.exception.status_code, 409)
        self.db.delete(duplicate)
        food.is_archived = True
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            foods.lookup_food_by_barcode(A)
        self.assertEqual(caught.exception.status_code, 409)

    def test_inventory_adds_alias_and_keeps_primary_and_stock_identity(self):
        food = self.food()
        item = inventory.create_inventory_item(s.InventoryItemCreate(
            name=food.name, food_id=food.id, barcode=" 5012-3456 78900 ", quantity=100, unit="g",
        ), self.db)
        self.assertEqual(food.barcode, A)
        self.assertEqual(food.barcodes, [A, B, C])
        self.assertEqual(item.barcode, C)
        self.assertEqual(foods.lookup_food_by_barcode(C).inventory_items[0].id, item.id)
        other = self.food(barcodes=[])
        with self.assertRaises(HTTPException) as caught:
            inventory.create_inventory_item(s.InventoryItemCreate(
                name=other.name, food_id=other.id, barcode=C, quantity=3,
            ), self.db)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

    def test_legacy_unlinked_stock_is_attached_by_alias(self):
        orphan = m.InventoryItem(name="Alter Bestand", barcode=B, quantity=50, unit="g")
        self.db.add(orphan)
        self.db.commit()
        food = self.food()
        self.assertEqual(orphan.food_id, food.id)
        self.assertEqual(foods.lookup_food_by_barcode(A).inventory_items[0].id, orphan.id)

    def test_external_lookup_adds_alias_without_losing_primary_or_other_lots(self):
        food = self.food(brand="Marke")
        item = self.stock(food, A)
        with patch.object(foods, "open_food_facts_product", return_value={
            "product_name": food.name, "brands": "Marke", "nutriments": {"energy-kcal_100g": 200},
        }):
            result = foods.lookup_food_by_barcode(C)
        self.assertEqual(result.food.id, food.id)
        self.assertEqual(food.barcodes, [A, B, C])
        self.assertEqual(food.barcode, A)
        self.assertEqual([lot.id for lot in result.inventory_items], [item.id])

    def test_ean_creates_complete_master_data_without_stock_or_meal(self):
        product = {
            "product_name_de": "Haferdrink", "brands": "Testmarke", "categories": "Getraenke, Pflanzlich",
            "serving_size": "250 ml", "nutriments": {
                "energy-kcal_100g": 46, "proteins_100g": 1.1,
                "fat_100g": 1.5, "carbohydrates_100g": 6.8,
                "fiber_100g": 0.75, "sugars_100g": 4.2, "caffeine_100g": 0.032,
                "caffeine_unit": "mg", "caffeine_value": 32,
            },
        }
        with patch.object(foods, "open_food_facts_product", return_value=product) as lookup:
            result = foods.lookup_food_by_barcode(A)
            created = result.food
            self.assertEqual((created.name, created.brand, created.category), ("Haferdrink", "Testmarke", "Getraenke"))
            self.assertEqual((created.serving_size, created.serving_unit), (250, "ml"))
            self.assertEqual((created.calories_per_100g, created.protein_per_100g, created.fat_per_100g, created.carbs_per_100g), (46, 1.1, 1.5, 6.8))
            self.assertEqual(created.barcodes, [A])
            self.assertEqual((created.fiber_per_100g, created.sugar_per_100g, created.caffeine_mg_per_100g), (0.75, 4.2, 32))
            self.assertIsNotNone(self.db.get(m.ProductUnit, created.product_unit_id))
            repeated = foods.lookup_food_by_barcode(A)
            self.assertEqual(repeated.food.id, created.id)
            lookup.assert_called_once_with(A)
        self.assertEqual(self.db.query(m.Food).count(), 1)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 0)
        self.assertEqual(self.db.query(m.MealLog).count(), 0)
        foods.update_food(created.id, s.FoodUpdate(expiry_days=7, storage_location="Vorrat"), self.db)
        self.assertEqual(self.db.get(m.Food, created.id).barcodes, [A])

    def test_ean_preview_preserves_optional_values_and_refresh_keeps_missing_values(self):
        product = {"product_name": "Test", "nutriments": {"fiber_100g": 1.25, "sugars_100g": 0}}
        with patch.object(foods, "open_food_facts_product", return_value=product):
            preview = s.FoodBarcodePreviewRead(**foods.preview_food_by_barcode(C))
        self.assertEqual((preview.fiber_per_100g, preview.sugar_per_100g, preview.caffeine_mg_per_100g), (1.25, 0, None))
        food = self.food(fiber_per_100g=2.5, sugar_per_100g=6.25, caffeine_mg_per_100g=32)
        foods.upsert_food_from_open_food_facts(self.db, A, {"product_name": food.name})
        self.db.commit()
        self.assertEqual((food.fiber_per_100g, food.sugar_per_100g, food.caffeine_mg_per_100g), (2.5, 6.25, 32))
        foods.upsert_food_from_open_food_facts(self.db, A, {"product_name": food.name, "nutriments": {
            "fiber_100g": 0, "sugars_100g": 0, "caffeine_100g": 0,
        }})
        self.db.commit()
        self.assertEqual((food.fiber_per_100g, food.sugar_per_100g, food.caffeine_mg_per_100g), (0, 0, 0))

    def test_ean_skips_invalid_or_unscaled_additional_nutrients(self):
        values = foods.additional_nutrients_from_open_food_facts({"nutriments": {
            "fiber_100g": "NaN", "sugars_100g": "Infinity", "caffeine_value": 32, "caffeine_unit": "mg",
        }})
        self.assertEqual(values, {})

    def test_missing_ean_and_network_failure_create_no_product(self):
        with self.assertRaises(HTTPException) as caught:
            foods.lookup_food_by_barcode(A)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertIn("manuell", caught.exception.detail)
        with patch.object(foods, "open_food_facts_product", side_effect=HTTPException(502, "offline")):
            with self.assertRaises(HTTPException) as caught:
                foods.lookup_food_by_barcode(A)
            self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(self.db.query(m.Food).count(), 0)
        self.assertEqual(self.db.query(m.FoodBarcode).count(), 0)

    def test_external_lookup_rechecks_local_data_without_holding_database_lock(self):
        for barcode, lookup in ((A, foods.lookup_food_by_barcode), (B, foods.preview_food_by_barcode)):
            with self.subTest(barcode=barcode):
                def upstream(code):
                    self.assertFalse(database.DATABASE_LOCK.locked())
                    self.assertEqual(code, barcode)
                    with contextmanager(get_db)() as db:
                        foods.create_food(s.FoodCreate(
                            name=f"Lokales Produkt {code}", barcode=code, calories_per_100g=100,
                        ), db)
                    return {"product_name": "Externe Antwort", "nutriments": {"energy-kcal_100g": 60}}

                with (
                    patch.object(database, "SessionLocal", sessionmaker(bind=self.engine, autoflush=False)),
                    patch.object(foods, "barcode_db_session", contextmanager(get_db)),
                    patch.object(foods, "open_food_facts_product", side_effect=upstream),
                ):
                    result = lookup(barcode)
                local_food = self.db.query(m.Food).filter_by(barcode=barcode).one()
                self.assertEqual(local_food.name, f"Lokales Produkt {barcode}")
                if isinstance(result, s.FoodBarcodeLookupRead):
                    self.assertEqual((result.source, result.food.id), ("local_food", local_food.id))
                else:
                    self.assertEqual((result["source"], result["name"]), ("local_food", local_food.name))

    def test_tracker_and_cooking_consume_shared_stock_across_codes(self):
        food = self.food()
        first, second = self.stock(food, A), self.stock(food, B)
        scanned = foods.lookup_food_by_barcode(B).food
        meal = meals.create_meal_log(s.MealLogCreate(
            food_id=scanned.id, quantity=150, unit="g", deduct_inventory=True, booking_key="multi-ean-meal-01",
        ), self.db)
        self.assertEqual(first.quantity + second.quantity, 50)
        meals.delete_meal_log(meal.id, self.db)
        self.assertEqual((first.quantity, second.quantity), (100, 100))
        recipe = m.Recipe(name="Testgericht", servings=1, ingredients=[
            m.RecipeIngredient(food_id=scanned.id, quantity=150, unit="g"),
        ])
        self.db.add(recipe)
        self.db.commit()
        recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        self.assertEqual(first.quantity + second.quantity, 50)
        self.assertEqual(recipe.ingredients[0].food_id, food.id)
        self.assertEqual(food.barcodes, [A, B])

    def test_shopping_merges_alias_selections_and_replenishes_same_food(self):
        food = self.food()
        for code in (A, B):
            scanned = foods.lookup_food_by_barcode(code).food
            shopping.create_shopping_item(s.ShoppingListItemCreate(
                name=scanned.name, food_id=scanned.id, quantity=100, unit="g",
            ), self.db)
        self.assertEqual(self.db.query(m.ShoppingListItem).count(), 1)
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        item = result["created_inventory_items"][0]
        self.assertEqual((item.food_id, item.quantity), (food.id, 200))
        self.assertEqual(foods.lookup_food_by_barcode(B).inventory_items[0].id, item.id)


class OpenFoodFactsTransportTest(unittest.TestCase):
    def test_incomplete_v2_product_falls_back_to_compatible_v3(self):
        missing, existing = MagicMock(), MagicMock()
        missing.__enter__.return_value.status = 200
        missing.__enter__.return_value.read.return_value = b'{"product":{"product_name":"Test"}}'
        existing_response = existing.__enter__.return_value
        existing_response.status = 200
        existing_response.read.return_value = b'{"product": {"product_name": "Test"}}'
        with patch.object(foods, "HTTPSConnection") as https:
            connection = https.return_value
            connection.getresponse.side_effect = [missing, existing]
            self.assertEqual(foods.open_food_facts_product(A), {"product_name": "Test"})
        request_paths = [request.args[1] for request in connection.request.call_args_list]
        self.assertEqual(request_paths, [
            f"/api/{version}/product/{A}.json?fields={foods.OPEN_FOOD_FACTS_PRODUCT_FIELDS}"
            for version in ("v2", "v3.4")
        ])

    def test_normalized_nutrition_uses_one_small_product_request(self):
        product = {
            "product_name": "Gnocchi", "brands": "REWE Beste Wahl", "serving_size": "200g",
            "nutriments": {
                "energy-kcal_100g": 144.5, "proteins_100g": 4.5,
                "fat_100g": 0.5, "carbohydrates_100g": 30.5,
            },
        }
        with patch.object(foods, "HTTPSConnection") as https:
            response = https.return_value.getresponse.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = json.dumps({"product": product}).encode()
            self.assertEqual(foods.open_food_facts_product("4388844003972"), product)
        https.assert_called_once_with("world.openfoodfacts.org", timeout=foods.OPEN_FOOD_FACTS_TIMEOUT_SECONDS)
        self.assertIn("?fields=product_name", https.return_value.request.call_args.args[1])
        headers = https.return_value.request.call_args.kwargs["headers"]
        self.assertIn("NokoTracker", headers["User-Agent"])
        self.assertEqual(foods.food_values_from_open_food_facts("4388844003972", product)["calories_per_100g"], 144.5)

    def test_failed_primary_api_uses_compatibility_response(self):
        for status in (500, 503):
            with self.subTest(status=status), patch.object(foods, "HTTPSConnection") as https:
                failed, success = MagicMock(), MagicMock()
                failed.__enter__.return_value.status = status
                success.__enter__.return_value.status = 200
                success.__enter__.return_value.read.return_value = b'{"product":{"product_name":"Test"}}'
                https.return_value.getresponse.side_effect = [failed, success]
                with self.assertLogs(foods.logger, level="WARNING") as logs:
                    self.assertEqual(foods.open_food_facts_product(A), {"product_name": "Test"})
                self.assertIn(f"HTTP {status}", " ".join(logs.output))
                self.assertNotIn(A, " ".join(logs.output))

    def test_timeout_fallback_preserves_available_product_data(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b'{"product":{"product_name":"Test"}}'
        for responses in ([TimeoutError(), response], [response, TimeoutError()]):
            with patch.object(foods, "HTTPSConnection") as https:
                https.return_value.getresponse.side_effect = responses
                with self.assertLogs(foods.logger, level="WARNING") as logs:
                    self.assertEqual(foods.open_food_facts_product(A), {"product_name": "Test"})
                self.assertIn("TimeoutError", " ".join(logs.output))
                self.assertNotIn(A, " ".join(logs.output))

    def test_certificate_failure_is_not_retried(self):
        with patch.object(foods, "HTTPSConnection") as https:
            https.return_value.request.side_effect = ssl.SSLCertVerificationError("certificate verification failed")
            with self.assertLogs(foods.logger, level="WARNING") as logs, self.assertRaises(HTTPException) as caught:
                foods.open_food_facts_product(A)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("SSLCertVerificationError", " ".join(logs.output))
        https.assert_called_once()

    def test_missing_product_is_reported_without_retrying_the_other_api(self):
        with patch.object(foods, "HTTPSConnection") as https:
            response = https.return_value.getresponse.return_value.__enter__.return_value
            response.status = 404
            self.assertIsNone(foods.open_food_facts_product(A))
        https.assert_called_once()

    def test_redirect_does_not_start_another_connection(self):
        with patch.object(foods, "HTTPSConnection") as https:
            response = https.return_value.getresponse.return_value.__enter__.return_value
            response.status = 302
            with self.assertLogs(foods.logger, level="WARNING"), self.assertRaises(HTTPException) as caught:
                foods.open_food_facts_product(A)
        self.assertEqual(caught.exception.status_code, 502)
        https.assert_called_once_with("world.openfoodfacts.org", timeout=foods.OPEN_FOOD_FACTS_TIMEOUT_SECONDS)
        method, path = https.return_value.request.call_args.args
        self.assertEqual((method, path), ("GET", f"/api/v2/product/{A}.json?fields={foods.OPEN_FOOD_FACTS_PRODUCT_FIELDS}"))
        response.read.assert_not_called()

    def test_response_size_and_invalid_json_are_reported_as_upstream_errors(self):
        for body in (b" " * 65, b"\xff", b"[]"):
            with (
                self.subTest(body=body),
                patch.object(foods, "OPEN_FOOD_FACTS_MAX_RESPONSE_BYTES", 64),
                patch.object(foods, "HTTPSConnection") as https,
            ):
                response = https.return_value.getresponse.return_value.__enter__.return_value
                response.status = 200
                response.read.return_value = body
                with self.assertLogs(foods.logger, level="WARNING"), self.assertRaises(HTTPException) as caught:
                    foods.open_food_facts_product(A)
                self.assertEqual(caught.exception.status_code, 502)
                self.assertEqual(response.read.call_count, 2)
                response.read.assert_called_with(65)


if __name__ == "__main__":
    unittest.main()
