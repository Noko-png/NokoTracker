import assert from "node:assert/strict";
import { test } from "node:test";
import { addFoodBarcode, foodBarcodes, foodMatchesSearch, normalizeBarcodes } from "../src/barcodes.ts";

test("EAN lists preserve leading zeros and remove duplicate and empty entries", () => {
  assert.deepEqual(normalizeBarcodes([" 0012 3456-78905 ", "0012345678905", "", "4012345678901"]),
    ["0012345678905", "4012345678901"]);
});

test("old products with only a single barcode remain searchable", () => {
  assert.deepEqual(foodBarcodes({ barcode: "0012345678905" }), ["0012345678905"]);
  assert.deepEqual(foodBarcodes({}), []);
});

test("adding a scanned EAN preserves all existing codes and avoids duplicates", () => {
  const codes = ["0012345678905", "4012345678901"];
  assert.deepEqual(addFoodBarcode(codes, "5012345678900"), [...codes, "5012345678900"]);
  assert.deepEqual(addFoodBarcode(codes, codes[0]), codes);
  assert.deepEqual(foodBarcodes({ barcode: codes[0], barcodes: codes }), codes);
});

test("tracker and shopping searches find secondary EANs, names and brands", () => {
  const food = { name: "Testprodukt", brand: "Testmarke", barcode: "0012345678905", barcodes: ["4012345678901"] };
  for (const query of ["0012345678905", " 4012345678901 ", "Testprodukt", "TESTMARKE"]) {
    assert.equal(foodMatchesSearch(food, query), true);
  }
  assert.equal(foodMatchesSearch(food, "5012345678900"), false);
});
