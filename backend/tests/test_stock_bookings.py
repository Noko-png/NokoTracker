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

    def test_recipe_preparations_merge_compatible_portions(self):
        food, item = self.stock(500)
        recipe = self.recipe(food, (100, "g"))
        first = recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        prepared_id = first["inventory_item"].id
        second = recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        self.assertEqual(second["inventory_item"].id, prepared_id)
        self.assertEqual((second["inventory_item"].quantity, second["inventory_item"].unit), (2, "Portion"))
        self.assertEqual(second["prepared_quantity"], 1)
        self.assertEqual(item.quantity, 300)
        self.assertEqual(self.db.query(m.InventoryItem).filter_by(food_id=recipe.prepared_food_id).count(), 1)

    def test_recipes_and_tracker_consume_existing_lots_in_different_units(self):
        food, first = self.stock(100, "g", 1000, m.ProductUnit(name="kg"))
        first.expiry_days = 1
        second = m.InventoryItem(food=food, name=food.name, quantity=1, unit="kg", serving_size=1000,
                                 serving_unit="g", purchase_date=date.today(), expiry_days=7)
        self.db.add(second)
        self.db.commit()
        recipe = self.recipe(food, (100, "g"), (.1, "kg"))
        recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        self.assertEqual(first.quantity, 0)
        self.assertAlmostEqual(second.quantity, .9)
        entry = self.book(food, 150)
        self.assertAlmostEqual(second.quantity, .75)
        meals.delete_meal_log(entry.id, self.db)
        self.assertAlmostEqual(second.quantity, .9)

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

    def test_changed_lot_unit_converts_refund_into_existing_stock(self):
        food, item = self.stock()
        entry = self.book(food)
        item.unit = "kg"
        item.quantity = .4
        self.db.commit()
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual((item.quantity, item.unit), (500, "g"))
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

    def test_deleted_lot_refund_reuses_compatible_existing_stock_in_another_unit(self):
        food, first = self.stock(100, "g")
        entry = self.book(food)
        second = m.InventoryItem(food=food, name=food.name, quantity=1, unit="kg", serving_size=100,
                                 serving_unit="g", purchase_date=first.purchase_date)
        self.db.add(second)
        self.db.commit()
        inventory.delete_inventory_item(first.id, self.db)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual((second.quantity, second.unit), (1100, "g"))
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

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
        self.assertEqual((item.quantity, item.unit, item.notes), (1300, "g", "Fresh edit"))

    def test_recipe_shopping_import_merges_in_primary_pack_unit(self):
        food, item = self.stock(100, "g", 500, m.ProductUnit(name="Packung"))
        recipe = self.recipe(food, (600, "g"))
        recipes.sync_missing_recipe_ingredients_to_shopping_list(recipe.id, self.db)
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual((item.quantity, item.unit), (1.2, "Packung"))
        self.assertEqual(result["created_inventory_items"], [])
        self.assertEqual(result["updated_inventory_items"][0].id, item.id)
        total = sum(nutrition.food_amount_in_grams(row, row.quantity, row.unit) for row in self.db.query(m.InventoryItem))
        self.assertEqual(total, 600)
        shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

    def test_shopping_recipe_and_tracker_share_the_same_stock(self):
        food, item = self.stock(1000, "g", 1000, m.ProductUnit(name="kg"))
        self.db.add(m.ShoppingListItem(name=food.name, food=food, inventory_item=item, quantity=1, unit="kg"))
        self.db.commit()
        shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual((item.quantity, item.unit), (2, "kg"))
        recipe = self.recipe(food, (.5, "kg"))
        recipes.prepare_recipe_from_inventory(recipe.id, db=self.db)
        self.assertEqual(item.quantity, 1.5)
        entry = self.book(food, 250)
        self.assertEqual(item.quantity, 1.25)
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(item.quantity, 1.5)
        self.assertEqual(self.db.query(m.InventoryItem).filter_by(food_id=food.id).count(), 1)

    def test_shopping_merges_multiple_source_lines_and_counts_each_purchase(self):
        food, item = self.stock(1000, "g", 1000, m.ProductUnit(name="kg"))
        food.storage_location = "Vorrat"
        item.storage_location = "Kueche"
        self.db.add_all([
            m.ShoppingListItem(name=food.name, food=food, inventory_item=item, quantity=1, unit="kg"),
            m.ShoppingListItem(name=food.name, food=food, inventory_item=item, quantity=.5, unit="kg"),
        ])
        self.db.commit()
        result = shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual((item.quantity, item.unit, item.storage_location), (2.5, "kg", "Kueche"))
        self.assertEqual(result["imported_count"], 2)
        self.assertEqual(len(result["deleted_shopping_item_ids"]), 2)
        self.assertEqual([row.id for row in result["updated_inventory_items"]], [item.id])
        self.assertEqual(result["created_inventory_items"], [])
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

    def test_receipt_merges_compatible_units_and_retries_do_not_add_quantity(self):
        food, item = self.stock(1000, "g", 1000, m.ProductUnit(name="kg"))
        request = s.ReceiptImportBookRequest(receipt_id="d" * 64, items=[
            s.ReceiptImportBookItem(source_index=0, raw_name="Artikelzeile 1", name=food.name, food_id=food.id, quantity=1000, unit="g"),
            s.ReceiptImportBookItem(source_index=1, raw_name="Artikelzeile 2", name=food.name, food_id=food.id, quantity=1, unit="kg"),
        ])
        result = receipt.book_receipt_import(self.db, request)
        self.assertEqual(result.booked_count, 2)
        self.assertEqual([row.id for row in result.inventory_items], [item.id])
        self.assertEqual((item.quantity, item.unit), (3, "kg"))
        self.assert_http(409, receipt.book_receipt_import, self.db, request)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)

    def test_import_batches_report_one_new_row_when_source_lines_merge(self):
        product_unit = m.ProductUnit(name="kg")
        for source in ("shopping", "receipt"):
            with self.subTest(source=source):
                food = m.Food(name=source, product_unit=product_unit, serving_size=1000, serving_unit="g")
                self.db.add(food)
                self.db.commit()
                if source == "shopping":
                    self.db.add_all([
                        m.ShoppingListItem(name=food.name, food=food, quantity=1, unit="kg"),
                        m.ShoppingListItem(name=food.name, food=food, quantity=500, unit="g"),
                    ])
                    self.db.commit()
                    result = shopping.import_shopping_list_to_inventory(db=self.db)
                    self.assertEqual(result["imported_count"], 2)
                    self.assertEqual(result["updated_inventory_items"], [])
                    rows = result["created_inventory_items"]
                else:
                    result = receipt.book_receipt_import(self.db, s.ReceiptImportBookRequest(items=[
                        s.ReceiptImportBookItem(source_index=0, raw_name=food.name, name=food.name, food_id=food.id, quantity=1, unit="kg"),
                        s.ReceiptImportBookItem(source_index=1, raw_name=food.name, name=food.name, food_id=food.id, quantity=500, unit="g"),
                    ]))
                    self.assertEqual(result.booked_count, 2)
                    rows = result.inventory_items
                self.assertEqual(len(rows), 1)
                self.assertEqual((rows[0].quantity, rows[0].unit), (1.5, "kg"))

    def test_different_inventory_pack_unit_uses_saved_size_for_availability_and_booking(self):
        food, item = self.stock(1, "Beutel", 1, m.ProductUnit(name="g"))
        item.serving_size = 500
        self.db.commit()
        self.assertEqual(nutrition.food_amount_in_grams(item, 1, "beutel"), 500)
        self.assertEqual(nutrition.food_quantity_from_grams(item, 250, "Beutel"), .5)
        self.assertEqual(nutrition.food_amount_in_grams(item, 1, "serving"), 1)
        recipe = self.recipe(food, (250, "g"))
        self.assertEqual(recipes.sync_missing_recipe_ingredients_to_shopping_list(recipe.id, self.db)["missing"], [])

        entry = self.book(food, 250)
        self.assertEqual(item.quantity, .5)
        self.assertEqual((food.serving_size, food.serving_unit), (1, "g"))
        meals.delete_meal_log(entry.id, self.db)
        self.assertEqual(item.quantity, 1)

    def test_explicit_food_conversion_takes_priority_over_inventory_pack_size(self):
        food, item = self.stock(1, "Beutel", 1, m.ProductUnit(name="g"))
        item.serving_size = 500
        food.conversions = [m.FoodConversion(quantity=.004, unit="Beutel")]
        self.db.commit()
        self.assertEqual(nutrition.food_amount_in_grams(item, 1, "Beutel"), 250)
        self.assertEqual(nutrition.food_quantity_from_grams(item, 125, "Beutel"), .5)
        self.book(food, 125)
        self.assertEqual(item.quantity, .5)

    def test_same_inventory_product_unit_keeps_linked_food_size(self):
        food, item = self.stock(1, "Beutel", 100, m.ProductUnit(name="Beutel"))
        item.serving_size = 500
        self.db.commit()
        self.assertEqual(nutrition.food_amount_in_grams(item, 1, "Beutel"), 100)
        self.assertEqual(nutrition.food_quantity_from_grams(item, 50, "Beutel"), .5)
        self.book(food, 50)
        self.assertEqual(item.quantity, .5)

    def test_physical_inventory_units_keep_standard_mass_conversion(self):
        _, item = self.stock(1, "kg", 100, m.ProductUnit(name="Beutel"))
        item.serving_size = 500
        self.db.commit()
        self.assertEqual(nutrition.food_amount_in_grams(item, 1, "kg"), 1000)
        self.assertEqual(nutrition.food_quantity_from_grams(item, 250, "kg"), .25)

    def test_shopping_import_does_not_renew_expired_stock(self):
        food, item = self.stock(1, "pcs", product_unit=m.ProductUnit(name="pcs"))
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

    def test_shopping_rejects_unattached_unit_without_partial_stock_or_new_unit(self):
        food = m.Food(name="Reis", product_unit=m.ProductUnit(name="Beutel"), serving_size=500, serving_unit="g")
        item = m.InventoryItem(name=food.name, food=food, quantity=2, unit="Beutel", serving_size=500, serving_unit="g")
        self.db.add_all([
            food, item,
            m.ShoppingListItem(name=food.name, food=food, quantity=1, unit="Beutel"),
            m.ShoppingListItem(name=food.name, food=food, quantity=1, unit="Palette"),
        ])
        self.db.commit()
        self.assert_http(422, shopping.import_shopping_list_to_inventory, db=self.db)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(self.db.query(m.ShoppingListItem).count(), 2)
        self.assertIsNone(self.db.query(m.ProductUnit).filter_by(name="Palette").first())
        self.assertEqual((food.serving_size, food.serving_unit), (500, "g"))

    def test_receipt_rejects_unattached_unit_without_partial_stock_or_receipt_marker(self):
        food = m.Food(name="Reis", product_unit=m.ProductUnit(name="Beutel"), serving_size=500, serving_unit="g")
        item = m.InventoryItem(name=food.name, food=food, quantity=2, unit="Beutel", serving_size=500, serving_unit="g")
        self.db.add_all([food, item])
        self.db.commit()
        request = s.ReceiptImportBookRequest(receipt_id="c" * 64, items=[
            s.ReceiptImportBookItem(source_index=0, raw_name=food.name, name=food.name, food_id=food.id, quantity=1, unit="Beutel"),
            s.ReceiptImportBookItem(source_index=1, raw_name=food.name, name=food.name, food_id=food.id, quantity=1, unit="Palette"),
        ])
        self.assert_http(422, receipt.book_receipt_import, self.db, request)
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(self.db.query(m.ReceiptBooking).count(), 0)
        self.assertIsNone(self.db.query(m.ProductUnit).filter_by(name="Palette").first())
        self.assertEqual((food.serving_size, food.serving_unit), (500, "g"))

    def test_shopping_and_receipt_use_attached_conversion_and_authoritative_nutrition(self):
        food = m.Food(
            name="Reis", product_unit=m.ProductUnit(name="Beutel"), serving_size=500, serving_unit="g",
            calories_per_100g=350, protein_per_100g=7, carbs_per_100g=78, fat_per_100g=1,
            conversions=[m.FoodConversion(quantity=2, unit="Tasse")],
        )
        self.db.add(food)
        self.db.add(m.ShoppingListItem(name=food.name, food=food, quantity=1, unit="tasse"))
        self.db.commit()
        shopping.import_shopping_list_to_inventory(db=self.db)
        receipt.book_receipt_import(self.db, s.ReceiptImportBookRequest(items=[
            s.ReceiptImportBookItem(source_index=0, raw_name=food.name, name=food.name, food_id=food.id, quantity=1, unit="Tasse"),
        ]))
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)
        for item in self.db.query(m.InventoryItem).all():
            self.assertEqual(item.unit, "Beutel")
            self.assertEqual(item.quantity, 1)
            self.assertEqual(nutrition.food_amount_in_grams(item, item.quantity, item.unit), 500)
            self.assertEqual(
                (item.calories_per_100g, item.protein_per_100g, item.carbs_per_100g, item.fat_per_100g),
                (350, 7, 78, 1),
            )

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
        self.assertEqual(self.db.query(m.InventoryItem).count(), 1)
        self.assertEqual(self.db.query(m.InventoryItem).one().quantity, 5)

    def test_unknown_shopping_product_uses_unit_default_and_keeps_it_after_change(self):
        product_unit = m.ProductUnit(
            name="Beutel", default_conversion_quantity=500, default_conversion_unit="g",
        )
        self.db.add(product_unit)
        self.db.add(m.ShoppingListItem(name="Reis", quantity=2, unit="Beutel"))
        self.db.commit()
        result = shopping.import_shopping_list_to_inventory(
            s.ShoppingListInventoryImportRequest(unknown_item_action="create"), self.db,
        )
        item = self.db.get(m.InventoryItem, result["created_inventory_items"][0].id)
        food = item.food
        self.assertEqual((food.serving_size, food.serving_unit), (500, "g"))
        self.assertEqual((item.serving_size, item.serving_unit), (500, "g"))
        self.assertEqual(nutrition.food_amount_in_grams(food, 2, "Beutel"), 1000)

        product_unit.default_conversion_quantity = 750
        self.db.add(m.ShoppingListItem(name="Reis", quantity=1, unit="Beutel"))
        self.db.commit()
        shopping.import_shopping_list_to_inventory(db=self.db)
        self.assertEqual((food.serving_size, food.serving_unit), (500, "g"))

    def test_unknown_receipt_product_uses_unit_default(self):
        self.db.add(m.ProductUnit(
            name="Beutel", default_conversion_quantity=500, default_conversion_unit="g",
        ))
        self.db.commit()
        receipt.book_receipt_import(self.db, s.ReceiptImportBookRequest(items=[
            s.ReceiptImportBookItem(source_index=0, raw_name="Reis", name="Reis", quantity=2, unit="Beutel"),
        ]))
        item = self.db.query(m.InventoryItem).one()
        self.assertEqual((item.food.serving_size, item.food.serving_unit), (500, "g"))
        self.assertEqual((item.serving_size, item.serving_unit), (500, "g"))
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
