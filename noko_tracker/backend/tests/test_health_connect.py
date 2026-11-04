import asyncio
import io
import json
import os
import unittest
from email.message import Message
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from fastapi import FastAPI, HTTPException

from app import security
from app.routers import health_connect as health
from test_security import request


def sensor(entity_id, state="1234", **attributes):
    return {"entity_id": entity_id, "state": state,
            "last_updated": "2026-11-04T10:00:00+00:00",
            "attributes": {"friendly_name": "Testhandy", "unit_of_measurement": "steps", **attributes}}


class HealthConnectTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(health.router)
        security.install_security(self.app)
        patches = [
            patch.dict(os.environ, {"NOKO_AUTH_MODE": "ingress", "SUPERVISOR_TOKEN": "private-test-token"}),
            patch.object(security, "resolve_principal", return_value=security.Principal(None, True)),
            patch.object(health, "fetch_states", return_value=[]),
        ]
        self.environment, self.principal, self.fetch = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)

    def call(self, path="/health-connect/test", **kwargs):
        return asyncio.run(request(self.app, "GET", path, **kwargs))

    def test_only_health_sensors_and_safe_fields_are_returned(self):
        self.fetch.return_value = [
            sensor("sensor.phone_health_connect_daily_steps", "0", private_note="secret-note"),
            sensor("sensor.other_phone_health_connect_daily_steps", "321"),
            sensor("sensor.phone_health_connect_heart_rate", "72", unit_of_measurement="bpm"),
            sensor("sensor.phone_health_connect_resting_heart_rate", "60", unit_of_measurement="bpm"),
            sensor("sensor.phone_health_connect_sleep_duration", "420.5", unit_of_measurement="min"),
            sensor("sensor.phone_health_connect_blood_glucose", "98"),
            sensor("sensor.phone_battery", "50"),
            sensor("switch.health_connect_daily_steps"),
            {"entity_id": None},
        ]
        status, result = self.call()
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "connected")
        self.assertEqual(len(result["sensors"]), 5)
        steps = next(item for item in result["sensors"] if item["entity_id"] == "sensor.phone_health_connect_daily_steps")
        self.assertEqual((steps["value"], steps["state"]), (0, "available"))
        encoded = json.dumps(result)
        for private in ("secret-note", "blood_glucose", "phone_battery", "private-test-token"):
            self.assertNotIn(private, encoded)
        self.fetch.assert_called_once_with("private-test-token")

    def test_unavailable_and_invalid_values_are_not_zero_measurements(self):
        for raw, expected in [("unknown", "unknown"), ("unavailable", "unavailable"),
                              ("NaN", "invalid"), ("Infinity", "invalid"), ("-1", "invalid"),
                              (True, "invalid"), ({}, "invalid"), (None, "invalid")]:
            with self.subTest(raw=raw):
                self.fetch.return_value = [sensor("sensor.phone_health_connect_heart_rate", raw)]
                status, result = self.call()
                self.assertEqual(status, 200)
                self.assertEqual(result["sensors"][0]["state"], expected)
                self.assertIsNone(result["sensors"][0]["value"])

    def test_manual_selection_handles_renamed_and_missing_entities(self):
        self.fetch.return_value = [sensor("sensor.phone_health_connect_daily_steps"), sensor("sensor.meine_schritte", "456")]
        status, result = self.call("/health-connect/test?steps_entity=sensor.meine_schritte&pulse_entity=sensor.fehlt")
        self.assertEqual(status, 200)
        self.assertEqual(len(result["sensors"]), 2)
        selected = {item["kind"]: item for item in result["sensors"]}
        self.assertEqual(selected["steps"]["value"], 456)
        self.assertEqual(selected["steps"]["selection"], "manual")
        self.assertEqual(selected["heart_rate"]["state"], "missing")
        self.assertIsNone(selected["heart_rate"]["value"])

    def test_rejects_invalid_entity_ids_before_contacting_ha(self):
        for value in ("http://evil.example", "sensor.foo/../../users", "light.bedroom", "sensor.foo,sensor.bar"):
            with self.subTest(value=value):
                self.assertEqual(self.call("/health-connect/test?steps_entity=" + value)[0], 422)
        self.fetch.assert_not_called()

    def test_empty_and_missing_connection_are_distinguished(self):
        self.assertEqual(self.call()[1]["status"], "empty")
        self.fetch.reset_mock()
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": ""}):
            status, result = self.call()
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "not_configured")
        self.fetch.assert_not_called()

    def test_non_admin_and_forged_ingress_have_no_sensor_access(self):
        for identity in (security.Principal(1, False), security.Principal(2, False)):
            self.principal.return_value = identity
            self.assertEqual(self.call()[0], 403)
        self.principal.return_value = security.Principal(None, True)
        self.assertEqual(self.call(peer="192.168.1.12")[0], 403)
        self.principal.side_effect = HTTPException(401, "Anmeldung fehlt")
        self.assertEqual(self.call()[0], 401)
        self.fetch.assert_not_called()

    def test_local_mode_does_not_use_even_an_existing_supervisor_token(self):
        with patch.dict(os.environ, {"NOKO_AUTH_MODE": "local"}):
            status, result = self.call(peer="127.0.0.1")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "not_configured")
        self.fetch.assert_not_called()


class SupervisorTransportTest(unittest.TestCase):
    def test_fixed_get_destination_with_token_and_no_proxy_or_redirect(self):
        response = io.BytesIO(b'[{"entity_id": "sensor.example"}]')
        response.headers = Message()
        response.headers["Content-Type"] = "application/json"
        with patch.object(health, "build_opener") as build:
            build.return_value.open.return_value = response
            self.assertEqual(health.fetch_states("secret"), [{"entity_id": "sensor.example"}])
        args, kwargs = build.return_value.open.call_args
        self.assertEqual(args[0].full_url, "http://supervisor/core/api/states")
        self.assertEqual(args[0].get_method(), "GET")
        self.assertEqual(args[0].get_header("Authorization"), "Bearer secret")
        self.assertEqual(kwargs["timeout"], 8)
        proxy, redirect = build.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_safe_errors_never_expose_upstream_body_or_credentials(self):
        errors = [URLError("secret"), TimeoutError("secret"),
                  HTTPError(health.STATES_URL, 401, "secret", {}, io.BytesIO(b"secret")),
                  HTTPError(health.STATES_URL, 403, "secret", {}, io.BytesIO(b"secret")),
                  HTTPError(health.STATES_URL, 302, "secret", {}, io.BytesIO(b"secret")),
                  HTTPError(health.STATES_URL, 500, "secret", {}, io.BytesIO(b"secret"))]
        for error in errors:
            with self.subTest(error=error), patch.object(health, "build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(HTTPException) as caught:
                    health.fetch_states("secret")
                self.assertEqual(caught.exception.status_code, 502)
                self.assertNotIn("secret", caught.exception.detail)
                self.assertEqual(caught.exception.headers, health.NO_STORE)

    def test_invalid_html_json_shapes_and_oversize_responses_are_rejected(self):
        for content, mime in [(b"<!doctype html>", "text/html"), (b"not json", "application/json"),
                              (b"{}", "application/json"), (b"[null]", "application/json"),
                              (b" " * 65, "application/json")]:
            with self.subTest(content=content), patch.object(health, "build_opener") as build, patch.object(health, "MAX_RESPONSE_BYTES", 64):
                response = io.BytesIO(content)
                response.headers = Message()
                response.headers["Content-Type"] = mime
                build.return_value.open.return_value = response
                with self.assertRaises(HTTPException) as caught:
                    health.fetch_states("secret")
                self.assertEqual(caught.exception.status_code, 502)
