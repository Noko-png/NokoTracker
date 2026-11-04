import os
import sys
from pathlib import Path
from threading import Lock

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app import models
from app.database import Base, get_db
from app.main import app
from app.routers import foods


def test_ean_product(barcode):
    # Deterministic EAN data: browser tests never call an external service.
    if barcode == "5012345678900":
        raise HTTPException(502, "EAN-Suche momentan nicht erreichbar")
    if barcode != "0012345678905":
        return None
    return {
        "product_name_de": "EAN Testdrink", "brands": "EAN Testmarke",
        "categories": "Getraenke", "serving_size": "250 ml",
        "nutriments": {"energy-kcal_100g": 46, "proteins_100g": 1.1,
                       "fat_100g": 1.5, "carbohydrates_100g": 6.8,
                       "fiber_100g": 0.75, "sugars_100g": 4.2, "caffeine_100g": 0.032},
    }


foods.open_food_facts_product = test_ean_product

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
test_db_lock = Lock()


def test_db():
    # StaticPool shares one SQLite connection across concurrent browser requests.
    with test_db_lock, Session(test_engine) as db:
        yield db


app.dependency_overrides[get_db] = test_db


@app.post("/__calendar_test__/reset")
def reset_calendar():
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as db:
        db.add(models.User(id=1, username="Kalendertest", password="test"))
        db.add(models.CalendarGroup(id=1, name="Arbeit", color="#3875ce"))
        db.add(models.CalendarGroup(
            id=2, name="Urlaub", color="#d4476f", suppresses_group_ids=[1]
        ))
        db.commit()
    return {"fixture": "calendar-create-memory"}


reset_calendar()
