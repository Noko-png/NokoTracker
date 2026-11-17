import assert from "node:assert/strict";
import { test } from "node:test";
import { defaultConversionForProductUnit, unitQuantityToGrams } from "../src/productUnitDefaults.ts";

test("selecting a product unit prefills its configured conversion", () => {
  const unit = { name: "Packung", default_conversion_quantity: 500, default_conversion_unit: "g" };
  assert.deepEqual(defaultConversionForProductUnit(unit, "100", "g"), { serving_size: "500", serving_unit: "g" });
  assert.deepEqual(defaultConversionForProductUnit({ ...unit, name: "Flasche", default_conversion_unit: "ml" }, "100", "g"),
    { serving_size: "500", serving_unit: "ml" });
});

test("configured defaults take precedence over built-in unit suggestions and preserve decimal inputs", () => {
  const unit = { name: "kg", default_conversion_quantity: 0.5, default_conversion_unit: "kg" };
  assert.deepEqual(defaultConversionForProductUnit(unit, "100", "g"), { serving_size: "0.5", serving_unit: "kg" });
});

test("units without defaults retain known mass conversions or the current product values", () => {
  assert.deepEqual(defaultConversionForProductUnit({ name: "kg" }, "100", "g"), { serving_size: "1000", serving_unit: "g" });
  assert.deepEqual(defaultConversionForProductUnit({ name: "Packung", default_conversion_quantity: null, default_conversion_unit: null }, "250", "ml"),
    { serving_size: "250", serving_unit: "ml" });
  assert.deepEqual(defaultConversionForProductUnit({ name: "Packung" }, "", ""), { serving_size: "100", serving_unit: "g" });
});

test("shared defaults are not used when converting already saved food quantities", () => {
  assert.equal(unitQuantityToGrams(2, "kg"), 2000);
  assert.equal(unitQuantityToGrams(500, "mg"), 0.5);
  assert.equal(unitQuantityToGrams(2, "Packung"), null);
});
