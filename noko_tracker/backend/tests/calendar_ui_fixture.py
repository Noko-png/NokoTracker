import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite://"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def test_db():
    with Session(test_engine) as db:
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
