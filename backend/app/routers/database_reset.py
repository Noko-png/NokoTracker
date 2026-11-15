from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from .. import models
from ..database import DATABASE_LOCK, engine
from ..security import current_principal

router = APIRouter(prefix="/database", tags=["database"])


class ResetConfirmation(BaseModel):
    confirmation: Literal["ALLE DATEN LOESCHEN"]


@router.post("/reset")
def reset_database(confirmation: ResetConfirmation):
    principal = current_principal.get()
    if principal is None or not principal.is_admin:
        raise HTTPException(403, "Nur der Administrator darf die Datenbank loeschen.")
    # One transaction preserves the schema and rolls back every deletion on error.
    # The shared lock prevents concurrent requests/imports during the reset.
    with DATABASE_LOCK, engine.begin() as connection:
        for table in reversed(models.Base.metadata.sorted_tables):
            connection.execute(table.delete())
    return {"message": "Alle Daten wurden geloescht."}
