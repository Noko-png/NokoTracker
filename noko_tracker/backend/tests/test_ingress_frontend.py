"""Exercise the complete HA app, including its SPA fallback and real auth routes."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SMOKE_TEST = r'''
import asyncio
import json
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import database

# The ingress auth check runs in a worker thread. Share only this test database.
database.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
database.SessionLocal.configure(bind=database.engine)
from app.main import app
from app import schemas
from app.routers.foods import create_food
with database.SessionLocal() as db:
    create_food(schemas.FoodCreate(name="EAN-Test", barcodes=["0012345678905", "4012345678901"], calories_per_100g=100), db)

async def request(path, *, accept="application/json", username="owner", peer="172.30.32.2", authenticated=True):
    headers = {"host": "localhost", "accept": accept, "x-ingress-path": "/api/hassio_ingress/test-session/"}
    if authenticated:
        headers.update({"x-remote-user-id": "test-ha-user", "x-remote-user-name": username, "x-remote-user-display-name": "owner"})
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 12345), "server": ("localhost", 8000),
    }
    sent = []
    async def receive():
        await asyncio.Event().wait()
    async def send(message):
        sent.append(message)
    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent)
    return start["status"], dict(start["headers"]), body

async def main():
    for path in ("/session", "//session"):
        status, headers, body = await request(path)
        assert status == 200 and b"application/json" in headers[b"content-type"], (path, status, body[:80])
        session = json.loads(body)
        assert session["is_admin"] and session["ha_username"] == "owner"
    for code in ("0012345678905", "4012345678901"):
        status, headers, body = await request("/foods/barcode/" + code)
        assert status == 200 and b"application/json" in headers[b"content-type"], (status, body[:200])
        assert json.loads(body)["food"]["barcodes"] == ["0012345678905", "4012345678901"]
    status, headers, body = await request("/", accept="text/html")
    assert status == 200 and b"<!doctype html>" in body.lower()
    assert headers.get(b"cache-control") == b"no-store"
    status, _, body = await request("/assets/test.js", accept="*/*")
    assert status == 200 and b"static asset" in body
    status, headers, body = await request("/missing-api-endpoint")
    assert status == 404 and json.loads(body)["detail"]
    status, _, body = await request("/session", username="different-login")
    assert status == 200 and not json.loads(body)["is_admin"]
    assert json.loads(body)["ha_username"] == "different-login"
    assert (await request("/session", peer="192.168.1.50"))[0] == 403
    assert (await request("/session", authenticated=False))[0] == 401
    print("Complete HA app: session JSON, HTML/assets, unknown API, username mismatch and ingress access checks passed.")

asyncio.run(main())
'''


class IngressFrontendTest(unittest.TestCase):
    def test_complete_addon_routes_session_before_frontend_fallback(self):
        project = Path(__file__).resolve().parents[2]
        addon_backend = project / "backend" if project.name == "noko_tracker" else project / "noko_tracker" / "backend"
        with tempfile.TemporaryDirectory(prefix="noko-ingress-test-") as directory:
            root = Path(directory)
            (root / "index.html").write_text("<!doctype html><html>NokoTracker</html>", encoding="utf-8")
            (root / "assets").mkdir()
            (root / "assets" / "test.js").write_text("// static asset", encoding="utf-8")
            environment = {
                **os.environ, "DATABASE_URL": "sqlite://", "NOKO_STATIC_DIR": str(root),
                "NOKO_AUTH_MODE": "ingress", "NOKO_ADMIN_USERNAME": "owner",
            }
            result = subprocess.run(
                [sys.executable, "-c", SMOKE_TEST], cwd=addon_backend, env=environment,
                capture_output=True, text=True, timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
