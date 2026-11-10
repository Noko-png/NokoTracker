import assert from "node:assert/strict";
import { test } from "node:test";
import {
  getCalendarOccurrences, getLocalDate, getRecurrenceStarts,
  recurrenceDescription, recurrenceFormError, recurrenceFormRule, recurrencePayload,
} from "../src/calendar.ts";

process.env.TZ = "Europe/Berlin";

const cycle = (overrides = {}) => ({
  start_at: "2026-11-09T18:00:00", recurrence_frequency: "cycle",
  recurrence_interval: 1, recurrence_until: null,
  cycle_training_days: 2, cycle_rest_days: 1,
  ...overrides,
});
const dates = (rule, until = "2026-11-18") =>
  [...getRecurrenceStarts(rule, new Date(`${until}T23:59:59`))].map(getLocalDate);
const shift = (id, date) => ({ id, event_id: 1, occurrence_start_at: `${date}T18:00:00`, days: 1 });

test("training cycles repeat two training days followed by one rest day across weeks", () => {
  assert.deepEqual(dates(cycle()), [
    "2026-11-09", "2026-11-10", "2026-11-12", "2026-11-13",
    "2026-11-15", "2026-11-16", "2026-11-18",
  ]);
  assert.deepEqual(dates(cycle({ cycle_training_days: 1, cycle_rest_days: 2 })), [
    "2026-11-09", "2026-11-12", "2026-11-15", "2026-11-18",
  ]);
});

test("a skip inserts an extra rest day and moves future training while retaining history", () => {
  assert.deepEqual(dates(cycle({ shifts: [shift(1, "2026-11-10")] })), [
    "2026-11-09", "2026-11-11", "2026-11-13", "2026-11-14",
    "2026-11-16", "2026-11-17",
  ]);
});

test("repeated skips at the moved training day replay in insertion order", () => {
  const shifts = [shift(2, "2026-11-11"), shift(1, "2026-11-10")];
  assert.deepEqual(dates(cycle({ shifts })), [
    "2026-11-09", "2026-11-12", "2026-11-14", "2026-11-15",
    "2026-11-17", "2026-11-18",
  ]);
  assert.deepEqual(dates(cycle({ shifts: shifts.filter((item) => item.id !== 2) })),
    dates(cycle({ shifts: [shift(1, "2026-11-10")] })));
});

test("an earlier skip after a later skip applies to the then-current schedule", () => {
  assert.deepEqual(dates(cycle({ shifts: [shift(1, "2026-11-13"), shift(2, "2026-11-10")] })), [
    "2026-11-09", "2026-11-11", "2026-11-13", "2026-11-15", "2026-11-17", "2026-11-18",
  ]);
});

test("series end remains inclusive after a pause shifts a training beyond it", () => {
  assert.deepEqual(dates(cycle({
    recurrence_until: "2026-11-10T23:59:59", shifts: [shift(1, "2026-11-10")],
  })), ["2026-11-09"]);
});

test("calendar exclusions refer to shifted training dates", () => {
  const event = {
    ...cycle({ shifts: [shift(1, "2026-11-10")] }),
    id: 1, title: "Training", entry_type: "event", all_day: false,
    exclusions: [{ occurrence_start_at: "2026-11-11T18:00:00" }],
  };
  assert.deepEqual(getCalendarOccurrences([event], new Date("2026-11-09T00:00:00"),
    new Date("2026-11-14T23:59:59")).map((item) => item.date), [
    "2026-11-09", "2026-11-13", "2026-11-14",
  ]);
});

test("training and inserted pause days preserve local hours across daylight saving", () => {
  for (const start_at of ["2026-03-27T18:00:00", "2026-10-23T18:00:00"]) {
    const start = new Date(start_at);
    const starts = [...getRecurrenceStarts(cycle({
      start_at,
      shifts: [{ id: 1, event_id: 1, occurrence_start_at: start_at, days: 1 }],
    }), new Date(start.getFullYear(), start.getMonth(), start.getDate() + 8))];
    assert.ok(starts.length >= 4);
    assert.ok(starts.every((date) => date.getHours() === 18));
    assert.equal(starts[0].getDate(), start.getDate() + 1);
  }
});

test("older cycles remain visible well beyond 4000 days", () => {
  const event = {
    ...cycle({ start_at: "2010-01-01T18:00:00" }), id: 1,
    title: "Training", entry_type: "event", all_day: false, exclusions: [],
  };
  const actual = getCalendarOccurrences([event], new Date("2026-11-09T00:00:00"), new Date("2026-11-11T23:59:59"));
  assert.equal(actual.length, 2);
});

const form = (overrides = {}) => ({
  date: "2026-11-09", recurrence_frequency: "cycle", recurrence_interval: "1", recurrence_until: "",
  cycle_training_days: "2", cycle_rest_days: "1", ...overrides,
});

test("cycle form normalizes the unrelated interval and previews the saved cadence", () => {
  const value = form({ recurrence_interval: "" });
  assert.equal(recurrenceFormError(value), null);
  assert.deepEqual(recurrencePayload(value), {
    recurrence_frequency: "cycle", recurrence_interval: 1, recurrence_until: null,
    cycle_training_days: 2, cycle_rest_days: 1,
  });
  assert.deepEqual(dates(recurrenceFormRule(value)), dates(cycle()));
  assert.equal(recurrenceDescription(value), "2 Tage Training, 1 Tag Pause – fortlaufend.");
});

test("edited cycle date previews include afternoon pauses on their exact dates", () => {
  const shifts = [shift(1, "2026-11-10"), shift(2, "2026-11-11")];
  assert.deepEqual(dates(recurrenceFormRule(form(), shifts)), dates(cycle({ shifts })));
  assert.equal(shifts[0].occurrence_start_at, "2026-11-10T18:00:00");
});

test("cycle lengths reject empty, fractional, negative and excessive values", () => {
  for (const field of ["cycle_training_days", "cycle_rest_days"]) {
    for (const value of ["", "0", "-1", "1.5", "32"]) {
      assert.throws(() => recurrencePayload(form({ [field]: value })), /1 bis 31/);
    }
  }
  assert.equal(recurrenceFormError(form({ cycle_training_days: "31", cycle_rest_days: "31" })), null);
  assert.deepEqual(dates(cycle({ cycle_training_days: 0 })), []);
  assert.deepEqual(dates(cycle({ cycle_rest_days: -1 })), []);
});
