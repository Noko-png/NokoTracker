import assert from "node:assert/strict";

// Reuse the existing isolated database fixture, never the normal backend.
const api = process.env.FOOD_TEST_API_URL ?? "http://127.0.0.1:8015";
const frontend = process.env.FOOD_TEST_FRONTEND_URL ?? "http://127.0.0.1:5175";
const cdp = process.env.FOOD_TEST_CDP_URL ?? "http://127.0.0.1:9225";
async function request(path, method = "GET", body) {
  const response = await fetch(`${api}${path}`, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  assert.ok(response.ok, JSON.stringify(result));
  return result;
}
const pages = await (await fetch(`${cdp}/json/list`)).json();
const page = pages.find((item) => item.type === "page");
assert.ok(page, "Start a dedicated headless Chrome instance for this test");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
const pending = new Map();
let sequence = 0;
let rejectInventorySave = false;
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
    if (rejectInventorySave && request.method === "PUT" && request.url.includes("/inventory/")) {
      rejectInventorySave = false;
      void send("Fetch.fulfillRequest", {
        requestId, responseCode: 422,
        responseHeaders: [
          { name: "Content-Type", value: "application/json" },
          { name: "Access-Control-Allow-Origin", value: "*" },
        ],
        body: Buffer.from(JSON.stringify({ detail: "Inventory test validation error" })).toString("base64"),
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
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Not ready: ${expression}\n${await evaluate("document.body.innerText.slice(0, 2000)")}`);
}
async function click(selector) {
  await waitFor(`document.querySelector(${JSON.stringify(selector)}) !== null`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
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
async function readField(scope, label) {
  return evaluate(`${field(scope, label)}.value`);
}
const foodForm = ".food-editor-modal form";
const stockForm = ".inventory-edit-modal form";
const daysLabel = "Haltbarkeit bis Ablauf (Tage)";
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const width of [390, 1440]) {
    const reset = await request("/__calendar_test__/reset", "POST");
    assert.equal(reset.fixture, "calendar-create-memory");
    const unit = await request("/product-units", "POST", { name: "g" });
    const group = await request("/product-groups", "POST", { name: "Testgruppe", default_expiry_days: 7 });
    const food = await request("/foods", "POST", {
      name: "A Testlebensmittel", brand: "Testmarke", product_unit_id: unit.id,
      product_group_id: group.id, purchase_date: "2026-10-20", expiry_days: 7,
      conversions: [{ unit: "Packung", quantity: 500 }],
    });
    await request("/foods", "POST", { name: "Z Belegt", brand: "Testmarke" });
    const stock = await request("/inventory", "POST", {
      name: food.name, food_id: food.id, product_unit_id: unit.id,
      product_group_id: group.id, quantity: 2, purchase_date: "2026-10-20", expiry_days: 7,
    });
    await send("Emulation.setDeviceMetricsOverride", {
      width, height: 900, deviceScaleFactor: 1, mobile: width < 760,
    });
    await send("Page.navigate", { url: frontend });
    await waitFor("document.body.innerText.includes('Kalendertest')");
    await click('[title="Stammdaten verwalten"]');
    await waitFor("Array.from(document.querySelectorAll('.sidebar-master-option')).some(el => el.textContent.trim() === 'Lebensmittel')");
    await evaluate("Array.from(document.querySelectorAll('.sidebar-master-option')).find(el => el.textContent.trim() === 'Lebensmittel').click()");
    await click('[title="Lebensmittel bearbeiten"]');
    await fill(foodForm, daysLabel, "14");
    await fill(foodForm, "Einlagerungsdatum", "2026-10-25");
    await fill(foodForm, "Name", "Z Belegt");
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`document.querySelector('${foodForm} [role=alert]') !== null`);
    assert.match(await evaluate(`document.querySelector('${foodForm} [role=alert]').textContent`), /Food could not be updated/);
    assert.equal(await readField(foodForm, daysLabel), "14");
    assert.equal((await request(`/foods/${food.id}`)).expiry_days, 7);
    await fill(foodForm, "Name", food.name);
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${foodForm}')`);
    const updatedFood = await request(`/foods/${food.id}`);
    assert.equal(updatedFood.expiry_days, 14);
    assert.equal(updatedFood.purchase_date, "2026-10-25");
    assert.equal(updatedFood.conversions[0].quantity, 500);
    await click('[title="Lebensmittel bearbeiten"]');
    assert.equal(await readField(foodForm, daysLabel), "14");
    await fill(foodForm, daysLabel, "0");
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${foodForm}')`);
    assert.equal((await request(`/foods/${food.id}`)).expiry_days, 0);
    console.log(`PASS ${width}px food editing: conflict retains inputs, retry saves, zero days persists`);

    await click('[title="Bestandsübersicht"]');
    await click('.stock-action.edit');
    await fill(stockForm, daysLabel, "21");
    await fill(stockForm, "Einlagerungsdatum", "2026-10-25");
    rejectInventorySave = true;
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`document.querySelector('${stockForm} [role=alert]')?.textContent.includes('Inventory test validation error')`);
    assert.equal(await readField(stockForm, daysLabel), "21");
    assert.equal((await request(`/inventory/${stock.id}`)).expiry_days, 7);
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    const updatedStock = await request(`/inventory/${stock.id}`);
    assert.equal(updatedStock.expiry_days, 21);
    assert.equal(updatedStock.purchase_date, "2026-10-25");
    assert.equal(updatedStock.expiry_date, "2026-11-15");
    await click('.stock-action.edit');
    assert.equal(await readField(stockForm, daysLabel), "21");
    await fill(stockForm, daysLabel, "0");
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    assert.equal((await request(`/inventory/${stock.id}`)).expiry_date, "2026-10-25");
    console.log(`PASS ${width}px inventory editing: error retains inputs, retry recalculates expiry, zero days persists`);
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
