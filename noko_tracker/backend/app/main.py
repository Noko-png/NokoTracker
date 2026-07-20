import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from . import crud, models
from .database import DATABASE_URL, SessionLocal, engine
from .routers import (
    calendar,
    dashboard,
    foods,
    imports,
    inventory,
    meals,
    nutrition,
    product_groups,
    product_units,
    recipes,
    shopping,
    storage_locations,
    users,
)


models.Base.metadata.create_all(bind=engine)


def migrate_sqlite_user_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    preference_migrations = {
        "theme": "ALTER TABLE users ADD COLUMN theme VARCHAR(32) NOT NULL DEFAULT 'light'",
        "daily_calories": "ALTER TABLE users ADD COLUMN daily_calories FLOAT NOT NULL DEFAULT 2500",
        "protein_percent": "ALTER TABLE users ADD COLUMN protein_percent FLOAT NOT NULL DEFAULT 25",
        "fat_percent": "ALTER TABLE users ADD COLUMN fat_percent FLOAT NOT NULL DEFAULT 30",
        "carbs_percent": "ALTER TABLE users ADD COLUMN carbs_percent FLOAT NOT NULL DEFAULT 45",
    }

    if {"id", "username", "password"}.issubset(columns):
        with engine.begin() as connection:
            for column_name, statement in preference_migrations.items():
                if column_name not in columns:
                    connection.execute(text(statement))
        return

    username_source = (
        "COALESCE(NULLIF(username, ''), 'user_' || id)"
        if "username" in columns
        else "'user_' || id"
    )
    password_source = (
        "COALESCE(NULLIF(password, ''), 'change-me')"
        if "password" in columns
        else "'change-me'"
    )

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("DROP TABLE IF EXISTS users_migrated"))
        connection.execute(
            text(
                "CREATE TABLE users_migrated ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "username VARCHAR(120) NOT NULL UNIQUE, "
                "password VARCHAR(255) NOT NULL, "
                "theme VARCHAR(32) NOT NULL DEFAULT 'light', "
                "daily_calories FLOAT NOT NULL DEFAULT 2500, "
                "protein_percent FLOAT NOT NULL DEFAULT 25, "
                "fat_percent FLOAT NOT NULL DEFAULT 30, "
                "carbs_percent FLOAT NOT NULL DEFAULT 45"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users_migrated "
                "(id, username, password) "
                f"SELECT id, {username_source}, {password_source} FROM users"
            )
        )
        connection.execute(text("DROP TABLE users"))
        connection.execute(text("ALTER TABLE users_migrated RENAME TO users"))
        connection.execute(text("CREATE INDEX ix_users_id ON users (id)"))
        connection.execute(text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


migrate_sqlite_user_schema()


def migrate_sqlite_calendar_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "calendar_events" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("calendar_events")}
    migrations = {
        "entry_type": "ALTER TABLE calendar_events ADD COLUMN entry_type VARCHAR(32) NOT NULL DEFAULT 'event'",
        "all_day": "ALTER TABLE calendar_events ADD COLUMN all_day BOOLEAN NOT NULL DEFAULT 0",
        "is_completed": "ALTER TABLE calendar_events ADD COLUMN is_completed BOOLEAN NOT NULL DEFAULT 0",
        "recurrence_frequency": (
            "ALTER TABLE calendar_events ADD COLUMN recurrence_frequency "
            "VARCHAR(32) NOT NULL DEFAULT 'none'"
        ),
        "recurrence_interval": (
            "ALTER TABLE calendar_events ADD COLUMN recurrence_interval INTEGER NOT NULL DEFAULT 1"
        ),
        "recurrence_until": "ALTER TABLE calendar_events ADD COLUMN recurrence_until DATETIME",
        "group_id": "ALTER TABLE calendar_events ADD COLUMN group_id INTEGER",
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))

    if "calendar_groups" in table_names:
        group_columns = {
            column["name"] for column in inspector.get_columns("calendar_groups")
        }
        group_migrations = {
            "suppresses_group_ids": (
                "ALTER TABLE calendar_groups "
                "ADD COLUMN suppresses_group_ids JSON NOT NULL DEFAULT '[]'"
            ),
            "hide_from_dashboard_and_month": (
                "ALTER TABLE calendar_groups "
                "ADD COLUMN hide_from_dashboard_and_month BOOLEAN NOT NULL DEFAULT 0"
            ),
        }
        with engine.begin() as connection:
            for column_name, statement in group_migrations.items():
                if column_name not in group_columns:
                    connection.execute(text(statement))


migrate_sqlite_calendar_schema()


def migrate_sqlite_recipe_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "recipes" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("recipes")}
    migrations = {
        "emoji": "ALTER TABLE recipes ADD COLUMN emoji VARCHAR(32) NOT NULL DEFAULT '🍲'",
        "is_archived": "ALTER TABLE recipes ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0",
        "tags": "ALTER TABLE recipes ADD COLUMN tags JSON NOT NULL DEFAULT '[]'",
        "image_path": "ALTER TABLE recipes ADD COLUMN image_path TEXT",
        "prepared_food_id": "ALTER TABLE recipes ADD COLUMN prepared_food_id INTEGER",
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))


migrate_sqlite_recipe_schema()


def migrate_sqlite_food_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "foods" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("foods")}
    migrations = {
        "emoji": "ALTER TABLE foods ADD COLUMN emoji VARCHAR(32) NOT NULL DEFAULT '🍽️'",
        "is_archived": "ALTER TABLE foods ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT 0",
        "product_group_id": "ALTER TABLE foods ADD COLUMN product_group_id INTEGER",
        "product_unit_id": "ALTER TABLE foods ADD COLUMN product_unit_id INTEGER",
        "storage_location": "ALTER TABLE foods ADD COLUMN storage_location VARCHAR(120)",
        "minimum_quantity": "ALTER TABLE foods ADD COLUMN minimum_quantity FLOAT NOT NULL DEFAULT 0",
        "barcode": "ALTER TABLE foods ADD COLUMN barcode VARCHAR(128)",
        "purchase_date": "ALTER TABLE foods ADD COLUMN purchase_date DATE",
        "expiry_days": "ALTER TABLE foods ADD COLUMN expiry_days INTEGER",
        "price": "ALTER TABLE foods ADD COLUMN price FLOAT",
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))


migrate_sqlite_food_schema()


def migrate_sqlite_food_conversion_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "foods" not in table_names:
        return
    if "food_conversions" in table_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS food_conversions ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "food_id INTEGER NOT NULL, "
                "quantity FLOAT NOT NULL, "
                "unit VARCHAR(32) NOT NULL, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "CONSTRAINT uq_food_conversion_food_unit UNIQUE (food_id, unit), "
                "CONSTRAINT ck_food_conversion_quantity_positive CHECK (quantity > 0), "
                "FOREIGN KEY(food_id) REFERENCES foods (id) ON DELETE CASCADE"
                ")"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_food_conversions_id ON food_conversions (id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_food_conversions_food_id "
                "ON food_conversions (food_id)"
            )
        )


migrate_sqlite_food_conversion_schema()


def migrate_sqlite_product_group_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "product_groups" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("product_groups")}
    migrations = {
        "default_expiry_days": (
            "ALTER TABLE product_groups ADD COLUMN default_expiry_days INTEGER"
        ),
        "default_storage_location": (
            "ALTER TABLE product_groups ADD COLUMN default_storage_location VARCHAR(120)"
        ),
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))

        refreshed_columns = {
            column["name"] for column in inspect(connection).get_columns("product_groups")
        }
        if {"default_expiry_date", "default_expiry_days"}.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE product_groups "
                    "SET default_expiry_days = MAX(0, CAST(julianday(default_expiry_date) - julianday('now') AS INTEGER)) "
                    "WHERE default_expiry_days IS NULL "
                    "AND default_expiry_date IS NOT NULL"
                )
            )


migrate_sqlite_product_group_schema()


def migrate_sqlite_inventory_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "inventory_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    migrations = {
        "emoji": "ALTER TABLE inventory_items ADD COLUMN emoji VARCHAR(32) NOT NULL DEFAULT '📦'",
        "brand": "ALTER TABLE inventory_items ADD COLUMN brand VARCHAR(160)",
        "minimum_quantity": "ALTER TABLE inventory_items ADD COLUMN minimum_quantity FLOAT NOT NULL DEFAULT 0",
        "storage_location": "ALTER TABLE inventory_items ADD COLUMN storage_location VARCHAR(120)",
        "expiry_days": "ALTER TABLE inventory_items ADD COLUMN expiry_days INTEGER",
        "purchase_date": "ALTER TABLE inventory_items ADD COLUMN purchase_date DATE",
        "price": "ALTER TABLE inventory_items ADD COLUMN price FLOAT",
        "barcode": "ALTER TABLE inventory_items ADD COLUMN barcode VARCHAR(128)",
        "image_path": "ALTER TABLE inventory_items ADD COLUMN image_path VARCHAR(500)",
        "notes": "ALTER TABLE inventory_items ADD COLUMN notes TEXT",
        "serving_size": "ALTER TABLE inventory_items ADD COLUMN serving_size FLOAT NOT NULL DEFAULT 100",
        "serving_unit": "ALTER TABLE inventory_items ADD COLUMN serving_unit VARCHAR(32) NOT NULL DEFAULT 'g'",
        "calories_per_100g": "ALTER TABLE inventory_items ADD COLUMN calories_per_100g FLOAT NOT NULL DEFAULT 0",
        "protein_per_100g": "ALTER TABLE inventory_items ADD COLUMN protein_per_100g FLOAT NOT NULL DEFAULT 0",
        "carbs_per_100g": "ALTER TABLE inventory_items ADD COLUMN carbs_per_100g FLOAT NOT NULL DEFAULT 0",
        "fat_per_100g": "ALTER TABLE inventory_items ADD COLUMN fat_per_100g FLOAT NOT NULL DEFAULT 0",
        "food_id": "ALTER TABLE inventory_items ADD COLUMN food_id INTEGER",
        "product_group_id": "ALTER TABLE inventory_items ADD COLUMN product_group_id INTEGER",
        "product_unit_id": "ALTER TABLE inventory_items ADD COLUMN product_unit_id INTEGER",
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))

        refreshed_columns = {
            column["name"] for column in inspect(connection).get_columns("inventory_items")
        }
        if {"location", "storage_location"}.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET storage_location = location "
                    "WHERE storage_location IS NULL"
                )
            )
        if {"expiration_date", "expiry_date"}.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET expiry_days = MAX(0, CAST(julianday(COALESCE(expiry_date, expiration_date)) - julianday(COALESCE(purchase_date, DATE('now'))) AS INTEGER)) "
                    "WHERE expiry_days IS NULL "
                    "AND COALESCE(expiry_date, expiration_date) IS NOT NULL"
                )
            )
        elif {"expiry_date", "expiry_days"}.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET expiry_days = MAX(0, CAST(julianday(expiry_date) - julianday(COALESCE(purchase_date, DATE('now'))) AS INTEGER)) "
                    "WHERE expiry_days IS NULL "
                    "AND expiry_date IS NOT NULL"
                )
            )
        elif {"expiration_date", "expiry_days"}.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET expiry_days = MAX(0, CAST(julianday(expiration_date) - julianday(COALESCE(purchase_date, DATE('now'))) AS INTEGER)) "
                    "WHERE expiry_days IS NULL "
                    "AND expiration_date IS NOT NULL"
                )
            )
        if "purchase_date" in refreshed_columns:
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET purchase_date = DATE('now') "
                    "WHERE purchase_date IS NULL"
                )
            )
        nutrition_columns = {
            "food_id",
            "serving_size",
            "serving_unit",
            "calories_per_100g",
            "protein_per_100g",
            "carbs_per_100g",
            "fat_per_100g",
        }
        if "foods" in inspect(connection).get_table_names() and nutrition_columns.issubset(refreshed_columns):
            connection.execute(
                text(
                    "UPDATE inventory_items "
                    "SET "
                    "serving_size = COALESCE((SELECT serving_size FROM foods WHERE foods.id = inventory_items.food_id), serving_size), "
                    "serving_unit = COALESCE((SELECT serving_unit FROM foods WHERE foods.id = inventory_items.food_id), serving_unit), "
                    "calories_per_100g = COALESCE((SELECT calories_per_100g FROM foods WHERE foods.id = inventory_items.food_id), calories_per_100g), "
                    "protein_per_100g = COALESCE((SELECT protein_per_100g FROM foods WHERE foods.id = inventory_items.food_id), protein_per_100g), "
                    "carbs_per_100g = COALESCE((SELECT carbs_per_100g FROM foods WHERE foods.id = inventory_items.food_id), carbs_per_100g), "
                    "fat_per_100g = COALESCE((SELECT fat_per_100g FROM foods WHERE foods.id = inventory_items.food_id), fat_per_100g) "
                    "WHERE food_id IS NOT NULL "
                    "AND EXISTS (SELECT 1 FROM foods WHERE foods.id = inventory_items.food_id) "
                    "AND calories_per_100g = 0 "
                    "AND protein_per_100g = 0 "
                    "AND carbs_per_100g = 0 "
                    "AND fat_per_100g = 0"
                )
            )


migrate_sqlite_inventory_schema()


DEFAULT_PRODUCT_UNITS = (
    "pcs",
    "g",
    "kg",
    "ml",
    "l",
    "pack",
    "Packung",
    "Flasche",
    "serving",
    "Portion",
)


def ensure_default_product_units() -> None:
    with SessionLocal() as db:
        for unit_name in DEFAULT_PRODUCT_UNITS:
            crud.get_or_create_product_unit(db, unit_name)
        db.commit()


def sync_existing_storage_locations() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "storage_locations" not in table_names:
        return

    names: set[str] = set()
    if "inventory_items" in table_names:
        inventory_columns = {
            column["name"] for column in inspector.get_columns("inventory_items")
        }
        if "storage_location" in inventory_columns:
            with SessionLocal() as db:
                names.update(
                    location.strip()
                    for (location,) in db.query(
                        models.InventoryItem.storage_location,
                    ).filter(models.InventoryItem.storage_location.is_not(None))
                    if location and location.strip()
                )

    if "product_groups" in table_names:
        product_group_columns = {
            column["name"] for column in inspector.get_columns("product_groups")
        }
        if "default_storage_location" in product_group_columns:
            with SessionLocal() as db:
                names.update(
                    location.strip()
                    for (location,) in db.query(
                        models.ProductGroup.default_storage_location,
                    ).filter(models.ProductGroup.default_storage_location.is_not(None))
                    if location and location.strip()
                )

    if "foods" in table_names:
        food_columns = {
            column["name"] for column in inspector.get_columns("foods")
        }
        if "storage_location" in food_columns:
            with SessionLocal() as db:
                names.update(
                    location.strip()
                    for (location,) in db.query(
                        models.Food.storage_location,
                    ).filter(models.Food.storage_location.is_not(None))
                    if location and location.strip()
                )

    if not names:
        return

    with SessionLocal() as db:
        existing_names = {
            location.name.lower() for location in db.query(models.StorageLocation).all()
        }
        for name in sorted(names):
            if name.lower() not in existing_names:
                db.add(models.StorageLocation(name=name))
        db.commit()


def sync_existing_inventory_foods() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if not {"foods", "inventory_items", "product_units"}.issubset(table_names):
        return

    inventory_columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    food_columns = {column["name"] for column in inspector.get_columns("foods")}
    required_inventory_columns = {
        "food_id",
        "name",
        "unit",
        "product_unit_id",
        "serving_size",
        "serving_unit",
        "calories_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "fat_per_100g",
    }
    required_food_columns = {"product_group_id", "product_unit_id"}
    has_food_storage_location = "storage_location" in food_columns
    has_inventory_storage_location = "storage_location" in inventory_columns
    if not required_inventory_columns.issubset(inventory_columns):
        return
    if not required_food_columns.issubset(food_columns):
        return

    with SessionLocal() as db:
        for item in db.query(models.InventoryItem).all():
            unit_name = (item.unit or "pcs").strip() or "pcs"
            product_unit = item.product_unit or crud.get_or_create_product_unit(db, unit_name)
            item.product_unit_id = product_unit.id
            item.unit = product_unit.name

            brand = item.brand.strip() if item.brand else None
            storage_location = (
                item.storage_location.strip()
                if has_inventory_storage_location and item.storage_location
                else None
            )
            food = item.food or crud.get_food_by_name_brand(db, item.name, brand)
            if food is None:
                food = models.Food(
                    name=item.name,
                    emoji=item.emoji,
                    brand=brand,
                    category=item.category,
                    storage_location=storage_location if has_food_storage_location else None,
                    product_group_id=item.product_group_id,
                    product_unit_id=product_unit.id,
                    minimum_quantity=item.minimum_quantity,
                    barcode=item.barcode,
                    purchase_date=item.purchase_date,
                    expiry_days=item.expiry_days,
                    price=item.price,
                    serving_size=item.serving_size,
                    serving_unit=item.serving_unit,
                    calories_per_100g=item.calories_per_100g,
                    protein_per_100g=item.protein_per_100g,
                    carbs_per_100g=item.carbs_per_100g,
                    fat_per_100g=item.fat_per_100g,
                )
                db.add(food)
                db.flush()
            else:
                food.emoji = food.emoji or item.emoji
                food.category = food.category or item.category
                if has_food_storage_location:
                    food.storage_location = food.storage_location or storage_location
                food.product_group_id = food.product_group_id or item.product_group_id
                food.product_unit_id = food.product_unit_id or product_unit.id
                food.minimum_quantity = food.minimum_quantity or item.minimum_quantity
                food.barcode = food.barcode or item.barcode
                food.purchase_date = food.purchase_date or item.purchase_date
                food.expiry_days = (
                    food.expiry_days
                    if food.expiry_days is not None
                    else item.expiry_days
                )
                food.price = food.price if food.price is not None else item.price
                if food.calories_per_100g == 0 and item.calories_per_100g > 0:
                    food.calories_per_100g = item.calories_per_100g
                if food.protein_per_100g == 0 and item.protein_per_100g > 0:
                    food.protein_per_100g = item.protein_per_100g
                if food.carbs_per_100g == 0 and item.carbs_per_100g > 0:
                    food.carbs_per_100g = item.carbs_per_100g
                if food.fat_per_100g == 0 and item.fat_per_100g > 0:
                    food.fat_per_100g = item.fat_per_100g

            item.food_id = food.id

        db.commit()


ensure_default_product_units()
sync_existing_storage_locations()
sync_existing_inventory_foods()


def drop_sqlite_obsolete_nutrition_columns() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    obsolete_columns = {
        "fiber_per_100g",
        "sugar_per_100g",
        "sodium_mg_per_100g",
    }

    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name in ("foods", "inventory_items"):
            if table_name not in inspector.get_table_names():
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name in obsolete_columns.intersection(columns):
                try:
                    connection.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
                except OperationalError:
                    pass


drop_sqlite_obsolete_nutrition_columns()


def migrate_sqlite_shopping_list_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "shopping_list_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("shopping_list_items")}
    if "is_purchased" in columns:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            rebuild_sqlite_shopping_list_table(connection)
        return

    migrations = {
        "inventory_item_id": "ALTER TABLE shopping_list_items ADD COLUMN inventory_item_id INTEGER",
        "store": "ALTER TABLE shopping_list_items ADD COLUMN store VARCHAR(120)",
        "is_checked": "ALTER TABLE shopping_list_items ADD COLUMN is_checked BOOLEAN NOT NULL DEFAULT 0",
        "priority": "ALTER TABLE shopping_list_items ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
    }

    with engine.begin() as connection:
        for column_name, statement in migrations.items():
            if column_name not in columns:
                connection.execute(text(statement))

        refreshed_columns = {
            column["name"] for column in inspect(connection).get_columns("shopping_list_items")
        }

def rebuild_sqlite_shopping_list_table(connection) -> None:
    existing_columns = {
        column["name"] for column in inspect(connection).get_columns("shopping_list_items")
    }
    source = {
        "name": (
            "COALESCE(NULLIF(name, ''), 'Imported item ' || id)"
            if "name" in existing_columns
            else "'Imported item ' || id"
        ),
        "food_id": "food_id" if "food_id" in existing_columns else "NULL",
        "inventory_item_id": (
            "inventory_item_id" if "inventory_item_id" in existing_columns else "NULL"
        ),
        "quantity": "COALESCE(quantity, 1)" if "quantity" in existing_columns else "1",
        "unit": (
            "COALESCE(NULLIF(unit, ''), 'pcs')" if "unit" in existing_columns else "'pcs'"
        ),
        "store": "store" if "store" in existing_columns else "NULL",
        "is_checked": (
            "COALESCE(is_checked, is_purchased, 0)"
            if {"is_checked", "is_purchased"}.issubset(existing_columns)
            else "COALESCE(is_checked, 0)"
            if "is_checked" in existing_columns
            else "COALESCE(is_purchased, 0)"
            if "is_purchased" in existing_columns
            else "0"
        ),
        "priority": "COALESCE(priority, 0)" if "priority" in existing_columns else "0",
        "notes": "notes" if "notes" in existing_columns else "NULL",
        "created_at": (
            "COALESCE(created_at, CURRENT_TIMESTAMP)"
            if "created_at" in existing_columns
            else "CURRENT_TIMESTAMP"
        ),
        "updated_at": (
            "COALESCE(updated_at, CURRENT_TIMESTAMP)"
            if "updated_at" in existing_columns
            else "CURRENT_TIMESTAMP"
        ),
    }

    connection.execute(text("PRAGMA foreign_keys=OFF"))
    connection.execute(text("DROP TABLE IF EXISTS shopping_list_items_migrated"))
    connection.execute(
        text(
            "CREATE TABLE shopping_list_items_migrated ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "name VARCHAR(200) NOT NULL, "
            "food_id INTEGER, "
            "inventory_item_id INTEGER, "
            "quantity FLOAT NOT NULL DEFAULT 1, "
            "unit VARCHAR(32) NOT NULL DEFAULT 'pcs', "
            "store VARCHAR(120), "
            "is_checked BOOLEAN NOT NULL DEFAULT 0, "
            "priority INTEGER NOT NULL DEFAULT 0, "
            "notes TEXT, "
            "created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL"
            ")"
        )
    )
    connection.execute(
        text(
            "INSERT INTO shopping_list_items_migrated "
            "(id, name, food_id, inventory_item_id, quantity, unit, store, "
            "is_checked, priority, notes, created_at, updated_at) "
            "SELECT "
            "id, "
            f"{source['name']}, "
            f"{source['food_id']}, "
            f"{source['inventory_item_id']}, "
            f"{source['quantity']}, "
            f"{source['unit']}, "
            f"{source['store']}, "
            f"{source['is_checked']}, "
            f"{source['priority']}, "
            f"{source['notes']}, "
            f"{source['created_at']}, "
            f"{source['updated_at']} "
            "FROM shopping_list_items"
        )
    )
    connection.execute(text("DROP TABLE shopping_list_items"))
    connection.execute(text("ALTER TABLE shopping_list_items_migrated RENAME TO shopping_list_items"))
    connection.execute(text("CREATE INDEX ix_shopping_list_items_id ON shopping_list_items (id)"))
    connection.execute(text("CREATE INDEX ix_shopping_list_items_name ON shopping_list_items (name)"))
    connection.execute(text("CREATE INDEX ix_shopping_list_items_food_id ON shopping_list_items (food_id)"))
    connection.execute(
        text(
            "CREATE INDEX ix_shopping_list_items_inventory_item_id "
            "ON shopping_list_items (inventory_item_id)"
        )
    )
    connection.execute(
        text("CREATE INDEX ix_shopping_list_items_is_checked ON shopping_list_items (is_checked)")
    )
    connection.execute(text("CREATE INDEX ix_shopping_list_items_priority ON shopping_list_items (priority)"))
    connection.execute(text("CREATE INDEX ix_shopping_list_items_store ON shopping_list_items (store)"))
    connection.execute(text("PRAGMA foreign_keys=ON"))


migrate_sqlite_shopping_list_schema()


def migrate_sqlite_meal_log_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "meal_logs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("meal_logs")}
    with engine.connect() as connection:
        create_sql = (
            connection.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='meal_logs'")
            ).scalar()
            or ""
        )

    required_columns = {
        "quick_add_name",
        "quick_calories",
        "quick_protein",
        "quick_fat",
        "quick_carbs",
        "meal_source",
        "planned_inventory_deduction",
        "inventory_deducted_at",
    }
    needs_rebuild = (
        not required_columns.issubset(columns)
        or "ck_meal_logs_exactly_one_source" not in create_sql
        or "ck_meal_logs_exactly_one_food_or_recipe" in create_sql
    )
    if not needs_rebuild:
        return

    def source(column_name: str, fallback: str) -> str:
        return column_name if column_name in columns else fallback

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("DROP TABLE IF EXISTS meal_logs_migrated"))
        connection.execute(
            text(
                "CREATE TABLE meal_logs_migrated ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "eaten_at DATETIME NOT NULL, "
                "meal_type VARCHAR(64), "
                "quantity FLOAT NOT NULL, "
                "unit VARCHAR(32) NOT NULL, "
                "notes TEXT, "
                "quick_add_name VARCHAR(200), "
                "quick_calories FLOAT, "
                "quick_protein FLOAT, "
                "quick_fat FLOAT, "
                "quick_carbs FLOAT, "
                "meal_source VARCHAR(32) NOT NULL, "
                "planned_inventory_deduction BOOLEAN NOT NULL, "
                "inventory_deducted_at DATETIME, "
                "user_id INTEGER, "
                "food_id INTEGER, "
                "recipe_id INTEGER, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL, "
                "CONSTRAINT ck_meal_logs_exactly_one_source CHECK ("
                "(food_id IS NOT NULL AND recipe_id IS NULL AND quick_add_name IS NULL) "
                "OR (food_id IS NULL AND recipe_id IS NOT NULL AND quick_add_name IS NULL) "
                "OR (food_id IS NULL AND recipe_id IS NULL AND quick_add_name IS NOT NULL)"
                "), "
                "CONSTRAINT ck_meal_logs_quick_calories_non_negative "
                "CHECK (quick_calories IS NULL OR quick_calories >= 0), "
                "CONSTRAINT ck_meal_logs_quick_protein_non_negative "
                "CHECK (quick_protein IS NULL OR quick_protein >= 0), "
                "CONSTRAINT ck_meal_logs_quick_fat_non_negative "
                "CHECK (quick_fat IS NULL OR quick_fat >= 0), "
                "CONSTRAINT ck_meal_logs_quick_carbs_non_negative "
                "CHECK (quick_carbs IS NULL OR quick_carbs >= 0), "
                "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, "
                "FOREIGN KEY(food_id) REFERENCES foods (id) ON DELETE RESTRICT, "
                "FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE RESTRICT"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO meal_logs_migrated ("
                "id, eaten_at, meal_type, quantity, unit, notes, "
                "quick_add_name, quick_calories, quick_protein, quick_fat, quick_carbs, "
                "meal_source, planned_inventory_deduction, inventory_deducted_at, "
                "user_id, food_id, recipe_id, created_at, updated_at"
                ") SELECT "
                f"{source('id', 'NULL')}, "
                f"COALESCE({source('eaten_at', 'NULL')}, CURRENT_TIMESTAMP), "
                f"{source('meal_type', 'NULL')}, "
                f"COALESCE({source('quantity', 'NULL')}, 1.0), "
                f"COALESCE(NULLIF({source('unit', 'NULL')}, ''), 'serving'), "
                f"{source('notes', 'NULL')}, "
                f"{source('quick_add_name', 'NULL')}, "
                f"{source('quick_calories', 'NULL')}, "
                f"{source('quick_protein', 'NULL')}, "
                f"{source('quick_fat', 'NULL')}, "
                f"{source('quick_carbs', 'NULL')}, "
                f"COALESCE(NULLIF({source('meal_source', 'NULL')}, ''), 'manual'), "
                f"COALESCE({source('planned_inventory_deduction', 'NULL')}, 0), "
                f"{source('inventory_deducted_at', 'NULL')}, "
                f"{source('user_id', 'NULL')}, "
                f"{source('food_id', 'NULL')}, "
                f"{source('recipe_id', 'NULL')}, "
                f"COALESCE({source('created_at', 'NULL')}, CURRENT_TIMESTAMP), "
                f"COALESCE({source('updated_at', 'NULL')}, CURRENT_TIMESTAMP) "
                "FROM meal_logs"
            )
        )
        connection.execute(text("DROP TABLE meal_logs"))
        connection.execute(text("ALTER TABLE meal_logs_migrated RENAME TO meal_logs"))
        connection.execute(text("CREATE INDEX ix_meal_logs_id ON meal_logs (id)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_eaten_at ON meal_logs (eaten_at)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_meal_type ON meal_logs (meal_type)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_quick_add_name ON meal_logs (quick_add_name)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_meal_source ON meal_logs (meal_source)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_user_id ON meal_logs (user_id)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_food_id ON meal_logs (food_id)"))
        connection.execute(text("CREATE INDEX ix_meal_logs_recipe_id ON meal_logs (recipe_id)"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


migrate_sqlite_meal_log_schema()


def ensure_default_user() -> None:
    with SessionLocal() as db:
        if db.query(models.User).first() is not None:
            return

        db.add(
            models.User(
                username="default",
                password="change-me",
            )
        )
        db.commit()


ensure_default_user()

app = FastAPI(
    title="Heim-ERP Backend",
    description="Backend API fuer ein privates Heim-ERP mit Kalender, Vorrat, Rezepten, Mahlzeiten und Einkaufsliste.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def normalize_ingress_double_slashes(request, call_next):
    path = request.scope.get("path")
    if isinstance(path, str) and path.startswith("//"):
        request.scope["path"] = "/" + path.lstrip("/")
    return await call_next(request)


@app.get("/health", tags=["system"])
def read_health():
    return {"status": "ok"}


app.include_router(users.router)
app.include_router(calendar.router)
app.include_router(calendar.groups_router)
app.include_router(inventory.router)
app.include_router(product_groups.router)
app.include_router(product_units.router)
app.include_router(storage_locations.router)
app.include_router(foods.router)
app.include_router(recipes.router)
app.include_router(meals.router)
app.include_router(nutrition.router)
app.include_router(shopping.router)
app.include_router(imports.router)
app.include_router(dashboard.router)


def configure_frontend() -> None:
    static_dir_env = os.getenv("NOKO_STATIC_DIR")
    static_dir = Path(static_dir_env).resolve() if static_dir_env else None
    index_file = static_dir / "index.html" if static_dir else None

    if not static_dir or not index_file or not index_file.is_file():
        @app.get("/", tags=["system"])
        def read_root():
            return {"name": "Heim-ERP Backend", "docs": "/docs"}

        return

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def read_frontend_index():
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    def read_frontend_asset_or_index(full_path: str):
        requested_path = (static_dir / full_path).resolve()
        try:
            requested_path.relative_to(static_dir)
        except ValueError:
            return FileResponse(index_file)

        if requested_path.is_file():
            return FileResponse(requested_path)

        return FileResponse(index_file)


configure_frontend()
