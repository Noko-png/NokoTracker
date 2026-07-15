from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db


router = APIRouter(prefix="/shopping-list", tags=["shopping-list"])


def get_item_or_404(db: Session, item_id: int) -> models.ShoppingListItem:
    item = crud.get(db, models.ShoppingListItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Shopping list item not found")
    return item


def ensure_food_exists(db: Session, food_id: int | None) -> None:
    if food_id is not None and crud.get(db, models.Food, food_id) is None:
        raise HTTPException(status_code=404, detail="Food not found")


def ensure_inventory_item_exists(db: Session, inventory_item_id: int | None) -> None:
    if inventory_item_id is not None and crud.get(db, models.InventoryItem, inventory_item_id) is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")


def validate_references(db: Session, item_in: schemas.ShoppingListItemBase) -> None:
    ensure_food_exists(db, item_in.food_id)
    ensure_inventory_item_exists(db, item_in.inventory_item_id)


def shopping_unit_for_food(food: models.Food) -> str:
    if food.product_unit is not None:
        return food.product_unit.name
    return food.serving_unit or "pcs"


def normalize_shopping_item_for_food(
    db: Session,
    item_in: schemas.ShoppingListItemCreate,
) -> schemas.ShoppingListItemCreate:
    if item_in.food_id is None:
        return item_in

    food = crud.get(db, models.Food, item_in.food_id)
    if food is None:
        return item_in

    return item_in.model_copy(
        update={
            "name": food.name,
            "unit": shopping_unit_for_food(food),
        }
    )


def normalized_quantity(value: float) -> float:
    return schemas.normalize_fractional_number(value)


def normalized_unit(value: str) -> str:
    return value.strip().lower()


def merge_shopping_item_quantity(
    shopping_item: models.ShoppingListItem,
    quantity: float,
    priority: int = 0,
    notes: str | None = None,
) -> models.ShoppingListItem:
    shopping_item.quantity = normalized_quantity(
        normalized_quantity(shopping_item.quantity) + normalized_quantity(quantity)
    )
    shopping_item.priority = max(shopping_item.priority, priority)
    if notes:
        if not shopping_item.notes:
            shopping_item.notes = notes
        elif notes not in shopping_item.notes:
            shopping_item.notes = f"{shopping_item.notes}; {notes}"
    return shopping_item


def fill_shopping_item_references(
    shopping_item: models.ShoppingListItem,
    food_id: int | None,
    inventory_item_id: int | None,
    store: str | None = None,
) -> models.ShoppingListItem:
    if shopping_item.food_id is None and food_id is not None:
        shopping_item.food_id = food_id
    if shopping_item.inventory_item_id is None and inventory_item_id is not None:
        shopping_item.inventory_item_id = inventory_item_id
    if shopping_item.store is None and store:
        shopping_item.store = store
    return shopping_item


def open_duplicate_for_shopping_item(
    db: Session,
    item_in: schemas.ShoppingListItemCreate,
) -> models.ShoppingListItem | None:
    filters = [func.lower(models.ShoppingListItem.name) == item_in.name.lower()]
    if item_in.food_id is not None:
        filters.append(models.ShoppingListItem.food_id == item_in.food_id)
    if item_in.inventory_item_id is not None:
        filters.append(models.ShoppingListItem.inventory_item_id == item_in.inventory_item_id)

    return (
        db.query(models.ShoppingListItem)
        .filter(models.ShoppingListItem.is_checked.is_(False))
        .filter(func.lower(models.ShoppingListItem.unit) == normalized_unit(item_in.unit))
        .filter(or_(*filters))
        .order_by(models.ShoppingListItem.id)
        .first()
    )


def open_duplicate_for_inventory_item(
    db: Session,
    inventory_item: models.InventoryItem,
) -> models.ShoppingListItem | None:
    filters = [models.ShoppingListItem.inventory_item_id == inventory_item.id]
    if inventory_item.food_id is not None:
        filters.append(models.ShoppingListItem.food_id == inventory_item.food_id)
    filters.append(func.lower(models.ShoppingListItem.name) == inventory_item.name.lower())

    return (
        db.query(models.ShoppingListItem)
        .filter(models.ShoppingListItem.is_checked.is_(False))
        .filter(func.lower(models.ShoppingListItem.unit) == normalized_unit(inventory_item.unit))
        .filter(or_(*filters))
        .first()
    )


def quantity_to_buy(inventory_item: models.InventoryItem) -> float:
    missing = normalized_quantity(
        normalized_quantity(inventory_item.minimum_quantity)
        - normalized_quantity(inventory_item.quantity)
    )
    return missing if missing > 0 else 1.0


def default_conversion_for_unit(unit_name: str) -> tuple[float, str]:
    normalized_unit = unit_name.strip().lower()
    if normalized_unit in {"g", "gram", "grams", "gramm"}:
        return 1.0, "g"
    if normalized_unit in {"kg", "kilogram", "kilograms", "kilogramm"}:
        return 1000.0, "g"
    if normalized_unit in {"ml", "milliliter", "milliliters"}:
        return 1.0, "ml"
    if normalized_unit in {"l", "liter", "liters"}:
        return 1000.0, "ml"
    return 100.0, "g"


def food_for_shopping_item(
    db: Session,
    shopping_item: models.ShoppingListItem,
) -> models.Food | None:
    if shopping_item.food is not None:
        return shopping_item.food
    return crud.get_food_by_name_brand(db, shopping_item.name, None)


def apply_default_inventory_values(
    inventory_item: models.InventoryItem,
    food: models.Food | None,
    purchase_date: date,
) -> None:
    inventory_item.purchase_date = purchase_date
    if food is None:
        return

    product_group = food.product_group
    inventory_item.food_id = food.id
    inventory_item.emoji = food.emoji
    inventory_item.brand = food.brand
    inventory_item.category = food.category
    inventory_item.product_group_id = food.product_group_id
    inventory_item.serving_size = food.serving_size
    inventory_item.serving_unit = food.serving_unit
    inventory_item.calories_per_100g = food.calories_per_100g
    inventory_item.protein_per_100g = food.protein_per_100g
    inventory_item.carbs_per_100g = food.carbs_per_100g
    inventory_item.fat_per_100g = food.fat_per_100g
    if inventory_item.storage_location is None:
        inventory_item.storage_location = (
            food.storage_location
            or (product_group.default_storage_location if product_group is not None else None)
        )
    if product_group is not None and product_group.default_expiry_days is not None:
        inventory_item.expiry_days = product_group.default_expiry_days


def matching_inventory_item_for_food(
    db: Session,
    food: models.Food,
    unit: str,
) -> models.InventoryItem | None:
    return (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.food_id == food.id)
        .filter(func.lower(models.InventoryItem.unit) == unit.lower())
        .order_by(models.InventoryItem.id)
        .first()
    )


def create_inventory_item_from_food(
    db: Session,
    food: models.Food,
    shopping_item: models.ShoppingListItem,
    purchase_date: date,
) -> models.InventoryItem:
    product_unit = crud.get_or_create_product_unit(db, shopping_item.unit)
    inventory_item = models.InventoryItem(
        name=food.name,
        quantity=normalized_quantity(shopping_item.quantity),
        unit=product_unit.name,
        minimum_quantity=0.0,
        product_unit_id=product_unit.id,
        notes=f"Aus Einkaufsliste uebernommen: {shopping_item.name}",
    )
    apply_default_inventory_values(inventory_item, food, purchase_date)
    db.add(inventory_item)
    db.flush()
    return inventory_item


def create_food_for_unknown_shopping_item(
    db: Session,
    shopping_item: models.ShoppingListItem,
) -> models.Food:
    product_unit = crud.get_or_create_product_unit(db, shopping_item.unit)
    serving_size, serving_unit = default_conversion_for_unit(product_unit.name)
    food = crud.get_food_by_name_brand(db, shopping_item.name, None)
    if food is None:
        food = models.Food(
            name=shopping_item.name,
            product_unit_id=product_unit.id,
            serving_size=serving_size,
            serving_unit=serving_unit,
        )
        db.add(food)
        db.flush()
    return food


def empty_import_result(message: str) -> dict:
    return {
        "imported_count": 0,
        "created_inventory_items": [],
        "updated_inventory_items": [],
        "deleted_shopping_item_ids": [],
        "kept_shopping_item_ids": [],
        "unknown_items": [],
        "requires_decision": False,
        "message": message,
    }


@router.get("", response_model=list[schemas.ShoppingListItemRead])
def list_shopping_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_checked: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(models.ShoppingListItem)
    if not include_checked:
        query = query.filter(models.ShoppingListItem.is_checked.is_(False))
    return query.offset(skip).limit(limit).all()


@router.post("", response_model=schemas.ShoppingListItemRead, status_code=status.HTTP_201_CREATED)
def create_shopping_item(
    item_in: schemas.ShoppingListItemCreate,
    db: Session = Depends(get_db),
):
    validate_references(db, item_in)
    item_in = normalize_shopping_item_for_food(db, item_in)
    try:
        duplicate = open_duplicate_for_shopping_item(db, item_in)
        if duplicate is not None:
            fill_shopping_item_references(
                duplicate,
                item_in.food_id,
                item_in.inventory_item_id,
                item_in.store,
            )
            merge_shopping_item_quantity(
                duplicate,
                item_in.quantity,
                item_in.priority,
                item_in.notes,
            )
            db.add(duplicate)
            db.commit()
            db.refresh(duplicate)
            return duplicate

        return crud.create(db, models.ShoppingListItem, item_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shopping list item could not be created") from exc


@router.post(
    "/generate-from-low-stock",
    response_model=list[schemas.ShoppingListItemRead],
    status_code=status.HTTP_201_CREATED,
)
def generate_shopping_items_from_low_stock(db: Session = Depends(get_db)):
    low_stock_items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.quantity <= models.InventoryItem.minimum_quantity)
        .all()
    )

    created_items = []
    for inventory_item in low_stock_items:
        if open_duplicate_for_inventory_item(db, inventory_item) is not None:
            continue

        shopping_item = models.ShoppingListItem(
            name=inventory_item.name,
            food_id=inventory_item.food_id,
            inventory_item_id=inventory_item.id,
            quantity=quantity_to_buy(inventory_item),
            unit=inventory_item.unit,
            is_checked=False,
            priority=1,
            notes="Generated from low stock",
        )
        db.add(shopping_item)
        created_items.append(shopping_item)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shopping list items could not be generated") from exc

    for item in created_items:
        db.refresh(item)
    return created_items


@router.post(
    "/import-to-inventory",
    response_model=schemas.ShoppingListInventoryImportResult,
)
def import_shopping_list_to_inventory(
    import_in: schemas.ShoppingListInventoryImportRequest | None = None,
    db: Session = Depends(get_db),
):
    request = import_in or schemas.ShoppingListInventoryImportRequest()
    open_items = (
        db.query(models.ShoppingListItem)
        .filter(models.ShoppingListItem.is_checked.is_(False))
        .order_by(models.ShoppingListItem.id)
        .all()
    )
    if not open_items:
        return empty_import_result("Keine offenen Einkaufsartikel zum Einlagern vorhanden.")

    unknown_items = [
        item
        for item in open_items
        if item.inventory_item is None and food_for_shopping_item(db, item) is None
    ]
    if unknown_items and request.unknown_item_action == "ask":
        return {
            **empty_import_result(
                "Einige Einkaufsartikel existieren noch nicht im System.",
            ),
            "unknown_items": unknown_items,
            "requires_decision": True,
        }

    created_inventory_items: list[models.InventoryItem] = []
    updated_inventory_items: list[models.InventoryItem] = []
    deleted_shopping_item_ids: list[int] = []
    kept_shopping_item_ids: list[int] = []

    try:
        for shopping_item in open_items:
            inventory_item = shopping_item.inventory_item
            food = food_for_shopping_item(db, shopping_item)

            if inventory_item is not None:
                inventory_item.quantity = normalized_quantity(
                    normalized_quantity(inventory_item.quantity)
                    + normalized_quantity(shopping_item.quantity)
                )
                apply_default_inventory_values(
                    inventory_item,
                    food or inventory_item.food,
                    request.purchase_date,
                )
                db.add(inventory_item)
                updated_inventory_items.append(inventory_item)
                deleted_shopping_item_ids.append(shopping_item.id)
                db.delete(shopping_item)
                continue

            if food is not None:
                inventory_item = matching_inventory_item_for_food(
                    db,
                    food,
                    shopping_item.unit,
                )
                if inventory_item is None:
                    inventory_item = create_inventory_item_from_food(
                        db,
                        food,
                        shopping_item,
                        request.purchase_date,
                    )
                    created_inventory_items.append(inventory_item)
                else:
                    inventory_item.quantity = normalized_quantity(
                        normalized_quantity(inventory_item.quantity)
                        + normalized_quantity(shopping_item.quantity)
                    )
                    apply_default_inventory_values(
                        inventory_item,
                        food,
                        request.purchase_date,
                    )
                    db.add(inventory_item)
                    updated_inventory_items.append(inventory_item)

                deleted_shopping_item_ids.append(shopping_item.id)
                db.delete(shopping_item)
                continue

            if request.unknown_item_action == "create":
                food = create_food_for_unknown_shopping_item(db, shopping_item)
                inventory_item = create_inventory_item_from_food(
                    db,
                    food,
                    shopping_item,
                    request.purchase_date,
                )
                created_inventory_items.append(inventory_item)
                deleted_shopping_item_ids.append(shopping_item.id)
                db.delete(shopping_item)
            elif request.unknown_item_action == "delete":
                deleted_shopping_item_ids.append(shopping_item.id)
                db.delete(shopping_item)
            else:
                kept_shopping_item_ids.append(shopping_item.id)

        db.commit()
        for inventory_item in created_inventory_items + updated_inventory_items:
            db.refresh(inventory_item)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Einkaufsliste konnte nicht in den Bestand uebernommen werden",
        ) from exc

    imported_count = len(created_inventory_items) + len(updated_inventory_items)
    if imported_count:
        message = f"{imported_count} Artikel in den Bestand uebernommen."
    elif deleted_shopping_item_ids:
        message = f"{len(deleted_shopping_item_ids)} Artikel von der Einkaufsliste geloescht."
    elif kept_shopping_item_ids:
        message = f"{len(kept_shopping_item_ids)} Artikel bleiben auf der Einkaufsliste."
    else:
        message = "Keine Artikel in den Bestand uebernommen."

    return {
        "imported_count": imported_count,
        "created_inventory_items": created_inventory_items,
        "updated_inventory_items": updated_inventory_items,
        "deleted_shopping_item_ids": deleted_shopping_item_ids,
        "kept_shopping_item_ids": kept_shopping_item_ids,
        "unknown_items": [],
        "requires_decision": False,
        "message": message,
    }


@router.post(
    "/from-inventory/{inventory_item_id}",
    response_model=schemas.ShoppingListItemRead,
    status_code=status.HTTP_201_CREATED,
)
def add_inventory_item_to_shopping_list(
    inventory_item_id: int,
    item_in: schemas.ShoppingListInventoryItemCreate,
    db: Session = Depends(get_db),
):
    inventory_item = crud.get(db, models.InventoryItem, inventory_item_id)
    if inventory_item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    quantity = (
        normalized_quantity(item_in.quantity)
        if item_in.quantity is not None
        else quantity_to_buy(inventory_item)
    )
    duplicate = open_duplicate_for_inventory_item(db, inventory_item)
    if duplicate is not None:
        fill_shopping_item_references(
            duplicate,
            inventory_item.food_id,
            inventory_item.id,
        )
        merge_shopping_item_quantity(
            duplicate,
            quantity,
            item_in.priority,
            item_in.notes,
        )
        db.add(duplicate)
        db.commit()
        db.refresh(duplicate)
        return duplicate

    shopping_item = models.ShoppingListItem(
        name=inventory_item.name,
        food_id=inventory_item.food_id,
        inventory_item_id=inventory_item.id,
        quantity=normalized_quantity(quantity),
        unit=inventory_item.unit,
        is_checked=False,
        priority=item_in.priority,
        notes=item_in.notes or "Aus Bestandsartikel hinzugefuegt",
    )
    try:
        db.add(shopping_item)
        db.commit()
        db.refresh(shopping_item)
        return shopping_item
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shopping list item could not be created") from exc


@router.put("/{item_id}", response_model=schemas.ShoppingListItemRead)
def replace_shopping_item(
    item_id: int,
    item_in: schemas.ShoppingListItemCreate,
    db: Session = Depends(get_db),
):
    item = get_item_or_404(db, item_id)
    validate_references(db, item_in)
    item_in = normalize_shopping_item_for_food(db, item_in)
    try:
        return crud.update(db, item, item_in)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shopping list item could not be updated") from exc


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_item(item_id: int, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    crud.delete(db, item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{item_id}/check", response_model=schemas.ShoppingListItemRead)
def check_shopping_item(item_id: int, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    item.is_checked = True
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/uncheck", response_model=schemas.ShoppingListItemRead)
def uncheck_shopping_item(item_id: int, db: Session = Depends(get_db)):
    item = get_item_or_404(db, item_id)
    item.is_checked = False
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
