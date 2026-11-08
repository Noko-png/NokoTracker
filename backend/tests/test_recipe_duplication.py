import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.routers import recipes


class RecipeDuplicationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(models.User(id=1, username="Test"))
        self.food = models.Food(name="Zutat", serving_size=100, calories_per_100g=200)
        self.db.add(self.food)
        self.db.commit()
        self.source = recipes.create_recipe(schemas.RecipeCreate(
            name="Original", emoji="🥘", description="Beschreibung", instructions="Schritt 1\n\nSchritt 2",
            tags=["Mahlzeit", "Veg"], image_path="data:image/png;base64,dGVzdA==", servings=2.5,
            prep_time_minutes=15, cook_time_minutes=25, created_by_user_id=1,
            ingredients=[schemas.RecipeIngredientCreateForRecipe(
                food_id=self.food.id, quantity=125.25, unit="g", notes="Fein schneiden",
            )],
        ), self.db)

    def test_copy_has_own_recipe_ingredients_and_prepared_product(self):
        original = schemas.RecipeRead.model_validate(self.source).model_dump()
        copy = recipes.duplicate_recipe(self.source.id, self.db)
        self.assertNotEqual(copy.id, self.source.id)
        self.assertEqual(copy.name, "Original (Kopie)")
        self.assertFalse(copy.is_archived)
        for field in ["emoji", "description", "instructions", "tags", "image_path", "servings", "prep_time_minutes", "cook_time_minutes"]:
            self.assertEqual(getattr(copy, field), getattr(self.source, field), field)
        source_ingredient, copied_ingredient = self.source.ingredients[0], copy.ingredients[0]
        self.assertNotEqual(source_ingredient.id, copied_ingredient.id)
        for field in ["food_id", "quantity", "unit", "notes"]:
            self.assertEqual(getattr(copied_ingredient, field), getattr(source_ingredient, field))
        self.assertNotEqual(copy.prepared_food_id, self.source.prepared_food_id)
        self.assertEqual(self.db.query(models.Food).count(), 3)  # shared ingredient + two prepared products

        recipes.update_recipe(copy.id, schemas.RecipeUpdate(
            name="Original v2", servings=4, instructions="Andere Zubereitung", tags=["v2"],
            ingredients=[schemas.RecipeIngredientCreateForRecipe(food_id=self.food.id, quantity=77.125, unit="g")],
        ), self.db)
        self.db.expire_all()
        self.assertEqual(schemas.RecipeRead.model_validate(self.source).model_dump(), original)
        self.assertEqual(copy.ingredients[0].quantity, 77.125)
        self.assertEqual(copy.prepared_food.name, "Original v2")
        self.assertEqual(self.source.prepared_food.name, "Original")
        self.assertEqual(self.db.query(models.MealLog).count(), 0)
        self.assertEqual(self.db.query(models.InventoryItem).count(), 0)

    def test_repeated_copies_and_orphaned_prepared_food_use_distinct_names(self):
        self.db.add(models.Food(name="Original (Kopie)", brand="Zubereitet"))
        self.db.commit()
        first = recipes.duplicate_recipe(self.source.id, self.db)
        second = recipes.duplicate_recipe(self.source.id, self.db)
        self.assertEqual(first.name, "Original (Kopie 2)")
        self.assertEqual(second.name, "Original (Kopie 3)")
        self.assertNotEqual(first.prepared_food_id, second.prepared_food_id)

    def test_long_names_and_archived_recipes_produce_valid_active_copy(self):
        self.source.name = "A" * 200
        self.source.is_archived = True
        self.db.commit()
        copy = recipes.duplicate_recipe(self.source.id, self.db)
        self.assertEqual(len(copy.name), 200)
        self.assertTrue(copy.name.endswith(" (Kopie)"))
        self.assertFalse(copy.is_archived)
        self.assertTrue(self.source.is_archived)

    def test_duplicate_failure_rolls_back_recipe_and_ingredients(self):
        counts = (self.db.query(models.Recipe).count(), self.db.query(models.RecipeIngredient).count(), self.db.query(models.Food).count())
        with patch.object(recipes, "recipe_prepared_food", side_effect=IntegrityError("test", {}, Exception("test"))):
            with self.assertRaises(HTTPException) as caught:
                recipes.duplicate_recipe(self.source.id, self.db)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual((self.db.query(models.Recipe).count(), self.db.query(models.RecipeIngredient).count(), self.db.query(models.Food).count()), counts)

    def test_missing_source_does_not_create_anything(self):
        with self.assertRaises(HTTPException) as caught:
            recipes.duplicate_recipe(999, self.db)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.db.query(models.Recipe).count(), 1)
