import assert from "node:assert/strict";
import { test } from "node:test";
import { formatFractionalQuantity, normalizeFractionalQuantityValue, newBookingKey } from "../src/quantity.ts";

test("small quantities and decimals retain their value when entered and displayed", () => {
  for (const value of [0.005, 0.08, 0.33, 0.000001, 0.999, 1.005, 12.3456789]) {
    assert.equal(normalizeFractionalQuantityValue(value), value);
    assert.equal(Number(formatFractionalQuantity(value).replace(",", ".")), value);
  }
});

test("actual fractions keep their fraction display", () => {
  assert.equal(formatFractionalQuantity(1 / 3), "1/3");
  assert.equal(formatFractionalQuantity(1.5), "1 1/2");
  assert.equal(formatFractionalQuantity(1 / 12), "1/12");
});

test("booking identifiers work without crypto.randomUUID", () => {
  const key = newBookingKey();
  assert.match(key, /^[a-f0-9]{32}$/);
  assert.notEqual(newBookingKey(), key);
});
