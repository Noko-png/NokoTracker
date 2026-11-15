import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.routers.nutrition import read_day_nutrition
from scripts.convert_macrofactor import import_foods, ingredient_names


class MacroFactorImportTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        models.Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

    def test_names_without_values_and_recipe_ingredients_are_not_lost(self):
        data = {'Custom Foods': [{'Food Name': 'Tofu'}],
                'History': [{'Food Name': 'TOFU'}, {'Food Name': 'Rice'}],
                'Recipes': [{'Ingredients': 'Oil (1 tablespoon)\nTofu (100 g)'}]}
        report = {'warnings': []}
        import_foods(self.session, data, report)
        self.session.commit()
        foods = self.session.query(models.Food).all()
        self.assertEqual({f.name for f in foods}, {'Tofu', 'Rice', 'Oil'})
        self.assertTrue(all(f.category == 'MacroFactor - Naehrwerte fehlen' for f in foods))
        self.assertTrue(all(not f.is_archived for f in foods))
        self.assertEqual(len(report['food_mapping']), 5)

    def test_conflicting_same_name_foods_keep_their_nutrition(self):
        first = {'Food Name': 'Pasta', 'Serving Weight (g)': 200,
                 'Calories (kcal)': 300, 'Protein (g)': 20, 'Fat (g)': 4, 'Carbs (g)': 40}
        second = {**first, 'Calories (kcal)': 400}
        report = {'warnings': []}
        import_foods(self.session, {'Custom Foods': [first, second]}, report)
        self.session.commit()
        foods = self.session.query(models.Food).all()
        self.assertEqual(len(foods), 2)
        self.assertEqual({f.calories_per_100g for f in foods}, {150, 200})
        self.assertEqual(len({f.name for f in foods}), 2)

    def test_missing_profile_returns_404_but_a_day_without_meals_is_valid(self):
        self.session.add(models.User(id=1, username='Noko'))
        self.session.commit()
        with self.assertRaises(HTTPException) as error:
            read_day_nutrition(2, date(2026, 11, 12), self.session)
        self.assertEqual(error.exception.status_code, 404)
        actual = read_day_nutrition(1, date(2026, 11, 12), self.session)
        self.assertEqual(actual['user_id'], 1)
        self.assertEqual(actual['totals']['calories'], 0)


if __name__ == '__main__':
    unittest.main()
