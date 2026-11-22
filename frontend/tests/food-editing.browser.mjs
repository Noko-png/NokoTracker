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
async function setInputValue(expression, value) {
  await evaluate(`(() => {
    const input = ${expression};
    const prototype = input.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}
async function fill(scope, label, value) {
  await setInputValue(field(scope, label), value);
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
async function assertStockFoodRestrictions(expectedUnits = ["g", "Packung"]) {
  const units = await evaluate(`Array.from((${field(stockForm, "Einheit")}).options).map(option => option.value).filter(Boolean)`);
  assert.deepEqual(units, expectedUnits);
  const editableFoodFields = await evaluate(`Array.from(document.querySelectorAll('${stockForm} label'))
    .filter(label => ['Kalorien / 100g', 'Protein / 100g', 'Fett / 100g', 'Kohlenhydrate / 100g', 'Umrechnungseinheit']
      .includes(label.querySelector('span')?.textContent))
    .filter(label => label.querySelector('input, select, textarea')).length`);
  assert.equal(editableFoodFields, 0);
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const width of [390, 1440]) {
    const reset = await request("/__calendar_test__/reset", "POST");
    assert.equal(reset.fixture, "calendar-create-memory");
    const unit = await request("/product-units", "POST", { name: "g" });
    await request("/product-units", "POST", { name: "kg" });
    await request("/product-units", "POST", { name: "oz" });
    const group = await request("/product-groups", "POST", { name: "Testgruppe", default_expiry_days: 7 });
    const food = await request("/foods", "POST", {
      name: "A Testlebensmittel", brand: "Testmarke", product_unit_id: unit.id,
      product_group_id: group.id, purchase_date: "2026-10-20", expiry_days: 7,
      conversions: [{ unit: "Packung", quantity: 500 }],
      calories_per_100g: 120, protein_per_100g: 5, fat_per_100g: 2, carbs_per_100g: 20,
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
    await assertStockFoodRestrictions();
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
    await waitFor("!document.querySelector('.loading-bar')");
    await click('.stock-action.edit');
    assert.equal(await readField(stockForm, daysLabel), "21");
    await fill(stockForm, daysLabel, "0");
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    assert.equal((await request(`/inventory/${stock.id}`)).expiry_date, "2026-10-25");
    console.log(`PASS ${width}px inventory editing: error retains inputs, retry recalculates expiry, zero days persists`);

    await clickButton('.inventory-overview-header', 'Bestand hinzufügen');
    await assertStockFoodRestrictions([]);
    assert.equal(await evaluate(`(${field(stockForm, 'Einheit')}).disabled`), true);
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('${stockForm} button')).some(button => button.textContent.trim() === 'Einheit')`), false);
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('${stockForm} .shopping-inventory-summary span'))
      .find(label => label.textContent === 'Kalorien / 100 g').nextElementSibling.textContent`), '—');
    await fill(stockForm, 'Lebensmittel', food.name);
    await waitFor(`(${field(stockForm, 'Einheit')}).value === 'g'`);
    assert.equal(await evaluate(`(${field(stockForm, 'Einheit')}).disabled`), false);
    await assertStockFoodRestrictions();
    assert.equal(await evaluate(`document.querySelector('${stockForm}').textContent.includes('120 kcal')`), true);
    await fill(stockForm, 'Lebensmittel', '');
    await waitFor(`(${field(stockForm, 'Einheit')}).disabled`);
    await assertStockFoodRestrictions([]);
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('${stockForm} .shopping-inventory-summary span'))
      .find(label => label.textContent === 'Kalorien / 100 g').nextElementSibling.textContent`), '—');
    await fill(stockForm, 'Lebensmittel', food.name);
    await waitFor(`(${field(stockForm, 'Einheit')}).value === 'g'`);
    await assertStockFoodRestrictions();
    await fill(stockForm, 'Einheit', 'Packung');
    await fill(stockForm, 'Menge', '1/2');
    await fill(stockForm, 'Einlagerungsdatum', updatedStock.purchase_date);
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    const storedRows = (await request('/inventory')).filter(item => item.food_id === food.id);
    assert.equal(storedRows.length, 1);
    const stored = storedRows[0];
    assert.equal(stored.id, stock.id);
    assert.equal(stored.unit, 'g');
    assert.equal(stored.quantity, 2.1);
    assert.equal(stored.calories_per_100g, 120);
    assert.equal(stored.protein_per_100g, 5);
    assert.equal(stored.fat_per_100g, 2);
    assert.equal(stored.carbs_per_100g, 20);
    assert.equal((await request('/product-units')).some(unit => unit.name === 'Packung'), false);
    console.log(`PASS ${width}px food storage: read-only nutrients, food-defined units, fractional conversion merged into existing stock without a new global unit`);

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

    const kilogram = (await request('/product-units')).find(unit => unit.name === 'kg');
    const mergeCases = [];
    for (const firstUnit of ['g', 'kg']) {
      const mergeFood = await request('/foods', 'POST', {
        name: `Mengentest ${firstUnit} zuerst`, product_unit_id: kilogram.id,
        serving_size: 1000, serving_unit: 'g', purchase_date: '2026-11-01',
        expiry_days: 7, storage_location: 'Vorrat', calories_per_100g: 100,
      });
      mergeCases.push({ food: mergeFood, firstUnit });
    }
    await click('[title="Bestandsübersicht"]');
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    for (const { food: mergeFood, firstUnit } of mergeCases) {
      let firstStock;
      const additions = firstUnit === 'g' ? [['g', '1000'], ['kg', '1']] : [['kg', '1'], ['g', '1000']];
      for (const [selectedUnit, quantity] of additions) {
        await clickButton('.inventory-overview-header', 'Bestand hinzufügen');
        await waitFor(`Array.from(document.querySelectorAll('#inventory-food-options option')).some(option => option.value.includes(${JSON.stringify(mergeFood.name)}))`);
        await fill(stockForm, 'Lebensmittel', mergeFood.name);
        await waitFor(`(${field(stockForm, 'Einheit')}).value === 'kg'`);
        await assertStockFoodRestrictions(['kg', 'g']);
        await fill(stockForm, 'Einheit', selectedUnit);
        await fill(stockForm, 'Menge', quantity);
        await click(`${stockForm} button[type=submit]`);
        await waitFor(`!document.querySelector('${stockForm}')`);
        const rows = (await request('/inventory')).filter(item => item.food_id === mergeFood.id);
        assert.equal(rows.length, 1);
        const row = rows[0];
        if (!firstStock) {
          firstStock = row;
          assert.equal(row.unit, 'kg');
          assert.equal(row.quantity, 1);
        } else {
          const total = 2;
          assert.equal(row.id, firstStock.id);
          assert.equal(row.unit, 'kg');
          assert.equal(row.quantity, total);
          assert.equal(row.purchase_date, firstStock.purchase_date);
          assert.equal(row.expiry_days, firstStock.expiry_days);
          assert.equal(row.storage_location, firstStock.storage_location);
          assert.equal(row.price, firstStock.price);
          await waitFor(`(() => {
            const cards = Array.from(document.querySelectorAll('.inventory-mobile-card'))
              .filter(card => card.querySelector('.inventory-mobile-product')?.textContent.includes(${JSON.stringify(mergeFood.name)}));
            return cards.length === 1 && cards[0].querySelector('.inventory-mobile-quantity')?.textContent.trim() === '2 kg';
          })()`);
        }
      }
    }
    console.log(`PASS ${width}px unit merging: both input orders use the food's primary kg unit; first stock ID and lot metadata retained`);

    const can = await request('/product-units', 'POST', { name: 'Dose' });
    const cannedFood = await request('/foods', 'POST', {
      name: 'Dosentomaten fuer Standardeinheit', product_unit_id: can.id,
      serving_size: 400, serving_unit: 'g', price: 2, conversions: [{ quantity: 2, unit: 'Portion' }],
      calories_per_100g: 40, protein_per_100g: 3, fat_per_100g: 1, carbs_per_100g: 4, expiry_days: 7,
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await clickButton('.inventory-overview-header', 'Bestand hinzufügen');
    await fill(stockForm, 'Lebensmittel', cannedFood.name);
    await waitFor(`(${field(stockForm, 'Einheit')}).value === 'Dose'`);
    await assertStockFoodRestrictions(['Dose', 'g', 'Portion']);
    assert.equal(await readField(stockForm, 'Preis pro Dose (optional)'), '2');
    await fill(stockForm, 'Einheit', 'g');
    await fill(stockForm, 'Menge', '800');
    assert.equal(await readField(stockForm, 'Preis pro g (optional)'), '0.005');
    assert.equal(await evaluate(`Array.from(document.querySelectorAll('${stockForm} .shopping-inventory-summary span'))
      .find(label => label.textContent === 'Bestandseinheit').nextElementSibling.textContent`), 'Dose');
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    let cannedStock = (await request('/inventory')).filter(row => row.food_id === cannedFood.id);
    assert.equal(cannedStock.length, 1);
    assert.equal(cannedStock[0].quantity, 2);
    assert.equal(cannedStock[0].unit, 'Dose');
    assert.equal(cannedStock[0].price, 2);
    assert.equal(cannedStock[0].product_unit_id, can.id);
    await evaluate(`Array.from(document.querySelectorAll('.inventory-mobile-card')).find(card => card.textContent.includes(${JSON.stringify(cannedFood.name)})).querySelector('.stock-action.edit').click()`);
    await waitFor(`Boolean(document.querySelector('${stockForm}'))`);
    await fill(stockForm, 'Einheit', 'g');
    await fill(stockForm, 'Menge', '300');
    await click(`${stockForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${stockForm}')`);
    cannedStock = (await request('/inventory')).filter(row => row.food_id === cannedFood.id);
    assert.equal(cannedStock[0].quantity, .75);
    assert.equal(cannedStock[0].unit, 'Dose');
    assert.equal(cannedStock[0].price, 2);
    await request('/meals/logs', 'POST', {
      food_id: cannedFood.id, user_id: 1, quantity: 100, unit: 'g', deduct_inventory: true,
      booking_key: `ui-standard-dose-${width}`,
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await waitFor(`Array.from(document.querySelectorAll('.inventory-mobile-card')).some(card => card.textContent.includes(${JSON.stringify(cannedFood.name)}) && card.querySelector('.inventory-mobile-quantity')?.textContent.trim() === '1/2 Dose')`);
    cannedStock = (await request('/inventory')).filter(row => row.food_id === cannedFood.id);
    assert.equal(cannedStock[0].quantity, .5);
    assert.equal(cannedStock[0].unit, 'Dose');
    assert.equal(cannedStock[0].serving_size, 400);
    assert.equal(cannedStock[0].serving_unit, 'g');
    assert.equal(cannedStock[0].food.conversions.find(conversion => conversion.unit === 'Portion').quantity, 2);
    console.log(`PASS ${width}px primary stock unit: grams are stored as cans, prices convert, stocktaking stays in cans and tracker gram deductions preserve food conversions`);

    const minimumFood = await request('/foods', 'POST', {
      name: 'Mindestbestand ohne Einlagerung', product_unit_id: kilogram.id,
      serving_size: 1000, serving_unit: 'g', minimum_quantity: 2,
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await waitFor("document.querySelector('.inventory-alert.low strong')?.textContent === '1'");
    await click('.inventory-minimum-stock summary');
    assert.match(await evaluate("document.querySelector('.inventory-minimum-stock').textContent"), /Mindestbestand ohne Einlagerung/);
    assert.match(await evaluate("document.querySelector('.inventory-minimum-stock').textContent"), /Fehlen: 2 kg/);
    assert.equal((await request('/inventory')).some(row => row.food_id === minimumFood.id), false);
    const planned = await request('/shopping-list/generate-from-low-stock', 'POST');
    assert.equal(planned.length, 1);
    assert.equal(planned[0].food_id, minimumFood.id);
    assert.equal(planned[0].quantity, 2);
    assert.equal(planned[0].unit, 'kg');
    await request('/inventory', 'POST', {
      name: minimumFood.name, food_id: minimumFood.id, quantity: 500, unit: 'g', minimum_quantity: 999,
      purchase_date: '2026-11-18',
    });
    await request('/inventory', 'POST', {
      name: minimumFood.name, food_id: minimumFood.id, quantity: .75, unit: 'kg',
      purchase_date: '2026-11-19',
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    assert.match(await evaluate("document.querySelector('.inventory-minimum-stock').textContent"), /Fehlen: 3\/4 kg/);
    await request(`/foods/${minimumFood.id}`, 'PATCH', { minimum_quantity: 1 });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await waitFor("document.querySelector('.inventory-alert.low strong')?.textContent === '0'");
    assert.equal(await evaluate("Boolean(document.querySelector('.inventory-minimum-stock'))"), false);
    console.log(`PASS ${width}px minimum stock: master data works without stock, lots convert into one total, changed master minimum applies immediately`);

    const shoppingFood = await request('/foods', 'POST', {
      name: 'Einkauf bis Mindestbestand', product_unit_id: kilogram.id,
      serving_size: 1000, serving_unit: 'g', minimum_quantity: 2,
    });
    await request('/inventory', 'POST', {
      name: shoppingFood.name, food_id: shoppingFood.id, quantity: 1, unit: 'kg',
    });
    const shoppingPlan = await request('/shopping-list', 'POST', {
      name: shoppingFood.name, food_id: shoppingFood.id, quantity: 250, unit: 'g',
    });
    await click('[title="Einkaufsliste"]');
    await clickButton('.shopping-header-actions', 'Aus Lagerbestand');
    await waitFor(`Array.from(document.querySelectorAll('.shopping-item')).some(row => row.textContent.includes(${JSON.stringify(shoppingFood.name)}) && row.textContent.includes('1000 g'))`);
    let shoppingRows = (await request('/shopping-list')).filter(row => row.food_id === shoppingFood.id);
    assert.equal(shoppingRows.length, 1);
    assert.equal(shoppingRows[0].id, shoppingPlan.id);
    assert.equal(shoppingRows[0].quantity, 1000);
    assert.equal(shoppingRows[0].unit, 'g');
    await clickButton('.shopping-header-actions', 'Aus Lagerbestand');
    await new Promise(resolve => setTimeout(resolve, 200));
    await waitFor("!document.querySelector('.loading-bar')");
    shoppingRows = (await request('/shopping-list')).filter(row => row.food_id === shoppingFood.id);
    assert.equal(shoppingRows.length, 1);
    assert.equal(shoppingRows[0].quantity, 1000);
    assert.equal(shoppingRows[0].unit, 'g');
    console.log(`PASS ${width}px shopping from stock: adds only remaining shortage, converts existing purchase units and repeated clicks keep the same quantity`);

    const groupForm = '.group-master-view .master-data-form';
    const priorityLabel = 'Einkaufspriorität (höhere Werte zuerst)';
    const shoppingNames = "Array.from(document.querySelectorAll('.shopping-item strong'), el => el.textContent)";
    await clickButton('.sidebar-master-options', 'Produktgruppen');
    await clickButton('.group-master-header', 'Hinzufügen');
    assert.equal(await readField(groupForm, priorityLabel), '0');
    await fill(groupForm, 'Name', 'Frische Ware');
    await fill(groupForm, priorityLabel, '5');
    await click(`${groupForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${groupForm}')`);
    const freshGroup = (await request('/product-groups')).find(row => row.name === 'Frische Ware');
    assert.equal(freshGroup.priority, 5);
    const apple = await request('/foods', 'POST', { name: 'Apfel', product_group_id: freshGroup.id });
    await request('/shopping-list', 'POST', { name: food.name, food_id: food.id });
    await request('/shopping-list', 'POST', { name: apple.name, food_id: apple.id });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await click('[title="Einkaufsliste"]');
    await waitFor(`${shoppingNames}.length === 4`);
    assert.deepEqual(await evaluate(shoppingNames), [apple.name, minimumFood.name, shoppingFood.name, food.name]);

    await clickButton('.sidebar-master-options', 'Produktgruppen');
    await evaluate("Array.from(document.querySelectorAll('.group-master-table tbody tr')).find(row => row.cells[1].textContent === 'Testgruppe').querySelector('[title=\"Produktgruppe bearbeiten\"]').click()");
    assert.equal(await readField(groupForm, priorityLabel), '0');
    await fill(groupForm, priorityLabel, '8');
    await click(`${groupForm} button[type=submit]`);
    await waitFor(`!document.querySelector('${groupForm}')`);
    assert.equal((await request(`/product-groups/${group.id}`)).priority, 8);
    await click('[title="Einkaufsliste"]');
    await waitFor(`${shoppingNames}.length === 4`);
    assert.deepEqual(await evaluate(shoppingNames), [food.name, apple.name, minimumFood.name, shoppingFood.name]);
    console.log(`PASS ${width}px shopping order: group priority can be set and updated, existing items follow the new order`);

    const openTextItem = await request('/shopping-list', 'POST', { name: 'Offener Freitext für später' });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor(`${shoppingNames}.includes(${JSON.stringify(openTextItem.name)})`);
    const bookButton = "document.querySelector('.shopping-header-actions .button.primary')";
    assert.equal(await evaluate(`${bookButton}.disabled`), true);
    await evaluate(`Array.from(document.querySelectorAll('.shopping-item')).find(row => row.textContent.includes(${JSON.stringify(shoppingFood.name)})).querySelector('.check-button').click()`);
    await waitFor(`${bookButton}.disabled === false`);
    await clickButton('.shopping-header-actions', 'In Bestand übernehmen');
    await waitFor(`!${shoppingNames}.includes(${JSON.stringify(shoppingFood.name)})`);
    assert.equal(await evaluate(`${bookButton}.disabled`), true);
    assert.deepEqual(await evaluate(shoppingNames), [food.name, apple.name, minimumFood.name, openTextItem.name]);
    const bookedStock = (await request('/inventory')).filter(row => row.food_id === shoppingFood.id);
    assert.equal(bookedStock.reduce((total, row) => total + row.quantity, 0), 2);
    console.log(`PASS ${width}px shopping import: the button requires a checked item and open food and text entries remain on the list`);

    const makeStock = (name, quantity) => request('/inventory', 'POST', {
      name, quantity, product_unit_id: kilogram.id, unit: 'kg', storage_location: 'Testlager', expiry_days: 7,
    });
    const smallLot = await makeStock('Teilmenge zum Entnehmen', .5);
    const exactLot = await makeStock('Genau eine Einheit', 1);
    const countedLot = await makeStock('Position für Bestandskorrektur', .5);
    const inventoryRow = (name) => `Array.from(document.querySelectorAll('.inventory-table tbody tr, .inventory-mobile-card'))
      .find(row => row.getClientRects().length && row.textContent.includes(${JSON.stringify(name)}))`;
    const stockButton = (name, action) => `${inventoryRow(name)}?.querySelector('.stock-action.${action}')`;
    const clickStockButton = async (name, action) => {
      const button = stockButton(name, action);
      await waitFor(`${button}?.disabled === false`);
      await evaluate(`${button}.click()`);
    };
    const removalDialog = '.inventory-underflow-dialog[open]';
    const dialogOpen = `document.querySelector('${removalDialog}') !== null`;
    await click('[title="Bestandsübersicht"]');
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");

    await clickStockButton(exactLot.name, 'decrement');
    await waitFor(`!(${inventoryRow(exactLot.name)})`);
    assert.equal(await evaluate(dialogOpen), false);
    assert.equal((await request(`/inventory/${exactLot.id}`)).quantity, 0);

    await clickStockButton(smallLot.name, 'decrement');
    await waitFor(dialogOpen);
    assert.match(await evaluate(`document.querySelector('${removalDialog}').textContent`), /Teilmenge zum Entnehmen.*Testlager.*unter 0/s);
    assert.equal(await evaluate('document.activeElement.textContent.trim()'), 'Abbrechen');
    await clickButton(removalDialog, 'Abbrechen');
    await waitFor(`!(${dialogOpen})`);
    assert.equal((await request(`/inventory/${smallLot.id}`)).quantity, .5);

    await clickStockButton(smallLot.name, 'decrement');
    await waitFor(dialogOpen);
    await request(`/inventory/${smallLot.id}/increase`, 'POST', { amount: .25 });
    await clickButton(removalDialog, 'Bestand löschen');
    await waitFor("document.querySelector('.notice.error')?.textContent.includes('inzwischen geändert')");
    assert.equal((await request(`/inventory/${smallLot.id}`)).quantity, .75);
    await clickStockButton(smallLot.name, 'decrement');
    await waitFor(dialogOpen);
    await clickButton(removalDialog, 'Bestand löschen');
    await waitFor(`!(${inventoryRow(smallLot.name)}) && !(${dialogOpen})`);
    assert.equal((await request('/inventory')).some(row => row.id === smallLot.id), false);

    await clickStockButton(countedLot.name, 'edit');
    await fill(stockForm, 'Menge', '-1/2');
    await click(`${stockForm} button[type=submit]`);
    await waitFor(dialogOpen);
    await clickButton(removalDialog, 'Abbrechen');
    await waitFor(`!(${dialogOpen})`);
    assert.equal(await readField(stockForm, 'Menge'), '-1/2');
    assert.equal((await request(`/inventory/${countedLot.id}`)).quantity, .5);
    await click(`${stockForm} button[type=submit]`);
    await waitFor(dialogOpen);
    await clickButton(removalDialog, 'Bestand löschen');
    await waitFor(`!(${dialogOpen}) && !document.querySelector('${stockForm}')`);
    assert.equal((await request('/inventory')).some(row => row.id === countedLot.id), false);
    assert.equal((await request(`/foods/${countedLot.food_id}`)).name, countedLot.name);
    console.log(`PASS ${width}px stock underflow: zero is saved, cancel leaves stock unchanged, changed stock is protected and only confirmation removes a lot`);

    const liter = await request('/product-units', 'POST', { name: 'l' });
    const broth = await request('/foods', 'POST', {
      name: 'Brühe mit Litereinheit', product_unit_id: liter.id, serving_unit: 'ml', serving_size: 1000,
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("!document.querySelector('.loading-bar')");
    await click('[title="Gerichte"]');
    await clickButton('.recipes-page .section-header', 'Gericht erstellen');
    await click('[title="Zutat hinzufuegen"]');
    const ingredientForm = '.recipe-builder-add-ingredient';
    const ingredientUnit = field(ingredientForm, 'Einheit');
    const ingredientUnits = `Array.from((${ingredientUnit}).options, option => option.value).filter(Boolean)`;
    assert.equal(await evaluate(`(${ingredientUnit}).disabled`), true);
    await fill(ingredientForm, 'Lebensmittel', cannedFood.name);
    assert.deepEqual(await evaluate(ingredientUnits), ['Dose', 'g', 'Portion']);
    await fill(ingredientForm, 'Einheit', 'Portion');
    await fill(ingredientForm, 'Lebensmittel', broth.name);
    assert.deepEqual(await evaluate(ingredientUnits), ['l', 'ml']);
    assert.equal(await evaluate(`(${ingredientUnit}).value`), 'l');
    await fill(ingredientForm, 'Lebensmittel', cannedFood.name);
    assert.deepEqual(await evaluate(ingredientUnits), ['Dose', 'g', 'Portion']);
    await click(`${ingredientForm} button[type=submit]`);

    const macroCards = "Array.from(document.querySelectorAll('.recipe-builder-nutrition-card > span'), el => el.textContent.trim())";
    const servingInput = "document.querySelector('input[aria-label=\"Serving Quantity\"]')";
    await waitFor(`${macroCards}[0] === '160 kcal per serving'`);
    await setInputValue(servingInput, '2');
    assert.deepEqual(await evaluate(macroCards), ['80 kcal per serving', '6 g per serving', '2 g per serving', '8 g per serving']);
    await setInputValue("document.querySelector('input[aria-label=Rezeptname]')", 'Tomaten als Testgericht');
    await clickButton('.recipe-builder-footer', 'Rezept anlegen');
    await waitFor("!document.querySelector('.recipe-builder-page')");
    const recipe = (await request('/recipes')).find(row => row.name === 'Tomaten als Testgericht');
    assert.equal(recipe.servings, 2);
    assert.equal(recipe.ingredients[0].unit, 'Dose');

    await clickButton('.recipe-card', 'Nährwerte');
    await waitFor("document.querySelector('.recipe-card .nutrition-mini') !== null");
    await click('[title="Gericht bearbeiten"]');
    await waitFor(`${macroCards}[0] === '80 kcal per serving'`);
    await setInputValue(servingInput, '4');
    assert.deepEqual(await evaluate(macroCards), ['40 kcal per serving', '3 g per serving', '1 g per serving', '4 g per serving']);
    await setInputValue(servingInput, '1/2');
    assert.equal(await evaluate(`${macroCards}[0]`), '320 kcal per serving');
    await setInputValue(servingInput, '');
    assert.equal(await evaluate(`${macroCards}[0]`), '—');
    assert.equal((await request(`/recipes/${recipe.id}`)).servings, 2);
    await click('[title="Zutat hinzufuegen"]');
    await fill(ingredientForm, 'Lebensmittel', cannedFood.name);
    assert.deepEqual(await evaluate(ingredientUnits), ['Dose', 'g', 'Portion']);
    await setInputValue(servingInput, '4');
    await clickButton('.recipe-builder-footer', 'Rezept speichern');
    await waitFor("!document.querySelector('.recipe-builder-page')");
    assert.equal(await evaluate("document.querySelector('.recipe-card .nutrition-mini') === null"), true);
    await clickButton('.recipe-card', 'Nährwerte');
    await waitFor("document.querySelector('.recipe-card .nutrition-mini strong')?.textContent === '40'");
    console.log(`PASS ${width}px recipes: only ingredient units are offered and nutrition follows draft servings in new and saved recipes without writing changes`);

    const [imageWidth, imageHeight] = width < 760 ? [720, 1280] : [1280, 720];
    const imagePath = await evaluate(`(() => {
      const canvas = document.createElement('canvas');
      canvas.width = ${imageWidth};
      canvas.height = ${imageHeight};
      const context = canvas.getContext('2d');
      context.fillStyle = '#194b73';
      context.fillRect(0, 0, canvas.width, canvas.height);
      return canvas.toDataURL('image/png');
    })()`);
    const steps = Array.from({ length: 12 }, (_, index) => `Testschritt ${index + 1}`);
    await request(`/recipes/${recipe.id}`, 'PATCH', {
      image_path: imagePath, description: 'Beschreibung unter dem Rezeptbild', instructions: steps.join('\n'),
    });
    await clickButton('.topbar-actions', 'Aktualisieren');
    await waitFor("document.querySelector('.recipe-card-image img')?.naturalWidth > 0");
    await clickButton('.recipe-card', 'Zubereiten');
    await waitFor("document.querySelector('.prepare-image img')?.naturalWidth > 0");
    const layout = await evaluate(`(() => {
      const panel = document.querySelector('.prepare-panel');
      const image = panel.querySelector('.prepare-image');
      const description = panel.querySelector('.prepare-section');
      const imageBottom = image.getBoundingClientRect().bottom;
      const descriptionTop = description.getBoundingClientRect().top;
      panel.scrollTop = panel.scrollHeight;
      return {
        imageBottom,
        descriptionTop,
        scrolled: panel.scrollTop > 0,
        lastStepVisible: panel.querySelector('.prepare-step:last-child').getBoundingClientRect().bottom <= panel.getBoundingClientRect().bottom,
      };
    })()`);
    assert.ok(layout.imageBottom <= layout.descriptionTop, `Recipe image overlaps the description: ${JSON.stringify(layout)}`);
    assert.ok(layout.scrolled && layout.lastStepVisible, 'Preparation steps must remain reachable by scrolling');
    console.log(`PASS ${width}px recipe preparation: the image has its own space and all steps remain reachable`);
  }
} finally {
  await send("Page.navigate", { url: "about:blank" });
  await send("Fetch.disable");
  socket.close();
}
