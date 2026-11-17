from sqlalchemy.orm import Session

from .. import models


def apply_product_unit_defaults(db: Session, data: dict) -> dict:
    payload = dict(data)
    if "serving_size" in payload or "serving_unit" in payload:
        return payload
    unit_id = payload.get("product_unit_id")
    product_unit = db.get(models.ProductUnit, unit_id) if unit_id is not None else None
    if product_unit is not None and product_unit.default_conversion_quantity is not None:
        payload["serving_size"] = product_unit.default_conversion_quantity
        payload["serving_unit"] = product_unit.default_conversion_unit
    return payload
