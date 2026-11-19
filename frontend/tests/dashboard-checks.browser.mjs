import assert from "node:assert/strict";

const api = process.env.DASHBOARD_TEST_API_URL ?? "http://127.0.0.1:8019";
const frontend = process.env.DASHBOARD_TEST_FRONTEND_URL ?? "http://127.0.0.1:5179";
const cdp = process.env.DASHBOARD_TEST_CDP_URL ?? "http://127.0.0.1:9239";
async function request(path, method = "GET", body) {
  const response = await fetch(`${api}${path}`, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  assert.ok(response.ok, await response.clone().text());
  return response.json();
}
const page = (await (await fetch(`${cdp}/json/list`)).json()).find(item => item.type === "page");
assert.ok(page);
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
let sequence = 0;
const pending = new Map();
const writes = [];
let rejectNext = false;
let holdNext = false;
let held = null;
function send(method, params = {}) {
  return new Promise((resolve, reject) => { const id = ++sequence; pending.set(id, { resolve, reject }); socket.send(JSON.stringify({ id, method, params })); });
}
socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.id) {
    const call = pending.get(message.id); pending.delete(message.id);
    message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
  } else if (message.method === "Fetch.requestPaused") {
    const { requestId, request: paused } = message.params;
    const isWrite = (paused.method === "PATCH" && paused.url.includes("/calendar/events/")) || (paused.method === "POST" && paused.url.endsWith("/check"));
    if (isWrite) writes.push({ method: paused.method, url: paused.url, body: paused.postData });
    if (isWrite && rejectNext) {
      rejectNext = false;
      void send("Fetch.fulfillRequest", { requestId, responseCode: 503, responseHeaders: [
        { name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: "*" },
      ], body: Buffer.from(JSON.stringify({ detail: "Dashboard test save failed" })).toString("base64") });
    } else if (isWrite && holdNext) {
      holdNext = false;
      held = { requestId, url: paused.url.replace("http://127.0.0.1:8000", api) };
    } else {
      void send("Fetch.continueRequest", { requestId, url: paused.url.replace("http://127.0.0.1:8000", api) });
    }
  }
});
async function evaluate(expression) {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function waitFor(expression) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 50)); }
  throw new Error(`Not ready: ${expression}\n${await evaluate("document.body.innerText.slice(-2000)")}`);
}
async function click(selector) { await waitFor(`Boolean(document.querySelector(${JSON.stringify(selector)}))`); await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
const todoButton = '.dashboard-check-row [title="ToDo erledigen"]';
const shoppingButton = '.dashboard-check-row [title="Einkaufsartikel abhaken"]';

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const width of [390, 1440]) {
    assert.equal((await request("/__calendar_test__/reset", "POST")).fixture, "calendar-create-memory");
    const todo = await request("/calendar/events", "POST", { title: "Dashboard ToDo", description: "Aufgabe direkt abhaken", entry_type: "task", start_at: "2026-11-19T00:00:00", user_id: 1 });
    const shopping = await request("/shopping-list", "POST", { name: "Dashboard Milch", quantity: 2, unit: "l" });
    writes.length = 0;
    await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: width < 760 });
    await send("Page.navigate", { url: frontend });
    await waitFor("document.body.innerText.includes('Kalendertest')");
    await click('[title="Dashboard"]');
    await waitFor(`Boolean(document.querySelector(${JSON.stringify(todoButton)})) && Boolean(document.querySelector(${JSON.stringify(shoppingButton)}))`);
    assert.equal(await evaluate("document.querySelectorAll('.dashboard-check-row button button').length"), 0);

    for (const [selector, kind] of [[todoButton, "todo"], [shoppingButton, "shopping"]]) {
      rejectNext = true;
      await click(selector);
      await waitFor("document.querySelector('.notice.error')?.textContent.includes('Dashboard test save failed')");
      await waitFor(`document.querySelector(${JSON.stringify(selector)})?.disabled === false`);
      assert.equal(await evaluate("document.querySelector('.topbar h1').textContent"), "Dashboard");
      const unchanged = kind === "todo" ? await request(`/calendar/events/${todo.id}`) : (await request("/shopping-list")).find(item => item.id === shopping.id);
      assert.equal(kind === "todo" ? unchanged.is_completed : unchanged.is_checked, false);
      holdNext = true;
      const before = writes.length;
      await click(selector);
      await waitFor(`document.querySelector(${JSON.stringify(selector)})?.disabled === true`);
      await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
      assert.ok(held);
      assert.equal(writes.length, before + 1);
      await send("Fetch.continueRequest", held);
      held = null;
      await waitFor(`!document.querySelector(${JSON.stringify(selector)})`);
      assert.equal(await evaluate("document.querySelector('.topbar h1').textContent"), "Dashboard");
    }
    assert.equal((await request(`/calendar/events/${todo.id}`)).is_completed, true);
    assert.equal((await request("/shopping-list")).find(item => item.id === shopping.id).is_checked, true);
    await click('[title="ToDo Tracker"]');
    await waitFor("Boolean(document.querySelector('.todo-item.completed'))");
    await click('.todo-item.completed [title="Wieder oeffnen"]');
    await waitFor("Boolean(document.querySelector('.todo-item:not(.completed)'))");
    await click('[title="Einkaufsliste"]');
    await waitFor("Boolean(document.querySelector('.shopping-item.checked'))");
    await click('.shopping-item.checked [title="Zuruecksetzen"]');
    await waitFor("Boolean(document.querySelector('.shopping-item:not(.checked)'))");
    await click('[title="Dashboard"]');
    await waitFor(`Boolean(document.querySelector(${JSON.stringify(todoButton)})) && Boolean(document.querySelector(${JSON.stringify(shoppingButton)}))`);
    const beforeNavigation = writes.length;
    await evaluate("Array.from(document.querySelectorAll('.dashboard-item-link')).find(button => button.textContent.includes('Aufgabe direkt abhaken')).click()");
    await waitFor("document.querySelector('.topbar h1')?.textContent === 'ToDo Tracker'");
    assert.equal(writes.length, beforeNavigation);
    await click('[title="Dashboard"]');
    await click(todoButton);
    await waitFor(`!document.querySelector(${JSON.stringify(todoButton)})`);
    await click(shoppingButton);
    await waitFor(`!document.querySelector(${JSON.stringify(shoppingButton)})`);
    await send("Page.reload");
    await waitFor("document.querySelector('.dashboard-clean-page')?.textContent.includes('Keine offenen ToDos') && document.querySelector('.dashboard-clean-page')?.textContent.includes('Keine offenen Artikel')");
    console.log(`PASS ${width}px dashboard: todo/shopping completion persists, failed saves can retry, duplicate clicks are blocked, list pages stay synchronized and text navigation remains available`);
  }
} finally {
  if (held) await send("Fetch.continueRequest", held);
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
