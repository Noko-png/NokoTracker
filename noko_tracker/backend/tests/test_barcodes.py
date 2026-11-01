import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as m, schemas as s
from app.database import Base
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
        self.assertEqual(foods.lookup_food_by_barcode(A, self.db)["food"].id, food.id)
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
            result = foods.lookup_food_by_barcode(code, self.db)
            self.assertEqual(result["food"].id, food.id)
            self.assertEqual({item.id for item in result["inventory_items"]}, {item.id for item in lots})
            preview = foods.preview_food_by_barcode(code, self.db)
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
            foods.lookup_food_by_barcode(B, self.db)
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
            foods.lookup_food_by_barcode(B, self.db)
        self.assertEqual(caught.exception.status_code, 409)
        self.db.delete(duplicate)
        food.is_archived = True
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            foods.lookup_food_by_barcode(A, self.db)
        self.assertEqual(caught.exception.status_code, 409)

    def test_inventory_adds_alias_and_keeps_primary_and_stock_identity(self):
        food = self.food()
        item = inventory.create_inventory_item(s.InventoryItemCreate(
            name=food.name, food_id=food.id, barcode=" 5012-3456 78900 ", quantity=100, unit="g",
        ), self.db)
        self.assertEqual(food.barcode, A)
        self.assertEqual(food.barcodes, [A, B, C])
        self.assertEqual(item.barcode, C)
        self.assertEqual(foods.lookup_food_by_barcode(C, self.db)["inventory_items"][0].id, item.id)
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
        self.assertEqual(foods.lookup_food_by_barcode(A, self.db)["inventory_items"][0].id, orphan.id)

    def test_external_lookup_adds_alias_without_losing_primary_or_other_lots(self):
        food = self.food(brand="Marke")
        item = self.stock(food, A)
        with patch.object(foods, "open_food_facts_product", return_value={
            "product_name": food.name, "brands": "Marke", "nutriments": {"energy-kcal_100g": 200},
        }):
            result = foods.lookup_food_by_barcode(C, self.db)
        self.assertEqual(result["food"].id, food.id)
        self.assertEqual(food.barcodes, [A, B, C])
        self.assertEqual(food.barcode, A)
        self.assertEqual([lot.id for lot in result["inventory_items"]], [item.id])

    def test_tracker_and_cooking_consume_shared_stock_across_codes(self):
        food = self.food()
        first, second = self.stock(food, A), self.stock(food, B)
        scanned = foods.lookup_food_by_barcode(B, self.db)["food"]
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
            scanned = foods.lookup_food_by_barcode(code, self.db)["food"]
            shopping.create_shopping_item(s.ShoppingListItemCreate(
                name=scanned.name, food_id=scanned.id, quantity=100, unit="g",
            ), self.db)
        self.assertEqual(self.db.query(m.ShoppingListItem).count(), 1)
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        item = result["created_inventory_items"][0]
        self.assertEqual((item.food_id, item.quantity), (food.id, 200))
        self.assertEqual(foods.lookup_food_by_barcode(B, self.db)["inventory_items"][0].id, item.id)


if __name__ == "__main__":
    unittest.main()
