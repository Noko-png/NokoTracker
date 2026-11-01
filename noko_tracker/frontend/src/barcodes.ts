type BarcodeProduct = { barcode?: string | null; barcodes?: string[] };

export function normalizeBarcodes(values: string[]): string[] {
  return [...new Set(values.map((code) => code.replace(/[\s-]+/g, "")).filter(Boolean))];
}

export function foodBarcodes(food: BarcodeProduct): string[] {
  return normalizeBarcodes([food.barcode ?? "", ...(food.barcodes ?? [])]);
}

export function addFoodBarcode(values: string[], code: string): string[] {
  return normalizeBarcodes([...values, code]);
}

export function foodMatchesSearch(food: BarcodeProduct & {
  name: string; brand?: string | null; storage_location?: string | null;
}, query: string): boolean {
  const search = query.trim().toLowerCase();
  return [food.name, food.brand ?? "", food.storage_location ?? "", ...foodBarcodes(food)]
    .join(" ").toLowerCase().includes(search);
}
