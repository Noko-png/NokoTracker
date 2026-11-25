import type { MealLog, MealPrepSelection } from "./api/client";
import { addDays, dateFromLocalValue, getLocalDate } from "./calendar";

export type MealPrepSlotKey = MealPrepSelection["meal_type"];

type MealPrepSlot = {
  id: MealPrepSlotKey;
  label: string;
  time: string;
  legacyLabel?: string;
};

export const mealPrepSource = "mealprep";
export const mealPrepSlots: readonly MealPrepSlot[] = [
  { id: "breakfast", label: "Frühstück", time: "08:00", legacyLabel: "Fruehstueck" },
  { id: "lunch", label: "Mittagessen", time: "12:30", legacyLabel: "Mittag" },
  { id: "dinner", label: "Abendessen", time: "18:30" },
];

export function mealPrepWeekDates(startDate: string) {
  const firstDay = dateFromLocalValue(startDate);
  return Array.from({ length: 7 }, (_, offset) => addDays(firstDay, offset));
}

export function isMealPrepSlotLog(mealLog: MealLog, day: string, slot: MealPrepSlot, userId: number) {
  if (mealLog.meal_source !== mealPrepSource || (mealLog.user_id != null && mealLog.user_id !== userId)) {
    return false;
  }
  const type = mealLog.meal_type?.trim().toLowerCase() ?? "";
  return (type === slot.id || type === slot.label.toLowerCase() || type === slot.legacyLabel?.toLowerCase())
    && getLocalDate(new Date(mealLog.eaten_at)) === day;
}
