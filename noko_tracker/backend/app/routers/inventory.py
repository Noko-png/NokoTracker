from datetime import date, timedelta, timezone
import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..services import barcode_service
from ..services.food_inventory import apply_food_inventory_values
from ..services.inventory_stock import add_or_merge_inventory
from ..services.unit_defaults import apply_product_unit_defaults


router = APIRouter(prefix="/inventory", tags=["inventory"])


def get_item_or_404(db: Session, item_id: int) -> models.InventoryItem:
    item = crud.get(db, models.InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    return item


def ensure_product_group_exists(db: Session, product_group_id: int | None) -> None:
    if product_group_id is None:
        return

    if crud.get(db, models.ProductGroup, product_group_id) is None:
        raise HTTPException(status_code=404, detail="Product group not found")


def ensure_product_unit_exists(db: Session, product_unit_id: int | None) -> None:
    if product_unit_id is None:
        return

    if crud.get(db, models.ProductUnit, product_unit_id) is None:
        raise HTTPException(status_code=404, detail="Product unit not found")


def normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def resolve_product_unit(
    db: Session,
    item_in: schemas.InventoryItemCreate,
) -> models.ProductUnit:
    if item_in.product_unit_id is not None:
        product_unit = crud.get(db, models.ProductUnit, item_in.product_unit_id)
        if product_unit is None:
            raise HTTPException(status_code=404, detail="Product unit not found")
        return product_unit

    return crud.get_or_create_product_unit(db, item_in.unit)


def inventory_payload_with_food(
    db: Session,
    item_in: schemas.InventoryItemCreate,
    *,
    use_unit_defaults: bool = False,
    existing_item: models.InventoryItem | None = None,
) -> dict:
    payload = item_in.model_dump(exclude={"expected_updated_at"})
    payload["barcode"] = barcode_service.normalize_barcode(item_in.barcode) if item_in.barcode and item_in.barcode.strip() else None
    codes = [payload["barcode"]] if payload["barcode"] else []
    brand = normalized_text(item_in.brand)
    category = normalized_text(item_in.category)

    food = (
        crud.get(db, models.Food, item_in.food_id)
        if item_in.food_id is not None
        else crud.get_food_by_name_brand(db, item_in.name, brand)
    )
    if item_in.food_id is not None and food is None:
        raise HTTPException(status_code=404, detail="Food not found")
    if food is not None:
        if "unit" not in item_in.model_fields_set:
            payload.pop("unit")
        payload = apply_food_inventory_values(db, food, payload, existing_item)
        barcode_service.append_barcodes(db, food, codes)
        return payload

    product_unit = resolve_product_unit(db, item_in)
    if use_unit_defaults:
        conversion = item_in.model_dump(include={"serving_size", "serving_unit"}, exclude_unset=True)
        conversion["product_unit_id"] = product_unit.id
        payload.update(apply_product_unit_defaults(db, conversion))

    food = models.Food(
        name=item_in.name, brand=brand, category=category,
        product_group_id=item_in.product_group_id, product_unit_id=product_unit.id,
        minimum_quantity=item_in.minimum_quantity,
        purchase_date=item_in.purchase_date, expiry_days=item_in.expiry_days, price=item_in.price,
        serving_size=payload["serving_size"], serving_unit=payload["serving_unit"],
        calories_per_100g=item_in.calories_per_100g, protein_per_100g=item_in.protein_per_100g,
        carbs_per_100g=item_in.carbs_per_100g, fat_per_100g=item_in.fat_per_100g,
    )
    db.add(food)
    barcode_service.append_barcodes(db, food, codes)
    db.flush()

    payload["brand"] = brand
    payload["category"] = category
    payload["unit"] = product_unit.name
    payload["food_id"] = food.id
    payload["product_unit_id"] = product_unit.id
    return payload


def apply_inventory_payload(item: models.InventoryItem, payload: dict) -> models.InventoryItem:
    for field, value in payload.items():
        setattr(item, field, value)
    return item


def normalized_quantity(value: float) -> float:
    return schemas.normalize_fractional_number(value)


def low_stock_query(db: Session):
    return db.query(models.InventoryItem).filter(
        models.InventoryItem.quantity <= models.InventoryItem.minimum_quantity
    )


def expiring_soon_query(db: Session, days: int):
    today = date.today()
    until = today + timedelta(days=days)
    return [
        item
        for item in db.query(models.InventoryItem)
        .filter(models.InventoryItem.expiry_days.is_not(None))
        .all()
        if item.expiry_date is not None and today <= item.expiry_date <= until
    ]


def expired_query(db: Session):
    today = date.today()
    return [
        item
        for item in db.query(models.InventoryItem)
        .filter(models.InventoryItem.expiry_days.is_not(None))
        .all()
        if item.expiry_date is not None and item.expiry_date < today
    ]


@router.get("", response_model=list[schemas.InventoryItemRead])
def list_inventory_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.InventoryItem, skip=skip, limit=limit)


@router.get("/low-stock", response_model=list[schemas.InventoryItemRead])
def list_low_stock_items(db: Session = Depends(get_db)):
    return low_stock_query(db).all()


@router.get("/expiring-soon", response_model=list[schemas.InventoryItemRead])
def list_expiring_soon_items(
    days: int = Query(7, ge=0, le=3650),
    db: Session = Depends(get_db),
):
    return expiring_soon_query(db, days)


@router.get("/expired", response_model=list[schemas.InventoryItemRead])
def list_expired_items(db: Session = Depends(get_db)):
    return expired_query(db)


@router.get("/warnings", response_model=schemas.InventoryWarningsRead)
def read_inventory_warnings(
    days: int = Query(7, ge=0, le=3650),
    db: Session = Depends(get_db),
):
    return {
        "low_stock": low_stock_query(db).all(),
        "expiring_soon": expiring_soon_query(db, days),
        "expired": expired_query(db),
    }


@router.get("/{item_id}", response_model=schemas.InventoryItemRead)
def read_inventory_item(item_id: int, db: Session = Depends(get_db)):
    return get_item_or_404(db, item_id)


@router.post("", response_model=schemas.InventoryItemRead, status_code=status.HTTP_201_CREATED)
def create_inventory_item(item_in: schemas.InventoryItemCreate, db: Session = Depends(get_db)):
    ensure_product_group_exists(db, item_in.product_group_id)
    ensure_product_unit_exists(db, item_in.product_unit_id)
    try:
        item = models.InventoryItem(**inventory_payload_with_food(db, item_in, use_unit_defaults=True))
        item, _created = add_or_merge_inventory(db, item)
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Inventory item could not be created") from exc
    except Exception:
        db.rollback()
        raise


@router.put("/{item_id}", response_model=schemas.InventoryItemRead)
def replace_inventory_item(
    item_id: int,
    item_in: schemas.InventoryItemReplace,
    db: Session = Depends(get_db),
):
    item = get_item_or_404(db, item_id)
    def utc_naive(value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if utc_naive(item.updated_at) != utc_naive(item_in.expected_updated_at):
        raise HTTPException(409, "Der Bestand wurde inzwischen geaendert. Bitte neu laden und den Eintrag erneut bearbeiten.")

    ensure_product_group_exists(db, item_in.product_group_id)
    ensure_product_unit_exists(db, item_in.product_unit_id)
    try:
        apply_inventory_payload(item, inventory_payload_with_food(db, item_in, existing_item=item))
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Inventory item could not be updated") from exc
    except Exception:
        db.rollback()
        raise


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(item_id: int, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    crud.delete(db, item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{item_id}/increase", response_model=schemas.InventoryItemRead)
def increase_inventory_item(
    item_id: int,
    change: schemas.InventoryQuantityChange,
    db: Session = Depends(get_db),
):
    item = get_item_or_404(db, item_id)
    quantity = normalized_quantity(
        normalized_quantity(item.quantity) + normalized_quantity(change.amount)
    )
    if not math.isfinite(quantity):
        raise HTTPException(422, "Die Bestandsmenge ist zu gross.")
    item.quantity = quantity
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/decrease", response_model=schemas.InventoryItemRead)
def decrease_inventory_item(
    item_id: int,
    change: schemas.InventoryQuantityChange,
    db: Session = Depends(get_db),
):
    item = get_item_or_404(db, item_id)
    next_quantity = normalized_quantity(
        normalized_quantity(item.quantity) - normalized_quantity(change.amount)
    )
    if next_quantity < 0 and abs(next_quantity) <= 0.000001:
        next_quantity = 0.0
    if next_quantity < 0:
        raise HTTPException(status_code=422, detail="Quantity cannot fall below 0")

    item.quantity = next_quantity
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
