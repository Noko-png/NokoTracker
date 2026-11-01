import assert from "node:assert/strict";
import { test } from "node:test";
import { readJsonResponse } from "../src/api/response.ts";

test("session JSON is returned without changing its access information", async () => {
  const session = { is_admin: true, ha_username: "owner", user_id: null };
  assert.deepEqual(await readJsonResponse(Response.json(session)), session);
});

test("HTML with success status produces a useful error rather than a JSON parse error", async () => {
  await assert.rejects(readJsonResponse(new Response("<!doctype html><html>NokoTracker</html>", {
    headers: { "content-type": "text/html; charset=utf-8" },
  })), /HTML statt JSON.*200/);
});

test("an expired ingress session returning HTML is also explained", async () => {
  await assert.rejects(readJsonResponse(new Response("<!doctype html><html>Login</html>", {
    status: 401, headers: { "content-type": "text/html" },
  })), /HTML statt JSON.*401/);
});

test("backend access errors retain their actual explanation", async () => {
  await assert.rejects(readJsonResponse(Response.json({ detail: "Profilzuordnung erforderlich." }, { status: 403 })), /Profilzuordnung erforderlich/);
});

test("empty delete responses do not try to parse JSON", async () => {
  assert.equal(await readJsonResponse(new Response(null, { status: 204 })), undefined);
});

test("invalid JSON and plain-text proxy errors do not expose parser exceptions", async () => {
  await assert.rejects(readJsonResponse(new Response("<!doctype html>", { headers: { "content-type": "application/json" } })), /kein gueltiges JSON/);
  await assert.rejects(readJsonResponse(new Response("Bad Gateway", { status: 502 })), /Unerwartete API-Antwort: 502/);
});
