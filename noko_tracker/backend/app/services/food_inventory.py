from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import crud, models
from . import nutrition_service


def food_unit_key(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    for canonical, aliases in (
        ("g", nutrition_service.GRAM_UNITS),
        ("kg", nutrition_service.KILOGRAM_UNITS),
        ("mg", nutrition_service.MILLIGRAM_UNITS),
        ("ml", nutrition_service.MILLILITER_UNITS),
        ("l", nutrition_service.LITER_UNITS),
        ("oz", nutrition_service.OUNCE_UNITS),
        ("lb", nutrition_service.POUND_UNITS),
    ):
        if normalized in aliases:
            return canonical
    return normalized


def food_serving_conversion(food: models.Food, unit: str) -> tuple[float, str]:
    physical_quantity = nutrition_service._unit_to_grams(1, unit)
    if physical_quantity is not None:
        target = "ml" if food_unit_key(unit) in {"ml", "l"} else "g"
        return physical_quantity, target
    conversion = next((row for row in food.conversions if (
        row.quantity > 0 and food_unit_key(row.unit) == food_unit_key(unit)
    )), None)
    quantity = conversion.quantity if conversion is not None else 1
    return food.serving_size / quantity, food.serving_unit


def apply_food_inventory_values(
    db: Session,
    food: models.Food,
    data: dict,
    existing_item: models.InventoryItem | None = None,
) -> dict:
    payload = dict(data)
    if "unit" in payload:
        requested_unit = payload["unit"]
    elif payload.get("product_unit_id") is not None:
        product_unit = db.get(models.ProductUnit, payload["product_unit_id"])
        if product_unit is None:
            raise HTTPException(404, "Product unit not found")
        requested_unit = product_unit.name
    elif existing_item is not None and existing_item.food_id == food.id:
        requested_unit = existing_item.unit
    else:
        requested_unit = food.product_unit.name if food.product_unit is not None else food.serving_unit

    same_stock_unit = (
        existing_item is not None and existing_item.food_id == food.id
        and food_unit_key(existing_item.unit) == food_unit_key(requested_unit)
    )
    allowed_units = [food.serving_unit]
    if food.product_unit is not None:
        allowed_units.insert(0, food.product_unit.name)
    allowed_units.extend(row.unit for row in food.conversions if row.quantity > 0)
    selected_unit = next((unit for unit in allowed_units if (
        food_unit_key(unit) == food_unit_key(requested_unit)
    )), None)
    if selected_unit is None and not same_stock_unit:
        raise HTTPException(422, "Diese Mengeneinheit ist beim ausgewaehlten Lebensmittel nicht hinterlegt.")

    if same_stock_unit:
        selected_unit = existing_item.unit
        payload["serving_size"] = existing_item.serving_size
        payload["serving_unit"] = existing_item.serving_unit
    else:
        payload["serving_size"], payload["serving_unit"] = food_serving_conversion(food, selected_unit)
    product_unit = crud.get_product_unit_by_name(db, selected_unit)
    payload.update({
        "name": food.name, "emoji": food.emoji,
        "brand": (food.brand or "").strip() or None,
        "category": (food.category or "").strip() or None,
        "unit": selected_unit, "food_id": food.id,
        "product_unit_id": product_unit.id if product_unit is not None else None,
        "calories_per_100g": food.calories_per_100g,
        "protein_per_100g": food.protein_per_100g,
        "carbs_per_100g": food.carbs_per_100g,
        "fat_per_100g": food.fat_per_100g,
    })
    return payload
