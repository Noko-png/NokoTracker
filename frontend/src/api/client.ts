export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export type DashboardSummary = {
  users: number;
  foods: number;
  recipes: number;
  inventory_items: number;
  shopping_open_items: number;
  upcoming_events: number;
  recent_meals: number;
};

export type ThemeName = "light" | "dark" | "purple" | "google";

export type User = {
  id: number;
  username: string;
  password: string;
  theme: ThemeName;
  daily_calories: number;
  protein_percent: number;
  fat_percent: number;
  carbs_percent: number;
};

export type UserCreate = Omit<User, "id">;
export type UserUpdate = Partial<UserCreate>;

export type Food = {
  id: number;
  name: string;
  emoji: string;
  is_archived: boolean;
  brand?: string | null;
  category?: string | null;
  storage_location?: string | null;
  product_group_id?: number | null;
  product_unit_id?: number | null;
  minimum_quantity: number;
  barcode?: string | null;
  purchase_date?: string | null;
  expiry_days?: number | null;
  price?: number | null;
  serving_size: number;
  serving_unit: string;
  conversions: FoodConversion[];
  calories_per_100g: number;
  protein_per_100g: number;
  carbs_per_100g: number;
  fat_per_100g: number;
  created_at: string;
  updated_at: string;
};

export type FoodConversion = {
  id: number;
  food_id: number;
  quantity: number;
  unit: string;
  created_at: string;
  updated_at: string;
};

export type FoodConversionCreate = {
  quantity: number;
  unit: string;
};

export type FoodCreatePayload = Omit<
  Partial<Food>,
  "id" | "conversions" | "created_at" | "updated_at"
> & {
  conversions?: FoodConversionCreate[];
};

export type ProductGroup = {
  id: number;
  name: string;
  default_expiry_days?: number | null;
  default_storage_location?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductGroupCreate = Omit<
  ProductGroup,
  "id" | "created_at" | "updated_at"
>;

export type ProductGroupUpdate = Partial<ProductGroupCreate>;

export type ProductUnit = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type ProductUnitCreate = Omit<
  ProductUnit,
  "id" | "created_at" | "updated_at"
>;

export type ProductUnitUpdate = Partial<ProductUnitCreate>;

export type StorageLocation = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type StorageLocationCreate = Omit<
  StorageLocation,
  "id" | "created_at" | "updated_at"
>;

export type StorageLocationUpdate = Partial<StorageLocationCreate>;

export type InventoryItem = {
  id: number;
  food_id?: number | null;
  name: string;
  emoji: string;
  brand?: string | null;
  category?: string | null;
  quantity: number;
  unit: string;
  minimum_quantity: number;
  storage_location?: string | null;
  expiry_days?: number | null;
  expiry_date?: string | null;
  purchase_date?: string | null;
  price?: number | null;
  barcode?: string | null;
  image_path?: string | null;
  notes?: string | null;
  product_group_id?: number | null;
  product_group?: ProductGroup | null;
  product_unit_id?: number | null;
  product_unit?: ProductUnit | null;
  food?: Food | null;
  serving_size: number;
  serving_unit: string;
  calories_per_100g: number;
  protein_per_100g: number;
  carbs_per_100g: number;
  fat_per_100g: number;
  created_at: string;
  updated_at: string;
};

export type InventoryItemSummary = Pick<
  InventoryItem,
  | "id"
  | "name"
  | "emoji"
  | "brand"
  | "food_id"
  | "quantity"
  | "unit"
  | "minimum_quantity"
  | "storage_location"
  | "expiry_days"
  | "expiry_date"
  | "product_group_id"
  | "product_unit_id"
  | "calories_per_100g"
  | "protein_per_100g"
  | "carbs_per_100g"
  | "fat_per_100g"
>;

export type FoodBarcodeLookup = {
  barcode: string;
  source: "local_food" | "local_inventory" | "open_food_facts";
  food: Food;
  inventory_items: InventoryItemSummary[];
};

export type FoodBarcodePreview = {
  barcode: string;
  source: "local_food" | "local_inventory" | "open_food_facts";
  name: string;
  brand?: string | null;
  category?: string | null;
  serving_size: number;
  serving_unit: string;
  calories_per_100g: number;
  protein_per_100g: number;
  fat_per_100g: number;
  carbs_per_100g: number;
};

export type RecipeIngredient = {
  id: number;
  recipe_id: number;
  food_id: number;
  quantity: number;
  unit: string;
  notes?: string | null;
  food: Pick<
    Food,
    | "id"
    | "name"
    | "emoji"
    | "brand"
    | "category"
    | "product_unit_id"
    | "serving_size"
    | "serving_unit"
    | "conversions"
    | "calories_per_100g"
    | "protein_per_100g"
    | "carbs_per_100g"
    | "fat_per_100g"
  >;
};

export type RecipeIngredientCreate = {
  food_id: number;
  quantity: number;
  unit: string;
  notes?: string | null;
};

export type RecipeIngredientUpdate = Partial<RecipeIngredientCreate>;

export type Recipe = {
  id: number;
  name: string;
  emoji: string;
  is_archived: boolean;
  description?: string | null;
  instructions?: string | null;
  tags: string[];
  image_path?: string | null;
  servings: number;
  prep_time_minutes?: number | null;
  cook_time_minutes?: number | null;
  created_by_user_id?: number | null;
  prepared_food_id?: number | null;
  prepared_food?: Food | null;
  ingredients: RecipeIngredient[];
  created_at: string;
  updated_at: string;
};

export type RecipeCreate = {
  name: string;
  emoji?: string;
  description?: string | null;
  instructions?: string | null;
  tags?: string[];
  image_path?: string | null;
  servings: number;
  prep_time_minutes?: number | null;
  cook_time_minutes?: number | null;
  created_by_user_id?: number | null;
  ingredients?: RecipeIngredientCreate[];
};

export type RecipeUpdate = Partial<RecipeCreate>;

export type MacroValues = {
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
};

export type NutritionDay = {
  date: string;
  user_id: number;
  totals: MacroValues;
  goals: MacroValues;
  remaining: MacroValues;
  percentages: MacroValues;
};

export type RecipeNutrition = {
  recipe_id: number;
  recipe_name: string;
  servings: number;
  total: MacroValues;
  per_serving: MacroValues;
};

export type RecipeShoppingListMissingIngredient = {
  food_id: number;
  name: string;
  required_quantity: number;
  available_quantity: number;
  missing_quantity: number;
  unit: string;
  action: "created" | "updated" | "covered";
  shopping_item: ShoppingListItem;
};

export type RecipeShoppingListSyncResult = {
  recipe_id: number;
  recipe_name: string;
  missing: RecipeShoppingListMissingIngredient[];
};

export type RecipePrepareConsumedIngredient = {
  food_id: number;
  name: string;
  quantity: number;
  unit: string;
};

export type RecipePrepareResult = {
  recipe_id: number;
  recipe_name: string;
  prepared_quantity: number;
  prepared_unit: string;
  inventory_item: InventoryItem;
  consumed: RecipePrepareConsumedIngredient[];
};

export type ShoppingListItem = {
  id: number;
  name: string;
  food_id?: number | null;
  inventory_item_id?: number | null;
  quantity: number;
  unit: string;
  store?: string | null;
  is_checked: boolean;
  notes?: string | null;
  food?: Food | null;
  inventory_item?: InventoryItem | null;
  created_at: string;
  updated_at: string;
};

export type InventoryShoppingListItemCreate = {
  quantity?: number | null;
  notes?: string | null;
};

export type ShoppingListInventoryUnknownAction =
  | "ask"
  | "create"
  | "delete"
  | "keep";

export type ShoppingListInventoryImportRequest = {
  purchase_date?: string;
  unknown_item_action?: ShoppingListInventoryUnknownAction;
};

export type ShoppingListInventoryImportResult = {
  imported_count: number;
  created_inventory_items: InventoryItem[];
  updated_inventory_items: InventoryItem[];
  deleted_shopping_item_ids: number[];
  kept_shopping_item_ids: number[];
  unknown_items: ShoppingListItem[];
  requires_decision: boolean;
  message: string;
};

export type CalendarEvent = {
  id: number;
  title: string;
  description?: string | null;
  start_at: string;
  end_at?: string | null;
  location?: string | null;
  entry_type: "event" | "task";
  all_day: boolean;
  is_completed: boolean;
  recurrence_frequency: "none" | "daily" | "weekly" | "monthly" | "yearly";
  recurrence_interval: number;
  recurrence_until?: string | null;
  user_id?: number | null;
  group_id?: number | null;
  group?: CalendarGroup | null;
  exclusions: CalendarEventExclusion[];
  created_at: string;
  updated_at: string;
};

export type CalendarEventCreate = Omit<
  CalendarEvent,
  "id" | "created_at" | "updated_at" | "group" | "exclusions"
>;

export type CalendarEventUpdate = Partial<CalendarEventCreate>;

export type CalendarEventExclusion = {
  id: number;
  event_id: number;
  occurrence_start_at: string;
};

export type CalendarGroup = {
  id: number;
  name: string;
  color: string;
  suppresses_group_ids: number[];
  hide_from_dashboard_and_month: boolean;
  user_id?: number | null;
  created_at?: string;
  updated_at?: string;
};

export type CalendarGroupCreate = Omit<
  CalendarGroup,
  "id" | "created_at" | "updated_at"
>;

export type CalendarGroupUpdate = Partial<CalendarGroupCreate>;

export type MealLogCreate = {
  eaten_at: string;
  meal_type?: string | null;
  quantity: number;
  unit: string;
  notes?: string | null;
  user_id?: number | null;
  food_id?: number | null;
  recipe_id?: number | null;
  quick_add_name?: string | null;
  quick_calories?: number | null;
  quick_protein?: number | null;
  quick_fat?: number | null;
  quick_carbs?: number | null;
  meal_source?: string;
  planned_inventory_deduction?: boolean;
  inventory_deducted_at?: string | null;
};

export type MealLog = MealLogCreate & {
  id: number;
  created_at: string;
  updated_at: string;
  food?: Pick<
    Food,
    | "id"
    | "name"
    | "brand"
    | "serving_size"
    | "serving_unit"
    | "calories_per_100g"
    | "protein_per_100g"
    | "fat_per_100g"
    | "carbs_per_100g"
  > | null;
  recipe?: Pick<Recipe, "id" | "name" | "emoji" | "servings"> | null;
};

export type MealLogUpdate = Partial<MealLogCreate>;

export type MealInventoryDeductionItem = {
  food_id: number;
  name: string;
  quantity: number;
  unit: string;
};

export type MealInventoryDeductionResult = {
  meal_log: MealLog;
  consumed: MealInventoryDeductionItem[];
};

export type InventoryWarnings = {
  low_stock: InventoryItem[];
  expiring_soon: InventoryItem[];
  expired: InventoryItem[];
};

export type CsvImportResult = {
  directory: string;
  dry_run: boolean;
  imported: Record<string, Record<string, number>>;
  warnings: string[];
};

export type ReceiptImportStatus = "ready" | "needs_review" | "ignored";

export type ReceiptFoodSuggestion = {
  food: Food;
  score: number;
};

export type ReceiptImportPreviewItem = {
  source_index: number;
  raw_name: string;
  name: string;
  quantity: number;
  unit: string;
  unit_price?: number | null;
  total_price?: number | null;
  tax_class?: string | null;
  status: ReceiptImportStatus;
  review_reason?: string | null;
  matched_food_id?: number | null;
  matched_food?: Food | null;
  suggestions: ReceiptFoodSuggestion[];
};

export type ReceiptImportPreview = {
  filename: string;
  receipt_date?: string | null;
  store_name?: string | null;
  total?: number | null;
  items: ReceiptImportPreviewItem[];
  imported_count: number;
  review_count: number;
  ignored_count: number;
  warnings: string[];
};

export type ReceiptImportBookItem = {
  source_index: number;
  raw_name: string;
  name: string;
  food_id?: number | null;
  quantity: number | string;
  unit: string;
  unit_price?: number | string | null;
  total_price?: number | string | null;
  storage_location?: string | null;
  book: boolean;
};

export type ReceiptImportBookRequest = {
  purchase_date: string;
  default_storage_location?: string | null;
  items: ReceiptImportBookItem[];
};

export type ReceiptImportBookResult = {
  booked_count: number;
  skipped_count: number;
  inventory_items: InventoryItem[];
  warnings: string[];
};

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const body =
    options.body === undefined ? undefined : JSON.stringify(options.body);
  if (body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // Keep the HTTP status when the backend sends an empty error body.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary");
}

export function getUsers() {
  return request<User[]>("/users");
}

export function createUser(user: UserCreate) {
  return request<User>("/users", {
    method: "POST",
    body: user,
  });
}

export function updateUser(id: number, user: UserUpdate) {
  return request<User>(`/users/${id}`, {
    method: "PATCH",
    body: user,
  });
}

export function deleteUser(id: number) {
  return request<void>(`/users/${id}`, {
    method: "DELETE",
  });
}

export function getInventory() {
  return request<InventoryItem[]>("/inventory");
}

export function createInventoryItem(item: Omit<Partial<InventoryItem>, "id">) {
  return request<InventoryItem>("/inventory", {
    method: "POST",
    body: item,
  });
}

export function updateInventoryItem(
  id: number,
  item: Omit<Partial<InventoryItem>, "id">,
) {
  return request<InventoryItem>(`/inventory/${id}`, {
    method: "PUT",
    body: item,
  });
}

export function deleteInventoryItem(id: number) {
  return request<void>(`/inventory/${id}`, {
    method: "DELETE",
  });
}

export function increaseInventoryItem(id: number, amount: number) {
  return request<InventoryItem>(`/inventory/${id}/increase`, {
    method: "POST",
    body: { amount },
  });
}

export function decreaseInventoryItem(id: number, amount: number) {
  return request<InventoryItem>(`/inventory/${id}/decrease`, {
    method: "POST",
    body: { amount },
  });
}

export function getInventoryWarnings(days = 7) {
  return request<InventoryWarnings>(`/inventory/warnings?days=${days}`);
}

export function getProductGroups() {
  return request<ProductGroup[]>("/product-groups");
}

export function createProductGroup(group: ProductGroupCreate) {
  return request<ProductGroup>("/product-groups", {
    method: "POST",
    body: group,
  });
}

export function updateProductGroup(id: number, group: ProductGroupUpdate) {
  return request<ProductGroup>(`/product-groups/${id}`, {
    method: "PATCH",
    body: group,
  });
}

export function deleteProductGroup(id: number) {
  return request<void>(`/product-groups/${id}`, {
    method: "DELETE",
  });
}

export function getProductUnits() {
  return request<ProductUnit[]>("/product-units");
}

export function createProductUnit(unit: ProductUnitCreate) {
  return request<ProductUnit>("/product-units", {
    method: "POST",
    body: unit,
  });
}

export function updateProductUnit(id: number, unit: ProductUnitUpdate) {
  return request<ProductUnit>(`/product-units/${id}`, {
    method: "PATCH",
    body: unit,
  });
}

export function deleteProductUnit(id: number) {
  return request<void>(`/product-units/${id}`, {
    method: "DELETE",
  });
}

export function getFoods() {
  return request<Food[]>("/foods");
}

export function lookupFoodByBarcode(barcode: string) {
  return request<FoodBarcodeLookup>(
    `/foods/barcode/${encodeURIComponent(barcode)}`,
  );
}

export function previewFoodByBarcode(barcode: string) {
  return request<FoodBarcodePreview>(
    `/foods/barcode/${encodeURIComponent(barcode)}/preview`,
  );
}

export function createFood(food: FoodCreatePayload) {
  return request<Food>("/foods", {
    method: "POST",
    body: food,
  });
}

export function updateFood(id: number, food: FoodCreatePayload) {
  return request<Food>(`/foods/${id}`, {
    method: "PATCH",
    body: food,
  });
}

export function deleteFood(id: number, keepReference = false) {
  const query = keepReference ? "?keep_reference=true" : "";
  return request<void>(`/foods/${id}${query}`, {
    method: "DELETE",
  });
}

export function getStorageLocations() {
  return request<StorageLocation[]>("/storage-locations");
}

export function createStorageLocation(location: StorageLocationCreate) {
  return request<StorageLocation>("/storage-locations", {
    method: "POST",
    body: location,
  });
}

export function updateStorageLocation(
  id: number,
  location: StorageLocationUpdate,
) {
  return request<StorageLocation>(`/storage-locations/${id}`, {
    method: "PATCH",
    body: location,
  });
}

export function deleteStorageLocation(id: number) {
  return request<void>(`/storage-locations/${id}`, {
    method: "DELETE",
  });
}

export function getRecipes() {
  return request<Recipe[]>("/recipes");
}

export function createRecipe(recipe: RecipeCreate) {
  return request<Recipe>("/recipes", {
    method: "POST",
    body: recipe,
  });
}

export function updateRecipe(id: number, recipe: RecipeUpdate) {
  return request<Recipe>(`/recipes/${id}`, {
    method: "PATCH",
    body: recipe,
  });
}

export function deleteRecipe(id: number, keepReference = false) {
  const query = keepReference ? "?keep_reference=true" : "";
  return request<void>(`/recipes/${id}${query}`, {
    method: "DELETE",
  });
}

export function createRecipeIngredient(
  recipeId: number,
  ingredient: RecipeIngredientCreate,
) {
  return request<RecipeIngredient>(`/recipes/${recipeId}/ingredients`, {
    method: "POST",
    body: ingredient,
  });
}

export function deleteRecipeIngredient(id: number) {
  return request<void>(`/recipes/ingredients/${id}`, {
    method: "DELETE",
  });
}

export function updateRecipeIngredient(
  id: number,
  ingredient: RecipeIngredientUpdate,
) {
  return request<RecipeIngredient>(`/recipes/ingredients/${id}`, {
    method: "PATCH",
    body: ingredient,
  });
}

export function getRecipeNutrition(recipeId: number) {
  return request<RecipeNutrition>(`/nutrition/recipes/${recipeId}`);
}

export function syncRecipeShoppingList(recipeId: number) {
  return request<RecipeShoppingListSyncResult>(
    `/recipes/${recipeId}/sync-shopping-list`,
    {
      method: "POST",
    },
  );
}

export function prepareRecipe(recipeId: number) {
  return request<RecipePrepareResult>(`/recipes/${recipeId}/prepare`, {
    method: "POST",
    body: {},
  });
}

export function getNutritionDay(userId: number, date: string) {
  return request<NutritionDay>(`/nutrition/day?user_id=${userId}&date=${date}`);
}

export function createMealLog(mealLog: MealLogCreate) {
  return request<MealLog>("/meals/logs", {
    method: "POST",
    body: mealLog,
  });
}

export function getMealLogs(limit = 500) {
  return request<MealLog[]>(`/meals/logs?limit=${limit}`);
}

export function updateMealLog(id: number, mealLog: MealLogUpdate) {
  return request<MealLog>(`/meals/logs/${id}`, {
    method: "PATCH",
    body: mealLog,
  });
}

export function deleteMealLog(id: number) {
  return request<void>(`/meals/logs/${id}`, {
    method: "DELETE",
  });
}

export function deductMealLogInventory(id: number) {
  return request<MealInventoryDeductionResult>(
    `/meals/logs/${id}/deduct-inventory`,
    {
      method: "POST",
      body: {},
    },
  );
}

export function getShoppingList() {
  return request<ShoppingListItem[]>("/shopping-list");
}

export function createShoppingListItem(
  item: Omit<Partial<ShoppingListItem>, "id">,
) {
  return request<ShoppingListItem>("/shopping-list", {
    method: "POST",
    body: item,
  });
}

export function updateShoppingListItem(
  id: number,
  item: Omit<
    Partial<ShoppingListItem>,
    "id" | "food" | "inventory_item" | "created_at" | "updated_at"
  >,
) {
  return request<ShoppingListItem>(`/shopping-list/${id}`, {
    method: "PUT",
    body: item,
  });
}

export function addInventoryItemToShoppingList(
  inventoryItemId: number,
  item: InventoryShoppingListItemCreate,
) {
  return request<ShoppingListItem>(
    `/shopping-list/from-inventory/${inventoryItemId}`,
    {
      method: "POST",
      body: item,
    },
  );
}

export function checkShoppingListItem(id: number) {
  return request<ShoppingListItem>(`/shopping-list/${id}/check`, {
    method: "POST",
  });
}

export function uncheckShoppingListItem(id: number) {
  return request<ShoppingListItem>(`/shopping-list/${id}/uncheck`, {
    method: "POST",
  });
}

export function deleteShoppingListItem(id: number) {
  return request<void>(`/shopping-list/${id}`, {
    method: "DELETE",
  });
}

export function generateShoppingListFromLowStock() {
  return request<ShoppingListItem[]>("/shopping-list/generate-from-low-stock", {
    method: "POST",
  });
}

export function importShoppingListToInventory(
  requestBody: ShoppingListInventoryImportRequest = {},
) {
  return request<ShoppingListInventoryImportResult>(
    "/shopping-list/import-to-inventory",
    {
      method: "POST",
      body: requestBody,
    },
  );
}

export function getCalendarEvents() {
  return request<CalendarEvent[]>("/calendar/events?limit=500");
}

export function getCalendarGroups() {
  return request<CalendarGroup[]>("/calendar/groups?limit=500");
}

export function importGrocyCsv(directory: string, dryRun = false) {
  return request<CsvImportResult>("/imports/grocy-csv", {
    method: "POST",
    body: {
      directory,
      dry_run: dryRun,
    },
  });
}

export function previewReceiptImport(filename: string, contentBase64: string) {
  return request<ReceiptImportPreview>("/imports/receipt/preview", {
    method: "POST",
    body: {
      filename,
      content_base64: contentBase64,
    },
  });
}

export function bookReceiptImport(requestBody: ReceiptImportBookRequest) {
  return request<ReceiptImportBookResult>("/imports/receipt/book", {
    method: "POST",
    body: requestBody,
  });
}

export function createCalendarEvent(event: CalendarEventCreate) {
  return request<CalendarEvent>("/calendar/events", {
    method: "POST",
    body: event,
  });
}

export function updateCalendarEvent(id: number, event: CalendarEventUpdate) {
  return request<CalendarEvent>(`/calendar/events/${id}`, {
    method: "PATCH",
    body: event,
  });
}

export function deleteCalendarEvent(id: number) {
  return request<void>(`/calendar/events/${id}`, {
    method: "DELETE",
  });
}

export function excludeCalendarOccurrence(id: number, occurrenceStartAt: string) {
  return request<CalendarEventExclusion>(`/calendar/events/${id}/exclusions`, {
    method: "POST",
    body: { occurrence_start_at: occurrenceStartAt },
  });
}

export function createCalendarGroup(group: CalendarGroupCreate) {
  return request<CalendarGroup>("/calendar/groups", {
    method: "POST",
    body: group,
  });
}

export function updateCalendarGroup(id: number, group: CalendarGroupUpdate) {
  return request<CalendarGroup>(`/calendar/groups/${id}`, {
    method: "PATCH",
    body: group,
  });
}

export function deleteCalendarGroup(id: number) {
  return request<void>(`/calendar/groups/${id}`, {
    method: "DELETE",
  });
}
