import assert from "node:assert/strict";
import { getLocalDate, addDays } from "../src/calendar.ts";

const api = process.env.CALENDAR_TEST_API_URL ?? "http://127.0.0.1:8019";
const frontend = process.env.CALENDAR_TEST_FRONTEND_URL ?? "http://127.0.0.1:5179";
const cdp = process.env.CALENDAR_TEST_CDP_URL ?? "http://127.0.0.1:9239";
const page = (await (await fetch(`${cdp}/json/list`)).json()).find(item => item.type === "page");
assert.ok(page);
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
let sequence = 0;
const pending = new Map();
function send(method, params = {}) {
  return new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
}
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.id) {
    const call = pending.get(message.id); pending.delete(message.id);
    message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
  } else if (message.method === "Fetch.requestPaused") {
    void send("Fetch.continueRequest", { requestId: message.params.requestId, url: message.params.request.url.replace("http://127.0.0.1:8000", api) });
  }
});
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function waitFor(expression) {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)); }
  throw new Error(`Not ready: ${expression}\n${await evaluate("document.body.innerText.slice(-2000)")}`);
}
async function click(selector) { await waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`); await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function file(content, name = "termine.ics") {
  await waitFor("document.querySelector('.calendar-ics-transfer input[type=file]')?.disabled === false");
  await evaluate(`(() => { const input = document.querySelector('.calendar-ics-transfer input[type=file]');
    const files = new DataTransfer(); files.items.add(new File([${JSON.stringify(content)}], ${JSON.stringify(name)}, { type: 'text/calendar' }));
    input.files = files.files; input.dispatchEvent(new Event('change', { bubbles: true })); })()`);
}
async function submit() {
  await waitFor("document.querySelector('.calendar-ics-transfer button[type=submit]')?.disabled === false");
  await click('.calendar-ics-transfer button[type=submit]');
}
const today = getLocalDate();
const next = getLocalDate(addDays(new Date(`${today}T12:00:00`), 1));
const calendar = title => ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//DE",
  "BEGIN:VEVENT", "UID:ui-series@test", `DTSTART;TZID=Europe/Berlin:${today.replaceAll('-', '')}T100000`,
  "DURATION:PT1H", "RRULE:FREQ=DAILY;COUNT=3", `SUMMARY:${title}`, "END:VEVENT",
  "BEGIN:VEVENT", "UID:ui-all-day@test", `DTSTART;VALUE=DATE:${today.replaceAll('-', '')}`,
  `DTEND;VALUE=DATE:${next.replaceAll('-', '')}`, "SUMMARY:ICS Ganztag", "END:VEVENT", "END:VCALENDAR", ""].join("\r\n");

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setTimezoneOverride", { timezoneId: "Europe/Berlin" });
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const width of [390, 1440]) {
    const reset = await (await fetch(`${api}/__calendar_test__/reset`, { method: "POST" })).json();
    assert.equal(reset.fixture, "calendar-create-memory");
    await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 760 });
    await send("Page.navigate", { url: frontend });
    await waitFor("document.body.innerText.includes('Kalendertest')");
    await click('[title="Kalender"]');
    await click('.calendar-ics-transfer summary');
    await file("kein Kalender");
    await submit();
    await waitFor("Boolean(document.querySelector('.calendar-ics-transfer [role=alert]'))");
    assert.equal((await (await fetch(`${api}/calendar/events`)).json()).length, 0);
    await file(calendar("ICS Besprechung"));
    await submit();
    await waitFor("document.querySelector('.calendar-ics-result')?.textContent.includes('2 importiert')");
    await waitFor("Array.from(document.querySelectorAll('.agenda-item')).some(row => row.textContent.includes('ICS Besprechung'))");
    assert.ok(await evaluate("Array.from(document.querySelectorAll('.agenda-item')).some(row => row.textContent.includes('ICS Ganztag'))"));
    assert.equal(await evaluate("Array.from(document.querySelectorAll('.agenda-item')).filter(row => row.textContent.includes('ICS Besprechung')).some(row => row.querySelector('[title=\"Eintrag bearbeiten\"]'))"), false);
    await file(calendar("ICS Besprechung"));
    await submit();
    await waitFor("document.querySelector('.calendar-ics-result')?.textContent.includes('2 unverändert')");
    assert.equal((await (await fetch(`${api}/calendar/events`)).json()).length, 2);
    await file(calendar("ICS Geändert"));
    await submit();
    await waitFor("document.querySelector('.calendar-ics-result')?.textContent.includes('1 aktualisiert')");
    await waitFor("Array.from(document.querySelectorAll('.agenda-item')).some(row => row.textContent.includes('ICS Geändert'))");
    const exportData = await evaluate(`(async () => {
      const response = await fetch('http://127.0.0.1:8000/calendar/ics/export?' + new URLSearchParams({ start: ${JSON.stringify(`${today}T00:00:00`)}, end: ${JSON.stringify(`${getLocalDate(addDays(new Date(`${today}T12:00:00`), 5))}T00:00:00`)}, timezone: 'Europe/Berlin' }));
      return { status: response.status, type: response.headers.get('Content-Type'), content: await response.text() };
    })()`);
    assert.equal(exportData.status, 200);
    assert.match(exportData.type, /text\/calendar/);
    assert.match(exportData.content, /BEGIN:VCALENDAR/);
    assert.equal((exportData.content.match(/BEGIN:VEVENT/g) ?? []).length, 4);
    await evaluate("Array.from(document.querySelectorAll('.agenda-item')).find(row => row.textContent.includes('ICS Geändert')).querySelector('[title=\"Nur dieses Serienvorkommen loeschen\"]').click()");
    await waitFor("!Array.from(document.querySelectorAll('.agenda-item')).some(row => row.textContent.includes('ICS Geändert'))");
    await click('.calendar-ics-sources summary');
    await evaluate("Array.from(document.querySelectorAll('.calendar-ics-sources button')).find(button => button.textContent.trim() === 'ICS-Termin löschen').click()");
    await waitFor("document.querySelector('.calendar-ics-sources summary')?.textContent.includes('(1)')");
    assert.equal((await (await fetch(`${api}/calendar/events`)).json()).length, 1);
    console.log(`PASS ${width}px ICS: invalid file recovery, recurring and all-day imports, UID deduplication and updates, calendar display, standard export and single-occurrence deletion`);
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
