import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

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
async function clickButton(scope, text) {
  const expression = `Array.from(document.querySelectorAll(${JSON.stringify(`${scope} button`)})).find(el => el.textContent.trim() === ${JSON.stringify(text)})`;
  await waitFor(`Boolean(${expression})`);
  await evaluate(`${expression}.click()`);
}
async function screenshot(name) {
  if (!process.env.FOOD_TEST_SCREENSHOTS) return;
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  await writeFile(join(process.env.FOOD_TEST_SCREENSHOTS, name), Buffer.from(data, 'base64'));
}
const foodForm = ".food-editor-modal form";
const stockForm = ".inventory-edit-modal form";
const daysLabel = "Haltbarkeit bis Ablauf (Tage)";
const fiberLabel = "Ballaststoffe (g / 100 g)";
const sugarLabel = "Zucker (g / 100 g)";
const caffeineLabel = "Koffein (mg / 100 g, optional)";
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
    await waitFor("!document.querySelector('.loading-bar')");
    await click('[title="Stammdaten verwalten"]');
    await waitFor("Array.from(document.querySelectorAll('.sidebar-master-option')).some(el => el.textContent.trim() === 'Lebensmittel')");
    await evaluate("Array.from(document.querySelectorAll('.sidebar-master-option')).find(el => el.textContent.trim() === 'Lebensmittel').click()");
    await click('[title="Lebensmittel bearbeiten"]');
    assert.equal(await readField(foodForm, caffeineLabel), "");
    await fill(foodForm, fiberLabel, "2.75");
    await fill(foodForm, sugarLabel, "8.5");
    await fill(foodForm, caffeineLabel, "32.5");
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
    assert.equal(updatedFood.fiber_per_100g, 2.75);
    assert.equal(updatedFood.sugar_per_100g, 8.5);
    assert.equal(updatedFood.caffeine_mg_per_100g, 32.5);
    await click('[title="Lebensmittel bearbeiten"]');
    assert.equal(await readField(foodForm, fiberLabel), "2.75");
    assert.equal(await readField(foodForm, sugarLabel), "8.5");
    assert.equal(await readField(foodForm, caffeineLabel), "32.5");
    await evaluate(`${field(foodForm, caffeineLabel)}.scrollIntoView({ block: 'center' })`);
    await screenshot(`food-nutrients-${width}.png`);
    await fill(foodForm, caffeineLabel, "0");
    assert.equal(await readField(foodForm, daysLabel), "14");
    await fill(foodForm, daysLabel, "0");
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${foodForm}')`);
    assert.equal((await request(`/foods/${food.id}`)).expiry_days, 0);
    assert.equal((await request(`/foods/${food.id}`)).caffeine_mg_per_100g, 0);
    await click('[title="Lebensmittel bearbeiten"]');
    assert.equal(await readField(foodForm, caffeineLabel), "0");
    await fill(foodForm, caffeineLabel, "");
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${foodForm}')`);
    assert.equal((await request(`/foods/${food.id}`)).caffeine_mg_per_100g, null);
    console.log(`PASS ${width}px food editing: conflict retains inputs, retry saves, nutrients persist, caffeine zero and empty stay distinct`);

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

    if (!await evaluate("Boolean(document.querySelector('.sidebar-master-options'))")) {
      await click('[title="Stammdaten verwalten"]');
    }
    await clickButton('.sidebar-master-options', 'Lebensmittel');
    await clickButton('.food-master-header', 'Aus EAN erstellen');
    await waitFor("document.querySelector('.food-editor-modal h2')?.textContent === 'Lebensmittel aus EAN erstellen'");
    assert.equal(await evaluate(`(() => {
      const header = document.querySelector('.food-editor-modal .panel-header');
      const rect = header.getBoundingClientRect();
      return header.contains(document.elementFromPoint(rect.x + 10, rect.y + 10));
    })()`), true, 'EAN dialog title must remain above the mobile app bar');
    assert.equal(await evaluate(`Boolean(document.querySelector('${foodForm} input[required]'))`), false);
    await fill(foodForm, 'EAN-Code', '0012345678905');
    await screenshot(`ean-create-${width}.png`);
    await clickButton(foodForm, 'Erstellen / öffnen');
    await waitFor("document.querySelector('.food-barcode-inline-status')?.textContent.includes('in den Stammdaten gespeichert')");
    assert.equal(await readField(foodForm, 'Name'), 'EAN Testdrink');
    assert.equal(await readField(foodForm, 'Markenname (optional)'), 'EAN Testmarke');
    assert.equal(await readField(foodForm, 'Kalorien / 100g'), '46');
    assert.equal(await readField(foodForm, fiberLabel), '0.75');
    assert.equal(await readField(foodForm, sugarLabel), '4.2');
    assert.equal(await readField(foodForm, caffeineLabel), '32');
    await screenshot(`ean-created-${width}.png`);
    const imported = (await request('/foods')).find(item => item.name === 'EAN Testdrink');
    assert.ok(imported);
    assert.equal(imported.serving_size, 250);
    assert.equal(imported.serving_unit, 'ml');
    assert.deepEqual(imported.barcodes, ['0012345678905']);
    assert.equal((await request('/inventory')).length, 1);
    assert.equal((await request('/meals/logs')).length, 0);
    await fill(foodForm, daysLabel, '14');
    await click(`${foodForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${foodForm}')`);
    assert.equal((await request(`/foods/${imported.id}`)).expiry_days, 14);
    await clickButton('.food-master-header', 'Aus EAN erstellen');
    await fill(foodForm, 'EAN-Code', '0012345678905');
    await clickButton(foodForm, 'Erstellen / öffnen');
    await waitFor("document.querySelector('.food-barcode-inline-status')?.textContent.includes('in den Stammdaten gespeichert')");
    assert.equal(await readField(foodForm, daysLabel), '14');
    assert.equal((await request('/foods')).filter(item => item.name === 'EAN Testdrink').length, 1);
    await click('.food-editor-modal [title="Schliessen"]');
    await clickButton('.food-master-header', 'Aus EAN erstellen');
    for (const [code, expected] of [['123', 'gueltigen'], ['5012345678900', 'nicht erreichbar'], ['4012345678901', 'kein Lebensmittel']]) {
      await fill(foodForm, 'EAN-Code', code);
      await clickButton(foodForm, 'Erstellen / öffnen');
      await waitFor(`document.querySelector('${foodForm} [role=status]')?.textContent.includes(${JSON.stringify(expected)})`);
    }
    assert.equal((await request('/foods')).length, 3);
    await clickButton(foodForm, 'Manuell anlegen');
    assert.equal(await readField(foodForm, 'EAN-Code 1'), '4012345678901');
    assert.equal(await readField(foodForm, 'Name'), '');
    await click('.food-editor-modal [title="Schliessen"]');
    console.log(`PASS ${width}px EAN creation: full master data, repeated scan opens existing product, editing, error recovery and manual fallback`);
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
