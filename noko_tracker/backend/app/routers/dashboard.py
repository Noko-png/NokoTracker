from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def read_dashboard_summary(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    recent_cutoff = now - timedelta(days=7)

    return {
        "users": db.query(models.User).count(),
        "foods": db.query(models.Food).filter(models.Food.is_archived.is_(False)).count(),
        "recipes": db.query(models.Recipe).filter(models.Recipe.is_archived.is_(False)).count(),
        "inventory_items": db.query(models.InventoryItem).count(),
        "shopping_open_items": db.query(models.ShoppingListItem)
        .filter(models.ShoppingListItem.is_checked.is_(False))
        .count(),
        "upcoming_events": db.query(models.CalendarEvent)
        .outerjoin(models.CalendarGroup)
        .filter(models.CalendarEvent.start_at >= now)
        .filter(
            or_(
                models.CalendarEvent.group_id.is_(None),
                models.CalendarGroup.hide_from_dashboard_and_month.is_(False),
            )
        )
        .count(),
        "recent_meals": db.query(models.MealLog)
        .filter(models.MealLog.eaten_at >= recent_cutoff)
        .count(),
    }
