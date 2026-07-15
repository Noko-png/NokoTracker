import math
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import get_db
from ..services import nutrition_service


router = APIRouter(prefix="/recipes", tags=["recipes"])


def get_recipe_or_404(db: Session, recipe_id: int) -> models.Recipe:
    recipe = crud.get(db, models.Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe


def get_ingredient_or_404(db: Session, ingredient_id: int) -> models.RecipeIngredient:
    ingredient = crud.get(db, models.RecipeIngredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")
    return ingredient


def ensure_user_exists(db: Session, user_id: int | None) -> None:
    if user_id is not None and crud.get(db, models.User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")


def ensure_food_exists(db: Session, food_id: int | None) -> None:
    if food_id is not None and crud.get(db, models.Food, food_id) is None:
        raise HTTPException(status_code=404, detail="Food not found")


def ensure_ingredients_are_valid(
    db: Session,
    ingredients: list[schemas.RecipeIngredientCreateForRecipe] | None,
) -> None:
    if ingredients is None:
        return
    for ingredient in ingredients:
        ensure_food_exists(db, ingredient.food_id)


def normalized_unit(value: str) -> str:
    return value.strip().lower()


def normalized_quantity(value: float) -> float:
    return schemas.normalize_fractional_number(value)


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


def quantity_in_unit(food: models.Food, grams: float, unit: str) -> float:
    return normalized_quantity(
        nutrition_service.food_quantity_from_grams(food, grams, unit)
    )


def amount_in_grams(food: models.Food, quantity: float, unit: str) -> float:
    return normalized_quantity(
        nutrition_service.food_amount_in_grams(food, quantity, unit)
    )


def shopping_unit_for_food(food: models.Food, fallback_unit: str) -> str:
    product_unit = food.product_unit.name if food.product_unit is not None else None
    return product_unit or fallback_unit


def shopping_quantity_for_missing_ingredient(
    food: models.Food,
    missing_grams: float,
    unit: str,
) -> float:
    quantity = quantity_in_unit(food, missing_grams, unit)
    if quantity <= 0:
        return 1.0
    return float(max(1, math.ceil(quantity - 0.000001)))


def matching_inventory_items(
    db: Session,
    food_id: int,
) -> list[models.InventoryItem]:
    return (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.food_id == food_id)
        .all()
    )


def open_shopping_item_for_ingredient(
    db: Session,
    food: models.Food,
    unit: str,
    inventory_items: list[models.InventoryItem],
) -> models.ShoppingListItem | None:
    filters = [
        models.ShoppingListItem.food_id == food.id,
        func.lower(models.ShoppingListItem.name) == food.name.lower(),
    ]
    inventory_item_ids = [item.id for item in inventory_items]
    if inventory_item_ids:
        filters.append(models.ShoppingListItem.inventory_item_id.in_(inventory_item_ids))

    return (
        db.query(models.ShoppingListItem)
        .filter(models.ShoppingListItem.is_checked.is_(False))
        .filter(func.lower(models.ShoppingListItem.unit) == normalized_unit(unit))
        .filter(or_(*filters))
        .order_by(models.ShoppingListItem.id)
        .first()
    )


def merge_missing_quantity_into_shopping_item(
    shopping_item: models.ShoppingListItem,
    quantity: float,
    recipe_name: str,
) -> models.ShoppingListItem:
    shopping_item.quantity = normalized_quantity(
        normalized_quantity(shopping_item.quantity) + normalized_quantity(quantity)
    )
    shopping_item.priority = max(shopping_item.priority, 1)
    note = f"Fehlt fuer Gericht: {recipe_name}"
    if not shopping_item.notes:
        shopping_item.notes = note
    elif note not in shopping_item.notes:
            shopping_item.notes = f"{shopping_item.notes}; {note}"
    return shopping_item


def fill_recipe_shopping_item_references(
    shopping_item: models.ShoppingListItem,
    food: models.Food,
    inventory_items: list[models.InventoryItem],
) -> models.ShoppingListItem:
    if shopping_item.food_id is None:
        shopping_item.food_id = food.id
    if shopping_item.inventory_item_id is None and inventory_items:
        shopping_item.inventory_item_id = inventory_items[0].id
    return shopping_item


def recipe_ingredient_requirements(recipe: models.Recipe) -> list[dict]:
    requirements: dict[tuple[int, str], dict] = {}
    for ingredient in recipe.ingredients:
        unit_key = normalized_unit(ingredient.unit)
        key = (ingredient.food_id, unit_key)
        if key not in requirements:
            requirements[key] = {
                "food": ingredient.food,
                "quantity": 0.0,
                "unit": ingredient.unit,
            }
        requirements[key]["quantity"] = normalized_quantity(
            requirements[key]["quantity"] + normalized_quantity(ingredient.quantity)
        )

    return list(requirements.values())


def recipe_ingredient_amount(food: models.Food, quantity: float, unit: str) -> float:
    return nutrition_service.food_amount_in_grams(food, quantity, unit)


def recipe_weight(recipe: models.Recipe) -> float:
    return normalized_quantity(
        sum(
            recipe_ingredient_amount(
                ingredient.food,
                ingredient.quantity,
                ingredient.unit,
            )
            for ingredient in recipe.ingredients
        )
    )


def recipe_prepared_food(
    db: Session,
    recipe: models.Recipe,
    product_unit: models.ProductUnit,
) -> models.Food:
    food = recipe.prepared_food
    if food is None and recipe.prepared_food_id is not None:
        food = crud.get(db, models.Food, recipe.prepared_food_id)
    if food is None:
        food = crud.get_food_by_name_brand(db, recipe.name, "Zubereitet")
    total_nutrition = nutrition_service.calculate_recipe_nutrition(recipe)
    servings = normalized_quantity(recipe.servings) or 1.0
    total_weight = recipe_weight(recipe)
    serving_size = normalized_quantity(total_weight / servings) if total_weight > 0 else 100.0

    if total_weight > 0:
        factor = 100.0 / total_weight
        calories_per_100g = round(total_nutrition["calories"] * factor, 2)
        protein_per_100g = round(total_nutrition["protein"] * factor, 2)
        fat_per_100g = round(total_nutrition["fat"] * factor, 2)
        carbs_per_100g = round(total_nutrition["carbs"] * factor, 2)
    else:
        per_serving = nutrition_service.calculate_recipe_nutrition_per_serving(recipe)
        calories_per_100g = per_serving["calories"]
        protein_per_100g = per_serving["protein"]
        fat_per_100g = per_serving["fat"]
        carbs_per_100g = per_serving["carbs"]

    if food is None:
        food = models.Food(name=recipe.name, brand="Zubereitet")
        db.add(food)

    food.name = recipe.name
    food.emoji = recipe.emoji
    food.is_archived = recipe.is_archived
    food.brand = "Zubereitet"
    food.category = "Gericht"
    food.product_unit_id = product_unit.id
    food.serving_size = serving_size
    food.serving_unit = product_unit.name
    food.calories_per_100g = calories_per_100g
    food.protein_per_100g = protein_per_100g
    food.fat_per_100g = fat_per_100g
    food.carbs_per_100g = carbs_per_100g
    db.flush()
    recipe.prepared_food_id = food.id
    recipe.prepared_food = food
    db.add(recipe)
    db.flush()
    return food


def prepared_inventory_item(
    db: Session,
    food: models.Food,
    product_unit: models.ProductUnit,
) -> models.InventoryItem | None:
    return (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.food_id == food.id)
        .filter(
            or_(
                models.InventoryItem.product_unit_id == product_unit.id,
                func.lower(models.InventoryItem.unit) == product_unit.name.lower(),
            )
        )
        .order_by(models.InventoryItem.id)
        .first()
    )


def apply_prepared_inventory_values(
    inventory_item: models.InventoryItem,
    recipe: models.Recipe,
    food: models.Food,
    product_unit: models.ProductUnit,
    request: schemas.RecipePrepareRequest,
) -> models.InventoryItem:
    inventory_item.name = food.name
    inventory_item.emoji = food.emoji
    inventory_item.brand = food.brand
    inventory_item.category = food.category
    inventory_item.unit = product_unit.name
    inventory_item.minimum_quantity = 0.0
    inventory_item.storage_location = (
        request.storage_location
        or inventory_item.storage_location
        or food.storage_location
    )
    inventory_item.expiry_days = None
    inventory_item.price = None
    inventory_item.barcode = None
    inventory_item.image_path = recipe.image_path
    inventory_item.notes = f"Zubereitet aus Rezept: {recipe.name}"
    inventory_item.food_id = food.id
    inventory_item.product_group_id = food.product_group_id
    inventory_item.product_unit_id = product_unit.id
    inventory_item.serving_size = food.serving_size
    inventory_item.serving_unit = food.serving_unit
    inventory_item.calories_per_100g = food.calories_per_100g
    inventory_item.protein_per_100g = food.protein_per_100g
    inventory_item.carbs_per_100g = food.carbs_per_100g
    inventory_item.fat_per_100g = food.fat_per_100g
    return inventory_item


def sync_recipe_as_food(db: Session, recipe: models.Recipe) -> models.Food:
    product_unit = crud.get_or_create_product_unit(db, "Portion")
    food = recipe_prepared_food(db, recipe, product_unit)
    db.commit()
    db.refresh(recipe)
    db.refresh(food)
    return food


def inventory_items_by_expiry(items: list[models.InventoryItem]) -> list[models.InventoryItem]:
    return sorted(
        items,
        key=lambda item: (
            item.expiry_date is None,
            item.expiry_date or item.purchase_date,
            item.id,
        ),
    )


@router.post("", response_model=schemas.RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(recipe_in: schemas.RecipeCreate, db: Session = Depends(get_db)):
    ensure_user_exists(db, recipe_in.created_by_user_id)
    ensure_ingredients_are_valid(db, recipe_in.ingredients)
    try:
        recipe = crud.create_recipe(db, recipe_in)
        sync_recipe_as_food(db, recipe)
        return recipe
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recipe could not be created") from exc


@router.get("", response_model=list[schemas.RecipeRead])
def list_recipes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
):
    query = db.query(models.Recipe)
    if not include_archived:
        query = query.filter(models.Recipe.is_archived.is_(False))
    return query.offset(skip).limit(limit).all()


@router.get("/{recipe_id}", response_model=schemas.RecipeRead)
def read_recipe(recipe_id: int, db: Session = Depends(get_db)):
    return get_recipe_or_404(db, recipe_id)


@router.patch("/{recipe_id}", response_model=schemas.RecipeRead)
def update_recipe(
    recipe_id: int,
    recipe_in: schemas.RecipeUpdate,
    db: Session = Depends(get_db),
):
    recipe = get_recipe_or_404(db, recipe_id)
    ensure_user_exists(db, recipe_in.created_by_user_id)
    ensure_ingredients_are_valid(db, recipe_in.ingredients)
    try:
        updated_recipe = crud.update_recipe(db, recipe, recipe_in)
        sync_recipe_as_food(db, updated_recipe)
        return updated_recipe
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recipe could not be updated") from exc


@router.post(
    "/{recipe_id}/sync-shopping-list",
    response_model=schemas.RecipeShoppingListSyncRead,
)
def sync_missing_recipe_ingredients_to_shopping_list(
    recipe_id: int,
    db: Session = Depends(get_db),
):
    recipe = get_recipe_or_404(db, recipe_id)
    missing_ingredients = []
    changed_items: list[models.ShoppingListItem] = []

    for requirement in recipe_ingredient_requirements(recipe):
        food = requirement["food"]
        required_quantity = normalized_quantity(requirement["quantity"])
        unit = requirement["unit"]
        shopping_unit = shopping_unit_for_food(food, unit)
        required_grams = amount_in_grams(food, required_quantity, unit)
        inventory_items = matching_inventory_items(db, food.id)
        available_grams = normalized_quantity(
            sum(
                amount_in_grams(item, item.quantity, item.unit)
                for item in inventory_items
            )
        )
        missing_grams = normalized_quantity(required_grams - available_grams)
        missing_quantity = quantity_in_unit(food, missing_grams, unit)
        if missing_grams <= 0.000001:
            continue
        available_quantity = quantity_in_unit(food, available_grams, unit)
        shopping_quantity = shopping_quantity_for_missing_ingredient(
            food,
            missing_grams,
            shopping_unit,
        )

        shopping_item = open_shopping_item_for_ingredient(
            db,
            food,
            shopping_unit,
            inventory_items,
        )
        if shopping_item is None:
            shopping_item = models.ShoppingListItem(
                name=food.name,
                food_id=food.id,
                inventory_item_id=inventory_items[0].id if inventory_items else None,
                quantity=shopping_quantity,
                unit=shopping_unit,
                is_checked=False,
                priority=1,
                notes=f"Fehlt fuer Gericht: {recipe.name}",
            )
            db.add(shopping_item)
            changed_items.append(shopping_item)
            action = "created"
        elif shopping_quantity > 0:
            fill_recipe_shopping_item_references(
                shopping_item,
                food,
                inventory_items,
            )
            merge_missing_quantity_into_shopping_item(
                shopping_item,
                shopping_quantity,
                recipe.name,
            )
            db.add(shopping_item)
            changed_items.append(shopping_item)
            action = "updated"
        else:
            action = "covered"

        missing_ingredients.append(
            {
                "food_id": food.id,
                "name": food.name,
                "required_quantity": required_quantity,
                "available_quantity": available_quantity,
                "missing_quantity": missing_quantity,
                "unit": unit,
                "action": action,
                "shopping_item": shopping_item,
            }
        )

    try:
        if changed_items:
            db.commit()
            for item in changed_items:
                db.refresh(item)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Shopping list items could not be generated",
        ) from exc

    return {
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "missing": missing_ingredients,
    }


@router.post(
    "/{recipe_id}/prepare",
    response_model=schemas.RecipePrepareResult,
    status_code=status.HTTP_201_CREATED,
)
def prepare_recipe_from_inventory(
    recipe_id: int,
    prepare_in: schemas.RecipePrepareRequest | None = None,
    db: Session = Depends(get_db),
):
    recipe = get_recipe_or_404(db, recipe_id)
    request = prepare_in or schemas.RecipePrepareRequest()
    requirements = recipe_ingredient_requirements(recipe)
    if not requirements:
        raise HTTPException(
            status_code=422,
            detail="Gericht kann ohne Zutaten nicht zubereitet werden",
        )

    requirement_rows: list[dict] = []
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

        requirement_rows.append(
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

    consumed: list[dict] = []
    try:
        for row in requirement_rows:
            remaining_grams = normalized_quantity(row["required_grams"])
            for item in row["inventory_items"]:
                if remaining_grams <= 0.000001:
                    break
                item_quantity = normalized_quantity(item.quantity)
                item_grams = amount_in_grams(item, item_quantity, item.unit)
                consumed_grams = min(item_grams, remaining_grams)
                consumed_quantity = quantity_in_unit(item, consumed_grams, item.unit)
                item.quantity = normalized_quantity(item_quantity - consumed_quantity)
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

        product_unit = crud.get_or_create_product_unit(db, "Portion")
        food = recipe_prepared_food(db, recipe, product_unit)
        prepared_quantity = normalized_quantity(recipe.servings)
        inventory_item = prepared_inventory_item(db, food, product_unit)
        if inventory_item is None:
            inventory_item = models.InventoryItem(
                quantity=0.0,
                purchase_date=request.purchase_date,
            )

        inventory_item.quantity = normalized_quantity(
            normalized_quantity(inventory_item.quantity) + prepared_quantity
        )
        apply_prepared_inventory_values(
            inventory_item,
            recipe,
            food,
            product_unit,
            request,
        )
        db.add(inventory_item)
        db.commit()
        db.refresh(inventory_item)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Gericht konnte nicht zubereitet gebucht werden",
        ) from exc

    return {
        "recipe_id": recipe.id,
        "recipe_name": recipe.name,
        "prepared_quantity": prepared_quantity,
        "prepared_unit": product_unit.name,
        "inventory_item": inventory_item,
        "consumed": consumed,
    }


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    keep_reference: bool = Query(False),
    db: Session = Depends(get_db),
):
    recipe = get_recipe_or_404(db, recipe_id)
    if keep_reference:
        recipe.is_archived = True
        if recipe.prepared_food is not None:
            recipe.prepared_food.is_archived = True
            db.add(recipe.prepared_food)
        db.add(recipe)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        crud.delete(db, recipe)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Recipe is still referenced. Use keep_reference=true to archive it.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{recipe_id}/ingredients",
    response_model=schemas.RecipeIngredientRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recipe_ingredient(
    recipe_id: int,
    ingredient_in: schemas.RecipeIngredientCreateForRecipe,
    db: Session = Depends(get_db),
):
    recipe = get_recipe_or_404(db, recipe_id)
    ensure_food_exists(db, ingredient_in.food_id)
    ingredient = schemas.RecipeIngredientCreate(recipe_id=recipe_id, **ingredient_in.model_dump())
    try:
        created_ingredient = crud.create(db, models.RecipeIngredient, ingredient)
        sync_recipe_as_food(db, recipe)
        db.refresh(created_ingredient)
        return created_ingredient
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recipe ingredient could not be created") from exc


@router.get("/{recipe_id}/ingredients", response_model=list[schemas.RecipeIngredientRead])
def list_recipe_ingredients(recipe_id: int, db: Session = Depends(get_db)):
    recipe = get_recipe_or_404(db, recipe_id)
    return recipe.ingredients


@router.get("/ingredients/{ingredient_id}", response_model=schemas.RecipeIngredientRead)
def read_recipe_ingredient(ingredient_id: int, db: Session = Depends(get_db)):
    return get_ingredient_or_404(db, ingredient_id)


@router.patch("/ingredients/{ingredient_id}", response_model=schemas.RecipeIngredientRead)
def update_recipe_ingredient(
    ingredient_id: int,
    ingredient_in: schemas.RecipeIngredientUpdate,
    db: Session = Depends(get_db),
):
    ingredient = get_ingredient_or_404(db, ingredient_id)
    ensure_food_exists(db, ingredient_in.food_id)
    recipe_id = ingredient.recipe_id
    try:
        updated_ingredient = crud.update(db, ingredient, ingredient_in)
        recipe = get_recipe_or_404(db, recipe_id)
        sync_recipe_as_food(db, recipe)
        db.refresh(updated_ingredient)
        return updated_ingredient
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Recipe ingredient could not be updated") from exc


@router.delete("/ingredients/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe_ingredient(ingredient_id: int, db: Session = Depends(get_db)):
    ingredient = get_ingredient_or_404(db, ingredient_id)
    recipe_id = ingredient.recipe_id
    crud.delete(db, ingredient)
    recipe = get_recipe_or_404(db, recipe_id)
    sync_recipe_as_food(db, recipe)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
