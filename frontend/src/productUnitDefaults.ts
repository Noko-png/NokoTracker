export const standardConversionUnits = ["g", "ml", "kg", "mg", "l", "oz", "lb"] as const;

type ProductUnitDefault = {
  name: string;
  default_conversion_quantity?: number | null;
  default_conversion_unit?: string | null;
};

const gramFactors: Record<string, number> = {
  g: 1, gram: 1, grams: 1, gramm: 1,
  kg: 1000, kilogram: 1000, kilograms: 1000, kilogramm: 1000,
  mg: 0.001, milligram: 0.001, milligrams: 0.001, milligramm: 0.001,
  ml: 1, milliliter: 1, milliliters: 1,
  l: 1000, liter: 1000, liters: 1000,
  oz: 28.3495, ounce: 28.3495, ounces: 28.3495,
  lb: 453.592, lbs: 453.592, pound: 453.592, pounds: 453.592,
};

export function unitQuantityToGrams(quantity: number, unit?: string | null): number | null {
  const factor = gramFactors[(unit ?? "").trim().toLowerCase()];
  return typeof factor === "number" ? quantity * factor : null;
}

export function defaultConversionForProductUnit(
  productUnit: ProductUnitDefault,
  currentSize: string,
  currentUnit: string,
) {
  const quantity = productUnit.default_conversion_quantity;
  const targetUnit = productUnit.default_conversion_unit;
  if (quantity != null && Number.isFinite(quantity) && quantity > 0 && targetUnit) {
    return { serving_size: String(quantity), serving_unit: targetUnit };
  }

  const directGrams = unitQuantityToGrams(1, productUnit.name);
  if (directGrams !== null) {
    return { serving_size: String(directGrams), serving_unit: "g" };
  }

  return { serving_size: currentSize || "100", serving_unit: currentUnit || "g" };
}

export function inventorySnapshotGramsPerUnit(
  item: { unit: string; serving_size?: number; serving_unit?: string },
  foodUnit: string,
  foodConversions: Array<{ unit: string; quantity: number }>,
): number | null {
  const unit = item.unit.trim().toLowerCase();
  const hasFoodConversion = foodConversions.some(
    (conversion) => conversion.quantity > 0 && conversion.unit.trim().toLowerCase() === unit,
  );
  if (!unit || unitQuantityToGrams(1, unit) !== null || unit === foodUnit.trim().toLowerCase() || hasFoodConversion) {
    return null;
  }
  if (item.serving_size == null || !Number.isFinite(item.serving_size) || item.serving_size <= 0 || !item.serving_unit) {
    return null;
  }
  return unitQuantityToGrams(item.serving_size, item.serving_unit) ?? item.serving_size;
}
