import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from .food_inventory import food_unit_key
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
    primary_unit = food.product_unit.name if food.product_unit is not None else None
    registered = unit == food_unit_key(primary_unit) or any(
        row.quantity > 0 and unit == food_unit_key(row.unit) for row in food.conversions
    )
    serving_unit = food_unit_key(item.serving_unit)
    if not registered or serving_unit not in MASS_UNITS | VOLUME_UNITS:
        return None
    factor = item.serving_size * nutrition_service._unit_to_grams(1, item.serving_unit)
    if not math.isfinite(factor) or factor <= 0:
        return None
    calculated_factor = nutrition_service.food_amount_in_grams(item, 1, item.unit)
    if not math.isfinite(calculated_factor) or not math.isclose(factor, calculated_factor, rel_tol=1e-9, abs_tol=1e-12):
        return None
    dimension = "volume" if serving_unit in VOLUME_UNITS else "mass"
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


def add_or_merge_inventory(
    db: Session, incoming: models.InventoryItem,
) -> tuple[models.InventoryItem, bool]:
    """Add a prepared transient lot within the caller's transaction."""
    if not math.isfinite(incoming.quantity) or incoming.quantity < 0:
        raise HTTPException(422, "Die Bestandsmenge muss endlich und mindestens null sein.")
    db.flush()
    if incoming.food_id is not None and incoming.quantity > 0:
        candidates = db.query(models.InventoryItem).filter(
            models.InventoryItem.food_id == incoming.food_id,
        ).order_by(models.InventoryItem.id).all()
        for target in candidates:
            factor = _conversion_factor(db, incoming, target)
            if factor is None or not _compatible_lot(incoming, target, factor):
                continue
            quantity = target.quantity + incoming.quantity * factor
            if not math.isfinite(quantity) or quantity < 0:
                raise HTTPException(422, "Die umgerechnete Bestandsmenge ist zu gross.")
            target.quantity = schemas.normalize_fractional_number(quantity)
            _append_notes(target, incoming)
            db.flush()
            return target, False
    db.add(incoming)
    db.flush()
    return incoming, True
