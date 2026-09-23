import assert from "node:assert/strict";
import { test } from "node:test";
import { getCalendarOccurrences } from "../src/calendar.ts";

process.env.TZ = "Europe/Berlin";

const groups = [
  { id: 1, name: "Arbeit", suppresses_group_ids: [] },
  { id: 2, name: "Urlaub", suppresses_group_ids: [1] },
];

function event(id, overrides = {}) {
  return {
    id,
    title: id === 1 ? "Arbeit" : "Urlaub",
    start_at: "2026-09-21T06:00:00",
    end_at: id === 1 ? "2026-09-21T15:00:00" : "2026-09-21T10:00:00",
    entry_type: "event",
    all_day: false,
    is_completed: false,
    recurrence_frequency: id === 1 ? "weekdays" : "none",
    recurrence_interval: 1,
    exclusions: [],
    group_id: id === 1 ? 1 : 2,
    ...overrides,
  };
}

function occurrences(events, start = "2026-09-21", end = start, rules = groups) {
  return getCalendarOccurrences(
    events, new Date(`${start}T00:00:00`), new Date(`${end}T23:59:59`), rules,
  );
}

function time(date) {
  return date?.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function workTimes(events, start, end, rules) {
  return occurrences(events, start, end, rules)
    .filter((item) => item.event.id === 1)
    .map((item) => [item.date, time(item.startAt), time(item.endAt)]);
}

test("a morning appointment preserves 10-15 and all other workdays", () => {
  const events = [event(1), event(2)];
  const original = structuredClone(events);
  const expected = [
    ["2026-09-21", "10:00", "15:00"],
    ["2026-09-22", "06:00", "15:00"],
  ];
  assert.deepEqual(workTimes(events, "2026-09-21", "2026-09-22"), expected);
  assert.deepEqual(workTimes([...events].reverse(), "2026-09-21", "2026-09-22"), expected);
  assert.deepEqual(events, original);
});

test("an appointment inside work hours preserves both segments", () => {
  const result = occurrences([event(1), event(2, {
    start_at: "2026-09-21T09:00:00", end_at: "2026-09-21T11:00:00",
  })]).filter((item) => item.event.id === 1);
  assert.deepEqual(result.map((item) => [time(item.startAt), time(item.endAt)]), [
    ["06:00", "09:00"], ["11:00", "15:00"],
  ]);
  assert.equal(new Set(result.map((item) => item.key)).size, 2);
  assert.ok(result.every((item) => time(item.occurrenceStartAt) === "06:00"));
});

test("touching boundaries and unrelated groups do not suppress", () => {
  const blockers = [
    event(2, { start_at: "2026-09-21T05:00:00", end_at: "2026-09-21T06:00:00" }),
    event(3, { start_at: "2026-09-21T15:00:00", end_at: "2026-09-21T16:00:00" }),
    event(4, { group_id: 3 }),
  ];
  assert.deepEqual(workTimes([event(1), ...blockers]), [["2026-09-21", "06:00", "15:00"]]);
});

test("multi-day all-day holidays suppress exactly their dates", () => {
  const holiday = event(2, {
    start_at: "2026-09-22T00:00:00", end_at: "2026-09-24T23:59:00", all_day: true,
  });
  assert.deepEqual(workTimes([event(1), holiday], "2026-09-21", "2026-09-28"), [
    ["2026-09-21", "06:00", "15:00"],
    ["2026-09-25", "06:00", "15:00"],
    ["2026-09-28", "06:00", "15:00"],
  ]);
});

test("moving, shortening, removing and ungrouping holidays restores work", () => {
  const work = event(1);
  let holiday = event(2, {
    start_at: "2026-09-21T00:00:00", end_at: "2026-09-23T23:59:00", all_day: true,
  });
  assert.deepEqual(workTimes([work, holiday]), []);
  holiday = { ...holiday, start_at: "2026-09-22T00:00:00", end_at: "2026-09-22T23:59:00" };
  const restored = [["2026-09-21", "06:00", "15:00"], ["2026-09-23", "06:00", "15:00"]];
  assert.deepEqual(workTimes([work, holiday], "2026-09-21", "2026-09-23"), restored);
  assert.deepEqual(workTimes([work]), [["2026-09-21", "06:00", "15:00"]]);
  assert.deepEqual(workTimes([work, { ...holiday, group_id: null }], "2026-09-22"), [
    ["2026-09-22", "06:00", "15:00"],
  ]);
  assert.deepEqual(workTimes([work, holiday], "2026-09-22", "2026-09-22", []), [
    ["2026-09-22", "06:00", "15:00"],
  ]);
});

test("recurring blockers respect frequency, recurrence end and exclusions", () => {
  const blocker = event(2, {
    recurrence_frequency: "daily", recurrence_interval: 2,
    recurrence_until: "2026-09-25T23:59:59",
    exclusions: [{ occurrence_start_at: "2026-09-23T06:00:00" }],
  });
  assert.deepEqual(workTimes([event(1), blocker], "2026-09-21", "2026-09-28"), [
    ["2026-09-21", "10:00", "15:00"], ["2026-09-22", "06:00", "15:00"],
    ["2026-09-23", "06:00", "15:00"], ["2026-09-24", "06:00", "15:00"],
    ["2026-09-25", "10:00", "15:00"], ["2026-09-28", "06:00", "15:00"],
  ]);
});

test("multiple overlapping blockers are subtracted once", () => {
  assert.deepEqual(workTimes([
    event(1), event(2),
    event(3, { start_at: "2026-09-21T09:00:00", end_at: "2026-09-21T12:00:00" }),
    event(4, { start_at: "2026-09-21T14:00:00", end_at: "2026-09-21T16:00:00" }),
  ]), [["2026-09-21", "12:00", "14:00"]]);
});

test("overnight work is only suppressed within the holiday day", () => {
  const work = event(1, { start_at: "2026-09-21T22:00:00", end_at: "2026-09-22T06:00:00" });
  const holiday = event(2, { start_at: "2026-09-22T00:00:00", end_at: "2026-09-22T23:59:00", all_day: true });
  assert.deepEqual(workTimes([work, holiday], "2026-09-21", "2026-09-23"), [
    ["2026-09-21", "22:00", "23:59"],
    ["2026-09-23", "00:00", "06:00"], ["2026-09-23", "22:00", "23:59"],
  ]);
});

test("midnight end does not create a phantom event on the next day", () => {
  const overnight = event(1, {
    start_at: "2026-09-21T22:00:00", end_at: "2026-09-22T00:00:00", recurrence_frequency: "none",
  });
  assert.deepEqual(workTimes([overnight], "2026-09-21", "2026-09-22"), [
    ["2026-09-21", "22:00", "23:59"],
  ]);
});

test("manually deleted occurrences stay deleted", () => {
  const work = event(1, { exclusions: [{ occurrence_start_at: "2026-09-22T06:00:00" }] });
  assert.deepEqual(workTimes([work, event(2)], "2026-09-21", "2026-09-23"), [
    ["2026-09-21", "10:00", "15:00"], ["2026-09-23", "06:00", "15:00"],
  ]);
});

test("single events, full overlap and default one-hour duration", () => {
  assert.deepEqual(workTimes([event(1, { recurrence_frequency: "none" }), event(2)]), [
    ["2026-09-21", "10:00", "15:00"],
  ]);
  assert.deepEqual(workTimes([event(1), event(2, { end_at: "2026-09-21T15:00:00" })]), []);
  assert.deepEqual(workTimes([event(1), event(2, { end_at: null })]), [
    ["2026-09-21", "07:00", "15:00"],
  ]);
});

test("hidden source groups still suppress before view filtering", () => {
  const hiddenGroups = groups.map((group) => ({ ...group, hide_from_dashboard_and_month: group.id === 2 }));
  const visible = occurrences([event(1), event(2)], undefined, undefined, hiddenGroups)
    .filter((item) => item.event.group_id !== 2);
  assert.deepEqual(visible.map((item) => [time(item.startAt), time(item.endAt)]), [["10:00", "15:00"]]);
});

test("open-ended overnight appointments keep their one-hour duration", () => {
  const work = event(1, {
    start_at: "2026-09-21T23:30:00", end_at: null, recurrence_frequency: "none",
  });
  assert.deepEqual(workTimes([work], "2026-09-21", "2026-09-22"), [
    ["2026-09-21", "23:30", "23:59"], ["2026-09-22", "00:00", "00:30"],
  ]);
});

test("all-day targets lose only the overlapping days", () => {
  const target = event(1, {
    start_at: "2026-09-21T00:00:00", end_at: "2026-09-23T23:59:00",
    all_day: true, recurrence_frequency: "none",
  });
  const blocker = event(2, {
    start_at: "2026-09-22T06:00:00", end_at: "2026-09-22T10:00:00",
  });
  assert.deepEqual(workTimes([target, blocker], "2026-09-21", "2026-09-23"), [
    ["2026-09-21", "00:00", "23:59"], ["2026-09-23", "00:00", "23:59"],
  ]);
});

test("all-day events and alternating workweeks keep their local dates across DST", () => {
  const work = event(1, {
    start_at: "2026-10-19T06:00:00", end_at: "2026-10-19T15:00:00", recurrence_interval: 2,
  });
  const holiday = event(2, {
    start_at: "2026-10-19T00:00:00", end_at: "2026-10-19T23:59:00",
    all_day: true, recurrence_frequency: "weekly", recurrence_interval: 2,
  });
  assert.deepEqual(workTimes([work, holiday], "2026-11-02", "2026-11-03"), [
    ["2026-11-03", "06:00", "15:00"],
  ]);
});
