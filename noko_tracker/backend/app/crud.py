from typing import Any, Type

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from .services import nutrition_service


def get(db: Session, model: Type[models.Base], object_id: int):
    return db.query(model).filter(model.id == object_id).first()


def get_multi(db: Session, model: Type[models.Base], skip: int = 0, limit: int = 100):
    return db.query(model).offset(skip).limit(limit).all()


def create(db: Session, model: Type[models.Base], obj_in: BaseModel):
    db_obj = model(**obj_in.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def update(db: Session, db_obj: models.Base, obj_in: BaseModel):
    update_data = obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete(db: Session, db_obj: models.Base):
    db.delete(db_obj)
    db.commit()
    return db_obj


def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()


def get_product_unit_by_name(db: Session, name: str):
    normalized_name = name.strip()
    return (
        db.query(models.ProductUnit)
        .filter(func.lower(models.ProductUnit.name) == normalized_name.lower())
        .first()
    )


def get_or_create_product_unit(db: Session, name: str):
    normalized_name = name.strip() or "pcs"
    product_unit = get_product_unit_by_name(db, normalized_name)
    if product_unit is not None:
        return product_unit

    product_unit = models.ProductUnit(name=normalized_name)
    db.add(product_unit)
    db.flush()
    return product_unit


def get_food_by_name_brand(
    db: Session,
    name: str,
    brand: str | None,
    include_archived: bool = False,
):
    exact_query = db.query(models.Food).filter(models.Food.name == name)
    fallback_query = db.query(models.Food).filter(func.lower(models.Food.name) == name.lower())

    if not include_archived:
        exact_query = exact_query.filter(models.Food.is_archived.is_(False))
        fallback_query = fallback_query.filter(models.Food.is_archived.is_(False))

    if brand is None:
        exact_query = exact_query.filter(models.Food.brand.is_(None))
        fallback_query = fallback_query.filter(models.Food.brand.is_(None))
    else:
        exact_query = exact_query.filter(models.Food.brand == brand)
        fallback_query = fallback_query.filter(func.lower(models.Food.brand) == brand.lower())

    return exact_query.first() or fallback_query.first()


def create_recipe(db: Session, obj_in: schemas.RecipeCreate):
    data = obj_in.model_dump(exclude={"ingredients"})
    ingredients = obj_in.ingredients

    db_recipe = models.Recipe(**data)
    db.add(db_recipe)
    db.flush()

    for ingredient in ingredients:
        db.add(
            models.RecipeIngredient(
                recipe_id=db_recipe.id,
                **ingredient.model_dump(),
            )
        )

    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def update_recipe(db: Session, db_recipe: models.Recipe, obj_in: schemas.RecipeUpdate):
    update_data = obj_in.model_dump(exclude_unset=True, exclude={"ingredients"})
    for field, value in update_data.items():
        setattr(db_recipe, field, value)

    if obj_in.ingredients is not None:
        db_recipe.ingredients.clear()
        db.flush()
        for ingredient in obj_in.ingredients:
            db_recipe.ingredients.append(models.RecipeIngredient(**ingredient.model_dump()))

    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    return db_recipe


def recipe_nutrition(recipe: models.Recipe) -> dict[str, Any]:
    total = {
        "calories": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
    }

    for ingredient in recipe.ingredients:
        food = ingredient.food
        grams = nutrition_service.food_amount_in_grams(
            food,
            schemas.normalize_fractional_number(ingredient.quantity),
            ingredient.unit,
        )
        values = nutrition_service.calculate_food_nutrition(food, grams)
        total["calories"] += values["calories"]
        total["protein"] += values["protein"]
        total["carbs"] += values["carbs"]
        total["fat"] += values["fat"]

    servings = schemas.normalize_fractional_number(recipe.servings) or 1.0
    per_serving = {key: value / servings for key, value in total.items()}
    return {"total": total, "per_serving": per_serving}
