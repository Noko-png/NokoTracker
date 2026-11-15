import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveProfileId } from "../src/profileSelection.ts";

test("restore resolves a stale stored profile before nutrition requests", () => {
  assert.equal(resolveProfileId([{ id: 1 }], 2, { is_admin: true, user_id: null }), 1);
  assert.equal(resolveProfileId([{ id: 1 }, { id: 2 }], 2, { is_admin: true, user_id: null }), 2);
  assert.equal(resolveProfileId([], 2, { is_admin: true, user_id: null }), null);
});

test("non-admin selection never falls back to another person's profile", () => {
  assert.equal(resolveProfileId([{ id: 1 }], 1, { is_admin: false, user_id: 2 }), null);
  assert.equal(resolveProfileId([{ id: 1 }, { id: 2 }], 1, { is_admin: false, user_id: 2 }), 2);
  assert.equal(resolveProfileId([{ id: 1 }], 1, { is_admin: false, user_id: null }), null);
});
