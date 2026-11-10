import { CalendarDays, CheckCircle2, Dumbbell, Pause, Undo2 } from "lucide-react";
import type { CalendarEvent, CalendarGroup, TrainingPlan, TrainingSession } from "./api/client";
import { addDays, dateFromLocalValue, getCalendarOccurrences, getLocalDate, type CalendarOccurrence } from "./calendar";

export function isTrainingOccurrenceCompleted(occurrence: CalendarOccurrence, sessions: TrainingSession[]) {
  return sessions.some((session) => session.calendar_event_id === occurrence.event.id &&
    !!session.calendar_occurrence_start_at &&
    new Date(session.calendar_occurrence_start_at).getTime() === occurrence.occurrenceStartAt.getTime());
}

type Actions = {
  busy: boolean;
  onStart: (occurrence: CalendarOccurrence) => void;
  onSkip: (occurrence: CalendarOccurrence) => void;
};

export function TrainingOccurrenceActions({ occurrence, sessions, busy, onStart, onSkip }: Actions & {
  occurrence: CalendarOccurrence;
  sessions: TrainingSession[];
}) {
  if (!occurrence.event.training_plan_id) return null;
  if (isTrainingOccurrenceCompleted(occurrence, sessions)) {
    return <div className="training-occurrence-completed"><CheckCircle2 size={16} />Absolviert</div>;
  }
  return <div className="training-occurrence-actions">
    <button className="button primary" disabled={busy} onClick={() => onStart(occurrence)} type="button">
      <Dumbbell size={16} />Training starten
    </button>
    {occurrence.event.recurrence_frequency === "cycle" && (
      <button className="button secondary" disabled={busy} onClick={() => onSkip(occurrence)} type="button"
        title="Einen Pausentag einfügen und dieses sowie alle folgenden Trainings um einen Tag verschieben">
        <Pause size={16} />Skip / 1 Tag Pause
      </button>
    )}
  </div>;
}

export function TrainingPauseHistory({ events, busy, onUndo, selectedDate }: {
  events: CalendarEvent[];
  busy: boolean;
  onUndo: (eventId: number, shiftId: number) => void;
  selectedDate?: string;
}) {
  const pauses = events.flatMap((event) => {
    const shifts = [...(event.shifts ?? [])].sort((first, second) => first.id - second.id);
    return shifts.map((shift, index) => {
      let pauseDate = new Date(shift.occurrence_start_at);
      for (const later of shifts.slice(index + 1)) {
        if (pauseDate >= new Date(later.occurrence_start_at)) pauseDate = addDays(pauseDate, later.days);
      }
      return { event, shift, pauseDate, latest: shift.id === shifts[shifts.length - 1]?.id };
    }).filter(({ pauseDate }) => !selectedDate || getLocalDate(pauseDate) === selectedDate).slice(-3);
  });
  if (!pauses.length) return null;
  return <div className="training-pause-history" aria-live="polite">
    {pauses.map(({ event, shift, pauseDate, latest }) => <div className="training-pause-row" key={shift.id}>
      <Pause size={16} />
      <span><strong>Zusätzliche Pause · {event.title}</strong>
        <small>{pauseDate.toLocaleDateString("de-DE")} · Training und Folgeeinheiten um {shift.days} Tag verschoben</small>
      </span>
      {latest && <button className="button secondary" disabled={busy} onClick={() => onUndo(event.id, shift.id)} type="button">
        <Undo2 size={16} />Rückgängig
      </button>}
    </div>)}
  </div>;
}

export function TrainingSchedulePanel({ events, groups, plans, sessions, busy, onStart, onSkip, onUndo, onSchedule }: Actions & {
  events: CalendarEvent[];
  groups: CalendarGroup[];
  plans: TrainingPlan[];
  sessions: TrainingSession[];
  onUndo: (eventId: number, shiftId: number) => void;
  onSchedule: (plan?: TrainingPlan) => void;
}) {
  const planIds = new Set(plans.map((plan) => plan.id));
  const linkedEvents = events.filter((event) => event.training_plan_id && planIds.has(event.training_plan_id));
  const today = dateFromLocalValue(getLocalDate());
  const seen = new Set<string>();
  const upcoming = getCalendarOccurrences(events, today, addDays(today, 90), groups)
    .filter((occurrence) => {
      if (!occurrence.event.training_plan_id || !planIds.has(occurrence.event.training_plan_id) ||
          occurrence.date !== getLocalDate(occurrence.occurrenceStartAt) || isTrainingOccurrenceCompleted(occurrence, sessions)) return false;
      const key = `${occurrence.event.id}-${occurrence.occurrenceStartAt.getTime()}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 4);
  return <section className="section training-schedule-panel">
    <div className="section-header">
      <div><p className="eyebrow">Dein Rhythmus</p><h2>Nächste Trainings</h2></div>
      <button className="button secondary" onClick={() => onSchedule(plans[0])} type="button">
        <CalendarDays size={16} />Trainingsserie planen
      </button>
    </div>
    <p className="training-schedule-hint">Zum Beispiel 2 Tage Training, 1 Tag Pause. Mit Skip schiebst du das Training und die folgenden Einheiten um einen Tag weiter.</p>
    {upcoming.length ? <div className="training-upcoming-list">
      {upcoming.map((occurrence) => <article className="training-upcoming-item" key={occurrence.key}>
        <div><strong>{occurrence.event.title}</strong>
          <span>{occurrence.startAt.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}
            {occurrence.event.all_day ? " · Ganztägig" : ` · ${occurrence.startAt.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`}</span>
        </div>
        <TrainingOccurrenceActions occurrence={occurrence} sessions={sessions} busy={busy} onStart={onStart} onSkip={onSkip} />
      </article>)}
    </div> : <p className="training-schedule-hint">Keine offenen Trainings in den nächsten 90 Tagen. Plane deine erste Serie im Kalender.</p>}
    <TrainingPauseHistory events={linkedEvents} busy={busy} onUndo={onUndo} />
  </section>;
}
