"""Copy selected data into a staged database; never execute an uploaded schema."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter

from .. import models, schemas


DATA_GROUPS = {
    "weight": ("Gewichtsdaten", {"weight_entries"}),
    "training": ("Training", {"training_plans", "training_exercises", "training_sessions", "training_session_sets"}),
    "calendar": ("Kalender und ToDos", {"calendar_groups", "calendar_events", "calendar_event_exclusions", "calendar_event_shifts"}),
    "recipes": ("Rezepte", {"recipes", "recipe_ingredients"}),
    "foods": ("Lebensmittel und Stammdaten", {"foods", "food_conversions", "food_barcodes", "product_groups", "product_units", "storage_locations"}),
    "inventory": ("Vorrat und Belegnachweise", {"inventory_items", "receipt_bookings"}),
    "meals": ("Mahlzeiten und Mealprep", {"meal_logs", "meal_inventory_bookings"}),
    "shopping": ("Einkaufsliste", {"shopping_list_items"}),
}

# Only these household records have a stable identity across installations.
IDENTITY_COLUMNS = {
    "users": ("username",),
    "foods": ("name", "brand"),
    "recipes": ("name",),
    "product_groups": ("name",),
    "product_units": ("name",),
    "storage_locations": ("name",),
}
CHILD_TABLES = {
    "foods": (("food_conversions", "food_id"), ("food_barcodes", "food_id")),
    "recipes": (("recipe_ingredients", "recipe_id"),),
}


class DataTransfer:
    def __init__(self, source: sqlite3.Connection, target: sqlite3.Connection, *, recipe_only=False):
        self.source = source
        self.target = target
        source.row_factory = sqlite3.Row
        target.row_factory = sqlite3.Row
        self.recipe_only = recipe_only
        self.tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.mapping: dict[tuple[str, int], int] = {}
        self.copied: set[tuple[str, int]] = set()
        self.selected: set[str] = set()
        self.counts: Counter = Counter()
        self.warnings: list[str] = []
        self.next_ids = {
            name: target.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{name}"').fetchone()[0] + 1
            for name in models.Base.metadata.tables
        }
        self.identities = {}
        for table, columns in IDENTITY_COLUMNS.items():
            identities = {}
            for row in target.execute(f'SELECT * FROM "{table}"'):
                key = tuple(row[column] for column in columns)
                identities.setdefault(key, []).append(row["id"])
            self.identities[table] = identities

    def rows(self, table):
        if table not in self.tables:
            return []
        return self.source.execute(f'SELECT * FROM "{table}" ORDER BY id')

    def identity(self, table, row):
        columns = IDENTITY_COLUMNS.get(table)
        if not columns:
            return None
        matches = self.identities[table].get(tuple(row[column] for column in columns), [])
        if len(matches) > 1:
            raise ValueError(f"Mehrdeutige Zuordnung in {table}: {row[columns[0]]}. Bitte zuerst die doppelten Namen bereinigen.")
        return matches[0] if matches else None

    def allocate(self, table):
        value = self.next_ids[table]
        self.next_ids[table] += 1
        return value

    def replace_groups(self, groups: list[str]):
        self.selected = set().union(*(DATA_GROUPS[group][1] for group in groups))
        if ("training" in groups) != ("calendar" in groups):
            # A linked calendar and its completed workouts form one history.
            # Importing a plan as an implicit dependency would lose its exercises;
            # importing a session's event would lose its pauses and exclusions.
            for connection in (self.source, self.target):
                for table, column in (("calendar_events", "training_plan_id"), ("training_sessions", "calendar_event_id")):
                    columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
                    if column in columns and connection.execute(f'SELECT 1 FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT 1').fetchone():
                        raise ValueError("Training und Kalender sind miteinander verknuepft. Bitte beide Datenbereiche gemeinsam auswaehlen.")
        if "inventory" in groups and "meals" not in groups and self.target.execute("SELECT 1 FROM meal_inventory_bookings LIMIT 1").fetchone():
            raise ValueError("Der Vorrat ist mit bestehenden Mahlzeitenbuchungen verbunden. Bitte Mahlzeiten ebenfalls auswaehlen.")
        if "meals" in groups and "inventory" not in groups:
            # A booking's JSON refers to specific stock lots. Without restoring
            # those lots, it must stay a legacy booking without automatic refund.
            self.warnings.append("Mahlzeiten ohne Vorrat importiert: Alte Bestandsabbuchungen koennen nicht automatisch rueckgaengig gemacht werden.")
        for table in self.selected:
            self.counts[table] = 0
            used = set()
            for row in self.rows(table):
                new_id = self.identity(table, row) if table in IDENTITY_COLUMNS else None
                if new_id in used:
                    raise ValueError(f"Mehrere Quelldatensaetze in {table} haben denselben Namen. Der Bereich kann nicht eindeutig ersetzt werden.")
                new_id = new_id if new_id is not None else self.allocate(table)
                used.add(new_id)
                self.mapping[table, row["id"]] = new_id
        # Foreign keys are disabled only in the isolated staging copy, so no
        # CASCADE/SET NULL can alter data outside the chosen areas.
        for table in self.selected:
            self.target.execute(f'DELETE FROM "{table}"')
        for table in models.Base.metadata.sorted_tables:
            if table.name in self.selected:
                for row in self.rows(table.name):
                    if table.name == "meal_inventory_bookings" and "inventory" not in groups:
                        continue
                    self.copy_row(table.name, row)
        self.check_links()

    def add_recipes(self, recipe_ids: list[int]):
        for recipe_id in recipe_ids:
            row = self.source.execute('SELECT * FROM recipes WHERE id=?', (recipe_id,)).fetchone()
            if row is None:
                raise ValueError(f"Rezept {recipe_id} wurde in der Datei nicht gefunden.")
            # Adding recipes always creates a new recipe, including when a name
            # already exists. Existing recipes and their ingredients stay intact.
            self.mapping["recipes", recipe_id] = self.allocate("recipes")
        for recipe_id in recipe_ids:
            self.copy_id("recipes", recipe_id)
        self.check_links()

    def copy_id(self, table, source_id):
        key = (table, source_id)
        if key in self.mapping:
            if table not in self.selected and key not in self.copied:
                row = self.source.execute(f'SELECT * FROM "{table}" WHERE id=?', (source_id,)).fetchone()
                self.copy_row(table, row)
            return self.mapping[key]
        row = self.source.execute(f'SELECT * FROM "{table}" WHERE id=?', (source_id,)).fetchone()
        if row is None:
            raise ValueError(f"Fehlende Verknuepfung in {table}.")
        existing = self.identity(table, row)
        if existing is not None:
            self.mapping[key] = existing
            self.copied.add(key)
            return existing
        if table == "users":
            raise ValueError(f"Profil '{row['username']}' fehlt. Bitte vor dem Teilimport ein Profil mit genau diesem Namen anlegen. Profil-IDs werden nicht als Zuordnung verwendet.")
        return self.copy_row(table, row)

    def copy_row(self, table_name, row):
        key = (table_name, row["id"])
        if key in self.copied:
            return self.mapping[key]
        if key not in self.mapping:
            self.mapping[key] = self.allocate(table_name)
        new_id = self.mapping[key]
        self.copied.add(key)
        table = models.Base.metadata.tables[table_name]
        values = {column: row[column] for column in table.columns.keys() if column in row.keys()}
        values["id"] = new_id
        if self.recipe_only and table_name in {"recipes", "foods"}:
            values["is_archived"] = False
        for foreign_key in table.foreign_keys:
            column = foreign_key.parent.name
            parent = foreign_key.column.table.name
            if values.get(column) is None:
                continue
            if self.recipe_only and (parent == "users" or (table_name == "recipes" and column == "prepared_food_id")):
                values[column] = None
            elif table_name == "shopping_list_items" and parent == "inventory_items" and parent not in self.selected:
                values[column] = None
            else:
                values[column] = self.copy_id(parent, values[column])
        if table_name == "calendar_groups":
            values["suppresses_group_ids"] = json.dumps([
                self.copy_id("calendar_groups", group_id)
                for group_id in json.loads(values["suppresses_group_ids"])
            ])
        if table_name == "meal_inventory_bookings":
            deductions = json.loads(values["deductions"])
            for deduction in deductions:
                schemas.StoredInventoryDeduction.model_validate(deduction)
                old_id = deduction["inventory_item_id"]
                lot = self.source.execute("SELECT 1 FROM inventory_items WHERE id=?", (old_id,)).fetchone()
                if lot:
                    deduction["inventory_item_id"] = self.copy_id("inventory_items", old_id)
                else:
                    # A legitimately deleted lot is recreated from its snapshot
                    # when refunded; reserve an ID that cannot point to a new lot.
                    if ("inventory_items", old_id) not in self.mapping:
                        self.mapping["inventory_items", old_id] = self.allocate("inventory_items")
                    deduction["inventory_item_id"] = self.mapping["inventory_items", old_id]
                for foreign_key in models.InventoryItem.__table__.foreign_keys:
                    column = foreign_key.parent.name
                    if deduction["snapshot"].get(column) is not None:
                        deduction["snapshot"][column] = self.copy_id(foreign_key.column.table.name, deduction["snapshot"][column])
            values["deductions"] = json.dumps(deductions)
        if table_name in {"foods", "food_barcodes"} and values.get("barcode"):
            code = values["barcode"]
            owner = values["id"] if table_name == "foods" else values["food_id"]
            conflict = self.target.execute("SELECT id FROM foods WHERE barcode=? AND id<>? UNION ALL SELECT food_id FROM food_barcodes WHERE barcode=? AND food_id<>?", (code, owner, code, owner)).fetchone()
            if conflict:
                raise ValueError(f"EAN {code} ist bereits einem anderen Lebensmittel zugeordnet. Bitte zuerst die Produktnamen und Marken abgleichen.")
        names = ", ".join(f'"{column}"' for column in values)
        placeholders = ", ".join("?" for _ in values)
        self.target.execute(f'INSERT INTO "{table_name}" ({names}) VALUES ({placeholders})', list(values.values()))
        self.counts[table_name] += 1
        for child, column in CHILD_TABLES.get(table_name, ()):
            if child in self.tables and child not in self.selected:
                for child_row in self.source.execute(f'SELECT * FROM "{child}" WHERE "{column}"=?', (row["id"],)):
                    self.copy_row(child, child_row)
        return new_id

    def check_links(self):
        if self.target.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Die Auswahl wuerde Verknuepfungen zu bestehenden Daten entfernen. Bitte die verbundenen Bereiche ebenfalls auswaehlen. Es wurde nichts importiert.")
        # These references are stored as JSON rather than SQL foreign keys.
        for row in self.target.execute("SELECT deductions FROM meal_inventory_bookings"):
            for item in json.loads(row[0]):
                for foreign_key in models.InventoryItem.__table__.foreign_keys:
                    parent = foreign_key.column.table.name
                    parent_id = item["snapshot"].get(foreign_key.parent.name)
                    if parent_id is not None and not self.target.execute(f'SELECT 1 FROM "{parent}" WHERE id=?', (parent_id,)).fetchone():
                        raise ValueError("Stammdaten sind mit bestehenden Mahlzeitenbuchungen verbunden. Bitte Mahlzeiten und Vorrat ebenfalls auswaehlen.")
        group_ids = {row[0] for row in self.target.execute("SELECT id FROM calendar_groups")}
        for row in self.target.execute("SELECT suppresses_group_ids FROM calendar_groups"):
            if any(group_id not in group_ids for group_id in json.loads(row[0])):
                raise ValueError("Eine Kalendergruppe verweist auf eine fehlende Gruppe.")
