import assert from "node:assert/strict";
import { test } from "node:test";
import {
  getCalendarOccurrences, getLocalDate, getRecurrenceStarts,
  recurrenceDescription, recurrenceFormError, recurrenceFormRule, recurrencePayload,
} from "../src/calendar.ts";

process.env.TZ = "Europe/Berlin";

function rule(overrides = {}) {
  return {
    start_at: "2026-10-19T06:00:00", recurrence_frequency: "weekly",
    recurrence_interval: 2, recurrence_until: null, ...overrides,
  };
}
const dates = (value, until = "2026-11-15", count = Infinity) =>
  [...getRecurrenceStarts(value, new Date(`${until}T23:59:59`), count)].map(getLocalDate);

test("weekly intervals keep the chosen weekday and local time across DST", () => {
  const starts = [...getRecurrenceStarts(rule({ start_at: "2026-10-21T06:00:00" }), new Date("2026-11-30"))];
  assert.deepEqual(starts.map(getLocalDate), ["2026-10-21", "2026-11-04", "2026-11-18"]);
  assert.ok(starts.every((date) => date.getHours() === 6 && date.getDay() === 3));
});

test("every other weekend includes both days and skips the intervening weekend", () => {
  assert.deepEqual(dates(rule({ recurrence_frequency: "weekends" })), [
    "2026-10-24", "2026-10-25", "2026-11-07", "2026-11-08",
  ]);
  assert.deepEqual(dates(rule({ recurrence_frequency: "weekends", start_at: "2026-10-25T06:00:00" })), [
    "2026-10-25", "2026-11-07", "2026-11-08",
  ]);
});

test("weekday intervals count Monday-based calendar weeks, starting no earlier than the date", () => {
  assert.deepEqual(dates(rule({ recurrence_frequency: "weekdays", start_at: "2026-10-21T06:00:00" }), "2026-11-06"), [
    "2026-10-21", "2026-10-22", "2026-10-23",
    "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
  ]);
});

test("the last day is inclusive and truncates grouped repetitions", () => {
  assert.deepEqual(dates(rule({ recurrence_frequency: "weekends", recurrence_until: "2026-11-07T23:59:59" })), [
    "2026-10-24", "2026-10-25", "2026-11-07",
  ]);
});

test("monthly dates use the last day of shorter months and recover the original day", () => {
  assert.deepEqual(dates(rule({
    start_at: "2026-01-31T06:00:00", recurrence_frequency: "monthly", recurrence_interval: 1,
  }), "2026-05-31"), ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]);
  assert.deepEqual(dates(rule({
    start_at: "2026-12-31T06:00:00", recurrence_frequency: "monthly", recurrence_interval: 2,
  }), "2027-06-30"), ["2026-12-31", "2027-02-28", "2027-04-30", "2027-06-30"]);
});

test("yearly leap-day repetitions return to February 29 in leap years", () => {
  assert.deepEqual(dates(rule({
    start_at: "2024-02-29T06:00:00", recurrence_frequency: "yearly", recurrence_interval: 1,
  }), "2028-03-01"), ["2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]);
});

test("series without an end do not disappear after 4000 days", () => {
  const event = {
    ...rule({ start_at: "2010-01-01T06:00:00", recurrence_frequency: "daily", recurrence_interval: 1 }),
    id: 1, title: "Arbeit", entry_type: "event", all_day: false, exclusions: [],
  };
  assert.deepEqual(getCalendarOccurrences([event], new Date("2026-10-19T00:00:00"), new Date("2026-10-20T23:59:59")).map((item) => item.date), [
    "2026-10-19", "2026-10-20",
  ]);
});

const form = (overrides = {}) => ({
  date: "2026-10-19", recurrence_frequency: "weekends", recurrence_interval: "2", recurrence_until: "", ...overrides,
});

test("form descriptions identify weeks and the exact days", () => {
  assert.equal(recurrenceDescription(form()), "Alle 2 Wochen am Samstag und Sonntag.");
  assert.equal(recurrenceDescription(form({ recurrence_frequency: "weekly" })), "Alle 2 Wochen am Montag.");
  assert.equal(recurrenceDescription(form({ recurrence_frequency: "weekdays", recurrence_interval: "1" })), "Jede Woche von Montag bis Freitag.");
});

test("invalid intervals and date ranges are rejected before saving", () => {
  for (const recurrence_interval of ["", "0", "-1", "1.5", "366"]) {
    assert.throws(() => recurrencePayload(form({ recurrence_interval })), /ganzen Zahlen/);
  }
  assert.throws(() => recurrencePayload(form({ recurrence_until: "2026-10-18" })), /nicht vor/);
  assert.match(recurrenceFormError(form({ recurrence_until: "2026-10-23" })), /kein passender Wochentag/);
  assert.equal(recurrenceFormError(form({ recurrence_until: "2026-10-24" })), null);
});

test("turning repetition off removes hidden interval and end-date values", () => {
  assert.deepEqual(recurrencePayload(form({ recurrence_frequency: "none", recurrence_interval: "", recurrence_until: "2020-01-01" })), {
    recurrence_frequency: "none", recurrence_interval: 1, recurrence_until: null,
  });
});

test("preview and calendar use the same recurrence dates", () => {
  for (const recurrence_frequency of ["daily", "weekly", "weekdays", "weekends", "monthly", "yearly"]) {
    const value = form({ recurrence_frequency });
    const preview = dates(recurrenceFormRule(value), "2040-01-01", 6);
    const event = {
      ...recurrenceFormRule(value), id: 1, title: "Test", entry_type: "event",
      all_day: false, exclusions: [],
    };
    const actual = getCalendarOccurrences([event], new Date(`${value.date}T00:00:00`), new Date(`${preview.at(-1)}T23:59:59`));
    assert.deepEqual(actual.map((item) => item.date), preview, recurrence_frequency);
  }
});
