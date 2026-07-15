from datetime import date as date_type, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..services import nutrition_service


router = APIRouter(prefix="/nutrition", tags=["nutrition"])


def empty_values() -> dict[str, float]:
    return {
        "calories": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
    }


def add_values(target: dict[str, float], source: dict[str, float], multiplier: float = 1.0) -> None:
    for key in target:
        target[key] += source[key] * multiplier


def round_values(values: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 2) for key, value in values.items()}


def food_values(food: models.Food, quantity: float = 100.0, unit: str = "g") -> dict[str, float]:
    grams = nutrition_service.food_amount_in_grams(food, quantity, unit)
    return nutrition_service.calculate_food_nutrition(food, grams)


def get_food_or_404(db: Session, food_id: int) -> models.Food:
    food = crud.get(db, models.Food, food_id)
    if food is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return food


def get_recipe_or_404(db: Session, recipe_id: int) -> models.Recipe:
    recipe = crud.get(db, models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


@router.get("/foods/{food_id}", response_model=schemas.NutritionValues)
def read_food_nutrition(
    food_id: int,
    quantity: float = Query(100.0, gt=0),
    unit: str = Query("g", min_length=1),
    db: Session = Depends(get_db),
):
    food = get_food_or_404(db, food_id)
    return round_values(food_values(food, quantity=quantity, unit=unit))


@router.get("/recipes/{recipe_id}", response_model=schemas.RecipeNutritionRead)
def read_recipe_nutrition(recipe_id: int, db: Session = Depends(get_db)):
    recipe = get_recipe_or_404(db, recipe_id)
    values = crud.recipe_nutrition(recipe)
    return {
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "servings": recipe.servings,
        "total": round_values(values["total"]),
        "per_serving": round_values(values["per_serving"]),
    }


@router.get("/meals/summary", response_model=schemas.NutritionValues)
def read_meal_nutrition_summary(
    user_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.MealLog)
    if user_id is not None:
        query = query.filter(models.MealLog.user_id == user_id)
    if start_at is not None:
        query = query.filter(models.MealLog.eaten_at >= start_at)
    if end_at is not None:
        query = query.filter(models.MealLog.eaten_at <= end_at)

    total = empty_values()
    for meal_log in query.all():
        add_values(total, nutrition_service.calculate_meal_log_nutrition(meal_log))

    return round_values(total)


@router.get("/day", response_model=schemas.DayNutritionRead)
def read_day_nutrition(
    user_id: int = Query(..., gt=0),
    date: date_type = Query(...),
    db: Session = Depends(get_db),
):
    try:
        return nutrition_service.calculate_day_nutrition(user_id=user_id, date=date, db=db)
    except nutrition_service.UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
