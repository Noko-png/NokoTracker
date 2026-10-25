import { useId } from "react";
import {
  type CalendarRecurrenceForm,
  addDays,
  calendarWeekStart,
  dateFromLocalValue,
  getLocalDate,
  getRecurrenceStarts,
  recurrenceDescription,
  recurrenceFormError,
  recurrenceFormRule,
  recurrenceUnit,
} from "./calendar";

const formatDate = (date: Date) => date.toLocaleDateString("de-DE", {
  weekday: "short", day: "2-digit", month: "2-digit", year: "numeric",
});

export function CalendarRecurrenceFields({ form, onChange }: {
  form: CalendarRecurrenceForm;
  onChange: (change: Partial<CalendarRecurrenceForm>) => void;
}) {
  const hintId = useId();
  const frequency = form.recurrence_frequency;
  const repeating = frequency !== "none";
  const error = recurrenceFormError(form);
  const start = dateFromLocalValue(form.date);
  const validDate = Number.isFinite(start.getTime());
  const grouped = frequency === "weekdays" || frequency === "weekends";
  const unit = recurrenceUnit(frequency);
  const preview = repeating && !error
    ? [...getRecurrenceStarts(recurrenceFormRule(form), new Date(9999, 11, 31), 6)]
    : [];

  return (
    <div className="calendar-recurrence">
      <label>
        <span>Wiederholung</span>
        <select
          value={frequency}
          onChange={(event) => {
            const next = event.target.value as CalendarRecurrenceForm["recurrence_frequency"];
            onChange({
              recurrence_frequency: next,
              recurrence_interval: "1",
              recurrence_until: next === "none" ? "" : form.recurrence_until,
            });
          }}
        >
          <option value="none">Keine – einmaliger Termin</option>
          <option value="daily">Täglich</option>
          <option value="weekly">Wöchentlich – am gleichen Wochentag</option>
          <option value="weekdays">Montag bis Freitag</option>
          <option value="weekends">Samstag und Sonntag</option>
          <option value="monthly">Monatlich</option>
          <option value="yearly">Jährlich</option>
        </select>
      </label>
      {repeating && (
        <>
          <label>
            <span>Wiederholen alle</span>
            <span className="calendar-recurrence-interval">
              <input
                aria-describedby={hintId}
                aria-label={`Abstand in ${unit}`}
                inputMode="numeric"
                min="1"
                max="365"
                step="1"
                required
                type="number"
                value={form.recurrence_interval}
                onChange={(event) => onChange({ recurrence_interval: event.target.value })}
              />
              <span>{Number(form.recurrence_interval) === 1
                ? { Tage: "Tag", Wochen: "Woche", Monate: "Monat", Jahre: "Jahr" }[unit]
                : unit}</span>
            </span>
          </label>
          <label>
            <span>Wiederholen bis (optional)</span>
            <input
              min={form.date}
              type="date"
              value={form.recurrence_until}
              onChange={(event) => onChange({ recurrence_until: event.target.value })}
            />
            <small>Leer lassen für eine Serie ohne Ende. Der gewählte Tag zählt mit.</small>
          </label>
          <div className="calendar-recurrence-preview" id={hintId} aria-live="polite">
            {error ? <p className="calendar-recurrence-error" role="alert">{error}</p> : (
              <>
                <strong>{recurrenceDescription(form)}</strong>
                {grouped && validDate && Number(form.recurrence_interval) > 1 && (
                  <p>
                    Startwoche: {formatDate(calendarWeekStart(start))} bis {formatDate(addDays(calendarWeekStart(start), 6))}.
                    {" "}Danach {Number(form.recurrence_interval) - 1 === 1 ? "eine Woche" : `${Number(form.recurrence_interval) - 1} Wochen`} Pause.
                  </p>
                )}
                {frequency === "monthly" && validDate && start.getDate() > 28 && (
                  <p>In kürzeren Monaten am letzten Tag; danach wieder am {start.getDate()}.</p>
                )}
                {frequency === "yearly" && validDate && start.getMonth() === 1 && start.getDate() === 29 && (
                  <p>In Jahren ohne 29. Februar am 28. Februar.</p>
                )}
                <p>{form.recurrence_until ? `Bis einschließlich ${formatDate(dateFromLocalValue(form.recurrence_until))}.` : "Ohne Enddatum."}</p>
                <span className="calendar-recurrence-preview-label">Vorschau ab Startdatum</span>
                <ol>
                  {preview.map((date) => <li key={getLocalDate(date)}><time dateTime={getLocalDate(date)}>{formatDate(date)}</time></li>)}
                </ol>
                <small>Jeweils mit der oben gewählten Uhrzeit und Dauer.</small>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
