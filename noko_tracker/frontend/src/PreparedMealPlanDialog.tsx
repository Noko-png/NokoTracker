import { Check, Plus } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { MealLog, MealPrepSelection } from "./api/client";
import { getLocalDate } from "./calendar";
import { isMealPrepSlotLog, mealPrepSlots, mealPrepWeekDates } from "./mealPrep";

const shortDate = new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
const fullDate = new Intl.DateTimeFormat("de-DE", { weekday: "long", day: "numeric", month: "long" });

function slotKey(slot: MealPrepSelection) {
  return `${slot.day}/${slot.meal_type}`;
}

export function PreparedMealPlanDialog({
  recipeName, portions, mealLogs, userId, onClose, onSave,
}: {
  recipeName: string;
  portions: number;
  mealLogs: MealLog[];
  userId: number;
  onClose: () => void;
  onSave: (startDate: string, slots: MealPrepSelection[]) => Promise<void>;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inFlight = useRef(false);
  const [startDate] = useState(getLocalDate);
  const [slots, setSlots] = useState<MealPrepSelection[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  const week = mealPrepWeekDates(startDate).map((date) => ({ date, day: getLocalDate(date) }));
  const occupied = new Set<string>();
  for (const { day } of week) {
    for (const slot of mealPrepSlots) {
      if (mealLogs.some((log) => isMealPrepSlotLog(log, day, slot, userId))) {
        occupied.add(slotKey({ day, meal_type: slot.id }));
      }
    }
  }
  const selected = slots.filter((slot) => !occupied.has(slotKey(slot)));
  const selectedKeys = new Set(selected.map(slotKey));

  function toggleSlot(slot: MealPrepSelection) {
    const key = slotKey(slot);
    setError("");
    if (selectedKeys.has(key)) {
      setSlots(selected.filter((entry) => slotKey(entry) !== key));
    } else if (selected.length < portions && !occupied.has(key)) {
      setSlots([...selected, slot]);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || selected.length === 0 || selected.length > portions) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await onSave(startDate, selected);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Die Portionen konnten nicht geplant werden.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <dialog
      aria-labelledby={titleId}
      aria-modal="true"
      className="modal-panel prepared-meal-dialog"
      onCancel={(event) => {
        event.preventDefault();
        if (!inFlight.current) onClose();
      }}
      ref={dialogRef}
    >
      <form onSubmit={submit}>
        <header>
          <h2 id={titleId}>Portionen einplanen</h2>
          <p>{recipeName}</p>
        </header>
        <table className="prepared-meal-grid">
          <thead>
            <tr>
              <th scope="col">Tag</th>
              {mealPrepSlots.map((slot) => <th key={slot.id} scope="col">{slot.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {week.map(({ day, date }) => (
              <tr key={day}>
                <th scope="row"><time dateTime={day}>{shortDate.format(date)}</time></th>
                {mealPrepSlots.map((meal) => {
                  const slot = { day, meal_type: meal.id };
                  const key = slotKey(slot);
                  const taken = occupied.has(key);
                  const pressed = selectedKeys.has(key);
                  return (
                    <td key={meal.id}>
                      <button
                        aria-label={`${meal.label}, ${fullDate.format(date)}${taken ? ", belegt" : ""}`}
                        aria-pressed={pressed}
                        className="prepared-meal-slot"
                        data-meal-type={meal.id}
                        disabled={busy || taken || (!pressed && selected.length >= portions)}
                        onClick={() => toggleSlot(slot)}
                        type="button"
                      >
                        {taken ? "Belegt" : pressed ? <Check size={18} aria-hidden="true" /> : <Plus size={18} aria-hidden="true" />}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p aria-live="polite" className="prepared-meal-count">
          {selected.length} von {portions} {portions === 1 ? "Portion" : "Portionen"} ausgewählt
        </p>
        {error && <p className="notice error" role="alert">{error}</p>}
        <div className="form-actions">
          <button className="button secondary" disabled={busy} onClick={onClose} type="button">Abbrechen</button>
          <button className="button primary" disabled={busy || selected.length === 0} type="submit">
            {busy ? "Wird gespeichert …" : "Plan speichern"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
