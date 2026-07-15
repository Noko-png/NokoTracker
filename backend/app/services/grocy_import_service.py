from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import crud, models, schemas


DEFAULT_GROCY_CSV_DIRECTORY = r"u:\Nico\Desktop\db"

SENSITIVE_OR_UNSUPPORTED_FILES = {
    "api_keys.csv",
    "sessions.csv",
    "migrations.csv",
    "permission_hierarchy.csv",
    "permission_tree.csv",
    "user_permissions.csv",
    "user_permissions_resolved.csv",
    "uihelper_user_permissions.csv",
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _int(value: Any) -> int | None:
    value = _text(value)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _float(value: Any, default: float = 0.0) -> float:
    value = _text(value)
    if value is None:
        return default
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return default


def _quantity(value: Any, default: float = 0.0) -> float:
    return schemas.normalize_fractional_number(_float(value, default))


def _bool(value: Any) -> bool:
    return _text(value) in {"1", "true", "True", "yes", "Ja", "ja"}


def _date(value: Any) -> date | None:
    value = _text(value)
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    if parsed.year >= 2800:
        return None
    return parsed


def _clean_html(value: Any) -> str | None:
    value = _text(value)
    if value is None:
        return None
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", without_tags).strip() or None


def _rows(directory: Path, filename: str, warnings: list[str]) -> list[dict[str, str]]:
    path = directory / filename
    if not path.exists():
        warnings.append(f"{filename} nicht gefunden")
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _counter() -> dict[str, int]:
    return {"created": 0, "updated": 0, "skipped": 0}


def _named_lookup(db: Session, model: type[models.Base], name: str):
    exact_match = db.query(model).filter(model.name == name).first()
    if exact_match is not None:
        return exact_match

    return (
        db.query(model)
        .filter(func.lower(model.name) == name.lower())
        .first()
    )


def _ensure_unit(
    db: Session,
    name: str,
    counters: dict[str, dict[str, int]],
) -> models.ProductUnit:
    unit = crud.get_product_unit_by_name(db, name)
    if unit is None:
        unit = models.ProductUnit(name=name)
        db.add(unit)
        db.flush()
        counters["quantity_units"]["created"] += 1
    return unit


def _barcode_by_product(directory: Path, warnings: list[str]) -> dict[int, str]:
    barcodes: dict[int, str] = {}
    for row in _rows(directory, "product_barcodes.csv", warnings):
        product_id = _int(row.get("product_id"))
        barcode = _text(row.get("barcode"))
        if product_id is not None and barcode and product_id not in barcodes:
            barcodes[product_id] = barcode
    return barcodes


def import_grocy_csv_directory(
    db: Session,
    directory: str = DEFAULT_GROCY_CSV_DIRECTORY,
    dry_run: bool = False,
) -> dict[str, Any]:
    csv_directory = Path(directory)
    if not csv_directory.exists() or not csv_directory.is_dir():
        raise FileNotFoundError(f"CSV-Verzeichnis nicht gefunden: {csv_directory}")

    counters = {
        "users": _counter(),
        "product_groups": _counter(),
        "quantity_units": _counter(),
        "storage_locations": _counter(),
        "foods": _counter(),
        "inventory_items": _counter(),
        "recipes": _counter(),
        "recipe_ingredients": _counter(),
        "shopping_list_items": _counter(),
        "calendar_tasks": _counter(),
    }
    warnings: list[str] = []
    today = date.today()

    user_by_grocy_id: dict[int, models.User] = {}
    for row in _rows(csv_directory, "users.csv", warnings):
        username = _text(row.get("username"))
        grocy_id = _int(row.get("id"))
        if username is None or grocy_id is None:
            counters["users"]["skipped"] += 1
            continue

        user = crud.get_user_by_username(db, username)
        if user is None:
            user = models.User(
                username=username,
                password=_text(row.get("password")) or "imported-user",
            )
            db.add(user)
            db.flush()
            counters["users"]["created"] += 1
        else:
            counters["users"]["updated"] += 1
        user_by_grocy_id[grocy_id] = user

    group_by_grocy_id: dict[int, models.ProductGroup] = {}
    for row in _rows(csv_directory, "product_groups.csv", warnings):
        if "active" in row and not _bool(row.get("active")):
            counters["product_groups"]["skipped"] += 1
            continue
        name = _text(row.get("name"))
        grocy_id = _int(row.get("id"))
        if name is None or grocy_id is None:
            counters["product_groups"]["skipped"] += 1
            continue

        group = _named_lookup(db, models.ProductGroup, name)
        if group is None:
            group = models.ProductGroup(name=name)
            db.add(group)
            db.flush()
            counters["product_groups"]["created"] += 1
        else:
            counters["product_groups"]["updated"] += 1
        group_by_grocy_id[grocy_id] = group

    unit_by_grocy_id: dict[int, models.ProductUnit] = {}
    for row in _rows(csv_directory, "quantity_units.csv", warnings):
        if "active" in row and not _bool(row.get("active")):
            counters["quantity_units"]["skipped"] += 1
            continue
        name = _text(row.get("name"))
        grocy_id = _int(row.get("id"))
        if name is None or grocy_id is None:
            counters["quantity_units"]["skipped"] += 1
            continue
        unit_by_grocy_id[grocy_id] = _ensure_unit(db, name, counters)

    location_by_grocy_id: dict[int, models.StorageLocation] = {}
    for row in _rows(csv_directory, "locations.csv", warnings):
        if "active" in row and not _bool(row.get("active")):
            counters["storage_locations"]["skipped"] += 1
            continue
        name = _text(row.get("name"))
        grocy_id = _int(row.get("id"))
        if name is None or grocy_id is None:
            counters["storage_locations"]["skipped"] += 1
            continue

        location = _named_lookup(db, models.StorageLocation, name)
        if location is None:
            location = models.StorageLocation(name=name)
            db.add(location)
            db.flush()
            counters["storage_locations"]["created"] += 1
        else:
            counters["storage_locations"]["updated"] += 1
        location_by_grocy_id[grocy_id] = location

    barcode_by_product = _barcode_by_product(csv_directory, warnings)
    food_by_grocy_id: dict[int, models.Food] = {}
    product_rows = _rows(csv_directory, "products.csv", warnings)
    for row in product_rows:
        if "active" in row and not _bool(row.get("active")):
            counters["foods"]["skipped"] += 1
            continue
        name = _text(row.get("name"))
        grocy_id = _int(row.get("id"))
        if name is None or grocy_id is None:
            counters["foods"]["skipped"] += 1
            continue

        group = group_by_grocy_id.get(_int(row.get("product_group_id")) or -1)
        unit = unit_by_grocy_id.get(
            _int(row.get("qu_id_stock")) or _int(row.get("qu_id_purchase")) or -1,
        )
        location = location_by_grocy_id.get(_int(row.get("location_id")) or -1)
        food = crud.get_food_by_name_brand(db, name, None)
        if food is None:
            food = models.Food(name=name, brand=None)
            db.add(food)
            counters["foods"]["created"] += 1
        else:
            counters["foods"]["updated"] += 1

        food.category = group.name if group is not None else food.category
        food.storage_location = location.name if location is not None else food.storage_location
        food.product_group_id = group.id if group is not None else food.product_group_id
        food.product_unit_id = unit.id if unit is not None else food.product_unit_id
        food.serving_size = 1.0
        food.serving_unit = unit.name if unit is not None else food.serving_unit
        food.calories_per_100g = _float(row.get("calories"))
        db.flush()
        food_by_grocy_id[grocy_id] = food

    for row in _rows(csv_directory, "stock_current_location_content.csv", warnings):
        amount = _quantity(row.get("amount"))
        if amount <= 0:
            counters["inventory_items"]["skipped"] += 1
            continue

        grocy_product_id = _int(row.get("product_id"))
        food = food_by_grocy_id.get(grocy_product_id or -1)
        product_row = next(
            (item for item in product_rows if _int(item.get("id")) == grocy_product_id),
            None,
        )
        location = location_by_grocy_id.get(_int(row.get("location_id")) or -1)
        if food is None or product_row is None:
            counters["inventory_items"]["skipped"] += 1
            continue

        unit = unit_by_grocy_id.get(
            _int(product_row.get("qu_id_stock")) or _int(product_row.get("qu_id_purchase")) or -1,
        )
        group = group_by_grocy_id.get(_int(product_row.get("product_group_id")) or -1)
        best_before = _date(row.get("best_before_date"))
        expiry_days = None
        if best_before is not None:
            expiry_days = max((best_before - today).days, 0)
        storage_name = location.name if location is not None else food.storage_location
        total_value = _float(row.get("value"))
        price = total_value / amount if amount > 0 and total_value > 0 else None

        query = db.query(models.InventoryItem).filter(
            models.InventoryItem.name == food.name,
            models.InventoryItem.storage_location == storage_name,
        )
        if food.id is not None:
            query = query.filter(models.InventoryItem.food_id == food.id)
        if expiry_days is None:
            query = query.filter(models.InventoryItem.expiry_days.is_(None))
        else:
            query = query.filter(models.InventoryItem.expiry_days == expiry_days)
        item = query.first()
        if item is None:
            item = models.InventoryItem(name=food.name)
            db.add(item)
            counters["inventory_items"]["created"] += 1
        else:
            counters["inventory_items"]["updated"] += 1

        item.food_id = food.id
        item.emoji = food.emoji
        item.brand = food.brand
        item.category = food.category
        item.quantity = amount
        item.unit = unit.name if unit is not None else food.serving_unit
        item.minimum_quantity = _quantity(product_row.get("min_stock_amount"))
        item.storage_location = storage_name
        item.expiry_days = expiry_days
        item.purchase_date = today
        item.price = price
        item.barcode = barcode_by_product.get(grocy_product_id or -1)
        item.notes = _text(product_row.get("description"))
        item.product_group_id = group.id if group is not None else food.product_group_id
        item.product_unit_id = unit.id if unit is not None else food.product_unit_id
        item.serving_size = food.serving_size
        item.serving_unit = food.serving_unit
        item.calories_per_100g = food.calories_per_100g
        item.protein_per_100g = food.protein_per_100g
        item.fat_per_100g = food.fat_per_100g
        item.carbs_per_100g = food.carbs_per_100g

    recipe_by_grocy_id: dict[int, models.Recipe] = {}
    for row in _rows(csv_directory, "recipes.csv", warnings):
        grocy_id = _int(row.get("id"))
        if grocy_id is None or grocy_id <= 0 or _text(row.get("type")) != "normal":
            counters["recipes"]["skipped"] += 1
            continue
        name = _text(row.get("name"))
        if name is None:
            counters["recipes"]["skipped"] += 1
            continue

        recipe = (
            db.query(models.Recipe)
            .filter(models.Recipe.name == name)
            .filter(models.Recipe.is_archived.is_(False))
            .first()
        )
        if recipe is None:
            recipe = (
                db.query(models.Recipe)
                .filter(func.lower(models.Recipe.name) == name.lower())
                .filter(models.Recipe.is_archived.is_(False))
                .first()
            )
        if recipe is None:
            recipe = models.Recipe(name=name)
            db.add(recipe)
            counters["recipes"]["created"] += 1
        else:
            recipe.ingredients.clear()
            counters["recipes"]["updated"] += 1

        recipe.description = _clean_html(row.get("description"))
        recipe.image_path = _text(row.get("picture_file_name"))
        recipe.servings = _quantity(row.get("desired_servings"), 1.0) or 1.0
        recipe.tags = ["Grocy"]
        db.flush()
        recipe_by_grocy_id[grocy_id] = recipe

    for row in _rows(csv_directory, "recipes_pos.csv", warnings):
        recipe = recipe_by_grocy_id.get(_int(row.get("recipe_id")) or -1)
        food = food_by_grocy_id.get(_int(row.get("product_id")) or -1)
        if recipe is None or food is None:
            counters["recipe_ingredients"]["skipped"] += 1
            continue

        unit = unit_by_grocy_id.get(_int(row.get("qu_id")) or -1)
        recipe.ingredients.append(
            models.RecipeIngredient(
                food_id=food.id,
                quantity=max(_quantity(row.get("amount")), 0.0001),
                unit=unit.name if unit is not None else food.serving_unit,
                notes=_text(row.get("note")),
            )
        )
        counters["recipe_ingredients"]["created"] += 1

    for row in _rows(csv_directory, "shopping_list.csv", warnings):
        if _bool(row.get("done")):
            counters["shopping_list_items"]["skipped"] += 1
            continue
        food = food_by_grocy_id.get(_int(row.get("product_id")) or -1)
        if food is None:
            counters["shopping_list_items"]["skipped"] += 1
            continue
        unit = unit_by_grocy_id.get(_int(row.get("qu_id")) or -1)
        amount = _quantity(row.get("amount"), 1.0) or 1.0
        existing = (
            db.query(models.ShoppingListItem)
            .filter(models.ShoppingListItem.food_id == food.id)
            .filter(models.ShoppingListItem.is_checked.is_(False))
            .first()
        )
        if existing is None:
            existing = models.ShoppingListItem(name=food.name, food_id=food.id)
            db.add(existing)
            counters["shopping_list_items"]["created"] += 1
        else:
            counters["shopping_list_items"]["updated"] += 1
        existing.quantity = amount
        existing.unit = unit.name if unit is not None else food.serving_unit
        existing.notes = _text(row.get("note"))

    for row in _rows(csv_directory, "tasks.csv", warnings):
        title = _text(row.get("name"))
        due_date = _date(row.get("due_date"))
        if title is None or due_date is None:
            counters["calendar_tasks"]["skipped"] += 1
            continue
        user = user_by_grocy_id.get(_int(row.get("assigned_to_user_id")) or -1)
        start_at = datetime.combine(due_date, datetime.min.time())
        existing = (
            db.query(models.CalendarEvent)
            .filter(models.CalendarEvent.title == title)
            .filter(models.CalendarEvent.start_at == start_at)
            .filter(models.CalendarEvent.entry_type == "task")
            .first()
        )
        if existing is None:
            existing = models.CalendarEvent(title=title, start_at=start_at, entry_type="task")
            db.add(existing)
            counters["calendar_tasks"]["created"] += 1
        else:
            counters["calendar_tasks"]["updated"] += 1
        existing.description = _clean_html(row.get("description"))
        existing.all_day = True
        existing.is_completed = _bool(row.get("done"))
        existing.user_id = user.id if user is not None else existing.user_id

    for filename in sorted(SENSITIVE_OR_UNSUPPORTED_FILES):
        if (csv_directory / filename).exists():
            counters.setdefault("ignored_files", _counter())
            counters["ignored_files"]["skipped"] += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "directory": str(csv_directory),
        "dry_run": dry_run,
        "imported": counters,
        "warnings": warnings,
    }
