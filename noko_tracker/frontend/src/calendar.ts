import type { CalendarEvent, CalendarGroup } from "./api/client";

export type CalendarOccurrence = {
  key: string;
  date: string;
  event: CalendarEvent;
  occurrenceStartAt: Date;
  startAt: Date;
  endAt: Date | null;
};

type EventInterval = {
  event: CalendarEvent;
  occurrenceStartAt: Date;
  startAt: Date;
  endAt: Date;
};

type Interval = [number, number];

export function getLocalDate(date = new Date()) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export function dateFromLocalValue(value: string) {
  return new Date(`${value}T00:00:00`);
}

export function dateAtEndOfDay(value: string) {
  return new Date(`${value}T23:59:59`);
}

export function addDays(date: Date, amount: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + amount);
  return next;
}

export function withCalendarDate<Form extends { date: string; end_date: string }>(
  form: Form,
  date: string,
): Form {
  return {
    ...form,
    date,
    end_date:
      !form.end_date || form.end_date === form.date || form.end_date < date
        ? date
        : form.end_date,
  };
}

function recurrenceDate(
  base: Date,
  frequency: CalendarEvent["recurrence_frequency"],
  interval: number,
  index: number,
) {
  const next = new Date(base);
  if (frequency === "daily") {
    next.setDate(base.getDate() + interval * index);
  }
  if (frequency === "weekdays" || frequency === "weekends") {
    next.setDate(base.getDate() + index);
  }
  if (frequency === "weekly") {
    next.setDate(base.getDate() + interval * index * 7);
  }
  if (frequency === "monthly" || frequency === "yearly") {
    // Always anchor to the original date, so February cannot shift later months.
    next.setDate(1);
    if (frequency === "monthly") next.setMonth(base.getMonth() + interval * index);
    else next.setFullYear(base.getFullYear() + interval * index);
    const lastDay = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
    next.setDate(Math.min(base.getDate(), lastDay));
  }
  return next;
}

export function calendarWeekStart(value: Date) {
  const weekStart = new Date(value);
  weekStart.setHours(0, 0, 0, 0);
  weekStart.setDate(weekStart.getDate() - ((weekStart.getDay() + 6) % 7));
  return weekStart;
}

function groupedRecurrenceMatchesDate(
  baseStart: Date,
  occurrenceStart: Date,
  frequency: CalendarEvent["recurrence_frequency"],
  interval: number,
) {
  const day = occurrenceStart.getDay();
  const matchesDay =
    frequency === "weekdays"
      ? day >= 1 && day <= 5
      : frequency === "weekends"
        ? day === 0 || day === 6
        : true;

  if (!matchesDay) {
    return false;
  }
  if (frequency !== "weekdays" && frequency !== "weekends") {
    return true;
  }

  const millisecondsPerWeek = 7 * 24 * 60 * 60 * 1000;
  const weekDistance = Math.round(
    (calendarWeekStart(occurrenceStart).getTime() -
      calendarWeekStart(baseStart).getTime()) /
      millisecondsPerWeek,
  );
  return weekDistance % Math.max(interval, 1) === 0;
}

export type CalendarRecurrence = Pick<CalendarEvent,
  "start_at" | "recurrence_frequency" | "recurrence_interval" | "recurrence_until"
>;

export function* getRecurrenceStarts(
  rule: CalendarRecurrence,
  rangeEnd: Date,
  limit = Infinity,
): Generator<Date> {
  const base = new Date(rule.start_at);
  const frequency = rule.recurrence_frequency ?? "none";
  const interval = rule.recurrence_interval;
  const until = rule.recurrence_until ? new Date(rule.recurrence_until) : rangeEnd;
  if (!Number.isFinite(base.getTime()) || !Number.isFinite(until.getTime()) ||
      !Number.isInteger(interval) || interval < 1 || limit < 1) return;
  let emitted = 0;
  for (let index = 0; ; index += 1) {
    const start = recurrenceDate(base, frequency, interval, index);
    if (!Number.isFinite(start.getTime()) || start > rangeEnd || start > until) return;
    if (groupedRecurrenceMatchesDate(base, start, frequency, interval)) {
      yield start;
      if (++emitted >= limit) return;
    }
    if (frequency === "none") return;
  }
}

export type CalendarRecurrenceForm = {
  date: string;
  recurrence_frequency: CalendarEvent["recurrence_frequency"];
  recurrence_interval: string;
  recurrence_until: string;
};

export function recurrenceUnit(frequency: CalendarEvent["recurrence_frequency"]) {
  if (frequency === "daily") return "Tage";
  if (frequency === "monthly") return "Monate";
  if (frequency === "yearly") return "Jahre";
  return "Wochen";
}

export function recurrenceFormRule(form: CalendarRecurrenceForm): CalendarRecurrence {
  return {
    start_at: `${form.date}T00:00:00`,
    recurrence_frequency: form.recurrence_frequency,
    recurrence_interval: Number(form.recurrence_interval),
    recurrence_until: form.recurrence_until ? `${form.recurrence_until}T23:59:59` : null,
  };
}

export function recurrenceFormError(form: CalendarRecurrenceForm): string | null {
  if (form.recurrence_frequency === "none") return null;
  const rule = recurrenceFormRule(form);
  if (!Number.isFinite(new Date(rule.start_at).getTime())) return "Bitte ein Startdatum wählen.";
  if (!Number.isInteger(rule.recurrence_interval) || rule.recurrence_interval < 1 || rule.recurrence_interval > 365) {
    return "Bitte einen Abstand von 1 bis 365 in ganzen Zahlen eingeben.";
  }
  if (form.recurrence_until) {
    if (form.recurrence_until < form.date) return "Das Serienende darf nicht vor dem Startdatum liegen.";
    if (![...getRecurrenceStarts(rule, dateAtEndOfDay(form.recurrence_until), 1)].length) {
      return "Bis zum Serienende liegt kein passender Wochentag. Bitte das Datum oder die Wiederholung ändern.";
    }
  }
  return null;
}

export function recurrencePayload(form: CalendarRecurrenceForm) {
  const error = recurrenceFormError(form);
  if (error) throw new Error(error);
  return {
    recurrence_frequency: form.recurrence_frequency,
    recurrence_interval: form.recurrence_frequency === "none" ? 1 : Number(form.recurrence_interval),
    recurrence_until: form.recurrence_frequency !== "none" && form.recurrence_until
      ? `${form.recurrence_until}T23:59:59` : null,
  };
}

export function recurrenceDescription(form: CalendarRecurrenceForm) {
  const date = dateFromLocalValue(form.date);
  if (!Number.isFinite(date.getTime())) return "";
  const interval = Number(form.recurrence_interval);
  const every = `Alle ${interval} ${recurrenceUnit(form.recurrence_frequency)}`;
  const weekday = date.toLocaleDateString("de-DE", { weekday: "long" });
  switch (form.recurrence_frequency) {
    case "daily": return interval === 1 ? "Jeden Tag." : `${every}.`;
    case "weekly": return interval === 1 ? `Jede Woche am ${weekday}.` : `${every} am ${weekday}.`;
    case "weekdays": return `${interval === 1 ? "Jede Woche" : every} von Montag bis Freitag.`;
    case "weekends": return `${interval === 1 ? "Jede Woche" : every} am Samstag und Sonntag.`;
    case "monthly": return `${interval === 1 ? "Jeden Monat" : every} am ${date.getDate()}.`;
    case "yearly": return `${interval === 1 ? "Jedes Jahr" : every} am ${date.toLocaleDateString("de-DE", { day: "numeric", month: "long" })}.`;
    default: return "Einmaliger Termin.";
  }
}

function startOfDay(value: Date) {
  return dateFromLocalValue(getLocalDate(value));
}

function occurrenceEnd(event: CalendarEvent, start: Date) {
  const baseStart = new Date(event.start_at);
  const baseEnd = event.end_at ? new Date(event.end_at) : null;
  if (!baseEnd) {
    return event.all_day
      ? addDays(startOfDay(start), 1)
      : new Date(start.getTime() + 60 * 60 * 1000);
  }

  const dayCount = Math.round(
    (startOfDay(baseEnd).getTime() - startOfDay(baseStart).getTime()) /
      (24 * 60 * 60 * 1000),
  );
  const end = addDays(startOfDay(start), dayCount);
  if (event.all_day) {
    return addDays(end, 1);
  }
  end.setHours(
    baseEnd.getHours(), baseEnd.getMinutes(),
    baseEnd.getSeconds(), baseEnd.getMilliseconds(),
  );
  return end > start ? end : new Date(start.getTime() + 60 * 1000);
}

function expandEvents(events: CalendarEvent[], rangeStart: Date, rangeEnd: Date) {
  const intervals: EventInterval[] = [];
  for (const event of events) {
    if (event.entry_type === "task") {
      continue;
    }
    const excludedStarts = new Set(
      (event.exclusions ?? []).map((item) => new Date(item.occurrence_start_at).getTime()),
    );
    for (const start of getRecurrenceStarts(event, rangeEnd)) {
      const end = occurrenceEnd(event, start);
      if (
        end > rangeStart &&
        !excludedStarts.has(start.getTime())
      ) {
        intervals.push({
          event,
          occurrenceStartAt: new Date(start),
          startAt: event.all_day ? startOfDay(start) : new Date(start),
          endAt: end,
        });
      }
    }
  }
  return intervals;
}

function subtractIntervals(target: EventInterval, blocked: Interval[]) {
  let remaining: Interval[] = [[target.startAt.getTime(), target.endAt.getTime()]];
  for (const [blockedStart, blockedEnd] of blocked) {
    const next: Interval[] = [];
    for (const [start, end] of remaining) {
      if (blockedStart >= end || blockedEnd <= start) {
        next.push([start, end]);
        continue;
      }
      if (blockedStart > start) {
        next.push([start, blockedStart]);
      }
      if (blockedEnd < end) {
        next.push([blockedEnd, end]);
      }
    }
    remaining = next;
    if (!remaining.length) {
      break;
    }
  }
  return remaining;
}

export function getCalendarOccurrences(
  events: CalendarEvent[],
  rangeStart: Date,
  rangeEnd: Date,
  groups: CalendarGroup[] = [],
) {
  const intervals = expandEvents(events, rangeStart, rangeEnd);
  const groupById = new Map(groups.map((group) => [group.id, group]));
  const blockedByGroup = new Map<number, EventInterval[]>();

  // Use all source occurrences before visibility filters, without changing stored events.
  for (const source of intervals) {
    const group = groupById.get(source.event.group_id ?? -1) ?? source.event.group;
    for (const groupId of group?.suppresses_group_ids ?? []) {
      if (groupId === source.event.group_id) {
        continue;
      }
      const blocked = blockedByGroup.get(groupId) ?? [];
      blocked.push(source);
      blockedByGroup.set(groupId, blocked);
    }
  }

  const occurrences: CalendarOccurrence[] = [];
  for (const target of intervals) {
    const blocked = (blockedByGroup.get(target.event.group_id ?? -1) ?? [])
      .filter((source) =>
        source.event.id !== target.event.id &&
        source.startAt < target.endAt && target.startAt < source.endAt,
      )
      .map((source): Interval => {
        if (!target.event.all_day) {
          return [source.startAt.getTime(), source.endAt.getTime()];
        }
        const endDay = startOfDay(source.endAt);
        return [
          startOfDay(source.startAt).getTime(),
          (source.endAt > endDay ? addDays(endDay, 1) : endDay).getTime(),
        ];
      });

    for (const [start, end] of subtractIntervals(target, blocked)) {
      let day = startOfDay(new Date(Math.max(start, rangeStart.getTime())));
      while (day.getTime() < end && day <= rangeEnd) {
        const nextDay = addDays(day, 1);
        const segmentStart = new Date(Math.max(start, day.getTime()));
        const segmentEnd = new Date(Math.min(end, nextDay.getTime()));
        const date = getLocalDate(day);
        const unchangedOpenEnd =
          !target.event.all_day && !target.event.end_at &&
          segmentStart.getTime() === target.startAt.getTime() &&
          segmentEnd.getTime() === target.endAt.getTime();
        occurrences.push({
          key: `${target.event.id}-${target.occurrenceStartAt.toISOString()}-${segmentStart.toISOString()}`,
          date,
          event: target.event,
          occurrenceStartAt: target.occurrenceStartAt,
          startAt: segmentStart,
          endAt: unchangedOpenEnd
            ? null
            : segmentEnd.getTime() === nextDay.getTime()
              ? dateAtEndOfDay(date)
              : segmentEnd,
        });
        day = nextDay;
      }
    }
  }

  return occurrences.sort((first, second) => first.startAt.getTime() - second.startAt.getTime());
}
