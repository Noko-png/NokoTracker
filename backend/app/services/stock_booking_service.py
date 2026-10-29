"""Stock mutations without commits: the caller owns the complete transaction."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from . import nutrition_service as nutrition


EPSILON = 1e-9


def aggregate_requirements(requirements: list[dict]) -> list[dict]:
    """Compare each food once, even when ingredients use different units."""
    totals = {}
    for row in requirements:
        food = row["food"]
        grams = nutrition.food_amount_in_grams(food, row["quantity"], row["unit"])
        if grams <= 0:
            raise HTTPException(422, "Die zu buchende Menge muss groesser als null sein")
        if food.id not in totals:
            totals[food.id] = {"food": food, "unit": row["unit"], "grams": 0.0}
        totals[food.id]["grams"] += grams
    return [
        {
            "food": row["food"], "unit": row["unit"],
            "quantity": schemas.normalize_fractional_number(nutrition.food_quantity_from_grams(
                row["food"], row["grams"], row["unit"],
            )),
        }
        for row in totals.values()
    ]


def deduct_inventory(db: Session, requirements: list[dict]) -> tuple[list[dict], list[dict]]:
    plans = []
    shortages = []
    for row in aggregate_requirements(requirements):
        food = row["food"]
        required = nutrition.food_amount_in_grams(food, row["quantity"], row["unit"])
        items = db.query(models.InventoryItem).filter(models.InventoryItem.food_id == food.id).all()
        items.sort(key=lambda item: (item.expiry_date is None, item.expiry_date or item.purchase_date, item.id))
        available = sum(nutrition.food_amount_in_grams(item, item.quantity, item.unit) for item in items)
        if required - available > EPSILON:
            shortages.append(food.name)
        plans.append((row, required, items))
    if shortages:
        raise HTTPException(422, "Nicht genug Bestand: " + "; ".join(shortages))

    consumed = []
    deductions = []
    for row, remaining, items in plans:
        for item in items:
            if remaining <= EPSILON:
                break
            available = nutrition.food_amount_in_grams(item, item.quantity, item.unit)
            grams = min(available, remaining)
            if grams <= 0:
                continue
            quantity = min(item.quantity, nutrition.food_quantity_from_grams(item, grams, item.unit))
            snapshot = schemas.InventoryItemCreate.model_validate(item, from_attributes=True)
            deductions.append({
                "inventory_item_id": item.id, "quantity": quantity,
                "snapshot": snapshot.model_dump(mode="json"),
            })
            item.quantity = schemas.normalize_fractional_number(max(0.0, item.quantity - quantity))
            remaining -= grams
            db.add(item)
        if remaining > EPSILON:
            raise HTTPException(422, "Bestand hat sich waehrend der Buchung geaendert")
        consumed.append({
            "food_id": row["food"].id, "name": row["food"].name,
            "quantity": row["quantity"], "unit": row["unit"],
        })
    return consumed, deductions


def restore_meal_inventory(db: Session, meal_log: models.MealLog) -> None:
    booking = meal_log.inventory_booking
    if booking is None:
        # Historic deductions did not record their lots. Guessing would create stock.
        raise HTTPException(409, "Diese Altbuchung hat keinen Bestandsnachweis. Eine automatische Bestandskorrektur ist nicht moeglich.")
    entries = [schemas.StoredInventoryDeduction.model_validate(row) for row in booking.deductions]
    lot_fields = ("food_id", "unit", "serving_size", "serving_unit", "purchase_date", "expiry_days", "storage_location")
    for entry in entries:
        item = db.get(models.InventoryItem, entry.inventory_item_id)
        snapshot = entry.snapshot
        if item is None or any(getattr(item, field) != getattr(snapshot, field) for field in lot_fields):
            item = models.InventoryItem(**snapshot.model_dump(exclude={"quantity"}), quantity=0.0)
            db.add(item)
        item.quantity = schemas.normalize_fractional_number(item.quantity + entry.quantity)
    # New/recreated lots must be visible to the subsequent deduction in this transaction.
    db.flush()
