import assert from "node:assert/strict";
import { test } from "node:test";
import {
  configuredConversionUnitNames, configuredUnitNames,
  defaultConversionForProductUnit, unitQuantityToGrams,
} from "../src/productUnitDefaults.ts";

test("unit choices come from configured units without adding known measurement names", () => {
  const units = [{ name: "g" }, { name: "kg" }, { name: "Packung" }];
  assert.deepEqual(configuredUnitNames(units), ["g", "kg", "Packung"]);
  assert.deepEqual(configuredConversionUnitNames(units), ["g", "kg"]);
  assert.deepEqual(configuredUnitNames([]), []);
  assert.deepEqual(configuredConversionUnitNames([]), []);
});

test("oz becomes selectable only after it is configured", () => {
  const units = [{ name: "g" }];
  assert.equal(configuredConversionUnitNames(units).includes("oz"), false);
  units.push({ name: "oz" });
  assert.deepEqual(configuredConversionUnitNames(units), ["g", "oz"]);
  assert.equal(unitQuantityToGrams(1, "oz"), 28.3495);
});

test("configured unit spelling is retained and equivalent names are deduplicated", () => {
  const units = [{ name: " KG " }, { name: "kg" }, { name: "" }, { name: "Flasche" }];
  assert.deepEqual(configuredUnitNames(units), ["KG", "Flasche"]);
  assert.deepEqual(configuredConversionUnitNames(units), ["kg"]);
});

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
