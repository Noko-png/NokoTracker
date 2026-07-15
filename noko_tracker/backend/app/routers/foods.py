import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/foods", tags=["foods"])

OPEN_FOOD_FACTS_USER_AGENT = "HeimERP/0.1 (local calorie tracker)"
OPEN_FOOD_FACTS_TIMEOUT_SECONDS = 6
OPEN_FOOD_FACTS_PRODUCT_URLS = (
    "https://world.openfoodfacts.org/api/v3.6/product/{barcode}.json",
    "https://world.openfoodfacts.org/api/v2/product/{barcode}.json",
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
    food: models.Food,
    conversions: list[schemas.FoodConversionCreate] | None,
) -> None:
    if conversions is None:
        return

    food.conversions.clear()
    for conversion in normalized_conversion_payload(conversions):
        food.conversions.append(models.FoodConversion(**conversion))


def normalize_barcode(value: str) -> str:
    normalized = re.sub(r"\D", "", value or "")
    if len(normalized) < 8:
        raise HTTPException(status_code=422, detail="Barcode is too short")
    return normalized


def number_from_open_food_facts(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        return max(float(value), 0.0)
    except (TypeError, ValueError):
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


def food_has_nutrition(food: models.Food) -> bool:
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
    if not value:
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
        return item.food

    product_unit = item.product_unit or crud.get_or_create_product_unit(db, item.unit)
    brand = item.brand.strip() if item.brand else None
    food = crud.get_food_by_name_brand(db, item.name, brand) or models.Food(name=item.name)
    for field, value in food_payload_from_inventory_item(item, product_unit).items():
        setattr(food, field, value)
    db.add(food)
    db.flush()
    item.food_id = food.id
    db.add(item)
    db.flush()
    return food


def open_food_facts_product(barcode: str) -> dict | None:
    best_product: dict | None = None
    best_score = -1
    barcode_path = quote(barcode)

    for url_template in OPEN_FOOD_FACTS_PRODUCT_URLS:
        url = url_template.format(barcode=barcode_path)
        request = Request(url, headers={"User-Agent": OPEN_FOOD_FACTS_USER_AGENT})
        try:
            with urlopen(request, timeout=OPEN_FOOD_FACTS_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise HTTPException(status_code=502, detail="Barcode lookup failed") from exc
        except (TimeoutError, URLError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail="Barcode lookup failed") from exc

        product = payload.get("product")
        if not isinstance(product, dict):
            continue
        score = product_nutrition_score(product)
        if score > best_score:
            best_product = product
            best_score = score
        if score >= 4:
            return product

    return best_product


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
    }


def upsert_food_from_open_food_facts(
    db: Session,
    barcode: str,
    product: dict,
) -> models.Food:
    values = food_values_from_open_food_facts(barcode, product)
    product_unit = crud.get_or_create_product_unit(db, "serving")
    food = (
        db.query(models.Food)
        .filter(models.Food.barcode == barcode)
        .filter(models.Food.is_archived.is_(False))
        .first()
    )
    if food is None:
        food = crud.get_food_by_name_brand(db, values["name"], values["brand"])
    if food is None:
        food = models.Food(name=values["name"])

    food.name = values["name"]
    food.emoji = food.emoji or schemas.DEFAULT_FOOD_EMOJI
    food.brand = values["brand"]
    food.category = values["category"]
    food.barcode = barcode
    food.product_unit_id = product_unit.id
    food.serving_size = values["serving_size"]
    food.serving_unit = values["serving_unit"]
    food.calories_per_100g = values["calories_per_100g"]
    food.protein_per_100g = values["protein_per_100g"]
    food.fat_per_100g = values["fat_per_100g"]
    food.carbs_per_100g = values["carbs_per_100g"]
    db.add(food)
    db.flush()
    return food


def refresh_food_from_open_food_facts(
    db: Session,
    barcode: str,
) -> models.Food | None:
    try:
        product = open_food_facts_product(barcode)
    except HTTPException as exc:
        if exc.status_code == 502:
            return None
        raise
    if product is None:
        return None
    return upsert_food_from_open_food_facts(db, barcode, product)


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


def barcode_lookup_response(
    barcode: str,
    source: str,
    food: models.Food,
    inventory_items: list[models.InventoryItem],
) -> dict:
    return {
        "barcode": barcode,
        "source": source,
        "food": food,
        "inventory_items": inventory_items,
    }


@router.post("", response_model=schemas.FoodRead, status_code=status.HTTP_201_CREATED)
def create_food(food_in: schemas.FoodCreate, db: Session = Depends(get_db)):
    validate_food_references(db, food_in.product_group_id, food_in.product_unit_id)
    try:
        data = food_in.model_dump(exclude={"conversions"})
        food = models.Food(**data)
        replace_food_conversions(food, food_in.conversions)
        db.add(food)
        db.commit()
        db.refresh(food)
        return food
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Food already exists or is invalid") from exc


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
    return query.offset(skip).limit(limit).all()


@router.get("/barcode/{barcode}/preview", response_model=schemas.FoodBarcodePreviewRead)
def preview_food_by_barcode(barcode: str, db: Session = Depends(get_db)):
    normalized_barcode = normalize_barcode(barcode)
    local_food = (
        db.query(models.Food)
        .filter(models.Food.barcode == normalized_barcode)
        .filter(models.Food.is_archived.is_(False))
        .first()
    )
    if local_food is not None and food_has_nutrition(local_food):
        return food_barcode_preview_from_food(
            normalized_barcode,
            "local_food",
            local_food,
        )

    product = open_food_facts_product(normalized_barcode)
    if product is not None and product_has_nutrition(product):
        return food_barcode_preview_from_open_food_facts(normalized_barcode, product)

    if local_food is not None:
        return food_barcode_preview_from_food(
            normalized_barcode,
            "local_food",
            local_food,
        )

    inventory_item = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.barcode == normalized_barcode)
        .order_by(models.InventoryItem.id)
        .first()
    )
    if inventory_item is not None:
        return food_barcode_preview_from_inventory_item(
            normalized_barcode,
            inventory_item,
        )

    if product is None:
        raise HTTPException(status_code=404, detail="Barcode not found")
    return food_barcode_preview_from_open_food_facts(normalized_barcode, product)


@router.get("/barcode/{barcode}", response_model=schemas.FoodBarcodeLookupRead)
def lookup_food_by_barcode(barcode: str, db: Session = Depends(get_db)):
    normalized_barcode = normalize_barcode(barcode)
    local_food = (
        db.query(models.Food)
        .filter(models.Food.barcode == normalized_barcode)
        .filter(models.Food.is_archived.is_(False))
        .first()
    )
    matching_inventory = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.barcode == normalized_barcode)
        .order_by(models.InventoryItem.id)
        .all()
    )
    if local_food is not None:
        source = "local_food"
        if not food_has_nutrition(local_food):
            refreshed_food = refresh_food_from_open_food_facts(db, normalized_barcode)
            if refreshed_food is not None:
                db.commit()
                db.refresh(refreshed_food)
                local_food = refreshed_food
                source = "open_food_facts"
        if not matching_inventory:
            matching_inventory = (
                db.query(models.InventoryItem)
                .filter(models.InventoryItem.food_id == local_food.id)
                .order_by(models.InventoryItem.id)
                .all()
            )
        return barcode_lookup_response(
            normalized_barcode,
            source,
            local_food,
            matching_inventory,
        )

    if matching_inventory:
        food = ensure_food_for_inventory_item(db, matching_inventory[0])
        source = "local_inventory"
        if not food_has_nutrition(food):
            refreshed_food = refresh_food_from_open_food_facts(db, normalized_barcode)
            if refreshed_food is not None:
                food = refreshed_food
                source = "open_food_facts"
        db.commit()
        db.refresh(food)
        return barcode_lookup_response(
            normalized_barcode,
            source,
            food,
            matching_inventory,
        )

    product = open_food_facts_product(normalized_barcode)
    if product is None:
        raise HTTPException(status_code=404, detail="Barcode not found")

    food = upsert_food_from_open_food_facts(db, normalized_barcode, product)
    db.commit()
    db.refresh(food)
    return barcode_lookup_response(
        normalized_barcode,
        "open_food_facts",
        food,
        [],
    )


@router.get("/{food_id}", response_model=schemas.FoodRead)
def read_food(food_id: int, db: Session = Depends(get_db)):
    return get_food_or_404(db, food_id)


@router.patch("/{food_id}", response_model=schemas.FoodRead)
def update_food(food_id: int, food_in: schemas.FoodUpdate, db: Session = Depends(get_db)):
    food = get_food_or_404(db, food_id)
    patch = food_in.model_dump(exclude_unset=True)
    validate_food_references(
        db,
        patch.get("product_group_id"),
        patch.get("product_unit_id"),
    )
    try:
        conversions = patch.pop("conversions", None)
        for field, value in patch.items():
            setattr(food, field, value)
        replace_food_conversions(food, conversions)
        db.add(food)
        db.commit()
        db.refresh(food)
        return food
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Food could not be updated") from exc


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
