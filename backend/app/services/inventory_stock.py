import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from .food_inventory import food_serving_conversion, food_unit_key
from . import nutrition_service


MASS_UNITS = {"g", "kg", "mg", "oz", "lb"}
VOLUME_UNITS = {"ml", "l"}


def _quantity_factor(db: Session, item: models.InventoryItem) -> tuple[str, float] | None:
    unit = food_unit_key(item.unit)
    if unit in MASS_UNITS | VOLUME_UNITS:
        dimension = "volume" if unit in VOLUME_UNITS else "mass"
        return dimension, nutrition_service._unit_to_grams(1, item.unit)

    food = item.food or db.get(models.Food, item.food_id)
    if food is None:
        return None
    serving_unit = food_unit_key(item.serving_unit)
    if not serving_unit:
        return None
    physical_factor = nutrition_service._unit_to_grams(1, item.serving_unit)
    factor = (item.serving_size or 0) * (physical_factor if physical_factor is not None else 1)
    if not math.isfinite(factor) or factor <= 0:
        return None
    calculated_factor = nutrition_service.food_amount_in_grams(item, 1, item.unit)
    if not math.isfinite(calculated_factor) or not math.isclose(factor, calculated_factor, rel_tol=1e-9, abs_tol=1e-12):
        return None
    dimension = "volume" if serving_unit in VOLUME_UNITS else "mass" if serving_unit in MASS_UNITS else f"unit:{serving_unit}"
    return dimension, factor


def _conversion_factor(db: Session, source: models.InventoryItem, target: models.InventoryItem) -> float | None:
    source_unit = food_unit_key(source.unit)
    target_unit = food_unit_key(target.unit)
    source_factor = _quantity_factor(db, source)
    target_factor = _quantity_factor(db, target)
    if source_factor is None or target_factor is None:
        if (
            source_unit == target_unit
            and source.serving_size == target.serving_size
            and food_unit_key(source.serving_unit) == food_unit_key(target.serving_unit)
        ):
            return 1.0
        return None
    if source_factor[0] != target_factor[0]:
        return None
    if (
        source_unit == target_unit and source_unit not in MASS_UNITS | VOLUME_UNITS
        and not math.isclose(source_factor[1], target_factor[1], rel_tol=1e-9, abs_tol=1e-12)
    ):
        return None
    factor = source_factor[1] / target_factor[1]
    return factor if math.isfinite(factor) and factor > 0 else None


def _compatible_lot(source: models.InventoryItem, target: models.InventoryItem, factor: float) -> bool:
    if any(getattr(source, field) != getattr(target, field) for field in (
        "purchase_date", "expiry_days", "product_group_id", "image_path",
    )):
        return False
    if (source.storage_location or "").strip() != (target.storage_location or "").strip():
        return False
    if source.price is None or target.price is None:
        return source.price is None and target.price is None
    return math.isclose(source.price / factor, target.price, rel_tol=1e-9, abs_tol=1e-9)


def _append_notes(target: models.InventoryItem, incoming: models.InventoryItem) -> None:
    current_note = (target.notes or "").strip()
    incoming_note = (incoming.notes or "").strip()
    if incoming_note and incoming_note != current_note and incoming_note not in current_note.split("\n\n"):
        target.notes = "\n\n".join(note for note in (current_note, incoming_note) if note)


def normalize_inventory_unit(db: Session, item: models.InventoryItem) -> None:
    """Store amounts in the food's primary unit without changing physical stock/value."""
    food = (item.food or db.get(models.Food, item.food_id)) if item.food_id is not None else None
    if food is None:
        return
    if not math.isfinite(nutrition_service.food_amount_in_grams(item, item.quantity, item.unit)):
        raise HTTPException(422, "Die umgerechnete Bestandsmenge ist zu gross.")
    unit = food.product_unit.name if food.product_unit is not None else food.serving_unit
    product_unit = food.product_unit or crud.get_product_unit_by_name(db, unit)
    if food_unit_key(item.unit) != food_unit_key(unit):
        serving_size, serving_unit = food_serving_conversion(food, unit)
        target = models.InventoryItem(food_id=food.id, unit=unit, serving_size=serving_size, serving_unit=serving_unit)
        factor = _conversion_factor(db, item, target)
        if factor is None:
            raise HTTPException(422, "Die Eingabeeinheit kann nicht eindeutig in die Standardeinheit des Lebensmittels umgerechnet werden.")
        values = {"quantity": item.quantity * factor}
        if item.minimum_quantity is not None:
            values["minimum_quantity"] = item.minimum_quantity * factor
        if item.price is not None:
            values["price"] = item.price / factor
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise HTTPException(422, "Die umgerechnete Bestandsmenge oder der Preis ist zu gross.")
        values["quantity"] = schemas.normalize_fractional_number(values["quantity"])
        if item.quantity > 0 and values["quantity"] == 0:
            raise HTTPException(422, "Die Menge ist fuer die Umrechnung in die Standardeinheit zu klein.")
        for field, value in values.items():
            setattr(item, field, value)
        item.serving_size = serving_size
        item.serving_unit = serving_unit
    item.unit = unit
    item.product_unit_id = product_unit.id if product_unit is not None else None


def add_or_merge_inventory(
    db: Session, incoming: models.InventoryItem,
) -> tuple[models.InventoryItem, bool]:
    """Add a prepared transient lot within the caller's transaction."""
    if not math.isfinite(incoming.quantity) or incoming.quantity < 0:
        raise HTTPException(422, "Die Bestandsmenge muss endlich und mindestens null sein.")
    normalize_inventory_unit(db, incoming)
    db.flush()
    if incoming.food_id is not None and incoming.quantity > 0:
        candidates = db.query(models.InventoryItem).filter(
            models.InventoryItem.food_id == incoming.food_id,
        ).order_by(models.InventoryItem.id).all()
        for target in candidates:
            factor = _conversion_factor(db, incoming, target)
            if factor is None or not _compatible_lot(incoming, target, factor):
                continue
            normalize_inventory_unit(db, target)
            factor = _conversion_factor(db, incoming, target)
            if factor is None:
                raise HTTPException(422, "Die Bestandspositionen haben unterschiedliche Umrechnungen.")
            quantity = target.quantity + incoming.quantity * factor
            if not math.isfinite(quantity) or quantity < 0:
                raise HTTPException(422, "Die umgerechnete Bestandsmenge ist zu gross.")
            target.quantity = schemas.normalize_fractional_number(quantity)
            normalize_inventory_unit(db, target)
            _append_notes(target, incoming)
            db.flush()
            return target, False
    db.add(incoming)
    db.flush()
    return incoming, True
