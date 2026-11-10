import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { addDays, dateAtEndOfDay, dateFromLocalValue, getLocalDate, getRecurrenceStarts } from "../src/calendar.ts";

// Run against calendar_ui_fixture:app, which keeps every test in an isolated in-memory DB.
const api = process.env.TRAINING_TEST_API_URL ?? "http://127.0.0.1:8017";
const frontend = process.env.TRAINING_TEST_FRONTEND_URL ?? "http://127.0.0.1:5177";
const cdp = process.env.TRAINING_TEST_CDP_URL ?? "http://127.0.0.1:9237";
process.env.TZ = "Europe/Berlin";
const today = dateFromLocalValue(getLocalDate());
const dateAfter = (days) => getLocalDate(addDays(today, days));
const starts = (event, limit = 6) => [...getRecurrenceStarts(event, dateAtEndOfDay(dateAfter(90)), limit)].map(getLocalDate);

async function request(path, method = "GET", body) {
  const response = await fetch(`${api}${path}`, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  assert.ok(response.ok, `${method} ${path}: ${JSON.stringify(data)}`);
  return data;
}

const pages = await (await fetch(`${cdp}/json/list`)).json();
const page = pages.find((item) => item.type === "page");
assert.ok(page, "Start a dedicated headless Chrome with remote debugging before running this test");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let sequence = 0;
const pending = new Map();
const mutations = [];
const browserErrors = [];
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.id) {
    const call = pending.get(message.id);
    pending.delete(message.id);
    if (!call) return;
    message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
  } else if (message.method === "Runtime.exceptionThrown") {
    browserErrors.push(message.params.exceptionDetails);
  } else if (message.method === "Fetch.requestPaused") {
    const { requestId, request: intercepted } = message.params;
    if (["POST", "PATCH", "DELETE"].includes(intercepted.method)) {
      mutations.push({ method: intercepted.method, url: intercepted.url, body: JSON.parse(intercepted.postData || "{}") });
    }
    // Every request to the app's normal API is redirected before it reaches the network.
    void send("Fetch.continueRequest", { requestId, url: intercepted.url.replace("http://127.0.0.1:8000", api) });
  }
});
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function waitFor(expression, timeout = 30000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Not ready: ${expression}\n${await evaluate("document.body.innerText.slice(0, 2500)")}\nBrowser errors: ${JSON.stringify(browserErrors)}`);
}
async function click(selector) {
  await waitFor(`!!document.querySelector(${JSON.stringify(selector)})`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
async function clickText(scope, label) {
  const expression = `Array.from(document.querySelectorAll(${JSON.stringify(`${scope} button`)})).find(el => el.textContent.trim() === ${JSON.stringify(label)})`;
  await waitFor(`!!(${expression})`);
  await evaluate(`${expression}.click()`);
}
function field(scope, label) {
  return `Array.from(document.querySelectorAll(${JSON.stringify(`${scope} label`)})).find(el => el.querySelector('span')?.textContent === ${JSON.stringify(label)}).querySelector('input, select')`;
}
async function fill(scope, label, value) {
  await evaluate(`(() => {
    const input = ${field(scope, label)};
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}
async function screenshot(name, selector) {
  if (!process.env.TRAINING_TEST_SCREENSHOTS) return;
  await send("Runtime.evaluate", {
    expression: "new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
    awaitPromise: true,
  });
  const clip = selector ? await evaluate(`(() => {
    const rect = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
    return {x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height, scale: 1};
  })()`) : undefined;
  const { data } = await send("Page.captureScreenshot", { format: "png", ...(clip ? {clip, captureBeyondViewport: true} : {}) });
  await writeFile(join(process.env.TRAINING_TEST_SCREENSHOTS, name), Buffer.from(data, "base64"));
}
async function scheduleIsReady(expectedFirstDay) {
  const formatted = dateFromLocalValue(expectedFirstDay).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  await waitFor(`document.querySelector('.training-upcoming-item > div span')?.textContent.includes(${JSON.stringify(formatted)}) && !document.querySelector('.training-upcoming-item button[disabled]')`);
}

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setTimezoneOverride", { timezoneId: "Europe/Berlin" });
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const width of [1440, 390]) {
    assert.equal((await request("/__calendar_test__/reset", "POST")).fixture, "calendar-create-memory",
      "Refuse to test against a database other than the in-memory fixture");
    const plan = await request("/training/plans", "POST", {
      name: "Zweier-Rhythmus", user_id: 1,
      exercises: [{ name: "Kniebeuge", position: 0 }],
    });
    mutations.length = 0;
    browserErrors.length = 0;
    await send("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: width < 760 });
    await send("Page.navigate", { url: frontend });
    await waitFor("document.body?.innerText.includes('Kalendertest')", 120000);
    await clickText(".nav-list", "Kalender");
    await clickText(".calendar-create-menu", "Erstellen");
    await clickText(".calendar-create-options", "Trainingsserie");
    await waitFor("!!document.querySelector('form.calendar-form')");
    await fill("form.calendar-form", "Titel", "Trainingsserie Test");
    await fill("form.calendar-form", "Datum", dateAfter(0));
    await fill("form.calendar-form", "Anfang", "18:00");
    await fill("form.calendar-form", "Ende", "19:00");
    await waitFor(`Array.from((${field("form.calendar-form", "Verknüpfter Trainingsplan")}).options).some(option => option.value === ${JSON.stringify(String(plan.id))})`);
    await fill("form.calendar-form", "Verknüpfter Trainingsplan", String(plan.id));
    await fill("form.calendar-form", "Trainingstage hintereinander", "2");
    await fill("form.calendar-form", "Pausentage danach", "1");
    assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.calendar-recurrence-preview time')).map(el => el.dateTime)"),
      [0, 1, 3, 4, 6, 7].map(dateAfter));
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true);
    assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('form.calendar-form input, form.calendar-form select')).filter(el => !el.checkValidity()).map(el => ({value: el.value, message: el.validationMessage, label: el.closest('label')?.innerText}))"), [], "Calendar form must be valid before saving");
    await screenshot(`frontend-screenshot-training-cycle-form-${width}.png`);
    await click("form.calendar-form button[type=submit]");
    await waitFor("!document.querySelector('form.calendar-form')");
    const events = await request("/calendar/events");
    assert.equal(events.length, 1);
    const event = events[0];
    assert.equal(event.training_plan_id, plan.id);
    assert.equal(event.recurrence_frequency, "cycle");
    assert.equal(event.cycle_training_days, 2);
    assert.equal(event.cycle_rest_days, 1);
    assert.deepEqual(starts(event), [0, 1, 3, 4, 6, 7].map(dateAfter));
    assert.equal(mutations.find((item) => item.url.endsWith("/calendar/events"))?.method, "POST");
    await waitFor("!!document.querySelector('.selected-day .training-occurrence-actions')");
    assert.equal(await evaluate("document.querySelector('.selected-day .training-occurrence-actions').getBoundingClientRect().width > 0"), true,
      "Calendar quick actions must be visible on mobile as well as desktop");

    await clickText(".nav-list", "Training");
    await scheduleIsReady(dateAfter(0));
    await clickText(".training-upcoming-item:first-child", "Skip / 1 Tag Pause");
    await scheduleIsReady(dateAfter(1));
    let shifted = await request(`/calendar/events/${event.id}`);
    assert.equal(shifted.shifts.length, 1);
    assert.deepEqual(starts(shifted), [1, 2, 4, 5, 7, 8].map(dateAfter));
    await clickText(".training-upcoming-item:first-child", "Skip / 1 Tag Pause");
    await scheduleIsReady(dateAfter(2));
    shifted = await request(`/calendar/events/${event.id}`);
    assert.equal(shifted.shifts.length, 2);
    assert.deepEqual(starts(shifted), [2, 3, 5, 6, 8, 9].map(dateAfter));
    assert.equal(await evaluate("document.querySelectorAll('.training-pause-history button').length"), 1,
      "Only the latest inserted pause can be undone");
    await clickText(".training-pause-history", "Rückgängig");
    await scheduleIsReady(dateAfter(1));
    shifted = await request(`/calendar/events/${event.id}`);
    assert.equal(shifted.shifts.length, 1);
    assert.deepEqual(starts(shifted), [1, 2, 4, 5, 7, 8].map(dateAfter));
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true);
    await evaluate("document.querySelector('.training-schedule-panel').scrollIntoView({block:'start'})");
    await screenshot(`frontend-screenshot-training-cycle-schedule-${width}.png`);

    await clickText(".training-upcoming-item:first-child", "Training starten");
    await waitFor("!!document.querySelector('.training-calendar-link')");
    assert.equal(await evaluate(`${field("form.training-session-form", "Trainingsplan")}.value`), String(plan.id));
    assert.equal(await evaluate(`${field("form.training-session-form", "Datum")}.value`), dateAfter(1));
    await fill("form.training-session-form", "Wdh.", "8");
    await clickText("form.training-session-form", "Einheit speichern");
    await waitFor("!document.querySelector('.training-calendar-link')");
    await scheduleIsReady(dateAfter(2));
    const sessions = await request("/training/sessions");
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].calendar_event_id, event.id);
    assert.equal(sessions[0].calendar_occurrence_start_at, `${dateAfter(1)}T18:00:00`);
    assert.equal(sessions[0].sets[0].reps, 8);
    assert.equal(sessions[0].sets[0].exercise_id, plan.exercises[0].id);

    await clickText(".nav-list", "Kalender");
    await clickText(".calendar-view-switch", "Tag");
    await click(".calendar-nav button[title='Naechster Zeitraum']");
    await waitFor("!!document.querySelector('.selected-day .training-occurrence-completed')");
    assert.equal(await evaluate("document.querySelector('.selected-day .training-occurrence-completed').textContent.trim()"), "Absolviert");
    assert.equal(await evaluate("document.querySelector('.selected-day .training-occurrence-completed').getBoundingClientRect().width > 0"), true,
      "Calendar completion must be visible on mobile as well as desktop");
    assert.equal(await evaluate("document.querySelectorAll('.selected-day .training-occurrence-actions button').length"), 0,
      "A completed training offers neither another start nor a skip");
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true);
    await evaluate("document.querySelector('.selected-day').scrollIntoView({block:'start'})");
    await screenshot(`frontend-screenshot-training-cycle-completed-${width}.png`, ".selected-day");
    assert.equal(mutations.filter((item) => item.url.endsWith("/skip") && item.method === "POST").length, 2);
    assert.equal(mutations.filter((item) => item.url.includes("/shifts/") && item.method === "DELETE").length, 1);
    assert.deepEqual(browserErrors, []);
    console.log(`PASS ${width}px: linked 2+1 training series, skip twice, undo, log exercise, calendar completion and responsive layout`);
    await send("Page.navigate", { url: "about:blank" });
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
