import assert from "node:assert/strict";
import { test } from "node:test";
import { foodInventoryUnitNames } from "../src/foodInventory.ts";

test("stock units come only from the selected food's units and conversions", () => {
  const food = { product_unit_id: 1, serving_unit: "g", conversions: [{ unit: "Glas", quantity: 2 }] };
  const units = [{ id: 1, name: "Packung" }, { id: 2, name: "kg" }, { id: 3, name: "oz" }];
  assert.deepEqual(foodInventoryUnitNames(food, units), ["Packung", "g", "Glas"]);
});

test("food-defined units remain available without global entries and duplicate names collapse", () => {
  const food = {
    product_unit_id: null, serving_unit: "ml",
    conversions: [{ unit: " ML ", quantity: 250 }, { unit: "Becher", quantity: 1 }, { unit: "leer", quantity: 0 }],
  };
  assert.deepEqual(foodInventoryUnitNames(food, []), ["ml", "Becher"]);
});
