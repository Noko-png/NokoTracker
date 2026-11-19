"""Minimum stock is a food setting, independent of the existence of stock lots."""

import math

from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from . import nutrition_service as nutrition


def foods_below_minimum(db: Session) -> list[schemas.FoodStockLevelRead]:
    foods = (
        db.query(models.Food)
        .filter(models.Food.is_archived.is_(False), models.Food.minimum_quantity > 0)
        .options(
            selectinload(models.Food.product_unit),
            selectinload(models.Food.conversions),
            selectinload(models.Food.inventory_items),
        )
        .order_by(models.Food.id)
        .all()
    )
    result = []
    for food in foods:
        unit = food.product_unit.name if food.product_unit is not None else food.serving_unit
        grams = sum(nutrition.food_amount_in_grams(item, item.quantity, item.unit) for item in food.inventory_items)
        quantity = nutrition.food_quantity_from_grams(food, grams, unit)
        if quantity >= food.minimum_quantity or math.isclose(quantity, food.minimum_quantity, rel_tol=1e-9, abs_tol=1e-9):
            continue
        result.append(schemas.FoodStockLevelRead(
            food_id=food.id, name=food.name, emoji=food.emoji, brand=food.brand,
            quantity=schemas.normalize_fractional_number(quantity), unit=unit,
            minimum_quantity=food.minimum_quantity,
            missing_quantity=schemas.normalize_fractional_number(food.minimum_quantity - quantity),
            inventory_item_id=min((item.id for item in food.inventory_items), default=None),
        ))
    return result
