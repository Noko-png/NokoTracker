import os
from threading import Lock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./home_erp.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
DATABASE_LOCK = Lock()


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    from .security import current_principal
    # Requests and full restores must never access different generations of the DB.
    with DATABASE_LOCK:
        db = SessionLocal()
        db.info["principal"] = current_principal.get()
        try:
            yield db
        finally:
            db.close()
