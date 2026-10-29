"""Ingress authentication and database-level isolation of personal profiles.

Identity headers are trusted only on the Supervisor's actual TCP connection.
Uvicorn MUST run with --no-proxy-headers in the add-on.
"""
import asyncio
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import event, inspect, or_, text
from sqlalchemy.orm import Session, with_loader_criteria
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from . import models
from .database import DATABASE_LOCK, SessionLocal


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    is_admin: bool
    ha_user_id: str | None = None
    ha_username: str | None = None
    admin_configured: bool = True


current_principal: ContextVar[Principal | None] = ContextVar("principal", default=None)
PERSONAL_MODELS = (models.MealLog, models.WeightEntry, models.TrainingPlan, models.TrainingSession)


def migrate_security_schema(engine):
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        if "home_assistant_user_id" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN home_assistant_user_id VARCHAR(128)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_ha_identity ON users (home_assistant_user_id)"))
        if "password" in columns:
            if engine.dialect.name == "sqlite":
                connection.execute(text("PRAGMA secure_delete=ON"))
            connection.execute(text("UPDATE users SET password='!' WHERE password <> '!'"))


def resolve_principal(headers: Headers) -> Principal:
    ha_id = headers.get("x-remote-user-id", "").strip()
    username = headers.get("x-remote-user-name", "").strip()
    if not ha_id or len(ha_id) > 128:
        raise HTTPException(401, "Home-Assistant-Anmeldung fehlt. Bitte ueber Home Assistant oeffnen.")
    admin_username = os.getenv("NOKO_ADMIN_USERNAME", "").strip()
    with DATABASE_LOCK, SessionLocal() as db:
        profile = db.query(models.User).filter_by(home_assistant_user_id=ha_id).first()
        return Principal(
            profile.id if profile else None,
            bool(admin_username and username == admin_username),
            ha_id, username or None, bool(admin_username),
        )


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.upload_slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = "/" + scope.get("path", "").lstrip("/")
        headers = Headers(scope=scope)
        peer = (scope.get("client") or ("", 0))[0]
        ingress = os.getenv("NOKO_AUTH_MODE", "local") == "ingress"
        try:
            if ingress:
                if peer != "172.30.32.2":
                    raise HTTPException(403, "Zugriff nur ueber Home Assistant erlaubt.")
                principal = None if path == "/health" else await run_in_threadpool(resolve_principal, headers)
            else:
                try:
                    local = ip_address(peer).is_loopback
                except ValueError:
                    local = False
                origin = headers.get("origin")
                local_origin = origin is None or re.fullmatch(r"http://(127\.0\.0\.1|localhost):\d{1,5}", origin)
                if not local or not local_origin:
                    raise HTTPException(403, "Lokaler Entwicklungszugriff ist nur vom eigenen Rechner erlaubt.")
                try:
                    hostname = urlsplit("http://" + headers.get("host", "")).hostname
                except ValueError:
                    raise HTTPException(400, "Ungueltiger Host.")
                if hostname not in {"localhost", "127.0.0.1", "::1"}:
                    raise HTTPException(403, "Ungueltiger Host.")
                principal = Principal(None, True)
            if headers.get("sec-fetch-site") == "cross-site":
                raise HTTPException(403, "Anfragen von fremden Webseiten sind nicht erlaubt.")

            public_ui = path in {"/", "/session", "/health", "/favicon.ico"} or path.startswith("/assets/")
            if principal and not principal.is_admin and principal.user_id is None and not public_ui:
                raise HTTPException(403, "Dein HA-Konto ist noch keinem NokoTracker-Profil zugeordnet.")
            admin_only = path.startswith(("/database/", "/imports/grocy-csv")) or (
                path.rstrip("/") == "/users" and scope["method"] == "POST"
            ) or (path.startswith("/users/") and scope["method"] == "DELETE")
            if admin_only and (not principal or not principal.is_admin):
                raise HTTPException(403, "Diese Funktion ist nur fuer den Administrator verfuegbar.")

            token = current_principal.set(principal)
            try:
                if scope["method"] in {"POST", "PATCH", "PUT"}:
                    async with self.upload_slots:
                        limit = 65 * 1024 * 1024 if path.rstrip("/") == "/database/import" else 12 * 1024 * 1024
                        if path.rstrip("/") == "/imports/grocy-csv/upload":
                            limit = 33 * 1024 * 1024
                        await self.bounded_request(scope, receive, send, headers, limit)
                else:
                    await self.app(scope, receive, send)
            finally:
                current_principal.reset(token)
        except HTTPException as exc:
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
        except TimeoutError:
            await JSONResponse({"detail": "Zeitlimit beim Upload erreicht."}, status_code=408)(scope, receive, send)

    async def bounded_request(self, scope, receive, send, headers, limit):
        try:
            length = int(headers.get("content-length", "0"))
        except ValueError:
            raise HTTPException(400, "Ungueltige Inhaltslaenge.")
        if length < 0 or length > limit:
            raise HTTPException(413, "Die Anfrage ist zu gross.")
        body = bytearray()
        while True:
            message = await asyncio.wait_for(receive(), timeout=30)
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                raise HTTPException(413, "Die Anfrage ist zu gross.")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, buffered_receive, send)


def install_security(app):
    app.add_middleware(SecurityMiddleware)

    @app.get("/session", tags=["system"])
    def read_session():
        principal = current_principal.get()
        if principal is None:
            raise HTTPException(401, "Anmeldung erforderlich.")
        return {
            "user_id": principal.user_id, "is_admin": principal.is_admin,
            "ha_user_id": principal.ha_user_id, "ha_username": principal.ha_username,
            "admin_configured": principal.admin_configured,
        }


@event.listens_for(Session, "do_orm_execute")
def isolate_personal_reads(state):
    principal = state.session.info.get("principal")
    if not principal or principal.is_admin:
        return
    if not state.is_select:
        # Existing stock/location operations update household data in bulk.
        if state.bind_mapper and state.bind_mapper.class_ in {models.Food, models.InventoryItem, models.ProductGroup, models.ProductUnit, models.StorageLocation, models.ShoppingListItem, models.Recipe, models.RecipeIngredient, models.FoodConversion}:
            return
        raise HTTPException(403, "Direkte Sammelaenderungen persoenlicher Daten sind nicht erlaubt.")
    user_id = principal.user_id
    criteria = [(model, model.user_id == user_id) for model in PERSONAL_MODELS]
    criteria.extend([
        (models.User, models.User.id == user_id),
        (models.TrainingExercise, models.TrainingExercise.plan.has(user_id=user_id)),
        (models.TrainingSessionSet, models.TrainingSessionSet.session.has(user_id=user_id)),
        (models.CalendarEvent, or_(models.CalendarEvent.entry_type != "task", models.CalendarEvent.user_id == user_id)),
    ])
    for model, condition in criteria:
        state.statement = state.statement.options(with_loader_criteria(model, condition, include_aliases=True))


@event.listens_for(Session, "before_flush")
def protect_personal_writes(db, _context, _instances):
    principal = db.info.get("principal")
    if not principal or principal.is_admin:
        return
    user_id = principal.user_id
    if user_id is None:
        raise HTTPException(403, "Profilzuordnung erforderlich.")
    for obj in db.new:
        if isinstance(obj, PERSONAL_MODELS) and obj.user_id is None:
            obj.user_id = user_id
    for obj in set(db.new) | set(db.dirty) | set(db.deleted):
        state = inspect(obj)
        if isinstance(obj, models.User):
            if obj in db.new or obj in db.deleted or obj.id != user_id or state.attrs.home_assistant_user_id.history.has_changes():
                raise HTTPException(403, "Nur der Administrator darf Profile zuordnen oder verwalten.")
        personal = isinstance(obj, PERSONAL_MODELS) or (
            isinstance(obj, models.CalendarEvent) and (
                obj.entry_type == "task" or "task" in state.attrs.entry_type.history.deleted
            )
        )
        if personal:
            history = state.attrs.user_id.history
            if history.deleted and history.deleted[0] != user_id:
                raise HTTPException(403, "Fremde Profildaten duerfen nicht veraendert werden.")
            if obj in db.new and obj.user_id is None:
                obj.user_id = user_id
            if obj.user_id != user_id:
                raise HTTPException(403, "Der Eintrag muss deinem Profil zugeordnet sein.")
        elif isinstance(obj, (models.CalendarEvent, models.CalendarGroup, models.Recipe)):
            field = "created_by_user_id" if isinstance(obj, models.Recipe) else "user_id"
            history = state.attrs[field].history
            if obj not in db.new and history.has_changes() and history.deleted:
                setattr(obj, field, history.deleted[0])
            elif obj in db.new:
                if getattr(obj, field) not in (None, user_id):
                    raise HTTPException(403, "Eintraege koennen nur im eigenen Namen erstellt werden.")
                setattr(obj, field, user_id)
        references = []
        if isinstance(obj, (models.TrainingExercise, models.TrainingSession)):
            references.append((models.TrainingPlan, obj.plan_id, obj.plan))
        if isinstance(obj, models.TrainingSessionSet):
            references.extend([(models.TrainingSession, obj.session_id, obj.session), (models.TrainingExercise, obj.exercise_id, obj.exercise)])
        for model, reference_id, related in references:
            target = db.get(model, reference_id) if reference_id else related
            owner = target.plan.user_id if isinstance(target, models.TrainingExercise) else getattr(target, "user_id", None)
            if target is None or owner != user_id:
                raise HTTPException(403, "Fremde Trainingsdaten duerfen nicht verknuepft werden.")
