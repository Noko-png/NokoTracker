import assert from "node:assert/strict";
import { test } from "node:test";
import { inventorySnapshotGramsPerUnit } from "../src/productUnitDefaults.ts";

test("a custom inventory unit uses the lot's saved size for stock deductions", () => {
  const item = { unit: "Beutel", serving_size: 500, serving_unit: "g" };
  const grams = inventorySnapshotGramsPerUnit(item, "g", []);
  assert.equal(grams, 500);
  assert.equal(250 / grams, 0.5);
  assert.equal(inventorySnapshotGramsPerUnit({ ...item, unit: "Flasche", serving_size: 0.33, serving_unit: "l" }, "ml", []), 330);
});

test("physical units and explicit food conversions keep their existing priority", () => {
  const item = { unit: "Beutel", serving_size: 500, serving_unit: "g" };
  assert.equal(inventorySnapshotGramsPerUnit(item, "g", [{ unit: " beutel ", quantity: 2 }]), null);
  assert.equal(inventorySnapshotGramsPerUnit(item, "BEUTEL", []), null);
  assert.equal(inventorySnapshotGramsPerUnit({ ...item, unit: "kg" }, "g", []), null);
});

test("older barcode summaries without a saved size use the existing food conversion", () => {
  assert.equal(inventorySnapshotGramsPerUnit({ unit: "Beutel" }, "g", []), null);
});
