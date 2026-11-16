import os
import stat
from pathlib import Path
from threading import Lock

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import declarative_base, sessionmaker

from .local_paths import resolve_local_path


def local_sqlite_configuration(value: str) -> tuple[URL, Path | None]:
    error = "DATABASE_URL muss eine lokale SQLite-Datei oder eine SQLite-In-Memory-Datenbank angeben."
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError(error) from None
    if (
        url.drivername not in {"sqlite", "sqlite+pysqlite"}
        or any(part is not None for part in (url.username, url.password, url.host, url.port))
        or "uri" in url.query
    ):
        raise ValueError(error)
    if not url.database or url.database == ":memory:":
        return url, None
    if url.database.lower().startswith("file:"):
        raise ValueError(error)
    path = resolve_local_path(url.database)
    return url.set(database=str(path)), path


def prepare_private_sqlite_file(path: Path) -> None:
    if os.name != "posix":
        return
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Die SQLite-Datenbank muss eine regulaere Datei sein.")
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./home_erp.db")
engine_url, DATABASE_PATH = local_sqlite_configuration(DATABASE_URL)
if DATABASE_PATH is not None:
    prepare_private_sqlite_file(DATABASE_PATH)

engine = create_engine(engine_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
DATABASE_LOCK = Lock()


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
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
