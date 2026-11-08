"""Standalone browser-test server with disposable SQLite files, never user data."""
import os
import sys
import tempfile
from pathlib import Path

directory = tempfile.TemporaryDirectory(prefix="noko-database-ui-")
root = Path(directory.name).resolve()
os.environ["DATABASE_URL"] = "sqlite:///" + (root / "current.db").as_posix()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.responses import FileResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.database import Base, DATABASE_LOCK, engine
from app.main import app
from app.routers import recipes

source_path = root / "source.db"
source_engine = create_engine("sqlite:///" + source_path.as_posix())
Base.metadata.create_all(source_engine)
with Session(source_engine) as db:
    db.add(models.User(id=1, username="Test"))
    db.add(models.Food(id=1, name="Quellzutat", brand="Testmarke", fiber_per_100g=4.25))
    db.add(models.Recipe(id=1, name="Importrezept", instructions="Schritt 1", servings=2, tags=["Test"]))
    db.add(models.Recipe(id=2, name="Nicht importieren"))
    db.flush()
    db.add(models.RecipeIngredient(recipe_id=1, food_id=1, quantity=125.25, unit="g"))
    db.add(models.WeightEntry(user_id=1, weight_kg=80))
    db.commit()
source_engine.dispose()


@app.post("/__database_test__/reset")
def reset_database():
    with DATABASE_LOCK:
        engine.dispose()
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(models.User(id=42, username="Test"))
            db.add(models.Food(id=7, name="Vorhandene Zutat", calories_per_100g=200))
            recipe = models.Recipe(
                id=7, name="Vorhandenes Rezept", emoji="🥘", servings=2.5, tags=["Original"],
                instructions="Vorbereiten.\n\nKochen.", description="Originalbeschreibung",
                prep_time_minutes=10, cook_time_minutes=20, created_by_user_id=42,
            )
            db.add(recipe)
            db.flush()
            db.add(models.RecipeIngredient(recipe_id=7, food_id=7, quantity=125.25, unit="g", notes="Fein schneiden"))
            db.add(models.WeightEntry(user_id=42, weight_kg=99))
            db.commit()
            recipes.sync_recipe_as_food(db, recipe)
    return {"fixture": "database-transfer-disposable"}


@app.get("/__database_test__/source")
def source_database():
    return FileResponse(source_path, media_type="application/vnd.sqlite3")


@app.post("/__database_test__/many-recipes")
def many_recipes():
    with DATABASE_LOCK, Session(engine) as db:
        db.add_all(models.Recipe(name=f"ZZ Testrezept {number}") for number in range(500))
        db.commit()
    return {"recipes": 501}


reset_database()
