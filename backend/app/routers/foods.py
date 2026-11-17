import json
import logging
import math
import re
import socket
import ssl
from contextlib import closing, contextmanager
from http.client import HTTPException as HTTPClientError, HTTPSConnection
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..services import barcode_service
from ..services.unit_defaults import apply_product_unit_defaults


router = APIRouter(prefix="/foods", tags=["foods"])
barcode_db_session = contextmanager(get_db)
logger = logging.getLogger(__name__)

OPEN_FOOD_FACTS_USER_AGENT = "NokoTracker/3 (https://github.com/Noko-png/NokoTracker)"
OPEN_FOOD_FACTS_TIMEOUT_SECONDS = 6
OPEN_FOOD_FACTS_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
OPEN_FOOD_FACTS_HOST = "world.openfoodfacts.org"
OPEN_FOOD_FACTS_PRODUCT_FIELDS = (
    "product_name,product_name_de,product_name_en,brands,categories,serving_size,nutriments"
)


def get_food_or_404(db: Session, food_id: int) -> models.Food:
    food = crud.get(db, models.Food, food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return food


def validate_food_references(
    db: Session,
    product_group_id: int | None = None,
    product_unit_id: int | None = None,
) -> None:
    if product_group_id is not None and crud.get(db, models.ProductGroup, product_group_id) is None:
        raise HTTPException(status_code=404, detail="Product group not found")
    if product_unit_id is not None and crud.get(db, models.ProductUnit, product_unit_id) is None:
        raise HTTPException(status_code=404, detail="Product unit not found")


def normalized_unit(value: str) -> str:
    return value.strip().lower()


def normalized_conversion_payload(
    conversions: list[schemas.FoodConversionCreate],
) -> list[dict]:
    normalized: dict[str, dict] = {}
    for conversion in conversions:
        unit = conversion.unit.strip()
        if not unit:
            continue
        normalized[normalized_unit(unit)] = {
            "quantity": schemas.normalize_fractional_number(conversion.quantity),
            "unit": unit,
        }
    return list(normalized.values())


def replace_food_conversions(
    db: Session,
    food: models.Food,
    conversions: list[schemas.FoodConversionCreate] | None,
) -> None:
    if conversions is None:
        return

    food.conversions.clear()
    if food.id is not None:
        # Delete old rows before inserting the same unique food/unit combination.
        db.flush()
    for conversion in normalized_conversion_payload(conversions):
        food.conversions.append(models.FoodConversion(**conversion))


def normalize_barcode(value: str) -> str:
    return barcode_service.normalize_barcode(value)


def number_from_open_food_facts(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        number = float(value)
        return max(number, 0.0) if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def nutrition_value(nutriments: dict, *keys: str) -> float:
    for key in keys:
        value = number_from_open_food_facts(nutriments.get(key))
        if value is not None:
            return value
    return 0.0


def product_nutriments(product: dict) -> dict:
    nutriments = product.get("nutriments")
    return nutriments if isinstance(nutriments, dict) else {}


def additional_nutrients_from_open_food_facts(product: dict) -> dict:
    # OFF *_100g amounts are normalized to grams, including caffeine:
    # https://github.com/openfoodfacts/openfoodfacts-server/blob/main/html/data-fields.txt
    nutriments = product_nutriments(product)
    values = {}
    for source, target, factor in (
        ("fiber_100g", "fiber_per_100g", 1),
        ("sugars_100g", "sugar_per_100g", 1),
        ("caffeine_100g", "caffeine_mg_per_100g", 1000),
    ):
        value = number_from_open_food_facts(nutriments.get(source))
        if value is not None:
            converted = value * factor
            if math.isfinite(converted):
                values[target] = round(converted, 8)
    return values


def product_nutrition_score(product: dict) -> int:
    nutriments = product_nutriments(product)
    return sum(
        nutrition_value(nutriments, *keys) > 0
        for keys in (
            ("energy-kcal_100g", "energy-kcal", "energy-kcal_value", "energy_100g"),
            ("proteins_100g", "proteins", "proteins_value"),
            ("fat_100g", "fat", "fat_value"),
            ("carbohydrates_100g", "carbohydrates", "carbohydrates_value"),
        )
    )


def product_has_nutrition(product: dict) -> bool:
    return product_nutrition_score(product) > 0


def food_has_nutrition(food: models.Food | models.InventoryItem) -> bool:
    return any(
        (getattr(food, field) or 0) > 0
        for field in (
            "calories_per_100g",
            "protein_per_100g",
            "fat_per_100g",
            "carbs_per_100g",
        )
    )


def parse_serving_size(value: str | None) -> tuple[float, str]:
    if not isinstance(value, str) or not value:
        return 100.0, "g"
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)?", value)
    if not match:
        return 100.0, "g"
    quantity = number_from_open_food_facts(match.group(1).replace(",", "."))
    unit = (match.group(2) or "g").lower()
    return quantity or 100.0, unit


def food_payload_from_inventory_item(
    item: models.InventoryItem,
    product_unit: models.ProductUnit,
) -> dict:
    return {
        "name": item.name,
        "emoji": item.emoji,
        "brand": item.brand,
        "category": item.category,
        "storage_location": item.storage_location,
        "product_group_id": item.product_group_id,
        "product_unit_id": product_unit.id,
        "minimum_quantity": item.minimum_quantity,
        "barcode": item.barcode,
        "purchase_date": item.purchase_date,
        "expiry_days": item.expiry_days,
        "price": item.price,
        "serving_size": item.serving_size,
        "serving_unit": item.serving_unit,
        "calories_per_100g": item.calories_per_100g,
        "protein_per_100g": item.protein_per_100g,
        "carbs_per_100g": item.carbs_per_100g,
        "fat_per_100g": item.fat_per_100g,
    }


def ensure_food_for_inventory_item(
    db: Session,
    item: models.InventoryItem,
) -> models.Food:
    if item.food is not None:
        barcode_service.append_barcodes(db, item.food, [item.barcode] if item.barcode else [])
        return item.food

    product_unit = item.product_unit or crud.get_or_create_product_unit(db, item.unit)
    brand = item.brand.strip() if item.brand else None
    food = crud.get_food_by_name_brand(db, item.name, brand) or models.Food(name=item.name)
    for field, value in food_payload_from_inventory_item(item, product_unit).items():
        if field != "barcode":
            setattr(food, field, value)
    barcode_service.append_barcodes(db, food, [item.barcode] if item.barcode else [])
    db.add(food)
    db.flush()
    item.food_id = food.id
    db.add(item)
    db.flush()
    return food


def open_food_facts_product(barcode: str) -> dict | None:
    best_product: dict | None = None
    best_score = -1
    last_error: Exception | None = None
    barcode_path = quote(barcode, safe="")

    # API v3.5 changed the nutrition structure. These versions expose normalized nutriments.
    for version in ("v2", "v3.4"):
        try:
            # Connect directly with certificate verification. Redirects are treated as errors.
            with closing(HTTPSConnection(OPEN_FOOD_FACTS_HOST, timeout=OPEN_FOOD_FACTS_TIMEOUT_SECONDS)) as connection:
                connection.request(
                    "GET", f"/api/{version}/product/{barcode_path}.json?fields={OPEN_FOOD_FACTS_PRODUCT_FIELDS}",
                    headers={"User-Agent": OPEN_FOOD_FACTS_USER_AGENT, "Accept": "application/json"},
                )
                with connection.getresponse() as response:
                    if response.status == 404:
                        return best_product
                    if response.status != 200:
                        logger.warning("Open Food Facts API %s returned HTTP %s", version, response.status)
                        last_error = HTTPClientError(f"Open Food Facts HTTP {response.status}")
                        if 300 <= response.status < 400 or response.status in {401, 403, 429}:
                            break
                        continue
                    raw = response.read(OPEN_FOOD_FACTS_MAX_RESPONSE_BYTES + 1)
            if len(raw) > OPEN_FOOD_FACTS_MAX_RESPONSE_BYTES:
                raise ValueError("Open Food Facts response is too large")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object from Open Food Facts")
        except (OSError, HTTPClientError, ValueError, RecursionError) as exc:
            logger.warning("Open Food Facts API %s request failed (%s)", version, type(exc).__name__)
            last_error = exc
            if isinstance(exc, (ssl.SSLCertVerificationError, socket.gaierror)):
                break
            continue

        product = payload.get("product")
        if not isinstance(product, dict):
            continue
        score = product_nutrition_score(product)
        if score > best_score:
            best_product = product
            best_score = score
        if score >= 4:
            return product

    if best_product is not None:
        return best_product
    if last_error is not None:
        raise HTTPException(
            status_code=502,
            detail="EAN-Suche ist momentan nicht erreichbar. Bitte erneut versuchen oder das Lebensmittel manuell anlegen.",
        ) from last_error
    return None


def food_values_from_open_food_facts(barcode: str, product: dict) -> dict:
    nutriments = product_nutriments(product)
    product_name = (
        product.get("product_name_de")
        or product.get("product_name")
        or product.get("product_name_en")
        or barcode
    )
    brand = product.get("brands")
    category = product.get("categories")
    serving_size, serving_unit = parse_serving_size(product.get("serving_size"))
    calories_per_100g = nutrition_value(
        nutriments,
        "energy-kcal_100g",
        "energy-kcal",
        "energy-kcal_value",
    )
    if calories_per_100g == 0:
        energy_kj = nutrition_value(nutriments, "energy_100g", "energy-kj_100g")
        calories_per_100g = round(energy_kj / 4.184, 2) if energy_kj else 0.0

    return {
        "name": str(product_name),
        "brand": str(brand).strip() if brand else None,
        "category": str(category).split(",")[0].strip() if category else None,
        "barcode": barcode,
        "serving_size": serving_size,
        "serving_unit": serving_unit or "g",
        "calories_per_100g": calories_per_100g,
        "protein_per_100g": nutrition_value(
            nutriments,
            "proteins_100g",
            "proteins",
            "proteins_value",
        ),
        "fat_per_100g": nutrition_value(nutriments, "fat_100g", "fat", "fat_value"),
        "carbs_per_100g": nutrition_value(
            nutriments,
            "carbohydrates_100g",
            "carbohydrates",
            "carbohydrates_value",
        ),
        "fiber_per_100g": 0.0,
        "sugar_per_100g": 0.0,
        "caffeine_mg_per_100g": None,
        **additional_nutrients_from_open_food_facts(product),
    }


def upsert_food_from_open_food_facts(
    db: Session,
    barcode: str,
    product: dict,
) -> models.Food:
    values = food_values_from_open_food_facts(barcode, product)
    product_unit = crud.get_or_create_product_unit(db, "serving")
    food = barcode_service.find_food(db, barcode)
    if food is None:
        food = crud.get_food_by_name_brand(db, values["name"], values["brand"])
    if food is None:
        food = models.Food(name=values["name"])

    food.name = values["name"]
    food.emoji = food.emoji or schemas.DEFAULT_FOOD_EMOJI
    food.brand = values["brand"]
    food.category = values["category"]
    food.product_unit_id = product_unit.id
    food.serving_size = values["serving_size"]
    food.serving_unit = values["serving_unit"]
    food.calories_per_100g = values["calories_per_100g"]
    food.protein_per_100g = values["protein_per_100g"]
    food.fat_per_100g = values["fat_per_100g"]
    food.carbs_per_100g = values["carbs_per_100g"]
    # A missing external value must not erase manually entered information.
    for field, value in additional_nutrients_from_open_food_facts(product).items():
        setattr(food, field, value)
    barcode_service.append_barcodes(db, food, [barcode])
    db.add(food)
    db.flush()
    return food


def fetch_barcode_product(barcode: str) -> tuple[dict | None, HTTPException | None]:
    try:
        return open_food_facts_product(barcode), None
    except HTTPException as exc:
        if exc.status_code != 502:
            raise
        return None, exc


def food_barcode_preview_from_food(
    barcode: str,
    source: str,
    food: models.Food,
) -> dict:
    return {
        "barcode": barcode,
        "source": source,
        "name": food.name,
        "brand": food.brand,
        "category": food.category,
        "serving_size": food.serving_size,
        "serving_unit": food.serving_unit,
        "calories_per_100g": food.calories_per_100g,
        "protein_per_100g": food.protein_per_100g,
        "fat_per_100g": food.fat_per_100g,
        "carbs_per_100g": food.carbs_per_100g,
        "fiber_per_100g": food.fiber_per_100g,
        "sugar_per_100g": food.sugar_per_100g,
        "caffeine_mg_per_100g": food.caffeine_mg_per_100g,
    }


def food_barcode_preview_from_inventory_item(
    barcode: str,
    item: models.InventoryItem,
) -> dict:
    return {
        "barcode": barcode,
        "source": "local_inventory",
        "name": item.name,
        "brand": item.brand,
        "category": item.category,
        "serving_size": item.serving_size,
        "serving_unit": item.serving_unit,
        "calories_per_100g": item.calories_per_100g,
        "protein_per_100g": item.protein_per_100g,
        "fat_per_100g": item.fat_per_100g,
        "carbs_per_100g": item.carbs_per_100g,
    }


def food_barcode_preview_from_open_food_facts(
    barcode: str,
    product: dict,
) -> dict:
    return {
        "source": "open_food_facts",
        **food_values_from_open_food_facts(barcode, product),
    }


def inventory_item_by_barcode(db: Session, barcode: str) -> models.InventoryItem | None:
    return (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.barcode == barcode)
        .order_by(models.InventoryItem.id)
        .first()
    )


def local_barcode_match(db: Session, barcode: str) -> tuple[models.Food | None, models.InventoryItem | None]:
    food = barcode_service.find_food(db, barcode)
    return food, None if food is not None else inventory_item_by_barcode(db, barcode)


def save_barcode_lookup(
    db: Session,
    barcode: str,
    food: models.Food | None,
    item: models.InventoryItem | None,
    product: dict | None = None,
) -> schemas.FoodBarcodeLookupRead:
    source = "local_food"
    if food is not None:
        barcode_service.append_barcodes(db, food, [barcode])
    elif item is not None:
        food = ensure_food_for_inventory_item(db, item)
        source = "local_inventory"

    if product is not None and (food is None or not food_has_nutrition(food)):
        food = upsert_food_from_open_food_facts(db, barcode, product)
        source = "open_food_facts"
    if food is None:
        raise HTTPException(status_code=404, detail="Zu diesem EAN-Code wurde kein Lebensmittel gefunden. Bitte den Code pruefen oder das Lebensmittel manuell anlegen.")

    db.commit()
    inventory_items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.food_id == food.id)
        .order_by(models.InventoryItem.id)
        .all()
    )
    return schemas.FoodBarcodeLookupRead.model_validate({
        "barcode": barcode, "source": source, "food": food, "inventory_items": inventory_items,
    })


@router.post("", response_model=schemas.FoodRead, status_code=status.HTTP_201_CREATED)
def create_food(food_in: schemas.FoodCreate, db: Session = Depends(get_db)):
    validate_food_references(db, food_in.product_group_id, food_in.product_unit_id)
    try:
        data = food_in.model_dump(exclude={"conversions", "barcode", "barcodes"})
        if not {"serving_size", "serving_unit"}.intersection(food_in.model_fields_set):
            data.pop("serving_size")
            data.pop("serving_unit")
        data = apply_product_unit_defaults(db, data)
        food = models.Food(**data)
        barcode_service.apply_input(db, food, food_in)
        replace_food_conversions(db, food, food_in.conversions)
        db.add(food)
        db.commit()
        db.refresh(food)
        return food
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Food already exists or is invalid") from exc
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[schemas.FoodRead])
def list_foods(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(models.Food)
    if not include_archived:
        query = query.filter(models.Food.is_archived.is_(False))
    return query.order_by(models.Food.id).offset(skip).limit(limit).all()


@router.get("/barcode/{barcode}/preview", response_model=schemas.FoodBarcodePreviewRead)
def preview_food_by_barcode(barcode: str):
    normalized_barcode = normalize_barcode(barcode)
    with barcode_db_session() as db:
        local_food = barcode_service.find_food(db, normalized_barcode)
        if local_food is not None and food_has_nutrition(local_food):
            return food_barcode_preview_from_food(normalized_barcode, "local_food", local_food)

    product, lookup_error = fetch_barcode_product(normalized_barcode)
    with barcode_db_session() as db:
        local_food = barcode_service.find_food(db, normalized_barcode)
        if local_food is not None and food_has_nutrition(local_food):
            return food_barcode_preview_from_food(normalized_barcode, "local_food", local_food)
        if lookup_error is not None:
            raise lookup_error
        if product is not None and product_has_nutrition(product):
            return food_barcode_preview_from_open_food_facts(normalized_barcode, product)
        if local_food is not None:
            return food_barcode_preview_from_food(normalized_barcode, "local_food", local_food)
        item = inventory_item_by_barcode(db, normalized_barcode)
        if item is not None:
            return food_barcode_preview_from_inventory_item(normalized_barcode, item)

    if product is None:
        raise HTTPException(status_code=404, detail="Zu diesem EAN-Code wurde kein Lebensmittel gefunden. Bitte den Code pruefen oder das Lebensmittel manuell anlegen.")
    return food_barcode_preview_from_open_food_facts(normalized_barcode, product)


@router.post("/barcode/{barcode}", response_model=schemas.FoodBarcodeLookupRead)
def lookup_food_by_barcode(barcode: str) -> schemas.FoodBarcodeLookupRead:
    normalized_barcode = normalize_barcode(barcode)
    with barcode_db_session() as db:
        food, item = local_barcode_match(db, normalized_barcode)
        candidate = (item.food or item) if item is not None else food
        if candidate is not None and food_has_nutrition(candidate):
            return save_barcode_lookup(db, normalized_barcode, food, item)

    product, lookup_error = fetch_barcode_product(normalized_barcode)
    # Another request or a database restore may have changed the local match during the fetch.
    with barcode_db_session() as db:
        food, item = local_barcode_match(db, normalized_barcode)
        if lookup_error is not None and food is None and item is None:
            raise lookup_error
        return save_barcode_lookup(db, normalized_barcode, food, item, product)


@router.get("/{food_id}", response_model=schemas.FoodRead)
def read_food(food_id: int, db: Session = Depends(get_db)):
    return get_food_or_404(db, food_id)


@router.patch("/{food_id}", response_model=schemas.FoodRead)
def update_food(food_id: int, food_in: schemas.FoodUpdate, db: Session = Depends(get_db)):
    food = get_food_or_404(db, food_id)
    patch = food_in.model_dump(exclude_unset=True, exclude={"conversions", "barcode", "barcodes"})
    validate_food_references(
        db,
        patch.get("product_group_id"),
        patch.get("product_unit_id"),
    )
    try:
        for field, value in patch.items():
            setattr(food, field, value)
        barcode_service.apply_input(db, food, food_in)
        replace_food_conversions(db, food, food_in.conversions)
        db.add(food)
        db.commit()
        db.refresh(food)
        return food
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Food could not be updated") from exc
    except Exception:
        db.rollback()
        raise


@router.delete("/{food_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_food(
    food_id: int,
    keep_reference: bool = Query(False),
    db: Session = Depends(get_db),
):
    food = get_food_or_404(db, food_id)
    if keep_reference:
        food.is_archived = True
        db.add(food)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        crud.delete(db, food)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Food is still referenced. Use keep_reference=true to archive it.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
