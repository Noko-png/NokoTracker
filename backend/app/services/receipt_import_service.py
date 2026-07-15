from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas


ITEM_LINE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<price>\d+(?:\.\d{3})*,\d{2})\s+(?P<tax>[A-Z])(?:\s+\*)?$"
)
QUANTITY_LINE_RE = re.compile(
    r"^(?P<quantity>\d+(?:[,.]\d+)?)\s*(?P<unit>Stk|STK|kg|KG|g|G|l|L|ml|ML)\s*x\s*"
    r"(?P<unit_price>\d+(?:\.\d{3})*,\d{2})$"
)
RECEIPT_DATE_RE = re.compile(r"Datum:\s*(?P<date>\d{2}\.\d{2}\.\d{4})")
TOTAL_RE = re.compile(r"\bSUMME\s+EUR\s+(?P<total>\d+(?:\.\d{3})*,\d{2})")

IGNORE_NAME_PREFIXES = (
    "PFAND",
    "SUMME",
    "GEG.",
    "STEUER",
    "GESAMTBETRAG",
    "BONUS",
    "COUPON",
    "RABATT",
)
UNIT_MAP = {
    "stk": "pcs",
    "kg": "kg",
    "g": "g",
    "l": "l",
    "ml": "ml",
}
READY_MATCH_THRESHOLD = 0.84
AMBIGUOUS_MATCH_DISTANCE = 0.05


@dataclass(frozen=True)
class ParsedReceiptLine:
    source_index: int
    raw_name: str
    quantity: float
    unit: str
    total_price: float
    unit_price: float | None
    tax_class: str | None
    ignored: bool
    review_reason: str | None


def parse_german_decimal(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def clean_receipt_name(value: str) -> str:
    return " ".join(value.strip().split())


def normalized_match_text(value: str) -> str:
    normalized = value.upper()
    replacements = {
        "Ä": "AE",
        "Ö": "OE",
        "Ü": "UE",
        "ẞ": "SS",
        "ß": "SS",
        "&": " UND ",
    }
    for source, replacement in replacements.items():
        normalized = normalized.replace(source, replacement)
    normalized = re.sub(r"[^A-Z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def decode_pdf_text(content_base64: str) -> str:
    payload = content_base64.split(",", 1)[-1]
    try:
        data = base64.b64decode(payload, validate=True)
    except ValueError as exc:
        raise ValueError("PDF konnte nicht als Base64 gelesen werden") from exc

    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:  # pragma: no cover - pypdf raises a few concrete types
        raise ValueError("PDF konnte nicht gelesen werden") from exc

    text_parts: list[str] = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts).strip()
    if not text:
        raise ValueError("Im PDF wurde kein lesbarer Text gefunden")
    return text


def parse_receipt_date(text: str) -> date | None:
    match = RECEIPT_DATE_RE.search(text)
    if match is None:
        fallback = re.search(r"(?P<date>\d{2}\.\d{2}\.\d{4})\s+\d{2}:\d{2}", text)
        match = fallback
    if match is None:
        return None
    return datetime.strptime(match.group("date"), "%d.%m.%Y").date()


def parse_receipt_total(text: str) -> float | None:
    match = TOTAL_RE.search(text)
    return parse_german_decimal(match.group("total")) if match else None


def parse_store_name(lines: list[str]) -> str | None:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("REWE "):
            return stripped
    return None


def is_ignored_name(name: str) -> bool:
    normalized = normalized_match_text(name)
    return any(normalized.startswith(prefix) for prefix in IGNORE_NAME_PREFIXES)


def parse_receipt_lines(text: str) -> list[ParsedReceiptLine]:
    lines = [line.strip() for line in text.splitlines()]
    parsed: list[ParsedReceiptLine] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        match = ITEM_LINE_RE.match(line)
        if match is None:
            index += 1
            continue

        raw_name = clean_receipt_name(match.group("name"))
        total_price = parse_german_decimal(match.group("price"))
        quantity = 1.0
        unit = "pcs"
        unit_price: float | None = total_price
        next_line_used = False
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        quantity_match = QUANTITY_LINE_RE.match(next_line)

        if quantity_match:
            quantity = schemas.normalize_fractional_number(
                parse_german_decimal(quantity_match.group("quantity"))
            )
            unit = UNIT_MAP.get(quantity_match.group("unit").lower(), quantity_match.group("unit"))
            unit_price = parse_german_decimal(quantity_match.group("unit_price"))
            next_line_used = True

        ignored = is_ignored_name(raw_name)
        review_reason = "Pfand, Rabatt oder Zahlungszeile" if ignored else None
        parsed.append(
            ParsedReceiptLine(
                source_index=len(parsed),
                raw_name=raw_name,
                quantity=quantity,
                unit=unit,
                total_price=total_price,
                unit_price=unit_price,
                tax_class=match.group("tax"),
                ignored=ignored,
                review_reason=review_reason,
            )
        )
        index += 2 if next_line_used else 1

    return parsed


def score_food_match(receipt_name: str, food: models.Food) -> float:
    receipt_text = normalized_match_text(receipt_name)
    food_text = normalized_match_text(food.name)
    if not receipt_text or not food_text:
        return 0.0
    if receipt_text == food_text:
        return 1.0

    sequence_score = SequenceMatcher(None, receipt_text, food_text).ratio()
    receipt_tokens = set(receipt_text.split())
    food_tokens = set(food_text.split())
    token_score = (
        len(receipt_tokens & food_tokens) / max(len(receipt_tokens | food_tokens), 1)
    )

    if receipt_text in food_text or food_text in receipt_text:
        sequence_score = max(sequence_score, 0.9)

    return max(sequence_score, token_score)


def food_suggestions(
    receipt_name: str,
    foods: list[models.Food],
) -> list[tuple[models.Food, float]]:
    scored = [
        (food, score_food_match(receipt_name, food))
        for food in foods
    ]
    return [
        (food, round(score, 4))
        for food, score in sorted(scored, key=lambda item: item[1], reverse=True)
        if score >= 0.35
    ][:5]


def classify_match(
    line: ParsedReceiptLine,
    suggestions: list[tuple[models.Food, float]],
) -> tuple[str, str | None, models.Food | None]:
    if line.ignored:
        return "ignored", line.review_reason, None
    if line.quantity <= 0:
        return "needs_review", "Menge konnte nicht eindeutig erkannt werden", None
    if not suggestions:
        return "needs_review", "Kein eindeutiger Lebensmittel-Datenbankeintrag gefunden", None

    best_food, best_score = suggestions[0]
    second_score = suggestions[1][1] if len(suggestions) > 1 else 0.0
    if best_score >= READY_MATCH_THRESHOLD and best_score - second_score >= AMBIGUOUS_MATCH_DISTANCE:
        return "ready", None, best_food
    if best_score < READY_MATCH_THRESHOLD:
        return "needs_review", "Kein eindeutiger Lebensmittel-Datenbankeintrag gefunden", None

    return "needs_review", "Mehrere moegliche Lebensmittel-Datenbankeintraege", None


def preview_receipt_import(
    db: Session,
    request: schemas.ReceiptImportPreviewRequest,
) -> schemas.ReceiptImportPreview:
    text = decode_pdf_text(request.content_base64)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    foods = db.query(models.Food).filter(models.Food.is_archived.is_(False)).all()
    parsed_lines = parse_receipt_lines(text)
    warnings: list[str] = []

    if not parsed_lines:
        warnings.append("Es wurden keine Produktzeilen im Kassenzettel gefunden")

    items = []
    for line in parsed_lines:
        suggestions = food_suggestions(line.raw_name, foods)
        status, review_reason, matched_food = classify_match(line, suggestions)
        item_suggestions = [
            {"food": food, "score": score}
            for food, score in suggestions
        ]
        items.append(
            {
                "source_index": line.source_index,
                "raw_name": line.raw_name,
                "name": matched_food.name if matched_food is not None else line.raw_name,
                "quantity": line.quantity,
                "unit": matched_food.product_unit.name
                if matched_food is not None and matched_food.product_unit is not None
                else line.unit,
                "unit_price": line.unit_price,
                "total_price": line.total_price,
                "tax_class": line.tax_class,
                "status": status,
                "review_reason": review_reason,
                "matched_food_id": matched_food.id if matched_food is not None else None,
                "matched_food": matched_food,
                "suggestions": item_suggestions,
            }
        )

    return schemas.ReceiptImportPreview(
        filename=request.filename,
        receipt_date=parse_receipt_date(text),
        store_name=parse_store_name(lines),
        total=parse_receipt_total(text),
        items=items,
        imported_count=sum(1 for item in items if item["status"] == "ready"),
        review_count=sum(1 for item in items if item["status"] == "needs_review"),
        ignored_count=sum(1 for item in items if item["status"] == "ignored"),
        warnings=warnings,
    )


def price_per_unit(item: schemas.ReceiptImportBookItem) -> float | None:
    if item.unit_price is not None:
        return item.unit_price
    if item.total_price is not None and item.quantity > 0:
        return round(item.total_price / item.quantity, 4)
    return None


def default_conversion_for_unit(unit_name: str) -> tuple[float, str]:
    normalized_unit = unit_name.strip().lower()
    if normalized_unit in {"g", "gram", "grams", "kg", "ml", "l"}:
        return 1.0, unit_name
    return 100.0, "g"


def food_or_create(
    db: Session,
    item: schemas.ReceiptImportBookItem,
    product_unit: models.ProductUnit,
) -> models.Food:
    if item.food_id is not None:
        food = crud.get(db, models.Food, item.food_id)
        if food is None:
            raise ValueError(f"Lebensmittel nicht gefunden: {item.food_id}")
        return food

    food = crud.get_food_by_name_brand(db, item.name, None)
    if food is not None:
        return food

    serving_size, serving_unit = default_conversion_for_unit(product_unit.name)
    food = models.Food(
        name=item.name,
        product_unit_id=product_unit.id,
        serving_size=serving_size,
        serving_unit=serving_unit,
    )
    db.add(food)
    db.flush()
    return food


def book_receipt_import(
    db: Session,
    request: schemas.ReceiptImportBookRequest,
) -> schemas.ReceiptImportBookResult:
    inventory_items: list[models.InventoryItem] = []
    warnings: list[str] = []
    skipped_count = 0

    try:
        for item in request.items:
            if not item.book:
                skipped_count += 1
                continue

            product_unit = crud.get_or_create_product_unit(db, item.unit)
            food = food_or_create(db, item, product_unit)
            product_group = (
                crud.get(db, models.ProductGroup, food.product_group_id)
                if food.product_group_id is not None
                else None
            )
            storage_location = (
                item.storage_location
                or request.default_storage_location
                or food.storage_location
                or (product_group.default_storage_location if product_group is not None else None)
            )
            inventory_item = models.InventoryItem(
                name=food.name,
                emoji=food.emoji,
                brand=food.brand,
                category=food.category,
                quantity=schemas.normalize_fractional_number(item.quantity),
                unit=product_unit.name,
                minimum_quantity=0.0,
                storage_location=storage_location,
                expiry_days=product_group.default_expiry_days if product_group is not None else None,
                purchase_date=request.purchase_date,
                price=price_per_unit(item),
                barcode=None,
                image_path=None,
                notes=f"REWE-Bon: {item.raw_name}",
                food_id=food.id,
                product_group_id=food.product_group_id,
                product_unit_id=product_unit.id,
                serving_size=food.serving_size,
                serving_unit=food.serving_unit,
                calories_per_100g=food.calories_per_100g,
                protein_per_100g=food.protein_per_100g,
                carbs_per_100g=food.carbs_per_100g,
                fat_per_100g=food.fat_per_100g,
            )
            db.add(inventory_item)
            inventory_items.append(inventory_item)

        if not inventory_items:
            warnings.append("Es wurden keine Kassenzettelzeilen zum Buchen ausgewaehlt")

        db.commit()
        for inventory_item in inventory_items:
            db.refresh(inventory_item)
    except (IntegrityError, ValueError):
        db.rollback()
        raise

    return schemas.ReceiptImportBookResult(
        booked_count=len(inventory_items),
        skipped_count=skipped_count,
        inventory_items=inventory_items,
        warnings=warnings,
    )
