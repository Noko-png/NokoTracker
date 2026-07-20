from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url
from starlette.background import BackgroundTask

from .. import schemas
from ..database import DATABASE_URL, engine


router = APIRouter(prefix="/database", tags=["database"])

EXPECTED_TABLES = {
    "users",
    "foods",
    "inventory_items",
    "recipes",
    "shopping_list_items",
}


def sqlite_database_path() -> Path:
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("sqlite"):
        raise HTTPException(
            status_code=400,
            detail="Datenbank-Import und -Export wird aktuell nur fuer SQLite unterstuetzt.",
        )
    if not url.database or url.database == ":memory:":
        raise HTTPException(
            status_code=400,
            detail="Diese SQLite-Datenbank liegt nicht als Datei vor.",
        )

    path = Path(url.database)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def backup_sqlite_database(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(source_path))
    try:
        target = sqlite3.connect(str(target_path))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def validate_sqlite_database(path: Path) -> None:
    try:
        connection = sqlite3.connect(str(path))
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("SQLite integrity_check fehlgeschlagen.")

            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("Die hochgeladene Datei ist keine gueltige SQLite-Datenbank.") from exc

    if not EXPECTED_TABLES.intersection(table_names):
        raise ValueError("Die Datenbank sieht nicht wie eine NokoTracker-Datenbank aus.")


def remove_sqlite_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()


@router.get("/export")
def export_database():
    db_path = sqlite_database_path()
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Datenbankdatei wurde nicht gefunden.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        prefix=f"noko-tracker-{timestamp}-",
        suffix=".db",
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        backup_sqlite_database(db_path, temp_path)
    except sqlite3.DatabaseError as exc:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Datenbank konnte nicht exportiert werden.") from exc

    return FileResponse(
        temp_path,
        filename=f"noko-tracker-{timestamp}.db",
        media_type="application/vnd.sqlite3",
        background=BackgroundTask(lambda: temp_path.unlink(missing_ok=True)),
    )


@router.post("/import", response_model=schemas.DatabaseImportResult)
async def import_database(file: UploadFile = File(...)):
    db_path = sqlite_database_path()
    filename = Path(file.filename or "noko-tracker-import.db").name
    if not filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
        raise HTTPException(
            status_code=422,
            detail="Bitte eine SQLite-Datenbank mit .db, .sqlite oder .sqlite3 hochladen.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as handle:
        upload_path = Path(handle.name)
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)

    try:
        validate_sqlite_database(upload_path)
    except ValueError as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.backup-{timestamp}")
    try:
        engine.dispose()
        if db_path.exists():
            backup_sqlite_database(db_path, backup_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        remove_sqlite_sidecars(db_path)
        shutil.copy2(upload_path, db_path)
        remove_sqlite_sidecars(db_path)
        engine.dispose()
    except (OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(status_code=500, detail="Datenbank konnte nicht importiert werden.") from exc
    finally:
        upload_path.unlink(missing_ok=True)

    return schemas.DatabaseImportResult(
        filename=filename,
        backup_path=str(backup_path) if backup_path.exists() else None,
        message="Datenbank importiert. Bitte die Seite neu laden.",
    )
