from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import grocy_import_service, receipt_import_service


router = APIRouter(prefix="/imports", tags=["imports"])


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
