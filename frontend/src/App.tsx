import {
  AlertTriangle,
  Apple,
  BarChart3,
  CalendarDays,
  Camera,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Database,
  Eye,
  EyeOff,
  Filter,
  Gauge,
  LayoutDashboard,
  Menu,
  Minus,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ScanBarcode,
  ShoppingCart,
  Soup,
  Trash2,
  Utensils,
  X,
} from "lucide-react";
import type {
  ChangeEvent,
  CSSProperties,
  FormEvent,
  MouseEvent as ReactMouseEvent,
} from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  API_BASE_URL,
  type CalendarEvent,
  type CalendarEventCreate,
  type CalendarGroup,
  type CalendarGroupCreate,
  type CsvImportResult,
  type DashboardSummary,
  type Food,
  type FoodBarcodeLookup,
  type FoodBarcodePreview,
  type InventoryItem,
  type InventoryItemSummary,
  type InventoryWarnings,
  type MacroValues,
  type MealLog,
  type NutritionDay,
  type ProductGroup,
  type ProductGroupCreate,
  type ProductGroupUpdate,
  type ProductUnit,
  type ProductUnitCreate,
  type ProductUnitUpdate,
  type Recipe,
  type RecipeIngredient,
  type RecipePrepareResult,
  type RecipeNutrition,
  type RecipeShoppingListSyncResult,
  type ReceiptImportBookItem,
  type ReceiptImportBookRequest,
  type ReceiptImportBookResult,
  type ReceiptImportPreview,
  type ReceiptImportStatus,
  type ShoppingListItem,
  type ShoppingListInventoryImportResult,
  type ShoppingListInventoryUnknownAction,
  type StorageLocation,
  type StorageLocationCreate,
  type StorageLocationUpdate,
  type ThemeName,
  type User,
  type UserCreate,
  bookReceiptImport,
  checkShoppingListItem,
  createCalendarEvent,
  createCalendarGroup,
  createFood,
  createInventoryItem,
  createShoppingListItem,
  createProductGroup,
  createProductUnit,
  createRecipeIngredient,
  createStorageLocation,
  createMealLog,
  createRecipe,
  createUser,
  decreaseInventoryItem,
  deductMealLogInventory,
  deleteInventoryItem,
  deleteMealLog,
  deleteCalendarEvent,
  deleteCalendarGroup,
  deleteFood,
  deleteProductGroup,
  deleteProductUnit,
  deleteRecipe,
  deleteRecipeIngredient,
  deleteStorageLocation,
  deleteShoppingListItem,
  deleteUser,
  generateShoppingListFromLowStock,
  getCalendarGroups,
  getCalendarEvents,
  getDashboardSummary,
  getFoods,
  getInventory,
  getInventoryWarnings,
  getMealLogs,
  getNutritionDay,
  getProductGroups,
  getProductUnits,
  getRecipeNutrition,
  getRecipes,
  getShoppingList,
  getStorageLocations,
  getUsers,
  importGrocyCsv,
  importShoppingListToInventory,
  increaseInventoryItem,
  lookupFoodByBarcode,
  excludeCalendarOccurrence,
  prepareRecipe,
  previewFoodByBarcode,
  previewReceiptImport,
  uncheckShoppingListItem,
  updateShoppingListItem,
  updateInventoryItem,
  updateFood,
  updateMealLog,
  updateCalendarGroup,
  updateProductGroup,
  updateProductUnit,
  updateRecipe,
  updateRecipeIngredient,
  updateStorageLocation,
  updateUser,
  updateCalendarEvent,
  syncRecipeShoppingList,
} from "./api/client";

type BarcodeDetectorResult = {
  rawValue: string;
};

type BarcodeDetectorConstructor = new (options?: {
  formats?: string[];
}) => {
  detect: (source: HTMLVideoElement) => Promise<BarcodeDetectorResult[]>;
};

type DeductableInventoryItem = (InventoryItem | InventoryItemSummary) & {
  barcode?: string | null;
};

type InventoryDeduction = {
  amount: number;
  inventoryItem: DeductableInventoryItem;
};

type Page =
  | "dashboard"
  | "calendar"
  | "foods"
  | "masterData"
  | "recipes"
  | "nutrition"
  | "shopping"
  | "settings";

type InventoryStatus = "ok" | "low" | "expiring" | "expired";

type InventoryColumnKey =
  | "brand"
  | "product_group"
  | "quantity"
  | "conversion"
  | "minimum_quantity"
  | "purchase_date"
  | "expiry_days"
  | "expiry_date"
  | "price"
  | "calories"
  | "protein"
  | "fat"
  | "carbs"
  | "status";

type InventoryColumnDefinition = {
  key: InventoryColumnKey;
  label: string;
  render: (item: InventoryItem) => React.ReactNode;
};

type InventoryForm = {
  food_id: string;
  food_query: string;
  name: string;
  emoji: string;
  brand: string;
  category: string;
  quantity: string;
  unit: string;
  minimum_quantity: string;
  storage_location: string;
  expiry_days: string;
  purchase_date: string;
  price: string;
  barcode: string;
  image_path: string;
  notes: string;
  product_group_id: string;
  product_unit_id: string;
  serving_size: string;
  serving_unit: string;
  calories_per_100g: string;
  protein_per_100g: string;
  fat_per_100g: string;
  carbs_per_100g: string;
};

type MasterDataTab = "foods" | "locations" | "units" | "groups";

type RecipeSort = "name" | "tag" | "servings" | "calories" | "calories-desc";

type FoodConversionForm = {
  quantity: string;
  unit: string;
};

type FoodForm = {
  name: string;
  emoji: string;
  brand: string;
  category: string;
  storage_location: string;
  product_group_id: string;
  product_unit_id: string;
  minimum_quantity: string;
  barcode: string;
  purchase_date: string;
  expiry_days: string;
  price: string;
  serving_size: string;
  serving_unit: string;
  conversions: FoodConversionForm[];
  calories_per_100g: string;
  protein_per_100g: string;
  fat_per_100g: string;
  carbs_per_100g: string;
};

type StorageLocationForm = {
  name: string;
};

type ProductGroupForm = {
  name: string;
  default_expiry_days: string;
  default_storage_location: string;
};

type ProductUnitForm = {
  name: string;
};

type RecipeForm = {
  cook_time_minutes: string;
  description: string;
  emoji: string;
  image_path: string;
  instructions: string;
  name: string;
  prep_time_minutes: string;
  servings: string;
  tags: string;
};

type RecipeIngredientForm = {
  food_id: string;
  food_query: string;
  quantity: string;
  unit: string;
  notes: string;
};

type PendingRecipeIngredient = {
  temp_id: string;
  food: Food;
  food_id: number;
  quantity: number;
  unit: string;
  notes?: string | null;
};

type MealForm = {
  kind: "food" | "recipe" | "quick";
  target_id: string;
  quantity: string;
  unit: string;
  meal_type: string;
  time: string;
  notes: string;
  quick_name: string;
  quick_calories: string;
  quick_protein: string;
  quick_fat: string;
  quick_carbs: string;
};

type ShoppingForm = {
  food_id: string;
  name: string;
  quantity: string;
  source: "food" | "text";
  unit: string;
  notes: string;
};

type CalendarForm = {
  entry_type: "event" | "task";
  title: string;
  date: string;
  start_time: string;
  end_time: string;
  all_day: boolean;
  recurrence_frequency: CalendarEvent["recurrence_frequency"];
  recurrence_interval: string;
  recurrence_until: string;
  location: string;
  description: string;
  group_id: string;
};

type CalendarGroupForm = {
  name: string;
  color: string;
  suppresses_group_ids: number[];
  hide_from_dashboard_and_month: boolean;
};

type CalendarView = "day" | "week" | "month";
type CalendarMode = "calendar" | "mealprep";
type MealPrepSlotKey = "breakfast" | "lunch" | "dinner";

const mealPrepSource = "mealprep";
const mealPrepSlots: Array<{
  id: MealPrepSlotKey;
  label: string;
  time: string;
}> = [
  { id: "breakfast", label: "Fruehstueck", time: "08:00" },
  { id: "lunch", label: "Mittag", time: "12:30" },
  { id: "dinner", label: "Abendessen", time: "18:30" },
];

type CalendarOccurrence = {
  key: string;
  date: string;
  event: CalendarEvent;
  startAt: Date;
  endAt: Date | null;
};

type CalendarTimeSelection = {
  dayIndex: number;
  startSlot: number;
  endSlot: number;
};

type UserForm = {
  username: string;
  password: string;
  theme: ThemeName;
  daily_calories: string;
  protein_percent: string;
  fat_percent: string;
  carbs_percent: string;
};

type UserSettingsForm = {
  theme: ThemeName;
  daily_calories: string;
  protein_percent: string;
  fat_percent: string;
  carbs_percent: string;
};

type CsvImportForm = {
  directory: string;
  dryRun: boolean;
};

const navigation = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "calendar", label: "Kalender", icon: CalendarDays },
  { id: "foods", label: "Bestandsübersicht", icon: Apple },
  { id: "recipes", label: "Gerichte", icon: Soup },
  { id: "nutrition", label: "Kalorientracker", icon: Gauge },
  { id: "shopping", label: "Einkaufsliste", icon: ShoppingCart },
] as const;

const settingsNavigationItem = {
  id: "settings",
  label: "Einstellungen",
  icon: Settings,
} as const;

const pageNavigation = [...navigation, settingsNavigationItem] as const;

const themeOptions: Array<{
  id: ThemeName;
  label: string;
  swatches: string[];
}> = [
  {
    id: "light",
    label: "Light",
    swatches: ["#ffffff", "#2563eb", "#15803d"],
  },
  {
    id: "dark",
    label: "Dark",
    swatches: ["#0f172a", "#60a5fa", "#22c55e"],
  },
  {
    id: "purple",
    label: "Purple",
    swatches: ["#f5f3ff", "#7c3aed", "#14b8a6"],
  },
  {
    id: "google",
    label: "Google",
    swatches: ["#ffffff", "#4285f4", "#fbbc05"],
  },
];

const macroMeta: Array<{
  key: keyof MacroValues;
  label: string;
  unit: string;
  tone: string;
}> = [
  { key: "calories", label: "Kalorien", unit: "kcal", tone: "blue" },
  { key: "protein", label: "Protein", unit: "g", tone: "green" },
  { key: "fat", label: "Fett", unit: "g", tone: "amber" },
  { key: "carbs", label: "Kohlenhydrate", unit: "g", tone: "red" },
];

const emptyNutrition: NutritionDay = {
  date: getLocalDate(),
  user_id: 1,
  totals: { calories: 0, protein: 0, fat: 0, carbs: 0 },
  goals: { calories: 2500, protein: 156.25, fat: 83.33, carbs: 281.25 },
  remaining: { calories: 2500, protein: 156.25, fat: 83.33, carbs: 281.25 },
  percentages: { calories: 0, protein: 0, fat: 0, carbs: 0 },
};

const defaultFoodEmoji = "🍽️";
const defaultInventoryEmoji = "📦";
const defaultRecipeEmoji = "🍲";

function isReferencedDeleteError(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }
  const message = error.message.toLowerCase();
  return message.includes("referenced") || message.includes("foreign key");
}

function apiErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "API-Fehler";
}

function isRecipeStockShortageError(error: unknown) {
  return apiErrorMessage(error).toLowerCase().includes("nicht genug bestand");
}

function createInitialInventoryForm(): InventoryForm {
  return {
    food_id: "",
    food_query: "",
    name: "",
    emoji: defaultInventoryEmoji,
    brand: "",
    category: "",
    quantity: "1",
    unit: "pcs",
    minimum_quantity: "0",
    storage_location: "",
    expiry_days: "",
    purchase_date: getLocalDate(),
    price: "",
    barcode: "",
    image_path: "",
    notes: "",
    product_group_id: "",
    product_unit_id: "",
    serving_size: "100",
    serving_unit: "g",
    calories_per_100g: "0",
    protein_per_100g: "0",
    fat_per_100g: "0",
    carbs_per_100g: "0",
  };
}

function createInitialFoodForm(): FoodForm {
  return {
    name: "",
    emoji: defaultFoodEmoji,
    brand: "",
    category: "",
    storage_location: "",
    product_group_id: "",
    product_unit_id: "",
    minimum_quantity: "0",
    barcode: "",
    purchase_date: getLocalDate(),
    expiry_days: "",
    price: "",
    serving_size: "100",
    serving_unit: "g",
    conversions: [],
    calories_per_100g: "0",
    protein_per_100g: "0",
    fat_per_100g: "0",
    carbs_per_100g: "0",
  };
}

const initialStorageLocationForm: StorageLocationForm = {
  name: "",
};

const initialProductGroupForm: ProductGroupForm = {
  name: "",
  default_expiry_days: "",
  default_storage_location: "",
};

const initialProductUnitForm: ProductUnitForm = {
  name: "",
};

const initialRecipeForm: RecipeForm = {
  cook_time_minutes: "",
  description: "",
  emoji: defaultRecipeEmoji,
  image_path: "",
  instructions: "",
  name: "",
  prep_time_minutes: "",
  servings: "1",
  tags: "",
};

const initialRecipeIngredientForm: RecipeIngredientForm = {
  food_id: "",
  food_query: "",
  quantity: "1",
  unit: "g",
  notes: "",
};

const draftRecipeIngredientKey = -1;

const initialMealForm: MealForm = {
  kind: "food",
  target_id: "",
  quantity: "100",
  unit: "g",
  meal_type: "lunch",
  time: "12:00",
  notes: "",
  quick_name: "",
  quick_calories: "",
  quick_protein: "",
  quick_fat: "",
  quick_carbs: "",
};

const initialShoppingForm: ShoppingForm = {
  food_id: "",
  name: "",
  quantity: "",
  source: "food",
  unit: "pcs",
  notes: "",
};

function createCalendarForm(date = getLocalDate()): CalendarForm {
  return {
    entry_type: "event",
    title: "",
    date,
    start_time: "09:00",
    end_time: "10:00",
    all_day: false,
    recurrence_frequency: "none",
    recurrence_interval: "1",
    recurrence_until: "",
    location: "",
    description: "",
    group_id: "",
  };
}

const initialCalendarGroupForm: CalendarGroupForm = {
  name: "",
  color: "#2563eb",
  suppresses_group_ids: [],
  hide_from_dashboard_and_month: false,
};

const initialUserForm: UserForm = {
  username: "",
  password: "",
  theme: "light",
  daily_calories: "2500",
  protein_percent: "25",
  fat_percent: "30",
  carbs_percent: "45",
};

const initialUserSettingsForm: UserSettingsForm = {
  theme: "light",
  daily_calories: "2500",
  protein_percent: "25",
  fat_percent: "30",
  carbs_percent: "45",
};

const initialCsvImportForm: CsvImportForm = {
  directory: "u:\\Nico\\Desktop\\db",
  dryRun: false,
};

function getLocalDate(date = new Date()) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function parseDecimalNumber(value: string) {
  return Number(value.replace(/,/g, "."));
}

function parseNumberInput(value: string) {
  const trimmed = value.trim();
  if (trimmed === "") {
    return Number.NaN;
  }

  const mixedFractionMatch = trimmed.match(
    /^([+-]?\d+(?:[,.]\d+)?)\s+(\d+(?:[,.]\d+)?)\s*\/\s*(\d+(?:[,.]\d+)?)$/,
  );
  if (mixedFractionMatch) {
    const whole = parseDecimalNumber(mixedFractionMatch[1]);
    const numerator = parseDecimalNumber(mixedFractionMatch[2]);
    const denominator = parseDecimalNumber(mixedFractionMatch[3]);
    if (
      !Number.isFinite(whole) ||
      !Number.isFinite(numerator) ||
      !Number.isFinite(denominator) ||
      denominator === 0
    ) {
      return Number.NaN;
    }
    const fraction = numerator / denominator;
    return whole < 0 ? whole - fraction : whole + fraction;
  }

  const fractionMatch = trimmed.match(
    /^([+-]?\d+(?:[,.]\d+)?)\s*\/\s*([+-]?\d+(?:[,.]\d+)?)$/,
  );
  if (fractionMatch) {
    const numerator = parseDecimalNumber(fractionMatch[1]);
    const denominator = parseDecimalNumber(fractionMatch[2]);
    if (
      !Number.isFinite(numerator) ||
      !Number.isFinite(denominator) ||
      denominator === 0
    ) {
      return Number.NaN;
    }
    return numerator / denominator;
  }

  return parseDecimalNumber(trimmed);
}

const fractionalQuantityDenominators = [2, 3, 4, 6, 8, 12];
const fractionalQuantityTolerance = 0.01;
const quantityPrecision = 1_000_000;

function roundQuantity(value: number) {
  return Math.round(value * quantityPrecision) / quantityPrecision;
}

function normalizeFractionalQuantityValue(value: number) {
  if (!Number.isFinite(value)) {
    return value;
  }

  const sign = value < 0 ? -1 : 1;
  const absoluteValue = Math.abs(value);
  let whole = Math.trunc(absoluteValue);
  const fraction = absoluteValue - whole;

  if (fraction < fractionalQuantityTolerance) {
    return sign * whole;
  }

  let bestFraction: {
    denominator: number;
    difference: number;
    numerator: number;
  } | null = null;

  for (const denominator of fractionalQuantityDenominators) {
    const numerator = Math.round(fraction * denominator);
    const difference = Math.abs(fraction - numerator / denominator);
    if (!bestFraction || difference < bestFraction.difference) {
      bestFraction = { denominator, difference, numerator };
    }
  }

  if (bestFraction && bestFraction.difference < fractionalQuantityTolerance) {
    if (bestFraction.numerator === bestFraction.denominator) {
      whole += 1;
      return sign * whole;
    }
    return sign * roundQuantity(whole + bestFraction.numerator / bestFraction.denominator);
  }

  return roundQuantity(value);
}

function parseQuantityInput(value: string) {
  const parsed = parseNumberInput(value);
  return Number.isFinite(parsed)
    ? normalizeFractionalQuantityValue(parsed)
    : Number.NaN;
}

function toNumber(value: string, fallback = 0) {
  const parsed = parseNumberInput(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toQuantityNumber(value: string, fallback = 0) {
  const parsed = parseQuantityInput(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalNumber(value: string) {
  return value.trim() === "" ? null : toNumber(value);
}

function optionalQuantityNumber(value: string) {
  return value.trim() === "" ? null : toQuantityNumber(value);
}

function optionalInteger(value: string) {
  const parsed = optionalNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
}

function optionalText(value: string) {
  return value.trim() === "" ? null : value.trim();
}

function toFormValue(value?: string | number | null) {
  return value === null || value === undefined ? "" : String(value);
}

function userPreferencesFromUser(user?: User | null): UserSettingsForm {
  if (!user) {
    return initialUserSettingsForm;
  }
  return {
    theme: user.theme,
    daily_calories: toFormValue(user.daily_calories),
    protein_percent: toFormValue(user.protein_percent),
    fat_percent: toFormValue(user.fat_percent),
    carbs_percent: toFormValue(user.carbs_percent),
  };
}

function userFormFromUser(user: User): UserForm {
  return {
    username: user.username,
    password: user.password,
    ...userPreferencesFromUser(user),
  };
}

function userPayloadFromForm(form: UserForm): UserCreate {
  return {
    username: form.username,
    password: form.password,
    ...userSettingsPayloadFromForm(form),
  };
}

function userSettingsPayloadFromForm(form: UserSettingsForm): Required<Pick<
  UserCreate,
  | "theme"
  | "daily_calories"
  | "protein_percent"
  | "fat_percent"
  | "carbs_percent"
>> {
  return {
    theme: form.theme,
    daily_calories: toNumber(form.daily_calories, 2500),
    protein_percent: toNumber(form.protein_percent, 25),
    fat_percent: toNumber(form.fat_percent, 30),
    carbs_percent: toNumber(form.carbs_percent, 45),
  };
}

function macroPercentTotal(form: UserSettingsForm) {
  return (
    toNumber(form.protein_percent) +
    toNumber(form.fat_percent) +
    toNumber(form.carbs_percent)
  );
}

function macroGoalsFromPercentages(form: UserSettingsForm) {
  const calories = Math.max(toNumber(form.daily_calories, 0), 0);
  return {
    calories,
    protein: (calories * toNumber(form.protein_percent, 0)) / 100 / 4,
    fat: (calories * toNumber(form.fat_percent, 0)) / 100 / 9,
    carbs: (calories * toNumber(form.carbs_percent, 0)) / 100 / 4,
  };
}

function createDraftId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function formatNumber(value: number, maximumFractionDigits = 1) {
  return new Intl.NumberFormat("de-DE", {
    maximumFractionDigits,
  }).format(value);
}

function greatestCommonDivisor(left: number, right: number): number {
  return right === 0 ? left : greatestCommonDivisor(right, left % right);
}

function formatFractionalQuantity(value: number) {
  if (!Number.isFinite(value)) {
    return "";
  }

  const normalizedValue = normalizeFractionalQuantityValue(value);
  const sign = normalizedValue < 0 ? "-" : "";
  const absoluteValue = Math.abs(normalizedValue);
  let whole = Math.trunc(absoluteValue);
  const fraction = absoluteValue - whole;
  if (fraction < 0.0005) {
    return `${sign}${whole}`;
  }

  let bestFraction: {
    denominator: number;
    difference: number;
    numerator: number;
  } | null = null;
  for (const denominator of fractionalQuantityDenominators) {
    const numerator = Math.round(fraction * denominator);
    if (numerator === 0) {
      continue;
    }
    const difference = Math.abs(fraction - numerator / denominator);
    if (!bestFraction || difference < bestFraction.difference) {
      bestFraction = { denominator, difference, numerator };
    }
  }

  if (bestFraction && bestFraction.difference < 0.0005) {
    if (bestFraction.numerator === bestFraction.denominator) {
      whole += 1;
      return `${sign}${whole}`;
    }

    const divisor = greatestCommonDivisor(
      bestFraction.numerator,
      bestFraction.denominator,
    );
    const numerator = bestFraction.numerator / divisor;
    const denominator = bestFraction.denominator / divisor;
    return whole === 0
      ? `${sign}${numerator}/${denominator}`
      : `${sign}${whole} ${numerator}/${denominator}`;
  }

  return formatNumber(normalizedValue, 3);
}

function formatRecipeShoppingAction(
  action: RecipeShoppingListSyncResult["missing"][number]["action"],
) {
  if (action === "created") {
    return "Neu auf Liste";
  }
  if (action === "updated") {
    return "Menge erhoeht";
  }
  return "Bereits abgedeckt";
}

function parseInventoryQuantity(value: string, label: string) {
  if (value.trim() === "") {
    return 0;
  }

  const parsed = parseQuantityInput(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${label} muss eine Zahl oder ein Bruch sein.`);
  }
  if (parsed < 0) {
    throw new Error(`${label} darf nicht negativ sein.`);
  }
  return parsed;
}

function clampPercent(value: number) {
  return Math.min(Math.max(value, 0), 100);
}

function formatCurrency(value?: number | null) {
  if (value === undefined || value === null) {
    return "-";
  }
  return new Intl.NumberFormat("de-DE", {
    currency: "EUR",
    style: "currency",
  }).format(value);
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatDate(value?: string | null) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
  }).format(new Date(`${value}T00:00:00`));
}

function formatMonth(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function formatCalendarTime(value: Date) {
  return new Intl.DateTimeFormat("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function formatTimeInput(value: Date) {
  return `${String(value.getHours()).padStart(2, "0")}:${String(
    value.getMinutes(),
  ).padStart(2, "0")}`;
}

function timeSlotLabel(slot: number) {
  const hours = Math.floor(slot / 2);
  const minutes = slot % 2 === 0 ? "00" : "30";
  return `${String(hours).padStart(2, "0")}:${minutes}`;
}

function timeSlotEndLabel(slot: number) {
  return slot >= 48 ? "23:59" : timeSlotLabel(slot);
}

function occurrenceStartSlot(occurrence: CalendarOccurrence) {
  return Math.max(
    0,
    Math.floor((occurrence.startAt.getHours() * 60 + occurrence.startAt.getMinutes()) / 30),
  );
}

function occurrenceEndSlot(occurrence: CalendarOccurrence) {
  if (occurrence.event.all_day) {
    return 48;
  }

  const end = occurrence.endAt ?? new Date(occurrence.startAt.getTime() + 60 * 60 * 1000);
  const slot = Math.ceil((end.getHours() * 60 + end.getMinutes()) / 30);
  return Math.min(Math.max(slot, occurrenceStartSlot(occurrence) + 1), 48);
}

function timeValueToSlot(value: string, fallback: number) {
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return fallback;
  }
  return Math.min(Math.max(Math.floor((hours * 60 + minutes) / 30), 0), 48);
}

function dateFromLocalValue(value: string) {
  return new Date(`${value}T00:00:00`);
}

function dateAtEndOfDay(value: string) {
  return new Date(`${value}T23:59:59`);
}

function addDays(date: Date, amount: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
}

function monthGridDates(selectedDate: string) {
  const firstOfMonth = dateFromLocalValue(selectedDate);
  firstOfMonth.setDate(1);
  const mondayOffset = (firstOfMonth.getDay() + 6) % 7;
  const firstCell = addDays(firstOfMonth, -mondayOffset);
  return Array.from({ length: 42 }, (_, index) => addDays(firstCell, index));
}

function weekGridDates(selectedDate: string) {
  const current = dateFromLocalValue(selectedDate);
  const mondayOffset = (current.getDay() + 6) % 7;
  const monday = addDays(current, -mondayOffset);
  return Array.from({ length: 7 }, (_, index) => addDays(monday, index));
}

function getVisibleCalendarDates(view: CalendarView, selectedDate: string) {
  if (view === "day") {
    return [dateFromLocalValue(selectedDate)];
  }
  if (view === "week") {
    return weekGridDates(selectedDate);
  }
  return monthGridDates(selectedDate);
}

function moveCalendarMonth(value: string, amount: number) {
  const next = dateFromLocalValue(value);
  next.setDate(1);
  next.setMonth(next.getMonth() + amount);
  return getLocalDate(next);
}

function moveCalendarView(value: string, view: CalendarView, amount: number) {
  if (view === "month") {
    return moveCalendarMonth(value, amount);
  }

  const next = dateFromLocalValue(value);
  next.setDate(next.getDate() + amount * (view === "week" ? 7 : 1));
  return getLocalDate(next);
}

function formatCalendarViewTitle(view: CalendarView, selectedDate: string) {
  if (view === "month") {
    return formatMonth(selectedDate);
  }
  if (view === "day") {
    return formatDate(selectedDate);
  }

  const week = weekGridDates(selectedDate);
  return `${formatDate(getLocalDate(week[0]))} - ${formatDate(
    getLocalDate(week[week.length - 1]),
  )}`;
}

function addRecurrenceStep(
  value: Date,
  frequency: CalendarEvent["recurrence_frequency"],
  interval: number,
) {
  const next = new Date(value);
  if (frequency === "daily") {
    next.setDate(next.getDate() + interval);
  }
  if (frequency === "weekly") {
    next.setDate(next.getDate() + interval * 7);
  }
  if (frequency === "monthly") {
    next.setMonth(next.getMonth() + interval);
  }
  if (frequency === "yearly") {
    next.setFullYear(next.getFullYear() + interval);
  }
  return next;
}

function sortCalendarOccurrences(occurrences: CalendarOccurrence[]) {
  return [...occurrences].sort(
    (first, second) => first.startAt.getTime() - second.startAt.getTime(),
  );
}

function getCalendarOccurrences(
  events: CalendarEvent[],
  rangeStart: Date,
  rangeEnd: Date,
) {
  const occurrences: CalendarOccurrence[] = [];

  for (const event of events) {
    const baseStart = new Date(event.start_at);
    const baseEnd = event.end_at ? new Date(event.end_at) : null;
    const duration = baseEnd ? baseEnd.getTime() - baseStart.getTime() : null;
    const frequency = event.recurrence_frequency ?? "none";
    const interval = Math.max(event.recurrence_interval || 1, 1);
    const recurrenceUntil = event.recurrence_until
      ? new Date(event.recurrence_until)
      : null;
    const excludedStarts = new Set(
      (event.exclusions ?? []).map((exclusion) =>
        new Date(exclusion.occurrence_start_at).getTime(),
      ),
    );
    let occurrenceStart = new Date(baseStart);
    let count = 0;

    while (count < 4000 && occurrenceStart <= rangeEnd) {
      if (recurrenceUntil && occurrenceStart > recurrenceUntil) {
        break;
      }

      if (
        occurrenceStart >= rangeStart &&
        !excludedStarts.has(occurrenceStart.getTime())
      ) {
        occurrences.push({
          key: `${event.id}-${occurrenceStart.toISOString()}`,
          date: getLocalDate(occurrenceStart),
          event,
          startAt: new Date(occurrenceStart),
          endAt: duration === null ? null : new Date(occurrenceStart.getTime() + duration),
        });
      }

      if (frequency === "none") {
        break;
      }

      occurrenceStart = addRecurrenceStep(occurrenceStart, frequency, interval);
      count += 1;
    }
  }

  return sortCalendarOccurrences(occurrences);
}

function formatOccurrenceTime(occurrence: CalendarOccurrence) {
  if (occurrence.event.all_day) {
    return "Ganztagig";
  }
  if (occurrence.endAt) {
    return `${formatCalendarTime(occurrence.startAt)} - ${formatCalendarTime(occurrence.endAt)}`;
  }
  return formatCalendarTime(occurrence.startAt);
}

function createCalendarFormFromEvent(event: CalendarEvent): CalendarForm {
  const startAt = new Date(event.start_at);
  const endAt = event.end_at ? new Date(event.end_at) : null;
  return {
    entry_type: event.entry_type,
    title: event.title,
    date: getLocalDate(startAt),
    start_time: formatTimeInput(startAt),
    end_time: endAt ? formatTimeInput(endAt) : "",
    all_day: event.all_day,
    recurrence_frequency: event.recurrence_frequency,
    recurrence_interval: String(event.recurrence_interval || 1),
    recurrence_until: event.recurrence_until
      ? getLocalDate(new Date(event.recurrence_until))
      : "",
    location: event.location ?? "",
    description: event.description ?? "",
    group_id: event.group_id ? String(event.group_id) : "",
  };
}

function daysUntil(dateValue?: string | null) {
  if (!dateValue) {
    return Number.POSITIVE_INFINITY;
  }
  const today = new Date(`${getLocalDate()}T00:00:00`);
  const target = new Date(`${dateValue}T00:00:00`);
  return Math.ceil((target.getTime() - today.getTime()) / 86_400_000);
}

function getInventoryStatus(item: InventoryItem): {
  status: InventoryStatus;
  label: string;
} {
  const expiryDistance = daysUntil(item.expiry_date);
  if (expiryDistance < 0) {
    return { status: "expired", label: "Abgelaufen" };
  }
  if (expiryDistance <= 7) {
    return { status: "expiring", label: "Laeuft bald ab" };
  }
  if (item.quantity <= item.minimum_quantity) {
    return { status: "low", label: "Niedrig" };
  }
  return { status: "ok", label: "OK" };
}

function formatDueDateWithDistance(value?: string | null) {
  if (!value) {
    return "-";
  }

  const distance = daysUntil(value);
  if (!Number.isFinite(distance)) {
    return value;
  }

  let distanceLabel = "";
  if (distance < 0) {
    distanceLabel = `seit ${formatNumber(Math.abs(distance), 0)} Tagen`;
  } else if (distance === 0) {
    distanceLabel = "heute";
  } else if (distance === 1) {
    distanceLabel = "morgen";
  } else if (distance < 31) {
    distanceLabel = `in ${formatNumber(distance, 0)} Tagen`;
  } else if (distance < 62) {
    distanceLabel = "in einem Monat";
  } else {
    distanceLabel = `in ${formatNumber(Math.round(distance / 30), 0)} Monaten`;
  }

  return (
    <>
      {value} <span className="due-distance">{distanceLabel}</span>
    </>
  );
}

const inventoryColumnStorageKey = "heim-erp-inventory-visible-columns";

function formatServingConversion(
  productUnit: string,
  item: Pick<InventoryItem | Food, "serving_size" | "serving_unit"> & {
    conversions?: Array<Pick<Food["conversions"][number], "quantity" | "unit">>;
  },
) {
  const mainConversion = `${formatFractionalQuantity(item.serving_size)} ${
    item.serving_unit
  }`;
  const extraConversions = (item.conversions ?? [])
    .filter((conversion) => conversion.quantity > 0 && conversion.unit.trim())
    .map(
      (conversion) =>
        `${formatFractionalQuantity(conversion.quantity)} ${conversion.unit}`,
    );
  return [`1 ${productUnit}`, mainConversion, ...extraConversions].join(" = ");
}

function defaultConversionForProductUnit(
  productUnit: string,
  currentSize: string,
  currentUnit: string,
) {
  const directGrams = unitQuantityToGrams(1, productUnit);
  if (directGrams !== null) {
    return {
      serving_size: formatFractionalQuantity(directGrams),
      serving_unit: "g",
    };
  }

  return {
    serving_size: currentSize || "100",
    serving_unit: currentUnit || "g",
  };
}

const inventoryColumnDefinitions: InventoryColumnDefinition[] = [
  {
    key: "product_group",
    label: "Produktgruppe",
    render: (item) => item.product_group?.name ?? item.category ?? "-",
  },
  {
    key: "quantity",
    label: "Menge",
    render: (item) => `${formatFractionalQuantity(item.quantity)} ${item.unit}`,
  },
  {
    key: "conversion",
    label: "Umrechnung",
    render: (item) =>
      formatServingConversion(item.unit, {
        ...item,
        conversions: item.food?.conversions ?? [],
      }),
  },
  {
    key: "minimum_quantity",
    label: "Minimum",
    render: (item) =>
      `${formatFractionalQuantity(item.minimum_quantity)} ${item.unit}`,
  },
  {
    key: "purchase_date",
    label: "Einlagerung",
    render: (item) => formatDate(item.purchase_date),
  },
  {
    key: "expiry_days",
    label: "Haltbarkeit",
    render: (item) =>
      item.expiry_days === null || item.expiry_days === undefined
        ? "-"
        : `${formatNumber(item.expiry_days, 0)} Tage`,
  },
  {
    key: "expiry_date",
    label: "Naechstes Faelligkeitsdatum",
    render: (item) => formatDueDateWithDistance(item.expiry_date),
  },
  {
    key: "price",
    label: "Preis",
    render: (item) => formatCurrency(item.price),
  },
  {
    key: "brand",
    label: "Marke",
    render: (item) => item.brand ?? "-",
  },
  {
    key: "calories",
    label: "kcal / 100g",
    render: (item) => `${formatNumber(item.calories_per_100g)} kcal`,
  },
  {
    key: "protein",
    label: "Protein",
    render: (item) => `${formatNumber(item.protein_per_100g)} g`,
  },
  {
    key: "fat",
    label: "Fett",
    render: (item) => `${formatNumber(item.fat_per_100g)} g`,
  },
  {
    key: "carbs",
    label: "KH",
    render: (item) => `${formatNumber(item.carbs_per_100g)} g`,
  },
  {
    key: "status",
    label: "Status",
    render: (item) => {
      const status = getInventoryStatus(item);
      return <StatusBadge status={status.status} label={status.label} />;
    },
  },
];

const defaultInventoryColumnKeys = inventoryColumnDefinitions.map(
  (column) => column.key,
);

function getInitialInventoryVisibleColumns(): InventoryColumnKey[] {
  try {
    const storedValue = localStorage.getItem(inventoryColumnStorageKey);
    if (!storedValue) {
      return defaultInventoryColumnKeys;
    }

    const parsedValue = JSON.parse(storedValue);
    if (!Array.isArray(parsedValue)) {
      return defaultInventoryColumnKeys;
    }

    const allowedColumns = new Set<InventoryColumnKey>(
      defaultInventoryColumnKeys,
    );
    const visibleColumns = parsedValue.filter(
      (key): key is InventoryColumnKey => allowedColumns.has(key),
    );
    return parsedValue.length === 0 || visibleColumns.length > 0
      ? visibleColumns
      : defaultInventoryColumnKeys;
  } catch {
    return defaultInventoryColumnKeys;
  }
}

function createInventoryFormFromItem(item: InventoryItem): InventoryForm {
  return {
    food_id: toFormValue(item.food_id ?? item.food?.id),
    food_query: item.food ? formatFoodSuggestionLabel(item.food) : item.name,
    name: item.name,
    emoji: item.emoji || defaultInventoryEmoji,
    brand: item.brand ?? "",
    category: item.category ?? item.product_group?.name ?? "",
    quantity: formatFractionalQuantity(item.quantity),
    unit: item.product_unit?.name ?? item.unit,
    minimum_quantity: formatFractionalQuantity(item.minimum_quantity),
    storage_location: item.storage_location ?? "",
    expiry_days: toFormValue(item.expiry_days),
    purchase_date: item.purchase_date ?? getLocalDate(),
    price: toFormValue(item.price),
    barcode: item.barcode ?? "",
    image_path: item.image_path ?? "",
    notes: item.notes ?? "",
    product_group_id: toFormValue(item.product_group_id ?? item.product_group?.id),
    product_unit_id: toFormValue(item.product_unit_id ?? item.product_unit?.id),
    serving_size: toFormValue(item.serving_size),
    serving_unit: item.serving_unit,
    calories_per_100g: toFormValue(item.calories_per_100g),
    protein_per_100g: toFormValue(item.protein_per_100g),
    fat_per_100g: toFormValue(item.fat_per_100g),
    carbs_per_100g: toFormValue(item.carbs_per_100g),
  };
}

function createInventoryFormFromFood(
  food: Food,
  productGroups: ProductGroup[],
  productUnits: ProductUnit[],
): InventoryForm {
  const productGroup = food.product_group_id
    ? productGroups.find((group) => group.id === food.product_group_id) ?? null
    : null;
  const productUnit = food.product_unit_id
    ? productUnits.find((unit) => unit.id === food.product_unit_id) ?? null
    : null;
  const storageLocation =
    food.storage_location?.trim() ||
    productGroup?.default_storage_location?.trim() ||
    "";

  return {
    food_id: toFormValue(food.id),
    food_query: formatFoodSuggestionLabel(food),
    name: food.name,
    emoji: food.emoji || defaultInventoryEmoji,
    brand: food.brand ?? "",
    category: food.category ?? productGroup?.name ?? "",
    quantity: "1",
    unit: productUnit?.name ?? food.serving_unit ?? "pcs",
    minimum_quantity: formatFractionalQuantity(food.minimum_quantity ?? 0),
    storage_location: storageLocation,
    expiry_days: toFormValue(food.expiry_days ?? productGroup?.default_expiry_days),
    purchase_date: food.purchase_date ?? getLocalDate(),
    price: toFormValue(food.price),
    barcode: food.barcode ?? "",
    image_path: "",
    notes: "",
    product_group_id: toFormValue(food.product_group_id),
    product_unit_id: toFormValue(food.product_unit_id),
    serving_size: toFormValue(food.serving_size),
    serving_unit: food.serving_unit,
    calories_per_100g: toFormValue(food.calories_per_100g),
    protein_per_100g: toFormValue(food.protein_per_100g),
    fat_per_100g: toFormValue(food.fat_per_100g),
    carbs_per_100g: toFormValue(food.carbs_per_100g),
  };
}

function createInventoryPayload(
  form: InventoryForm,
  productGroups: ProductGroup[],
) {
  const selectedProductGroup = productGroups.find(
    (group) => String(group.id) === form.product_group_id,
  );
  return {
    food_id: optionalNumber(form.food_id),
    name: form.name,
    emoji: form.emoji.trim() || defaultInventoryEmoji,
    brand: optionalText(form.brand),
    category: optionalText(form.category) ?? selectedProductGroup?.name ?? null,
    quantity: parseInventoryQuantity(form.quantity, "Menge"),
    unit: form.unit,
    minimum_quantity: parseInventoryQuantity(
      form.minimum_quantity,
      "Mindestbestand",
    ),
    storage_location: optionalText(form.storage_location),
    expiry_days: optionalInteger(form.expiry_days),
    purchase_date: form.purchase_date,
    price: optionalNumber(form.price),
    barcode: optionalText(form.barcode),
    image_path: optionalText(form.image_path),
    notes: optionalText(form.notes),
    product_group_id: optionalNumber(form.product_group_id),
    product_unit_id: optionalNumber(form.product_unit_id),
    serving_size: toNumber(form.serving_size, 100),
    serving_unit: form.serving_unit,
    calories_per_100g: toNumber(form.calories_per_100g),
    protein_per_100g: toNumber(form.protein_per_100g),
    fat_per_100g: toNumber(form.fat_per_100g),
    carbs_per_100g: toNumber(form.carbs_per_100g),
  };
}

function createFoodFormFromFood(food: Food): FoodForm {
  return {
    name: food.name,
    emoji: food.emoji || defaultFoodEmoji,
    brand: food.brand ?? "",
    category: food.category ?? "",
    storage_location: food.storage_location ?? "",
    product_group_id: toFormValue(food.product_group_id),
    product_unit_id: toFormValue(food.product_unit_id),
    minimum_quantity: formatFractionalQuantity(food.minimum_quantity ?? 0),
    barcode: food.barcode ?? "",
    purchase_date: food.purchase_date ?? getLocalDate(),
    expiry_days: toFormValue(food.expiry_days),
    price: toFormValue(food.price),
    serving_size: toFormValue(food.serving_size),
    serving_unit: food.serving_unit,
    conversions: (food.conversions ?? []).map((conversion) => ({
      quantity: toFormValue(conversion.quantity),
      unit: conversion.unit,
    })),
    calories_per_100g: toFormValue(food.calories_per_100g),
    protein_per_100g: toFormValue(food.protein_per_100g),
    fat_per_100g: toFormValue(food.fat_per_100g),
    carbs_per_100g: toFormValue(food.carbs_per_100g),
  };
}

function createFoodPayload(form: FoodForm) {
  return {
    name: form.name,
    emoji: form.emoji.trim() || defaultFoodEmoji,
    brand: optionalText(form.brand),
    category: optionalText(form.category),
    storage_location: optionalText(form.storage_location),
    product_group_id: optionalNumber(form.product_group_id),
    product_unit_id: optionalNumber(form.product_unit_id),
    minimum_quantity: toQuantityNumber(form.minimum_quantity, 0),
    barcode: optionalText(form.barcode),
    purchase_date: form.purchase_date,
    expiry_days: optionalInteger(form.expiry_days),
    price: optionalNumber(form.price),
    serving_size: toNumber(form.serving_size, 100),
    serving_unit: form.serving_unit,
    conversions: form.conversions
      .map((conversion) => ({
        quantity: toQuantityNumber(conversion.quantity, 0),
        unit: conversion.unit.trim(),
      }))
      .filter((conversion) => conversion.quantity > 0 && conversion.unit !== ""),
    calories_per_100g: toNumber(form.calories_per_100g),
    protein_per_100g: toNumber(form.protein_per_100g),
    fat_per_100g: toNumber(form.fat_per_100g),
    carbs_per_100g: toNumber(form.carbs_per_100g),
  };
}

function createRecipeFormFromRecipe(recipe: Recipe): RecipeForm {
  return {
    cook_time_minutes: toFormValue(recipe.cook_time_minutes),
    description: recipe.description ?? "",
    emoji: recipe.emoji || defaultRecipeEmoji,
    image_path: recipe.image_path ?? "",
    instructions: recipe.instructions ?? "",
    name: recipe.name,
    prep_time_minutes: toFormValue(recipe.prep_time_minutes),
    servings: formatFractionalQuantity(recipe.servings),
    tags: formatRecipeTags(recipe.tags),
  };
}

function createRecipePayload(form: RecipeForm) {
  return {
    cook_time_minutes: optionalInteger(form.cook_time_minutes),
    description: optionalText(form.description),
    emoji: form.emoji.trim() || defaultRecipeEmoji,
    image_path: optionalText(form.image_path),
    instructions: optionalText(form.instructions),
    name: form.name,
    prep_time_minutes: optionalInteger(form.prep_time_minutes),
    servings: toQuantityNumber(form.servings, 1),
    tags: parseRecipeTags(form.tags),
  };
}

function parseRecipeTags(value: string) {
  const seen = new Set<string>();
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (!key || seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

function formatRecipeTags(tags?: string[] | null) {
  return (tags ?? []).join(", ");
}

function getMealLogDate(mealLog: MealLog) {
  return getLocalDate(new Date(mealLog.eaten_at));
}

function getMealLogTime(mealLog: MealLog) {
  return formatTimeInput(new Date(mealLog.eaten_at));
}

function getMealLogTitle(mealLog: MealLog) {
  return mealLog.food?.name ?? mealLog.recipe?.name ?? mealLog.quick_add_name ?? "Mahlzeit";
}

function getMealLogTargetId(mealLog: MealLog) {
  return mealLog.food_id ?? mealLog.recipe_id ?? null;
}

function mealPrepSelectionValueFromLog(mealLog?: MealLog | null) {
  if (!mealLog) {
    return "";
  }
  if (mealLog.food_id !== null && mealLog.food_id !== undefined) {
    return `food:${mealLog.food_id}`;
  }
  if (mealLog.recipe_id !== null && mealLog.recipe_id !== undefined) {
    return `recipe:${mealLog.recipe_id}`;
  }
  return "";
}

function parseMealPrepSelectionValue(value: string) {
  const [kind, rawId] = value.split(":");
  const id = Number(rawId);
  if ((kind !== "food" && kind !== "recipe") || !Number.isFinite(id) || id <= 0) {
    return null;
  }
  return { id, kind };
}

function isMealPrepSlotLog(
  mealLog: MealLog,
  date: string,
  slot: (typeof mealPrepSlots)[number],
  userId: number,
) {
  const mealType = normalizedUnitName(mealLog.meal_type);
  return (
    mealLog.meal_source === mealPrepSource &&
    getMealLogDate(mealLog) === date &&
    (mealLog.user_id === null ||
      mealLog.user_id === undefined ||
      mealLog.user_id === userId) &&
    (mealType === normalizedUnitName(slot.label) || mealType === slot.id)
  );
}

function createMealFormFromLog(mealLog: MealLog): MealForm {
  const isQuickAdd = Boolean(mealLog.quick_add_name);
  return {
    kind: isQuickAdd
      ? "quick"
      : mealLog.food_id !== null && mealLog.food_id !== undefined
        ? "food"
        : "recipe",
    target_id: toFormValue(getMealLogTargetId(mealLog)),
    quantity: formatFractionalQuantity(mealLog.quantity),
    unit: mealLog.unit,
    meal_type: mealLog.meal_type ?? "",
    time: getMealLogTime(mealLog),
    notes: mealLog.notes ?? "",
    quick_name: mealLog.quick_add_name ?? "",
    quick_calories: toFormValue(mealLog.quick_calories),
    quick_protein: toFormValue(mealLog.quick_protein),
    quick_fat: toFormValue(mealLog.quick_fat),
    quick_carbs: toFormValue(mealLog.quick_carbs),
  };
}

function splitRecipeSteps(instructions?: string | null) {
  return (instructions ?? "")
    .split(/\r?\n/)
    .map((step) => step.trim())
    .filter(Boolean);
}

function joinRecipeSteps(steps: string[]) {
  return steps.join("\n");
}

function getStoredUserId() {
  const stored = localStorage.getItem("heim-erp-user-id");
  const parsed = stored ? Number(stored) : 1;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export default function App() {
  const [activePage, setActivePage] = useState<Page>("dashboard");
  const [masterDataOpen, setMasterDataOpen] = useState(true);
  const [activeMasterDataTab, setActiveMasterDataTab] =
    useState<MasterDataTab>("foods");
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [foods, setFoods] = useState<Food[]>([]);
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [productUnits, setProductUnits] = useState<ProductUnit[]>([]);
  const [storageLocations, setStorageLocations] = useState<StorageLocation[]>(
    [],
  );
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [mealLogs, setMealLogs] = useState<MealLog[]>([]);
  const [shoppingList, setShoppingList] = useState<ShoppingListItem[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [calendarGroups, setCalendarGroups] = useState<CalendarGroup[]>([]);
  const [warnings, setWarnings] = useState<InventoryWarnings>({
    low_stock: [],
    expiring_soon: [],
    expired: [],
  });
  const [nutrition, setNutrition] = useState<NutritionDay>(emptyNutrition);
  const [selectedDate, setSelectedDate] = useState(getLocalDate());
  const [calendarDate, setCalendarDate] = useState(getLocalDate());
  const [calendarView, setCalendarView] = useState<CalendarView>("month");
  const [hiddenCalendarGroupIds, setHiddenCalendarGroupIds] = useState<number[]>([]);
  const [userId, setUserId] = useState(getStoredUserId);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  const [inventorySearch, setInventorySearch] = useState("");
  const [inventoryCategory, setInventoryCategory] = useState("all");
  const [inventoryStatus, setInventoryStatus] = useState("all");
  const [inventoryForm, setInventoryForm] =
    useState<InventoryForm>(createInitialInventoryForm);
  const [editingInventoryItemId, setEditingInventoryItemId] = useState<
    number | null
  >(null);
  const [inventoryCreateOpen, setInventoryCreateOpen] = useState(false);
  const [productGroupForm, setProductGroupForm] = useState<ProductGroupForm>(
    initialProductGroupForm,
  );
  const [productUnitForm, setProductUnitForm] = useState<ProductUnitForm>(
    initialProductUnitForm,
  );
  const [foodForm, setFoodForm] = useState<FoodForm>(createInitialFoodForm);
  const [storageLocationForm, setStorageLocationForm] =
    useState<StorageLocationForm>(initialStorageLocationForm);
  const [masterProductGroupForm, setMasterProductGroupForm] =
    useState<ProductGroupForm>(initialProductGroupForm);
  const [masterProductUnitForm, setMasterProductUnitForm] =
    useState<ProductUnitForm>(initialProductUnitForm);
  const [editingFoodId, setEditingFoodId] = useState<number | null>(null);
  const [editingStorageLocationId, setEditingStorageLocationId] = useState<
    number | null
  >(null);
  const [editingProductGroupId, setEditingProductGroupId] = useState<
    number | null
  >(null);
  const [editingProductUnitId, setEditingProductUnitId] = useState<
    number | null
  >(null);
  const [recipeForm, setRecipeForm] = useState<RecipeForm>(initialRecipeForm);
  const [editingRecipeId, setEditingRecipeId] = useState<number | null>(null);
  const [recipeEditorOpen, setRecipeEditorOpen] = useState(false);
  const [recipeStepDraft, setRecipeStepDraft] = useState("");
  const [recipeIngredientForms, setRecipeIngredientForms] = useState<
    Record<number, RecipeIngredientForm>
  >({});
  const [pendingRecipeIngredients, setPendingRecipeIngredients] = useState<
    PendingRecipeIngredient[]
  >([]);
  const [recipeNutrition, setRecipeNutrition] = useState<
    Record<number, RecipeNutrition>
  >({});
  const [mealForm, setMealForm] = useState<MealForm>(initialMealForm);
  const [editingMealLogId, setEditingMealLogId] = useState<number | null>(null);
  const [shoppingForm, setShoppingForm] =
    useState<ShoppingForm>(initialShoppingForm);
  const [calendarForm, setCalendarForm] = useState<CalendarForm>(
    createCalendarForm,
  );
  const [calendarGroupForm, setCalendarGroupForm] = useState<CalendarGroupForm>(
    initialCalendarGroupForm,
  );
  const [editingCalendarGroupId, setEditingCalendarGroupId] = useState<
    number | null
  >(null);
  const [editingCalendarEventId, setEditingCalendarEventId] = useState<
    number | null
  >(null);
  const [userForm, setUserForm] = useState<UserForm>(initialUserForm);
  const [userSettingsForm, setUserSettingsForm] = useState<UserSettingsForm>(
    initialUserSettingsForm,
  );
  const [csvImportForm, setCsvImportForm] =
    useState<CsvImportForm>(initialCsvImportForm);
  const [csvImportResult, setCsvImportResult] =
    useState<CsvImportResult | null>(null);
  const [csvImportRunning, setCsvImportRunning] = useState(false);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    const errors: string[] = [];

    async function load<T>(promise: Promise<T>, apply: (value: T) => void) {
      try {
        apply(await promise);
      } catch (error) {
        errors.push(error instanceof Error ? error.message : "API-Fehler");
      }
    }

    await Promise.all([
      load(getDashboardSummary(), setDashboard),
      load(getUsers(), setUsers),
      load(getInventory(), setInventory),
      load(getFoods(), setFoods),
      load(getProductGroups(), setProductGroups),
      load(getProductUnits(), setProductUnits),
      load(getStorageLocations(), setStorageLocations),
      load(getRecipes(), setRecipes),
      load(getMealLogs(), setMealLogs),
      load(getShoppingList(), setShoppingList),
      load(getCalendarEvents(), setCalendarEvents),
      load(getCalendarGroups(), setCalendarGroups),
      load(getInventoryWarnings(7), setWarnings),
      load(getNutritionDay(userId, selectedDate), setNutrition),
    ]);

    setApiError(errors.length > 0 ? errors[0] : null);
    setLoading(false);
  }, [selectedDate, userId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    localStorage.setItem("heim-erp-user-id", String(userId));
  }, [userId]);

  useEffect(() => {
    if (users.length > 0 && !users.some((user) => user.id === userId)) {
      setUserId(users[0].id);
    }
  }, [userId, users]);

  const activeUser = useMemo(
    () => users.find((user) => user.id === userId) ?? null,
    [userId, users],
  );

  useEffect(() => {
    setUserSettingsForm(userPreferencesFromUser(activeUser));
  }, [activeUser]);

  const positiveInventory = useMemo(
    () => inventory.filter((item) => item.quantity > 0),
    [inventory],
  );

  const filteredInventory = useMemo(() => {
    return positiveInventory.filter((item) => {
      const status = getInventoryStatus(item).status;
      const productGroupName = item.product_group?.name ?? item.category ?? "";
      const matchesSearch = `${item.name} ${item.brand ?? ""} ${productGroupName} ${
        item.storage_location ?? ""
      } ${item.barcode ?? ""}`
        .toLowerCase()
        .includes(inventorySearch.toLowerCase());
      const matchesCategory =
        inventoryCategory === "all" ||
        productGroupName === inventoryCategory ||
        item.category === inventoryCategory;
      const matchesStatus =
        inventoryStatus === "all" || status === inventoryStatus;
      return matchesSearch && matchesCategory && matchesStatus;
    });
  }, [inventoryCategory, inventorySearch, inventoryStatus, positiveInventory]);

  const inventoryCategories = useMemo(() => {
    return Array.from(
      new Set([
        ...productGroups.map((group) => group.name),
        ...positiveInventory
          .map((item) => item.product_group?.name ?? item.category)
          .filter(Boolean),
      ]),
    ) as string[];
  }, [positiveInventory, productGroups]);

  const dashboardCalendarEvents = useMemo(() => {
    const hiddenOverviewGroupIds = new Set(
      calendarGroups
        .filter((group) => group.hide_from_dashboard_and_month)
        .map((group) => group.id),
    );
    return calendarEvents.filter(
      (event) =>
        !event.group_id || !hiddenOverviewGroupIds.has(event.group_id),
    );
  }, [calendarEvents, calendarGroups]);

  const todaysEvents = useMemo(() => {
    const today = getLocalDate();
    return getCalendarOccurrences(
      dashboardCalendarEvents,
      dateFromLocalValue(today),
      dateAtEndOfDay(today),
    );
  }, [dashboardCalendarEvents]);

  const openShoppingList = useMemo(
    () => shoppingList.filter((item) => !item.is_checked),
    [shoppingList],
  );

  const pageTitle =
    activePage === "masterData"
      ? "Stammdaten verwalten"
      : pageNavigation.find((item) => item.id === activePage)?.label ?? "Dashboard";
  const appliedTheme =
    activePage === "settings" && activeUser
      ? userSettingsForm.theme
      : activeUser?.theme ?? "light";

  async function submitInventory(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = createInventoryPayload(inventoryForm, productGroups);
      if (editingInventoryItemId === null) {
        await createInventoryItem(payload);
      } else {
        await updateInventoryItem(editingInventoryItemId, payload);
      }
      setInventoryForm(createInitialInventoryForm());
      setEditingInventoryItemId(null);
      setInventoryCreateOpen(false);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingInventoryItem(item: InventoryItem) {
    setInventoryForm(createInventoryFormFromItem(item));
    setEditingInventoryItemId(item.id);
    setInventoryCreateOpen(false);
    setActivePage("foods");
  }

  function startStoringFood(food: Food) {
    setInventoryForm(
      createInventoryFormFromFood(food, productGroups, productUnits),
    );
    setEditingInventoryItemId(null);
    setInventoryCreateOpen(true);
    setActivePage("foods");
  }

  function startCreatingInventoryItem() {
    setInventoryForm(createInitialInventoryForm());
    setEditingInventoryItemId(null);
    setInventoryCreateOpen(true);
    setActivePage("foods");
  }

  function cancelEditingInventoryItem() {
    setInventoryForm(createInitialInventoryForm());
    setEditingInventoryItemId(null);
    setInventoryCreateOpen(false);
  }

  async function previewReceiptImportFile(
    filename: string,
    contentBase64: string,
  ): Promise<ReceiptImportPreview> {
    try {
      setApiError(null);
      return await previewReceiptImport(filename, contentBase64);
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      throw error;
    }
  }

  async function submitReceiptImport(
    request: ReceiptImportBookRequest,
  ): Promise<ReceiptImportBookResult> {
    try {
      setApiError(null);
      const result = await bookReceiptImport(request);
      await loadData();
      return result;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      throw error;
    }
  }

  async function removeInventoryItem(id: number) {
    try {
      setApiError(null);
      await deleteInventoryItem(id);
      if (editingInventoryItemId === id) {
        cancelEditingInventoryItem();
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitProductGroup(event: FormEvent) {
    event.preventDefault();
    await createProductGroup({
      name: productGroupForm.name,
      default_expiry_days: optionalInteger(productGroupForm.default_expiry_days),
      default_storage_location: optionalText(
        productGroupForm.default_storage_location,
      ),
    } satisfies ProductGroupCreate);
    setProductGroupForm(initialProductGroupForm);
    await loadData();
  }

  async function submitProductUnit(event: FormEvent) {
    event.preventDefault();
    await createProductUnit({
      name: productUnitForm.name,
    } satisfies ProductUnitCreate);
    setProductUnitForm(initialProductUnitForm);
    await loadData();
  }

  async function submitFood(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = createFoodPayload(foodForm);
      if (editingFoodId === null) {
        await createFood(payload);
      } else {
        await updateFood(editingFoodId, payload);
      }
      setFoodForm(createInitialFoodForm());
      setEditingFoodId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingFood(food: Food) {
    setFoodForm(createFoodFormFromFood(food));
    setEditingFoodId(food.id);
  }

  function cancelEditingFood() {
    setFoodForm(createInitialFoodForm());
    setEditingFoodId(null);
  }

  async function removeFood(foodId: number) {
    try {
      setApiError(null);
      await deleteFood(foodId);
      if (editingFoodId === foodId) {
        cancelEditingFood();
      }
      await loadData();
    } catch (error) {
      if (!isReferencedDeleteError(error)) {
        setApiError(apiErrorMessage(error));
        return;
      }

      const keepReference = window.confirm(
        "Dieses Lebensmittel wird noch verwendet, zum Beispiel im Kalorientracker. Aus normalen Listen ausblenden und Referenzen behalten?",
      );
      if (!keepReference) {
        return;
      }

      try {
        await deleteFood(foodId, true);
        if (editingFoodId === foodId) {
          cancelEditingFood();
        }
        await loadData();
      } catch (archiveError) {
        setApiError(apiErrorMessage(archiveError));
      }
    }
  }

  async function submitStorageLocation(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = {
        name: storageLocationForm.name,
      } satisfies StorageLocationCreate;
      if (editingStorageLocationId === null) {
        await createStorageLocation(payload);
      } else {
        await updateStorageLocation(
          editingStorageLocationId,
          payload satisfies StorageLocationUpdate,
        );
      }
      setStorageLocationForm(initialStorageLocationForm);
      setEditingStorageLocationId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingStorageLocation(location: StorageLocation) {
    setStorageLocationForm({ name: location.name });
    setEditingStorageLocationId(location.id);
  }

  function cancelEditingStorageLocation() {
    setStorageLocationForm(initialStorageLocationForm);
    setEditingStorageLocationId(null);
  }

  async function removeStorageLocation(locationId: number) {
    try {
      setApiError(null);
      await deleteStorageLocation(locationId);
      if (editingStorageLocationId === locationId) {
        cancelEditingStorageLocation();
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitMasterProductGroup(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = {
        name: masterProductGroupForm.name,
        default_expiry_days: optionalInteger(
          masterProductGroupForm.default_expiry_days,
        ),
        default_storage_location: optionalText(
          masterProductGroupForm.default_storage_location,
        ),
      } satisfies ProductGroupCreate;
      if (editingProductGroupId === null) {
        await createProductGroup(payload);
      } else {
        await updateProductGroup(
          editingProductGroupId,
          payload satisfies ProductGroupUpdate,
        );
      }
      setMasterProductGroupForm(initialProductGroupForm);
      setEditingProductGroupId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingProductGroup(group: ProductGroup) {
    setMasterProductGroupForm({
      name: group.name,
      default_expiry_days: toFormValue(group.default_expiry_days),
      default_storage_location: group.default_storage_location ?? "",
    });
    setEditingProductGroupId(group.id);
  }

  function cancelEditingProductGroup() {
    setMasterProductGroupForm(initialProductGroupForm);
    setEditingProductGroupId(null);
  }

  async function removeProductGroup(groupId: number) {
    try {
      setApiError(null);
      await deleteProductGroup(groupId);
      if (editingProductGroupId === groupId) {
        cancelEditingProductGroup();
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitMasterProductUnit(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = {
        name: masterProductUnitForm.name,
      } satisfies ProductUnitCreate;
      if (editingProductUnitId === null) {
        await createProductUnit(payload);
      } else {
        await updateProductUnit(
          editingProductUnitId,
          payload satisfies ProductUnitUpdate,
        );
      }
      setMasterProductUnitForm(initialProductUnitForm);
      setEditingProductUnitId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingProductUnit(unit: ProductUnit) {
    setMasterProductUnitForm({ name: unit.name });
    setEditingProductUnitId(unit.id);
  }

  function cancelEditingProductUnit() {
    setMasterProductUnitForm(initialProductUnitForm);
    setEditingProductUnitId(null);
  }

  async function removeProductUnit(unitId: number) {
    try {
      setApiError(null);
      await deleteProductUnit(unitId);
      if (editingProductUnitId === unitId) {
        cancelEditingProductUnit();
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function toggleRecipeNutrition(recipeId: number) {
    if (recipeNutrition[recipeId]) {
      setRecipeNutrition((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      return;
    }

    try {
      setApiError(null);
      const values = await getRecipeNutrition(recipeId);
      setRecipeNutrition((current) => ({
        ...current,
        [recipeId]: values,
      }));
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function syncRecipeMissingIngredients(recipeId: number) {
    try {
      setApiError(null);
      const result = await syncRecipeShoppingList(recipeId);
      await loadData();
      return result;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      throw error;
    }
  }

  async function prepareRecipeFromInventory(
    recipeId: number,
  ): Promise<RecipePrepareResult> {
    try {
      setApiError(null);
      const result = await prepareRecipe(recipeId);
      await loadData();
      return result;
    } catch (error) {
      throw error;
    }
  }

  async function submitRecipe(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = createRecipePayload(recipeForm);
      if (editingRecipeId === null) {
        await createRecipe({
          ...payload,
          created_by_user_id: userId,
          ingredients: pendingRecipeIngredients.map((ingredient) => ({
            food_id: ingredient.food_id,
            quantity: ingredient.quantity,
            unit: ingredient.unit,
            notes: ingredient.notes,
          })),
        });
      } else {
        await updateRecipe(editingRecipeId, payload);
      }
      await loadData();
      closeRecipeEditor();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startCreatingRecipe() {
    setRecipeForm(initialRecipeForm);
    setEditingRecipeId(null);
    setPendingRecipeIngredients([]);
    setRecipeIngredientForms((current) => {
      const next = { ...current };
      delete next[draftRecipeIngredientKey];
      return next;
    });
    setRecipeStepDraft("");
    setRecipeEditorOpen(true);
  }

  function startEditingRecipe(recipe: Recipe) {
    setRecipeForm(createRecipeFormFromRecipe(recipe));
    setEditingRecipeId(recipe.id);
    setPendingRecipeIngredients([]);
    setRecipeIngredientForms((current) => {
      const next = { ...current };
      delete next[draftRecipeIngredientKey];
      delete next[recipe.id];
      return next;
    });
    setRecipeStepDraft("");
    setRecipeEditorOpen(true);
  }

  function closeRecipeEditor() {
    const recipeId = editingRecipeId;
    setRecipeForm(initialRecipeForm);
    setEditingRecipeId(null);
    setPendingRecipeIngredients([]);
    setRecipeIngredientForms((current) => {
      const next = { ...current };
      delete next[draftRecipeIngredientKey];
      if (recipeId !== null) {
        delete next[recipeId];
      }
      return next;
    });
    setRecipeStepDraft("");
    setRecipeEditorOpen(false);
  }

  function addRecipeStep() {
    const nextStep = recipeStepDraft.trim();
    if (!nextStep) {
      return;
    }
    const steps = splitRecipeSteps(recipeForm.instructions);
    setRecipeForm({
      ...recipeForm,
      instructions: joinRecipeSteps([...steps, nextStep]),
    });
    setRecipeStepDraft("");
  }

  function removeRecipeStep(index: number) {
    const steps = splitRecipeSteps(recipeForm.instructions).filter(
      (_, stepIndex) => stepIndex !== index,
    );
    setRecipeForm({
      ...recipeForm,
      instructions: joinRecipeSteps(steps),
    });
  }

  function updateRecipeIngredientForm(
    recipeId: number,
    form: RecipeIngredientForm,
  ) {
    setRecipeIngredientForms((current) => ({
      ...current,
      [recipeId]: form,
    }));
  }

  async function submitRecipeIngredient(recipeId: number, event: FormEvent) {
    event.preventDefault();
    const form = recipeIngredientForms[recipeId] ?? initialRecipeIngredientForm;
    const selectedFood = findFoodByIngredientForm(foods, form);
    if (!selectedFood) {
      setApiError(
        "Bitte ein Lebensmittel ueber die Suche auswaehlen oder exakt eintragen.",
      );
      return;
    }

    const ingredientPayload = {
      food_id: selectedFood.id,
      quantity: toQuantityNumber(form.quantity, 1),
      unit: form.unit || selectedFood.serving_unit || "g",
      notes: optionalText(form.notes),
    };

    if (recipeId === draftRecipeIngredientKey) {
      setApiError(null);
      setPendingRecipeIngredients((current) => [
        ...current,
        {
          temp_id: createDraftId(),
          food: selectedFood,
          ...ingredientPayload,
        },
      ]);
      setRecipeIngredientForms((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      return;
    }

    try {
      setApiError(null);
      await createRecipeIngredient(recipeId, ingredientPayload);
      setRecipeIngredientForms((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      setRecipeNutrition((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function updatePendingRecipeIngredientAmount(tempId: string, quantity: string) {
    setPendingRecipeIngredients((current) =>
      current.map((ingredient) =>
        ingredient.temp_id === tempId
          ? { ...ingredient, quantity: toQuantityNumber(quantity, ingredient.quantity) }
          : ingredient,
      ),
    );
  }

  function removePendingRecipeIngredient(tempId: string) {
    setPendingRecipeIngredients((current) =>
      current.filter((ingredient) => ingredient.temp_id !== tempId),
    );
  }

  async function updateRecipeIngredientAmount(
    ingredient: RecipeIngredient,
    quantity: string,
  ) {
    try {
      setApiError(null);
      await updateRecipeIngredient(ingredient.id, {
        food_id: ingredient.food_id,
        quantity: toQuantityNumber(quantity, ingredient.quantity),
        unit: ingredient.unit,
        notes: ingredient.notes,
      });
      setRecipeNutrition((current) => {
        const next = { ...current };
        delete next[ingredient.recipe_id];
        return next;
      });
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function removeRecipe(recipeId: number) {
    try {
      setApiError(null);
      await deleteRecipe(recipeId);
      if (editingRecipeId === recipeId) {
        closeRecipeEditor();
      }
      setRecipeIngredientForms((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      setRecipeNutrition((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      await loadData();
    } catch (error) {
      if (!isReferencedDeleteError(error)) {
        setApiError(apiErrorMessage(error));
        return;
      }

      const keepReference = window.confirm(
        "Dieses Gericht wird noch verwendet, zum Beispiel im Kalorientracker. Aus normalen Listen ausblenden und Referenzen behalten?",
      );
      if (!keepReference) {
        return;
      }

      try {
        await deleteRecipe(recipeId, true);
        if (editingRecipeId === recipeId) {
          closeRecipeEditor();
        }
        setRecipeIngredientForms((current) => {
          const next = { ...current };
          delete next[recipeId];
          return next;
        });
        setRecipeNutrition((current) => {
          const next = { ...current };
          delete next[recipeId];
          return next;
        });
        await loadData();
      } catch (archiveError) {
        setApiError(apiErrorMessage(archiveError));
      }
    }
  }

  async function removeRecipeIngredient(recipeId: number, ingredientId: number) {
    try {
      setApiError(null);
      await deleteRecipeIngredient(ingredientId);
      setRecipeNutrition((current) => {
        const next = { ...current };
        delete next[recipeId];
        return next;
      });
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitMeal(event?: FormEvent) {
    event?.preventDefault();
    try {
      setApiError(null);
      const basePayload = {
        eaten_at: `${selectedDate}T${mealForm.time}:00`,
        meal_type: optionalText(mealForm.meal_type),
        notes: optionalText(mealForm.notes),
        user_id: userId,
      };
      let payload;

      if (mealForm.kind === "quick") {
        const quickName = optionalText(mealForm.quick_name);
        const quickProtein = optionalNumber(mealForm.quick_protein) ?? 0;
        const quickFat = optionalNumber(mealForm.quick_fat) ?? 0;
        const quickCarbs = optionalNumber(mealForm.quick_carbs) ?? 0;
        const estimatedCalories = quickProtein * 4 + quickFat * 9 + quickCarbs * 4;
        const quickCalories = optionalNumber(mealForm.quick_calories) ?? estimatedCalories;

        if (quickName === null) {
          setApiError("Bitte einen Namen fuer den Quick-Add eintragen.");
          return false;
        }
        if (
          quickCalories === 0 &&
          quickProtein === 0 &&
          quickFat === 0 &&
          quickCarbs === 0
        ) {
          setApiError("Bitte mindestens einen Naehrwert fuer den Quick-Add eintragen.");
          return false;
        }

        payload = {
          ...basePayload,
          quantity: 1,
          unit: "quick",
          food_id: null,
          recipe_id: null,
          quick_add_name: quickName,
          quick_calories: quickCalories,
          quick_protein: quickProtein,
          quick_fat: quickFat,
          quick_carbs: quickCarbs,
        };
      } else {
        const targetId = Number(mealForm.target_id);
        if (!Number.isFinite(targetId) || targetId <= 0) {
          setApiError("Bitte ein Lebensmittel oder Gericht auswaehlen.");
          return false;
        }

        payload = {
          ...basePayload,
          quantity: toQuantityNumber(mealForm.quantity, 1),
          unit: mealForm.unit,
          food_id: mealForm.kind === "food" ? targetId : null,
          recipe_id: mealForm.kind === "recipe" ? targetId : null,
          quick_add_name: null,
          quick_calories: null,
          quick_protein: null,
          quick_fat: null,
          quick_carbs: null,
        };
      }
      if (editingMealLogId === null) {
        await createMealLog(payload);
      } else {
        await updateMealLog(editingMealLogId, payload);
      }
      setMealForm(initialMealForm);
      setEditingMealLogId(null);
      await loadData();
      return true;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      return false;
    }
  }

  function startEditingMealLog(mealLog: MealLog) {
    setSelectedDate(getMealLogDate(mealLog));
    setMealForm(createMealFormFromLog(mealLog));
    setEditingMealLogId(mealLog.id);
  }

  function cancelEditingMealLog() {
    setMealForm(initialMealForm);
    setEditingMealLogId(null);
  }

  async function removeMealLog(mealLogId: number) {
    try {
      setApiError(null);
      await deleteMealLog(mealLogId);
      if (editingMealLogId === mealLogId) {
        cancelEditingMealLog();
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function moveMealLog(mealLog: MealLog, date: string, time: string) {
    try {
      setApiError(null);
      await updateMealLog(mealLog.id, {
        eaten_at: `${date}T${time}:00`,
      });
      if (editingMealLogId === mealLog.id) {
        setMealForm({
          ...mealForm,
          time,
        });
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function updateMealPrepSlot(
    date: string,
    slotId: MealPrepSlotKey,
    value: string,
  ) {
    try {
      setApiError(null);
      const slot = mealPrepSlots.find((item) => item.id === slotId);
      if (!slot) {
        return;
      }
      const existingMealLog =
        mealLogs.find((mealLog) =>
          isMealPrepSlotLog(mealLog, date, slot, userId),
        ) ?? null;

      if (!value) {
        if (existingMealLog) {
          await deleteMealLog(existingMealLog.id);
          if (editingMealLogId === existingMealLog.id) {
            cancelEditingMealLog();
          }
          await loadData();
        }
        return;
      }

      const selection = parseMealPrepSelectionValue(value);
      if (!selection) {
        setApiError("Bitte ein Lebensmittel oder Gericht auswaehlen.");
        return;
      }

      const basePayload = {
        eaten_at: `${date}T${slot.time}:00`,
        meal_type: slot.label,
        notes: "Mealprep: Bestand am Tag buchen",
        user_id: userId,
        meal_source: mealPrepSource,
        planned_inventory_deduction: true,
        inventory_deducted_at: null,
      };

      if (selection.kind === "food") {
        const food = foods.find((item) => item.id === selection.id);
        if (!food) {
          setApiError("Lebensmittel wurde nicht gefunden.");
          return;
        }
        const unit = productUnitNameForFood(food, productUnits) || "g";
        const payload = {
          ...basePayload,
          quantity: normalizedUnitName(unit) === "g" ? 100 : 1,
          unit,
          food_id: food.id,
          recipe_id: null,
          quick_add_name: null,
          quick_calories: null,
          quick_protein: null,
          quick_fat: null,
          quick_carbs: null,
        };
        if (existingMealLog) {
          await updateMealLog(existingMealLog.id, payload);
        } else {
          await createMealLog(payload);
        }
      } else {
        const recipe = recipes.find((item) => item.id === selection.id);
        if (!recipe) {
          setApiError("Gericht wurde nicht gefunden.");
          return;
        }
        const payload = {
          ...basePayload,
          quantity: 1,
          unit: "serving",
          food_id: null,
          recipe_id: recipe.id,
          quick_add_name: null,
          quick_calories: null,
          quick_protein: null,
          quick_fat: null,
          quick_carbs: null,
        };
        if (existingMealLog) {
          await updateMealLog(existingMealLog.id, payload);
        } else {
          await createMealLog(payload);
        }
      }

      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitShoppingItem(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);

      if (shoppingForm.source === "food") {
        const foodId = optionalInteger(shoppingForm.food_id);
        const food = foods.find((item) => item.id === foodId);
        if (!food) {
          setApiError("Bitte ein Lebensmittel auswaehlen.");
          return;
        }

        const unit = productUnitNameForFood(food, productUnits);
        await createShoppingListItem({
          name: food.name,
          food_id: food.id,
          quantity: toQuantityNumber(shoppingForm.quantity, 1),
          unit: unit || "pcs",
          is_checked: false,
          notes: optionalText(shoppingForm.notes),
        });
      } else {
        const name = optionalText(shoppingForm.name);
        if (!name) {
          setApiError("Bitte einen Namen fuer den Einkaufsartikel eingeben.");
          return;
        }

        await createShoppingListItem({
          name,
          quantity: toQuantityNumber(shoppingForm.quantity, 1),
          unit: shoppingForm.unit || "pcs",
          is_checked: false,
          notes: optionalText(shoppingForm.notes),
        });
      }

      setShoppingForm(initialShoppingForm);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function increaseShoppingItemQuantity(item: ShoppingListItem) {
    return runAction(() =>
      updateShoppingListItem(item.id, {
        name: item.name,
        food_id: item.food_id ?? null,
        inventory_item_id: item.inventory_item_id ?? null,
        quantity: normalizeFractionalQuantityValue(item.quantity + 1),
        unit: item.unit,
        store: item.store ?? null,
        is_checked: item.is_checked,
        notes: item.notes ?? null,
      }),
    );
  }

  async function importShoppingItemsToInventory(
    unknownItemAction: ShoppingListInventoryUnknownAction = "ask",
  ) {
    try {
      setApiError(null);
      const result = await importShoppingListToInventory({
        unknown_item_action: unknownItemAction,
      });
      if (!result.requires_decision) {
        await loadData();
      }
      return result;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      throw error;
    }
  }

  async function submitCalendarEntry(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const startAt = calendarForm.all_day
        ? `${calendarForm.date}T00:00:00`
        : `${calendarForm.date}T${calendarForm.start_time}:00`;
      const endAt = calendarForm.all_day
        ? `${calendarForm.date}T23:59:00`
        : calendarForm.end_time
          ? `${calendarForm.date}T${calendarForm.end_time}:00`
          : null;
      const payload = {
        title: calendarForm.title,
        description: optionalText(calendarForm.description),
        start_at: startAt,
        end_at: endAt,
        location: optionalText(calendarForm.location),
        entry_type: calendarForm.entry_type,
        all_day: calendarForm.all_day,
        is_completed: false,
        recurrence_frequency: calendarForm.recurrence_frequency,
        recurrence_interval: toNumber(calendarForm.recurrence_interval, 1),
        recurrence_until: calendarForm.recurrence_until
          ? `${calendarForm.recurrence_until}T23:59:59`
          : null,
        user_id: userId,
        group_id: optionalNumber(calendarForm.group_id),
      } satisfies CalendarEventCreate;
      const calendarEvent =
        editingCalendarEventId === null
          ? await createCalendarEvent(payload)
          : await updateCalendarEvent(editingCalendarEventId, payload);
      setCalendarDate(getLocalDate(new Date(calendarEvent.start_at)));
      setCalendarForm(createCalendarForm(calendarForm.date));
      setEditingCalendarEventId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function selectCalendarDate(value: string) {
    setCalendarDate(value);
    setCalendarForm((current) => ({ ...current, date: value }));
  }

  function startEditingCalendarEntry(event: CalendarEvent) {
    setCalendarForm(createCalendarFormFromEvent(event));
    setEditingCalendarEventId(event.id);
    setActivePage("calendar");
  }

  function cancelEditingCalendarEntry() {
    setCalendarForm(createCalendarForm(calendarDate));
    setEditingCalendarEventId(null);
  }

  async function removeCalendarOccurrence(occurrence: CalendarOccurrence) {
    await runAction(() =>
      excludeCalendarOccurrence(
        occurrence.event.id,
        `${getLocalDate(occurrence.startAt)}T${formatTimeInput(
          occurrence.startAt,
        )}:00`,
      ),
    );
  }

  async function removeCalendarSeries(event: CalendarEvent) {
    if (
      event.recurrence_frequency !== "none" &&
      !window.confirm(
        `Willst du wirklich ALLE Termine der Serie "${event.title}" loeschen?`,
      )
    ) {
      return;
    }

    await runAction(() => deleteCalendarEvent(event.id));
  }

  async function submitCalendarGroup(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = {
        name: calendarGroupForm.name,
        color: calendarGroupForm.color,
        suppresses_group_ids: calendarGroupForm.suppresses_group_ids,
        hide_from_dashboard_and_month:
          calendarGroupForm.hide_from_dashboard_and_month,
        user_id: userId,
      } satisfies CalendarGroupCreate;
      if (editingCalendarGroupId === null) {
        await createCalendarGroup(payload);
      } else {
        await updateCalendarGroup(editingCalendarGroupId, payload);
      }
      setCalendarGroupForm(initialCalendarGroupForm);
      setEditingCalendarGroupId(null);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  function startEditingCalendarGroup(group: CalendarGroup) {
    setCalendarGroupForm({
      name: group.name,
      color: group.color,
      suppresses_group_ids: group.suppresses_group_ids ?? [],
      hide_from_dashboard_and_month:
        group.hide_from_dashboard_and_month ?? false,
    });
    setEditingCalendarGroupId(group.id);
  }

  function cancelEditingCalendarGroup() {
    setCalendarGroupForm(initialCalendarGroupForm);
    setEditingCalendarGroupId(null);
  }

  async function removeCalendarGroup(groupId: number) {
    await runAction(async () => {
      await deleteCalendarGroup(groupId);
      if (editingCalendarGroupId === groupId) {
        cancelEditingCalendarGroup();
      }
    });
  }

  function toggleCalendarGroup(groupId: number) {
    setHiddenCalendarGroupIds((current) =>
      current.includes(groupId)
        ? current.filter((id) => id !== groupId)
        : [...current, groupId],
    );
  }

  async function submitUser(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      const payload = userPayloadFromForm(userForm);
      const user =
        editingUserId === null
          ? await createUser(payload)
          : await updateUser(editingUserId, payload);
      setUserForm(initialUserForm);
      setEditingUserId(null);
      setUserId(user.id);
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitUserSettings(event: FormEvent) {
    event.preventDefault();
    if (!activeUser) {
      return;
    }
    try {
      setApiError(null);
      await updateUser(activeUser.id, userSettingsPayloadFromForm(userSettingsForm));
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function submitCsvImport(event: FormEvent) {
    event.preventDefault();
    try {
      setApiError(null);
      setCsvImportRunning(true);
      const result = await importGrocyCsv(
        csvImportForm.directory,
        csvImportForm.dryRun,
      );
      setCsvImportResult(result);
      if (!csvImportForm.dryRun) {
        await loadData();
      }
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    } finally {
      setCsvImportRunning(false);
    }
  }

  function startEditingUser(user: User) {
    setUserForm(userFormFromUser(user));
    setEditingUserId(user.id);
    setActivePage("settings");
  }

  function cancelEditingUser() {
    setUserForm(initialUserForm);
    setEditingUserId(null);
  }

  async function removeUser(user: User) {
    try {
      setApiError(null);
      const remainingUsers = users.filter((item) => item.id !== user.id);
      await deleteUser(user.id);
      setUsers(remainingUsers);
      if (user.id === userId && remainingUsers.length > 0) {
        setUserId(remainingUsers[0].id);
        return;
      }
      await loadData();
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
    }
  }

  async function runAction(action: () => Promise<unknown>) {
    try {
      setApiError(null);
      await action();
      await loadData();
      return true;
    } catch (error) {
      setApiError(error instanceof Error ? error.message : "API-Fehler");
      return false;
    }
  }

  function selectMasterDataTab(tab: MasterDataTab) {
    setActiveMasterDataTab(tab);
    setMasterDataOpen(true);
    setActivePage("masterData");
  }

  const SettingsIcon = settingsNavigationItem.icon;

  return (
    <div className="app-shell" data-theme={appliedTheme}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Utensils size={22} />
          </div>
          <div>
            <strong>Heim-ERP</strong>
            <span>Haushalt</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="Navigation">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button
              className={`nav-item ${activePage === id ? "active" : ""}`}
              key={id}
              onClick={() => setActivePage(id)}
              type="button"
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-secondary-nav">
          <button
            className={`nav-item ${
              activePage === settingsNavigationItem.id ? "active" : ""
            }`}
            onClick={() => setActivePage(settingsNavigationItem.id)}
            type="button"
          >
            <SettingsIcon size={18} />
            <span>{settingsNavigationItem.label}</span>
          </button>
        </div>

        <div className="sidebar-master-data">
          <button
            className={`sidebar-master-toggle ${
              activePage === "masterData" ? "active" : ""
            }`}
            onClick={() => setMasterDataOpen((current) => !current)}
            type="button"
          >
            <Database size={18} />
            <span>Stammdaten verwalten</span>
            <ChevronDown size={16} />
          </button>
          {masterDataOpen && (
            <div className="sidebar-master-options">
              {masterDataTabs.map((tab) => (
                <button
                  className={`sidebar-master-option ${
                    activePage === "masterData" && activeMasterDataTab === tab.id
                      ? "active"
                      : ""
                  }`}
                  key={tab.id}
                  onClick={() => selectMasterDataTab(tab.id)}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">http://127.0.0.1:8000</p>
            <h1>{pageTitle}</h1>
          </div>
          <div className="topbar-actions">
            <label className="compact-field">
              <span>User</span>
              <select
                onChange={(event) => setUserId(toNumber(event.target.value, 1))}
                value={userId}
              >
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.username}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary" onClick={loadData} type="button">
              <RefreshCw size={16} />
              Aktualisieren
            </button>
          </div>
        </header>

        {apiError && (
          <div className="notice error">
            <AlertTriangle size={18} />
            <span>{apiError}</span>
          </div>
        )}

        {loading && <div className="loading-bar" />}

        {activePage === "dashboard" && (
          <DashboardPage
            dashboard={dashboard}
            inventoryWarnings={warnings}
            nutrition={nutrition}
            onNavigate={setActivePage}
            openShoppingList={openShoppingList}
            todaysEvents={todaysEvents}
          />
        )}

        {activePage === "calendar" && (
          <CalendarPage
            events={calendarEvents}
            foods={foods}
            groups={calendarGroups}
            groupForm={calendarGroupForm}
            hiddenGroupIds={hiddenCalendarGroupIds}
            editingGroupId={editingCalendarGroupId}
            editingEventId={editingCalendarEventId}
            form={calendarForm}
            mealLogs={mealLogs}
            onCancelEdit={cancelEditingCalendarEntry}
            onCancelGroupEdit={cancelEditingCalendarGroup}
            onDateChange={selectCalendarDate}
            onDeleteGroup={removeCalendarGroup}
            onDeleteOccurrence={removeCalendarOccurrence}
            onDeleteSeries={removeCalendarSeries}
            onDeductMealLogInventory={(mealLogId) =>
              runAction(() => deductMealLogInventory(mealLogId))
            }
            onEdit={startEditingCalendarEntry}
            onEditGroup={startEditingCalendarGroup}
            onFormChange={setCalendarForm}
            onGroupFormChange={setCalendarGroupForm}
            onGroupSubmit={submitCalendarGroup}
            onMealPrepChange={updateMealPrepSlot}
            onSubmit={submitCalendarEntry}
            onToggleGroup={toggleCalendarGroup}
            onToggleTask={(event) =>
              runAction(() =>
                updateCalendarEvent(event.id, {
                  is_completed: !event.is_completed,
                }),
              )
            }
            onViewChange={setCalendarView}
            productUnits={productUnits}
            recipes={recipes}
            selectedDate={calendarDate}
            userId={userId}
            view={calendarView}
          />
        )}

        {activePage === "foods" && (
          <InventoryPage
            activeMasterDataTab={activeMasterDataTab}
            categories={inventoryCategories}
            editingFoodId={editingFoodId}
            editingItemId={editingInventoryItemId}
            editingProductGroupId={editingProductGroupId}
            editingProductUnitId={editingProductUnitId}
            editingStorageLocationId={editingStorageLocationId}
            foodForm={foodForm}
            foods={foods}
            form={inventoryForm}
            inventory={filteredInventory}
            inventoryCategory={inventoryCategory}
            inventoryCreateOpen={inventoryCreateOpen}
            inventorySearch={inventorySearch}
            inventoryStatus={inventoryStatus}
            masterProductGroupForm={masterProductGroupForm}
            masterProductUnitForm={masterProductUnitForm}
            onCancelEditingFood={cancelEditingFood}
            onCancelEditingProductGroup={cancelEditingProductGroup}
            onCancelEditingProductUnit={cancelEditingProductUnit}
            onCancelEditingStorageLocation={cancelEditingStorageLocation}
            onCancelEdit={cancelEditingInventoryItem}
            onCategoryChange={setInventoryCategory}
            onCreateInventoryItem={startCreatingInventoryItem}
            onDelete={removeInventoryItem}
            onDeleteFood={removeFood}
            onDeleteProductGroup={removeProductGroup}
            onDeleteProductUnit={removeProductUnit}
            onDeleteStorageLocation={removeStorageLocation}
            onDecrease={(id) => runAction(() => decreaseInventoryItem(id, 1))}
            onEdit={startEditingInventoryItem}
            onEditFood={startEditingFood}
            onEditProductGroup={startEditingProductGroup}
            onEditProductUnit={startEditingProductUnit}
            onEditStorageLocation={startEditingStorageLocation}
            onFoodFormChange={setFoodForm}
            onFormChange={setInventoryForm}
            onGroupDelete={(id) => runAction(() => deleteProductGroup(id))}
            onGroupFormChange={setProductGroupForm}
            onGroupSubmit={submitProductGroup}
            onIncrease={(id) => runAction(() => increaseInventoryItem(id, 1))}
            onMasterProductGroupFormChange={setMasterProductGroupForm}
            onMasterProductGroupSubmit={submitMasterProductGroup}
            onMasterProductUnitFormChange={setMasterProductUnitForm}
            onMasterProductUnitSubmit={submitMasterProductUnit}
            onReceiptBook={submitReceiptImport}
            onReceiptPreview={previewReceiptImportFile}
            onSearchChange={setInventorySearch}
            onStorageLocationFormChange={setStorageLocationForm}
            onStorageLocationSubmit={submitStorageLocation}
            onStatusChange={setInventoryStatus}
            onFoodSubmit={submitFood}
            onSubmit={submitInventory}
            onUnitDelete={(id) => runAction(() => deleteProductUnit(id))}
            onUnitFormChange={setProductUnitForm}
            onUnitSubmit={submitProductUnit}
            productGroupForm={productGroupForm}
            productGroups={productGroups}
            productUnitForm={productUnitForm}
            productUnits={productUnits}
            storageLocationForm={storageLocationForm}
            storageLocations={storageLocations}
          />
        )}

        {activePage === "masterData" && (
          <section className="section master-data-main-section">
            <MasterDataPanel
              activeTab={activeMasterDataTab}
              editingFoodId={editingFoodId}
              editingProductGroupId={editingProductGroupId}
              editingProductUnitId={editingProductUnitId}
              editingStorageLocationId={editingStorageLocationId}
              foodForm={foodForm}
              foods={foods}
              onCancelEditingFood={cancelEditingFood}
              onCancelEditingProductGroup={cancelEditingProductGroup}
              onCancelEditingProductUnit={cancelEditingProductUnit}
              onCancelEditingStorageLocation={cancelEditingStorageLocation}
              onDeleteFood={removeFood}
              onDeleteProductGroup={removeProductGroup}
              onDeleteProductUnit={removeProductUnit}
              onDeleteStorageLocation={removeStorageLocation}
              onEditFood={startEditingFood}
              onEditProductGroup={startEditingProductGroup}
              onEditProductUnit={startEditingProductUnit}
              onEditStorageLocation={startEditingStorageLocation}
              onFoodFormChange={setFoodForm}
              onFoodSubmit={submitFood}
              onProductGroupFormChange={setMasterProductGroupForm}
              onProductGroupSubmit={submitMasterProductGroup}
              onProductUnitFormChange={setMasterProductUnitForm}
              onProductUnitSubmit={submitMasterProductUnit}
              onStoreFood={startStoringFood}
              onStorageLocationFormChange={setStorageLocationForm}
              onStorageLocationSubmit={submitStorageLocation}
              productGroupForm={masterProductGroupForm}
              productGroups={productGroups}
              productUnitForm={masterProductUnitForm}
              productUnits={productUnits}
              showTabs={false}
              storageLocationForm={storageLocationForm}
              storageLocations={storageLocations}
            />
          </section>
        )}

        {activePage === "recipes" && (
          <RecipesPage
            editingRecipeId={editingRecipeId}
            editorOpen={recipeEditorOpen}
            foods={foods}
            form={recipeForm}
            ingredientForms={recipeIngredientForms}
            onCalculate={toggleRecipeNutrition}
            onDeleteIngredient={removeRecipeIngredient}
            onDeletePendingIngredient={removePendingRecipeIngredient}
            onDeleteRecipe={removeRecipe}
            onCloseEditor={closeRecipeEditor}
            onCreateRecipe={startCreatingRecipe}
            onEditRecipe={startEditingRecipe}
            onFormChange={setRecipeForm}
            onIngredientAmountChange={updateRecipeIngredientAmount}
            onIngredientFormChange={updateRecipeIngredientForm}
            onIngredientSubmit={submitRecipeIngredient}
            onPendingIngredientAmountChange={updatePendingRecipeIngredientAmount}
            onPrepareRecipe={prepareRecipeFromInventory}
            onRecipeStepAdd={addRecipeStep}
            onRecipeStepDraftChange={setRecipeStepDraft}
            onRecipeStepRemove={removeRecipeStep}
            onSyncShoppingList={syncRecipeMissingIngredients}
            onSubmit={submitRecipe}
            pendingIngredients={pendingRecipeIngredients}
            productUnits={productUnits}
            recipeStepDraft={recipeStepDraft}
            recipeNutrition={recipeNutrition}
            recipes={recipes}
          />
        )}

        {activePage === "nutrition" && (
          <NutritionPage
            editingMealLogId={editingMealLogId}
            foods={foods}
            form={mealForm}
            inventory={inventory}
            mealLogs={mealLogs}
            nutrition={nutrition}
            onCancelEdit={cancelEditingMealLog}
            onDateChange={setSelectedDate}
            onDelete={removeMealLog}
            onEdit={startEditingMealLog}
            onFormChange={setMealForm}
            onDeductMealLogInventory={(mealLogId) =>
              runAction(() => deductMealLogInventory(mealLogId))
            }
            onInventoryDecrease={(id, amount) =>
              runAction(() => decreaseInventoryItem(id, amount))
            }
            onMove={moveMealLog}
            onSubmit={submitMeal}
            productUnits={productUnits}
            recipes={recipes}
            selectedDate={selectedDate}
          />
        )}

        {activePage === "shopping" && (
          <ShoppingPage
            foods={foods}
            form={shoppingForm}
            items={shoppingList}
            onImportToInventory={importShoppingItemsToInventory}
            onCheck={(item) =>
              runAction(() =>
                item.is_checked
                  ? uncheckShoppingListItem(item.id)
                  : checkShoppingListItem(item.id),
              )
            }
            onDelete={(id) => runAction(() => deleteShoppingListItem(id))}
            onIncrease={increaseShoppingItemQuantity}
            onFormChange={setShoppingForm}
            onGenerate={() => runAction(generateShoppingListFromLowStock)}
            productUnits={productUnits}
            onSubmit={submitShoppingItem}
          />
        )}

        {activePage === "settings" && (
          <SettingsPage
            activeUser={activeUser}
            apiBaseUrl={API_BASE_URL}
            csvImportForm={csvImportForm}
            csvImportResult={csvImportResult}
            csvImportRunning={csvImportRunning}
            form={userForm}
            editingUserId={editingUserId}
            onCancelEditing={cancelEditingUser}
            onCsvImportFormChange={setCsvImportForm}
            onCsvImportSubmit={submitCsvImport}
            onDelete={removeUser}
            onEdit={startEditingUser}
            onFormChange={setUserForm}
            onSettingsFormChange={setUserSettingsForm}
            onSettingsSubmit={submitUserSettings}
            onSubmit={submitUser}
            onUserIdChange={setUserId}
            settingsForm={userSettingsForm}
            userId={userId}
            users={users}
          />
        )}
      </main>
    </div>
  );
}

function DashboardPage({
  dashboard,
  inventoryWarnings,
  nutrition,
  onNavigate,
  openShoppingList,
  todaysEvents,
}: {
  dashboard: DashboardSummary | null;
  inventoryWarnings: InventoryWarnings;
  nutrition: NutritionDay;
  onNavigate: (page: Page) => void;
  openShoppingList: ShoppingListItem[];
  todaysEvents: CalendarOccurrence[];
}) {
  return (
    <div className="page-grid">
      <section className="metric-grid">
        {macroMeta.map((macro) => (
          <button
            className="metric-card dashboard-link-card"
            key={macro.key}
            onClick={() => onNavigate("nutrition")}
            type="button"
          >
            <div>
              <p>{macro.label}</p>
              <strong>
                {formatNumber(nutrition.totals[macro.key])}
                <span>{macro.unit}</span>
              </strong>
            </div>
            <div className="progress-track" aria-hidden="true">
              <span
                className={`progress-fill ${macro.tone}`}
                style={{
                  width: `${Math.min(nutrition.percentages[macro.key], 100)}%`,
                }}
              />
            </div>
            <small>
              {formatNumber(nutrition.remaining[macro.key])} {macro.unit} offen
            </small>
          </button>
        ))}
      </section>

      <section className="dashboard-grid">
        <Panel title="Heute">
          <div className="list-stack">
            {todaysEvents.length === 0 ? (
              <button
                className="empty-state dashboard-empty-link"
                onClick={() => onNavigate("calendar")}
                type="button"
              >
                Keine Termine
              </button>
            ) : (
              todaysEvents.map((occurrence) => (
                <button
                  className="list-row dashboard-list-link"
                  key={occurrence.key}
                  onClick={() => onNavigate("calendar")}
                  type="button"
                >
                  <CalendarDays size={18} />
                  <div>
                    <strong>{occurrence.event.title}</strong>
                    <span>{formatOccurrenceTime(occurrence)}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        </Panel>

        <Panel title="Lagerwarnungen">
          <div className="warning-grid">
            <WarningCount
              label="Niedrig"
              onClick={() => onNavigate("foods")}
              tone="low"
              value={inventoryWarnings.low_stock.length}
            />
            <WarningCount
              label="Bald ablaufend"
              onClick={() => onNavigate("foods")}
              tone="expiring"
              value={inventoryWarnings.expiring_soon.length}
            />
            <WarningCount
              label="Abgelaufen"
              onClick={() => onNavigate("foods")}
              tone="expired"
              value={inventoryWarnings.expired.length}
            />
          </div>
        </Panel>

        <Panel title="Offene Einkaufsliste">
          <div className="list-stack">
            {openShoppingList.length === 0 ? (
              <button
                className="empty-state dashboard-empty-link"
                onClick={() => onNavigate("shopping")}
                type="button"
              >
                Keine offenen Artikel
              </button>
            ) : (
              openShoppingList.slice(0, 6).map((item) => (
                <button
                  className="list-row dashboard-list-link"
                  key={item.id}
                  onClick={() => onNavigate("shopping")}
                  type="button"
                >
                  <ShoppingCart size={18} />
                  <div>
                    <strong>{item.name}</strong>
                    <span>
                      {formatFractionalQuantity(item.quantity)} {item.unit}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </Panel>
      </section>
    </div>
  );
}

function CalendarPage({
  events,
  foods,
  groups,
  groupForm,
  hiddenGroupIds,
  editingGroupId,
  editingEventId,
  form,
  mealLogs,
  onCancelEdit,
  onCancelGroupEdit,
  onDateChange,
  onDeleteGroup,
  onDeleteOccurrence,
  onDeleteSeries,
  onDeductMealLogInventory,
  onEdit,
  onEditGroup,
  onFormChange,
  onGroupFormChange,
  onGroupSubmit,
  onMealPrepChange,
  onSubmit,
  onToggleGroup,
  onToggleTask,
  onViewChange,
  productUnits,
  recipes,
  selectedDate,
  userId,
  view,
}: {
  events: CalendarEvent[];
  foods: Food[];
  groups: CalendarGroup[];
  groupForm: CalendarGroupForm;
  hiddenGroupIds: number[];
  editingGroupId: number | null;
  editingEventId: number | null;
  form: CalendarForm;
  mealLogs: MealLog[];
  onCancelEdit: () => void;
  onCancelGroupEdit: () => void;
  onDateChange: (value: string) => void;
  onDeleteGroup: (id: number) => void;
  onDeleteOccurrence: (occurrence: CalendarOccurrence) => void;
  onDeleteSeries: (event: CalendarEvent) => void;
  onDeductMealLogInventory: (mealLogId: number) => Promise<boolean> | boolean;
  onEdit: (event: CalendarEvent) => void;
  onEditGroup: (group: CalendarGroup) => void;
  onFormChange: (value: CalendarForm) => void;
  onGroupFormChange: (value: CalendarGroupForm) => void;
  onGroupSubmit: (event: FormEvent) => void;
  onMealPrepChange: (
    date: string,
    slotId: MealPrepSlotKey,
    value: string,
  ) => Promise<void> | void;
  onSubmit: (event: FormEvent) => void;
  onToggleGroup: (id: number) => void;
  onToggleTask: (event: CalendarEvent) => void;
  productUnits: ProductUnit[];
  recipes: Recipe[];
  selectedDate: string;
  userId: number;
  onViewChange: (value: CalendarView) => void;
  view: CalendarView;
}) {
  const [timeSelection, setTimeSelection] =
    useState<CalendarTimeSelection | null>(null);
  const [calendarMode, setCalendarMode] = useState<CalendarMode>("calendar");
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const createMenuRef = useCloseOnOutsideClick<HTMLDivElement>(
    createMenuOpen,
    () => setCreateMenuOpen(false),
  );
  const [createPanel, setCreatePanel] = useState<"event" | "group" | null>(
    null,
  );

  useEffect(() => {
    if (editingEventId !== null) {
      setCreatePanel("event");
    }
  }, [editingEventId]);

  useEffect(() => {
    if (editingGroupId !== null) {
      setCreatePanel("group");
    }
  }, [editingGroupId]);

  const gridDates = getVisibleCalendarDates(view, selectedDate);
  const gridStart = gridDates[0];
  const gridEnd = dateAtEndOfDay(getLocalDate(gridDates[gridDates.length - 1]));
  const overviewHiddenGroupIds = new Set(
    groups
      .filter((group) => group.hide_from_dashboard_and_month)
      .map((group) => group.id),
  );
  const visibleEvents = events.filter(
    (event) =>
      (!event.group_id || !hiddenGroupIds.includes(event.group_id)) &&
      (view !== "month" ||
        !event.group_id ||
        !overviewHiddenGroupIds.has(event.group_id)),
  );
  const occurrences = getCalendarOccurrences(visibleEvents, gridStart, gridEnd);
  const occurrencesByDate = new Map<string, CalendarOccurrence[]>();
  for (const occurrence of occurrences) {
    const current = occurrencesByDate.get(occurrence.date) ?? [];
    current.push(occurrence);
    occurrencesByDate.set(occurrence.date, current);
  }
  const timeGridRowOffset = 3;
  const selectedOccurrences = occurrencesByDate.get(selectedDate) ?? [];
  const selectedMonth = dateFromLocalValue(selectedDate).getMonth();
  const miniMonthDates = monthGridDates(selectedDate);
  const today = getLocalDate();
  const groupById = new Map(groups.map((group) => [group.id, group]));
  const navigationView: CalendarView = calendarMode === "mealprep" ? "week" : view;
  const toolbarTitle =
    calendarMode === "mealprep"
      ? "Mealprep"
      : formatCalendarViewTitle(view, selectedDate);

  function toggleSuppressedGroup(groupId: number) {
    const selected = groupForm.suppresses_group_ids.includes(groupId);
    onGroupFormChange({
      ...groupForm,
      suppresses_group_ids: selected
        ? groupForm.suppresses_group_ids.filter((id) => id !== groupId)
        : [...groupForm.suppresses_group_ids, groupId],
    });
  }

  function suppressedGroupNames(group: CalendarGroup) {
    return (group.suppresses_group_ids ?? [])
      .map((groupId) => groupById.get(groupId)?.name)
      .filter(Boolean)
      .join(", ");
  }

  function openEventCreatePanel(entryType: "event" | "task") {
    if (editingEventId !== null) {
      onCancelEdit();
    }
    onFormChange({
      ...createCalendarForm(selectedDate),
      entry_type: entryType,
    });
    setCreatePanel("event");
    setCreateMenuOpen(false);
  }

  function openGroupCreatePanel() {
    if (editingGroupId !== null) {
      onCancelGroupEdit();
    }
    onGroupFormChange(initialCalendarGroupForm);
    setCreatePanel("group");
    setCreateMenuOpen(false);
  }

  function closeCreatePanel() {
    if (createPanel === "event") {
      onCancelEdit();
    }
    if (createPanel === "group") {
      onCancelGroupEdit();
    }
    setCreatePanel(null);
    setCreateMenuOpen(false);
  }

  function occurrenceColor(occurrence: CalendarOccurrence) {
    return occurrence.event.group_id
      ? groupById.get(occurrence.event.group_id)?.color
      : undefined;
  }

  function renderOccurrenceChip(occurrence: CalendarOccurrence) {
    return (
      <span
        className={`calendar-chip ${occurrence.event.entry_type} ${
          occurrence.event.is_completed ? "completed" : ""
        }`}
        key={occurrence.key}
        style={{ borderLeftColor: occurrenceColor(occurrence) }}
      >
        {occurrence.event.title}
      </span>
    );
  }

  function startTimeSelection(dayIndex: number, slot: number) {
    setTimeSelection({ dayIndex, startSlot: slot, endSlot: slot });
  }

  function extendTimeSelection(dayIndex: number, slot: number) {
    setTimeSelection((current) =>
      current && current.dayIndex === dayIndex
        ? { ...current, endSlot: slot }
        : current,
    );
  }

  function finishTimeSelection() {
    if (!timeSelection) {
      return;
    }

    const date = getLocalDate(gridDates[timeSelection.dayIndex]);
    const startSlot = Math.min(timeSelection.startSlot, timeSelection.endSlot);
    const endSlot = Math.min(
      Math.max(timeSelection.startSlot, timeSelection.endSlot) + 1,
      48,
    );
    onDateChange(date);
    onFormChange({
      ...form,
      date,
      start_time: timeSlotLabel(startSlot),
      end_time: timeSlotEndLabel(endSlot),
      all_day: false,
    });
    setTimeSelection(null);
  }

  function isTimeSlotSelected(dayIndex: number, slot: number) {
    if (!timeSelection || timeSelection.dayIndex !== dayIndex) {
      return false;
    }
    const start = Math.min(timeSelection.startSlot, timeSelection.endSlot);
    const end = Math.max(timeSelection.startSlot, timeSelection.endSlot);
    return slot >= start && slot <= end;
  }

  const draftDayIndex = gridDates.findIndex(
    (date) => getLocalDate(date) === form.date,
  );
  const draftStartSlot = timeSelection
    ? Math.min(timeSelection.startSlot, timeSelection.endSlot)
    : timeValueToSlot(form.start_time, 18);
  const draftEndSlot = timeSelection
    ? Math.min(Math.max(timeSelection.startSlot, timeSelection.endSlot) + 1, 48)
    : Math.max(timeValueToSlot(form.end_time, draftStartSlot + 2), draftStartSlot + 1);
  const draftPreview =
    view !== "month" &&
    editingEventId === null &&
    !form.all_day &&
    draftDayIndex >= 0
      ? {
          dayIndex: timeSelection?.dayIndex ?? draftDayIndex,
          startSlot: draftStartSlot,
          endSlot: Math.min(draftEndSlot, 48),
          title: form.title.trim() || "Neuer Eintrag",
        }
      : null;

  return (
    <div className="calendar-layout">
      <section className="section calendar-section">
        <div className="calendar-toolbar">
          <div>
            <p className="eyebrow">{formatDate(selectedDate)}</p>
            <h2>{toolbarTitle}</h2>
          </div>
          <div className="calendar-controls">
            <div className="calendar-mode-switch" aria-label="Kalendermenue">
              {[
                { id: "calendar", label: "Kalender" },
                { id: "mealprep", label: "Mealprep" },
              ].map((mode) => (
                <button
                  className={calendarMode === mode.id ? "active" : ""}
                  key={mode.id}
                  onClick={() => setCalendarMode(mode.id as CalendarMode)}
                  type="button"
                >
                  {mode.label}
                </button>
              ))}
            </div>
            {calendarMode === "calendar" && (
              <div className="calendar-view-switch" aria-label="Kalenderansicht">
              {[
                { id: "day", label: "Tag" },
                { id: "week", label: "Woche" },
                { id: "month", label: "Monat" },
              ].map((calendarView) => (
                <button
                  className={calendarView.id === view ? "active" : ""}
                  key={calendarView.id}
                  onClick={() => onViewChange(calendarView.id as CalendarView)}
                  type="button"
                >
                  {calendarView.label}
                </button>
              ))}
              </div>
            )}
            <div className="calendar-nav">
              <button
                className="icon-button"
                onClick={() =>
                  onDateChange(moveCalendarView(selectedDate, navigationView, -1))
                }
                title="Vorheriger Zeitraum"
                type="button"
              >
                <ChevronLeft size={17} />
              </button>
              <button
                className="button secondary"
                onClick={() => onDateChange(today)}
                type="button"
              >
                Heute
              </button>
              <button
                className="icon-button"
                onClick={() =>
                  onDateChange(moveCalendarView(selectedDate, navigationView, 1))
                }
                title="Naechster Zeitraum"
                type="button"
              >
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
        </div>
        {calendarMode === "mealprep" ? (
          <MealPrepPlanner
            foods={foods}
            mealLogs={mealLogs}
            onDateChange={onDateChange}
            onDeductMealLogInventory={onDeductMealLogInventory}
            onMealPrepChange={onMealPrepChange}
            productUnits={productUnits}
            recipes={recipes}
            selectedDate={selectedDate}
            userId={userId}
          />
        ) : view === "month" ? (
          <>
            <div className="calendar-weekdays" aria-hidden="true">
              {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((weekday) => (
                <span key={weekday}>{weekday}</span>
              ))}
            </div>
            <div className="calendar-grid">
              {gridDates.map((date) => {
                const dateValue = getLocalDate(date);
                const dayOccurrences = occurrencesByDate.get(dateValue) ?? [];
                const dayClasses = [
                  "calendar-day",
                  dateValue === selectedDate ? "selected" : "",
                  dateValue === today ? "today" : "",
                  date.getMonth() !== selectedMonth ? "outside" : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                return (
                  <button
                    className={dayClasses}
                    key={dateValue}
                    onClick={() => onDateChange(dateValue)}
                    type="button"
                  >
                    <span className="day-number">{date.getDate()}</span>
                    <span className="day-events">
                      {dayOccurrences.slice(0, 3).map(renderOccurrenceChip)}
                      {dayOccurrences.length > 3 && (
                        <span className="calendar-more">
                          +{dayOccurrences.length - 3}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div
            className={`calendar-time-grid ${view}`}
            onPointerLeave={() => setTimeSelection(null)}
            onPointerUp={finishTimeSelection}
          >
            <span className="time-grid-corner" />
            {gridDates.map((date) => {
              const dateValue = getLocalDate(date);
              return (
                <button
                  className={`time-grid-header ${dateValue === selectedDate ? "selected" : ""}`}
                  key={`header-${dateValue}`}
                  onClick={() => onDateChange(dateValue)}
                  style={{ gridColumn: gridDates.indexOf(date) + 2 }}
                  type="button"
                >
                  <span>
                    {new Intl.DateTimeFormat("de-DE", { weekday: "short" }).format(
                      date,
                    )}
                  </span>
                  <strong>{date.getDate()}</strong>
                </button>
              );
            })}
            <span className="all-day-grid-label">Ganztag</span>
            {gridDates.map((date, dayIndex) => {
              const dateValue = getLocalDate(date);
              const allDayOccurrences = (occurrencesByDate.get(dateValue) ?? []).filter(
                (occurrence) => occurrence.event.all_day,
              );
              return (
                <div
                  className="all-day-grid-cell"
                  key={`all-day-${dateValue}`}
                  style={{ gridColumn: dayIndex + 2 }}
                >
                  {allDayOccurrences.map((occurrence) => (
                    <button
                      className={`all-day-grid-entry ${occurrence.event.entry_type} ${
                        occurrence.event.is_completed ? "completed" : ""
                      }`}
                      key={`all-day-entry-${occurrence.key}`}
                      onClick={() => {
                        onDateChange(occurrence.date);
                        onEdit(occurrence.event);
                      }}
                      style={{ borderLeftColor: occurrenceColor(occurrence) }}
                      title={`${occurrence.event.title} | ${formatOccurrenceTime(
                        occurrence,
                      )}`}
                      type="button"
                    >
                      {occurrence.event.title}
                    </button>
                  ))}
                </div>
              );
            })}
            {Array.from({ length: 48 }, (_, slot) => (
              <span
                className={`time-grid-label ${slot % 2 !== 0 ? "half" : ""}`}
                key={`label-${slot}`}
                style={{ gridRow: slot + timeGridRowOffset }}
              >
                {slot % 2 === 0 ? timeSlotLabel(slot) : ""}
              </span>
            ))}
            {gridDates.map((date, dayIndex) =>
              Array.from({ length: 48 }, (_, slot) => (
                <button
                  aria-label={`${formatDate(getLocalDate(date))} ${timeSlotLabel(slot)}`}
                  className={`time-grid-slot ${
                    isTimeSlotSelected(dayIndex, slot) ? "selecting" : ""
                  } ${slot % 2 !== 0 ? "half" : ""}`}
                  key={`${getLocalDate(date)}-${slot}`}
                  onPointerDown={(event) => {
                    event.preventDefault();
                    startTimeSelection(dayIndex, slot);
                  }}
                  onPointerEnter={() => extendTimeSelection(dayIndex, slot)}
                  style={{
                    gridColumn: dayIndex + 2,
                    gridRow: slot + timeGridRowOffset,
                  }}
                  type="button"
                />
              )),
            )}
            {gridDates.map((date, dayIndex) =>
              (occurrencesByDate.get(getLocalDate(date)) ?? [])
                .filter((occurrence) => !occurrence.event.all_day)
                .map((occurrence) => (
                  <button
                    className={`time-grid-entry ${occurrence.event.entry_type} ${
                      occurrence.event.is_completed ? "completed" : ""
                    }`}
                    key={`time-${occurrence.key}`}
                    onClick={() => {
                      onDateChange(occurrence.date);
                      onEdit(occurrence.event);
                    }}
                    style={{
                      borderLeftColor: occurrenceColor(occurrence),
                      gridColumn: dayIndex + 2,
                      gridRow: `${occurrenceStartSlot(occurrence) + timeGridRowOffset} / ${
                        occurrenceEndSlot(occurrence) + timeGridRowOffset
                      }`,
                    }}
                    title={`${occurrence.event.title} | ${formatOccurrenceTime(
                      occurrence,
                    )}`}
                    type="button"
                  >
                    <strong>{occurrence.event.title}</strong>
                    <span>{formatOccurrenceTime(occurrence)}</span>
                  </button>
                )),
            )}
            {draftPreview && (
              <div
                className="time-grid-entry preview"
                style={{
                  gridColumn: draftPreview.dayIndex + 2,
                  gridRow: `${draftPreview.startSlot + timeGridRowOffset} / ${
                    draftPreview.endSlot + timeGridRowOffset
                  }`,
                }}
              >
                <strong>{draftPreview.title}</strong>
                <span>
                  {timeSlotLabel(draftPreview.startSlot)} -{" "}
                  {timeSlotEndLabel(draftPreview.endSlot)}
                </span>
              </div>
            )}
          </div>
        )}
        {calendarMode === "calendar" && (
        <div className="selected-day">
          <div className="section-header">
            <div>
              <p className="eyebrow">{formatDate(selectedDate)}</p>
              <h2>Eintraege</h2>
            </div>
          </div>
          <div className="agenda-list">
            {selectedOccurrences.length === 0 ? (
              <EmptyState label="Keine Eintraege" />
            ) : (
              selectedOccurrences.map((occurrence) => (
                <article
                  className={`agenda-item ${occurrence.event.entry_type} ${
                    occurrence.event.is_completed ? "completed" : ""
                  }`}
                  key={occurrence.key}
                >
                  {occurrence.event.entry_type === "task" ? (
                    <button
                      className="check-button"
                      onClick={() => onToggleTask(occurrence.event)}
                      title={
                        occurrence.event.is_completed
                          ? "Aufgabe oeffnen"
                          : "Aufgabe erledigen"
                      }
                      type="button"
                    >
                      {occurrence.event.is_completed ? (
                        <CheckCircle2 size={18} />
                      ) : (
                        <Circle size={18} />
                      )}
                    </button>
                  ) : (
                    <CalendarDays size={20} />
                  )}
                  <div>
                    <strong>{occurrence.event.title}</strong>
                    <span>
                      {formatOccurrenceTime(occurrence)}
                      {occurrence.event.location ? ` | ${occurrence.event.location}` : ""}
                      {occurrence.event.group_id
                        ? ` | ${groupById.get(occurrence.event.group_id)?.name ?? ""}`
                        : ""}
                    </span>
                    {occurrence.event.description && (
                      <p>{occurrence.event.description}</p>
                    )}
                  </div>
                  <div className="agenda-actions">
                    <button
                      className="icon-button"
                      onClick={() => onEdit(occurrence.event)}
                      title="Eintrag bearbeiten"
                      type="button"
                    >
                      <Pencil size={16} />
                    </button>
                    {occurrence.event.recurrence_frequency !== "none" && (
                      <button
                        className="icon-button danger"
                        onClick={() => onDeleteOccurrence(occurrence)}
                        title="Nur dieses Serienvorkommen loeschen"
                        type="button"
                      >
                        <X size={16} />
                      </button>
                    )}
                    <button
                      className="icon-button danger"
                      onClick={() => onDeleteSeries(occurrence.event)}
                      title={
                        occurrence.event.recurrence_frequency === "none"
                          ? "Eintrag loeschen"
                          : "Ganze Serie loeschen"
                      }
                      type="button"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
        )}
      </section>

      <div className="calendar-sidebar">
        <div className="calendar-create-menu" ref={createMenuRef}>
          <button
            aria-expanded={createMenuOpen}
            className={`calendar-create-button ${createMenuOpen ? "active" : ""}`}
            onClick={() => setCreateMenuOpen((open) => !open)}
            type="button"
          >
            <Plus size={22} />
            <span>Erstellen</span>
            <ChevronDown size={16} />
          </button>
          {createMenuOpen && (
            <div className="calendar-create-options">
              <button onClick={() => openEventCreatePanel("event")} type="button">
                <CalendarDays size={16} />
                Termin
              </button>
              <button onClick={() => openEventCreatePanel("task")} type="button">
                <CheckCircle2 size={16} />
                Aufgabe
              </button>
              <button onClick={openGroupCreatePanel} type="button">
                <Plus size={16} />
                Kalendergruppe
              </button>
            </div>
          )}
        </div>

        {createPanel === "event" && (
          <Panel
            title={
              editingEventId !== null
                ? "Eintrag bearbeiten"
                : form.entry_type === "task"
                  ? "Aufgabe anlegen"
                  : "Termin anlegen"
            }
          >
            <form className="form-grid calendar-form" onSubmit={onSubmit}>
              <label>
                <span>Typ</span>
                <select
                  onChange={(event) =>
                    onFormChange({
                      ...form,
                      entry_type: event.target.value as "event" | "task",
                    })
                  }
                  value={form.entry_type}
                >
                  <option value="event">Termin</option>
                  <option value="task">Aufgabe</option>
                </select>
              </label>
              <TextInput
                label="Titel"
                onChange={(title) => onFormChange({ ...form, title })}
                required
                value={form.title}
              />
              <DateInput
                label="Datum"
                onChange={(date) => onFormChange({ ...form, date })}
                value={form.date}
              />
              <label className="check-field">
                <input
                  checked={form.all_day}
                  onChange={(event) =>
                    onFormChange({ ...form, all_day: event.target.checked })
                  }
                  type="checkbox"
                />
                <span>Ganztagig</span>
              </label>
              {!form.all_day && (
                <div className="time-fields">
                  <TextInput
                    label="Anfang"
                    onChange={(start_time) =>
                      onFormChange({ ...form, start_time })
                    }
                    required
                    type="time"
                    value={form.start_time}
                  />
                  <TextInput
                    label="Ende"
                    onChange={(end_time) => onFormChange({ ...form, end_time })}
                    type="time"
                    value={form.end_time}
                  />
                </div>
              )}
              <TextInput
                label="Ort"
                onChange={(location) => onFormChange({ ...form, location })}
                value={form.location}
              />
              <label>
                <span>Gruppe</span>
                <select
                  onChange={(event) =>
                    onFormChange({ ...form, group_id: event.target.value })
                  }
                  value={form.group_id}
                >
                  <option value="">Ohne Gruppe</option>
                  {groups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Wiederholung</span>
                <select
                  onChange={(event) =>
                    onFormChange({
                      ...form,
                      recurrence_frequency:
                        event.target.value as CalendarForm["recurrence_frequency"],
                    })
                  }
                  value={form.recurrence_frequency}
                >
                  <option value="none">Keine</option>
                  <option value="daily">TÃ¤glich</option>
                  <option value="weekly">WÃ¶chentlich</option>
                  <option value="monthly">Monatlich</option>
                  <option value="yearly">JÃ¤hrlich</option>
                </select>
              </label>
              {form.recurrence_frequency !== "none" && (
                <div className="time-fields">
                  <NumberInput
                    label="Intervall"
                    onChange={(recurrence_interval) =>
                      onFormChange({ ...form, recurrence_interval })
                    }
                    value={form.recurrence_interval}
                  />
                  <DateInput
                    label="Serienende"
                    onChange={(recurrence_until) =>
                      onFormChange({ ...form, recurrence_until })
                    }
                    value={form.recurrence_until}
                  />
                </div>
              )}
              <label>
                <span>Notizen</span>
                <textarea
                  onChange={(event) =>
                    onFormChange({ ...form, description: event.target.value })
                  }
                  value={form.description}
                />
              </label>
              <div className="form-actions">
                <button className="button primary" type="submit">
                  {editingEventId !== null ? (
                    <Pencil size={16} />
                  ) : (
                    <Plus size={16} />
                  )}
                  {editingEventId !== null ? "Speichern" : "Anlegen"}
                </button>
                <button
                  className="button secondary"
                  onClick={closeCreatePanel}
                  type="button"
                >
                  <X size={16} />
                  {editingEventId !== null ? "Abbrechen" : "Schliessen"}
                </button>
              </div>
            </form>
          </Panel>
        )}

        {createPanel === "group" && (
          <Panel
            title={
              editingGroupId === null ? "Kalendergruppe anlegen" : "Gruppe bearbeiten"
            }
          >
            <form className="form-grid group-form" onSubmit={onGroupSubmit}>
              <TextInput
                label={editingGroupId === null ? "Neue Gruppe" : "Gruppe bearbeiten"}
                onChange={(name) => onGroupFormChange({ ...groupForm, name })}
                required
                value={groupForm.name}
              />
              <label>
                <span>Farbe</span>
                <input
                  onChange={(event) =>
                    onGroupFormChange({ ...groupForm, color: event.target.value })
                  }
                  type="color"
                  value={groupForm.color}
                />
              </label>
              <label className="check-field calendar-wide-check">
                <input
                  checked={groupForm.hide_from_dashboard_and_month}
                  onChange={(event) =>
                    onGroupFormChange({
                      ...groupForm,
                      hide_from_dashboard_and_month: event.target.checked,
                    })
                  }
                  type="checkbox"
                />
                <span>Aus Dashboard und Monatsansicht ausblenden</span>
              </label>
              {groups.some((group) => group.id !== editingGroupId) && (
                <div className="calendar-link-options">
                  <span>Verdraengt Kalender</span>
                  {groups
                    .filter((group) => group.id !== editingGroupId)
                    .map((group) => (
                      <label className="check-field" key={group.id}>
                        <input
                          checked={groupForm.suppresses_group_ids.includes(group.id)}
                          onChange={() => toggleSuppressedGroup(group.id)}
                          type="checkbox"
                        />
                        <span>{group.name}</span>
                      </label>
                    ))}
                </div>
              )}
              <div className="form-actions">
                <button className="button secondary" type="submit">
                  {editingGroupId === null ? (
                    <Plus size={16} />
                  ) : (
                    <Pencil size={16} />
                  )}
                  {editingGroupId === null ? "Gruppe anlegen" : "Speichern"}
                </button>
                <button
                  className="button secondary"
                  onClick={closeCreatePanel}
                  type="button"
                >
                  <X size={16} />
                  {editingGroupId === null ? "Schliessen" : "Abbrechen"}
                </button>
              </div>
            </form>
          </Panel>
        )}

        <div className="mini-calendar">
          <div className="mini-calendar-head">
            <strong>{formatMonth(selectedDate)}</strong>
            <div>
              <button
                className="icon-button compact"
                onClick={() => onDateChange(moveCalendarMonth(selectedDate, -1))}
                title="Vorheriger Monat"
                type="button"
              >
                <ChevronLeft size={15} />
              </button>
              <button
                className="icon-button compact"
                onClick={() => onDateChange(moveCalendarMonth(selectedDate, 1))}
                title="Naechster Monat"
                type="button"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
          <div className="mini-calendar-weekdays" aria-hidden="true">
            {["M", "D", "M", "D", "F", "S", "S"].map((weekday, index) => (
              <span key={`${weekday}-${index}`}>{weekday}</span>
            ))}
          </div>
          <div className="mini-calendar-grid">
            {miniMonthDates.map((date) => {
              const dateValue = getLocalDate(date);
              const dayClasses = [
                "mini-calendar-day",
                dateValue === selectedDate ? "selected" : "",
                dateValue === today ? "today" : "",
                date.getMonth() !== selectedMonth ? "outside" : "",
              ]
                .filter(Boolean)
                .join(" ");

              return (
                <button
                  className={dayClasses}
                  key={`mini-${dateValue}`}
                  onClick={() => onDateChange(dateValue)}
                  type="button"
                >
                  {date.getDate()}
                </button>
              );
            })}
          </div>
        </div>

        <Panel title="Kalendergruppen">
          <div className="calendar-group-list">
            {groups.length === 0 ? (
              <EmptyState label="Keine Gruppen" />
            ) : (
              groups.map((group) => {
                const hidden = hiddenGroupIds.includes(group.id);
                return (
                  <div className={`calendar-group-row ${hidden ? "hidden" : ""}`} key={group.id}>
                    <button
                      className="icon-button"
                      onClick={() => onToggleGroup(group.id)}
                      title={hidden ? "Gruppe einblenden" : "Gruppe ausblenden"}
                      type="button"
                    >
                      {hidden ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                    <span className="group-swatch" style={{ background: group.color }} />
                    <div className="calendar-group-info">
                      <strong>{group.name}</strong>
                      {suppressedGroupNames(group) && (
                        <small>Verdraengt: {suppressedGroupNames(group)}</small>
                      )}
                      {group.hide_from_dashboard_and_month && (
                        <small>Dashboard/Monat ausgeblendet</small>
                      )}
                    </div>
                    <button
                      className="icon-button"
                      onClick={() => onEditGroup(group)}
                      title="Gruppe bearbeiten"
                      type="button"
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      className="icon-button danger"
                      onClick={() => onDeleteGroup(group.id)}
                      title="Gruppe loeschen"
                      type="button"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </Panel>

        {false && (
        <Panel
          title={
            editingEventId !== null
              ? "Eintrag bearbeiten"
              : form.entry_type === "task"
                ? "Aufgabe anlegen"
                : "Termin anlegen"
          }
        >
          <form className="form-grid calendar-form" onSubmit={onSubmit}>
          <label>
            <span>Typ</span>
            <select
              onChange={(event) =>
                onFormChange({
                  ...form,
                  entry_type: event.target.value as "event" | "task",
                })
              }
              value={form.entry_type}
            >
              <option value="event">Termin</option>
              <option value="task">Aufgabe</option>
            </select>
          </label>
          <TextInput
            label="Titel"
            onChange={(title) => onFormChange({ ...form, title })}
            required
            value={form.title}
          />
          <DateInput
            label="Datum"
            onChange={(date) => onFormChange({ ...form, date })}
            value={form.date}
          />
          <label className="check-field">
            <input
              checked={form.all_day}
              onChange={(event) =>
                onFormChange({ ...form, all_day: event.target.checked })
              }
              type="checkbox"
            />
            <span>Ganztagig</span>
          </label>
          {!form.all_day && (
            <div className="time-fields">
              <TextInput
                label="Anfang"
                onChange={(start_time) => onFormChange({ ...form, start_time })}
                required
                type="time"
                value={form.start_time}
              />
              <TextInput
                label="Ende"
                onChange={(end_time) => onFormChange({ ...form, end_time })}
                type="time"
                value={form.end_time}
              />
            </div>
          )}
          <TextInput
            label="Ort"
            onChange={(location) => onFormChange({ ...form, location })}
            value={form.location}
          />
          <label>
            <span>Gruppe</span>
            <select
              onChange={(event) =>
                onFormChange({ ...form, group_id: event.target.value })
              }
              value={form.group_id}
            >
              <option value="">Ohne Gruppe</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Wiederholung</span>
            <select
              onChange={(event) =>
                onFormChange({
                  ...form,
                  recurrence_frequency:
                    event.target.value as CalendarForm["recurrence_frequency"],
                })
              }
              value={form.recurrence_frequency}
            >
              <option value="none">Keine</option>
              <option value="daily">Täglich</option>
              <option value="weekly">Wöchentlich</option>
              <option value="monthly">Monatlich</option>
              <option value="yearly">Jährlich</option>
            </select>
          </label>
          {form.recurrence_frequency !== "none" && (
            <div className="time-fields">
              <NumberInput
                label="Intervall"
                onChange={(recurrence_interval) =>
                  onFormChange({ ...form, recurrence_interval })
                }
                value={form.recurrence_interval}
              />
              <DateInput
                label="Serienende"
                onChange={(recurrence_until) =>
                  onFormChange({ ...form, recurrence_until })
                }
                value={form.recurrence_until}
              />
            </div>
          )}
          <label>
            <span>Notizen</span>
            <textarea
              onChange={(event) =>
                onFormChange({ ...form, description: event.target.value })
              }
              value={form.description}
            />
          </label>
          <div className="form-actions">
            <button className="button primary" type="submit">
              {editingEventId !== null ? <Pencil size={16} /> : <Plus size={16} />}
              {editingEventId !== null ? "Speichern" : "Anlegen"}
            </button>
            {editingEventId !== null && (
              <button className="button secondary" onClick={onCancelEdit} type="button">
                <X size={16} />
                Abbrechen
              </button>
            )}
          </div>
        </form>
      </Panel>
        )}
      </div>
    </div>
  );
}

function MealPrepPlanner({
  foods,
  mealLogs,
  onDateChange,
  onDeductMealLogInventory,
  onMealPrepChange,
  productUnits,
  recipes,
  selectedDate,
  userId,
}: {
  foods: Food[];
  mealLogs: MealLog[];
  onDateChange: (value: string) => void;
  onDeductMealLogInventory: (mealLogId: number) => Promise<boolean> | boolean;
  onMealPrepChange: (
    date: string,
    slotId: MealPrepSlotKey,
    value: string,
  ) => Promise<void> | void;
  productUnits: ProductUnit[];
  recipes: Recipe[];
  selectedDate: string;
  userId: number;
}) {
  const weekDates = weekGridDates(selectedDate);
  const today = getLocalDate();
  const sortedRecipes = [...recipes].sort((first, second) =>
    first.name.localeCompare(second.name, "de-DE"),
  );
  const sortedFoods = [...foods].sort((first, second) =>
    first.name.localeCompare(second.name, "de-DE"),
  );
  const weekDateValues = new Set(weekDates.map((date) => getLocalDate(date)));
  const weekMealPrepLogs = mealLogs.filter(
    (mealLog) =>
      mealLog.meal_source === mealPrepSource &&
      weekDateValues.has(getMealLogDate(mealLog)) &&
      (mealLog.user_id === null ||
        mealLog.user_id === undefined ||
        mealLog.user_id === userId),
  );
  const bookedCount = weekMealPrepLogs.filter(
    (mealLog) => mealLog.inventory_deducted_at,
  ).length;

  function mealLogForSlot(date: string, slot: (typeof mealPrepSlots)[number]) {
    return (
      mealLogs.find((mealLog) =>
        isMealPrepSlotLog(mealLog, date, slot, userId),
      ) ?? null
    );
  }

  function foodMealPrepOptionLabel(food: Food) {
    const unit = productUnitNameForFood(food, productUnits) || "g";
    const quantity = normalizedUnitName(unit) === "g" ? "100" : "1";
    return `${food.name}${food.brand ? ` | ${food.brand}` : ""} (${quantity} ${unit})`;
  }

  function statusLabel(mealLog: MealLog | null) {
    if (!mealLog) {
      return "Nicht geplant";
    }
    return mealLog.inventory_deducted_at ? "Gebucht" : "Bestand geplant";
  }

  return (
    <div className="mealprep-planner">
      <div className="mealprep-header">
        <div>
          <p className="eyebrow">{formatCalendarViewTitle("week", selectedDate)}</p>
          <h3>Mealprep</h3>
        </div>
        <div className="mealprep-summary">
          <span>{weekMealPrepLogs.length} geplant</span>
          <span>{bookedCount} gebucht</span>
        </div>
      </div>

      <div className="mealprep-grid">
        {weekDates.map((date) => {
          const dateValue = getLocalDate(date);
          const isSelected = dateValue === selectedDate;
          const isToday = dateValue === today;

          return (
            <article
              className={`mealprep-day-card ${isSelected ? "selected" : ""} ${
                isToday ? "today" : ""
              }`}
              key={dateValue}
            >
              <button
                className="mealprep-day-head"
                onClick={() => onDateChange(dateValue)}
                type="button"
              >
                <span>
                  {new Intl.DateTimeFormat("de-DE", { weekday: "short" }).format(
                    date,
                  )}
                </span>
                <strong>{date.getDate()}</strong>
              </button>

              <div className="mealprep-slots">
                {mealPrepSlots.map((slot) => {
                  const mealLog = mealLogForSlot(dateValue, slot);
                  const selectionValue = mealPrepSelectionValueFromLog(mealLog);
                  const booked = Boolean(mealLog?.inventory_deducted_at);

                  return (
                    <div className="mealprep-slot-row" key={slot.id}>
                      <div className="mealprep-slot-label">
                        <span>{slot.label}</span>
                        <small>{slot.time}</small>
                      </div>
                      <select
                        aria-label={`${slot.label} ${formatDate(dateValue)}`}
                        onChange={(event) =>
                          void onMealPrepChange(dateValue, slot.id, event.target.value)
                        }
                        value={selectionValue}
                      >
                        <option value="">Nicht geplant</option>
                        <optgroup label="Gerichte">
                          {sortedRecipes.map((recipe) => (
                            <option key={recipe.id} value={`recipe:${recipe.id}`}>
                              {recipe.name}
                            </option>
                          ))}
                        </optgroup>
                        <optgroup label="Lebensmittel">
                          {sortedFoods.map((food) => (
                            <option key={food.id} value={`food:${food.id}`}>
                              {foodMealPrepOptionLabel(food)}
                            </option>
                          ))}
                        </optgroup>
                      </select>
                      <div className="mealprep-slot-actions">
                        <span
                          className={`mealprep-status ${
                            mealLog ? (booked ? "booked" : "pending") : "empty"
                          }`}
                        >
                          {statusLabel(mealLog)}
                        </span>
                        {mealLog && !booked && (
                          <button
                            className="button secondary mealprep-book-button"
                            onClick={() => void onDeductMealLogInventory(mealLog.id)}
                            type="button"
                          >
                            <Check size={15} />
                            Bestand buchen
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function InventoryPage({
  activeMasterDataTab,
  categories,
  editingFoodId,
  editingItemId,
  editingProductGroupId,
  editingProductUnitId,
  editingStorageLocationId,
  foodForm,
  foods,
  form,
  inventory,
  inventoryCategory,
  inventoryCreateOpen,
  inventorySearch,
  inventoryStatus,
  masterProductGroupForm,
  masterProductUnitForm,
  onCancelEditingFood,
  onCancelEditingProductGroup,
  onCancelEditingProductUnit,
  onCancelEditingStorageLocation,
  onCancelEdit,
  onCategoryChange,
  onCreateInventoryItem,
  onDelete,
  onDeleteFood,
  onDeleteProductGroup,
  onDeleteProductUnit,
  onDeleteStorageLocation,
  onDecrease,
  onEdit,
  onEditFood,
  onEditProductGroup,
  onEditProductUnit,
  onEditStorageLocation,
  onFoodFormChange,
  onFormChange,
  onGroupDelete,
  onGroupFormChange,
  onGroupSubmit,
  onIncrease,
  onMasterProductGroupFormChange,
  onMasterProductGroupSubmit,
  onMasterProductUnitFormChange,
  onMasterProductUnitSubmit,
  onReceiptBook,
  onReceiptPreview,
  onSearchChange,
  onStorageLocationFormChange,
  onStorageLocationSubmit,
  onStatusChange,
  onFoodSubmit,
  onSubmit,
  onUnitDelete,
  onUnitFormChange,
  onUnitSubmit,
  productGroupForm,
  productGroups,
  productUnitForm,
  productUnits,
  storageLocationForm,
  storageLocations,
}: {
  activeMasterDataTab: MasterDataTab;
  categories: string[];
  editingFoodId: number | null;
  editingItemId: number | null;
  editingProductGroupId: number | null;
  editingProductUnitId: number | null;
  editingStorageLocationId: number | null;
  foodForm: FoodForm;
  foods: Food[];
  form: InventoryForm;
  inventory: InventoryItem[];
  inventoryCategory: string;
  inventoryCreateOpen: boolean;
  inventorySearch: string;
  inventoryStatus: string;
  masterProductGroupForm: ProductGroupForm;
  masterProductUnitForm: ProductUnitForm;
  onCancelEditingFood: () => void;
  onCancelEditingProductGroup: () => void;
  onCancelEditingProductUnit: () => void;
  onCancelEditingStorageLocation: () => void;
  onCancelEdit: () => void;
  onCategoryChange: (value: string) => void;
  onCreateInventoryItem: () => void;
  onDelete: (id: number) => void;
  onDeleteFood: (id: number) => void;
  onDeleteProductGroup: (id: number) => void;
  onDeleteProductUnit: (id: number) => void;
  onDeleteStorageLocation: (id: number) => void;
  onDecrease: (id: number) => void;
  onEdit: (item: InventoryItem) => void;
  onEditFood: (food: Food) => void;
  onEditProductGroup: (group: ProductGroup) => void;
  onEditProductUnit: (unit: ProductUnit) => void;
  onEditStorageLocation: (location: StorageLocation) => void;
  onFoodFormChange: (value: FoodForm) => void;
  onFormChange: (value: InventoryForm) => void;
  onGroupDelete: (id: number) => void;
  onGroupFormChange: (value: ProductGroupForm) => void;
  onGroupSubmit: (event: FormEvent) => Promise<void> | void;
  onIncrease: (id: number) => void;
  onMasterProductGroupFormChange: (value: ProductGroupForm) => void;
  onMasterProductGroupSubmit: (event: FormEvent) => Promise<void> | void;
  onMasterProductUnitFormChange: (value: ProductUnitForm) => void;
  onMasterProductUnitSubmit: (event: FormEvent) => Promise<void> | void;
  onReceiptBook: (
    request: ReceiptImportBookRequest,
  ) => Promise<ReceiptImportBookResult>;
  onReceiptPreview: (
    filename: string,
    contentBase64: string,
  ) => Promise<ReceiptImportPreview>;
  onSearchChange: (value: string) => void;
  onStorageLocationFormChange: (value: StorageLocationForm) => void;
  onStorageLocationSubmit: (event: FormEvent) => Promise<void> | void;
  onStatusChange: (value: string) => void;
  onFoodSubmit: (event: FormEvent) => Promise<void> | void;
  onSubmit: (event: FormEvent) => void;
  onUnitDelete: (id: number) => void;
  onUnitFormChange: (value: ProductUnitForm) => void;
  onUnitSubmit: (event: FormEvent) => Promise<void> | void;
  productGroupForm: ProductGroupForm;
  productGroups: ProductGroup[];
  productUnitForm: ProductUnitForm;
  productUnits: ProductUnit[];
  storageLocationForm: StorageLocationForm;
  storageLocations: StorageLocation[];
}) {
  const [productGroupUiOpen, setProductGroupUiOpen] = useState(false);
  const [productUnitUiOpen, setProductUnitUiOpen] = useState(false);
  const [columnEditorOpen, setColumnEditorOpen] = useState(false);
  const columnEditorRef = useCloseOnOutsideClick<HTMLDivElement>(
    columnEditorOpen,
    () => setColumnEditorOpen(false),
  );
  const [inventoryLocation, setInventoryLocation] = useState("all");
  const [visibleColumnKeys, setVisibleColumnKeys] = useState<
    InventoryColumnKey[]
  >(getInitialInventoryVisibleColumns);
  const [receiptImportOpen, setReceiptImportOpen] = useState(false);
  const [receiptImportFile, setReceiptImportFile] = useState<File | null>(null);
  const [receiptPreview, setReceiptPreview] =
    useState<ReceiptImportPreview | null>(null);
  const [receiptRows, setReceiptRows] = useState<ReceiptImportBookItem[]>([]);
  const [receiptPurchaseDate, setReceiptPurchaseDate] = useState(getLocalDate());
  const [receiptStorageLocation, setReceiptStorageLocation] = useState("");
  const [receiptImportBusy, setReceiptImportBusy] = useState(false);
  const [receiptImportMessage, setReceiptImportMessage] = useState("");

  useEffect(() => {
    localStorage.setItem(
      inventoryColumnStorageKey,
      JSON.stringify(visibleColumnKeys),
    );
  }, [visibleColumnKeys]);

  const visibleColumns = inventoryColumnDefinitions.filter((column) =>
    visibleColumnKeys.includes(column.key),
  );
  const locationOptions = Array.from(
    new Set(
      [
        ...storageLocations.map((location) => location.name),
        ...inventory
          .map((item) => item.storage_location)
          .filter((location): location is string => Boolean(location)),
      ],
    ),
  );
  const storageLocationSelectOptions = Array.from(
    new Set(
      [...locationOptions, form.storage_location].filter(
        (location): location is string => Boolean(location?.trim()),
      ),
    ),
  );
  const displayedInventory = inventory.filter(
    (item) =>
      inventoryLocation === "all" ||
      item.storage_location === inventoryLocation,
  );
  const totalInventoryValue = displayedInventory.reduce(
    (sum, item) => sum + (item.price ?? 0) * item.quantity,
    0,
  );
  const expiredCount = displayedInventory.filter(
    (item) => daysUntil(item.expiry_date) < 0,
  ).length;
  const overdueCount = displayedInventory.filter(
    (item) => daysUntil(item.expiry_date) === 0,
  ).length;
  const dueSoonCount = displayedInventory.filter((item) => {
    const distance = daysUntil(item.expiry_date);
    return distance >= 0 && distance <= 5;
  }).length;
  const lowStockCount = displayedInventory.filter(
    (item) => item.quantity <= item.minimum_quantity,
  ).length;
  const foodOptions = foods
    .slice()
    .sort((first, second) => first.name.localeCompare(second.name, "de"));
  const selectedInventoryFood =
    foods.find((food) => String(food.id) === form.food_id) ?? null;
  const selectedInventoryFoodUnit = selectedInventoryFood
    ? productUnitNameForFood(selectedInventoryFood, productUnits)
    : "";

  function selectInventoryFood(foodId: string, foodQuery?: string) {
    const food = foods.find((item) => String(item.id) === foodId);
    if (!food) {
      onFormChange({
        ...createInitialInventoryForm(),
        food_query: "",
        quantity: form.quantity,
        minimum_quantity: form.minimum_quantity,
        purchase_date: form.purchase_date,
        price: form.price,
        barcode: form.barcode,
        image_path: form.image_path,
        notes: form.notes,
      });
      return;
    }

    const nextForm = createInventoryFormFromFood(
      food,
      productGroups,
      productUnits,
    );
    const preserveExistingDetails = editingItemId !== null && form.food_id !== "";
    const preserveManualStorageLocation =
      form.food_id === "" && form.storage_location && !form.food_query.trim();
    onFormChange({
      ...nextForm,
      food_query: foodQuery ?? formatFoodSuggestionLabel(food),
      quantity: form.quantity || nextForm.quantity,
      minimum_quantity: preserveExistingDetails
        ? form.minimum_quantity || nextForm.minimum_quantity
        : nextForm.minimum_quantity,
      storage_location: preserveManualStorageLocation
        ? form.storage_location
        : nextForm.storage_location,
      purchase_date: form.purchase_date || nextForm.purchase_date,
      price: form.price || nextForm.price,
      barcode: preserveExistingDetails
        ? form.barcode || nextForm.barcode
        : nextForm.barcode,
      image_path: form.image_path,
      notes: form.notes,
    });
  }

  function searchInventoryFood(query: string) {
    const normalizedQuery = query.trim().toLowerCase();
    const selectedFood = foods.find((food) => {
      const label = formatFoodSuggestionLabel(food).toLowerCase();
      return label === normalizedQuery || food.name.toLowerCase() === normalizedQuery;
    });

    if (selectedFood) {
      selectInventoryFood(String(selectedFood.id), formatFoodSuggestionLabel(selectedFood));
      return;
    }

    onFormChange({
      ...form,
      food_id: "",
      food_query: query,
    });
  }

  function selectProductGroup(productGroupId: string) {
    const productGroup = productGroups.find(
      (group) => String(group.id) === productGroupId,
    );
    onFormChange({
      ...form,
      product_group_id: productGroupId,
      category: productGroup?.name ?? "",
      expiry_days:
        productGroup?.default_expiry_days === null ||
        productGroup?.default_expiry_days === undefined
          ? form.expiry_days
          : String(productGroup.default_expiry_days),
      storage_location:
        productGroup?.default_storage_location ?? form.storage_location,
    });
  }

  function selectProductUnit(productUnitId: string) {
    const productUnit = productUnits.find(
      (unit) => String(unit.id) === productUnitId,
    );
    const conversion = defaultConversionForProductUnit(
      productUnit?.name ?? form.unit,
      form.serving_size,
      form.serving_unit,
    );
    onFormChange({
      ...form,
      product_unit_id: productUnitId,
      unit: productUnit?.name ?? form.unit,
      ...conversion,
    });
  }

  function submitProductGroupAndClose(event: FormEvent) {
    void onGroupSubmit(event);
    setProductGroupUiOpen(false);
  }

  function submitProductUnitAndClose(event: FormEvent) {
    void onUnitSubmit(event);
    setProductUnitUiOpen(false);
  }

  function toggleColumn(columnKey: InventoryColumnKey) {
    setVisibleColumnKeys((current) =>
      current.includes(columnKey)
        ? current.filter((key) => key !== columnKey)
        : [...current, columnKey],
    );
  }

  function readReceiptFileAsBase64(file: File) {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        const value = String(reader.result ?? "");
        resolve(value.includes(",") ? value.split(",")[1] : value);
      });
      reader.addEventListener("error", () =>
        reject(new Error("Kassenzettel konnte nicht gelesen werden")),
      );
      reader.readAsDataURL(file);
    });
  }

  function receiptPreviewItemToBookItem(
    item: ReceiptImportPreview["items"][number],
  ): ReceiptImportBookItem {
    const matchedFood = item.matched_food ?? null;
    return {
      source_index: item.source_index,
      raw_name: item.raw_name,
      name: matchedFood?.name ?? item.name,
      food_id: matchedFood?.id ?? null,
      quantity: formatFractionalQuantity(item.quantity),
      unit: item.unit,
      unit_price: toFormValue(item.unit_price),
      total_price: toFormValue(item.total_price),
      storage_location: matchedFood?.storage_location ?? "",
      book: item.status === "ready",
    };
  }

  function resetReceiptImport() {
    setReceiptImportFile(null);
    setReceiptPreview(null);
    setReceiptRows([]);
    setReceiptPurchaseDate(getLocalDate());
    setReceiptStorageLocation("");
    setReceiptImportMessage("");
  }

  async function submitReceiptPreview(event: FormEvent) {
    event.preventDefault();
    if (!receiptImportFile) {
      setReceiptImportMessage("Bitte zuerst einen PDF-Kassenzettel auswaehlen.");
      return;
    }

    try {
      setReceiptImportBusy(true);
      setReceiptImportMessage("");
      const contentBase64 = await readReceiptFileAsBase64(receiptImportFile);
      const preview = await onReceiptPreview(
        receiptImportFile.name,
        contentBase64,
      );
      setReceiptPreview(preview);
      setReceiptRows(preview.items.map(receiptPreviewItemToBookItem));
      setReceiptPurchaseDate(preview.receipt_date ?? getLocalDate());
      setReceiptImportMessage(
        `${preview.imported_count} bereit, ${preview.review_count} zur Korrektur, ${preview.ignored_count} ignoriert.`,
      );
    } catch (error) {
      setReceiptImportMessage(
        error instanceof Error ? error.message : "Kassenzettel konnte nicht gelesen werden.",
      );
    } finally {
      setReceiptImportBusy(false);
    }
  }

  function updateReceiptRow(
    sourceIndex: number,
    patch: Partial<ReceiptImportBookItem>,
  ) {
    setReceiptRows((current) =>
      current.map((row) =>
        row.source_index === sourceIndex ? { ...row, ...patch } : row,
      ),
    );
  }

  function selectReceiptFood(sourceIndex: number, foodId: string) {
    const food = foods.find((item) => String(item.id) === foodId) ?? null;
    if (!food) {
      updateReceiptRow(sourceIndex, { food_id: null });
      return;
    }

    const productUnit = productUnits.find(
      (unit) => unit.id === food.product_unit_id,
    );
    updateReceiptRow(sourceIndex, {
      food_id: food.id,
      name: food.name,
      unit: productUnit?.name ?? food.serving_unit,
      storage_location: food.storage_location ?? "",
      book: true,
    });
  }

  async function submitReceiptBooking() {
    const selectedRows = receiptRows.filter((row) => row.book);
    if (selectedRows.length === 0) {
      setReceiptImportMessage("Bitte mindestens eine Zeile zum Buchen auswaehlen.");
      return;
    }

    try {
      setReceiptImportBusy(true);
      const result = await onReceiptBook({
        purchase_date: receiptPurchaseDate,
        default_storage_location: receiptStorageLocation || null,
        items: receiptRows,
      });
      setReceiptImportMessage(
        `${result.booked_count} Artikel eingelagert, ${result.skipped_count} uebersprungen.`,
      );
      setReceiptRows((current) =>
        current.map((row) => ({ ...row, book: false })),
      );
    } catch (error) {
      setReceiptImportMessage(
        error instanceof Error ? error.message : "Kassenzettel konnte nicht gebucht werden.",
      );
    } finally {
      setReceiptImportBusy(false);
    }
  }

  function receiptStatusLabel(status: ReceiptImportStatus) {
    if (status === "ready") {
      return "Bereit";
    }
    if (status === "ignored") {
      return "Ignoriert";
    }
    return "Korrektur";
  }

  const selectedProductUnitId =
    form.product_unit_id ||
    String(productUnits.find((unit) => unit.name === form.unit)?.id ?? "");
  const selectedProductUnitName =
    productUnits.find((unit) => String(unit.id) === selectedProductUnitId)?.name ||
    form.unit ||
    "Einheit";
  const servingUnitOptions = Array.from(
    new Set(
      ["g", "kg", "ml", "l", form.serving_unit].filter(
        (unit): unit is string => Boolean(unit),
      ),
    ),
  );
  const inventoryEditorOpen = editingItemId !== null || inventoryCreateOpen;
  const inventoryEditorIsCreate = editingItemId === null;

  return (
    <div className="inventory-page-layout">
      <section className="section wide inventory-overview">
        <div className="inventory-overview-header">
          <h2>
            Bestandsübersicht{" "}
            <span>
              {displayedInventory.length} Produkte,{" "}
              {formatCurrency(totalInventoryValue)} Gesamtwert
            </span>
          </h2>
          <div className="inventory-overview-actions">
            <button
              className="button primary"
              onClick={onCreateInventoryItem}
              type="button"
            >
              <Plus size={16} />
              Bestand hinzufügen
            </button>
          </div>
        </div>

        <div className="inventory-warning-strip">
          <div className="inventory-alert-bars">
            <div className="inventory-alert expired">
              <strong>{expiredCount}</strong> Produkte sind abgelaufen
            </div>
            <div className="inventory-alert overdue">
              <strong>{overdueCount}</strong> Produkte sind überfaellig
            </div>
            <div className="inventory-alert due">
              <strong>{dueSoonCount}</strong> Produkte sind fällig innerhalb
              der nächsten 5 Tage
            </div>
            <div className="inventory-alert low">
              <strong>{lowStockCount}</strong>{" "}
              {lowStockCount === 1 ? "Produkt ist" : "Produkte sind"} unter
              Mindestbestand
            </div>
          </div>
          <div className="inventory-column-menu" ref={columnEditorRef}>
            <button
              className={`inventory-filter-toggle ${
                columnEditorOpen ? "active" : ""
              }`}
              onClick={() => setColumnEditorOpen((current) => !current)}
              title="Spalten bearbeiten"
              type="button"
            >
              <Filter size={18} />
            </button>
            {columnEditorOpen && (
              <div className="column-editor" aria-label="Spalten bearbeiten">
                <span className="column-editor-title">Spalten</span>
                <div className="column-toggle-list">
                  {inventoryColumnDefinitions.map((column) => {
                    const isVisible = visibleColumnKeys.includes(column.key);
                    return (
                      <label
                        className={`column-toggle ${
                          isVisible ? "active" : ""
                        }`}
                        key={column.key}
                      >
                        <input
                          checked={isVisible}
                          onChange={() => toggleColumn(column.key)}
                          type="checkbox"
                        />
                        {isVisible ? <Check size={14} /> : <Circle size={14} />}
                        <span>{column.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="inventory-filter-row">
          <label className="inventory-search-field">
            <Search size={18} />
            <input
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Suche"
              type="search"
              value={inventorySearch}
            />
          </label>
          <label className="inventory-select-field">
            <span>
              <Filter size={17} />
              Standort
            </span>
            <select
              onChange={(event) => setInventoryLocation(event.target.value)}
              value={inventoryLocation}
            >
              <option value="all">Alle</option>
              {locationOptions.map((location) => (
                <option key={location} value={location}>
                  {location}
                </option>
              ))}
            </select>
          </label>
          <label className="inventory-select-field">
            <span>
              <Filter size={17} />
              Produktgruppe
            </span>
            <select
              onChange={(event) => onCategoryChange(event.target.value)}
              value={inventoryCategory}
            >
              <option value="all">Alle</option>
              {categories.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </select>
          </label>
          <label className="inventory-select-field">
            <span>
              <Filter size={17} />
              Status
            </span>
            <select
              onChange={(event) => onStatusChange(event.target.value)}
              value={inventoryStatus}
            >
              <option value="all">Alle</option>
              <option value="ok">OK</option>
              <option value="low">Niedrig</option>
              <option value="expiring">Laeuft bald ab</option>
              <option value="expired">Abgelaufen</option>
            </select>
          </label>
        </div>

        <div className="inventory-table-wrap">
          <table className="inventory-table">
            <thead>
              <tr>
                <th className="sticky-column action-column">
                  <Eye size={16} />
                </th>
                <th className="sticky-column name-column">Produkt</th>
                <th className="sticky-column storage-column">Lagerort</th>
                {visibleColumns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayedInventory.length === 0 ? (
                <tr>
                  <td colSpan={visibleColumns.length + 3}>
                    <EmptyState label="Keine Artikel vorhanden" />
                  </td>
                </tr>
              ) : (
                displayedInventory.map((item) => (
                  <tr
                    className={editingItemId === item.id ? "is-editing" : ""}
                    key={item.id}
                  >
                    <td className="sticky-column action-column">
                      <div className="inventory-action-cluster">
                        <button
                          className="stock-action decrement"
                          onClick={() => onDecrease(item.id)}
                          title="Menge reduzieren"
                          type="button"
                        >
                          <Minus size={15} />
                        </button>
                        <button
                          className="stock-action increment"
                          onClick={() => onIncrease(item.id)}
                          title="Menge erhoehen"
                          type="button"
                        >
                          <Plus size={15} />
                        </button>
                        <button
                          className={`stock-action edit ${
                            editingItemId === item.id ? "active" : ""
                          }`}
                          onClick={() => onEdit(item)}
                          title="Bearbeiten"
                          type="button"
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          className="stock-action delete"
                          onClick={() => onDelete(item.id)}
                          title="Loeschen"
                          type="button"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                    <td className="sticky-column name-column">
                      <strong className="inventory-item-name">
                        <span aria-hidden="true" className="inventory-item-emoji">
                          {item.food?.emoji || item.emoji || defaultInventoryEmoji}
                        </span>
                        <span>{item.name}</span>
                      </strong>
                      <span className="muted-line">
                        {item.barcode || item.product_group?.name || item.category || ""}
                      </span>
                    </td>
                    <td className="sticky-column storage-column">
                      {item.storage_location || "-"}
                    </td>
                    {visibleColumns.map((column) => (
                      <td key={column.key}>{column.render(item)}</td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {receiptImportOpen && (
        <ModalBackdrop
          onClose={() => {
            resetReceiptImport();
            setReceiptImportOpen(false);
          }}
        >
          <section className="modal-panel receipt-import-modal">
            <div className="panel-header">
              <h2>Kassenzettel einlagern</h2>
              <button
                className="icon-button"
                onClick={() => {
                  resetReceiptImport();
                  setReceiptImportOpen(false);
                }}
                title="Schliessen"
                type="button"
              >
                <X size={16} />
              </button>
            </div>

            <form className="receipt-import-form" onSubmit={submitReceiptPreview}>
              <label>
                <span>REWE-PDF</span>
                <input
                  accept="application/pdf"
                  onChange={(event: ChangeEvent<HTMLInputElement>) =>
                    setReceiptImportFile(event.target.files?.[0] ?? null)
                  }
                  type="file"
                />
              </label>
              <DateInput
                label="Einlagerungsdatum"
                onChange={setReceiptPurchaseDate}
                required
                value={receiptPurchaseDate}
              />
              <label>
                <span>Standardlagerort</span>
                <select
                  onChange={(event) =>
                    setReceiptStorageLocation(event.target.value)
                  }
                  value={receiptStorageLocation}
                >
                  <option value="">Aus Lebensmittel/Produktgruppe</option>
                  {storageLocations.map((location) => (
                    <option key={location.id} value={location.name}>
                      {location.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button primary"
                disabled={receiptImportBusy}
                type="submit"
              >
                <Search size={16} />
                Vorschau
              </button>
            </form>

            {receiptImportMessage && (
              <div className="receipt-import-message">
                {receiptImportMessage}
              </div>
            )}

            {receiptPreview && (
              <div className="receipt-import-summary">
                <article>
                  <span>Markt</span>
                  <strong>{receiptPreview.store_name ?? "-"}</strong>
                </article>
                <article>
                  <span>Datum</span>
                  <strong>
                    {receiptPreview.receipt_date
                      ? formatDate(receiptPreview.receipt_date)
                      : "-"}
                  </strong>
                </article>
                <article>
                  <span>Summe</span>
                  <strong>
                    {receiptPreview.total === null ||
                    receiptPreview.total === undefined
                      ? "-"
                      : formatCurrency(receiptPreview.total)}
                  </strong>
                </article>
                <article>
                  <span>Korrektur</span>
                  <strong>{receiptPreview.review_count}</strong>
                </article>
              </div>
            )}

            {receiptRows.length > 0 && (
              <>
                <div className="receipt-import-table-wrap">
                  <table className="receipt-import-table">
                    <thead>
                      <tr>
                        <th>Buchen</th>
                        <th>Status</th>
                        <th>Bon</th>
                        <th>Lebensmittel</th>
                        <th>Menge</th>
                        <th>Einheit</th>
                        <th>Preis</th>
                        <th>Lagerort</th>
                      </tr>
                    </thead>
                    <tbody>
                      {receiptRows.map((row) => {
                        const previewItem = receiptPreview?.items.find(
                          (item) => item.source_index === row.source_index,
                        );
                        const status = previewItem?.status ?? "needs_review";
                        return (
                          <tr className={`receipt-row ${status}`} key={row.source_index}>
                            <td>
                              <label className="receipt-check">
                                <input
                                  checked={row.book}
                                  onChange={(event) =>
                                    updateReceiptRow(row.source_index, {
                                      book: event.target.checked,
                                    })
                                  }
                                  type="checkbox"
                                />
                                <span>{row.book ? "Ja" : "Nein"}</span>
                              </label>
                            </td>
                            <td>
                              <span className={`receipt-status ${status}`}>
                                {receiptStatusLabel(status)}
                              </span>
                              {previewItem?.review_reason && (
                                <small>{previewItem.review_reason}</small>
                              )}
                            </td>
                            <td>
                              <strong>{row.raw_name}</strong>
                              {previewItem?.suggestions.length ? (
                                <small>
                                  Vorschlag:{" "}
                                  {previewItem.suggestions
                                    .slice(0, 2)
                                    .map((suggestion) => suggestion.food.name)
                                    .join(", ")}
                                </small>
                              ) : null}
                            </td>
                            <td>
                              <select
                                onChange={(event) =>
                                  selectReceiptFood(
                                    row.source_index,
                                    event.target.value,
                                  )
                                }
                                value={row.food_id ?? ""}
                              >
                                <option value="">Neu / manuell</option>
                                {foods.map((food) => (
                                  <option key={food.id} value={food.id}>
                                    {formatFoodSuggestionLabel(food)}
                                  </option>
                                ))}
                              </select>
                              <input
                                onChange={(event) =>
                                  updateReceiptRow(row.source_index, {
                                    name: event.target.value,
                                  })
                                }
                                type="text"
                                value={row.name}
                              />
                            </td>
                            <td>
                              <input
                                inputMode="decimal"
                                onChange={(event) =>
                                  updateReceiptRow(row.source_index, {
                                    quantity: event.target.value,
                                  })
                                }
                                type="text"
                                value={String(row.quantity)}
                              />
                            </td>
                            <td>
                              <input
                                onChange={(event) =>
                                  updateReceiptRow(row.source_index, {
                                    unit: event.target.value,
                                  })
                                }
                                type="text"
                                value={row.unit}
                              />
                            </td>
                            <td>
                              <input
                                inputMode="decimal"
                                onChange={(event) =>
                                  updateReceiptRow(row.source_index, {
                                    unit_price: event.target.value,
                                  })
                                }
                                type="text"
                                value={String(row.unit_price ?? "")}
                              />
                              {row.total_price !== null &&
                                row.total_price !== undefined &&
                                row.total_price !== "" && (
                                  <small>Bon: {row.total_price} EUR</small>
                                )}
                            </td>
                            <td>
                              <select
                                onChange={(event) =>
                                  updateReceiptRow(row.source_index, {
                                    storage_location: event.target.value,
                                  })
                                }
                                value={row.storage_location ?? ""}
                              >
                                <option value="">Standard</option>
                                {storageLocations.map((location) => (
                                  <option key={location.id} value={location.name}>
                                    {location.name}
                                  </option>
                                ))}
                              </select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="form-actions receipt-import-actions">
                  <button
                    className="button primary"
                    disabled={
                      receiptImportBusy || receiptRows.every((row) => !row.book)
                    }
                    onClick={() => void submitReceiptBooking()}
                    type="button"
                  >
                    <CheckCircle2 size={16} />
                    Bestand buchen
                  </button>
                  <button
                    className="button secondary"
                    onClick={resetReceiptImport}
                    type="button"
                  >
                    <RefreshCw size={16} />
                    Zuruecksetzen
                  </button>
                </div>
              </>
            )}
          </section>
        </ModalBackdrop>
      )}

      {inventoryEditorOpen && (
        <ModalBackdrop onClose={onCancelEdit}>
          <section className="modal-panel inventory-edit-modal">
            <Panel
              title={
                inventoryEditorIsCreate
                  ? "Lebensmittel einlagern"
                  : "Bestand bearbeiten"
              }
            >
          <form className="form-grid" onSubmit={onSubmit}>
            <label>
              <span>Lebensmittel</span>
              <input
                list="inventory-food-options"
                onChange={(event) => searchInventoryFood(event.target.value)}
                placeholder="Lebensmittel suchen"
                required
                value={form.food_query}
              />
              <datalist id="inventory-food-options">
                {foodOptions.map((food) => (
                  <option key={food.id} value={formatFoodSuggestionLabel(food)} />
                ))}
              </datalist>
            </label>
            {selectedInventoryFood && (
              <>
                {!inventoryEditorIsCreate && (
                  <div className="shopping-inventory-summary">
                    <span>Umrechnung</span>
                    <strong>
                      {formatServingConversion(
                        selectedInventoryFoodUnit,
                        selectedInventoryFood,
                      )}
                    </strong>
                  </div>
                )}
                {selectedInventoryFood.brand && (
                  <div className="shopping-inventory-summary">
                    <span>Marke</span>
                    <strong>{selectedInventoryFood.brand}</strong>
                  </div>
                )}
              </>
            )}
            {!inventoryEditorIsCreate && (
              <div className="field-with-action">
                <label>
                  <span>Produktgruppe (optional)</span>
                  <select
                    onChange={(event) => selectProductGroup(event.target.value)}
                    value={form.product_group_id}
                  >
                    <option value="">Keine Produktgruppe</option>
                    {productGroups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button secondary field-action"
                  onClick={() => setProductGroupUiOpen(true)}
                  type="button"
                >
                  <Plus size={16} />
                  Gruppe
                </button>
              </div>
            )}
            <FractionNumberInput
              label="Menge"
              onChange={(quantity) => onFormChange({ ...form, quantity })}
              value={form.quantity}
            />
            <div className="field-with-action">
              <label>
                <span>Einheit</span>
                <select
                  onChange={(event) => selectProductUnit(event.target.value)}
                  required
                  value={selectedProductUnitId}
                >
                  <option value="">Einheit auswaehlen</option>
                  {productUnits.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button secondary field-action"
                onClick={() => setProductUnitUiOpen(true)}
                type="button"
              >
                <Plus size={16} />
                Einheit
              </button>
            </div>
            {!inventoryEditorIsCreate && (
              <FractionNumberInput
                label="Minimumstand (optional)"
                onChange={(minimum_quantity) =>
                  onFormChange({ ...form, minimum_quantity })
                }
                value={form.minimum_quantity}
              />
            )}
            <label>
              <span>Lagerort</span>
              <select
                onChange={(event) =>
                  onFormChange({ ...form, storage_location: event.target.value })
                }
                value={form.storage_location}
              >
                <option value="">Kein Lagerort</option>
                {storageLocationSelectOptions.map((location) => (
                  <option key={location} value={location}>
                    {location}
                  </option>
                ))}
              </select>
            </label>
            {!inventoryEditorIsCreate && (
              <TextInput
                label="Barcode (optional)"
                onChange={(barcode) => onFormChange({ ...form, barcode })}
                value={form.barcode}
              />
            )}
            <DateInput
              label="Einlagerungsdatum"
              onChange={(purchase_date) =>
                onFormChange({ ...form, purchase_date })
              }
              required
              value={form.purchase_date}
            />
            <NumberInput
              label="Haltbarkeit bis Ablauf (Tage)"
              min="0"
              onChange={(expiry_days) => onFormChange({ ...form, expiry_days })}
              required
              step="1"
              value={form.expiry_days}
            />
            <NumberInput
              label="Preis (optional)"
              onChange={(price) => onFormChange({ ...form, price })}
              value={form.price}
            />
            {!inventoryEditorIsCreate && (
              <div className="inline-field-pair">
                <NumberInput
                  label={`1 ${selectedProductUnitName} =`}
                  onChange={(serving_size) =>
                    onFormChange({ ...form, serving_size })
                  }
                  value={form.serving_size}
                />
                <label>
                  <span>Umrechnungseinheit</span>
                  <select
                    onChange={(event) =>
                      onFormChange({ ...form, serving_unit: event.target.value })
                    }
                    value={form.serving_unit}
                  >
                    {servingUnitOptions.map((unit) => (
                      <option key={unit} value={unit}>
                        {unit}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
            <NumberInput
              label="Kalorien / 100g"
              onChange={(calories_per_100g) =>
                onFormChange({ ...form, calories_per_100g })
              }
              value={form.calories_per_100g}
            />
            <NumberInput
              label="Protein / 100g"
              onChange={(protein_per_100g) =>
                onFormChange({ ...form, protein_per_100g })
              }
              value={form.protein_per_100g}
            />
            <NumberInput
              label="Fett / 100g"
              onChange={(fat_per_100g) =>
                onFormChange({ ...form, fat_per_100g })
              }
              value={form.fat_per_100g}
            />
            <NumberInput
              label="Kohlenhydrate / 100g"
              onChange={(carbs_per_100g) =>
                onFormChange({ ...form, carbs_per_100g })
              }
              value={form.carbs_per_100g}
            />
            <div className="form-actions">
              <button
                className="button primary"
                disabled={form.food_id === ""}
                type="submit"
              >
                {inventoryEditorIsCreate ? (
                  <Plus size={16} />
                ) : (
                  <Pencil size={16} />
                )}
                {inventoryEditorIsCreate ? "Einlagern" : "Speichern"}
              </button>
              <button
                className="button secondary"
                onClick={onCancelEdit}
                type="button"
              >
                <X size={16} />
                Abbrechen
              </button>
            </div>
          </form>
            </Panel>

        {productGroupUiOpen && (
          <ModalBackdrop onClose={() => setProductGroupUiOpen(false)}>
            <section className="modal-panel">
              <div className="panel-header">
                <h2>Produktgruppe anlegen</h2>
                <button
                  className="icon-button"
                  onClick={() => setProductGroupUiOpen(false)}
                  title="Schliessen"
                  type="button"
                >
                  <X size={16} />
                </button>
              </div>
              <form className="form-grid" onSubmit={submitProductGroupAndClose}>
                <TextInput
                  label="Produktgruppenname"
                  onChange={(name) =>
                    onGroupFormChange({ ...productGroupForm, name })
                  }
                  required
                  value={productGroupForm.name}
                />
                <NumberInput
                  label="Standardhaltbarkeit (Tage)"
                  min="0"
                  onChange={(default_expiry_days) =>
                    onGroupFormChange({
                      ...productGroupForm,
                      default_expiry_days,
                    })
                  }
                  step="1"
                  value={productGroupForm.default_expiry_days}
                />
                <TextInput
                  label="Standardlagerort"
                  onChange={(default_storage_location) =>
                    onGroupFormChange({
                      ...productGroupForm,
                      default_storage_location,
                    })
                  }
                  value={productGroupForm.default_storage_location}
                />
                <div className="form-actions">
                  <button className="button primary" type="submit">
                    <Plus size={16} />
                    Anlegen
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => setProductGroupUiOpen(false)}
                    type="button"
                  >
                    <X size={16} />
                    Abbrechen
                  </button>
                </div>
              </form>
              <div className="product-group-list">
                {productGroups.length === 0 ? (
                  <EmptyState label="Keine Produktgruppen vorhanden" />
                ) : (
                  productGroups.map((group) => (
                    <div className="product-group-row" key={group.id}>
                      <div>
                        <strong>{group.name}</strong>
                        <span className="muted-line">
                          {[
                            group.default_storage_location,
                            group.default_expiry_days === null ||
                            group.default_expiry_days === undefined
                              ? null
                              : `${formatNumber(group.default_expiry_days, 0)} Tage`,
                          ]
                            .filter((value) => value && value !== "-")
                            .join(" | ") || "-"}
                        </span>
                      </div>
                      <button
                        className="icon-button danger"
                        onClick={() => onGroupDelete(group.id)}
                        title="Produktgruppe loeschen"
                        type="button"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>
          </ModalBackdrop>
        )}

        {productUnitUiOpen && (
          <ModalBackdrop onClose={() => setProductUnitUiOpen(false)}>
            <section className="modal-panel">
              <div className="panel-header">
                <h2>Einheit anlegen</h2>
                <button
                  className="icon-button"
                  onClick={() => setProductUnitUiOpen(false)}
                  title="Schliessen"
                  type="button"
                >
                  <X size={16} />
                </button>
              </div>
              <form className="form-grid" onSubmit={submitProductUnitAndClose}>
                <TextInput
                  label="Einheitsname"
                  onChange={(name) =>
                    onUnitFormChange({ ...productUnitForm, name })
                  }
                  required
                  value={productUnitForm.name}
                />
                <div className="form-actions">
                  <button className="button primary" type="submit">
                    <Plus size={16} />
                    Anlegen
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => setProductUnitUiOpen(false)}
                    type="button"
                  >
                    <X size={16} />
                    Abbrechen
                  </button>
                </div>
              </form>
              <div className="product-group-list">
                {productUnits.length === 0 ? (
                  <EmptyState label="Keine Einheiten vorhanden" />
                ) : (
                  productUnits.map((unit) => (
                    <div className="product-group-row" key={unit.id}>
                      <div>
                        <strong>{unit.name}</strong>
                      </div>
                      <button
                        className="icon-button danger"
                        onClick={() => onUnitDelete(unit.id)}
                        title="Einheit loeschen"
                        type="button"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>
          </ModalBackdrop>
        )}
          </section>
        </ModalBackdrop>
      )}
    </div>
  );
}

const masterDataTabs: Array<{ id: MasterDataTab; label: string }> = [
  { id: "foods", label: "Lebensmittel" },
  { id: "locations", label: "Standorte" },
  { id: "units", label: "Mengeneinheiten" },
  { id: "groups", label: "Produktgruppen" },
];

function MasterDataPanel({
  activeTab,
  editingFoodId,
  editingProductGroupId,
  editingProductUnitId,
  editingStorageLocationId,
  foodForm,
  foods,
  onCancelEditingFood,
  onCancelEditingProductGroup,
  onCancelEditingProductUnit,
  onCancelEditingStorageLocation,
  onDeleteFood,
  onDeleteProductGroup,
  onDeleteProductUnit,
  onDeleteStorageLocation,
  onEditFood,
  onEditProductGroup,
  onEditProductUnit,
  onEditStorageLocation,
  onFoodFormChange,
  onFoodSubmit,
  onProductGroupFormChange,
  onProductGroupSubmit,
  onProductUnitFormChange,
  onProductUnitSubmit,
  onStoreFood,
  onStorageLocationFormChange,
  onStorageLocationSubmit,
  onTabChange,
  productGroupForm,
  productGroups,
  productUnitForm,
  productUnits,
  showTabs = true,
  storageLocationForm,
  storageLocations,
}: {
  activeTab: MasterDataTab;
  editingFoodId: number | null;
  editingProductGroupId: number | null;
  editingProductUnitId: number | null;
  editingStorageLocationId: number | null;
  foodForm: FoodForm;
  foods: Food[];
  onCancelEditingFood: () => void;
  onCancelEditingProductGroup: () => void;
  onCancelEditingProductUnit: () => void;
  onCancelEditingStorageLocation: () => void;
  onDeleteFood: (id: number) => void;
  onDeleteProductGroup: (id: number) => void;
  onDeleteProductUnit: (id: number) => void;
  onDeleteStorageLocation: (id: number) => void;
  onEditFood: (food: Food) => void;
  onEditProductGroup: (group: ProductGroup) => void;
  onEditProductUnit: (unit: ProductUnit) => void;
  onEditStorageLocation: (location: StorageLocation) => void;
  onFoodFormChange: (value: FoodForm) => void;
  onFoodSubmit: (event: FormEvent) => Promise<void> | void;
  onProductGroupFormChange: (value: ProductGroupForm) => void;
  onProductGroupSubmit: (event: FormEvent) => Promise<void> | void;
  onProductUnitFormChange: (value: ProductUnitForm) => void;
  onProductUnitSubmit: (event: FormEvent) => Promise<void> | void;
  onStoreFood: (food: Food) => void;
  onStorageLocationFormChange: (value: StorageLocationForm) => void;
  onStorageLocationSubmit: (event: FormEvent) => Promise<void> | void;
  onTabChange?: (tab: MasterDataTab) => void;
  productGroupForm: ProductGroupForm;
  productGroups: ProductGroup[];
  productUnitForm: ProductUnitForm;
  productUnits: ProductUnit[];
  showTabs?: boolean;
  storageLocationForm: StorageLocationForm;
  storageLocations: StorageLocation[];
}) {
  const [foodEditorOpen, setFoodEditorOpen] = useState(false);
  const [foodSearch, setFoodSearch] = useState("");
  const [foodProductGroupFilter, setFoodProductGroupFilter] = useState("all");
  const [foodStorageLocationFilter, setFoodStorageLocationFilter] =
    useState("all");
  const [locationEditorOpen, setLocationEditorOpen] = useState(false);
  const [productGroupEditorOpen, setProductGroupEditorOpen] = useState(false);
  const [productUnitEditorOpen, setProductUnitEditorOpen] = useState(false);
  const [foodBarcodePanelOpen, setFoodBarcodePanelOpen] = useState(false);
  const [foodBarcodeInput, setFoodBarcodeInput] = useState("");
  const [foodBarcodeBusy, setFoodBarcodeBusy] = useState(false);
  const [foodBarcodeStatus, setFoodBarcodeStatus] = useState("");
  const [foodCameraError, setFoodCameraError] = useState("");
  const [foodScannerActive, setFoodScannerActive] = useState(false);
  const foodBarcodeVideoRef = useRef<HTMLVideoElement | null>(null);
  const foodBarcodeStreamRef = useRef<MediaStream | null>(null);
  const foodBarcodeScanLoopRef = useRef<number | null>(null);
  const foodBarcodeScannerRunningRef = useRef(false);
  const productGroupById = useMemo(
    () => new Map(productGroups.map((group) => [group.id, group])),
    [productGroups],
  );
  const productUnitById = useMemo(
    () => new Map(productUnits.map((unit) => [unit.id, unit])),
    [productUnits],
  );
  const servingUnitOptions = Array.from(
    new Set(
      [
        "g",
        "kg",
        "ml",
        "l",
        foodForm.serving_unit,
      ].filter((unit): unit is string => Boolean(unit)),
    ),
  );
  const selectedFoodProductUnitName =
    foodForm.product_unit_id
      ? productUnitById.get(toNumber(foodForm.product_unit_id))?.name ?? "Einheit"
      : "Einheit";
  const foodStorageLocationOptions = useMemo(
    () =>
      Array.from(
        new Set(
          [
            ...storageLocations.map((location) => location.name),
            ...productGroups
              .map((group) => group.default_storage_location)
              .filter((location): location is string => Boolean(location)),
            ...foods
              .map((food) => food.storage_location)
              .filter((location): location is string => Boolean(location)),
            foodForm.storage_location,
          ].filter((location): location is string => Boolean(location)),
        ),
      ).sort((left, right) => left.localeCompare(right, "de")),
    [foodForm.storage_location, foods, productGroups, storageLocations],
  );

  function getFoodProductGroup(food: Food) {
    return food.product_group_id
      ? productGroupById.get(food.product_group_id) ?? null
      : null;
  }

  function getFoodStorageLocation(food: Food) {
    const group = getFoodProductGroup(food);
    return (
      food.storage_location?.trim() ||
      group?.default_storage_location?.trim() ||
      "Ohne Lagerort"
    );
  }

  function getFoodUnitName(food: Food) {
    return food.product_unit_id
      ? productUnitById.get(food.product_unit_id)?.name ?? food.serving_unit
      : food.serving_unit;
  }

  function selectFoodProductGroup(productGroupId: string) {
    const productGroup = productGroups.find(
      (group) => String(group.id) === productGroupId,
    );
    onFoodFormChange({
      ...foodForm,
      category: productGroup?.name ?? foodForm.category,
      product_group_id: productGroupId,
      storage_location:
        foodForm.storage_location ||
        productGroup?.default_storage_location ||
        "",
      expiry_days:
        foodForm.expiry_days ||
        toFormValue(productGroup?.default_expiry_days),
    });
  }

  function selectFoodProductUnit(productUnitId: string) {
    const productUnit = productUnits.find(
      (unit) => String(unit.id) === productUnitId,
    );
    const conversion = defaultConversionForProductUnit(
      productUnit?.name ?? selectedFoodProductUnitName,
      foodForm.serving_size,
      foodForm.serving_unit,
    );
    onFoodFormChange({
      ...foodForm,
      product_unit_id: productUnitId,
      ...conversion,
    });
  }

  function addFoodConversion() {
    onFoodFormChange({
      ...foodForm,
      conversions: [...foodForm.conversions, { quantity: "1", unit: "" }],
    });
  }

  function updateFoodConversion(
    index: number,
    patch: Partial<FoodConversionForm>,
  ) {
    onFoodFormChange({
      ...foodForm,
      conversions: foodForm.conversions.map((conversion, currentIndex) =>
        currentIndex === index ? { ...conversion, ...patch } : conversion,
      ),
    });
  }

  function removeFoodConversion(index: number) {
    onFoodFormChange({
      ...foodForm,
      conversions: foodForm.conversions.filter(
        (_conversion, currentIndex) => currentIndex !== index,
      ),
    });
  }

  function foodBarcodeDetector() {
    return (
      globalThis as typeof globalThis & {
        BarcodeDetector?: BarcodeDetectorConstructor;
      }
    ).BarcodeDetector;
  }

  function stopFoodBarcodeScanner() {
    foodBarcodeScannerRunningRef.current = false;
    if (foodBarcodeScanLoopRef.current !== null) {
      cancelAnimationFrame(foodBarcodeScanLoopRef.current);
      foodBarcodeScanLoopRef.current = null;
    }
    foodBarcodeStreamRef.current?.getTracks().forEach((track) => track.stop());
    foodBarcodeStreamRef.current = null;
    setFoodScannerActive(false);
  }

  function resetFoodBarcodePanel() {
    stopFoodBarcodeScanner();
    setFoodBarcodePanelOpen(false);
    setFoodBarcodeInput("");
    setFoodBarcodeStatus("");
    setFoodCameraError("");
  }

  function closeFoodEditor() {
    resetFoodBarcodePanel();
    setFoodEditorOpen(false);
  }

  function cancelFoodEditor() {
    onCancelEditingFood();
    closeFoodEditor();
  }

  function applyFoodBarcodePreview(result: FoodBarcodePreview) {
    onFoodFormChange({
      ...foodForm,
      name: result.name || foodForm.name,
      brand: result.brand ?? foodForm.brand,
      barcode: result.barcode,
      calories_per_100g: toFormValue(result.calories_per_100g),
      protein_per_100g: toFormValue(result.protein_per_100g),
      fat_per_100g: toFormValue(result.fat_per_100g),
      carbs_per_100g: toFormValue(result.carbs_per_100g),
    });
    setFoodBarcodeInput(result.barcode);
    setFoodBarcodeStatus(`${result.name} gefunden und ins Formular uebernommen.`);
    setFoodCameraError("");
  }

  async function lookupFoodBarcode(code: string) {
    const normalizedBarcode = code.replace(/\D/g, "");
    if (normalizedBarcode.length < 8) {
      setFoodBarcodeStatus("Bitte einen gueltigen EAN-Code eingeben.");
      return;
    }

    try {
      setFoodBarcodeBusy(true);
      setFoodBarcodeStatus("EAN wird gesucht...");
      const result = await previewFoodByBarcode(normalizedBarcode);
      applyFoodBarcodePreview(result);
    } catch (error) {
      setFoodBarcodeStatus(
        error instanceof Error
          ? error.message
          : "EAN konnte nicht gefunden werden.",
      );
    } finally {
      setFoodBarcodeBusy(false);
    }
  }

  async function startFoodBarcodeScanner() {
    const Detector = foodBarcodeDetector();
    if (!Detector) {
      setFoodCameraError(
        "Kamera-Scan wird von diesem Browser nicht unterstuetzt. EAN manuell eingeben.",
      );
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setFoodCameraError("Keine Kamera-Schnittstelle verfuegbar.");
      return;
    }

    try {
      setFoodCameraError("");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      foodBarcodeStreamRef.current = stream;
      if (foodBarcodeVideoRef.current) {
        foodBarcodeVideoRef.current.srcObject = stream;
        await foodBarcodeVideoRef.current.play();
      }
      const detector = new Detector({
        formats: ["ean_13", "ean_8", "upc_a", "upc_e"],
      });
      foodBarcodeScannerRunningRef.current = true;
      setFoodScannerActive(true);

      const scanFrame = async () => {
        if (!foodBarcodeScannerRunningRef.current || !foodBarcodeVideoRef.current) {
          return;
        }
        try {
          const codes = await detector.detect(foodBarcodeVideoRef.current);
          const rawValue = codes[0]?.rawValue;
          if (rawValue) {
            stopFoodBarcodeScanner();
            setFoodBarcodeInput(rawValue);
            await lookupFoodBarcode(rawValue);
            return;
          }
        } catch {
          setFoodCameraError("Barcode konnte im Kamerabild nicht gelesen werden.");
        }
        foodBarcodeScanLoopRef.current = requestAnimationFrame(scanFrame);
      };

      foodBarcodeScanLoopRef.current = requestAnimationFrame(scanFrame);
    } catch {
      setFoodCameraError("Kamera konnte nicht gestartet werden.");
      stopFoodBarcodeScanner();
    }
  }

  useEffect(() => () => stopFoodBarcodeScanner(), []);

  const filteredFoods = useMemo(() => {
    const searchTerm = foodSearch.trim().toLowerCase();
    return foods.filter((food) => {
      const group = getFoodProductGroup(food);
      const storageLocation = getFoodStorageLocation(food);
      const unitName = getFoodUnitName(food);
      const matchesSearch =
        searchTerm === "" ||
        [
          food.name,
          food.brand,
          food.category,
          group?.name,
          storageLocation,
          unitName,
        ]
          .filter(Boolean)
          .some((value) => value?.toLowerCase().includes(searchTerm));
      const matchesGroup =
        foodProductGroupFilter === "all" ||
        String(food.product_group_id ?? "") === foodProductGroupFilter;
      const matchesLocation =
        foodStorageLocationFilter === "all" ||
        storageLocation === foodStorageLocationFilter;

      return matchesSearch && matchesGroup && matchesLocation;
    });
  }, [
    foodProductGroupFilter,
    foodSearch,
    foodStorageLocationFilter,
    foods,
    productGroupById,
    productUnitById,
  ]);

  const groupedFoods = useMemo(() => {
    const groups = new Map<string, Food[]>();
    for (const food of filteredFoods) {
      const storageLocation = getFoodStorageLocation(food);
      groups.set(storageLocation, [...(groups.get(storageLocation) ?? []), food]);
    }

    return Array.from(groups.entries())
      .sort(([left], [right]) => left.localeCompare(right, "de"))
      .map(([storageLocation, groupFoods]) => ({
        foods: groupFoods.sort((left, right) =>
          left.name.localeCompare(right.name, "de"),
        ),
        storageLocation,
      }));
  }, [filteredFoods, productGroupById]);

  return (
    <div className="master-data-panel">
      {showTabs && (
        <div className="master-data-tabs" role="tablist">
          {masterDataTabs.map((tab) => (
            <button
              className={`master-data-tab ${activeTab === tab.id ? "active" : ""}`}
              key={tab.id}
              onClick={() => onTabChange?.(tab.id)}
              role="tab"
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {activeTab === "foods" && (
        <section className="food-master-view">
          <div className="food-master-header">
            <h3>Produkte</h3>
            <button
              className="button primary food-add-button"
              onClick={() => {
                onCancelEditingFood();
                resetFoodBarcodePanel();
                setFoodEditorOpen(true);
              }}
              type="button"
            >
              Hinzufügen
            </button>
          </div>

          <div className="food-master-filter-row">
            <label className="food-search-field">
              <Search size={18} />
              <input
                onChange={(event) => setFoodSearch(event.target.value)}
                placeholder="Suche"
                type="search"
                value={foodSearch}
              />
            </label>
            <label className="food-select-field">
              <span>
                <Filter size={17} />
                Produktgruppe
              </span>
              <select
                onChange={(event) =>
                  setFoodProductGroupFilter(event.target.value)
                }
                value={foodProductGroupFilter}
              >
                <option value="all">Alle</option>
                {productGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="food-select-field">
              <span>
                <Filter size={17} />
                Lagerort
              </span>
              <select
                onChange={(event) =>
                  setFoodStorageLocationFilter(event.target.value)
                }
                value={foodStorageLocationFilter}
              >
                <option value="all">Alle</option>
                {foodStorageLocationOptions.map((location) => (
                  <option key={location} value={location}>
                    {location}
                  </option>
                ))}
                <option value="Ohne Lagerort">Ohne Lagerort</option>
              </select>
            </label>
          </div>

          <div className="food-table-wrap">
            <table className="food-master-table">
              <thead>
                <tr>
                  <th className="food-action-heading">
                    <Eye size={16} />
                  </th>
                  <th>Name</th>
                  <th>Lagerort</th>
                  <th>Mindestbestand</th>
                  <th>Umrechnung</th>
                  <th>Produktgruppe</th>
                  <th>Marke</th>
                </tr>
              </thead>
              <tbody>
                {groupedFoods.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState label="Keine Lebensmittel vorhanden" />
                    </td>
                  </tr>
                ) : (
                  groupedFoods.map((group) => [
                    <tr
                      className="food-location-group-row"
                      key={`${group.storageLocation}-heading`}
                    >
                      <td colSpan={7}>{group.storageLocation}</td>
                    </tr>,
                    ...group.foods.map((food) => {
                      const productGroup = getFoodProductGroup(food);
                      const storageLocation = getFoodStorageLocation(food);
                      return (
                        <tr key={food.id}>
                          <td className="food-actions-cell">
                            <button
                              className="food-action-button store"
                              onClick={() => onStoreFood(food)}
                              title="Lebensmittel einlagern"
                              type="button"
                            >
                              <Plus size={16} />
                            </button>
                            <button
                              className="food-action-button edit"
                              onClick={() => {
                                onEditFood(food);
                                resetFoodBarcodePanel();
                                setFoodEditorOpen(true);
                              }}
                              title="Lebensmittel bearbeiten"
                              type="button"
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              className="food-action-button delete"
                              onClick={() => onDeleteFood(food.id)}
                              title="Lebensmittel löschen"
                              type="button"
                            >
                              <Trash2 size={16} />
                            </button>
                          </td>
                          <td>
                            <span className="food-name-with-emoji">
                              <span aria-hidden="true">{food.emoji || defaultFoodEmoji}</span>
                              <span>{food.name}</span>
                            </span>
                          </td>
                          <td>{storageLocation}</td>
                          <td>{formatFractionalQuantity(food.minimum_quantity ?? 0)}</td>
                          <td>{formatServingConversion(getFoodUnitName(food), food)}</td>
                          <td>{productGroup?.name ?? food.category ?? "-"}</td>
                          <td>{food.brand ?? "-"}</td>
                        </tr>
                      );
                    }),
                  ])
                )}
              </tbody>
            </table>
          </div>

          {foodEditorOpen && (
            <ModalBackdrop onClose={cancelFoodEditor}>
              <section className="modal-panel food-editor-modal">
                <div className="panel-header">
                  <h2>
                    {editingFoodId === null
                      ? "Lebensmittel hinzufügen"
                      : "Lebensmittel bearbeiten"}
                  </h2>
                  <button
                    className="icon-button"
                    onClick={cancelFoodEditor}
                    title="Schliessen"
                    type="button"
                  >
                    <X size={16} />
                  </button>
                </div>
                <form
                  className="master-data-form"
                  onSubmit={(event) => {
                    void Promise.resolve(onFoodSubmit(event)).then(() =>
                      closeFoodEditor(),
                    );
                  }}
                >
                  <div className="food-barcode-tools">
                    <button
                      className={`button secondary ${
                        foodBarcodePanelOpen ? "active" : ""
                      }`}
                      onClick={() => {
                        if (foodBarcodePanelOpen) {
                          resetFoodBarcodePanel();
                        } else {
                          setFoodBarcodePanelOpen(true);
                          setFoodBarcodeStatus("");
                          setFoodCameraError("");
                        }
                      }}
                      type="button"
                    >
                      <ScanBarcode size={16} />
                      EAN scannen
                    </button>
                    {foodBarcodeStatus && (
                      <span className="food-barcode-inline-status">
                        {foodBarcodeStatus}
                      </span>
                    )}
                  </div>
                  {foodBarcodePanelOpen && (
                    <div className="nutrition-barcode-panel food-barcode-panel">
                      <div className="nutrition-barcode-panel-head">
                        <div>
                          <strong>EAN importieren</strong>
                          <span>Name, Marke und Nährwerte übernehmen</span>
                        </div>
                        <button
                          className="icon-button compact"
                          onClick={resetFoodBarcodePanel}
                          title="EAN-Import schliessen"
                          type="button"
                        >
                          <X size={15} />
                        </button>
                      </div>
                      <div className="nutrition-camera-frame">
                        <video
                          muted
                          playsInline
                          ref={foodBarcodeVideoRef}
                        />
                        {!foodScannerActive && (
                          <button
                            className="button secondary"
                            disabled={foodBarcodeBusy}
                            onClick={() => void startFoodBarcodeScanner()}
                            type="button"
                          >
                            <Camera size={16} />
                            Kamera starten
                          </button>
                        )}
                        {foodScannerActive && (
                          <button
                            className="button secondary"
                            onClick={stopFoodBarcodeScanner}
                            type="button"
                          >
                            <X size={16} />
                            Kamera stoppen
                          </button>
                        )}
                      </div>
                      <div className="nutrition-barcode-form food-barcode-form">
                        <label>
                          <span>EAN-Code</span>
                          <input
                            inputMode="numeric"
                            onChange={(event) =>
                              setFoodBarcodeInput(event.target.value)
                            }
                            onKeyDown={(event) => {
                              if (event.key === "Enter") {
                                event.preventDefault();
                                void lookupFoodBarcode(foodBarcodeInput);
                              }
                            }}
                            placeholder="z.B. 7613035614611"
                            value={foodBarcodeInput}
                          />
                        </label>
                        <button
                          className="button primary"
                          disabled={foodBarcodeBusy}
                          onClick={() => void lookupFoodBarcode(foodBarcodeInput)}
                          type="button"
                        >
                          {foodBarcodeBusy ? "Suche" : "Übernehmen"}
                        </button>
                      </div>
                      {(foodBarcodeStatus || foodCameraError) && (
                        <div
                          className={`nutrition-barcode-message ${
                            foodCameraError ? "error" : ""
                          }`}
                        >
                          {foodCameraError || foodBarcodeStatus}
                        </div>
                      )}
                    </div>
                  )}
                  <TextInput
                    label="Name"
                    onChange={(name) => onFoodFormChange({ ...foodForm, name })}
                    required
                    value={foodForm.name}
                  />
                  <TextInput
                    label="Emoji"
                    maxLength={32}
                    onChange={(emoji) =>
                      onFoodFormChange({ ...foodForm, emoji })
                    }
                    value={foodForm.emoji}
                  />
                  <TextInput
                    label="Markenname (optional)"
                    onChange={(brand) =>
                      onFoodFormChange({ ...foodForm, brand })
                    }
                    value={foodForm.brand}
                  />
                  <label>
                    <span>Produktgruppe (optional)</span>
                    <select
                      onChange={(event) =>
                        selectFoodProductGroup(event.target.value)
                      }
                      value={foodForm.product_group_id}
                    >
                      <option value="">Keine</option>
                      {productGroups.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Einheit</span>
                    <select
                      onChange={(event) =>
                        selectFoodProductUnit(event.target.value)
                      }
                      required
                      value={foodForm.product_unit_id}
                    >
                      <option value="">Einheit auswaehlen</option>
                      {productUnits.map((unit) => (
                        <option key={unit.id} value={unit.id}>
                          {unit.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <FractionNumberInput
                    label="Minimumstand (optional)"
                    onChange={(minimum_quantity) =>
                      onFoodFormChange({ ...foodForm, minimum_quantity })
                    }
                    value={foodForm.minimum_quantity}
                  />
                  <label>
                    <span>Lagerort</span>
                    <select
                      onChange={(event) =>
                        onFoodFormChange({
                          ...foodForm,
                          storage_location: event.target.value,
                        })
                      }
                      value={foodForm.storage_location}
                    >
                      <option value="">Ohne Lagerort</option>
                      {foodStorageLocationOptions.map((location) => (
                        <option key={location} value={location}>
                          {location}
                        </option>
                      ))}
                    </select>
                  </label>
                  <TextInput
                    label="Barcode (optional)"
                    onChange={(barcode) =>
                      onFoodFormChange({ ...foodForm, barcode })
                    }
                    value={foodForm.barcode}
                  />
                  <DateInput
                    label="Einlagerungsdatum"
                    onChange={(purchase_date) =>
                      onFoodFormChange({ ...foodForm, purchase_date })
                    }
                    required
                    value={foodForm.purchase_date}
                  />
                  <NumberInput
                    label="Haltbarkeit bis Ablauf (Tage)"
                    min="0"
                    onChange={(expiry_days) =>
                      onFoodFormChange({ ...foodForm, expiry_days })
                    }
                    required
                    step="1"
                    value={foodForm.expiry_days}
                  />
                  <NumberInput
                    label="Preis (optional)"
                    onChange={(price) =>
                      onFoodFormChange({ ...foodForm, price })
                    }
                    value={foodForm.price}
                  />
                  <div className="inline-field-pair">
                    <NumberInput
                      label={`1 ${selectedFoodProductUnitName} =`}
                      onChange={(serving_size) =>
                        onFoodFormChange({ ...foodForm, serving_size })
                      }
                      value={foodForm.serving_size}
                    />
                    <label>
                      <span>Umrechnungseinheit</span>
                      <select
                        onChange={(event) =>
                          onFoodFormChange({
                            ...foodForm,
                            serving_unit: event.target.value,
                          })
                        }
                        value={foodForm.serving_unit}
                      >
                        {servingUnitOptions.map((unit) => (
                          <option key={unit} value={unit}>
                            {unit}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="food-conversion-editor">
                    <div className="food-conversion-head">
                      <span>Weitere Umrechnungen</span>
                      <button
                        className="icon-button compact"
                        onClick={addFoodConversion}
                        title="Umrechnung hinzufuegen"
                        type="button"
                      >
                        <Plus size={15} />
                      </button>
                    </div>
                    {foodForm.conversions.length === 0 ? (
                      <div className="food-conversion-empty">Keine weiteren Umrechnungen</div>
                    ) : (
                      foodForm.conversions.map((conversion, index) => (
                        <div className="food-conversion-row" key={index}>
                          <NumberInput
                            label={`1 ${selectedFoodProductUnitName} =`}
                            onChange={(quantity) =>
                              updateFoodConversion(index, { quantity })
                            }
                            value={conversion.quantity}
                          />
                          <TextInput
                            label="Einheit"
                            onChange={(unit) => updateFoodConversion(index, { unit })}
                            value={conversion.unit}
                          />
                          <button
                            className="icon-button danger compact"
                            onClick={() => removeFoodConversion(index)}
                            title="Umrechnung loeschen"
                            type="button"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  <div className="master-data-number-grid">
                    <NumberInput
                      label="Kalorien / 100g"
                      onChange={(calories_per_100g) =>
                        onFoodFormChange({ ...foodForm, calories_per_100g })
                      }
                      value={foodForm.calories_per_100g}
                    />
                    <NumberInput
                      label="Protein / 100g"
                      onChange={(protein_per_100g) =>
                        onFoodFormChange({ ...foodForm, protein_per_100g })
                      }
                      value={foodForm.protein_per_100g}
                    />
                    <NumberInput
                      label="Fett / 100g"
                      onChange={(fat_per_100g) =>
                        onFoodFormChange({ ...foodForm, fat_per_100g })
                      }
                      value={foodForm.fat_per_100g}
                    />
                    <NumberInput
                      label="Kohlenhydrate / 100g"
                      onChange={(carbs_per_100g) =>
                        onFoodFormChange({ ...foodForm, carbs_per_100g })
                      }
                      value={foodForm.carbs_per_100g}
                    />
                  </div>
                  <MasterDataFormActions
                    editing={editingFoodId !== null}
                    onCancel={cancelFoodEditor}
                  />
                </form>
              </section>
            </ModalBackdrop>
          )}
        </section>
      )}

      {activeTab === "locations" && (
        <section className="location-master-view">
          <div className="location-master-header">
            <h3>Standorte</h3>
            <button
              className="button primary location-add-button"
              onClick={() => {
                onCancelEditingStorageLocation();
                setLocationEditorOpen(true);
              }}
              type="button"
            >
              Hinzufügen
            </button>
          </div>

          <div className="location-table-wrap">
            <table className="location-master-table">
              <thead>
                <tr>
                  <th className="location-action-heading">
                    <Eye size={16} />
                  </th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {storageLocations.length === 0 ? (
                  <tr>
                    <td colSpan={2}>
                      <EmptyState label="Keine Standorte vorhanden" />
                    </td>
                  </tr>
                ) : (
                  storageLocations.map((location) => (
                    <tr key={location.id}>
                      <td className="location-actions-cell">
                        <button
                          className="location-action-button edit"
                          onClick={() => {
                            onEditStorageLocation(location);
                            setLocationEditorOpen(true);
                          }}
                          title="Standort bearbeiten"
                          type="button"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          className="location-action-button delete"
                          onClick={() => onDeleteStorageLocation(location.id)}
                          title="Standort löschen"
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                      <td>{location.name}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {locationEditorOpen && (
            <ModalBackdrop
              onClose={() => {
                onCancelEditingStorageLocation();
                setLocationEditorOpen(false);
              }}
            >
              <section className="modal-panel">
                <div className="panel-header">
                  <h2>
                    {editingStorageLocationId === null
                      ? "Standort hinzufügen"
                      : "Standort bearbeiten"}
                  </h2>
                  <button
                    className="icon-button"
                    onClick={() => {
                      onCancelEditingStorageLocation();
                      setLocationEditorOpen(false);
                    }}
                    title="Schliessen"
                    type="button"
                  >
                    <X size={16} />
                  </button>
                </div>
                <form
                  className="master-data-form"
                  onSubmit={(event) => {
                    void Promise.resolve(onStorageLocationSubmit(event)).then(
                      () => setLocationEditorOpen(false),
                    );
                  }}
                >
                  <TextInput
                    label="Name"
                    onChange={(name) =>
                      onStorageLocationFormChange({
                        ...storageLocationForm,
                        name,
                      })
                    }
                    required
                    value={storageLocationForm.name}
                  />
                  <MasterDataFormActions
                    editing={editingStorageLocationId !== null}
                    onCancel={() => {
                      onCancelEditingStorageLocation();
                      setLocationEditorOpen(false);
                    }}
                  />
                </form>
              </section>
            </ModalBackdrop>
          )}
        </section>
      )}

      {activeTab === "units" && (
        <section className="unit-master-view">
          <div className="unit-master-header">
            <h3>Mengeneinheiten</h3>
            <button
              className="button primary unit-add-button"
              onClick={() => {
                onCancelEditingProductUnit();
                setProductUnitEditorOpen(true);
              }}
              type="button"
            >
              Hinzufügen
            </button>
          </div>

          <div className="unit-table-wrap">
            <table className="unit-master-table">
              <thead>
                <tr>
                  <th className="unit-action-heading">
                    <Eye size={16} />
                  </th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {productUnits.length === 0 ? (
                  <tr>
                    <td colSpan={2}>
                      <EmptyState label="Keine Mengeneinheiten vorhanden" />
                    </td>
                  </tr>
                ) : (
                  productUnits.map((unit) => (
                    <tr key={unit.id}>
                      <td className="unit-actions-cell">
                        <button
                          className="unit-action-button edit"
                          onClick={() => {
                            onEditProductUnit(unit);
                            setProductUnitEditorOpen(true);
                          }}
                          title="Mengeneinheit bearbeiten"
                          type="button"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          className="unit-action-button delete"
                          onClick={() => onDeleteProductUnit(unit.id)}
                          title="Mengeneinheit löschen"
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                      <td>{unit.name}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {productUnitEditorOpen && (
            <ModalBackdrop
              onClose={() => {
                onCancelEditingProductUnit();
                setProductUnitEditorOpen(false);
              }}
            >
              <section className="modal-panel">
                <div className="panel-header">
                  <h2>
                    {editingProductUnitId === null
                      ? "Mengeneinheit hinzufügen"
                      : "Mengeneinheit bearbeiten"}
                  </h2>
                  <button
                    className="icon-button"
                    onClick={() => {
                      onCancelEditingProductUnit();
                      setProductUnitEditorOpen(false);
                    }}
                    title="Schliessen"
                    type="button"
                  >
                    <X size={16} />
                  </button>
                </div>
                <form
                  className="master-data-form"
                  onSubmit={(event) => {
                    void Promise.resolve(onProductUnitSubmit(event)).then(() =>
                      setProductUnitEditorOpen(false),
                    );
                  }}
                >
                  <TextInput
                    label="Name"
                    onChange={(name) =>
                      onProductUnitFormChange({ ...productUnitForm, name })
                    }
                    required
                    value={productUnitForm.name}
                  />
                  <MasterDataFormActions
                    editing={editingProductUnitId !== null}
                    onCancel={() => {
                      onCancelEditingProductUnit();
                      setProductUnitEditorOpen(false);
                    }}
                  />
                </form>
              </section>
            </ModalBackdrop>
          )}
        </section>
      )}

      {activeTab === "groups" && (
        <section className="group-master-view">
          <div className="group-master-header">
            <h3>Produktgruppen</h3>
            <button
              className="button primary group-add-button"
              onClick={() => {
                onCancelEditingProductGroup();
                setProductGroupEditorOpen(true);
              }}
              type="button"
            >
              Hinzufügen
            </button>
          </div>

          <div className="group-table-wrap">
            <table className="group-master-table">
              <thead>
                <tr>
                  <th className="group-action-heading">
                    <Eye size={16} />
                  </th>
                  <th>Name</th>
                  <th>Standardstandort</th>
                  <th>Standardhaltbarkeit</th>
                </tr>
              </thead>
              <tbody>
                {productGroups.length === 0 ? (
                  <tr>
                    <td colSpan={4}>
                      <EmptyState label="Keine Produktgruppen vorhanden" />
                    </td>
                  </tr>
                ) : (
                  productGroups.map((group) => (
                    <tr key={group.id}>
                      <td className="group-actions-cell">
                        <button
                          className="group-action-button edit"
                          onClick={() => {
                            onEditProductGroup(group);
                            setProductGroupEditorOpen(true);
                          }}
                          title="Produktgruppe bearbeiten"
                          type="button"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          className="group-action-button delete"
                          onClick={() => onDeleteProductGroup(group.id)}
                          title="Produktgruppe löschen"
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </td>
                      <td>{group.name}</td>
                      <td>{group.default_storage_location ?? "-"}</td>
                      <td>
                        {group.default_expiry_days === null ||
                        group.default_expiry_days === undefined
                          ? "-"
                          : `${formatNumber(group.default_expiry_days, 0)} Tage`}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {productGroupEditorOpen && (
            <ModalBackdrop
              onClose={() => {
                onCancelEditingProductGroup();
                setProductGroupEditorOpen(false);
              }}
            >
              <section className="modal-panel">
                <div className="panel-header">
                  <h2>
                    {editingProductGroupId === null
                      ? "Produktgruppe hinzufügen"
                      : "Produktgruppe bearbeiten"}
                  </h2>
                  <button
                    className="icon-button"
                    onClick={() => {
                      onCancelEditingProductGroup();
                      setProductGroupEditorOpen(false);
                    }}
                    title="Schliessen"
                    type="button"
                  >
                    <X size={16} />
                  </button>
                </div>
                <form
                  className="master-data-form"
                  onSubmit={(event) => {
                    void Promise.resolve(onProductGroupSubmit(event)).then(
                      () => setProductGroupEditorOpen(false),
                    );
                  }}
                >
                  <TextInput
                    label="Name"
                    onChange={(name) =>
                      onProductGroupFormChange({ ...productGroupForm, name })
                    }
                    required
                    value={productGroupForm.name}
                  />
                  <label>
                    <span>Standardstandort</span>
                    <select
                      onChange={(event) =>
                        onProductGroupFormChange({
                          ...productGroupForm,
                          default_storage_location: event.target.value,
                        })
                      }
                      value={productGroupForm.default_storage_location}
                    >
                      <option value="">Keiner</option>
                      {storageLocations.map((location) => (
                        <option key={location.id} value={location.name}>
                          {location.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <NumberInput
                    label="Standardhaltbarkeit"
                    min="0"
                    onChange={(default_expiry_days) =>
                      onProductGroupFormChange({
                        ...productGroupForm,
                        default_expiry_days,
                      })
                    }
                    step="1"
                    value={productGroupForm.default_expiry_days}
                  />
                  <MasterDataFormActions
                    editing={editingProductGroupId !== null}
                    onCancel={() => {
                      onCancelEditingProductGroup();
                      setProductGroupEditorOpen(false);
                    }}
                  />
                </form>
              </section>
            </ModalBackdrop>
          )}
        </section>
      )}
    </div>
  );
}

function MasterDataFormActions({
  editing,
  onCancel,
}: {
  editing: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="form-actions">
      <button className="button primary" type="submit">
        {editing ? <Pencil size={16} /> : <Plus size={16} />}
        {editing ? "Speichern" : "Anlegen"}
      </button>
      {editing && (
        <button className="button secondary" onClick={onCancel} type="button">
          <X size={16} />
          Abbrechen
        </button>
      )}
    </div>
  );
}

function MasterDataRow({
  detail,
  editing,
  onDelete,
  onEdit,
  title,
}: {
  detail?: string;
  editing: boolean;
  onDelete: () => void;
  onEdit: () => void;
  title: string;
}) {
  return (
    <div className={`master-data-row ${editing ? "editing" : ""}`}>
      <div>
        <strong>{title}</strong>
        {detail && <span>{detail}</span>}
      </div>
      <div className="icon-actions">
        <button
          className={`icon-button ${editing ? "active" : ""}`}
          onClick={onEdit}
          title="Bearbeiten"
          type="button"
        >
          <Pencil size={16} />
        </button>
        <button
          className="icon-button danger"
          onClick={onDelete}
          title="Loeschen"
          type="button"
        >
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}

function formatFoodSuggestionLabel(food: Food) {
  return [food.name, food.brand, food.storage_location]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(" | ");
}

function updateIngredientFoodSearch(
  foods: Food[],
  form: RecipeIngredientForm,
  query: string,
  productUnits: ProductUnit[] = [],
) {
  const normalizedQuery = query.trim().toLowerCase();
  const selectedFood = foods.find((food) => {
    const label = formatFoodSuggestionLabel(food).toLowerCase();
    return label === normalizedQuery || food.name.toLowerCase() === normalizedQuery;
  });

  return {
    ...form,
    food_id: selectedFood ? String(selectedFood.id) : "",
    food_query: query,
    unit: selectedFood
      ? selectedFood.serving_unit ||
        productUnitNameForFood(selectedFood, productUnits) ||
        form.unit ||
        "g"
      : form.unit || "g",
  };
}

function findFoodByIngredientForm(foods: Food[], form: RecipeIngredientForm) {
  const foodId = optionalNumber(form.food_id);
  if (foodId !== null && foodId > 0) {
    const selectedFood = foods.find((food) => food.id === foodId);
    if (selectedFood) {
      return selectedFood;
    }
  }

  const normalizedQuery = form.food_query.trim().toLowerCase();
  if (!normalizedQuery) {
    return null;
  }

  return (
    foods.find((food) => {
      const label = formatFoodSuggestionLabel(food).toLowerCase();
      return label === normalizedQuery || food.name.toLowerCase() === normalizedQuery;
    }) ?? null
  );
}

type RecipeIngredientPreview = {
  food: Pick<
    Food,
    | "calories_per_100g"
    | "protein_per_100g"
    | "fat_per_100g"
    | "carbs_per_100g"
    | "product_unit_id"
    | "serving_size"
    | "serving_unit"
    | "conversions"
  >;
  quantity: number;
  unit: string;
};

const gramUnits = new Set(["g", "gram", "grams", "gramm"]);
const kilogramUnits = new Set(["kg", "kilogram", "kilograms", "kilogramm"]);
const milligramUnits = new Set(["mg", "milligram", "milligrams", "milligramm"]);
const milliliterUnits = new Set(["ml", "milliliter", "milliliters"]);
const literUnits = new Set(["l", "liter", "liters"]);
const ounceUnits = new Set(["oz", "ounce", "ounces"]);
const poundUnits = new Set(["lb", "lbs", "pound", "pounds"]);
const servingAliasUnits = new Set(["serving", "servings", "portion", "portions"]);

function normalizedUnitName(unit?: string | null) {
  return (unit ?? "").trim().toLowerCase();
}

function unitQuantityToGrams(quantity: number, unit?: string | null) {
  const normalizedUnit = normalizedUnitName(unit);
  if (gramUnits.has(normalizedUnit)) {
    return quantity;
  }
  if (kilogramUnits.has(normalizedUnit)) {
    return quantity * 1000;
  }
  if (milligramUnits.has(normalizedUnit)) {
    return quantity / 1000;
  }
  if (milliliterUnits.has(normalizedUnit)) {
    return quantity;
  }
  if (literUnits.has(normalizedUnit)) {
    return quantity * 1000;
  }
  if (ounceUnits.has(normalizedUnit)) {
    return quantity * 28.3495;
  }
  if (poundUnits.has(normalizedUnit)) {
    return quantity * 453.592;
  }
  return null;
}

function productUnitNameForFood(
  food: Pick<Food, "product_unit_id" | "serving_unit">,
  productUnits: ProductUnit[] = [],
) {
  return food.product_unit_id
    ? productUnits.find((unit) => unit.id === food.product_unit_id)?.name ??
        food.serving_unit
    : food.serving_unit;
}

function foodUnitOptions(
  food:
    | (Pick<Food, "product_unit_id" | "serving_unit" | "conversions">)
    | null
    | undefined,
  productUnits: ProductUnit[] = [],
  currentUnit = "",
) {
  const units = ["g", "kg", "ml", "l"];
  if (food) {
    units.push(productUnitNameForFood(food, productUnits));
    units.push(food.serving_unit);
    units.push(...(food.conversions ?? []).map((conversion) => conversion.unit));
  }
  units.push(currentUnit);

  const seen = new Set<string>();
  return units.filter((unit) => {
    const normalizedUnit = normalizedUnitName(unit);
    if (!normalizedUnit || seen.has(normalizedUnit)) {
      return false;
    }
    seen.add(normalizedUnit);
    return true;
  });
}

function foodServingSizeInGrams(
  food: Pick<Food, "serving_size" | "serving_unit">,
) {
  return (
    unitQuantityToGrams(
      normalizeFractionalQuantityValue(food.serving_size),
      food.serving_unit,
    ) ?? normalizeFractionalQuantityValue(food.serving_size)
  );
}

function foodConversionQuantityForUnit(
  food: { conversions?: Array<Pick<Food["conversions"][number], "quantity" | "unit">> },
  unit: string,
) {
  const normalizedUnit = normalizedUnitName(unit);
  const conversion = (food.conversions ?? []).find(
    (item) => normalizedUnitName(item.unit) === normalizedUnit,
  );
  if (!conversion || conversion.quantity <= 0) {
    return null;
  }
  return normalizeFractionalQuantityValue(conversion.quantity);
}

function foodQuantityToGrams(
  food: Pick<
    Food,
    "product_unit_id" | "serving_size" | "serving_unit" | "conversions"
  >,
  quantity: number,
  unit: string,
  productUnits: ProductUnit[] = [],
) {
  const normalizedQuantity = normalizeFractionalQuantityValue(quantity);
  const directGrams = unitQuantityToGrams(normalizedQuantity, unit);
  if (directGrams !== null) {
    return directGrams;
  }

  const normalizedUnit = normalizedUnitName(unit);
  const servingSize = foodServingSizeInGrams(food);
  const conversionQuantity = foodConversionQuantityForUnit(food, unit);
  if (conversionQuantity !== null && servingSize > 0) {
    return (normalizedQuantity * servingSize) / conversionQuantity;
  }

  const normalizedProductUnit = normalizedUnitName(
    productUnitNameForFood(food, productUnits),
  );
  if (
    servingAliasUnits.has(normalizedUnit) ||
    (normalizedProductUnit && normalizedUnit === normalizedProductUnit)
  ) {
    return servingSize * normalizedQuantity;
  }

  return normalizedQuantity;
}

function foodQuantityFromGrams(
  food: Pick<
    Food,
    "product_unit_id" | "serving_size" | "serving_unit" | "conversions"
  >,
  grams: number,
  unit: string,
  productUnits: ProductUnit[] = [],
) {
  const safeGrams = Math.max(grams, 0);
  const normalizedUnit = normalizedUnitName(unit);
  if (gramUnits.has(normalizedUnit)) {
    return safeGrams;
  }
  if (kilogramUnits.has(normalizedUnit)) {
    return safeGrams / 1000;
  }
  if (milligramUnits.has(normalizedUnit)) {
    return safeGrams * 1000;
  }
  if (milliliterUnits.has(normalizedUnit)) {
    return safeGrams;
  }
  if (literUnits.has(normalizedUnit)) {
    return safeGrams / 1000;
  }
  if (ounceUnits.has(normalizedUnit)) {
    return safeGrams / 28.3495;
  }
  if (poundUnits.has(normalizedUnit)) {
    return safeGrams / 453.592;
  }

  const servingSize = foodServingSizeInGrams(food);
  const conversionQuantity = foodConversionQuantityForUnit(food, unit);
  if (conversionQuantity !== null && servingSize > 0) {
    return (safeGrams / servingSize) * conversionQuantity;
  }

  const normalizedProductUnit = normalizedUnitName(
    productUnitNameForFood(food, productUnits),
  );
  if (
    servingAliasUnits.has(normalizedUnit) ||
    (normalizedProductUnit && normalizedUnit === normalizedProductUnit)
  ) {
    return servingSize > 0 ? safeGrams / servingSize : safeGrams;
  }

  return safeGrams;
}

function getIngredientWeight(
  ingredients: RecipeIngredientPreview[],
  productUnits: ProductUnit[] = [],
) {
  return ingredients.reduce((total, ingredient) => {
    return (
      total +
      foodQuantityToGrams(
        ingredient.food,
        ingredient.quantity,
        ingredient.unit,
        productUnits,
      )
    );
  }, 0);
}

function getRecipeIngredientWeight(
  recipe?: Recipe | null,
  pendingIngredients: PendingRecipeIngredient[] = [],
  productUnits: ProductUnit[] = [],
) {
  return getIngredientWeight(recipe?.ingredients ?? pendingIngredients, productUnits);
}

function getIngredientMacroPreview(
  ingredients: RecipeIngredientPreview[],
  servings = 1,
  productUnits: ProductUnit[] = [],
) {
  const emptyTotals: MacroValues = {
    calories: 0,
    protein: 0,
    fat: 0,
    carbs: 0,
  };
  const total = ingredients.reduce<MacroValues>(
    (values, ingredient) => {
      const grams = foodQuantityToGrams(
        ingredient.food,
        ingredient.quantity,
        ingredient.unit,
        productUnits,
      );
      const factor = grams / 100;
      return {
        calories: values.calories + ingredient.food.calories_per_100g * factor,
        protein: values.protein + ingredient.food.protein_per_100g * factor,
        fat: values.fat + ingredient.food.fat_per_100g * factor,
        carbs: values.carbs + ingredient.food.carbs_per_100g * factor,
      };
    },
    emptyTotals,
  );
  const safeServings = servings || 1;
  return {
    per_serving: {
      calories: total.calories / safeServings,
      protein: total.protein / safeServings,
      fat: total.fat / safeServings,
      carbs: total.carbs / safeServings,
    },
    total,
  };
}

function getIngredientCalories(
  ingredient: RecipeIngredientPreview,
  productUnits: ProductUnit[] = [],
) {
  return (
    ingredient.food.calories_per_100g *
    (foodQuantityToGrams(
      ingredient.food,
      ingredient.quantity,
      ingredient.unit,
      productUnits,
    ) /
      100)
  );
}

function getRecipeMacroPreview(
  recipe?: Recipe | null,
  pendingIngredients: PendingRecipeIngredient[] = [],
  servings = 1,
  productUnits: ProductUnit[] = [],
) {
  const ingredients = recipe?.ingredients ?? pendingIngredients;
  return getIngredientMacroPreview(
    ingredients,
    recipe?.servings || servings,
    productUnits,
  );
}

function RecipesPage({
  editingRecipeId,
  editorOpen,
  foods,
  form,
  ingredientForms,
  onCalculate,
  onCloseEditor,
  onCreateRecipe,
  onDeleteIngredient,
  onDeletePendingIngredient,
  onDeleteRecipe,
  onEditRecipe,
  onFormChange,
  onIngredientAmountChange,
  onIngredientFormChange,
  onIngredientSubmit,
  onPendingIngredientAmountChange,
  onPrepareRecipe,
  onRecipeStepAdd,
  onRecipeStepDraftChange,
  onRecipeStepRemove,
  onSyncShoppingList,
  onSubmit,
  pendingIngredients,
  productUnits,
  recipeStepDraft,
  recipeNutrition,
  recipes,
}: {
  editingRecipeId: number | null;
  editorOpen: boolean;
  foods: Food[];
  form: RecipeForm;
  ingredientForms: Record<number, RecipeIngredientForm>;
  onCalculate: (recipeId: number) => void;
  onCloseEditor: () => void;
  onCreateRecipe: () => void;
  onDeleteIngredient: (recipeId: number, ingredientId: number) => void;
  onDeletePendingIngredient: (tempId: string) => void;
  onDeleteRecipe: (recipeId: number) => void;
  onEditRecipe: (recipe: Recipe) => void;
  onFormChange: (value: RecipeForm) => void;
  onIngredientAmountChange: (
    ingredient: RecipeIngredient,
    quantity: string,
  ) => void;
  onIngredientFormChange: (
    recipeId: number,
    value: RecipeIngredientForm,
  ) => void;
  onIngredientSubmit: (recipeId: number, event: FormEvent) => void;
  onPendingIngredientAmountChange: (tempId: string, quantity: string) => void;
  onPrepareRecipe: (recipeId: number) => Promise<RecipePrepareResult>;
  onRecipeStepAdd: () => void;
  onRecipeStepDraftChange: (value: string) => void;
  onRecipeStepRemove: (index: number) => void;
  onSyncShoppingList: (recipeId: number) => Promise<RecipeShoppingListSyncResult>;
  onSubmit: (event: FormEvent) => void;
  pendingIngredients: PendingRecipeIngredient[];
  productUnits: ProductUnit[];
  recipeStepDraft: string;
  recipeNutrition: Record<number, RecipeNutrition>;
  recipes: Recipe[];
}) {
  const editingRecipe =
    editingRecipeId === null
      ? null
      : recipes.find((recipe) => recipe.id === editingRecipeId) ?? null;
  const ingredientFormKey = editingRecipeId ?? draftRecipeIngredientKey;
  const ingredientForm =
    ingredientForms[ingredientFormKey] ?? initialRecipeIngredientForm;
  const selectedIngredientFood = findFoodByIngredientForm(foods, ingredientForm);
  const ingredientUnitOptions = foodUnitOptions(
    selectedIngredientFood,
    productUnits,
    ingredientForm.unit,
  );
  const ingredientWeight = getRecipeIngredientWeight(
    editingRecipe,
    pendingIngredients,
    productUnits,
  );
  const servingCount = toQuantityNumber(form.servings, 1);
  const perServingWeight = servingCount > 0 ? ingredientWeight / servingCount : 0;
  const recipePreviewNutrition =
    editingRecipe && recipeNutrition[editingRecipe.id]
      ? {
          per_serving: recipeNutrition[editingRecipe.id].per_serving,
          total: recipeNutrition[editingRecipe.id].total,
        }
      : getRecipeMacroPreview(
          editingRecipe,
          pendingIngredients,
          servingCount,
          productUnits,
        );
  const recipeSteps = splitRecipeSteps(form.instructions);
  const [ingredientEditorOpen, setIngredientEditorOpen] = useState(false);
  const [preparingRecipeId, setPreparingRecipeId] = useState<number | null>(null);
  const [shoppingSyncResults, setShoppingSyncResults] = useState<
    Record<number, RecipeShoppingListSyncResult>
  >({});
  const [shoppingSyncingRecipeId, setShoppingSyncingRecipeId] = useState<
    number | null
  >(null);
  const [prepareResults, setPrepareResults] = useState<
    Record<number, RecipePrepareResult>
  >({});
  const [preparingInventoryRecipeId, setPreparingInventoryRecipeId] = useState<
    number | null
  >(null);
  const [prepareMessages, setPrepareMessages] = useState<Record<number, string>>(
    {},
  );
  const [recipeTagFilter, setRecipeTagFilter] = useState("all");
  const [recipeSort, setRecipeSort] = useState<RecipeSort>("name");
  const recipeCaloriesById = useMemo(() => {
    return new Map(
      recipes.map((recipe) => [
        recipe.id,
        getRecipeMacroPreview(recipe, [], recipe.servings, productUnits)
          .per_serving.calories,
      ]),
    );
  }, [productUnits, recipes]);
  const recipeTags = useMemo(() => {
    const tags = new Set<string>();
    recipes.forEach((recipe) => {
      recipe.tags?.forEach((tag) => {
        if (tag.trim()) {
          tags.add(tag.trim());
        }
      });
    });
    return [...tags].sort((a, b) => a.localeCompare(b, "de"));
  }, [recipes]);
  const visibleRecipes = useMemo(() => {
    return recipes
      .filter((recipe) =>
        recipeTagFilter === "all"
          ? true
          : recipe.tags?.some(
              (tag) => tag.toLowerCase() === recipeTagFilter.toLowerCase(),
            ),
      )
      .slice()
      .sort((first, second) => {
        if (recipeSort === "calories" || recipeSort === "calories-desc") {
          const firstCalories = recipeCaloriesById.get(first.id) ?? 0;
          const secondCalories = recipeCaloriesById.get(second.id) ?? 0;
          const caloriesComparison = firstCalories - secondCalories;
          return (
            (recipeSort === "calories"
              ? caloriesComparison
              : -caloriesComparison) ||
            first.name.localeCompare(second.name, "de")
          );
        }
        if (recipeSort === "servings") {
          return first.servings - second.servings || first.name.localeCompare(second.name, "de");
        }
        if (recipeSort === "tag") {
          return (
            (first.tags?.[0] ?? "").localeCompare(second.tags?.[0] ?? "", "de") ||
            first.name.localeCompare(second.name, "de")
          );
        }
        return first.name.localeCompare(second.name, "de");
      });
  }, [recipeCaloriesById, recipeSort, recipeTagFilter, recipes]);
  const preparingRecipe =
    preparingRecipeId === null
      ? null
      : recipes.find((recipe) => recipe.id === preparingRecipeId) ?? null;
  const preparingSteps = splitRecipeSteps(preparingRecipe?.instructions);
  const preparingShoppingSyncResult =
    preparingRecipe === null ? null : shoppingSyncResults[preparingRecipe.id] ?? null;
  const preparingShoppingSyncing =
    preparingRecipe !== null && shoppingSyncingRecipeId === preparingRecipe.id;
  const preparingInventoryBusy =
    preparingRecipe !== null && preparingInventoryRecipeId === preparingRecipe.id;
  const preparingResult =
    preparingRecipe === null ? null : prepareResults[preparingRecipe.id] ?? null;
  const preparingMessage =
    preparingRecipe === null ? "" : prepareMessages[preparingRecipe.id] ?? "";

  useEffect(() => {
    setIngredientEditorOpen(false);
  }, [editingRecipeId, editorOpen]);

  useEffect(() => {
    if (
      recipeTagFilter !== "all" &&
      !recipeTags.some((tag) => tag.toLowerCase() === recipeTagFilter.toLowerCase())
    ) {
      setRecipeTagFilter("all");
    }
  }, [recipeTagFilter, recipeTags]);

  async function syncPreparingRecipeShoppingList(recipeId: number) {
    setShoppingSyncingRecipeId(recipeId);
    try {
      const result = await onSyncShoppingList(recipeId);
      setShoppingSyncResults((current) => ({
        ...current,
        [recipeId]: result,
      }));
      return result;
    } catch {
      // The global API notice already shows the error.
      return null;
    } finally {
      setShoppingSyncingRecipeId(null);
    }
  }

  async function prepareInventoryRecipe(recipeId: number) {
    setPreparingInventoryRecipeId(recipeId);
    setPrepareMessages((current) => {
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
    setPrepareResults((current) => {
      if (!(recipeId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
    setShoppingSyncResults((current) => {
      if (!(recipeId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
    try {
      const result = await onPrepareRecipe(recipeId);
      setPrepareResults((current) => ({
        ...current,
        [recipeId]: result,
      }));
    } catch (error) {
      if (isRecipeStockShortageError(error)) {
        const message = apiErrorMessage(error);
        const shouldAddMissing = window.confirm(
          "Es ist zu wenig Bestand vorhanden. Fehlende Zutaten auf die Einkaufsliste setzen?",
        );
        if (!shouldAddMissing) {
          setPrepareMessages((current) => ({
            ...current,
            [recipeId]: message,
          }));
          return;
        }

        const result = await syncPreparingRecipeShoppingList(recipeId);
        setPrepareMessages((current) => ({
          ...current,
          [recipeId]:
            result === null
              ? "Fehlende Zutaten konnten nicht auf die Einkaufsliste gesetzt werden."
              : result.missing.length === 0
                ? "Bestand reicht inzwischen aus."
                : "Fehlende Zutaten wurden auf die Einkaufsliste gesetzt.",
        }));
        return;
      }

      setPrepareMessages((current) => ({
        ...current,
        [recipeId]:
          error instanceof Error
            ? error.message
            : "Gericht konnte nicht zubereitet werden.",
      }));
    } finally {
      setPreparingInventoryRecipeId(null);
    }
  }

  function openPreparingRecipe(recipeId: number) {
    setPreparingRecipeId(recipeId);
    setShoppingSyncResults((current) => {
      if (!(recipeId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
    setPrepareResults((current) => {
      if (!(recipeId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
    setPrepareMessages((current) => {
      if (!(recipeId in current)) {
        return current;
      }
      const next = { ...current };
      delete next[recipeId];
      return next;
    });
  }

  function handleRecipeImageFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) {
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const imagePath = typeof reader.result === "string" ? reader.result : "";
      if (imagePath) {
        onFormChange({ ...form, image_path: imagePath });
      }
    };
    reader.readAsDataURL(file);
    event.target.value = "";
  }

  if (editorOpen) {
    return (
      <div className="recipe-builder-page">
        <section className="recipe-builder-shell">
          <div className="recipe-builder-topbar">
            <button
              className="recipe-builder-back"
              onClick={onCloseEditor}
              title="Zurueck"
              type="button"
            >
              <ChevronLeft size={28} />
            </button>
            <h2>
              {editingRecipeId === null ? "Rezept erstellen" : "Rezept bearbeiten"}
            </h2>
          </div>
          <div className="recipe-builder-progress">
            <span />
          </div>

          <div className="recipe-builder-form">
            <section className="recipe-builder-section">
              <h3>Build your recipe</h3>
              <div className="recipe-builder-field-head">
                <span>Recipe Name</span>
                <small>Required</small>
              </div>
              <input
                onChange={(event) =>
                  onFormChange({ ...form, name: event.target.value })
                }
                required
                value={form.name}
              />

              <label className="recipe-builder-field">
                <span>Emoji</span>
                <input
                  maxLength={32}
                  onChange={(event) =>
                    onFormChange({ ...form, emoji: event.target.value })
                  }
                  value={form.emoji}
                />
              </label>

              <label className="recipe-builder-field">
                <span>Tags</span>
                <input
                  onChange={(event) =>
                    onFormChange({ ...form, tags: event.target.value })
                  }
                  placeholder="Fruehstueck, Mahlzeit, Nudeln, Reis, Veg"
                  value={form.tags}
                />
              </label>

              <label className="recipe-builder-field">
                <span>Bild</span>
                <div className="recipe-image-tools">
                  <input
                    accept="image/*"
                    onChange={handleRecipeImageFile}
                    type="file"
                  />
                  <input
                    onChange={(event) =>
                      onFormChange({ ...form, image_path: event.target.value })
                    }
                    placeholder="Bild-URL einfuegen"
                    readOnly={form.image_path.startsWith("data:")}
                    value={form.image_path.startsWith("data:")
                      ? "Lokales Bild ausgewaehlt"
                      : form.image_path}
                  />
                </div>
                <div className="recipe-image-preview">
                  {form.image_path ? (
                    <>
                      <img alt="Rezeptbild Vorschau" src={form.image_path} />
                      <button
                        className="button secondary"
                        onClick={() => onFormChange({ ...form, image_path: "" })}
                        type="button"
                      >
                        Bild entfernen
                      </button>
                    </>
                  ) : (
                    <span>Keine Bildvorschau</span>
                  )}
                </div>
              </label>

              <div className="recipe-builder-field-head">
                <span>Serving Quantity</span>
                <small>Required</small>
              </div>
              <input
                inputMode="decimal"
                onChange={(event) =>
                  onFormChange({ ...form, servings: event.target.value })
                }
                pattern={fractionNumberPattern}
                required
                title="Zahl oder Bruch, z.B. 2/3"
                value={form.servings}
              />

              <label className="recipe-builder-field">
                <span>Total Weight</span>
                <div className="recipe-builder-suffix-field">
                  <input readOnly value={formatNumber(ingredientWeight)} />
                  <strong>g</strong>
                </div>
                <small>
                  Per serving weight will be {formatNumber(perServingWeight)} g
                </small>
              </label>
            </section>

            <section className="recipe-builder-section">
              <div className="recipe-builder-section-head">
                <div>
                  <h3>Ingredients</h3>
                  <p>Weight of ingredients is {formatNumber(ingredientWeight)} g</p>
                </div>
                <button
                  className="recipe-builder-round-button"
                  onClick={() => setIngredientEditorOpen((open) => !open)}
                  title="Zutat hinzufuegen"
                  type="button"
                >
                  <Plus size={28} />
                </button>
              </div>

              {editingRecipeId === null ? (
                <>
                  <div className="recipe-builder-ingredients">
                    {pendingIngredients.length === 0 ? (
                      <div className="recipe-builder-empty">Keine Zutaten</div>
                    ) : (
                      pendingIngredients.map((ingredient) => (
                        <div
                          className="recipe-builder-ingredient"
                          key={ingredient.temp_id}
                        >
                          <Utensils size={28} />
                          <div>
                            <strong className="food-name-with-emoji">
                              <span aria-hidden="true">
                                {ingredient.food.emoji || defaultFoodEmoji}
                              </span>
                              <span>{ingredient.food.name}</span>
                            </strong>
                            <span>
                              {formatNumber(getIngredientCalories(ingredient, productUnits))}
                              kcal Â· {formatNumber(ingredient.food.protein_per_100g)}P{" "}
                              {formatNumber(ingredient.food.fat_per_100g)}F{" "}
                              {formatNumber(ingredient.food.carbs_per_100g)}C Â·{" "}
                              {formatFractionalQuantity(ingredient.quantity)} {ingredient.unit}
                            </span>
                          </div>
                          <div className="recipe-builder-amount">
                            <input
                              defaultValue={formatFractionalQuantity(
                                ingredient.quantity,
                              )}
                              inputMode="decimal"
                              onBlur={(event) => {
                                const nextQuantity = toQuantityNumber(
                                  event.target.value,
                                  ingredient.quantity,
                                );
                                event.target.value =
                                  formatFractionalQuantity(nextQuantity);
                                if (nextQuantity !== normalizeFractionalQuantityValue(ingredient.quantity)) {
                                  onPendingIngredientAmountChange(
                                    ingredient.temp_id,
                                    event.target.value,
                                  );
                                }
                              }}
                              pattern={fractionNumberPattern}
                              title="Zahl oder Bruch, z.B. 2/3"
                            />
                            <span>{ingredient.unit}</span>
                          </div>
                          <button
                            className="recipe-builder-delete"
                            onClick={() =>
                              onDeletePendingIngredient(ingredient.temp_id)
                            }
                            title="Zutat loeschen"
                            type="button"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>

                  {ingredientEditorOpen && (
                    <form
                      className="recipe-builder-add-ingredient"
                      onSubmit={(event) =>
                        onIngredientSubmit(draftRecipeIngredientKey, event)
                      }
                    >
                      <label>
                        <span>Lebensmittel</span>
                        <input
                          list="recipe-builder-food-options-draft"
                          onChange={(event) =>
                            onIngredientFormChange(
                              draftRecipeIngredientKey,
                              updateIngredientFoodSearch(
                                foods,
                                ingredientForm,
                                event.target.value,
                                productUnits,
                              ),
                            )
                          }
                          placeholder="Lebensmittel suchen"
                          required
                          value={ingredientForm.food_query}
                        />
                        <datalist id="recipe-builder-food-options-draft">
                          {foods.map((food) => (
                            <option
                              key={food.id}
                              value={formatFoodSuggestionLabel(food)}
                            />
                          ))}
                        </datalist>
                      </label>
                      <label>
                        <span>Menge</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onIngredientFormChange(draftRecipeIngredientKey, {
                              ...ingredientForm,
                              quantity: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          required
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={ingredientForm.quantity}
                        />
                      </label>
                      <label>
                        <span>Einheit</span>
                        <select
                          onChange={(event) =>
                            onIngredientFormChange(draftRecipeIngredientKey, {
                              ...ingredientForm,
                              unit: event.target.value,
                            })
                          }
                          required
                          value={ingredientForm.unit}
                        >
                          {ingredientUnitOptions.map((unit) => (
                            <option key={unit} value={unit}>
                              {unit}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button className="button primary" type="submit">
                        <Plus size={16} />
                        Hinzufuegen
                      </button>
                    </form>
                  )}
                </>
              ) : (
                <>
                  <div className="recipe-builder-ingredients">
                    {editingRecipe?.ingredients.length === 0 ? (
                      <div className="recipe-builder-empty">Keine Zutaten</div>
                    ) : (
                      editingRecipe?.ingredients.map((ingredient) => (
                        <div className="recipe-builder-ingredient" key={ingredient.id}>
                          <Utensils size={28} />
                          <div>
                            <strong className="food-name-with-emoji">
                              <span aria-hidden="true">
                                {ingredient.food.emoji || defaultFoodEmoji}
                              </span>
                              <span>{ingredient.food.name}</span>
                            </strong>
                            <span>
                              {formatNumber(getIngredientCalories(ingredient, productUnits))}
                              kcal · {formatNumber(ingredient.food.protein_per_100g)}P{" "}
                              {formatNumber(ingredient.food.fat_per_100g)}F{" "}
                              {formatNumber(ingredient.food.carbs_per_100g)}C ·{" "}
                              {formatFractionalQuantity(ingredient.quantity)} {ingredient.unit}
                            </span>
                          </div>
                          <div className="recipe-builder-amount">
                            <input
                              defaultValue={formatFractionalQuantity(
                                ingredient.quantity,
                              )}
                              inputMode="decimal"
                              onBlur={(event) => {
                                const nextQuantity = toQuantityNumber(
                                  event.target.value,
                                  ingredient.quantity,
                                );
                                event.target.value =
                                  formatFractionalQuantity(nextQuantity);
                                if (nextQuantity !== normalizeFractionalQuantityValue(ingredient.quantity)) {
                                  onIngredientAmountChange(
                                    ingredient,
                                    event.target.value,
                                  );
                                }
                              }}
                              pattern={fractionNumberPattern}
                              title="Zahl oder Bruch, z.B. 2/3"
                            />
                            <span>{ingredient.unit}</span>
                          </div>
                          <button
                            className="recipe-builder-delete"
                            onClick={() =>
                              onDeleteIngredient(editingRecipe.id, ingredient.id)
                            }
                            title="Zutat loeschen"
                            type="button"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>

                  {ingredientEditorOpen && (
                    <form
                      className="recipe-builder-add-ingredient"
                      onSubmit={(event) => onIngredientSubmit(editingRecipeId, event)}
                    >
                      <label>
                        <span>Lebensmittel</span>
                        <input
                          list={`recipe-builder-food-options-${editingRecipeId}`}
                          onChange={(event) =>
                            onIngredientFormChange(
                              editingRecipeId,
                              updateIngredientFoodSearch(
                                foods,
                                ingredientForm,
                                event.target.value,
                                productUnits,
                              ),
                            )
                          }
                          placeholder="Lebensmittel suchen"
                          required
                          value={ingredientForm.food_query}
                        />
                        <datalist
                          id={`recipe-builder-food-options-${editingRecipeId}`}
                        >
                          {foods.map((food) => (
                            <option
                              key={food.id}
                              value={formatFoodSuggestionLabel(food)}
                            />
                          ))}
                        </datalist>
                      </label>
                      <label>
                        <span>Menge</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onIngredientFormChange(editingRecipeId, {
                              ...ingredientForm,
                              quantity: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          required
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={ingredientForm.quantity}
                        />
                      </label>
                      <label>
                        <span>Einheit</span>
                        <select
                          onChange={(event) =>
                            onIngredientFormChange(editingRecipeId, {
                              ...ingredientForm,
                              unit: event.target.value,
                            })
                          }
                          required
                          value={ingredientForm.unit}
                        >
                          {ingredientUnitOptions.map((unit) => (
                            <option key={unit} value={unit}>
                              {unit}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button className="button primary" type="submit">
                        <Plus size={16} />
                        Hinzufuegen
                      </button>
                    </form>
                  )}
                </>
              )}
            </section>

            <section className="recipe-builder-section">
              <div className="recipe-builder-section-head">
                <h3>Nutrition</h3>
                {editingRecipeId !== null && (
                  <button
                    className="recipe-builder-pill"
                    onClick={() => onCalculate(editingRecipeId)}
                    type="button"
                  >
                    Serving
                  </button>
                )}
              </div>
              <div className="recipe-builder-nutrition-grid">
                {macroMeta.map((macro) => (
                  <article className="recipe-builder-nutrition-card" key={macro.key}>
                    <strong>{macro.label}</strong>
                    <span>
                      {formatNumber(recipePreviewNutrition.per_serving[macro.key])}{" "}
                      {macro.key === "calories" ? "kcal" : "g"} per serving
                    </span>
                    <div className="recipe-builder-meter">
                      <span
                        className={macro.tone}
                        style={{
                          width: `${Math.min(
                            recipePreviewNutrition.per_serving[macro.key],
                            100,
                          )}%`,
                        }}
                      />
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="recipe-builder-section">
              <h3>Preparation (optional)</h3>
              <div className="recipe-builder-time-grid">
                <label className="recipe-builder-field">
                  <span>Preparation Time</span>
                  <div className="recipe-builder-suffix-field">
                    <input
                      min="0"
                      onChange={(event) =>
                        onFormChange({
                          ...form,
                          prep_time_minutes: event.target.value,
                        })
                      }
                      type="number"
                      value={form.prep_time_minutes}
                    />
                    <strong>min</strong>
                  </div>
                </label>
                <label className="recipe-builder-field">
                  <span>Cooking Time</span>
                  <div className="recipe-builder-suffix-field">
                    <input
                      min="0"
                      onChange={(event) =>
                        onFormChange({
                          ...form,
                          cook_time_minutes: event.target.value,
                        })
                      }
                      type="number"
                      value={form.cook_time_minutes}
                    />
                    <strong>min</strong>
                  </div>
                </label>
              </div>
              <label className="recipe-builder-field">
                <span>Description</span>
                <textarea
                  maxLength={1500}
                  onChange={(event) =>
                    onFormChange({ ...form, description: event.target.value })
                  }
                  placeholder="Describe the recipe"
                  value={form.description}
                />
                <small>{form.description.length}/1500</small>
              </label>
              <div className="recipe-builder-section-head">
                <div>
                  <h3>Steps</h3>
                  <p>Add preparation steps</p>
                </div>
                <button
                  className="recipe-builder-round-button"
                  onClick={onRecipeStepAdd}
                  type="button"
                >
                  <Plus size={28} />
                </button>
              </div>
              <div className="recipe-builder-step-input">
                <textarea
                  onChange={(event) => onRecipeStepDraftChange(event.target.value)}
                  placeholder="Neuen Schritt beschreiben"
                  value={recipeStepDraft}
                />
              </div>
              <div className="recipe-builder-steps">
                {recipeSteps.map((step, index) => (
                  <article className="recipe-builder-step" key={`${step}-${index}`}>
                    <div>
                      <strong>Step {index + 1}</strong>
                      <p>{step}</p>
                    </div>
                    <button
                      className="recipe-builder-delete"
                      onClick={() => onRecipeStepRemove(index)}
                      title="Schritt loeschen"
                      type="button"
                    >
                      <Trash2 size={18} />
                    </button>
                  </article>
                ))}
              </div>
            </section>

            <div className="recipe-builder-footer">
              <button className="button secondary" onClick={onCloseEditor} type="button">
                Abbrechen
              </button>
              {editingRecipeId !== null && (
                <button
                  className="button danger"
                  onClick={() => onDeleteRecipe(editingRecipeId)}
                  type="button"
                >
                  <Trash2 size={16} />
                  Rezept loeschen
                </button>
              )}
              <button
                className="button primary"
                onClick={(event) => onSubmit(event as unknown as FormEvent)}
                type="button"
              >
                {editingRecipeId === null ? "Rezept anlegen" : "Rezept speichern"}
              </button>
            </div>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="recipes-page">
      <section className="section wide">
        <div className="section-header">
          <div>
            <p className="eyebrow">
              {visibleRecipes.length} von {recipes.length} Gerichten
            </p>
            <h2>Gerichte</h2>
          </div>
          <button className="button primary" onClick={onCreateRecipe} type="button">
            <Plus size={16} />
            Gericht erstellen
          </button>
        </div>
        <div className="recipe-filter-row">
          <label>
            <span>Tag</span>
            <select
              onChange={(event) => setRecipeTagFilter(event.target.value)}
              value={recipeTagFilter}
            >
              <option value="all">Alle Tags</option>
              {recipeTags.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Sortierung</span>
            <select
              onChange={(event) =>
                setRecipeSort(event.target.value as RecipeSort)
              }
              value={recipeSort}
            >
              <option value="name">Name</option>
              <option value="tag">Tag</option>
              <option value="servings">Portionen</option>
              <option value="calories">Kalorien aufsteigend</option>
              <option value="calories-desc">Kalorien absteigend</option>
            </select>
          </label>
        </div>
        <div className="recipe-grid">
          {recipes.length === 0 ? (
            <EmptyState label="Keine Gerichte vorhanden" />
          ) : visibleRecipes.length === 0 ? (
            <EmptyState label="Keine Gerichte fuer diesen Tag vorhanden" />
          ) : (
            visibleRecipes.map((recipe) => {
              const caloriesPerServing = recipeCaloriesById.get(recipe.id) ?? 0;
              return (
                <article className="recipe-card" key={recipe.id}>
                  {recipe.image_path && (
                    <div className="recipe-card-image">
                      <img alt={`${recipe.name} Bild`} src={recipe.image_path} />
                    </div>
                  )}
                  <div className="recipe-head">
                    <div>
                      <h3 className="recipe-title-with-emoji">
                        <span aria-hidden="true">
                          {recipe.emoji || defaultRecipeEmoji}
                        </span>
                        <span>{recipe.name}</span>
                      </h3>
                      <span>
                        {formatFractionalQuantity(recipe.servings)} Portionen |{" "}
                        {formatNumber(caloriesPerServing, 0)} kcal / Portion
                      </span>
                      {(recipe.tags ?? []).length > 0 && (
                        <div className="recipe-tags">
                          {(recipe.tags ?? []).map((tag) => (
                            <span key={tag}>{tag}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="recipe-actions">
                      <button
                        className="icon-button"
                        onClick={() => onEditRecipe(recipe)}
                        title="Gericht bearbeiten"
                        type="button"
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        className="button secondary"
                        onClick={() => openPreparingRecipe(recipe.id)}
                        type="button"
                      >
                        <Utensils size={16} />
                        Zubereiten
                      </button>
                      <button
                        className="button secondary"
                        onClick={() => onCalculate(recipe.id)}
                        type="button"
                      >
                        <BarChart3 size={16} />
                        {recipeNutrition[recipe.id] ? "Einklappen" : "Naehrwerte"}
                      </button>
                    </div>
                  </div>
                  {recipeNutrition[recipe.id] && (
                    <div className="nutrition-mini">
                      {macroMeta.map((macro) => (
                        <Stat
                          key={macro.key}
                          label={macro.label}
                          value={formatNumber(
                            recipeNutrition[recipe.id].per_serving[macro.key],
                          )}
                        />
                      ))}
                    </div>
                  )}
                </article>
              );
            })
          )}
        </div>
      </section>
      {preparingRecipe && (
        <ModalBackdrop
          onClose={() => setPreparingRecipeId(null)}
          role="presentation"
        >
          <section className="prepare-panel" role="dialog" aria-modal="true">
            <div className="prepare-header">
              <div>
                <p className="eyebrow">
                  {formatFractionalQuantity(preparingRecipe.servings)} Portionen
                </p>
                <h2 className="recipe-title-with-emoji">
                  <span aria-hidden="true">
                    {preparingRecipe.emoji || defaultRecipeEmoji}
                  </span>
                  <span>{preparingRecipe.name}</span>
                </h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setPreparingRecipeId(null)}
                title="Schliessen"
                type="button"
              >
                <X size={18} />
              </button>
            </div>

            {preparingRecipe.image_path && (
              <div className="prepare-image">
                <img
                  alt={`${preparingRecipe.name} Bild`}
                  src={preparingRecipe.image_path}
                />
              </div>
            )}

            <section className="prepare-section">
              <h3>Beschreibung</h3>
              {preparingRecipe.description ? (
                <p>{preparingRecipe.description}</p>
              ) : (
                <p className="muted-line">Keine Beschreibung hinterlegt</p>
              )}
            </section>

            <section className="prepare-section">
              <h3>Benoetigt</h3>
              {preparingRecipe.ingredients.length === 0 ? (
                <p className="muted-line">Keine Zutaten hinterlegt</p>
              ) : (
                <div className="prepare-ingredient-list">
                  {preparingRecipe.ingredients.map((ingredient) => (
                    <div className="prepare-ingredient-row" key={ingredient.id}>
                      <span>{ingredient.food.name}</span>
                      <strong>
                        {formatFractionalQuantity(ingredient.quantity)} {ingredient.unit}
                      </strong>
                    </div>
                  ))}
                </div>
              )}
              <div className="prepare-stock-actions">
                <button
                  className="button primary"
                  disabled={
                    preparingRecipe.ingredients.length === 0 ||
                    preparingInventoryBusy ||
                    preparingShoppingSyncing
                  }
                  onClick={() => void prepareInventoryRecipe(preparingRecipe.id)}
                  type="button"
                >
                  <Utensils size={16} />
                  {preparingShoppingSyncing
                    ? "Einkaufsliste wird geschrieben"
                    : preparingInventoryBusy
                      ? "Gericht wird gebucht"
                      : "Gericht zubereiten"}
                </button>
              </div>
              {preparingMessage && (
                <div className="prepare-stock-result missing">
                  <div className="prepare-stock-result-head">
                    <AlertTriangle size={18} />
                    <strong>{preparingMessage}</strong>
                  </div>
                </div>
              )}
              {preparingResult && (
                <div className="prepare-stock-result complete">
                  <div className="prepare-stock-result-head">
                    <CheckCircle2 size={18} />
                    <strong>
                      {formatFractionalQuantity(preparingResult.prepared_quantity)}{" "}
                      {preparingResult.prepared_unit} eingelagert
                    </strong>
                  </div>
                  <div className="prepare-stock-missing-list">
                    {preparingResult.consumed.map((item) => (
                      <div
                        className="prepare-stock-missing-row"
                        key={`${item.food_id}-${item.unit}`}
                      >
                        <span>{item.name}</span>
                        <strong>
                          -{formatFractionalQuantity(item.quantity)} {item.unit}
                        </strong>
                        <small>verbraucht</small>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {preparingShoppingSyncResult && (
                <div
                  className={`prepare-stock-result ${
                    preparingShoppingSyncResult.missing.length === 0
                      ? "complete"
                      : "missing"
                  }`}
                >
                  <div className="prepare-stock-result-head">
                    {preparingShoppingSyncResult.missing.length === 0 ? (
                      <CheckCircle2 size={18} />
                    ) : (
                      <AlertTriangle size={18} />
                    )}
                    <strong>
                      {preparingShoppingSyncResult.missing.length === 0
                        ? "Bestand reicht aus"
                        : `${preparingShoppingSyncResult.missing.length} fehlende Zutaten`}
                    </strong>
                  </div>
                  {preparingShoppingSyncResult.missing.length > 0 && (
                    <div className="prepare-stock-missing-list">
                      {preparingShoppingSyncResult.missing.map((item) => (
                        <div
                          className="prepare-stock-missing-row"
                          key={`${item.food_id}-${item.unit}`}
                        >
                          <span>{item.name}</span>
                          <strong>
                            {formatFractionalQuantity(item.shopping_item.quantity)}{" "}
                            {item.shopping_item.unit}
                          </strong>
                          <small>{formatRecipeShoppingAction(item.action)}</small>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </section>

            <section className="prepare-section">
              <h3>Schritte</h3>
              {preparingSteps.length === 0 ? (
                <p className="muted-line">Keine Schritte hinterlegt</p>
              ) : (
                <div className="prepare-steps">
                  {preparingSteps.map((step, index) => (
                    <article className="prepare-step" key={`${step}-${index}`}>
                      <strong>Schritt {index + 1}</strong>
                      <p>{step}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </section>
        </ModalBackdrop>
      )}
    </div>
  );
}

function NutritionPage({
  editingMealLogId,
  foods,
  form,
  inventory,
  mealLogs,
  nutrition,
  onCancelEdit,
  onDateChange,
  onDelete,
  onDeductMealLogInventory,
  onEdit,
  onFormChange,
  onInventoryDecrease,
  onMove,
  onSubmit,
  productUnits,
  recipes,
  selectedDate,
}: {
  editingMealLogId: number | null;
  foods: Food[];
  form: MealForm;
  inventory: InventoryItem[];
  mealLogs: MealLog[];
  nutrition: NutritionDay;
  onCancelEdit: () => void;
  onDateChange: (value: string) => void;
  onDelete: (mealLogId: number) => void;
  onDeductMealLogInventory: (mealLogId: number) => Promise<boolean> | boolean;
  onEdit: (mealLog: MealLog) => void;
  onFormChange: (value: MealForm) => void;
  onInventoryDecrease: (id: number, amount: number) => Promise<boolean> | boolean;
  onMove: (mealLog: MealLog, date: string, time: string) => void;
  onSubmit: (event?: FormEvent) => Promise<boolean> | boolean;
  productUnits: ProductUnit[];
  recipes: Recipe[];
  selectedDate: string;
}) {
  const [draggedMealLogId, setDraggedMealLogId] = useState<number | null>(null);
  const [addSheetOpen, setAddSheetOpen] = useState(false);
  const [sheetMode, setSheetMode] = useState<"search" | "details">("search");
  const [nutritionSearch, setNutritionSearch] = useState("");
  const [barcodePanelOpen, setBarcodePanelOpen] = useState(false);
  const [barcodeInput, setBarcodeInput] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const [barcodeStatus, setBarcodeStatus] = useState("");
  const [barcodeFoodOverride, setBarcodeFoodOverride] = useState<Food | null>(
    null,
  );
  const [barcodeInventoryItems, setBarcodeInventoryItems] = useState<
    InventoryItemSummary[]
  >([]);
  const [scannerActive, setScannerActive] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scanLoopRef = useRef<number | null>(null);
  const scannerRunningRef = useRef(false);
  const timelineStartSlot = 12;
  const timelineEndSlot = 44;
  const timelineSlots = Array.from(
    { length: timelineEndSlot - timelineStartSlot + 1 },
    (_, index) => timelineStartSlot + index,
  );
  const hourSlots = timelineSlots.filter((slot) => slot % 2 === 0);
  const dayMealLogs = useMemo(
    () =>
      mealLogs
        .filter(
          (mealLog) =>
            getMealLogDate(mealLog) === selectedDate &&
            (mealLog.user_id === null ||
              mealLog.user_id === undefined ||
              mealLog.user_id === nutrition.user_id),
        )
        .sort(
          (first, second) =>
            new Date(first.eaten_at).getTime() - new Date(second.eaten_at).getTime(),
        ),
    [mealLogs, nutrition.user_id, selectedDate],
  );
  const mealLogSlotGroups = useMemo(() => {
    const groups = new Map<number, MealLog[]>();

    for (const mealLog of dayMealLogs) {
      const slot = timeValueToSlot(getMealLogTime(mealLog), 18);
      if (slot < timelineStartSlot || slot > timelineEndSlot) {
        continue;
      }

      const logs = groups.get(slot) ?? [];
      logs.push(mealLog);
      groups.set(slot, logs);
    }

    return Array.from(groups.entries()).map(([slot, logs]) => ({
      logs,
      slot,
    }));
  }, [dayMealLogs]);
  const draggedMealLog =
    draggedMealLogId === null
      ? null
      : mealLogs.find((mealLog) => mealLog.id === draggedMealLogId) ?? null;
  const selectedSlot = timeValueToSlot(form.time, 18);
  const today = getLocalDate();
  const yesterday = getLocalDate(addDays(dateFromLocalValue(today), -1));
  const dateTitle =
    selectedDate === today
      ? "Heute"
      : selectedDate === yesterday
        ? "Gestern"
        : formatDate(selectedDate);
  const weekDates = useMemo(() => weekGridDates(selectedDate), [selectedDate]);
  const selectedFood =
    form.kind === "food"
      ? foods.find((food) => String(food.id) === form.target_id) ??
        (barcodeFoodOverride &&
        String(barcodeFoodOverride.id) === form.target_id
          ? barcodeFoodOverride
          : null)
      : null;
  const selectedRecipe =
    form.kind === "recipe"
      ? recipes.find((recipe) => String(recipe.id) === form.target_id) ?? null
      : null;
  const selectedTargetName =
    selectedFood?.name ??
    selectedRecipe?.name ??
    (form.kind === "quick"
      ? form.quick_name.trim() || "Quick-Add"
      : "Lebensmittel auswaehlen");

  function emptyNutritionValues(): MacroValues {
    return { calories: 0, protein: 0, fat: 0, carbs: 0 };
  }

  function quickCaloriesFromMacros(protein: number, fat: number, carbs: number) {
    return protein * 4 + fat * 9 + carbs * 4;
  }

  function getQuickFormMacros(): MacroValues {
    const protein = optionalNumber(form.quick_protein) ?? 0;
    const fat = optionalNumber(form.quick_fat) ?? 0;
    const carbs = optionalNumber(form.quick_carbs) ?? 0;
    const estimatedCalories = quickCaloriesFromMacros(protein, fat, carbs);
    return {
      calories: optionalNumber(form.quick_calories) ?? estimatedCalories,
      protein,
      fat,
      carbs,
    };
  }

  function getQuickMealLogMacros(mealLog: MealLog): MacroValues {
    return {
      calories: mealLog.quick_calories ?? 0,
      protein: mealLog.quick_protein ?? 0,
      fat: mealLog.quick_fat ?? 0,
      carbs: mealLog.quick_carbs ?? 0,
    };
  }

  function getFoodLogMacros(food: Food, quantity: number, unit: string): MacroValues {
    const grams = foodQuantityToGrams(food, quantity, unit, productUnits);
    const factor = grams / 100;
    return {
      calories: food.calories_per_100g * factor,
      protein: food.protein_per_100g * factor,
      fat: food.fat_per_100g * factor,
      carbs: food.carbs_per_100g * factor,
    };
  }

  function getRecipeLogMacros(
    recipe: Recipe,
    quantity: number,
    unit: string,
  ): MacroValues {
    const normalizedQuantity = normalizeFractionalQuantityValue(quantity);
    const preview = getIngredientMacroPreview(
      recipe.ingredients,
      recipe.servings || 1,
      productUnits,
    );
    const base =
      unit.toLowerCase() === "recipe" ? preview.total : preview.per_serving;
    return {
      calories: base.calories * normalizedQuantity,
      protein: base.protein * normalizedQuantity,
      fat: base.fat * normalizedQuantity,
      carbs: base.carbs * normalizedQuantity,
    };
  }

  function getMealLogMacros(mealLog: MealLog) {
    if (mealLog.quick_add_name) {
      return getQuickMealLogMacros(mealLog);
    }
    if (mealLog.food) {
      return getFoodLogMacros(mealLog.food as Food, mealLog.quantity, mealLog.unit);
    }
    const recipe = mealLog.recipe_id
      ? recipes.find((item) => item.id === mealLog.recipe_id)
      : null;
    return recipe
      ? getRecipeLogMacros(recipe, mealLog.quantity, mealLog.unit)
      : emptyNutritionValues();
  }

  function formatMacroLine(values: MacroValues) {
    return `${formatNumber(values.calories, 0)}kcal ${formatNumber(
      values.protein,
      0,
    )}P ${formatNumber(values.fat, 0)}F ${formatNumber(values.carbs, 0)}C`;
  }

  function macroProgress(key: keyof MacroValues) {
    return `${clampPercent(nutrition.percentages[key])}%`;
  }

  function macroShareLabel(key: keyof MacroValues, values: MacroValues) {
    if (key === "calories" || values.calories <= 0) {
      return null;
    }
    const macroCalories =
      key === "fat" ? values.fat * 9 : values[key] * 4;
    return `${formatNumber((macroCalories / values.calories) * 100, 0)}%`;
  }

  const selectedTargetMacros =
    form.kind === "quick"
      ? getQuickFormMacros()
      : selectedFood
        ? getFoodLogMacros(selectedFood, toQuantityNumber(form.quantity, 1), form.unit)
        : selectedRecipe
          ? getRecipeLogMacros(selectedRecipe, toQuantityNumber(form.quantity, 1), form.unit)
          : emptyNutritionValues();
  const quickEstimatedCalories = quickCaloriesFromMacros(
    optionalNumber(form.quick_protein) ?? 0,
    optionalNumber(form.quick_fat) ?? 0,
    optionalNumber(form.quick_carbs) ?? 0,
  );
  const inventoryDeductionPlan =
    editingMealLogId === null && form.kind === "food" && selectedFood
      ? getInventoryDeductionPlan(
          selectedFood,
          toQuantityNumber(form.quantity, 1),
          form.unit,
        )
      : [];
  const inventoryDeductionSummary = inventoryDeductionPlan
    .map(
      ({ amount, inventoryItem }) =>
        `${formatFractionalQuantity(amount)} ${inventoryItem.unit}`,
    )
    .join(", ");
  const canAddAndDeduct = inventoryDeductionPlan.length > 0;
  const weekCalorieTotals = useMemo(() => {
    const totals: Record<string, number> = {};
    const visibleDates = new Set(weekDates.map((date) => getLocalDate(date)));

    for (const mealLog of mealLogs) {
      const dateValue = getMealLogDate(mealLog);
      const belongsToUser =
        mealLog.user_id === null ||
        mealLog.user_id === undefined ||
        mealLog.user_id === nutrition.user_id;

      if (!belongsToUser || !visibleDates.has(dateValue)) {
        continue;
      }

      totals[dateValue] = (totals[dateValue] ?? 0) + getMealLogMacros(mealLog).calories;
    }

    return totals;
  }, [mealLogs, nutrition.user_id, productUnits, recipes, weekDates]);
  const calorieGoal = Math.max(nutrition.goals.calories, 1);

  function dayCalorieProgress(dateValue: string) {
    return clampPercent(((weekCalorieTotals[dateValue] ?? 0) / calorieGoal) * 100);
  }

  const filteredFoods = foods
    .filter((food) =>
      `${food.name} ${food.brand ?? ""}`
        .toLowerCase()
        .includes(nutritionSearch.toLowerCase()),
    )
    .slice(0, 8);
  const filteredRecipes = recipes
    .filter((recipe) =>
      `${recipe.name} ${(recipe.tags ?? []).join(" ")}`
        .toLowerCase()
        .includes(nutritionSearch.toLowerCase()),
    )
    .slice(0, 8);

  function barcodeDetector() {
    return (
      globalThis as typeof globalThis & {
        BarcodeDetector?: BarcodeDetectorConstructor;
      }
    ).BarcodeDetector;
  }

  function stopBarcodeScanner() {
    scannerRunningRef.current = false;
    if (scanLoopRef.current !== null) {
      cancelAnimationFrame(scanLoopRef.current);
      scanLoopRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setScannerActive(false);
  }

  function openBarcodePanel() {
    setAddSheetOpen(true);
    setSheetMode("search");
    setBarcodePanelOpen(true);
    setBarcodeStatus("");
    setCameraError("");
  }

  function closeBarcodePanel() {
    stopBarcodeScanner();
    setBarcodePanelOpen(false);
    setCameraError("");
  }

  function applyBarcodeLookup(result: FoodBarcodeLookup) {
    const food = result.food;
    const unit = productUnitNameForFood(food, productUnits);
    setBarcodeFoodOverride(food);
    setBarcodeInventoryItems(result.inventory_items ?? []);
    onFormChange({
      ...form,
      kind: "food",
      target_id: String(food.id),
      quantity: unit === "g" ? "100" : "1",
      unit,
    });
    setNutritionSearch("");
    setBarcodeStatus(
      `${food.name} gefunden${
        result.inventory_items.length > 0 ? " - im Bestand vorhanden" : ""
      }.`,
    );
    setBarcodePanelOpen(false);
    setSheetMode("details");
  }

  async function lookupBarcode(code: string) {
    const normalizedBarcode = code.replace(/\D/g, "");
    if (normalizedBarcode.length < 8) {
      setBarcodeStatus("Bitte einen gueltigen EAN-Code eingeben.");
      return;
    }

    try {
      setBarcodeBusy(true);
      setBarcodeStatus("EAN wird gesucht...");
      const result = await lookupFoodByBarcode(normalizedBarcode);
      applyBarcodeLookup(result);
    } catch (error) {
      setBarcodeStatus(
        error instanceof Error
          ? error.message
          : "EAN konnte nicht gefunden werden.",
      );
    } finally {
      setBarcodeBusy(false);
    }
  }

  async function startBarcodeScanner() {
    const Detector = barcodeDetector();
    if (!Detector) {
      setCameraError(
        "Kamera-Scan wird von diesem Browser nicht unterstuetzt. EAN manuell eingeben.",
      );
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Keine Kamera-Schnittstelle verfuegbar.");
      return;
    }

    try {
      setCameraError("");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      const detector = new Detector({
        formats: ["ean_13", "ean_8", "upc_a", "upc_e"],
      });
      scannerRunningRef.current = true;
      setScannerActive(true);

      const scanFrame = async () => {
        if (!scannerRunningRef.current || !videoRef.current) {
          return;
        }
        try {
          const codes = await detector.detect(videoRef.current);
          const rawValue = codes[0]?.rawValue;
          if (rawValue) {
            stopBarcodeScanner();
            setBarcodeInput(rawValue);
            await lookupBarcode(rawValue);
            return;
          }
        } catch {
          setCameraError("Barcode konnte im Kamerabild nicht gelesen werden.");
        }
        scanLoopRef.current = requestAnimationFrame(scanFrame);
      };

      scanLoopRef.current = requestAnimationFrame(scanFrame);
    } catch {
      setCameraError("Kamera konnte nicht gestartet werden.");
      stopBarcodeScanner();
    }
  }

  function matchingInventoryItemsForFood(food: Food) {
    const items = new Map<number, DeductableInventoryItem>();
    for (const item of barcodeInventoryItems) {
      if (item.quantity > 0) {
        items.set(item.id, item);
      }
    }
    for (const item of inventory) {
      const matchesFood = item.food_id === food.id;
      const matchesBarcode = Boolean(food.barcode && item.barcode === food.barcode);
      if ((matchesFood || matchesBarcode) && item.quantity > 0) {
        items.set(item.id, item);
      }
    }
    return Array.from(items.values()).sort((first, second) => {
      const firstExpiry = "expiry_date" in first ? first.expiry_date ?? "" : "";
      const secondExpiry = "expiry_date" in second ? second.expiry_date ?? "" : "";
      return firstExpiry.localeCompare(secondExpiry) || first.id - second.id;
    });
  }

  function getInventoryDeductionPlan(
    food: Food,
    quantity: number,
    unit: string,
  ): InventoryDeduction[] {
    const candidates = matchingInventoryItemsForFood(food);
    let remainingGrams = foodQuantityToGrams(food, quantity, unit, productUnits);
    const deductions: InventoryDeduction[] = [];

    if (!Number.isFinite(remainingGrams) || remainingGrams <= 0) {
      return deductions;
    }

    for (const inventoryItem of candidates) {
      if (remainingGrams <= 0.000001) {
        break;
      }

      const rawAmount = foodQuantityFromGrams(
        food,
        remainingGrams,
        inventoryItem.unit,
        productUnits,
      );
      const amount = Math.min(
        normalizeFractionalQuantityValue(rawAmount),
        inventoryItem.quantity,
      );
      const consumedGrams = foodQuantityToGrams(
        food,
        amount,
        inventoryItem.unit,
        productUnits,
      );

      if (
        !Number.isFinite(amount) ||
        !Number.isFinite(consumedGrams) ||
        amount <= 0 ||
        consumedGrams <= 0
      ) {
        continue;
      }

      deductions.push({ amount, inventoryItem });
      remainingGrams = Math.max(0, remainingGrams - consumedGrams);
    }

    return remainingGrams <= 0.000001 ? deductions : [];
  }

  async function deductInventoryPlan(plan: InventoryDeduction[]) {
    for (const deduction of plan) {
      const deducted = await onInventoryDecrease(
        deduction.inventoryItem.id,
        deduction.amount,
      );
      if (deducted === false) {
        return false;
      }
    }
    return true;
  }

  useEffect(() => {
    if (editingMealLogId !== null) {
      setAddSheetOpen(true);
      setSheetMode("details");
    }
  }, [editingMealLogId]);

  useEffect(() => () => stopBarcodeScanner(), []);

  function selectSlot(slot: number) {
    onFormChange({ ...form, time: timeSlotLabel(slot) });
  }

  function openFoodSearch(slot?: number) {
    stopBarcodeScanner();
    setBarcodeFoodOverride(null);
    setBarcodeInventoryItems([]);
    setBarcodePanelOpen(false);
    setBarcodeStatus("");
    setCameraError("");
    setNutritionSearch("");
    onFormChange({
      ...form,
      kind: "food",
      target_id: "",
      quantity: "1",
      unit: "g",
      time: slot === undefined ? form.time : timeSlotLabel(slot),
    });
    setSheetMode("search");
    setAddSheetOpen(true);
  }

  function openAddAt(slot: number) {
    openFoodSearch(slot);
  }

  function dropMealLog(slot: number) {
    if (!draggedMealLog) {
      return;
    }
    onMove(draggedMealLog, selectedDate, timeSlotLabel(slot));
    setDraggedMealLogId(null);
  }

  function chooseFood(food: Food) {
    const unit = productUnitNameForFood(food, productUnits);
    setBarcodeFoodOverride(null);
    setBarcodeInventoryItems([]);
    onFormChange({
      ...form,
      kind: "food",
      target_id: String(food.id),
      quantity: unit === "g" ? "100" : "1",
      unit,
    });
    setSheetMode("details");
  }

  function chooseRecipe(recipe: Recipe) {
    setBarcodeFoodOverride(null);
    setBarcodeInventoryItems([]);
    onFormChange({
      ...form,
      kind: "recipe",
      target_id: String(recipe.id),
      quantity: "1",
      unit: "serving",
    });
    setSheetMode("details");
  }

  function chooseQuickAdd() {
    setBarcodeFoodOverride(null);
    setBarcodeInventoryItems([]);
    onFormChange({
      ...form,
      kind: "quick",
      target_id: "",
      quantity: "1",
      unit: "quick",
    });
    setSheetMode("details");
  }

  function closeAddSheet() {
    stopBarcodeScanner();
    setAddSheetOpen(false);
    setSheetMode("search");
    setNutritionSearch("");
    setBarcodePanelOpen(false);
    if (editingMealLogId !== null) {
      onCancelEdit();
    }
  }

  async function submitFromSheet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as
      | HTMLButtonElement
      | null;
    const shouldDeductInventory =
      submitter?.dataset.action === "add-and-deduct";
    const deductionPlan = shouldDeductInventory ? inventoryDeductionPlan : [];

    if (shouldDeductInventory && deductionPlan.length === 0) {
      return;
    }

    const saved = await onSubmit();
    if (!saved) {
      return;
    }

    if (shouldDeductInventory) {
      await deductInventoryPlan(deductionPlan);
    }

    stopBarcodeScanner();
    setAddSheetOpen(false);
    setSheetMode("search");
    setNutritionSearch("");
    setBarcodePanelOpen(false);
  }

  return (
    <div className="nutrition-food-log">
      <section className="nutrition-log-shell">
        <div className="nutrition-log-header">
          <div className="nutrition-log-nav">
            <button className="nutrition-icon-button" type="button">
              <Menu size={24} />
            </button>
            <button
              className="nutrition-icon-button"
              onClick={() => onDateChange(moveCalendarView(selectedDate, "day", -1))}
              title="Vorheriger Tag"
              type="button"
            >
              <ChevronLeft size={28} />
            </button>
            <h2>{dateTitle}</h2>
            <button
              className="nutrition-icon-button"
              onClick={() => onDateChange(moveCalendarView(selectedDate, "day", 1))}
              title="Naechster Tag"
              type="button"
            >
              <ChevronRight size={28} />
            </button>
          </div>
          <div className="nutrition-week-strip">
            {weekDates.map((date) => {
              const dateValue = getLocalDate(date);
              const consumedCalories = weekCalorieTotals[dateValue] ?? 0;
              const progress = dayCalorieProgress(dateValue);
              return (
                <button
                  className={dateValue === selectedDate ? "active" : ""}
                  key={dateValue}
                  onClick={() => onDateChange(dateValue)}
                  style={
                    {
                      "--day-progress": `${progress}%`,
                    } as CSSProperties
                  }
                  title={`${formatNumber(consumedCalories, 0)} von ${formatNumber(
                    nutrition.goals.calories,
                    0,
                  )} kcal`}
                  type="button"
                >
                  <span>
                    {new Intl.DateTimeFormat("de-DE", { weekday: "short" })
                      .format(date)
                      .slice(0, 1)}
                  </span>
                  <strong>{date.getDate()}</strong>
                </button>
              );
            })}
          </div>
          <div className="nutrition-macro-strip">
            {macroMeta.map((macro) => (
              <article className={macro.tone} key={macro.key}>
                <strong>
                  {macro.key === "calories"
                    ? formatNumber(nutrition.remaining[macro.key], 0)
                    : `${macro.label.slice(0, 1)} ${formatNumber(
                        nutrition.remaining[macro.key],
                        0,
                      )}`}
                  {" left"}
                </strong>
                <span>
                  <i style={{ width: macroProgress(macro.key) }} />
                </span>
              </article>
            ))}
          </div>
        </div>

        <div className="nutrition-time-grid">
          {timelineSlots.map((slot) => (
            <button
              className={`nutrition-drop-slot ${
                selectedSlot === slot ? "selecting" : ""
              } ${slot % 2 !== 0 ? "half" : ""}`}
              key={`nutrition-slot-${slot}`}
              onClick={() => selectSlot(slot)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                dropMealLog(slot);
              }}
              style={{
                gridColumn: 3,
                gridRow: slot - timelineStartSlot + 1,
              }}
              type="button"
            />
          ))}
          {hourSlots.map((slot) => (
            <div
              className="nutrition-hour-row"
              key={`nutrition-hour-${slot}`}
              style={{ gridRow: slot - timelineStartSlot + 1 }}
            >
              <span>{timeSlotLabel(slot)}</span>
              <button onClick={() => openAddAt(slot)} type="button">
                <Plus size={22} />
              </button>
            </div>
          ))}
          {mealLogSlotGroups.map(({ logs, slot }) => (
            <div
              className={`nutrition-time-entry-stack ${
                logs.length > 1 ? "multiple" : ""
              }`}
              key={`meal-slot-${slot}`}
              style={{
                gridColumn: 3,
                gridRow: `${slot - timelineStartSlot + 1} / ${Math.min(
                  slot - timelineStartSlot + 3,
                  timelineEndSlot - timelineStartSlot + 2,
                )}`,
              }}
            >
              {logs.map((mealLog) => {
                const values = getMealLogMacros(mealLog);

                return (
                  <article
                    className={`nutrition-time-entry ${
                      mealLog.quick_add_name
                        ? "quick"
                        : mealLog.food_id
                          ? "food"
                          : "recipe"
                    } ${editingMealLogId === mealLog.id ? "editing" : ""}`}
                    draggable
                    key={mealLog.id}
                    onDragEnd={() => setDraggedMealLogId(null)}
                    onDragStart={() => setDraggedMealLogId(mealLog.id)}
                  >
                    <button
                      className="nutrition-time-entry-main"
                      onClick={() => onEdit(mealLog)}
                      type="button"
                    >
                      <strong>{getMealLogTitle(mealLog)}</strong>
                      <span>
                        {formatMacroLine(values)}
                        {mealLog.quick_add_name
                          ? ""
                          : ` | ${formatFractionalQuantity(mealLog.quantity)} ${
                              mealLog.unit
                            }`}
                        {mealLog.meal_type ? ` | ${mealLog.meal_type}` : ""}
                      </span>
                    </button>
                    {mealLog.planned_inventory_deduction && (
                      <span
                        className={`nutrition-inventory-status ${
                          mealLog.inventory_deducted_at ? "booked" : "pending"
                        }`}
                      >
                        {mealLog.inventory_deducted_at
                          ? "Bestand gebucht"
                          : "Bestand geplant"}
                      </span>
                    )}
                    {mealLog.planned_inventory_deduction &&
                      !mealLog.inventory_deducted_at && (
                        <button
                          className="nutrition-card-edit"
                          onClick={() => void onDeductMealLogInventory(mealLog.id)}
                          title="Bestand buchen"
                          type="button"
                        >
                          <Check size={17} />
                        </button>
                      )}
                    <button
                      className="nutrition-card-edit"
                      onClick={() => onEdit(mealLog)}
                      title="Bearbeiten"
                      type="button"
                    >
                      <Pencil size={17} />
                    </button>
                  </article>
                );
              })}
            </div>
          ))}
        </div>

        <div className="nutrition-search-actions">
          <button
            className="nutrition-search-pill"
            onClick={() => openFoodSearch()}
            type="button"
          >
            <Search size={24} />
            <span>Lebensmittel suchen</span>
          </button>
          <button
            className="nutrition-barcode-pill"
            onClick={openBarcodePanel}
            type="button"
          >
            <ScanBarcode size={24} />
            <span>EAN</span>
          </button>
        </div>
      </section>

      {addSheetOpen && (
        <ModalBackdrop
          className="nutrition-sheet-backdrop"
          onClose={closeAddSheet}
        >
          <section className="nutrition-add-sheet">
            <div className="nutrition-sheet-grip" />
            <div className="nutrition-sheet-top">
              <button
                className="nutrition-sheet-round"
                onClick={closeAddSheet}
                type="button"
              >
                <X size={24} />
              </button>
              <div className="nutrition-sheet-time">
                <strong>{form.time || "12:00"}</strong>
                <span>{dateTitle}</span>
              </div>
              <div className="nutrition-sheet-mini">
                <strong>
                  {formatNumber(nutrition.totals.calories, 0)} /{" "}
                  {formatNumber(nutrition.goals.calories, 0)}
                </strong>
                <span>
                  {formatNumber(nutrition.totals.protein, 0)} /{" "}
                  {formatNumber(nutrition.goals.protein, 0)} P
                </span>
              </div>
              <button className="nutrition-sheet-round" type="button">
                <ChevronDown size={24} />
              </button>
            </div>

            {sheetMode === "search" ? (
              <>
                {barcodePanelOpen && (
                  <div className="nutrition-barcode-panel">
                    <div className="nutrition-barcode-panel-head">
                      <div>
                        <strong>EAN scannen</strong>
                        <span>Produkt wird nur im Kalorientracker eingetragen.</span>
                      </div>
                      <button
                        className="icon-button"
                        onClick={closeBarcodePanel}
                        title="Scanner schliessen"
                        type="button"
                      >
                        <X size={16} />
                      </button>
                    </div>
                    <div className="nutrition-camera-frame">
                      <video
                        muted
                        playsInline
                        ref={videoRef}
                      />
                      {!scannerActive && (
                        <button
                          className="button secondary"
                          disabled={barcodeBusy}
                          onClick={() => void startBarcodeScanner()}
                          type="button"
                        >
                          <Camera size={16} />
                          Kamera starten
                        </button>
                      )}
                      {scannerActive && (
                        <button
                          className="button secondary"
                          onClick={stopBarcodeScanner}
                          type="button"
                        >
                          <X size={16} />
                          Kamera stoppen
                        </button>
                      )}
                    </div>
                    <form
                      className="nutrition-barcode-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void lookupBarcode(barcodeInput);
                      }}
                    >
                      <label className="nutrition-detail-field">
                        <span>EAN-Code</span>
                        <input
                          inputMode="numeric"
                          onChange={(event) => setBarcodeInput(event.target.value)}
                          placeholder="z.B. 400..."
                          value={barcodeInput}
                        />
                      </label>
                      <button
                        className="button primary"
                        disabled={barcodeBusy}
                        type="submit"
                      >
                        <Search size={16} />
                        {barcodeBusy ? "Suche" : "Eintragen"}
                      </button>
                    </form>
                    {(barcodeStatus || cameraError) && (
                      <div
                        className={`nutrition-barcode-message ${
                          cameraError ? "error" : ""
                        }`}
                      >
                        {cameraError || barcodeStatus}
                      </div>
                    )}
                  </div>
                )}
                <div className="nutrition-search-tabs">
                  <button
                    className={form.kind === "food" ? "active" : ""}
                    onClick={() =>
                      onFormChange({
                        ...form,
                        kind: "food",
                        target_id: "",
                        unit: "g",
                      })
                    }
                    type="button"
                  >
                    <Search size={20} />
                    Search
                  </button>
                  <button
                    className={form.kind === "recipe" ? "active" : ""}
                    onClick={() =>
                      onFormChange({
                        ...form,
                        kind: "recipe",
                        target_id: "",
                        unit: "serving",
                      })
                    }
                    type="button"
                  >
                    <Soup size={20} />
                    Gerichte
                  </button>
                  <button
                    className={form.kind === "quick" ? "active" : ""}
                    onClick={chooseQuickAdd}
                    type="button"
                  >
                    <Gauge size={20} />
                    Quick-Add
                  </button>
                </div>
                {form.kind === "quick" ? (
                  <div className="nutrition-pick-list">
                    <button
                      className="nutrition-pick-item"
                      onClick={chooseQuickAdd}
                      type="button"
                    >
                      <span className="nutrition-pick-icon quick">
                        <Gauge size={24} />
                      </span>
                      <span>
                        <strong>Quick-Add</strong>
                        <small>Freie Naehrwerte</small>
                      </span>
                      <Plus size={20} />
                    </button>
                  </div>
                ) : (
                  <>
                    <label className="nutrition-sheet-search">
                      <Search size={22} />
                      <input
                        autoFocus
                        onChange={(event) => setNutritionSearch(event.target.value)}
                        placeholder={
                          form.kind === "food"
                            ? "Search for a food"
                            : "Gericht suchen"
                        }
                        value={nutritionSearch}
                      />
                    </label>
                    <div className="nutrition-pick-list">
                      {form.kind === "food"
                        ? filteredFoods.map((food) => {
                            const productUnit = productUnitNameForFood(
                              food,
                              productUnits,
                            );
                            const values = getFoodLogMacros(food, 1, productUnit);
                            return (
                              <button
                                className="nutrition-pick-item"
                                key={food.id}
                                onClick={() => chooseFood(food)}
                                type="button"
                              >
                                <span className="nutrition-pick-icon">
                                  <Apple size={24} />
                                </span>
                                <span>
                                  <strong>
                                    {food.name}
                                    {food.brand ? ` By ${food.brand}` : ""}
                                  </strong>
                                  <small>
                                    {formatMacroLine(values)} |{" "}
                                    {formatServingConversion(productUnit, food)}
                                  </small>
                                </span>
                                <Plus size={20} />
                              </button>
                            );
                          })
                        : filteredRecipes.map((recipe) => {
                            const values = getRecipeLogMacros(recipe, 1, "serving");
                            return (
                              <button
                                className="nutrition-pick-item"
                                key={recipe.id}
                                onClick={() => chooseRecipe(recipe)}
                                type="button"
                              >
                                <span className="nutrition-pick-icon">
                                  <Soup size={24} />
                                </span>
                                <span>
                                  <strong>{recipe.name}</strong>
                                  <small>
                                    {formatMacroLine(values)} | 1 serving
                                  </small>
                                </span>
                                <Plus size={20} />
                              </button>
                            );
                          })}
                      {((form.kind === "food" && filteredFoods.length === 0) ||
                        (form.kind === "recipe" && filteredRecipes.length === 0)) && (
                        <EmptyState label="Keine Treffer gefunden" />
                      )}
                    </div>
                  </>
                )}
              </>
            ) : (
              <form className="nutrition-detail-panel" onSubmit={submitFromSheet}>
                <button
                  className="nutrition-back-button"
                  onClick={() => setSheetMode("search")}
                  type="button"
                >
                  <ChevronLeft size={26} />
                  {selectedTargetName}
                </button>
                <div className="nutrition-detail-macros">
                  {macroMeta.map((macro) => (
                    <article className={macro.tone} key={macro.key}>
                      {macroShareLabel(macro.key, selectedTargetMacros) && (
                        <small>
                          {macroShareLabel(macro.key, selectedTargetMacros)}
                        </small>
                      )}
                      <strong>
                        {formatNumber(selectedTargetMacros[macro.key], 1)}
                      </strong>
                      <span>
                        {macro.label}
                        {macro.key !== "calories" ? ` (${macro.unit})` : ""}
                      </span>
                    </article>
                  ))}
                </div>
                {form.kind === "quick" ? (
                  <>
                    <label className="nutrition-detail-field">
                      <span>Name</span>
                      <input
                        onChange={(event) =>
                          onFormChange({ ...form, quick_name: event.target.value })
                        }
                        required
                        value={form.quick_name}
                      />
                    </label>
                    <div className="nutrition-quick-grid">
                      <label className="nutrition-detail-field nutrition-quick-calories">
                        <span>Kalorien</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onFormChange({
                              ...form,
                              quick_calories: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={form.quick_calories}
                        />
                        {quickEstimatedCalories > 0 && (
                          <small className="nutrition-estimate">
                            Aus Makros ca. {formatNumber(quickEstimatedCalories, 0)} kcal
                          </small>
                        )}
                      </label>
                      <label className="nutrition-detail-field">
                        <span>Protein</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onFormChange({
                              ...form,
                              quick_protein: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={form.quick_protein}
                        />
                      </label>
                      <label className="nutrition-detail-field">
                        <span>Fett</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onFormChange({
                              ...form,
                              quick_fat: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={form.quick_fat}
                        />
                      </label>
                      <label className="nutrition-detail-field">
                        <span>Kohlenhydrate</span>
                        <input
                          inputMode="decimal"
                          onChange={(event) =>
                            onFormChange({
                              ...form,
                              quick_carbs: event.target.value,
                            })
                          }
                          pattern={fractionNumberPattern}
                          title="Zahl oder Bruch, z.B. 2/3"
                          value={form.quick_carbs}
                        />
                      </label>
                    </div>
                  </>
                ) : (
                  <>
                    <label className="nutrition-quantity-box">
                      <input
                        inputMode="decimal"
                        onChange={(event) =>
                          onFormChange({ ...form, quantity: event.target.value })
                        }
                        pattern={fractionNumberPattern}
                        required
                        title="Zahl oder Bruch, z.B. 2/3"
                        value={form.quantity}
                      />
                      <span>{form.unit}</span>
                    </label>
                    <div className="nutrition-unit-row">
                      {(form.kind === "food"
                        ? foodUnitOptions(selectedFood, productUnits, form.unit)
                        : ["serving", "recipe"]
                      ).map((unit) => (
                        <button
                          className={form.unit === unit ? "active" : ""}
                          key={unit}
                          onClick={() => onFormChange({ ...form, unit })}
                          type="button"
                        >
                          {unit}
                        </button>
                      ))}
                    </div>
                  </>
                )}
                <label className="nutrition-detail-field">
                  <span>Art</span>
                  <input
                    onChange={(event) =>
                      onFormChange({ ...form, meal_type: event.target.value })
                    }
                    placeholder="Fruehstueck, Mittag, Snack"
                    value={form.meal_type}
                  />
                </label>
                <label className="nutrition-detail-field">
                  <span>Notizen</span>
                  <textarea
                    onChange={(event) =>
                      onFormChange({ ...form, notes: event.target.value })
                    }
                    value={form.notes}
                  />
                </label>
                <div className="nutrition-detail-actions">
                  {editingMealLogId !== null && (
                    <button
                      className="button danger"
                      onClick={() => {
                        onDelete(editingMealLogId);
                        closeAddSheet();
                      }}
                      type="button"
                    >
                      <Trash2 size={16} />
                      Entfernen
                    </button>
                  )}
                  <button
                    className="button secondary"
                    onClick={closeAddSheet}
                    type="button"
                  >
                    Abbrechen
                  </button>
                  {editingMealLogId === null ? (
                    <>
                      <button
                        className="button primary"
                        data-action="add"
                        type="submit"
                      >
                        Hinzufügen
                      </button>
                      <button
                        className="button primary"
                        data-action="add-and-deduct"
                        disabled={!canAddAndDeduct}
                        title={
                          canAddAndDeduct
                            ? `Bucht ${inventoryDeductionSummary} aus dem Bestand ab`
                            : "Nur für Lebensmittel mit ausreichendem Bestand"
                        }
                        type="submit"
                      >
                        <Minus size={16} />
                        Hinzufügen und vom Bestand abziehen
                      </button>
                    </>
                  ) : (
                    <button className="button primary" type="submit">
                      Speichern
                    </button>
                  )}
                </div>
              </form>
            )}
          </section>
        </ModalBackdrop>
      )}
    </div>
  );
}

function ShoppingPage({
  foods,
  form,
  items,
  onImportToInventory,
  onCheck,
  onDelete,
  onIncrease,
  onFormChange,
  onGenerate,
  productUnits,
  onSubmit,
}: {
  foods: Food[];
  form: ShoppingForm;
  items: ShoppingListItem[];
  onImportToInventory: (
    unknownItemAction?: ShoppingListInventoryUnknownAction,
  ) => Promise<ShoppingListInventoryImportResult>;
  onCheck: (item: ShoppingListItem) => void;
  onDelete: (id: number) => void;
  onIncrease: (item: ShoppingListItem) => void;
  onFormChange: (value: ShoppingForm) => void;
  onGenerate: () => void;
  productUnits: ProductUnit[];
  onSubmit: (event: FormEvent) => void;
}) {
  const [inventoryImportBusy, setInventoryImportBusy] = useState(false);
  const [inventoryImportResult, setInventoryImportResult] =
    useState<ShoppingListInventoryImportResult | null>(null);
  const foodOptions = foods
    .slice()
    .sort((first, second) => first.name.localeCompare(second.name, "de"));
  const selectedFood =
    foods.find((food) => String(food.id) === form.food_id) ?? null;
  const selectedFoodUnit = selectedFood
    ? productUnitNameForFood(selectedFood, productUnits)
    : "";
  const openItems = items.filter((item) => !item.is_checked);

  async function importToInventory(
    unknownItemAction: ShoppingListInventoryUnknownAction = "ask",
  ) {
    try {
      setInventoryImportBusy(true);
      const result = await onImportToInventory(unknownItemAction);
      setInventoryImportResult(result);
    } finally {
      setInventoryImportBusy(false);
    }
  }

  function selectFood(foodId: string) {
    const food = foods.find((item) => String(item.id) === foodId);
    const unit = food ? productUnitNameForFood(food, productUnits) : form.unit;
    onFormChange({
      ...form,
      food_id: foodId,
      quantity: form.quantity || "1",
      unit: unit || "pcs",
    });
  }

  function selectSource(source: ShoppingForm["source"]) {
    onFormChange({
      ...initialShoppingForm,
      source,
      notes: form.notes,
      quantity: form.quantity || "1",
      unit: source === "text" ? "pcs" : form.unit,
    });
  }

  const canSubmit =
    form.source === "food" ? form.food_id !== "" : form.name.trim() !== "";

  return (
    <div className="work-layout">
      <section className="section wide">
        <div className="section-header">
          <div>
            <p className="eyebrow">{items.filter((item) => !item.is_checked).length} offen</p>
            <h2>Einkaufsliste</h2>
          </div>
          <div className="shopping-header-actions">
            <button
              className="button primary"
              disabled={openItems.length === 0 || inventoryImportBusy}
              onClick={() => void importToInventory()}
              type="button"
            >
              <Database size={16} />
              {inventoryImportBusy ? "Wird uebernommen" : "In Bestand uebernehmen"}
            </button>
            <button className="button secondary" onClick={onGenerate} type="button">
              <RefreshCw size={16} />
              Aus Lagerbestand
            </button>
          </div>
        </div>
        {inventoryImportResult && (
          <div
            className={`shopping-import-message ${
              inventoryImportResult.requires_decision ? "needs-decision" : "done"
            }`}
          >
            <div>
              <strong>{inventoryImportResult.message}</strong>
              {inventoryImportResult.requires_decision ? (
                <span>
                  {inventoryImportResult.unknown_items
                    .map((item) => `${item.name} (${formatFractionalQuantity(item.quantity)} ${item.unit})`)
                    .join(", ")}
                </span>
              ) : (
                <span>
                  {inventoryImportResult.imported_count} uebernommen,{" "}
                  {inventoryImportResult.deleted_shopping_item_ids.length} von der Liste entfernt
                </span>
              )}
            </div>
            {inventoryImportResult.requires_decision && (
              <div className="shopping-import-actions">
                <button
                  className="button primary"
                  disabled={inventoryImportBusy}
                  onClick={() => void importToInventory("create")}
                  type="button"
                >
                  Ins System uebernehmen
                </button>
                <button
                  className="button danger"
                  disabled={inventoryImportBusy}
                  onClick={() => void importToInventory("delete")}
                  type="button"
                >
                  Von Liste loeschen
                </button>
                <button
                  className="button secondary"
                  disabled={inventoryImportBusy}
                  onClick={() => void importToInventory("keep")}
                  type="button"
                >
                  Stehen lassen
                </button>
              </div>
            )}
          </div>
        )}
        <div className="shopping-list">
          {items.length === 0 ? (
            <EmptyState label="Keine Artikel vorhanden" />
          ) : (
            items.map((item) => (
              <article
                className={`shopping-item ${item.is_checked ? "checked" : ""}`}
                key={item.id}
              >
                <button
                  className="check-button"
                  onClick={() => onCheck(item)}
                  title={item.is_checked ? "Zuruecksetzen" : "Abhaken"}
                  type="button"
                >
                  {item.is_checked ? <X size={16} /> : <Check size={16} />}
                </button>
                <div>
                  <strong>{item.name}</strong>
                  <span>
                    {formatFractionalQuantity(item.quantity)} {item.unit}
                    {item.store ? ` · ${item.store}` : ""}
                  </span>
                </div>
                <button
                  className="icon-button"
                  onClick={() => onIncrease(item)}
                  title="Menge erhoehen"
                  type="button"
                >
                  <Plus size={16} />
                </button>
                <button
                  className="icon-button danger"
                  onClick={() => onDelete(item.id)}
                  title="Loeschen"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </article>
            ))
          )}
        </div>
      </section>

      <Panel title="Einkaufsartikel hinzufügen">
        <form className="form-grid shopping-add-form" onSubmit={onSubmit}>
          <div className="shopping-source-tabs" role="tablist" aria-label="Quelle">
            {[
              { id: "food", label: "Lebensmittel" },
              { id: "text", label: "Freitext" },
            ].map((source) => (
              <button
                className={form.source === source.id ? "active" : ""}
                key={source.id}
                onClick={() => selectSource(source.id as ShoppingForm["source"])}
                aria-selected={form.source === source.id}
                role="tab"
                type="button"
              >
                {source.label}
              </button>
            ))}
          </div>

          {form.source === "food" && (
            <>
              <label>
                <span>Lebensmittel</span>
                <select
                  onChange={(event) => selectFood(event.target.value)}
                  required
                  value={form.food_id}
                >
                  <option value="">Lebensmittel auswaehlen</option>
                  {foodOptions.map((food) => (
                    <option key={food.id} value={food.id}>
                      {formatFoodSuggestionLabel(food)}
                    </option>
                  ))}
                </select>
              </label>
              {selectedFood && (
                <div className="shopping-inventory-summary">
                  <span>Umrechnung</span>
                  <strong>
                    {formatServingConversion(
                      selectedFoodUnit,
                      selectedFood,
                    )}
                  </strong>
                </div>
              )}
              {selectedFoodUnit && (
                <div className="shopping-inventory-summary">
                  <span>Einheit</span>
                  <strong>{selectedFoodUnit}</strong>
                </div>
              )}
            </>
          )}

          {form.source === "text" && (
            <TextInput
              label="Artikelname"
              onChange={(name) => onFormChange({ ...form, name })}
              required
              value={form.name}
            />
          )}
          <FractionNumberInput
            label="Einkaufsmenge"
            onChange={(quantity) => onFormChange({ ...form, quantity })}
            value={form.quantity}
          />
          {form.source === "text" && (
            <TextInput
              label="Einheit"
              onChange={(unit) => onFormChange({ ...form, unit })}
              required
              value={form.unit}
            />
          )}
          <TextInput
            label="Notiz"
            onChange={(notes) => onFormChange({ ...form, notes })}
            value={form.notes}
          />
          <button
            className="button primary full shopping-add-submit"
            disabled={!canSubmit}
            type="submit"
          >
            <Plus size={16} />
            Zur Einkaufsliste
          </button>
        </form>
      </Panel>
    </div>
  );
}

function SettingsPage({
  activeUser,
  apiBaseUrl,
  csvImportForm,
  csvImportResult,
  csvImportRunning,
  editingUserId,
  form,
  onCancelEditing,
  onCsvImportFormChange,
  onCsvImportSubmit,
  onDelete,
  onEdit,
  onFormChange,
  onSettingsFormChange,
  onSettingsSubmit,
  onSubmit,
  settingsForm,
  userId,
  users,
  onUserIdChange,
}: {
  activeUser: User | null;
  apiBaseUrl: string;
  csvImportForm: CsvImportForm;
  csvImportResult: CsvImportResult | null;
  csvImportRunning: boolean;
  editingUserId: number | null;
  form: UserForm;
  onCancelEditing: () => void;
  onCsvImportFormChange: (value: CsvImportForm) => void;
  onCsvImportSubmit: (event: FormEvent) => void;
  onDelete: (user: User) => void;
  onEdit: (user: User) => void;
  onFormChange: (value: UserForm) => void;
  onSettingsFormChange: (value: UserSettingsForm) => void;
  onSettingsSubmit: (event: FormEvent) => void;
  onSubmit: (event: FormEvent) => void;
  settingsForm: UserSettingsForm;
  userId: number;
  users: User[];
  onUserIdChange: (value: number) => void;
}) {
  const goals = macroGoalsFromPercentages(settingsForm);
  const percentTotal = macroPercentTotal(settingsForm);
  const isMacroBalanceValid = Math.abs(percentTotal - 100) <= 0.01;

  return (
    <div className="settings-layout">
      <section className="section settings-panel">
        <div className="settings-row">
          <span>API</span>
          <strong>{apiBaseUrl}</strong>
        </div>
        <div className="settings-row">
          <span>Aktiver User</span>
          <select
            onChange={(event) => onUserIdChange(toNumber(event.target.value, 1))}
            value={userId}
          >
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.username}
              </option>
            ))}
          </select>
        </div>
        <div className="user-list">
          {users.map((user) => (
            <article className="user-row" key={user.id}>
              <div className="user-avatar">
                <strong>{user.username.slice(0, 1)}</strong>
              </div>
              <div>
                <strong>{user.username}</strong>
                <span>@{user.username}</span>
              </div>
              <div className="user-actions">
                <button
                  className="icon-button"
                  onClick={() => onEdit(user)}
                  title="User bearbeiten"
                  type="button"
                >
                  <Pencil size={16} />
                </button>
                <button
                  className="icon-button danger"
                  disabled={users.length <= 1}
                  onClick={() => onDelete(user)}
                  title={
                    users.length <= 1
                      ? "Mindestens ein User bleibt erhalten"
                      : "User loeschen"
                  }
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="settings-side">
        <Panel title="Theme und Ziele">
          <form className="settings-preferences-form" onSubmit={onSettingsSubmit}>
            <div className="active-user-chip">
              <span>Aktiver User</span>
              <strong>{activeUser?.username ?? "-"}</strong>
            </div>

            <div className="theme-option-grid">
              {themeOptions.map((theme) => (
                <button
                  className={`theme-option ${
                    settingsForm.theme === theme.id ? "active" : ""
                  }`}
                  key={theme.id}
                  onClick={() =>
                    onSettingsFormChange({ ...settingsForm, theme: theme.id })
                  }
                  type="button"
                >
                  <span className="theme-swatches" aria-hidden="true">
                    {theme.swatches.map((color) => (
                      <i key={color} style={{ background: color }} />
                    ))}
                  </span>
                  <span>
                    <strong>{theme.label}</strong>
                  </span>
                </button>
              ))}
            </div>

            <NumberInput
              label="Kalorienziel"
              min="1"
              onChange={(daily_calories) =>
                onSettingsFormChange({ ...settingsForm, daily_calories })
              }
              required
              step="1"
              value={settingsForm.daily_calories}
            />

            <div className="macro-settings-grid">
              <NumberInput
                label="Protein %"
                min="0"
                onChange={(protein_percent) =>
                  onSettingsFormChange({ ...settingsForm, protein_percent })
                }
                required
                step="0.1"
                value={settingsForm.protein_percent}
              />
              <NumberInput
                label="Fett %"
                min="0"
                onChange={(fat_percent) =>
                  onSettingsFormChange({ ...settingsForm, fat_percent })
                }
                required
                step="0.1"
                value={settingsForm.fat_percent}
              />
              <NumberInput
                label="Kohlenhydrate %"
                min="0"
                onChange={(carbs_percent) =>
                  onSettingsFormChange({ ...settingsForm, carbs_percent })
                }
                required
                step="0.1"
                value={settingsForm.carbs_percent}
              />
            </div>

            <div
              className={`macro-balance ${
                isMacroBalanceValid ? "balanced" : "unbalanced"
              }`}
            >
              <span>Summe</span>
              <strong>{formatNumber(percentTotal, 1)}%</strong>
            </div>

            <div className="calculated-macro-grid">
              {macroMeta.map((macro) => (
                <article className={macro.tone} key={macro.key}>
                  <span>{macro.label}</span>
                  <strong>
                    {formatNumber(goals[macro.key], macro.key === "calories" ? 0 : 1)}
                  </strong>
                  <small>{macro.unit}</small>
                </article>
              ))}
            </div>

            <button
              className="button primary full"
              disabled={!activeUser || !isMacroBalanceValid}
              type="submit"
            >
              <CheckCircle2 size={16} />
              Einstellungen speichern
            </button>
          </form>
        </Panel>

        <Panel title={editingUserId === null ? "User anlegen" : "User bearbeiten"}>
          <form className="form-grid" onSubmit={onSubmit}>
            <TextInput
              label="Username"
              onChange={(username) => onFormChange({ ...form, username })}
              required
              value={form.username}
            />
            <TextInput
              label="Passwort"
              onChange={(password) => onFormChange({ ...form, password })}
              required
              type="password"
              value={form.password}
            />
            <div className="form-actions">
              <button className="button primary" type="submit">
                {editingUserId === null ? <Plus size={16} /> : <Pencil size={16} />}
                {editingUserId === null ? "Anlegen" : "Speichern"}
              </button>
              {editingUserId !== null && (
                <button
                  className="button secondary"
                  onClick={onCancelEditing}
                  type="button"
                >
                  <X size={16} />
                  Abbrechen
                </button>
              )}
            </div>
          </form>
        </Panel>

        <Panel title="Grocy CSV-Import">
          <form className="settings-import-form" onSubmit={onCsvImportSubmit}>
            <TextInput
              label="CSV-Ordner"
              onChange={(directory) =>
                onCsvImportFormChange({ ...csvImportForm, directory })
              }
              required
              value={csvImportForm.directory}
            />
            <label className="check-field">
              <input
                checked={csvImportForm.dryRun}
                onChange={(event) =>
                  onCsvImportFormChange({
                    ...csvImportForm,
                    dryRun: event.target.checked,
                  })
                }
                type="checkbox"
              />
              <span>Testlauf</span>
            </label>
            <button
              className="button primary full"
              disabled={csvImportRunning}
              type="submit"
            >
              <Database size={16} />
              {csvImportRunning ? "Import laeuft" : "Import starten"}
            </button>
          </form>

          {csvImportResult && (
            <div className="csv-import-result">
              <div className="csv-import-meta">
                <span>{csvImportResult.dry_run ? "Testlauf" : "Import"}</span>
                <strong>{csvImportResult.directory}</strong>
              </div>
              <div className="csv-import-grid">
                {Object.entries(csvImportResult.imported).map(([key, value]) => (
                  <article key={key}>
                    <strong>{key.replace(/_/g, " ")}</strong>
                    <span>
                      +{value.created ?? 0} / {value.updated ?? 0} /{" "}
                      {value.skipped ?? 0}
                    </span>
                  </article>
                ))}
              </div>
              {csvImportResult.warnings.length > 0 && (
                <div className="csv-import-warnings">
                  {csvImportResult.warnings.slice(0, 4).map((warning) => (
                    <span key={warning}>{warning}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Panel({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function useCloseOnOutsideClick<TElement extends HTMLElement>(
  active: boolean,
  onClose: () => void,
) {
  const containerRef = useRef<TElement | null>(null);

  useEffect(() => {
    if (!active) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (!containerRef.current?.contains(target)) {
        onClose();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [active, onClose]);

  return containerRef;
}

function ModalBackdrop({
  children,
  className = "modal-backdrop",
  onClose,
  role = "dialog",
}: {
  children: React.ReactNode;
  className?: string;
  onClose: () => void;
  role?: "dialog" | "presentation";
}) {
  function handleBackdropClick(event: ReactMouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      onClose();
    }
  }

  return (
    <div
      aria-modal={role === "dialog" ? true : undefined}
      className={className}
      onClick={handleBackdropClick}
      role={role}
    >
      {children}
    </div>
  );
}

function TextInput({
  inputMode,
  label,
  maxLength,
  min,
  onChange,
  pattern,
  required,
  step,
  title,
  type = "text",
  value,
}: {
  inputMode?:
    | "decimal"
    | "email"
    | "none"
    | "numeric"
    | "search"
    | "tel"
      | "text"
      | "url";
  label: string;
  maxLength?: number;
  min?: string;
  onChange: (value: string) => void;
  pattern?: string;
  required?: boolean;
  step?: string;
  title?: string;
  type?: string;
  value: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        inputMode={inputMode}
        maxLength={maxLength}
        min={min}
        onChange={(event) => onChange(event.target.value)}
        pattern={pattern}
        required={required}
        step={step}
        title={title}
        type={type}
        value={value}
      />
    </label>
  );
}

function NumberInput({
  label,
  min,
  onChange,
  required,
  step,
  value,
}: {
  label: string;
  min?: string;
  onChange: (value: string) => void;
  required?: boolean;
  step?: string;
  value: string;
}) {
  return (
    <TextInput
      label={label}
      min={min}
      onChange={onChange}
      required={required}
      step={step}
      type="number"
      value={value}
    />
  );
}

const fractionNumberPattern =
  "\\s*\\d+(?:[,.]\\d+)?" +
  "(?:\\s+\\d+(?:[,.]\\d+)?\\s*/\\s*\\d+(?:[,.]\\d+)?|" +
  "\\s*/\\s*\\d+(?:[,.]\\d+)?)?\\s*";

function FractionNumberInput({
  label,
  onChange,
  required,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  value: string;
}) {
  return (
    <TextInput
      inputMode="decimal"
      label={label}
      onChange={onChange}
      pattern={fractionNumberPattern}
      required={required}
      title="Zahl oder Bruch, z.B. 2/3"
      value={value}
    />
  );
}

function DateInput({
  label,
  onChange,
  required,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  value: string;
}) {
  return (
    <TextInput
      label={label}
      onChange={onChange}
      required={required}
      type="date"
      value={value}
    />
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}

function StatusBadge({
  label,
  status,
}: {
  label: string;
  status: InventoryStatus;
}) {
  return <span className={`status-badge ${status}`}>{label}</span>;
}

function WarningCount({
  label,
  onClick,
  tone,
  value,
}: {
  label: string;
  onClick?: () => void;
  tone: InventoryStatus;
  value: number;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      className={`warning-count ${tone} ${onClick ? "dashboard-warning-link" : ""}`}
      onClick={onClick}
      type={onClick ? "button" : undefined}
    >
      <strong>{value}</strong>
      <span>{label}</span>
    </Tag>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
