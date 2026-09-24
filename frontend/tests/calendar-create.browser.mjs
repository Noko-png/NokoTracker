import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { getLocalDate, addDays } from "../src/calendar.ts";

const api = process.env.CALENDAR_TEST_API_URL ?? "http://127.0.0.1:8015";
const frontend = process.env.CALENDAR_TEST_FRONTEND_URL ?? "http://127.0.0.1:5175";
const cdp = process.env.CALENDAR_TEST_CDP_URL ?? "http://127.0.0.1:9225";
const monday = new Date();
monday.setHours(0, 0, 0, 0);
monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
const workDay = getLocalDate(monday);
const workUntil = getLocalDate(addDays(monday, 365));
const pages = await (await fetch(`${cdp}/json/list`)).json();
const page = pages.find((item) => item.type === "page");
assert.ok(page, "Start a dedicated headless Chrome instance for this test");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
const pending = new Map();
const requests = [];
let sequence = 0;
let rejectNextCreate = false;
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
    message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
  } else if (message.method === "Fetch.requestPaused") {
    const { requestId, request } = message.params;
    if (request.url.includes("/calendar/") && ["POST", "PATCH", "DELETE"].includes(request.method)) {
      requests.push({ method: request.method, url: request.url, body: JSON.parse(request.postData || "{}") });
    }
    if (rejectNextCreate && request.method === "POST" && request.url.endsWith("/calendar/events")) {
      rejectNextCreate = false;
      void send("Fetch.fulfillRequest", {
        requestId, responseCode: 422,
        responseHeaders: [
          { name: "Content-Type", value: "application/json" },
          { name: "Access-Control-Allow-Origin", value: "*" },
        ],
        body: Buffer.from(JSON.stringify({ detail: "Calendar test validation error" })).toString("base64"),
      });
    } else {
      void send("Fetch.continueRequest", {
        requestId, url: request.url.replace("http://127.0.0.1:8000", api),
      });
    }
  }
});
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function waitFor(expression) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Not ready: ${expression}`);
}
async function clickText(label) {
  const value = JSON.stringify(label);
  await waitFor(`Array.from(document.querySelectorAll('button')).some(el => el.textContent.trim() === ${value})`);
  await evaluate(`Array.from(document.querySelectorAll('button')).find(el => el.textContent.trim() === ${value}).click()`);
}
async function fill(label, value) {
  await evaluate(`(() => {
    const label = Array.from(document.querySelectorAll('form.calendar-form label')).find(el => el.querySelector('span')?.textContent === ${JSON.stringify(label)});
    const input = label.querySelector('input, select');
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}
async function readField(label) {
  return evaluate(`Array.from(document.querySelectorAll('form.calendar-form label')).find(el => el.querySelector('span')?.textContent === ${JSON.stringify(label)}).querySelector('input, select').value`);
}
async function submit() {
  await evaluate("document.querySelector('form.calendar-form button[type=submit]').click()");
}

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setTimezoneOverride", { timezoneId: "Europe/Berlin" });
  // Redirect the app's default API to the isolated fixture; never write to the user's database.
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const scenario of [
    { name: "mobile-tap", width: 390, tap: true },
    { name: "desktop-tap", width: 1440, tap: true },
    { name: "mobile-date-input", width: 390, tap: false },
    { name: "mobile-all-day-tap", width: 390, tap: true, allDay: true },
    { name: "mobile-validation-error", width: 390, tap: true, failOnce: true },
  ]) {
    const reset = await (await fetch(`${api}/__calendar_test__/reset`, { method: "POST" })).json();
    assert.equal(reset.fixture, "calendar-create-memory", "Only use the in-memory calendar fixture");
    const originalWork = await (await fetch(`${api}/calendar/events`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "Arbeit",
        start_at: `${workDay}T${scenario.allDay ? "00:00" : "06:00"}:00`,
        end_at: `${workDay}T${scenario.allDay ? "23:59" : "15:00"}:00`,
        all_day: Boolean(scenario.allDay), recurrence_frequency: "weekdays",
        recurrence_until: `${workUntil}T23:59:59`, group_id: 1, user_id: 1,
      }),
    })).json();
    const holidayDay = getLocalDate(addDays(monday, scenario.tap ? 3 : 1));
    requests.length = 0;
    await send("Emulation.setDeviceMetricsOverride", {
      width: scenario.width, height: 900, deviceScaleFactor: 1, mobile: scenario.width < 760,
    });
    await send("Page.navigate", { url: frontend });
    await waitFor("document.body.innerText.includes('Kalendertest')");
    await clickText("Kalender");
    await clickText("Woche");
    await waitFor("Array.from(document.querySelectorAll('[title]')).filter(el => el.title.startsWith('Arbeit |')).length === 5");
    await clickText("Erstellen");
    await clickText("Termin");
    await fill("Titel", "Urlaub");
    await fill("Gruppe", "2");
    await evaluate("Array.from(document.querySelectorAll('form.calendar-form label')).find(el => el.textContent.trim() === 'Ganztagig').querySelector('input').click()");
    if (scenario.tap) {
      await evaluate("Array.from(document.querySelectorAll('[title]')).filter(el => el.title.startsWith('Arbeit |'))[3].click()");
    } else {
      // Moving backwards must not turn one holiday into a multi-day range.
      await fill("Datum", getLocalDate(addDays(monday, 4)));
      await fill("Datum", holidayDay);
    }
    assert.equal(await readField("Titel"), "Urlaub");
    assert.equal(await readField("Gruppe"), "2");
    assert.equal(await readField("Wiederholung"), "none");
    assert.equal(await readField("Datum"), holidayDay);
    assert.equal(await readField("Bis"), holidayDay);
    assert.ok(await evaluate("document.querySelector('form.calendar-form button[type=submit]').innerText.includes('Anlegen')"));
    if (scenario.failOnce) {
      rejectNextCreate = true;
      await submit();
      await waitFor("document.body.innerText.includes('Calendar test validation error')");
      assert.equal(await readField("Titel"), "Urlaub");
      assert.equal((await (await fetch(`${api}/calendar/events`)).json()).length, 1);
    }
    await submit();
    await waitFor("!document.querySelector('form.calendar-form')");
    const stored = await (await fetch(`${api}/calendar/events?limit=500`)).json();
    assert.equal(requests.at(-1).method, "POST", "Creating a holiday must not patch the work series");
    assert.deepEqual(stored.find((event) => event.id === originalWork.id), originalWork);
    assert.equal(stored.length, 2);
    await waitFor("Array.from(document.querySelectorAll('[title]')).filter(el => el.title.startsWith('Arbeit |')).length === 4");
    assert.equal(await evaluate("document.documentElement.scrollWidth <= window.innerWidth"), true);
    if (process.env.CALENDAR_TEST_SCREENSHOTS) {
      await writeFile(
        `${process.env.CALENDAR_TEST_SCREENSHOTS}/frontend-screenshot-${scenario.name}.png`,
        Buffer.from((await send("Page.captureScreenshot", { format: "png" })).data, "base64"),
      );
    }
    // After creation closes, clicking an existing event must still open normal editing.
    await evaluate("Array.from(document.querySelectorAll('[title]')).find(el => el.title.startsWith('Arbeit |')).click()");
    await waitFor("document.querySelector('form.calendar-form') !== null");
    assert.equal(await readField("Titel"), "Arbeit");
    await fill("Titel", "Arbeit bearbeitet");
    await submit();
    await waitFor("!document.querySelector('form.calendar-form')");
    assert.equal(requests.at(-1).method, "PATCH");
    const updatedWork = await (await fetch(`${api}/calendar/events/${originalWork.id}`)).json();
    assert.equal(updatedWork.title, "Arbeit bearbeitet");
    assert.equal(updatedWork.recurrence_frequency, "weekdays");
    assert.equal(updatedWork.start_at, originalWork.start_at);
    console.log(`PASS ${scenario.name}: new holiday, preserved series, normal editing`);
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
