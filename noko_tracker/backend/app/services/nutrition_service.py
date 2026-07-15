from datetime import date as date_type, datetime, time, timedelta

from sqlalchemy.orm import Session

from .. import models, schemas


DEFAULT_DAILY_GOALS = {
    "calories": 2500.0,
    "protein": 156.25,
    "fat": 83.33,
    "carbs": 281.25,
}

GRAM_UNITS = {"g", "gram", "grams", "gramm"}
KILOGRAM_UNITS = {"kg", "kilogram", "kilograms", "kilogramm"}
MILLIGRAM_UNITS = {"mg", "milligram", "milligrams", "milligramm"}
MILLILITER_UNITS = {"ml", "milliliter", "milliliters"}
LITER_UNITS = {"l", "liter", "liters"}
OUNCE_UNITS = {"oz", "ounce", "ounces"}
POUND_UNITS = {"lb", "lbs", "pound", "pounds"}
SERVING_UNITS = {"serving", "servings", "portion", "portions"}


class UserNotFoundError(ValueError):
    pass


def _safe_number(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return max(float(value), 0.0)


def _safe_quantity(value: float | int | None) -> float:
    return _safe_number(schemas.normalize_fractional_number(value))


def _normalized_unit(value: str | None) -> str:
    return (value or "").strip().lower()


def _unit_to_grams(quantity: float, unit: str | None) -> float | None:
    normalized_unit = _normalized_unit(unit)
    if normalized_unit in GRAM_UNITS:
        return quantity
    if normalized_unit in KILOGRAM_UNITS:
        return quantity * 1000.0
    if normalized_unit in MILLIGRAM_UNITS:
        return quantity / 1000.0
    if normalized_unit in MILLILITER_UNITS:
        return quantity
    if normalized_unit in LITER_UNITS:
        return quantity * 1000.0
    if normalized_unit in OUNCE_UNITS:
        return quantity * 28.3495
    if normalized_unit in POUND_UNITS:
        return quantity * 453.592
    return None


def _food_conversion_source(food):
    linked_food = getattr(food, "food", None)
    return linked_food or food


def _product_unit_name(food) -> str:
    source = _food_conversion_source(food)
    product_unit = getattr(source, "product_unit", None) or getattr(food, "product_unit", None)
    if product_unit is not None:
        return product_unit.name
    return getattr(source, "unit", None) or getattr(food, "unit", None) or ""


def _conversion_quantity_for_unit(food, unit: str | None) -> float | None:
    normalized_unit = _normalized_unit(unit)
    if not normalized_unit:
        return None

    source = _food_conversion_source(food)
    for conversion in getattr(source, "conversions", []) or []:
        if _normalized_unit(conversion.unit) != normalized_unit:
            continue
        quantity = _safe_quantity(conversion.quantity)
        if quantity > 0:
            return quantity
    return None


def food_serving_size_in_grams(food: models.Food) -> float:
    source = _food_conversion_source(food)
    serving_size = _safe_number(getattr(source, "serving_size", None)) or _safe_number(
        getattr(food, "serving_size", None)
    ) or 100.0
    serving_unit = getattr(source, "serving_unit", None) or getattr(food, "serving_unit", None)
    return _unit_to_grams(serving_size, serving_unit) or serving_size


def food_amount_in_grams(food: models.Food, quantity: float, unit: str | None) -> float:
    normalized_unit = _normalized_unit(unit or "g")
    safe_quantity = _safe_quantity(quantity)
    direct_grams = _unit_to_grams(safe_quantity, normalized_unit)
    if direct_grams is not None:
        return direct_grams

    serving_size = food_serving_size_in_grams(food)
    conversion_quantity = _conversion_quantity_for_unit(food, normalized_unit)
    if conversion_quantity is not None and serving_size > 0:
        return safe_quantity * serving_size / conversion_quantity

    product_unit = _normalized_unit(_product_unit_name(food))
    inventory_unit = _normalized_unit(getattr(food, "unit", None))
    if (
        normalized_unit in SERVING_UNITS
        or (product_unit and normalized_unit == product_unit)
        or (inventory_unit and normalized_unit == inventory_unit)
    ):
        return safe_quantity * serving_size

    return safe_quantity


def food_quantity_from_grams(food: models.Food, grams: float, unit: str | None) -> float:
    normalized_unit = _normalized_unit(unit or "g")
    safe_grams = _safe_number(grams)

    if normalized_unit in GRAM_UNITS:
        return safe_grams
    if normalized_unit in KILOGRAM_UNITS:
        return safe_grams / 1000.0
    if normalized_unit in MILLIGRAM_UNITS:
        return safe_grams * 1000.0
    if normalized_unit in MILLILITER_UNITS:
        return safe_grams
    if normalized_unit in LITER_UNITS:
        return safe_grams / 1000.0
    if normalized_unit in OUNCE_UNITS:
        return safe_grams / 28.3495
    if normalized_unit in POUND_UNITS:
        return safe_grams / 453.592

    serving_size = food_serving_size_in_grams(food)
    conversion_quantity = _conversion_quantity_for_unit(food, normalized_unit)
    if conversion_quantity is not None and serving_size > 0:
        return safe_grams / serving_size * conversion_quantity

    product_unit = _normalized_unit(_product_unit_name(food))
    inventory_unit = _normalized_unit(getattr(food, "unit", None))
    if (
        normalized_unit in SERVING_UNITS
        or (product_unit and normalized_unit == product_unit)
        or (inventory_unit and normalized_unit == inventory_unit)
    ):
        if serving_size > 0:
            return safe_grams / serving_size

    return safe_grams


def _empty_nutrition() -> dict[str, float]:
    return {
        "calories": 0.0,
        "protein": 0.0,
        "fat": 0.0,
        "carbs": 0.0,
    }


def _add_nutrition(
    target: dict[str, float],
    values: dict[str, float],
    multiplier: float = 1.0,
) -> dict[str, float]:
    safe_multiplier = _safe_number(multiplier)
    for key in target:
        target[key] = _safe_number(target[key] + _safe_number(values.get(key)) * safe_multiplier)
    return target


def _round_nutrition(values: dict[str, float]) -> dict[str, float]:
    return {key: round(_safe_number(value), 2) for key, value in values.items()}


def calculate_user_goals(user: models.User) -> dict[str, float]:
    calories = _safe_number(user.daily_calories) or DEFAULT_DAILY_GOALS["calories"]
    protein_percent = _safe_number(user.protein_percent)
    fat_percent = _safe_number(user.fat_percent)
    carbs_percent = _safe_number(user.carbs_percent)
    percent_total = protein_percent + fat_percent + carbs_percent

    if percent_total <= 0:
        return _round_nutrition(DEFAULT_DAILY_GOALS)

    return _round_nutrition(
        {
            "calories": calories,
            "protein": calories * (protein_percent / 100) / 4,
            "fat": calories * (fat_percent / 100) / 9,
            "carbs": calories * (carbs_percent / 100) / 4,
        }
    )


def _amount_from_food_unit(food: models.Food, quantity: float, unit: str | None) -> float:
    return food_amount_in_grams(food, quantity, unit)


def calculate_food_nutrition(food: models.Food, amount: float) -> dict[str, float]:
    safe_amount = _safe_number(amount)
    factor = safe_amount / 100

    return _round_nutrition(
        {
            "calories": factor * _safe_number(food.calories_per_100g),
            "protein": factor * _safe_number(food.protein_per_100g),
            "fat": factor * _safe_number(food.fat_per_100g),
            "carbs": factor * _safe_number(food.carbs_per_100g),
        }
    )


def calculate_recipe_nutrition(recipe: models.Recipe) -> dict[str, float]:
    totals = _empty_nutrition()

    for ingredient in recipe.ingredients:
        amount = _amount_from_food_unit(ingredient.food, ingredient.quantity, ingredient.unit)
        ingredient_nutrition = calculate_food_nutrition(ingredient.food, amount)
        _add_nutrition(totals, ingredient_nutrition)

    return _round_nutrition(totals)


def calculate_recipe_nutrition_per_serving(recipe: models.Recipe) -> dict[str, float]:
    totals = calculate_recipe_nutrition(recipe)
    servings = _safe_quantity(recipe.servings) or 1.0

    return _round_nutrition({key: value / servings for key, value in totals.items()})


def calculate_quick_add_nutrition(meal_log: models.MealLog) -> dict[str, float]:
    return _round_nutrition(
        {
            "calories": meal_log.quick_calories or 0.0,
            "protein": meal_log.quick_protein or 0.0,
            "carbs": meal_log.quick_carbs or 0.0,
            "fat": meal_log.quick_fat or 0.0,
        }
    )


def calculate_meal_log_nutrition(meal_log: models.MealLog) -> dict[str, float]:
    if meal_log.quick_add_name is not None:
        return calculate_quick_add_nutrition(meal_log)

    if meal_log.food_id is not None and meal_log.food is not None:
        amount = _amount_from_food_unit(meal_log.food, meal_log.quantity, meal_log.unit)
        return calculate_food_nutrition(meal_log.food, amount)

    if meal_log.recipe_id is not None and meal_log.recipe is not None:
        normalized_unit = (meal_log.unit or "serving").lower()
        quantity = _safe_quantity(meal_log.quantity)
        if normalized_unit == "recipe":
            return _round_nutrition(
                {
                    key: value * quantity
                    for key, value in calculate_recipe_nutrition(meal_log.recipe).items()
                }
            )

        return _round_nutrition(
            {
                key: value * quantity
                for key, value in calculate_recipe_nutrition_per_serving(meal_log.recipe).items()
            }
        )

    return _empty_nutrition()


def calculate_day_nutrition(user_id: int, date: date_type, db: Session) -> dict:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise UserNotFoundError(f"User with id {user_id} does not exist")

    day_start = datetime.combine(date, time.min)
    day_end = day_start + timedelta(days=1)
    meal_logs = (
        db.query(models.MealLog)
        .filter(models.MealLog.user_id == user_id)
        .filter(models.MealLog.eaten_at >= day_start)
        .filter(models.MealLog.eaten_at < day_end)
        .all()
    )

    totals = _empty_nutrition()
    for meal_log in meal_logs:
        _add_nutrition(totals, calculate_meal_log_nutrition(meal_log))

    totals = _round_nutrition(totals)
    goals = calculate_user_goals(user)
    remaining = _round_nutrition(
        {
            key: max(goals[key] - totals[key], 0.0)
            for key in goals
        }
    )
    percentages = _round_nutrition(
        {
            key: (totals[key] / goals[key] * 100) if goals[key] > 0 else 0.0
            for key in goals
        }
    )

    return {
        "date": date,
        "user_id": user_id,
        "totals": totals,
        "goals": goals,
        "remaining": remaining,
        "percentages": percentages,
    }
