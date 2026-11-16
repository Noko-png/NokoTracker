import assert from "node:assert/strict";
import { test } from "node:test";
import { localRecipeImagePath, recipeImageUpdate } from "../src/recipeImagePath.ts";

test("recipe images only render URLs containing embedded image data", () => {
  const localImage = "data:image/png;base64,dGVzdA==";
  assert.equal(localRecipeImagePath(localImage), localImage);
  for (const path of [
    "https://example.invalid/image.png",
    "//example.invalid/image.png",
    "/assets/image.png",
    "blob:https://example.invalid/opaque-id",
    "data:text/plain;base64,dGVzdA==",
    "data:image/png;base64,a",
  ]) {
    assert.equal(localRecipeImagePath(path), undefined);
  }
});

test("recipe updates preserve old blocked image references until removed or replaced", () => {
  const previousImage = "https://example.invalid/image.png";
  const newImage = "data:image/jpeg;base64,dGVzdA==";
  assert.equal(JSON.stringify({ image_path: recipeImageUpdate(previousImage) }), "{}");
  assert.equal(recipeImageUpdate(""), null);
  assert.equal(recipeImageUpdate(newImage), newImage);
});
