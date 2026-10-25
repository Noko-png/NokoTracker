import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.routers import foods, inventory, shopping


class FoodEditingTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.food = foods.create_food(
            schemas.FoodCreate(
                name="Testlebensmittel",
                brand="Testmarke",
                purchase_date=date(2026, 10, 20),
                expiry_days=7,
                conversions=[schemas.FoodConversionCreate(quantity=500, unit="Packung")],
            ),
            self.db,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_full_edit_saves_dates_and_other_fields_with_existing_conversions(self):
        payload = schemas.FoodCreate.model_validate(
            schemas.FoodRead.model_validate(self.food).model_dump()
        ).model_dump()
        payload.update(
            expiry_days=14,
            purchase_date=date(2026, 10, 25),
            name="Geaendertes Lebensmittel",
            brand="Neue Marke",
            storage_location="Kuehlschrank",
            calories_per_100g=120,
        )
        foods.update_food(self.food.id, schemas.FoodUpdate(**payload), self.db)
        self.db.expire_all()
        updated = foods.read_food(self.food.id, self.db)
        self.assertEqual(updated.expiry_days, 14)
        self.assertEqual(updated.purchase_date, date(2026, 10, 25))
        self.assertEqual(updated.name, "Geaendertes Lebensmittel")
        self.assertEqual(updated.brand, "Neue Marke")
        self.assertEqual(updated.storage_location, "Kuehlschrank")
        self.assertEqual(updated.calories_per_100g, 120)
        self.assertEqual([(item.unit, item.quantity) for item in updated.conversions], [("Packung", 500)])

    def test_repeated_edit_can_replace_a_conversion_with_the_same_unit(self):
        for days, quantity in [(14, 250), (0, 125), (30, 500)]:
            foods.update_food(
                self.food.id,
                schemas.FoodUpdate(
                    expiry_days=days,
                    conversions=[schemas.FoodConversionCreate(unit="Packung", quantity=quantity)],
                ),
                self.db,
            )
            self.db.expire_all()
            self.assertEqual(self.food.expiry_days, days)
            self.assertEqual([(item.unit, item.quantity) for item in self.food.conversions], [("Packung", quantity)])

    def test_partial_edit_does_not_remove_conversions_and_can_clear_expiry(self):
        for days in (14, 0, None):
            foods.update_food(self.food.id, schemas.FoodUpdate(expiry_days=days), self.db)
            self.db.expire_all()
            self.assertEqual(self.food.expiry_days, days)
            self.assertEqual(len(self.food.conversions), 1)

    def test_empty_conversion_list_removes_conversions(self):
        foods.update_food(self.food.id, schemas.FoodUpdate(conversions=[], expiry_days=14), self.db)
        self.db.expire_all()
        self.assertEqual(self.food.expiry_days, 14)
        self.assertEqual(self.food.conversions, [])

    def test_failed_edit_rolls_back_the_food_and_its_conversions(self):
        foods.create_food(schemas.FoodCreate(name="Belegt", brand="Testmarke"), self.db)
        with self.assertRaises(HTTPException) as context:
            foods.update_food(
                self.food.id,
                schemas.FoodUpdate(
                    name="Belegt", expiry_days=14,
                    conversions=[schemas.FoodConversionCreate(unit="Packung", quantity=250)],
                ),
                self.db,
            )
        self.assertEqual(context.exception.status_code, 409)
        self.db.expire_all()
        self.assertEqual(self.food.name, "Testlebensmittel")
        self.assertEqual(self.food.expiry_days, 7)
        self.assertEqual(self.food.conversions[0].quantity, 500)

    def test_inventory_edit_recalculates_only_the_edited_batch_expiry_date(self):
        item = inventory.create_inventory_item(
            schemas.InventoryItemCreate(
                name=self.food.name, food_id=self.food.id, quantity=2,
                purchase_date=date(2026, 10, 20), expiry_days=7,
            ),
            self.db,
        )
        other = inventory.create_inventory_item(
            schemas.InventoryItemCreate(
                name=self.food.name, food_id=self.food.id, quantity=1,
                purchase_date=date(2026, 10, 21), expiry_days=3,
            ),
            self.db,
        )
        inventory.replace_inventory_item(
            item.id,
            schemas.InventoryItemCreate(
                name=self.food.name, food_id=self.food.id, quantity=2,
                purchase_date=date(2026, 10, 25), expiry_days=14,
            ),
            self.db,
        )
        self.db.expire_all()
        self.assertEqual(item.expiry_date, date(2026, 11, 8))
        self.assertEqual(other.expiry_date, date(2026, 10, 24))
        self.assertEqual(self.food.expiry_days, 7)

    def test_shopping_import_uses_food_expiry_before_group_default(self):
        group = models.ProductGroup(name="Testgruppe", default_expiry_days=7)
        self.db.add(group)
        self.db.commit()
        self.food.product_group = group
        for days in (14, 0, None):
            self.food.expiry_days = days
            self.db.commit()
            item = models.InventoryItem(name=self.food.name)
            shopping.apply_default_inventory_values(item, self.food, date(2026, 10, 25))
            self.assertEqual(item.expiry_days, days if days is not None else 7)


if __name__ == "__main__":
    unittest.main()
