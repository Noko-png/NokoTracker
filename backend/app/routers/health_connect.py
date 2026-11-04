"""Read-only, admin-only diagnostic view of HA Companion health sensors.

The Supervisor token remains server-side. Never accept a URL from the caller or
forward arbitrary HA attributes (which may contain unrelated personal data).
"""
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from ..security import current_principal


router = APIRouter(prefix="/health-connect", tags=["health-connect"])
STATES_URL = "http://supervisor/core/api/states"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
NO_STORE = {"Cache-Control": "no-store, private"}
ENTITY_PATTERN = r"^sensor\.[a-z0-9_]{1,180}$"
AUTO_SENSOR = re.compile(
    r"(?:^|_)health_connect_(daily_steps|heart_rate|resting_heart_rate|sleep_duration)(?:_\d+)?$"
)
KINDS = {"daily_steps": "steps", "heart_rate": "heart_rate",
         "resting_heart_rate": "resting_heart_rate", "sleep_duration": "sleep"}


class HealthSensor(BaseModel):
    entity_id: str
    name: str
    kind: Literal["steps", "heart_rate", "resting_heart_rate", "sleep"]
    value: float | None
    unit: str | None
    state: Literal["available", "unknown", "unavailable", "invalid", "missing"]
    last_updated: str | None = None
    selection: Literal["automatic", "manual"] = "automatic"


class HealthTestRead(BaseModel):
    status: Literal["connected", "empty", "not_configured"]
    message: str
    checked_at: str
    sensors: list[HealthSensor]


def require_admin():
    principal = current_principal.get()
    if principal is None:
        raise HTTPException(401, "Home-Assistant-Anmeldung erforderlich.", headers=NO_STORE)
    if not principal.is_admin:
        raise HTTPException(403, "Das Test Health dashboard ist nur fuer den Administrator freigegeben.", headers=NO_STORE)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_states(token: str) -> list[dict]:
    # Fixed internal destination; disable environment proxies and redirects so
    # the administrator credential cannot leave the Supervisor connection.
    request = Request(STATES_URL, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=8) as result:
            if result.headers.get_content_type() != "application/json":
                raise HTTPException(502, "Home Assistant hat keine JSON-Daten geliefert. Bitte das Add-on aktualisieren und neu starten.", headers=NO_STORE)
            raw = result.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise HTTPException(502, "Die Sensorantwort von Home Assistant ist zu gross.", headers=NO_STORE)
        states = json.loads(raw)
        if not isinstance(states, list) or not all(isinstance(item, dict) for item in states):
            raise ValueError("Invalid state list")
        return states
    except HTTPError as exc:
        exc.close()
        if exc.code in (401, 403):
            detail = "Home Assistant verweigert den Sensorzugriff. Bitte das Add-on auf die aktuelle Version aktualisieren und neu starten; der HA-API-Zugriff muss aktiviert sein."
        else:
            detail = "Die Sensorabfrage bei Home Assistant ist fehlgeschlagen. Bitte spaeter erneut versuchen."
        raise HTTPException(502, detail, headers=NO_STORE) from None
    except (TimeoutError, URLError, OSError):
        raise HTTPException(502, "Home Assistant ist momentan nicht erreichbar. Bitte die Verbindung pruefen und erneut versuchen.", headers=NO_STORE) from None
    except (ValueError, UnicodeError):
        raise HTTPException(502, "Home Assistant hat ungueltige Sensordaten geliefert.", headers=NO_STORE) from None


def safe_timestamp(value) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo else None
    except ValueError:
        return None


def sensor_value(record: dict, kind: str, *, manual=False) -> HealthSensor:
    attributes = record.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    raw_state = record.get("state")
    state = raw_state if raw_state in ("unknown", "unavailable", "missing") else "invalid"
    value = None
    try:
        number = float(raw_state)
        if not isinstance(raw_state, bool) and math.isfinite(number) and number >= 0:
            value, state = number, "available"
    except (ValueError, TypeError, OverflowError):
        pass
    name = attributes.get("friendly_name")
    unit = attributes.get("unit_of_measurement")
    return HealthSensor(
        entity_id=record["entity_id"],
        name=name[:180] if isinstance(name, str) else record["entity_id"],
        kind=kind, value=value, state=state,
        unit=unit[:32] if isinstance(unit, str) else None,
        last_updated=safe_timestamp(record.get("last_updated")),
        selection="manual" if manual else "automatic",
    )


@router.get("/test", response_model=HealthTestRead, dependencies=[Depends(require_admin)])
def read_health_test(
    response: Response,
    steps_entity: str | None = Query(None, pattern=ENTITY_PATTERN, max_length=187),
    pulse_entity: str | None = Query(None, pattern=ENTITY_PATTERN, max_length=187),
    sleep_entity: str | None = Query(None, pattern=ENTITY_PATTERN, max_length=187),
):
    response.headers.update(NO_STORE)
    checked_at = datetime.now(timezone.utc).isoformat()
    token = os.getenv("SUPERVISOR_TOKEN", "").strip()
    if os.getenv("NOKO_AUTH_MODE") != "ingress":
        return HealthTestRead(status="not_configured", checked_at=checked_at, sensors=[],
                              message="Die Sensorabfrage ist im Home-Assistant-Add-on verfuegbar. Lokal besteht keine Verbindung zu deiner HA-Instanz.")
    if not token:
        return HealthTestRead(status="not_configured", checked_at=checked_at, sensors=[],
                              message="Der interne HA-Zugang fehlt. Bitte das Add-on aktualisieren und neu starten.")
    records = fetch_states(token)
    manual = {kind: entity for kind, entity in (("steps", steps_entity), ("heart_rate", pulse_entity), ("sleep", sleep_entity)) if entity}
    sensors = []
    by_id = {}
    for record in records:
        entity_id = record.get("entity_id")
        if not isinstance(entity_id, str) or not re.fullmatch(ENTITY_PATTERN, entity_id):
            continue
        by_id[entity_id] = record
        match = AUTO_SENSOR.search(entity_id.removeprefix("sensor."))
        if match and KINDS[match[1]] not in manual:
            sensors.append(sensor_value(record, KINDS[match[1]]))
    for kind, entity_id in manual.items():
        record = by_id.get(entity_id, {"entity_id": entity_id, "state": "missing"})
        sensors.append(sensor_value(record, kind, manual=True))
    sensors.sort(key=lambda sensor: (sensor.kind, sensor.entity_id))
    return HealthTestRead(
        status="connected" if sensors else "empty", checked_at=checked_at, sensors=sensors,
        message="Verbindung zu Home Assistant hergestellt." if sensors else
                "Verbunden, aber keine passenden Health-Connect-Sensoren gefunden. Bitte die Sensoren in der HA-App aktivieren oder umbenannte Sensoren unten manuell auswaehlen.",
    )
