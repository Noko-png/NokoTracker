type FoodInventoryUnits = {
  product_unit_id?: number | null;
  serving_unit: string;
  conversions?: Array<{ unit: string; quantity: number }>;
};

export function foodInventoryUnitNames(
  food: FoodInventoryUnits,
  productUnits: Array<{ id: number; name: string }>,
): string[] {
  const primaryUnit = productUnits.find((unit) => unit.id === food.product_unit_id)?.name;
  const units = [
    primaryUnit ?? "",
    food.serving_unit,
    ...(food.conversions ?? []).filter((conversion) => conversion.quantity > 0).map((conversion) => conversion.unit),
  ];
  const seen = new Set<string>();
  return units.map((unit) => unit.trim()).filter((unit) => {
    const name = unit.toLowerCase();
    if (!name || seen.has(name)) return false;
    seen.add(name);
    return true;
  });
}
