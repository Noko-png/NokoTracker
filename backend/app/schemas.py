import math
import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SIMPLE_FRACTION_RE = re.compile(
    r"^([+-]?\d+(?:[,.]\d+)?)\s*/\s*([+-]?\d+(?:[,.]\d+)?)$"
)
MIXED_FRACTION_RE = re.compile(
    r"^([+-]?\d+(?:[,.]\d+)?)\s+(\d+(?:[,.]\d+)?)\s*/\s*(\d+(?:[,.]\d+)?)$"
)
FRACTIONAL_QUANTITY_DENOMINATORS = (2, 3, 4, 6, 8, 12)
FRACTIONAL_QUANTITY_TOLERANCE = 0.01
QUANTITY_PRECISION = 1_000_000
DEFAULT_FOOD_EMOJI = "🍽️"
DEFAULT_INVENTORY_EMOJI = "📦"
DEFAULT_RECIPE_EMOJI = "🍲"


def normalize_fractional_number(value):
    if value is None or isinstance(value, bool):
        return value

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return value

    if not math.isfinite(numeric_value):
        return value

    sign = -1 if numeric_value < 0 else 1
    absolute_value = abs(numeric_value)
    whole = math.trunc(absolute_value)
    fraction = absolute_value - whole

    if fraction < FRACTIONAL_QUANTITY_TOLERANCE:
        return float(sign * whole)

    best_fraction = None
    for denominator in FRACTIONAL_QUANTITY_DENOMINATORS:
        numerator = round(fraction * denominator)
        difference = abs(fraction - numerator / denominator)
        if best_fraction is None or difference < best_fraction["difference"]:
            best_fraction = {
                "denominator": denominator,
                "difference": difference,
                "numerator": numerator,
            }

    if best_fraction and best_fraction["difference"] < FRACTIONAL_QUANTITY_TOLERANCE:
        if best_fraction["numerator"] == best_fraction["denominator"]:
            whole += 1
            return float(sign * whole)
        normalized = whole + best_fraction["numerator"] / best_fraction["denominator"]
        return round(sign * normalized, 6)

    return round(numeric_value, 6)


def parse_fractional_number(value):
    if not isinstance(value, str):
        return normalize_fractional_number(value)

    text = value.strip()
    if not text:
        return value

    mixed_match = MIXED_FRACTION_RE.match(text)
    if mixed_match:
        whole = float(mixed_match.group(1).replace(",", "."))
        numerator = float(mixed_match.group(2).replace(",", "."))
        denominator = float(mixed_match.group(3).replace(",", "."))
        if denominator == 0:
            raise ValueError("Fraction denominator must not be zero")
        fraction = numerator / denominator
        return normalize_fractional_number(whole - fraction if whole < 0 else whole + fraction)

    fraction_match = SIMPLE_FRACTION_RE.match(text)
    if fraction_match:
        numerator = float(fraction_match.group(1).replace(",", "."))
        denominator = float(fraction_match.group(2).replace(",", "."))
        if denominator == 0:
            raise ValueError("Fraction denominator must not be zero")
        return normalize_fractional_number(numerator / denominator)

    try:
        return normalize_fractional_number(float(value.replace(",", ".")))
    except ValueError:
        return value.replace(",", ".")


def normalize_emoji(value, default: str):
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    return value.strip() or default


def normalize_inventory_emoji(value):
    return normalize_emoji(value, DEFAULT_INVENTORY_EMOJI)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


ThemeName = Literal["light", "dark", "purple", "google"]


def validate_macro_percent_total(
    protein_percent: float | None,
    fat_percent: float | None,
    carbs_percent: float | None,
) -> None:
    if protein_percent is None or fat_percent is None or carbs_percent is None:
        return
    total = protein_percent + fat_percent + carbs_percent
    if abs(total - 100.0) > 0.01:
        raise ValueError("Macro percentages must add up to 100")


class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=255)
    theme: ThemeName = "light"
    daily_calories: float = Field(2500.0, gt=0)
    protein_percent: float = Field(25.0, ge=0, le=100)
    fat_percent: float = Field(30.0, ge=0, le=100)
    carbs_percent: float = Field(45.0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_macro_percentages(self):
        validate_macro_percent_total(
            self.protein_percent,
            self.fat_percent,
            self.carbs_percent,
        )
        return self


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=120)
    password: Optional[str] = Field(None, min_length=1, max_length=255)
    theme: Optional[ThemeName] = None
    daily_calories: Optional[float] = Field(None, gt=0)
    protein_percent: Optional[float] = Field(None, ge=0, le=100)
    fat_percent: Optional[float] = Field(None, ge=0, le=100)
    carbs_percent: Optional[float] = Field(None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_macro_percentages(self):
        validate_macro_percent_total(
            self.protein_percent,
            self.fat_percent,
            self.carbs_percent,
        )
        return self


class UserRead(UserBase, ORMBase):
    id: int


class UserSummary(ORMBase):
    id: int
    username: str


class CalendarGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    color: str = Field("#2563eb", min_length=1, max_length=32)
    suppresses_group_ids: list[int] = Field(default_factory=list)
    hide_from_dashboard_and_month: bool = False
    user_id: Optional[int] = None

    @field_validator("suppresses_group_ids", mode="before")
    @classmethod
    def normalize_suppressed_group_ids(cls, value):
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        normalized: list[int] = []
        seen: set[int] = set()
        for item in value:
            try:
                group_id = int(item)
            except (TypeError, ValueError):
                continue
            if group_id > 0 and group_id not in seen:
                normalized.append(group_id)
                seen.add(group_id)
        return normalized


class CalendarGroupCreate(CalendarGroupBase):
    pass


class CalendarGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    color: Optional[str] = Field(None, min_length=1, max_length=32)
    suppresses_group_ids: Optional[list[int]] = None
    hide_from_dashboard_and_month: Optional[bool] = None
    user_id: Optional[int] = None

    @field_validator("suppresses_group_ids", mode="before")
    @classmethod
    def normalize_suppressed_group_ids(cls, value):
        if value is None:
            return None
        if not isinstance(value, list):
            return value
        normalized: list[int] = []
        seen: set[int] = set()
        for item in value:
            try:
                group_id = int(item)
            except (TypeError, ValueError):
                continue
            if group_id > 0 and group_id not in seen:
                normalized.append(group_id)
                seen.add(group_id)
        return normalized


class CalendarGroupSummary(CalendarGroupBase, ORMBase):
    id: int


class CalendarGroupRead(CalendarGroupSummary):
    created_at: datetime
    updated_at: datetime
    user: Optional[UserSummary] = None


class CalendarEventExclusionCreate(BaseModel):
    event_id: int
    occurrence_start_at: datetime


class CalendarEventExclusionRequest(BaseModel):
    occurrence_start_at: datetime


class CalendarEventExclusionRead(ORMBase):
    id: int
    event_id: int
    occurrence_start_at: datetime


class CalendarEventBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    entry_type: Literal["event", "task"] = "event"
    all_day: bool = False
    is_completed: bool = False
    recurrence_frequency: Literal["none", "daily", "weekly", "monthly", "yearly"] = "none"
    recurrence_interval: int = Field(1, ge=1, le=365)
    recurrence_until: Optional[datetime] = None
    user_id: Optional[int] = None
    group_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_event_dates(self):
        if self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at must be greater than or equal to start_at")
        if self.recurrence_until is not None and self.recurrence_until < self.start_at:
            raise ValueError("recurrence_until must be greater than or equal to start_at")
        return self


class CalendarEventCreate(CalendarEventBase):
    pass


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    entry_type: Optional[Literal["event", "task"]] = None
    all_day: Optional[bool] = None
    is_completed: Optional[bool] = None
    recurrence_frequency: Optional[
        Literal["none", "daily", "weekly", "monthly", "yearly"]
    ] = None
    recurrence_interval: Optional[int] = Field(None, ge=1, le=365)
    recurrence_until: Optional[datetime] = None
    user_id: Optional[int] = None
    group_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_event_dates(self):
        if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
            raise ValueError("end_at must be greater than or equal to start_at")
        if (
            self.start_at is not None
            and self.recurrence_until is not None
            and self.recurrence_until < self.start_at
        ):
            raise ValueError("recurrence_until must be greater than or equal to start_at")
        return self


class CalendarEventRead(CalendarEventBase, ORMBase):
    id: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserSummary] = None
    group: Optional[CalendarGroupSummary] = None
    exclusions: list[CalendarEventExclusionRead] = Field(default_factory=list)


class FoodConversionBase(BaseModel):
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=32)

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str):
        return value.strip()


class FoodConversionCreate(FoodConversionBase):
    pass


class FoodConversionRead(FoodConversionBase, ORMBase):
    id: int
    food_id: int
    created_at: datetime
    updated_at: datetime


class FoodBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    emoji: str = Field(DEFAULT_FOOD_EMOJI, min_length=1, max_length=32)
    brand: Optional[str] = Field(None, max_length=160)
    category: Optional[str] = Field(None, max_length=120)
    storage_location: Optional[str] = Field(None, max_length=120)
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None
    minimum_quantity: float = Field(0.0, ge=0)
    barcode: Optional[str] = Field(None, max_length=128)
    purchase_date: Optional[date] = Field(default_factory=date.today)
    expiry_days: Optional[int] = Field(None, ge=0)
    price: Optional[float] = Field(None, ge=0)
    serving_size: float = Field(100.0, gt=0)
    serving_unit: str = Field("g", min_length=1, max_length=32)
    conversions: list[FoodConversionCreate] = Field(default_factory=list)
    calories_per_100g: float = Field(0.0, ge=0)
    protein_per_100g: float = Field(0.0, ge=0)
    carbs_per_100g: float = Field(0.0, ge=0)
    fat_per_100g: float = Field(0.0, ge=0)

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_food_emoji(cls, value):
        return normalize_emoji(value, DEFAULT_FOOD_EMOJI)

    @field_validator("minimum_quantity", mode="before")
    @classmethod
    def parse_minimum_quantity(cls, value):
        return parse_fractional_number(value)


class FoodCreate(FoodBase):
    pass


class FoodUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    emoji: Optional[str] = Field(None, min_length=1, max_length=32)
    brand: Optional[str] = Field(None, max_length=160)
    category: Optional[str] = Field(None, max_length=120)
    storage_location: Optional[str] = Field(None, max_length=120)
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None
    minimum_quantity: Optional[float] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=128)
    purchase_date: Optional[date] = None
    expiry_days: Optional[int] = Field(None, ge=0)
    price: Optional[float] = Field(None, ge=0)
    serving_size: Optional[float] = Field(None, gt=0)
    serving_unit: Optional[str] = Field(None, min_length=1, max_length=32)
    conversions: Optional[list[FoodConversionCreate]] = None
    calories_per_100g: Optional[float] = Field(None, ge=0)
    protein_per_100g: Optional[float] = Field(None, ge=0)
    carbs_per_100g: Optional[float] = Field(None, ge=0)
    fat_per_100g: Optional[float] = Field(None, ge=0)

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_food_emoji(cls, value):
        return None if value is None else normalize_emoji(value, DEFAULT_FOOD_EMOJI)

    @field_validator("minimum_quantity", mode="before")
    @classmethod
    def parse_minimum_quantity(cls, value):
        return None if value is None else parse_fractional_number(value)


class FoodRead(FoodBase, ORMBase):
    id: int
    is_archived: bool = False
    conversions: list[FoodConversionRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class FoodBarcodeLookupRead(BaseModel):
    barcode: str
    source: Literal["local_food", "local_inventory", "open_food_facts"]
    food: FoodRead
    inventory_items: list["InventoryItemSummary"] = Field(default_factory=list)


class FoodBarcodePreviewRead(BaseModel):
    barcode: str
    source: Literal["local_food", "local_inventory", "open_food_facts"]
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    serving_size: float = 100.0
    serving_unit: str = "g"
    calories_per_100g: float = 0.0
    protein_per_100g: float = 0.0
    fat_per_100g: float = 0.0
    carbs_per_100g: float = 0.0


class FoodSummary(ORMBase):
    id: int
    name: str
    emoji: str = DEFAULT_FOOD_EMOJI
    is_archived: bool = False
    brand: Optional[str] = None
    category: Optional[str] = None
    storage_location: Optional[str] = None
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None
    minimum_quantity: float = 0.0
    barcode: Optional[str] = None
    purchase_date: Optional[date] = None
    expiry_days: Optional[int] = None
    price: Optional[float] = None
    serving_size: float
    serving_unit: str
    conversions: list[FoodConversionRead] = Field(default_factory=list)
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float


class ProductGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    default_expiry_days: Optional[int] = Field(None, ge=0)
    default_storage_location: Optional[str] = Field(None, max_length=120)


class ProductGroupCreate(ProductGroupBase):
    pass


class ProductGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    default_expiry_days: Optional[int] = Field(None, ge=0)
    default_storage_location: Optional[str] = Field(None, max_length=120)


class ProductGroupSummary(ProductGroupBase, ORMBase):
    id: int


class ProductGroupRead(ProductGroupSummary):
    created_at: datetime
    updated_at: datetime


class ProductUnitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)


class ProductUnitCreate(ProductUnitBase):
    pass


class ProductUnitUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=32)


class ProductUnitSummary(ProductUnitBase, ORMBase):
    id: int


class ProductUnitRead(ProductUnitSummary):
    created_at: datetime
    updated_at: datetime


class StorageLocationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class StorageLocationCreate(StorageLocationBase):
    pass


class StorageLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)


class StorageLocationRead(StorageLocationBase, ORMBase):
    id: int
    created_at: datetime
    updated_at: datetime


class InventoryItemBase(BaseModel):
    food_id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=200)
    emoji: str = Field(DEFAULT_INVENTORY_EMOJI, min_length=1, max_length=32)
    brand: Optional[str] = Field(None, max_length=160)
    category: Optional[str] = Field(None, max_length=120)
    quantity: float = Field(0.0, ge=0)
    unit: str = Field("pcs", min_length=1, max_length=32)
    minimum_quantity: float = Field(0.0, ge=0)
    storage_location: Optional[str] = Field(None, max_length=120)
    expiry_days: Optional[int] = Field(None, ge=0)
    purchase_date: date = Field(default_factory=date.today)
    price: Optional[float] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=128)
    image_path: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    serving_size: float = Field(100.0, gt=0)
    serving_unit: str = Field("g", min_length=1, max_length=32)
    calories_per_100g: float = Field(0.0, ge=0)
    protein_per_100g: float = Field(0.0, ge=0)
    carbs_per_100g: float = Field(0.0, ge=0)
    fat_per_100g: float = Field(0.0, ge=0)
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None

    @field_validator("quantity", "minimum_quantity", mode="before")
    @classmethod
    def parse_fractional_quantities(cls, value):
        return parse_fractional_number(value)

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_emoji(cls, value):
        return normalize_inventory_emoji(value)


class InventoryItemCreate(InventoryItemBase):
    pass


class InventoryItemUpdate(BaseModel):
    food_id: Optional[int] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    emoji: Optional[str] = Field(None, min_length=1, max_length=32)
    brand: Optional[str] = Field(None, max_length=160)
    category: Optional[str] = Field(None, max_length=120)
    quantity: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    minimum_quantity: Optional[float] = Field(None, ge=0)
    storage_location: Optional[str] = Field(None, max_length=120)
    expiry_days: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date] = None
    price: Optional[float] = Field(None, ge=0)
    barcode: Optional[str] = Field(None, max_length=128)
    image_path: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    serving_size: Optional[float] = Field(None, gt=0)
    serving_unit: Optional[str] = Field(None, min_length=1, max_length=32)
    calories_per_100g: Optional[float] = Field(None, ge=0)
    protein_per_100g: Optional[float] = Field(None, ge=0)
    carbs_per_100g: Optional[float] = Field(None, ge=0)
    fat_per_100g: Optional[float] = Field(None, ge=0)
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None

    @field_validator("quantity", "minimum_quantity", mode="before")
    @classmethod
    def parse_fractional_quantities(cls, value):
        return parse_fractional_number(value)

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_emoji(cls, value):
        return None if value is None else normalize_inventory_emoji(value)


class InventoryItemRead(InventoryItemBase, ORMBase):
    id: int
    food_id: Optional[int] = None
    expiry_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    food: Optional[FoodSummary] = None
    product_group: Optional[ProductGroupSummary] = None
    product_unit: Optional[ProductUnitSummary] = None


class InventoryItemSummary(ORMBase):
    id: int
    name: str
    emoji: str = DEFAULT_INVENTORY_EMOJI
    brand: Optional[str] = None
    food_id: Optional[int] = None
    quantity: float
    unit: str
    minimum_quantity: float
    storage_location: Optional[str] = None
    expiry_days: Optional[int] = None
    expiry_date: Optional[date] = None
    product_group_id: Optional[int] = None
    product_unit_id: Optional[int] = None
    calories_per_100g: float = 0.0
    protein_per_100g: float = 0.0
    carbs_per_100g: float = 0.0
    fat_per_100g: float = 0.0


class InventoryQuantityChange(BaseModel):
    amount: float = Field(..., gt=0)

    @field_validator("amount", mode="before")
    @classmethod
    def parse_fractional_amount(cls, value):
        return parse_fractional_number(value)


class InventoryWarningsRead(BaseModel):
    low_stock: list[InventoryItemRead]
    expiring_soon: list[InventoryItemRead]
    expired: list[InventoryItemRead]


class RecipeIngredientBase(BaseModel):
    food_id: int
    quantity: float = Field(..., gt=0)
    unit: str = Field("g", min_length=1, max_length=32)
    notes: Optional[str] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class RecipeIngredientCreate(RecipeIngredientBase):
    recipe_id: int


class RecipeIngredientCreateForRecipe(RecipeIngredientBase):
    pass


class RecipeIngredientUpdate(BaseModel):
    food_id: Optional[int] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    notes: Optional[str] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class RecipeIngredientRead(RecipeIngredientBase, ORMBase):
    id: int
    recipe_id: int
    created_at: datetime
    updated_at: datetime
    food: FoodSummary


def normalize_recipe_tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        raw_tags = value.split(",")
    else:
        raw_tags = value

    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        tag = str(raw_tag).strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        tags.append(tag[:48])
        seen.add(key)
    return tags[:20]


class RecipeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    emoji: str = Field(DEFAULT_RECIPE_EMOJI, min_length=1, max_length=32)
    description: Optional[str] = None
    instructions: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    image_path: Optional[str] = None
    servings: float = Field(1.0, gt=0)
    prep_time_minutes: Optional[int] = Field(None, ge=0)
    cook_time_minutes: Optional[int] = Field(None, ge=0)
    created_by_user_id: Optional[int] = None

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_recipe_emoji(cls, value):
        return normalize_emoji(value, DEFAULT_RECIPE_EMOJI)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        return normalize_recipe_tags(value)

    @field_validator("servings", mode="before")
    @classmethod
    def parse_fractional_servings(cls, value):
        return parse_fractional_number(value)


class RecipeCreate(RecipeBase):
    ingredients: list[RecipeIngredientCreateForRecipe] = Field(default_factory=list)


class RecipeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    emoji: Optional[str] = Field(None, min_length=1, max_length=32)
    description: Optional[str] = None
    instructions: Optional[str] = None
    tags: Optional[list[str]] = None
    image_path: Optional[str] = None
    servings: Optional[float] = Field(None, gt=0)
    prep_time_minutes: Optional[int] = Field(None, ge=0)
    cook_time_minutes: Optional[int] = Field(None, ge=0)
    created_by_user_id: Optional[int] = None
    ingredients: Optional[list[RecipeIngredientCreateForRecipe]] = None

    @field_validator("emoji", mode="before")
    @classmethod
    def normalize_recipe_emoji(cls, value):
        return None if value is None else normalize_emoji(value, DEFAULT_RECIPE_EMOJI)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value):
        if value is None:
            return None
        return normalize_recipe_tags(value)

    @field_validator("servings", mode="before")
    @classmethod
    def parse_fractional_servings(cls, value):
        return parse_fractional_number(value)


class RecipeRead(RecipeBase, ORMBase):
    id: int
    is_archived: bool = False
    prepared_food_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UserSummary] = None
    prepared_food: Optional[FoodSummary] = None
    ingredients: list[RecipeIngredientRead] = Field(default_factory=list)


class RecipeSummary(ORMBase):
    id: int
    name: str
    emoji: str = DEFAULT_RECIPE_EMOJI
    is_archived: bool = False
    servings: float


class MealLogBase(BaseModel):
    eaten_at: datetime = Field(default_factory=datetime.utcnow)
    meal_type: Optional[str] = Field(None, max_length=64)
    quantity: float = Field(1.0, gt=0)
    unit: str = Field("serving", min_length=1, max_length=32)
    notes: Optional[str] = None
    quick_add_name: Optional[str] = Field(None, max_length=200)
    quick_calories: Optional[float] = Field(None, ge=0)
    quick_protein: Optional[float] = Field(None, ge=0)
    quick_fat: Optional[float] = Field(None, ge=0)
    quick_carbs: Optional[float] = Field(None, ge=0)
    meal_source: str = Field("manual", min_length=1, max_length=32)
    planned_inventory_deduction: bool = False
    inventory_deducted_at: Optional[datetime] = None
    user_id: Optional[int] = None
    food_id: Optional[int] = None
    recipe_id: Optional[int] = None

    @field_validator(
        "quantity",
        "quick_calories",
        "quick_protein",
        "quick_fat",
        "quick_carbs",
        mode="before",
    )
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)

    @model_validator(mode="after")
    def validate_source(self):
        has_food = self.food_id is not None
        has_recipe = self.recipe_id is not None
        has_quick_add = self.quick_add_name is not None and self.quick_add_name.strip() != ""
        if sum((has_food, has_recipe, has_quick_add)) != 1:
            raise ValueError("Exactly one of food_id, recipe_id or quick_add_name must be set")
        if has_quick_add:
            if (
                (self.quick_calories or 0) == 0
                and (self.quick_protein or 0) == 0
                and (self.quick_fat or 0) == 0
                and (self.quick_carbs or 0) == 0
            ):
                raise ValueError("Quick add needs at least one nutrition value")
        return self


class MealLogCreate(MealLogBase):
    pass


class MealLogUpdate(BaseModel):
    eaten_at: Optional[datetime] = None
    meal_type: Optional[str] = Field(None, max_length=64)
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    notes: Optional[str] = None
    quick_add_name: Optional[str] = Field(None, max_length=200)
    quick_calories: Optional[float] = Field(None, ge=0)
    quick_protein: Optional[float] = Field(None, ge=0)
    quick_fat: Optional[float] = Field(None, ge=0)
    quick_carbs: Optional[float] = Field(None, ge=0)
    meal_source: Optional[str] = Field(None, min_length=1, max_length=32)
    planned_inventory_deduction: Optional[bool] = None
    inventory_deducted_at: Optional[datetime] = None
    user_id: Optional[int] = None
    food_id: Optional[int] = None
    recipe_id: Optional[int] = None

    @field_validator(
        "quantity",
        "quick_calories",
        "quick_protein",
        "quick_fat",
        "quick_carbs",
        mode="before",
    )
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class MealLogRead(MealLogBase, ORMBase):
    id: int
    created_at: datetime
    updated_at: datetime
    user: Optional[UserSummary] = None
    food: Optional[FoodSummary] = None
    recipe: Optional[RecipeSummary] = None


class MealInventoryDeductionItem(BaseModel):
    food_id: int
    name: str
    quantity: float
    unit: str


class MealInventoryDeductionResult(BaseModel):
    meal_log: MealLogRead
    consumed: list[MealInventoryDeductionItem]


class ShoppingListItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    food_id: Optional[int] = None
    inventory_item_id: Optional[int] = None
    quantity: float = Field(1.0, gt=0)
    unit: str = Field("pcs", min_length=1, max_length=32)
    store: Optional[str] = Field(None, max_length=120)
    is_checked: bool = False
    priority: int = Field(0, ge=0)
    notes: Optional[str] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class ShoppingListItemCreate(ShoppingListItemBase):
    pass


class ShoppingListInventoryItemCreate(BaseModel):
    quantity: Optional[float] = Field(None, gt=0)
    priority: int = Field(1, ge=0)
    notes: Optional[str] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class ShoppingListInventoryImportRequest(BaseModel):
    purchase_date: date = Field(default_factory=date.today)
    unknown_item_action: Literal["ask", "create", "delete", "keep"] = "ask"


class ShoppingListItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    food_id: Optional[int] = None
    inventory_item_id: Optional[int] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, min_length=1, max_length=32)
    store: Optional[str] = Field(None, max_length=120)
    is_checked: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None

    @field_validator("quantity", mode="before")
    @classmethod
    def parse_fractional_quantity(cls, value):
        return parse_fractional_number(value)


class ShoppingListItemRead(ShoppingListItemBase, ORMBase):
    id: int
    created_at: datetime
    updated_at: datetime
    food: Optional[FoodSummary] = None
    inventory_item: Optional[InventoryItemSummary] = None


class ShoppingListInventoryImportResult(BaseModel):
    imported_count: int
    created_inventory_items: list[InventoryItemRead]
    updated_inventory_items: list[InventoryItemRead]
    deleted_shopping_item_ids: list[int]
    kept_shopping_item_ids: list[int]
    unknown_items: list[ShoppingListItemRead]
    requires_decision: bool = False
    message: str


class RecipeShoppingListMissingIngredient(BaseModel):
    food_id: int
    name: str
    required_quantity: float
    available_quantity: float
    missing_quantity: float
    unit: str
    action: Literal["created", "updated", "covered"]
    shopping_item: ShoppingListItemRead


class RecipeShoppingListSyncRead(BaseModel):
    recipe_id: int
    recipe_name: str
    missing: list[RecipeShoppingListMissingIngredient]


class RecipePrepareRequest(BaseModel):
    purchase_date: date = Field(default_factory=date.today)
    storage_location: Optional[str] = Field(None, max_length=120)


class RecipePrepareConsumedIngredient(BaseModel):
    food_id: int
    name: str
    quantity: float
    unit: str


class RecipePrepareResult(BaseModel):
    recipe_id: int
    recipe_name: str
    prepared_quantity: float
    prepared_unit: str
    inventory_item: InventoryItemRead
    consumed: list[RecipePrepareConsumedIngredient]


class NutritionValues(BaseModel):
    calories: float
    protein: float
    carbs: float
    fat: float


class CalorieMacroValues(BaseModel):
    calories: float = Field(..., ge=0)
    protein: float = Field(..., ge=0)
    fat: float = Field(..., ge=0)
    carbs: float = Field(..., ge=0)


class RecipeNutritionRead(BaseModel):
    recipe_id: int
    recipe_name: str
    servings: float
    total: NutritionValues
    per_serving: NutritionValues


class DayNutritionRead(BaseModel):
    date: date
    user_id: int
    totals: CalorieMacroValues
    goals: CalorieMacroValues
    remaining: CalorieMacroValues
    percentages: CalorieMacroValues


class CsvImportRequest(BaseModel):
    directory: str = Field(r"u:\Nico\Desktop\db", min_length=1)
    dry_run: bool = False


class CsvImportResult(BaseModel):
    directory: str
    dry_run: bool
    imported: dict[str, dict[str, int]]
    warnings: list[str] = Field(default_factory=list)


ReceiptImportStatus = Literal["ready", "needs_review", "ignored"]


class ReceiptImportPreviewRequest(BaseModel):
    filename: str = Field("Kassenzettel.pdf", min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


class ReceiptFoodSuggestion(BaseModel):
    food: FoodRead
    score: float = Field(..., ge=0, le=1)


class ReceiptImportPreviewItem(BaseModel):
    source_index: int
    raw_name: str
    name: str
    quantity: float = Field(..., ge=0)
    unit: str
    unit_price: Optional[float] = Field(None, ge=0)
    total_price: Optional[float] = Field(None, ge=0)
    tax_class: Optional[str] = None
    status: ReceiptImportStatus
    review_reason: Optional[str] = None
    matched_food_id: Optional[int] = None
    matched_food: Optional[FoodRead] = None
    suggestions: list[ReceiptFoodSuggestion] = Field(default_factory=list)


class ReceiptImportPreview(BaseModel):
    filename: str
    receipt_date: Optional[date] = None
    store_name: Optional[str] = None
    total: Optional[float] = None
    items: list[ReceiptImportPreviewItem]
    imported_count: int
    review_count: int
    ignored_count: int
    warnings: list[str] = Field(default_factory=list)


class ReceiptImportBookItem(BaseModel):
    source_index: int
    raw_name: str = Field(..., min_length=1, max_length=200)
    name: str = Field(..., min_length=1, max_length=200)
    food_id: Optional[int] = None
    quantity: float = Field(..., gt=0)
    unit: str = Field("pcs", min_length=1, max_length=32)
    unit_price: Optional[float] = Field(None, ge=0)
    total_price: Optional[float] = Field(None, ge=0)
    storage_location: Optional[str] = Field(None, max_length=120)
    book: bool = True

    @field_validator("quantity", "unit_price", "total_price", mode="before")
    @classmethod
    def parse_receipt_numbers(cls, value):
        return parse_fractional_number(value)


class ReceiptImportBookRequest(BaseModel):
    purchase_date: date = Field(default_factory=date.today)
    default_storage_location: Optional[str] = Field(None, max_length=120)
    items: list[ReceiptImportBookItem]


class ReceiptImportBookResult(BaseModel):
    booked_count: int
    skipped_count: int
    inventory_items: list[InventoryItemRead]
    warnings: list[str] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    users: int
    foods: int
    recipes: int
    inventory_items: int
    shopping_open_items: int
    upcoming_events: int
    recent_meals: int
