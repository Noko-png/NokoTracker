from datetime import date, datetime, timedelta

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    theme = Column(String(32), default="light", nullable=False)
    daily_calories = Column(Float, default=2500.0, nullable=False)
    protein_percent = Column(Float, default=25.0, nullable=False)
    fat_percent = Column(Float, default=30.0, nullable=False)
    carbs_percent = Column(Float, default=45.0, nullable=False)

    calendar_events = relationship(
        "CalendarEvent",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    calendar_groups = relationship(
        "CalendarGroup",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    recipes = relationship("Recipe", back_populates="created_by")
    meal_logs = relationship(
        "MealLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("daily_calories > 0", name="ck_users_daily_calories_positive"),
        CheckConstraint("protein_percent >= 0", name="ck_users_protein_percent_non_negative"),
        CheckConstraint("fat_percent >= 0", name="ck_users_fat_percent_non_negative"),
        CheckConstraint("carbs_percent >= 0", name="ck_users_carbs_percent_non_negative"),
    )


class CalendarGroup(TimestampMixin, Base):
    __tablename__ = "calendar_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    color = Column(String(32), default="#2563eb", nullable=False)
    suppresses_group_ids = Column(JSON, default=list, nullable=False)
    hide_from_dashboard_and_month = Column(Boolean, default=False, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    user = relationship("User", back_populates="calendar_groups")
    calendar_events = relationship("CalendarEvent", back_populates="group")


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=True, index=True)
    location = Column(String(255), nullable=True)
    entry_type = Column(String(32), default="event", nullable=False, index=True)
    all_day = Column(Boolean, default=False, nullable=False)
    is_completed = Column(Boolean, default=False, nullable=False, index=True)
    recurrence_frequency = Column(String(32), default="none", nullable=False, index=True)
    recurrence_interval = Column(Integer, default=1, nullable=False)
    recurrence_until = Column(DateTime(timezone=True), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    group_id = Column(
        Integer,
        ForeignKey("calendar_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user = relationship("User", back_populates="calendar_events")
    group = relationship("CalendarGroup", back_populates="calendar_events")
    exclusions = relationship(
        "CalendarEventExclusion",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="CalendarEventExclusion.occurrence_start_at",
    )

    __table_args__ = (
        CheckConstraint("recurrence_interval >= 1", name="ck_calendar_recurrence_interval_positive"),
    )


class CalendarEventExclusion(Base):
    __tablename__ = "calendar_event_exclusions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(
        Integer,
        ForeignKey("calendar_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurrence_start_at = Column(DateTime(timezone=True), nullable=False, index=True)

    event = relationship("CalendarEvent", back_populates="exclusions")

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "occurrence_start_at",
            name="uq_calendar_event_exclusion_occurrence",
        ),
    )


class Food(TimestampMixin, Base):
    __tablename__ = "foods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    emoji = Column(String(32), default="🍽️", nullable=False)
    brand = Column(String(160), nullable=True)
    category = Column(String(120), nullable=True, index=True)
    storage_location = Column(String(120), nullable=True, index=True)
    product_group_id = Column(
        Integer,
        ForeignKey("product_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_unit_id = Column(
        Integer,
        ForeignKey("product_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    minimum_quantity = Column(Float, default=0.0, nullable=False)
    barcode = Column(String(128), nullable=True, index=True)
    purchase_date = Column(Date, default=date.today, nullable=True, index=True)
    expiry_days = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)
    serving_size = Column(Float, default=100.0, nullable=False)
    serving_unit = Column(String(32), default="g", nullable=False)
    calories_per_100g = Column(Float, default=0.0, nullable=False)
    protein_per_100g = Column(Float, default=0.0, nullable=False)
    carbs_per_100g = Column(Float, default=0.0, nullable=False)
    fat_per_100g = Column(Float, default=0.0, nullable=False)

    product_group = relationship("ProductGroup", back_populates="foods")
    product_unit = relationship("ProductUnit", back_populates="foods")
    conversions = relationship(
        "FoodConversion",
        back_populates="food",
        cascade="all, delete-orphan",
        order_by="FoodConversion.id",
    )
    recipe_ingredients = relationship("RecipeIngredient", back_populates="food")
    inventory_items = relationship("InventoryItem", back_populates="food")
    meal_logs = relationship("MealLog", back_populates="food")
    shopping_items = relationship("ShoppingListItem", back_populates="food")

    __table_args__ = (
        UniqueConstraint("name", "brand", name="uq_food_name_brand"),
        CheckConstraint("minimum_quantity >= 0", name="ck_food_minimum_quantity_non_negative"),
        CheckConstraint(
            "expiry_days IS NULL OR expiry_days >= 0",
            name="ck_food_expiry_days_non_negative",
        ),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_food_price_non_negative"),
    )


class FoodConversion(TimestampMixin, Base):
    __tablename__ = "food_conversions"

    id = Column(Integer, primary_key=True, index=True)
    food_id = Column(
        Integer,
        ForeignKey("foods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity = Column(Float, nullable=False)
    unit = Column(String(32), nullable=False)

    food = relationship("Food", back_populates="conversions")

    __table_args__ = (
        UniqueConstraint("food_id", "unit", name="uq_food_conversion_food_unit"),
        CheckConstraint("quantity > 0", name="ck_food_conversion_quantity_positive"),
    )


class ProductGroup(TimestampMixin, Base):
    __tablename__ = "product_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    default_expiry_days = Column(Integer, nullable=True)
    default_storage_location = Column(String(120), nullable=True, index=True)

    foods = relationship("Food", back_populates="product_group")
    inventory_items = relationship("InventoryItem", back_populates="product_group")

    __table_args__ = (
        CheckConstraint(
            "default_expiry_days IS NULL OR default_expiry_days >= 0",
            name="ck_product_group_default_expiry_days_non_negative",
        ),
    )


class ProductUnit(TimestampMixin, Base):
    __tablename__ = "product_units"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(32), nullable=False, unique=True, index=True)

    foods = relationship("Food", back_populates="product_unit")
    inventory_items = relationship("InventoryItem", back_populates="product_unit")


class StorageLocation(TimestampMixin, Base):
    __tablename__ = "storage_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)


class InventoryItem(TimestampMixin, Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    emoji = Column(String(32), default="📦", nullable=False)
    brand = Column(String(160), nullable=True)
    category = Column(String(120), nullable=True, index=True)
    quantity = Column(Float, default=0.0, nullable=False)
    unit = Column(String(32), default="pcs", nullable=False)
    minimum_quantity = Column(Float, default=0.0, nullable=False)
    storage_location = Column(String(120), nullable=True, index=True)
    expiry_days = Column(Integer, nullable=True)
    purchase_date = Column(Date, default=date.today, nullable=False, index=True)
    price = Column(Float, nullable=True)
    barcode = Column(String(128), nullable=True, index=True)
    image_path = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)
    serving_size = Column(Float, default=100.0, nullable=False)
    serving_unit = Column(String(32), default="g", nullable=False)
    calories_per_100g = Column(Float, default=0.0, nullable=False)
    protein_per_100g = Column(Float, default=0.0, nullable=False)
    carbs_per_100g = Column(Float, default=0.0, nullable=False)
    fat_per_100g = Column(Float, default=0.0, nullable=False)
    food_id = Column(Integer, ForeignKey("foods.id", ondelete="SET NULL"), nullable=True, index=True)
    product_group_id = Column(
        Integer,
        ForeignKey("product_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_unit_id = Column(
        Integer,
        ForeignKey("product_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    food = relationship("Food", back_populates="inventory_items")
    product_group = relationship("ProductGroup", back_populates="inventory_items")
    product_unit = relationship("ProductUnit", back_populates="inventory_items")
    shopping_items = relationship("ShoppingListItem", back_populates="inventory_item")

    @property
    def expiry_date(self):
        if self.purchase_date is None or self.expiry_days is None:
            return None
        return self.purchase_date + timedelta(days=self.expiry_days)

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_quantity_non_negative"),
        CheckConstraint("minimum_quantity >= 0", name="ck_inventory_minimum_quantity_non_negative"),
        CheckConstraint(
            "expiry_days IS NULL OR expiry_days >= 0",
            name="ck_inventory_expiry_days_non_negative",
        ),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_inventory_price_non_negative"),
        CheckConstraint("serving_size > 0", name="ck_inventory_serving_size_positive"),
        CheckConstraint("calories_per_100g >= 0", name="ck_inventory_calories_non_negative"),
        CheckConstraint("protein_per_100g >= 0", name="ck_inventory_protein_non_negative"),
        CheckConstraint("carbs_per_100g >= 0", name="ck_inventory_carbs_non_negative"),
        CheckConstraint("fat_per_100g >= 0", name="ck_inventory_fat_non_negative"),
    )


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    emoji = Column(String(32), default="🍲", nullable=False)
    description = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    tags = Column(JSON, default=list, nullable=False)
    image_path = Column(Text, nullable=True)
    servings = Column(Float, default=1.0, nullable=False)
    prep_time_minutes = Column(Integer, nullable=True)
    cook_time_minutes = Column(Integer, nullable=True)
    prepared_food_id = Column(
        Integer,
        ForeignKey("foods.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_by = relationship("User", back_populates="recipes")
    prepared_food = relationship("Food", foreign_keys=[prepared_food_id])
    ingredients = relationship(
        "RecipeIngredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.id",
    )
    meal_logs = relationship("MealLog", back_populates="recipe")


class RecipeIngredient(TimestampMixin, Base):
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(
        Integer,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    food_id = Column(
        Integer,
        ForeignKey("foods.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Float, nullable=False)
    unit = Column(String(32), default="g", nullable=False)
    notes = Column(Text, nullable=True)

    recipe = relationship("Recipe", back_populates="ingredients")
    food = relationship("Food", back_populates="recipe_ingredients")


class MealLog(TimestampMixin, Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True, index=True)
    eaten_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    meal_type = Column(String(64), nullable=True, index=True)
    quantity = Column(Float, default=1.0, nullable=False)
    unit = Column(String(32), default="serving", nullable=False)
    notes = Column(Text, nullable=True)
    quick_add_name = Column(String(200), nullable=True, index=True)
    quick_calories = Column(Float, nullable=True)
    quick_protein = Column(Float, nullable=True)
    quick_fat = Column(Float, nullable=True)
    quick_carbs = Column(Float, nullable=True)
    meal_source = Column(String(32), default="manual", nullable=False, index=True)
    planned_inventory_deduction = Column(Boolean, default=False, nullable=False)
    inventory_deducted_at = Column(DateTime(timezone=True), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    food_id = Column(Integer, ForeignKey("foods.id", ondelete="RESTRICT"), nullable=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="RESTRICT"), nullable=True, index=True)

    user = relationship("User", back_populates="meal_logs")
    food = relationship("Food", back_populates="meal_logs")
    recipe = relationship("Recipe", back_populates="meal_logs")

    __table_args__ = (
        CheckConstraint(
            "("
            "food_id IS NOT NULL AND recipe_id IS NULL AND quick_add_name IS NULL"
            ") OR ("
            "food_id IS NULL AND recipe_id IS NOT NULL AND quick_add_name IS NULL"
            ") OR ("
            "food_id IS NULL AND recipe_id IS NULL AND quick_add_name IS NOT NULL"
            ")",
            name="ck_meal_logs_exactly_one_source",
        ),
        CheckConstraint(
            "quick_calories IS NULL OR quick_calories >= 0",
            name="ck_meal_logs_quick_calories_non_negative",
        ),
        CheckConstraint(
            "quick_protein IS NULL OR quick_protein >= 0",
            name="ck_meal_logs_quick_protein_non_negative",
        ),
        CheckConstraint(
            "quick_fat IS NULL OR quick_fat >= 0",
            name="ck_meal_logs_quick_fat_non_negative",
        ),
        CheckConstraint(
            "quick_carbs IS NULL OR quick_carbs >= 0",
            name="ck_meal_logs_quick_carbs_non_negative",
        ),
    )


class ShoppingListItem(TimestampMixin, Base):
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    food_id = Column(Integer, ForeignKey("foods.id", ondelete="SET NULL"), nullable=True, index=True)
    inventory_item_id = Column(
        Integer,
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quantity = Column(Float, default=1.0, nullable=False)
    unit = Column(String(32), default="pcs", nullable=False)
    store = Column(String(120), nullable=True, index=True)
    is_checked = Column(Boolean, default=False, nullable=False, index=True)
    priority = Column(Integer, default=0, nullable=False, index=True)
    notes = Column(Text, nullable=True)

    food = relationship("Food", back_populates="shopping_items")
    inventory_item = relationship("InventoryItem", back_populates="shopping_items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_shopping_quantity_positive"),
        CheckConstraint("priority >= 0", name="ck_shopping_priority_non_negative"),
    )
