from datetime import datetime
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..services import nutrition_service


router = APIRouter(prefix="/meals/logs", tags=["meals"])


def get_meal_log_or_404(db: Session, meal_log_id: int) -> models.MealLog:
    meal_log = crud.get(db, models.MealLog, meal_log_id)
    if meal_log is None:
        raise HTTPException(status_code=404, detail="Meal log not found")
    return meal_log


def ensure_reference_exists(db: Session, model: type[models.Base], object_id: int | None, label: str) -> None:
    if object_id is not None and crud.get(db, model, object_id) is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def normalize_quick_add_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def quick_values_from_patch(patch: dict, meal_log: models.MealLog | None = None) -> tuple[float, float, float, float]:
    return (
        patch.get("quick_calories", getattr(meal_log, "quick_calories", None)) or 0,
        patch.get("quick_protein", getattr(meal_log, "quick_protein", None)) or 0,
        patch.get("quick_fat", getattr(meal_log, "quick_fat", None)) or 0,
        patch.get("quick_carbs", getattr(meal_log, "quick_carbs", None)) or 0,
    )


def ensure_quick_add_has_values(
    quick_add_name: str | None,
    quick_calories: float,
    quick_protein: float,
    quick_fat: float,
    quick_carbs: float,
) -> None:
    if quick_add_name is not None and all(
        value == 0 for value in (quick_calories, quick_protein, quick_fat, quick_carbs)
    ):
        raise HTTPException(status_code=422, detail="Quick add needs at least one nutrition value")


def validate_meal_log_references(
    db: Session,
    user_id: int | None,
    food_id: int | None,
    recipe_id: int | None,
    quick_add_name: str | None,
) -> None:
    ensure_reference_exists(db, models.User, user_id, "User")
    ensure_reference_exists(db, models.Food, food_id, "Food")
    ensure_reference_exists(db, models.Recipe, recipe_id, "Recipe")
    has_quick_add = quick_add_name is not None and quick_add_name.strip() != ""
    if sum((food_id is not None, recipe_id is not None, has_quick_add)) != 1:
        raise HTTPException(
            status_code=422,
            detail="Exactly one of food_id, recipe_id or quick_add_name must be set",
        )


def normalized_unit(value: str | None) -> str:
    return (value or "").strip().lower()


def normalized_quantity(value: float) -> float:
    normalized = schemas.normalize_fractional_number(value)
    return float(normalized) if isinstance(normalized, (int, float)) else 0.0


def format_quantity(value: float) -> str:
    normalized = normalized_quantity(value)
    fraction = Fraction(normalized).limit_denominator(12)
    if abs(float(fraction) - normalized) <= 0.000001:
        if fraction.denominator == 1:
            return str(fraction.numerator)
        if abs(fraction.numerator) > fraction.denominator:
            whole = fraction.numerator // fraction.denominator
            remainder = abs(fraction.numerator % fraction.denominator)
            return f"{whole} {remainder}/{fraction.denominator}"
        return f"{fraction.numerator}/{fraction.denominator}"
    return str(normalized)


def quantity_in_unit(food: models.Food | models.InventoryItem, grams: float, unit: str) -> float:
    return normalized_quantity(
        nutrition_service.food_quantity_from_grams(food, grams, unit)
    )


def amount_in_grams(food: models.Food | models.InventoryItem, quantity: float, unit: str) -> float:
    return normalized_quantity(
        nutrition_service.food_amount_in_grams(food, quantity, unit)
    )


def inventory_items_by_expiry(items: list[models.InventoryItem]) -> list[models.InventoryItem]:
    return sorted(
        items,
        key=lambda item: (
            item.expiry_date is None,
            item.expiry_date or item.purchase_date,
            item.id,
        ),
    )


def matching_inventory_items(
    db: Session,
    food_id: int,
) -> list[models.InventoryItem]:
    return (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.food_id == food_id)
        .all()
    )


def recipe_multiplier_for_meal_log(meal_log: models.MealLog) -> float:
    quantity = normalized_quantity(meal_log.quantity)
    if normalized_unit(meal_log.unit) in {"recipe", "recipes", "gericht", "gerichte"}:
        return quantity
    servings = normalized_quantity(meal_log.recipe.servings if meal_log.recipe else 1.0) or 1.0
    return quantity / servings


def meal_log_inventory_requirements(meal_log: models.MealLog) -> list[dict]:
    if meal_log.quick_add_name is not None:
        raise HTTPException(
            status_code=422,
            detail="Quick-Add kann nicht aus dem Bestand gebucht werden",
        )

    if meal_log.food_id is not None and meal_log.food is not None:
        return [
            {
                "food": meal_log.food,
                "quantity": normalized_quantity(meal_log.quantity),
                "unit": meal_log.unit,
            }
        ]

    if meal_log.recipe_id is not None and meal_log.recipe is not None:
        multiplier = recipe_multiplier_for_meal_log(meal_log)
        requirements: dict[tuple[int, str], dict] = {}
        for ingredient in meal_log.recipe.ingredients:
            unit_key = normalized_unit(ingredient.unit)
            key = (ingredient.food_id, unit_key)
            if key not in requirements:
                requirements[key] = {
                    "food": ingredient.food,
                    "quantity": 0.0,
                    "unit": ingredient.unit,
                }
            requirements[key]["quantity"] = normalized_quantity(
                requirements[key]["quantity"]
                + normalized_quantity(ingredient.quantity) * multiplier
            )

        if not requirements:
            raise HTTPException(
                status_code=422,
                detail="Gericht kann ohne Zutaten nicht aus dem Bestand gebucht werden",
            )
        return list(requirements.values())

    raise HTTPException(status_code=422, detail="Meal log has no inventory source")


def inventory_deduction_rows(db: Session, requirements: list[dict]) -> list[dict]:
    rows: list[dict] = []
    shortages: list[str] = []

    for requirement in requirements:
        food = requirement["food"]
        required_quantity = normalized_quantity(requirement["quantity"])
        unit = requirement["unit"]
        required_grams = amount_in_grams(food, required_quantity, unit)
        inventory_items = inventory_items_by_expiry(
            matching_inventory_items(db, food.id)
        )
        available_grams = normalized_quantity(
            sum(
                amount_in_grams(item, item.quantity, item.unit)
                for item in inventory_items
            )
        )
        missing_grams = normalized_quantity(required_grams - available_grams)
        if missing_grams > 0.000001:
            missing_quantity = quantity_in_unit(food, missing_grams, unit)
            shortages.append(
                f"{food.name}: {format_quantity(missing_quantity)} {unit}"
            )

        rows.append(
            {
                "food": food,
                "required_quantity": required_quantity,
                "required_grams": required_grams,
                "unit": unit,
                "inventory_items": inventory_items,
            }
        )

    if shortages:
        raise HTTPException(
            status_code=422,
            detail="Nicht genug Bestand: " + "; ".join(shortages),
        )

    return rows


def normalize_meal_log_source_payload(patch: dict) -> dict:
    quick_add_name = normalize_quick_add_name(patch.get("quick_add_name"))
    if "quick_add_name" in patch:
        patch["quick_add_name"] = quick_add_name

    if quick_add_name is not None:
        patch["food_id"] = None
        patch["recipe_id"] = None
        patch.setdefault("quantity", 1.0)
        patch.setdefault("unit", "quick")
    elif patch.get("food_id") is not None:
        patch["recipe_id"] = None
        patch["quick_add_name"] = None
        patch["quick_calories"] = None
        patch["quick_protein"] = None
        patch["quick_fat"] = None
        patch["quick_carbs"] = None
    elif patch.get("recipe_id") is not None:
        patch["food_id"] = None
        patch["quick_add_name"] = None
        patch["quick_calories"] = None
        patch["quick_protein"] = None
        patch["quick_fat"] = None
        patch["quick_carbs"] = None

    return patch


@router.post("", response_model=schemas.MealLogRead, status_code=status.HTTP_201_CREATED)
def create_meal_log(meal_log_in: schemas.MealLogCreate, db: Session = Depends(get_db)):
    payload = normalize_meal_log_source_payload(meal_log_in.model_dump())
    quick_calories, quick_protein, quick_fat, quick_carbs = quick_values_from_patch(payload)
    validate_meal_log_references(
        db,
        payload.get("user_id"),
        payload.get("food_id"),
        payload.get("recipe_id"),
        payload.get("quick_add_name"),
    )
    ensure_quick_add_has_values(
        payload.get("quick_add_name"),
        quick_calories,
        quick_protein,
        quick_fat,
        quick_carbs,
    )
    try:
        db_obj = models.MealLog(**payload)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Meal log could not be created") from exc


@router.get("", response_model=list[schemas.MealLogRead])
def list_meal_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_multi(db, models.MealLog, skip=skip, limit=limit)


@router.get("/{meal_log_id}", response_model=schemas.MealLogRead)
def read_meal_log(meal_log_id: int, db: Session = Depends(get_db)):
    return get_meal_log_or_404(db, meal_log_id)


@router.post(
    "/{meal_log_id}/deduct-inventory",
    response_model=schemas.MealInventoryDeductionResult,
)
def deduct_meal_log_from_inventory(meal_log_id: int, db: Session = Depends(get_db)):
    meal_log = get_meal_log_or_404(db, meal_log_id)
    if meal_log.inventory_deducted_at is not None:
        raise HTTPException(
            status_code=409,
            detail="Bestand wurde fuer diesen Eintrag bereits gebucht",
        )

    requirements = meal_log_inventory_requirements(meal_log)
    rows = inventory_deduction_rows(db, requirements)
    consumed: list[dict] = []

    try:
        for row in rows:
            remaining_grams = normalized_quantity(row["required_grams"])
            for item in row["inventory_items"]:
                if remaining_grams <= 0.000001:
                    break
                item_quantity = normalized_quantity(item.quantity)
                item_grams = amount_in_grams(item, item_quantity, item.unit)
                if item_grams <= 0.000001:
                    continue
                consumed_grams = min(item_grams, remaining_grams)
                consumed_quantity = quantity_in_unit(item, consumed_grams, item.unit)
                item.quantity = normalized_quantity(
                    max(0.0, item_quantity - consumed_quantity)
                )
                remaining_grams = normalized_quantity(remaining_grams - consumed_grams)
                db.add(item)

            consumed.append(
                {
                    "food_id": row["food"].id,
                    "name": row["food"].name,
                    "quantity": row["required_quantity"],
                    "unit": row["unit"],
                }
            )

        meal_log.planned_inventory_deduction = True
        meal_log.inventory_deducted_at = datetime.utcnow()
        db.add(meal_log)
        db.commit()
        db.refresh(meal_log)
        return {"meal_log": meal_log, "consumed": consumed}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Bestand konnte fuer den Kalorientracker-Eintrag nicht gebucht werden",
        ) from exc


@router.patch("/{meal_log_id}", response_model=schemas.MealLogRead)
def update_meal_log(
    meal_log_id: int,
    meal_log_in: schemas.MealLogUpdate,
    db: Session = Depends(get_db),
):
    meal_log = get_meal_log_or_404(db, meal_log_id)
    patch = normalize_meal_log_source_payload(meal_log_in.model_dump(exclude_unset=True))
    next_user_id = patch.get("user_id", meal_log.user_id)
    next_food_id = patch.get("food_id", meal_log.food_id)
    next_recipe_id = patch.get("recipe_id", meal_log.recipe_id)
    next_quick_add_name = normalize_quick_add_name(
        patch.get("quick_add_name", meal_log.quick_add_name)
    )
    quick_calories, quick_protein, quick_fat, quick_carbs = quick_values_from_patch(patch, meal_log)
    validate_meal_log_references(
        db,
        next_user_id,
        next_food_id,
        next_recipe_id,
        next_quick_add_name,
    )
    ensure_quick_add_has_values(
        next_quick_add_name,
        quick_calories,
        quick_protein,
        quick_fat,
        quick_carbs,
    )
    try:
        for field, value in patch.items():
            setattr(meal_log, field, value)
        db.add(meal_log)
        db.commit()
        db.refresh(meal_log)
        return meal_log
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Meal log could not be updated") from exc


@router.delete("/{meal_log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_log(meal_log_id: int, db: Session = Depends(get_db)):
    meal_log = get_meal_log_or_404(db, meal_log_id)
    crud.delete(db, meal_log)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
