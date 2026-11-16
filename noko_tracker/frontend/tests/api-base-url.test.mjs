import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveApiBaseUrl } from "../src/api/baseUrl.ts";

test("keeps configured relative, loopback and HTTPS API bases", () => {
  assert.equal(resolveApiBaseUrl(undefined), "http://127.0.0.1:8000");
  assert.equal(resolveApiBaseUrl("./"), "./");
  assert.equal(resolveApiBaseUrl("/tracker/api"), "/tracker/api");
  assert.equal(resolveApiBaseUrl("http://localhost:8000"), "http://localhost:8000/");
  assert.equal(resolveApiBaseUrl("https://ha.example:8123/api"), "https://ha.example:8123/api");
});

test("rejects insecure remote API bases and implicit protocol-relative origins", () => {
  assert.throws(() => resolveApiBaseUrl("http://ha.example:8123"), /HTTPS/);
  assert.throws(() => resolveApiBaseUrl("//ha.example:8123"), /HTTPS/);
});
