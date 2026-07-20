import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import grocy_import_service, receipt_import_service


router = APIRouter(prefix="/imports", tags=["imports"])


async def save_grocy_uploads(files: list[UploadFile], directory: Path) -> int:
    csv_count = 0
    for file in files:
        filename = Path(file.filename or "").name
        if not filename:
            continue

        suffix = Path(filename).suffix.lower()
        if suffix == ".zip":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as handle:
                archive_path = Path(handle.name)
                while chunk := await file.read(1024 * 1024):
                    handle.write(chunk)

            try:
                with zipfile.ZipFile(archive_path) as archive:
                    for member in archive.infolist():
                        member_name = Path(member.filename).name
                        if not member_name.lower().endswith(".csv"):
                            continue
                        with archive.open(member) as source, (directory / member_name).open("wb") as target:
                            shutil.copyfileobj(source, target)
                        csv_count += 1
            except zipfile.BadZipFile as exc:
                raise ValueError("Die hochgeladene ZIP-Datei konnte nicht gelesen werden.") from exc
            finally:
                archive_path.unlink(missing_ok=True)
            continue

        if suffix == ".csv":
            with (directory / filename).open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    handle.write(chunk)
            csv_count += 1

    return csv_count


@router.post("/grocy-csv", response_model=schemas.CsvImportResult)
def import_grocy_csv(
    request: schemas.CsvImportRequest,
    db: Session = Depends(get_db),
):
    try:
        return grocy_import_service.import_grocy_csv_directory(
            db=db,
            directory=request.directory,
            dry_run=request.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/grocy-csv/upload", response_model=schemas.CsvImportResult)
async def import_grocy_csv_upload(
    files: list[UploadFile] = File(...),
    dry_run: bool = Form(False),
    db: Session = Depends(get_db),
):
    with tempfile.TemporaryDirectory(prefix="noko-grocy-") as directory:
        try:
            csv_count = await save_grocy_uploads(files, Path(directory))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if csv_count == 0:
            raise HTTPException(
                status_code=422,
                detail="Bitte Grocy-CSV-Dateien oder ein ZIP mit CSV-Dateien hochladen.",
            )
        return grocy_import_service.import_grocy_csv_directory(
            db=db,
            directory=directory,
            dry_run=dry_run,
        )


@router.post("/receipt/preview", response_model=schemas.ReceiptImportPreview)
def preview_receipt_import(
    request: schemas.ReceiptImportPreviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return receipt_import_service.preview_receipt_import(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/receipt/book", response_model=schemas.ReceiptImportBookResult)
def book_receipt_import(
    request: schemas.ReceiptImportBookRequest,
    db: Session = Depends(get_db),
):
    try:
        return receipt_import_service.book_receipt_import(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Kassenzettel konnte nicht gebucht werden") from exc
