import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import grocy_import_service, receipt_import_service
from ..upload_limits import MAX_ARCHIVE_BYTES, MAX_EXPANDED_BYTES, MAX_CSV_BYTES, MAX_IMPORT_FILES, copy_upload


router = APIRouter(prefix="/imports", tags=["imports"])


async def save_grocy_uploads(files: list[UploadFile], directory: Path) -> int:
    csv_count = 0
    expanded_size = 0
    uploaded_size = 0
    seen_names = set()
    if len(files) > MAX_IMPORT_FILES:
        raise ValueError("Maximal 64 Importdateien sind erlaubt.")
    for file in files:
        filename = Path(file.filename or "").name
        if not filename:
            continue

        suffix = Path(filename).suffix.lower()
        if suffix == ".zip":
            archive_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as handle:
                    archive_path = Path(handle.name)
                    uploaded_size += await copy_upload(file, handle, MAX_ARCHIVE_BYTES - uploaded_size)
                with zipfile.ZipFile(archive_path) as archive:
                    if len(archive.infolist()) > MAX_IMPORT_FILES:
                        raise ValueError("Das ZIP enthaelt zu viele Dateien (maximal 64).")
                    for member in archive.infolist():
                        member_name = Path(member.filename).name
                        if not member_name.lower().endswith(".csv"):
                            continue
                        if member.file_size > MAX_CSV_BYTES or member.file_size > 100 * max(member.compress_size, 1):
                            raise ValueError("Die ZIP-Datei ist zu stark komprimiert oder enthaelt zu grosse CSV-Dateien.")
                        if member_name.lower() in seen_names:
                            raise ValueError("Doppelte CSV-Dateinamen sind nicht erlaubt.")
                        seen_names.add(member_name.lower())
                        if len(seen_names) > MAX_IMPORT_FILES:
                            raise ValueError("Zu viele CSV-Dateien.")
                        with archive.open(member) as source, (directory / member_name).open("wb") as target:
                            member_size = 0
                            while chunk := source.read(1024 * 1024):
                                member_size += len(chunk)
                                expanded_size += len(chunk)
                                if member_size > MAX_CSV_BYTES or expanded_size > MAX_EXPANDED_BYTES:
                                    raise ValueError("Entpackte Importdaten sind zu gross.")
                                target.write(chunk)
                        csv_count += 1
            except zipfile.BadZipFile as exc:
                raise ValueError("Die hochgeladene ZIP-Datei konnte nicht gelesen werden.") from exc
            finally:
                if archive_path:
                    archive_path.unlink(missing_ok=True)
            continue

        if suffix == ".csv":
            if filename.lower() in seen_names:
                raise ValueError("Doppelte CSV-Dateinamen sind nicht erlaubt.")
            seen_names.add(filename.lower())
            with (directory / filename).open("wb") as handle:
                size = await copy_upload(file, handle, min(MAX_CSV_BYTES, MAX_ARCHIVE_BYTES - uploaded_size, MAX_EXPANDED_BYTES - expanded_size))
                uploaded_size += size
                expanded_size += size
            csv_count += 1

    return csv_count


@router.post("/grocy-csv", response_model=schemas.CsvImportResult)
def import_grocy_csv(
    request: schemas.CsvImportRequest,
    db: Session = Depends(get_db),
):
    if os.getenv("NOKO_AUTH_MODE") == "ingress":
        allowed = Path("/data/imports").resolve()
        requested = Path(request.directory).resolve()
        if not requested.is_relative_to(allowed):
            raise HTTPException(403, "Serverimporte sind nur aus /data/imports erlaubt. Alternativ CSV/ZIP hochladen.")
    try:
        return grocy_import_service.import_grocy_csv_directory(
            db=db,
            directory=request.directory,
            dry_run=request.dry_run,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
        try:
            return grocy_import_service.import_grocy_csv_directory(
                db=db,
                directory=directory,
                dry_run=dry_run,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


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
