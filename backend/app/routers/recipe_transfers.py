"""Recipe file transfers, independent from the database restoration API."""
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import create_engine
from starlette.background import BackgroundTask

from .. import models, schemas
from ..database import DATABASE_LOCK
from ..services.database_transfer import DataTransfer
from . import backups


router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.post("/import/preview", response_model=schemas.RecipeImportPreview)
async def preview_recipes(file: UploadFile = File(...)):
    def inspect(path, filename):
        try:
            _, warnings = backups.validate_sqlite_database(path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as source:
            return schemas.RecipeImportPreview(
                filename=filename,
                recipes=[schemas.RecipeImportItem(id=row[0], name=row[1])
                         for row in source.execute("SELECT id,name FROM recipes ORDER BY name,id")],
                warnings=warnings,
            )
    return await backups.read_database_upload(file, inspect)


@router.post("/import", response_model=schemas.RecipeImportResult)
async def import_recipes(
    file: UploadFile = File(...),
    recipe_ids: Annotated[str, Form()] = "[]",
):
    selection = backups.parse_selection(recipe_ids, int)
    if not selection or any(value <= 0 for value in selection):
        raise HTTPException(422, "Bitte mindestens ein Rezept auswaehlen.")
    db_path = backups.sqlite_database_path()

    def restore(path, filename):
        result = backups.restore_database(path, db_path, filename, mode="recipes", recipe_ids=selection)
        return schemas.RecipeImportResult(
            filename=result.filename,
            imported_count=result.imported_tables.get("recipes", 0),
            message=result.message,
            warnings=result.warnings,
        )
    return await backups.read_database_upload(file, restore)


@router.get("/{recipe_id}/export")
def export_recipe(recipe_id: int):
    db_path = backups.sqlite_database_path()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as handle:
        path = Path(handle.name)
    temporary_engine = create_engine("sqlite:///" + path.as_posix())
    try:
        models.Base.metadata.create_all(temporary_engine)
        temporary_engine.dispose()
        with DATABASE_LOCK, closing(sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)) as source, closing(sqlite3.connect(path)) as target:
            transfer = DataTransfer(source, target, recipe_only=True)
            transfer.add_recipes([recipe_id])
            target.execute("CREATE TABLE noko_recipe_export (version INTEGER NOT NULL)")
            target.execute("INSERT INTO noko_recipe_export VALUES (1)")
            target.commit()
    except (ValueError, sqlite3.DatabaseError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "Rezept konnte nicht exportiert werden: " + str(exc)) from exc
    finally:
        temporary_engine.dispose()
    return FileResponse(
        path, filename=f"noko-rezept-{recipe_id}.db", media_type="application/vnd.sqlite3",
        background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )
