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
    training_plan_id: 10, training_plan: { id: 10, name: "Ganzkörper" },
    exclusions: [{ occurrence_start_at: "2026-11-11T18:00:00" }],
  };
  assert.deepEqual(getCalendarOccurrences([event], new Date("2026-11-09T00:00:00"),
    new Date("2026-11-14T23:59:59")).map((item) => [item.date, item.trainingPlanId, item.trainingPlanName]), [
    ["2026-11-09", 10, "Ganzkörper"], ["2026-11-13", 10, "Ganzkörper"], ["2026-11-14", 10, "Ganzkörper"],
  ]);
});

test("a pause shifts the ordered training plans without restarting the rotation", () => {
  const event = {
    ...cycle(), id: 1, title: "Training", entry_type: "event", all_day: false,
    training_plan_ids: [10, 20, 30, 10],
    training_plans: [{ id: 10, name: "A" }, { id: 20, name: "B" }, { id: 30, name: "C" }, { id: 10, name: "A" }],
  };
  const from = new Date("2026-11-09T00:00:00");
  const until = new Date("2026-11-17T23:59:59");
  const dateAndPlan = (item) => [item.date, item.trainingPlanId, item.trainingPlanName];

  assert.deepEqual(getCalendarOccurrences([event], from, until).map(dateAndPlan), [
    ["2026-11-09", 10, "A"], ["2026-11-10", 20, "B"], ["2026-11-12", 30, "C"],
    ["2026-11-13", 10, "A"], ["2026-11-15", 10, "A"], ["2026-11-16", 20, "B"],
  ]);
  const shifted = { ...event, shifts: [shift(1, "2026-11-10")] };
  assert.deepEqual(getCalendarOccurrences([shifted], from, until).map(dateAndPlan), [
    ["2026-11-09", 10, "A"], ["2026-11-11", 20, "B"], ["2026-11-13", 30, "C"],
    ["2026-11-14", 10, "A"], ["2026-11-16", 10, "A"], ["2026-11-17", 20, "B"],
  ]);
});

test("hidden slots and split appointments retain their original plan assignment", () => {
  const event = {
    ...cycle({ shifts: [shift(1, "2026-11-10")] }),
    id: 1, group_id: 1, title: "Training", entry_type: "event", all_day: false,
    end_at: "2026-11-09T21:00:00", training_plan_ids: [10, 20, 30],
    exclusions: [{ occurrence_start_at: "2026-11-11T18:00:00" }],
  };
  const blocker = {
    ...cycle({ recurrence_frequency: "none", start_at: "2026-11-13T19:00:00" }),
    id: 2, group_id: 2, title: "Blockiert", entry_type: "event", all_day: false,
    end_at: "2026-11-13T20:00:00",
  };
  const occurrences = getCalendarOccurrences([event, blocker], new Date("2026-11-11T00:00:00"),
    new Date("2026-11-14T23:59:59"), [{ id: 2, suppresses_group_ids: [1] }]);
  assert.deepEqual(occurrences.filter((item) => item.event.id === event.id).map((item) => [
    item.date, item.trainingPlanId, item.startAt.getHours(), item.occurrenceStartAt.getHours(),
  ]), [
    ["2026-11-13", 30, 18, 18], ["2026-11-13", 30, 20, 18], ["2026-11-14", 10, 18, 18],
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
