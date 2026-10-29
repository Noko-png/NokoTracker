import asyncio
import base64
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app import security
from app.routers import users, weight, training, meals, calendar, nutrition, backups, imports, dashboard, storage_locations
from app.services.receipt_import_service import decode_pdf_text


async def request(app, method, path, payload=None, *, headers=None, peer="172.30.32.2", raw=None):
    body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else b""
    supplied = {"host": "localhost", "content-type": "application/json", **(headers or {})}
    route_path, _, query = path.partition("?")
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": method, "scheme": "http",
        "path": route_path, "raw_path": route_path.encode(), "query_string": query.encode(),
        "root_path": "", "headers": [(k.lower().encode(), v.encode()) for k, v in supplied.items()],
        "client": (peer, 12345), "server": ("localhost", 8000),
    }
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(content) if content else None


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([
                models.User(id=1, username="Alice", home_assistant_user_id="ha-a", password="legacy-secret"),
                models.User(id=2, username="Bob", home_assistant_user_id="ha-b"),
                models.WeightEntry(id=1, user_id=1, weight_kg=70),
                models.WeightEntry(id=2, user_id=2, weight_kg=80),
                models.WeightEntry(id=3, user_id=None, weight_kg=90),
                models.MealLog(id=1, user_id=1, quick_add_name="A", quick_calories=100),
                models.MealLog(id=2, user_id=2, quick_add_name="B", quick_calories=200),
                models.CalendarEvent(id=1, title="Shared", user_id=2, start_at=datetime(2026, 10, 29)),
                models.CalendarEvent(id=2, title="A task", entry_type="task", user_id=1, start_at=datetime(2026, 10, 29)),
                models.CalendarEvent(id=3, title="B task", entry_type="task", user_id=2, start_at=datetime(2026, 10, 29)),
                models.TrainingPlan(id=1, name="A", user_id=1),
                models.TrainingPlan(id=2, name="B", user_id=2),
            ])
            db.commit()
            db.add_all([models.TrainingExercise(id=1, plan_id=1, name="A"), models.TrainingExercise(id=2, plan_id=2, name="B")])
            db.commit()
        self.app = FastAPI()
        for router in [users.router, weight.router, training.plans_router, training.exercises_router,
                       training.sessions_router, meals.router, calendar.router, calendar.groups_router,
                       nutrition.router, backups.router, imports.router, dashboard.router, storage_locations.router]:
            self.app.include_router(router)
        security.install_security(self.app)

        def db_override():
            with Session(self.engine) as db:
                db.info["principal"] = security.current_principal.get()
                yield db

        self.app.dependency_overrides[get_db] = db_override
        for mocked in [patch.dict(os.environ, {"NOKO_AUTH_MODE": "ingress", "NOKO_ADMIN_USERNAME": "owner"}),
                       patch.object(security, "SessionLocal", side_effect=lambda: Session(self.engine))]:
            mocked.start()
            self.addCleanup(mocked.stop)

    def call(self, method, path, payload=None, *, identity="a", **kwargs):
        headers = {} if identity is None else {"x-remote-user-id": "ha-" + identity, "x-remote-user-name": "owner" if identity == "admin" else identity}
        headers.update(kwargs.pop("headers", {}))
        return asyncio.run(request(self.app, method, path, payload, headers=headers, **kwargs))

    def test_direct_requests_and_spoofed_proxy_headers_are_denied(self):
        for peer in ["192.168.1.20", "172.30.33.5", "127.0.0.1"]:
            status, _ = self.call("GET", "/users", peer=peer, headers={"x-forwarded-for": "172.30.32.2"})
            self.assertEqual(status, 403)
        self.assertEqual(self.call("GET", "/users", identity=None)[0], 401)

    def test_session_and_passwordless_user_response(self):
        status, session = self.call("GET", "/session")
        self.assertEqual(status, 200)
        self.assertEqual(session["user_id"], 1)
        self.assertFalse(session["is_admin"])
        status, rows = self.call("GET", "/users")
        self.assertEqual([row["id"] for row in rows], [1])
        self.assertNotIn("password", rows[0])
        self.assertEqual(self.call("GET", "/users/2")[0], 404)
        self.assertEqual(len(self.call("GET", "/users", identity="admin")[1]), 2)

    def test_personal_reads_and_summaries_do_not_leak_other_profiles(self):
        self.assertEqual([row["id"] for row in self.call("GET", "/weight-entries")[1]], [1])
        self.assertEqual(self.call("GET", "/weight-entries?user_id=2")[1], [])
        self.assertEqual([row["id"] for row in self.call("GET", "/meals/logs")[1]], [1])
        self.assertEqual(self.call("GET", "/nutrition/meals/summary")[1]["calories"], 100)
        self.assertEqual(self.call("GET", "/nutrition/day?user_id=2&date=2026-10-29")[0], 404)
        self.assertEqual(self.call("GET", "/dashboard/summary")[1]["users"], 1)
        self.assertEqual([row["id"] for row in self.call("GET", "/training/plans")[1]], [1])

    def test_other_users_writes_and_owner_changes_are_denied(self):
        self.assertEqual(self.call("PATCH", "/weight-entries/2", {"weight_kg": 50})[0], 404)
        self.assertEqual(self.call("DELETE", "/weight-entries/2")[0], 404)
        self.assertIn(self.call("PATCH", "/weight-entries/1", {"user_id": 2})[0], [403, 404])
        self.assertEqual(self.call("PATCH", "/weight-entries/1", {"user_id": None})[0], 403)
        self.assertEqual(self.call("PATCH", "/weight-entries/1", {"weight_kg": 71})[0], 200)
        status, created = self.call("POST", "/weight-entries", {"weight_kg": 72})
        self.assertEqual(status, 201)
        self.assertEqual(created["user_id"], 1)

    def test_profile_binding_and_admin_operations_are_protected(self):
        for method, path, body in [
            ("POST", "/users", {"username": "C"}), ("DELETE", "/users/2", None),
            ("POST", "/database/import", None), ("GET", "/database/export", None),
            ("POST", "/imports/grocy-csv/upload", None),
            ("PATCH", "/users/1", {"home_assistant_user_id": "ha-attacker"}),
        ]:
            self.assertEqual(self.call(method, path, body)[0], 403, path)
        self.assertEqual(self.call("PATCH", "/users/1", {"theme": "dark"})[0], 200)
        self.assertEqual(self.call("PATCH", "/users/2", {"home_assistant_user_id": "ha-c"}, identity="admin")[0], 200)
        status, created = self.call("POST", "/users", {"username": "C", "password": "discard-me"}, identity="admin")
        self.assertEqual(status, 201)
        with Session(self.engine) as db:
            self.assertEqual(db.get(models.User, created["id"]).password, "!")

    def test_unmapped_user_has_no_implicit_default_profile(self):
        self.assertIsNone(self.call("GET", "/session", identity="new")[1]["user_id"])
        self.assertEqual(self.call("GET", "/users", identity="new")[0], 403)
        with patch.dict(os.environ, {"NOKO_ADMIN_USERNAME": ""}):
            self.assertFalse(self.call("GET", "/session", identity="admin")[1]["is_admin"])

    def test_shared_calendar_and_private_tasks(self):
        self.assertEqual({row["id"] for row in self.call("GET", "/calendar/events")[1]}, {1, 2})
        self.assertEqual(self.call("PATCH", "/calendar/events/3", {"title": "attack"})[0], 404)
        status, row = self.call("PATCH", "/calendar/events/1", {"title": "Shared edit", "user_id": 1})
        self.assertEqual(status, 200)
        self.assertEqual(row["user_id"], 2)

    def test_shared_stock_location_updates_remain_available(self):
        with Session(self.engine) as db:
            db.add(models.StorageLocation(id=1, name="Old"))
            db.add(models.Food(name="Shared food", storage_location="Old"))
            db.commit()
        self.assertEqual(self.call("PATCH", "/storage-locations/1", {"name": "New"})[0], 200)
        with Session(self.engine) as db:
            self.assertEqual(db.query(models.Food).one().storage_location, "New")

    def test_training_sessions_and_nested_sets_are_isolated(self):
        payload = {"plan_id": 2, "user_id": 2, "sets": [{"exercise_id": 2, "reps": 5}]}
        status, other = self.call("POST", "/training/sessions", payload, identity="admin")
        self.assertEqual(status, 201)
        self.assertEqual(self.call("GET", "/training/sessions")[1], [])
        self.assertEqual(self.call("PATCH", f"/training/sessions/{other['id']}", {"notes": "attack"})[0], 404)
        self.assertEqual(self.call("DELETE", f"/training/exercises/2")[0], 404)
        self.assertEqual(self.call("GET", "/training/sessions", identity="b")[1][0]["sets"][0]["exercise_id"], 2)

    def test_training_nested_writes_and_foreign_plan_rejected(self):
        status, plan = self.call("POST", "/training/plans", {"name": "Own", "exercises": [{"name": "Squat"}]})
        self.assertEqual(status, 201, plan)
        status, session = self.call("POST", "/training/sessions", {"plan_id": plan["id"], "sets": [{"exercise_id": plan["exercises"][0]["id"], "reps": 5}]})
        self.assertEqual(status, 201, session)
        self.assertEqual(self.call("POST", "/training/sessions", {"plan_id": 2, "user_id": 1, "sets": [{"exercise_id": 2, "reps": 5}]})[0], 404)
        self.assertEqual(self.call("GET", "/training/exercises/2/results")[0], 404)

    def test_size_limits_and_cross_site_requests(self):
        self.assertEqual(self.call("POST", "/weight-entries", {}, headers={"content-length": str(100 * 1024 * 1024)})[0], 413)
        self.assertEqual(self.call("POST", "/weight-entries", raw=b" " * (12 * 1024 * 1024 + 1))[0], 413)
        self.assertEqual(self.call("POST", "/weight-entries", {}, headers={"sec-fetch-site": "cross-site"})[0], 403)

    def test_migration_discards_legacy_passwords(self):
        security.migrate_security_schema(self.engine)
        with Session(self.engine) as db:
            self.assertEqual(db.get(models.User, 1).password, "!")

    def test_local_development_allows_loopback_ports_but_rejects_remote_origins(self):
        with patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"}):
            self.assertEqual(self.call("GET", "/users", peer="127.0.0.1", headers={"origin": "http://127.0.0.1:5175"})[0], 200)
            self.assertEqual(self.call("GET", "/users", peer="127.0.0.1", headers={"origin": "https://attacker.invalid"})[0], 403)
            self.assertEqual(self.call("GET", "/users", peer="127.0.0.1", headers={"host": "attacker.invalid"})[0], 403)
            self.assertEqual(self.call("GET", "/users", peer="192.168.1.20")[0], 403)


class ImportSecurityTest(unittest.TestCase):
    def test_compressed_bomb_is_rejected_before_extraction(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as writer:
            writer.writestr("products.csv", b"a,b\n" * 100_000)
        with tempfile.TemporaryDirectory(prefix="noko-security-test-") as directory:
            upload = UploadFile(io.BytesIO(archive.getvalue()), filename="archive.zip")
            with self.assertRaisesRegex(ValueError, "komprimiert"):
                asyncio.run(imports.save_grocy_uploads([upload], Path(directory)))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_pdf_page_and_byte_limits_and_valid_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        valid_writer = PdfWriter()
        page = valid_writer.add_blank_page(width=100, height=100)
        font = valid_writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }))
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 10 10 Td (Audit PDF) Tj ET")
        page[NameObject("/Contents")] = valid_writer._add_object(stream)
        valid_pdf = io.BytesIO()
        valid_writer.write(valid_pdf)
        self.assertIn("Audit PDF", decode_pdf_text(base64.b64encode(valid_pdf.getvalue()).decode()))
        writer = PdfWriter()
        for _ in range(31):
            writer.add_blank_page(width=100, height=100)
        pdf = io.BytesIO()
        writer.write(pdf)
        with self.assertRaisesRegex(ValueError, "Verarbeitungslimit"):
            decode_pdf_text(base64.b64encode(pdf.getvalue()).decode())
        with self.assertRaisesRegex(ValueError, "8 MB"):
            decode_pdf_text("A" * 11_200_001)


if __name__ == "__main__":
    unittest.main()
