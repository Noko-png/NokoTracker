"""Product barcode aliases. All callers retain ownership of their transaction."""
import re

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models


def normalize_barcode(value: str) -> str:
    code = re.sub(r"[\s-]+", "", value or "")
    if not re.fullmatch(r"[0-9]{8,128}", code):
        raise HTTPException(422, "EAN-Codes muessen aus 8 bis 128 Ziffern bestehen")
    return code


def barcode_match(code: str):
    return or_(models.Food.barcode == code, models.Food.barcode_entries.any(models.FoodBarcode.barcode == code))


def find_food(db: Session, code: str) -> models.Food | None:
    matches = db.query(models.Food).filter(barcode_match(code)).limit(2).all()
    if len(matches) > 1:
        raise HTTPException(409, "Dieser EAN-Code ist mehreren Produkten zugeordnet. Bitte die Stammdaten korrigieren.")
    if matches and matches[0].is_archived:
        raise HTTPException(409, "Das Produkt zu diesem EAN-Code ist archiviert. Bitte zuerst wiederherstellen.")
    return matches[0] if matches else None


def replace_barcodes(db: Session, food: models.Food, values: list[str]) -> None:
    codes = list(dict.fromkeys(normalize_barcode(value) for value in values if value.strip()))
    if len(codes) > 100:
        raise HTTPException(422, "Pro Produkt sind maximal 100 EAN-Codes erlaubt")
    for code in codes:
        owners = db.query(models.Food).filter(barcode_match(code))
        stock_owners = db.query(models.InventoryItem).filter(
            models.InventoryItem.barcode == code, models.InventoryItem.food_id.is_not(None),
        )
        if food.id is not None:
            owners = owners.filter(models.Food.id != food.id)
            stock_owners = stock_owners.filter(models.InventoryItem.food_id != food.id)
        if owners.first() is not None or stock_owners.first() is not None:
            raise HTTPException(409, f"EAN {code} ist bereits einem anderen Produkt zugeordnet")

    removed = set(food.barcodes) - set(codes)
    if food.id is not None and removed:
        # A removed product alias must not stay searchable through an old lot.
        for item in db.query(models.InventoryItem).filter(
            models.InventoryItem.food_id == food.id, models.InventoryItem.barcode.in_(removed),
        ):
            item.barcode = None
    existing = {entry.barcode: entry for entry in food.barcode_entries}
    food.barcode_entries[:] = [entry for entry in food.barcode_entries if entry.barcode in codes]
    for code in codes:
        if code not in existing:
            food.barcode_entries.append(models.FoodBarcode(barcode=code))
    food.barcode = codes[0] if codes else None
    db.add(food)
    db.flush()
    for item in db.query(models.InventoryItem).filter(
        models.InventoryItem.food_id.is_(None), models.InventoryItem.barcode.in_(codes),
    ):
        item.food_id = food.id
    db.flush()


def append_barcodes(db: Session, food: models.Food, values: list[str]) -> None:
    if values:
        replace_barcodes(db, food, [*food.barcodes, *values])


def apply_input(db: Session, food: models.Food, payload) -> None:
    if "barcodes" in payload.model_fields_set:
        replace_barcodes(db, food, payload.barcodes or [])
    elif "barcode" in payload.model_fields_set:
        # Old clients change the primary code without deleting secondary aliases.
        others = [code for code in food.barcodes if code != food.barcode]
        replace_barcodes(db, food, ([payload.barcode] if payload.barcode else []) + others)
