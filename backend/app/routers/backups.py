from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.engine import make_url
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from sqlalchemy import create_engine

from .. import models, schemas
from ..database import DATABASE_URL, DATABASE_LOCK, engine
from ..upload_limits import MAX_DATABASE_BYTES, copy_upload


router = APIRouter(prefix="/database", tags=["database"])

EXPECTED_TABLES = set(models.Base.metadata.tables)
MAX_SQLITE_VALUE_BYTES = 12 * 1024 * 1024

TRAINING_TABLES = {
    "training_exercises",
    "training_plans",
    "training_session_sets",
    "training_sessions",
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


def count_database_tables(
    connection: sqlite3.Connection,
    table_names: set[str],
) -> dict[str, int]:
    table_counts: dict[str, int] = {}
    for table_name in sorted(EXPECTED_TABLES.intersection(table_names)):
        count = connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
        table_counts[table_name] = int(count[0] if count else 0)
    return table_counts


def validate_sqlite_database(path: Path) -> tuple[dict[str, int], list[str]]:
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_SQLITE_VALUE_BYTES)
            connection.execute("PRAGMA trusted_schema=OFF")
            deadline = time.monotonic() + 10
            connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            objects = connection.execute("SELECT type, name, sql FROM sqlite_master").fetchall()
            if any(kind in {"trigger", "view"} or (sql and "CREATE VIRTUAL TABLE" in sql.upper()) for kind, name, sql in objects):
                raise ValueError("Sicherungen mit Triggern, Views oder virtuellen Tabellen sind nicht erlaubt.")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("SQLite integrity_check fehlgeschlagen.")

            table_names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            missing_tables = sorted(EXPECTED_TABLES - table_names)
            if missing_tables:
                raise ValueError(
                    "Die Datenbank ist unvollstaendig oder nicht kompatibel. Fehlende Tabellen: "
                    + ", ".join(missing_tables)
                )

            for table in models.Base.metadata.sorted_tables:
                columns = {
                    row[1] for row in connection.execute(f'PRAGMA table_info("{table.name}")')
                }
                optional_columns = {"home_assistant_user_id"} if table.name == "users" else set()
                missing_columns = sorted(set(table.columns.keys()) - columns - optional_columns)
                if missing_columns:
                    raise ValueError(
                        f"Die Datenbank ist nicht kompatibel. Fehlende Spalten in {table.name}: "
                        + ", ".join(missing_columns)
                    )

            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Die Datenbank enthaelt ungueltige Datenverknuepfungen.")

            # Check the application's relationships even if the uploaded schema
            # omitted its FOREIGN KEY constraints. Identifiers come from our models.
            for table in models.Base.metadata.sorted_tables:
                for foreign_key in table.foreign_keys:
                    parent = foreign_key.column
                    child = foreign_key.parent
                    invalid_reference = connection.execute(
                        f'SELECT 1 FROM "{table.name}" AS child '
                        f'LEFT JOIN "{parent.table.name}" AS parent '
                        f'ON child."{child.name}" = parent."{parent.name}" '
                        f'WHERE child."{child.name}" IS NOT NULL '
                        f'AND parent."{parent.name}" IS NULL LIMIT 1'
                    ).fetchone()
                    if invalid_reference:
                        raise ValueError(
                            f"Ungueltige Datenverknuepfung: {table.name}.{child.name}."
                        )
            table_counts = count_database_tables(connection, table_names)
            if sum(table_counts.values()) > 200_000:
                raise ValueError("Die Sicherung enthaelt zu viele Datensaetze (maximal 200000).")
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError("Die hochgeladene Datei ist keine gueltige SQLite-Datenbank.") from exc

    extra_tables = sorted(table_names - EXPECTED_TABLES - {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4"})
    warnings = ["Unbekannte Tabellen werden nicht uebernommen: " + ", ".join(extra_tables)] if extra_tables else []
    return table_counts, warnings


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
        with DATABASE_LOCK:
            backup_sqlite_database(db_path, temp_path)
        # Legacy credentials and HA access mappings never leave this installation.
        with closing(sqlite3.connect(temp_path)) as sanitized:
            sanitized.execute("PRAGMA secure_delete=ON")
            sanitized.execute("UPDATE users SET password='!', home_assistant_user_id=NULL")
            sanitized.commit()
            sanitized.execute("VACUUM")
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

    upload_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as handle:
            upload_path = Path(handle.name)
            await copy_upload(file, handle, MAX_DATABASE_BYTES)
        return await run_in_threadpool(restore_database, upload_path, db_path, filename)
    finally:
        if upload_path:
            upload_path.unlink(missing_ok=True)


def restore_database(upload_path: Path, db_path: Path, filename: str):
    try:
        table_counts, warnings = validate_sqlite_database(upload_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = db_path.with_name(f"{db_path.name}.backup-{timestamp}")
    clean_path = db_path.with_name(f".noko-restore-{uuid.uuid4().hex}.db")
    clean_engine = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        clean_engine = create_engine("sqlite:///" + clean_path.as_posix())
        models.Base.metadata.create_all(clean_engine)
        clean_engine.dispose()
        with DATABASE_LOCK:
            bindings = {}
            if db_path.exists():
                with closing(sqlite3.connect(db_path)) as current:
                    bindings = dict(current.execute("SELECT username, home_assistant_user_id FROM users WHERE home_assistant_user_id IS NOT NULL"))
            source = sqlite3.connect(f"{upload_path.resolve().as_uri()}?mode=ro", uri=True)
            target = sqlite3.connect(clean_path)
            try:
                source.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_SQLITE_VALUE_BYTES)
                source.execute("PRAGMA trusted_schema=OFF")
                target.execute("PRAGMA foreign_keys=ON")
                for table in models.Base.metadata.sorted_tables:
                    columns = [column.name for column in table.columns if column.name != "home_assistant_user_id"]
                    names = ", ".join(f'"{name}"' for name in columns)
                    placeholders = ", ".join("?" for name in columns)
                    for row in source.execute(f'SELECT {names} FROM "{table.name}"'):
                        values = list(row)
                        if table.name == "users":
                            values[columns.index("password")] = "!"
                        target.execute(f'INSERT INTO "{table.name}" ({names}) VALUES ({placeholders})', values)
                for username, ha_id in bindings.items():
                    target.execute("UPDATE users SET home_assistant_user_id=? WHERE username=?", (ha_id, username))
                target.commit()
            finally:
                source.close()
                target.close()
            engine.dispose()
            if db_path.exists():
                backup_sqlite_database(db_path, backup_path)
            remove_sqlite_sidecars(db_path)
            os.replace(clean_path, db_path)
            engine.dispose()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(422, "Die Sicherung verletzt Datenregeln. Die bisherige Datenbank bleibt erhalten.") from exc
    except (OSError, sqlite3.DatabaseError) as exc:
        raise HTTPException(status_code=500, detail="Datenbank konnte nicht importiert werden.") from exc
    finally:
        if clean_engine:
            clean_engine.dispose()
        clean_path.unlink(missing_ok=True)

    return schemas.DatabaseImportResult(
        filename=filename,
        backup_path=str(backup_path) if backup_path.exists() else None,
        imported_tables=table_counts,
        message="Datenbank importiert. Bitte die Seite neu laden.",
        training_rows=sum(
            table_counts.get(table_name, 0) for table_name in TRAINING_TABLES
        ),
        warnings=warnings,
    )
