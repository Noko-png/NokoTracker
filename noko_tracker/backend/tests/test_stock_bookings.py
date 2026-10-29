import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app import models as m, schemas as s
from app.database import Base
from app.routers import inventory, meals, recipes, shopping
from app.services import nutrition_service as nutrition, receipt_import_service as receipt


class StockBookingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def stock(self, quantity=500, unit="g", serving=100, product_unit=None):
        food = m.Food(name=f"Food {self.db.query(m.Food).count()}", serving_size=serving,
                      serving_unit="g", product_unit=product_unit)
        item = m.InventoryItem(name=food.name, food=food, quantity=quantity, unit=unit,
                               serving_size=serving, serving_unit="g")
        self.db.add_all([food, item])
        self.db.commit()
        return food, item

    def meal(self, food, quantity=100, **kwargs):
        return meals.create_meal_log(s.MealLogCreate(food_id=food.id, quantity=quantity, unit="g", **kwargs), self.db)

    def book(self, food, quantity=100, **kwargs):
        entry = self.meal(food, quantity, **kwargs)
        meals.deduct_meal_log_from_inventory(entry.id, self.db)
        return entry

    def assert_http(self, code, function, *args, **kwargs):
        with self.assertRaises(HTTPException) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.status_code, code)

    def recipe(self, food, *ingredients):
        recipe = m.Recipe(name="Mixed units", servings=1, ingredients=[
            m.RecipeIngredient(food=food, quantity=quantity, unit=unit) for quantity, unit in ingredients
        ])
        self.db.add(recipe)
        self.db.commit()
        return recipe

    def test_small_and_decimal_consumption_preserves_exact_quantities(self):
        for quantity in (5, 80, 1, 0.001):
            with self.subTest(quantity=quantity):
                food, item = self.stock(1, "kg")
                entry = self.book(food, quantity)
                self.assertAlmostEqual(item.quantity, 1 - quantity / 1000, places=12)
                self.assertIsNotNone(entry.inventory_deducted_at)
                meals.delete_meal_log(entry.id, self.db)
                self.assertAlmostEqual(item.quantity, 1, places=12)

    def test_decimal_and_fraction_inputs_do_not_snap_to_nearby_fractions(self):
        for value, expected in [("0,005", .005), ("0.08", .08), ("0.33", .33), ("1/3", 1/3), ("1 1/2", 1.5)]:
            self.assertAlmostEqual(s.parse_fractional_number(value), expected, places=12)

    def test_mixed_units_cannot_use_the_same_stock_twice(self):
        food, item = self.stock(150)
        recipe = self.recipe(food, (100, "g"), (.1, "kg"))
        self.assert_http(422, recipes.prepare_recipe_from_inventory, recipe.id, db=self.db)
        entry = meals.create_meal_log(s.MealLogCreate(recipe_id=recipe.id), self.db)
        self.assert_http(422, meals.deduct_meal_log_from_inventory, entry.id, self.db)
        self.assertEqual(item.quantity, 150)
        self.assertIsNone(entry.inventory_deducted_at)
        self.assertIsNone(recipe.prepared_food_id)

    def test_mixed_units_book_total_when_enough_stock_is_available(self):
        food, item = self.stock(250)
        recipe = self.recipe(food, (100, "g"), (.1, "kg"))
        result = recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        self.assertEqual(item.quantity, 50)
        self.assertEqual(result["prepared_quantity"], 1)
        self.assertEqual(len(result["consumed"]), 1)

    def test_recipe_preparations_keep_separate_lots(self):
        food, item = self.stock(500)
        recipe = self.recipe(food, (100, "g"))
        first = recipes.prepare_recipe_from_inventory(recipe.id, s.RecipePrepareRequest(purchase_date=date(2026, 10, 20)), self.db)
        second = recipes.prepare_recipe_from_inventory(recipe.id, s.RecipePrepareRequest(purchase_date=date(2026, 10, 21)), self.db)
        self.assertNotEqual(first["inventory_item"].id, second["inventory_item"].id)
        self.assertEqual(first["inventory_item"].purchase_date, date(2026, 10, 20))
        self.assertEqual(item.quantity, 300)

    def test_atomic_create_shortage_leaves_no_meal_or_partial_deduction(self):
        food, item = self.stock(60)
        request = s.MealLogCreate(food_id=food.id, quantity=100, unit="g", deduct_inventory=True, booking_key="atomic-shortage-1")
        self.assert_http(422, meals.create_meal_log, request, self.db)
        self.assertEqual(item.quantity, 60)
        self.assertEqual(self.db.query(m.MealLog).count(), 0)
        self.assertEqual(self.db.query(m.MealInventoryBooking).count(), 0)

    def test_atomic_create_books_multiple_lots_and_retry_is_idempotent(self):
        food, first = self.stock(60)
        second = m.InventoryItem(food=food, name=food.name, quantity=60, unit="g")
        self.db.add(second)
        self.db.commit()
        request = s.MealLogCreate(food_id=food.id, quantity=100, unit="g", deduct_inventory=True, booking_key="atomic-success-01")
        entry = meals.create_meal_log(request, self.db)
        self.assertEqual((first.quantity, second.quantity), (0, 20))
        self.assertEqual(len(entry.inventory_booking.deductions), 2)
        self.db.expire_all()
        repeated = meals.create_meal_log(request, self.db)
        self.assertEqual(repeated.id, entry.id)
        self.assertEqual((first.quantity, second.quantity), (0, 20))
        self.assertEqual(self.db.query(m.MealLog).count(), 1)
        changed = request.model_copy(update={"quantity": 20})
        self.assert_http(409, meals.create_meal_log, changed, self.db)

    def test_failure_after_deduction_rolls_back_the_whole_transaction(self):
        food, item = self.stock()
        request = s.MealLogCreate(food_id=food.id, quantity=100, unit="g", deduct_inventory=True, booking_key="failed-request-01")
        with patch.object(self.db, "commit", side_effect=RuntimeError("simulated storage failure")):
            with self.assertRaises(RuntimeError):
                meals.create_meal_log(request, self.db)
        self.assertEqual(item.quantity, 500)
        self.assertEqual(self.db.query(m.MealLog).count(), 0)
        self.assertEqual(self.db.query(m.MealInventoryBooking).count(), 0)

    def test_mealprep_edit_cannot_reset_booking_status(self):
        food, item = self.stock()
        entry = self.book(food, meal_source="mealprep")
        meals.update_meal_log(entry.id, s.MealLogUpdate(food_id=food.id, quantity=100, unit="g", inventory_deducted_at=None), self.db)
        self.assert_http(409, meals.deduct_meal_log_from_inventory, entry.id, self.db)
        self.assertEqual(item.quantity, 400)

    def test_quantity_edit_and_delete_reverse_the_recorded_amounts(self):
        food, item = self.stock()
        entry = self.book(food)
        meals.update_meal_log(entry.id, s.MealLogUpdate(quantity=200), self.db)
        self.assertEqual(item.quantity, 300)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(item.quantity, 500)
        self.assertEqual(self.db.query(m.MealInventoryBooking).count(), 0)
        self.assert_http(404, meals.delete_meal_log, entry.id, self.db)

    def test_switch_food_refunds_original_and_books_new_food(self):
        first_food, first = self.stock()
        second_food, second = self.stock()
        entry = self.book(first_food, meal_source="mealprep")
        meals.update_meal_log(entry.id, s.MealLogUpdate(food_id=second_food.id), self.db)
        self.assertEqual((first.quantity, second.quantity), (500, 400))
        self.assertEqual(entry.food.id, second_food.id)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual((first.quantity, second.quantity), (500, 500))

    def test_failed_edit_preserves_original_booking_and_stock(self):
        first_food, first = self.stock()
        second_food, second = self.stock(20)
        entry = self.book(first_food)
        self.assert_http(422, meals.update_meal_log, entry.id, s.MealLogUpdate(food_id=second_food.id), self.db)
        self.assertEqual((first.quantity, second.quantity), (400, 20))
        self.assertEqual(entry.food_id, first_food.id)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(first.quantity, 500)

    def test_switch_to_quick_add_refunds_stock_without_booking_it_again(self):
        food, item = self.stock()
        entry = self.book(food)
        meals.update_meal_log(entry.id, s.MealLogUpdate(quick_add_name="Correction", quick_calories=100), self.db)
        self.assertEqual(item.quantity, 500)
        self.assertIsNone(entry.inventory_deducted_at)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(item.quantity, 500)

    def test_non_finite_quantities_are_rejected_before_booking(self):
        for value in ("inf", "NaN", float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                s.InventoryQuantityChange(amount=value)

    def test_deleted_lot_is_restored_with_original_unit_and_expiry(self):
        food, item = self.stock(100)
        item.expiry_days = 7
        item.purchase_date = date(2026, 10, 20)
        self.db.commit()
        entry = self.book(food)
        inventory.delete_inventory_item(item.id, self.db)
        meals.delete_meal_log(entry.id, self.db)
        restored = self.db.query(m.InventoryItem).one()
        self.assertEqual((restored.quantity, restored.unit, restored.expiry_date), (100, "g", date(2026, 10, 27)))

    def test_changed_lot_unit_does_not_mix_units_on_refund(self):
        food, item = self.stock()
        entry = self.book(food)
        item.unit = "kg"
        item.quantity = .4
        self.db.commit()
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(item.quantity, .4)
        restored = self.db.query(m.InventoryItem).filter_by(unit="g").one()
        self.assertEqual(restored.quantity, 100)

    def test_legacy_booking_without_evidence_does_not_invent_stock(self):
        food, item = self.stock(400)
        entry = self.meal(food)
        entry.inventory_deducted_at = datetime.utcnow()
        self.db.commit()
        self.assert_http(409, meals.update_meal_log, entry.id, s.MealLogUpdate(quantity=200), self.db)
        self.assert_http(409, meals.delete_meal_log, entry.id, self.db)
        meals.update_meal_log(entry.id, s.MealLogUpdate(notes="Keep history"), self.db)
        self.assertEqual(item.quantity, 400)

    def test_stale_inventory_form_cannot_overwrite_a_booking(self):
        food, item = self.stock(10, "pcs")
        stale = s.InventoryItemReplace.model_validate({
            **s.InventoryItemCreate.model_validate(item, from_attributes=True).model_dump(), "expected_updated_at": item.updated_at,
        })
        inventory.increase_inventory_item(item.id, s.InventoryQuantityChange(amount=3), self.db)
        self.assert_http(409, inventory.replace_inventory_item, item.id, stale, self.db)
        self.assertEqual(item.quantity, 13)
        current = stale.model_copy(update={"quantity": 13, "expected_updated_at": item.updated_at, "notes": "Fresh edit"})
        inventory.replace_inventory_item(item.id, current, self.db)
        self.assertEqual((item.quantity, item.notes), (13, "Fresh edit"))

    def test_recipe_shopping_import_preserves_pack_quantity_and_existing_lot(self):
        food, item = self.stock(100, "g", 500, m.ProductUnit(name="Packung"))
        recipe = self.recipe(food, (600, "g"))
        recipes.sync_missing_recipe_ingredients_to_shopping_list(recipe.id, self.db)
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual(item.quantity, 100)
        added = result["created_inventory_items"][0]
        self.assertEqual((added.quantity, added.unit), (1, "Packung"))
        total = sum(nutrition.food_amount_in_grams(row, row.quantity, row.unit) for row in self.db.query(m.InventoryItem))
        self.assertEqual(total, 600)
        shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 2)

    def test_shopping_import_does_not_renew_expired_stock(self):
        food, item = self.stock(1, "pcs")
        food.expiry_days = 5
        item.purchase_date = date.today() - timedelta(days=10)
        item.expiry_days = 5
        self.db.add(m.ShoppingListItem(name=food.name, food=food, inventory_item=item, quantity=1, unit="pcs"))
        self.db.commit()
        old_expiry = item.expiry_date
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual(item.expiry_date, old_expiry)
        self.assertEqual(item.quantity, 1)
        self.assertEqual(result["created_inventory_items"][0].expiry_date, date.today() + timedelta(days=5))

    def test_receipt_retries_and_changed_rows_cannot_book_same_receipt_twice(self):
        request = s.ReceiptImportBookRequest(receipt_id="a" * 64, items=[
            s.ReceiptImportBookItem(source_index=0, raw_name="Milk", name="Milk", quantity=2, unit="pcs")
        ])
        receipt.book_receipt_import(self.db, request)
        self.db.expire_all()
        self.assert_http(409, receipt.book_receipt_import, self.db, request)
        request.items[0].quantity = 3
        self.assert_http(409, receipt.book_receipt_import, self.db, request)
        self.assertEqual(self.db.query(m.InventoryItem).one().quantity, 2)
        receipt.book_receipt_import(self.db, request.model_copy(update={"receipt_id": "b" * 64}))
        self.assertEqual(self.db.query(m.InventoryItem).count(), 2)

    def test_older_receipt_client_identical_request_is_also_protected(self):
        request = s.ReceiptImportBookRequest(items=[
            s.ReceiptImportBookItem(source_index=0, raw_name="Milk", name="Milk", quantity=2)
        ])
        receipt.book_receipt_import(self.db, request)
        self.assert_http(409, receipt.book_receipt_import, self.db, request)

    def test_failed_receipt_can_be_retried_without_leftover_stock_or_marker(self):
        request = s.ReceiptImportBookRequest(items=[
            s.ReceiptImportBookItem(source_index=0, raw_name="Milk", name="Milk", quantity=2)
        ])
        with patch.object(self.db, "commit", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                receipt.book_receipt_import(self.db, request)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 0)
        self.assertEqual(self.db.query(m.ReceiptBooking).count(), 0)
        receipt.book_receipt_import(self.db, request)
        self.assertEqual(self.db.query(m.InventoryItem).one().quantity, 2)


if __name__ == "__main__":
    unittest.main()
