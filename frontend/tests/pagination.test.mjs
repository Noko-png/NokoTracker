import assert from "node:assert/strict";
import { test } from "node:test";
import { loadAllPages } from "../src/pagination.ts";

test("food catalogue loads beyond both the default 100 and maximum page size 500", async () => {
  const foods = Array.from({ length: 1132 }, (_, id) => ({ id }));
  const requests = [];
  const actual = await loadAllPages(async (skip, limit) => {
    requests.push(skip);
    return foods.slice(skip, skip + limit);
  });
  assert.deepEqual(actual, foods);
  assert.deepEqual(requests, [0, 500, 1000]);
});

test("empty lists complete and a failed later page does not return a partial catalogue", async () => {
  assert.deepEqual(await loadAllPages(async () => []), []);
  await assert.rejects(loadAllPages(async (skip, limit) => {
    if (skip) throw new Error("offline");
    return Array(limit).fill({ id: 1 });
  }), /offline/);
});
