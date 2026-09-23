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

function addRecurrenceStep(
  value: Date,
  frequency: CalendarEvent["recurrence_frequency"],
  interval: number,
) {
  const next = new Date(value);
  if (frequency === "daily") {
    next.setDate(next.getDate() + interval);
  }
  if (frequency === "weekdays" || frequency === "weekends") {
    next.setDate(next.getDate() + 1);
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

function calendarWeekStart(value: Date) {
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
    const baseStart = new Date(event.start_at);
    const frequency = event.recurrence_frequency ?? "none";
    const interval = Math.max(event.recurrence_interval || 1, 1);
    const recurrenceUntil = event.recurrence_until
      ? new Date(event.recurrence_until)
      : null;
    const excludedStarts = new Set(
      (event.exclusions ?? []).map((item) => new Date(item.occurrence_start_at).getTime()),
    );
    let start = new Date(baseStart);

    for (let count = 0; count < 4000 && start <= rangeEnd; count += 1) {
      if (recurrenceUntil && start > recurrenceUntil) {
        break;
      }
      const end = occurrenceEnd(event, start);
      if (
        end > rangeStart &&
        groupedRecurrenceMatchesDate(baseStart, start, frequency, interval) &&
        !excludedStarts.has(start.getTime())
      ) {
        intervals.push({
          event,
          occurrenceStartAt: new Date(start),
          startAt: event.all_day ? startOfDay(start) : new Date(start),
          endAt: end,
        });
      }
      if (frequency === "none") {
        break;
      }
      start = addRecurrenceStep(start, frequency, interval);
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
