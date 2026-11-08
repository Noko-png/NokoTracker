import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";

// Use only database_ui_fixture and a dedicated browser, never the normal app DB.
const api = process.env.DATABASE_TEST_API_URL ?? "http://127.0.0.1:8022";
const frontend = process.env.DATABASE_TEST_FRONTEND_URL ?? "http://127.0.0.1:5182";
const cdp = process.env.DATABASE_TEST_CDP_URL ?? "http://127.0.0.1:9232";
const fixture = await (await fetch(`${api}/__database_test__/reset`, { method: "POST" })).json();
assert.equal(fixture.fixture, "database-transfer-disposable");
const directory = await mkdtemp(join(tmpdir(), "noko-transfer-browser-"));
assert.equal(resolve(dirname(directory)), resolve(tmpdir()));
assert.ok(basename(directory).startsWith("noko-transfer-browser-"));
const sourceFile = join(directory, "source.db");
await writeFile(sourceFile, Buffer.from(await (await fetch(`${api}/__database_test__/source`)).arrayBuffer()));
const pages = await (await fetch(`${cdp}/json/list`)).json();
const page = pages.find(item => item.type === "page");
assert.ok(page, "Start a separate headless Chrome instance for this test");
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});
let sequence = 0;
let cancelConfirmation = false;
let rejectDuplicate = false;
let nonAdmin = false;
const confirmations = [];
const requests = [];
const pending = new Map();
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
    requests.push(request.url);
    if (rejectDuplicate && request.url.endsWith("/recipes/7/duplicate")) {
      rejectDuplicate = false;
      void send("Fetch.fulfillRequest", {
        requestId, responseCode: 409,
        responseHeaders: [{ name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: "*" }],
        body: Buffer.from(JSON.stringify({ detail: "Test: Kopie konnte nicht angelegt werden." })).toString("base64"),
      });
    } else if (nonAdmin && request.url.endsWith("/session")) {
      void send("Fetch.fulfillRequest", {
        requestId, responseCode: 200,
        responseHeaders: [{ name: "Content-Type", value: "application/json" }, { name: "Access-Control-Allow-Origin", value: "*" }],
        body: Buffer.from(JSON.stringify({ is_admin: false, user_id: 42, ha_user_id: "recipe-test-user", ha_username: "Test", admin_configured: true })).toString("base64"),
      });
    } else {
      void send("Fetch.continueRequest", { requestId, url: request.url.replace("http://127.0.0.1:8000", api) });
    }
  } else if (message.method === "Page.javascriptDialogOpening") {
    confirmations.push(message.params.message);
    void send("Page.handleJavaScriptDialog", { accept: !cancelConfirmation });
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
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Not ready: ${expression}`);
}
async function clickText(text) {
  const expression = `Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === ${JSON.stringify(text)})`;
  await waitFor(`!!(${expression})`);
  await evaluate(`(${expression}).click()`);
}
async function upload(file, waitForPreview = true) {
  const { root } = await send("DOM.getDocument");
  const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: 'input[type="file"][accept=".db,.sqlite,.sqlite3"]' });
  assert.ok(nodeId);
  await send("DOM.setFileInputFiles", { nodeId, files: [file] });
  if (waitForPreview) await waitFor("!!document.querySelector('.database-import-selection')");
}
async function apiData(path) {
  const response = await fetch(`${api}${path}`);
  assert.ok(response.ok, `${response.status} ${path}`);
  return response.json();
}
async function fill(selector, value) {
  await evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(selector)});
    const prototype = input.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}
async function screenshot(name) {
  if (!process.env.DATABASE_TEST_SCREENSHOTS) return;
  const screenshot = await send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(process.env.DATABASE_TEST_SCREENSHOTS, name), Buffer.from(screenshot.data, "base64"));
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: directory });
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
    nonAdmin = false;
    await fetch(`${api}/__database_test__/reset`, { method: "POST" });
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: name === "mobile" });
    await send("Page.navigate", { url: frontend });
    await waitFor("Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === 'Einstellungen')");
    await clickText("Einstellungen");
    await upload(sourceFile);
    assert.equal(await evaluate("Array.from(document.querySelectorAll('#database-transfer select option')).some(option => option.value === 'recipes')"), false);
    assert.equal(await evaluate("document.querySelector('.database-import-selection').querySelectorAll('input:checked').length"), 0);
    assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === 'Ausgewaehlte Bereiche ersetzen').disabled"), true);
    await evaluate("Array.from(document.querySelectorAll('.database-import-selection label')).find(label => label.textContent.includes('Gewichtsdaten')).querySelector('input').click()");
    const before = await Promise.all([apiData("/foods"), apiData("/recipes"), apiData("/users")]);
    cancelConfirmation = true;
    const cancelledCount = requests.filter(url => url.endsWith("/database/import")).length;
    await clickText("Ausgewaehlte Bereiche ersetzen");
    await waitFor("!Array.from(document.querySelectorAll('button')).find(button => button.textContent.trim() === 'Ausgewaehlte Bereiche ersetzen').disabled");
    assert.equal(requests.filter(url => url.endsWith("/database/import")).length, cancelledCount);
    cancelConfirmation = false;
    await clickText("Ausgewaehlte Bereiche ersetzen");
    await waitFor("document.querySelector('.database-transfer-result')?.textContent.includes('Ausgewaehlte Datenbereiche ersetzt.')");
    const weight = await apiData("/weight-entries?user_id=42");
    assert.equal(weight.length, 1);
    assert.equal(weight[0].weight_kg, 80);
    assert.equal(weight[0].user_id, 42);
    assert.deepEqual(await Promise.all([apiData("/foods"), apiData("/recipes"), apiData("/users")]), before);
    const databaseMessage = await evaluate("document.querySelector('.database-transfer-result').textContent");
    const original = (await apiData("/recipes")).find(recipe => recipe.id === 7);
    const response = await fetch(`${api}/recipes/7/export`);
    assert.ok(response.ok);
    const recipeFile = join(directory, `recipe-${name}.db`);
    await writeFile(recipeFile, Buffer.from(await response.arrayBuffer()));
    // General database imports only handle database restoration.
    await upload(recipeFile, false);
    await waitFor("document.querySelector('#database-transfer [role=alert]')?.textContent.includes('Gerichte')");
    assert.equal(await evaluate("!!document.querySelector('.database-import-selection')"), false);
    // Re-selecting a valid database still works after rejecting a recipe file.
    await upload(sourceFile);
    await clickText("Gerichte");
    await waitFor("document.querySelectorAll('.recipe-more-button').length === 1");
    assert.equal(await evaluate("Array.from(document.querySelectorAll('.recipe-actions button')).some(button => button.textContent.includes('Exportieren'))"), false);
    await evaluate("document.querySelector('.recipe-more-button').click()");
    await waitFor("document.querySelectorAll('.recipe-more-menu [role=menuitem]').length === 2");
    await evaluate("document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key:'Escape', bubbles:true }))");
    assert.equal(await evaluate("!!document.querySelector('.recipe-more-menu')"), false);
    assert.equal(await evaluate("document.activeElement.classList.contains('recipe-more-button')"), true);
    await evaluate("document.querySelector('.recipe-more-button').click()");
    await clickText("Exportieren");
    await waitFor("document.querySelector('.recipes-page [role=status]')?.textContent.includes('heruntergeladen')");
    assert.ok(requests.some(url => url.endsWith("/recipes/7/export")));
    assert.equal(await evaluate("!!document.querySelector('.recipe-more-menu')"), false);

    await clickText("Rezepte importieren");
    await waitFor("!!document.querySelector('.recipe-import-dialog')");
    assert.equal(await evaluate("!!document.querySelector('.settings-layout')"), false);
    assert.equal(await evaluate("(() => { const button=document.querySelector('.recipe-import-dialog button'); const rect=button.getBoundingClientRect(); return document.elementFromPoint(rect.x+rect.width/2, rect.y+rect.height/2)?.closest('button') === button })()"), true, "Import dialog must cover the mobile app bar");
    await upload(sourceFile);
    assert.equal(await evaluate("document.querySelector('.recipe-import-dialog select') === null"), true);
    assert.equal(await evaluate("document.querySelector('.database-import-selection').querySelectorAll('input:checked').length"), 0);
    await evaluate("Array.from(document.querySelectorAll('.database-import-selection label')).find(label => label.textContent.trim() === 'Importrezept').querySelector('input').click()");
    await screenshot(`recipe-import-${name}.png`);
    await clickText("Ausgewaehlte Rezepte hinzufuegen");
    await waitFor("document.querySelector('.recipe-import-dialog [role=status]')?.textContent.includes('1 Rezept(e) hinzugefuegt.')");
    const recipes = await apiData("/recipes");
    assert.deepEqual(recipes.map(recipe => recipe.name).sort(), ["Importrezept", "Vorhandenes Rezept"]);
    assert.equal(recipes.find(recipe => recipe.name === "Importrezept").ingredients[0].quantity, 125.25);
    assert.deepEqual(recipes.find(recipe => recipe.id === 7), original);
    await upload(sourceFile);
    assert.equal(await evaluate("document.querySelector('.database-import-selection').querySelectorAll('input:checked').length"), 0);
    await evaluate("document.querySelector('[aria-label=\"Rezeptimport schliessen\"]').click()");
    await clickText("Rezepte importieren");
    await upload(recipeFile);
    assert.equal(await evaluate("document.querySelector('.database-import-selection').querySelectorAll('input:checked').length"), 1);
    await evaluate("document.querySelector('[aria-label=\"Rezeptimport schliessen\"]').click()");

    // An API failure leaves the source intact and allows a clean retry.
    rejectDuplicate = true;
    await evaluate("document.querySelector('[aria-label=\"Weitere Aktionen fuer Vorhandenes Rezept\"]').click()");
    await clickText("Duplizieren");
    await waitFor("document.body.innerText.includes('Test: Kopie konnte nicht angelegt werden.')");
    assert.equal(await evaluate("!!document.querySelector('.recipe-builder-page')"), false);
    assert.equal((await apiData("/recipes")).length, 2);
    const duplicateRequests = requests.filter(url => url.endsWith("/recipes/7/duplicate")).length;
    await evaluate("document.querySelector('[aria-label=\"Weitere Aktionen fuer Vorhandenes Rezept\"]').click()");
    await clickText("Duplizieren");
    await waitFor("document.querySelector('input[aria-label=Rezeptname]')?.value === 'Vorhandenes Rezept (Kopie)'");
    assert.equal(requests.filter(url => url.endsWith("/recipes/7/duplicate")).length, duplicateRequests + 1);
    const copied = (await apiData("/recipes")).find(recipe => recipe.name === "Vorhandenes Rezept (Kopie)");
    assert.ok(copied);
    assert.notEqual(copied.id, original.id);
    assert.notEqual(copied.prepared_food_id, original.prepared_food_id);
    assert.equal(copied.ingredients[0].quantity, 125.25);
    assert.equal(copied.ingredients[0].notes, "Fein schneiden");
    assert.equal(copied.instructions, original.instructions);
    assert.equal(copied.prep_time_minutes, 10);
    assert.equal(copied.cook_time_minutes, 20);
    assert.equal(await evaluate("document.querySelector('.recipe-builder-topbar h2').textContent.trim()"), "Rezept bearbeiten");
    await screenshot(`recipe-duplicate-${name}.png`);
    await fill('input[aria-label="Rezeptname"]', "Vorhandenes Rezept v2");
    await evaluate("document.querySelector('.recipe-builder-amount input').focus()");
    await fill('.recipe-builder-amount input', "77.125");
    await evaluate("document.querySelector('.recipe-builder-amount input').blur()");
    await waitFor("document.querySelector('.recipe-builder-ingredients').textContent.includes('77')");
    await clickText("Rezept speichern");
    await waitFor("!document.querySelector('.recipe-builder-page')");
    const afterCopy = await apiData("/recipes");
    const version2 = afterCopy.find(recipe => recipe.id === copied.id);
    assert.equal(version2.name, "Vorhandenes Rezept v2");
    assert.equal(version2.ingredients[0].quantity, 77.125);
    assert.deepEqual(afterCopy.find(recipe => recipe.id === original.id), original);
    assert.equal((await apiData("/weight-entries?user_id=42"))[0].weight_kg, 80);
    assert.equal(await evaluate("document.documentElement.scrollWidth > window.innerWidth"), false, `${name} overflows`);
    assert.ok(await evaluate("Array.from(document.querySelectorAll('.recipe-card-heading h3')).every(heading => heading.getBoundingClientRect().width > 120)"), `${name} recipe names must remain readable beside the menu`);
    assert.ok(await evaluate("Array.from(document.querySelectorAll('.recipe-card')).every(card => card.getBoundingClientRect().height < 500)"), `${name} recipe cards must not stretch into narrow columns`);
    await evaluate("window.scrollTo(0,0)");
    await screenshot(`recipe-actions-${name}.png`);
    await clickText("Einstellungen");
    assert.equal(await evaluate("document.querySelector('.database-transfer-result').textContent"), databaseMessage);
    nonAdmin = true;
    await send("Page.reload");
    await waitFor("Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === 'Gerichte')");
    await clickText("Gerichte");
    await waitFor("document.querySelectorAll('.recipe-more-button').length === 3");
    assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === 'Rezepte importieren')"), false);
    await evaluate("document.querySelector('[aria-label=\"Weitere Aktionen fuer Vorhandenes Rezept\"]').click()");
    await waitFor("!!document.querySelector('.recipe-more-menu')");
    assert.equal(await evaluate("Array.from(document.querySelectorAll('.recipe-more-menu button')).map(button => button.textContent.trim()).join(',')"), "Duplizieren");
    console.log(`${name}: separate database/recipe imports, subtle export menu, duplicate-and-edit, failure/retry, independent variant and user permissions passed`);
  }
  // Duplicates must stay editable after reloads even beyond a full API page.
  nonAdmin = false;
  await fetch(`${api}/__database_test__/reset`, { method: "POST" });
  await fetch(`${api}/__database_test__/many-recipes`, { method: "POST" });
  await send("Page.reload");
  await waitFor("Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === 'Gerichte')");
  await clickText("Gerichte");
  await waitFor("document.querySelectorAll('.recipe-card').length === 501");
  await evaluate("document.querySelector('[aria-label=\"Weitere Aktionen fuer Vorhandenes Rezept\"]').click()");
  await clickText("Duplizieren");
  await waitFor("document.querySelector('input[aria-label=Rezeptname]')?.value === 'Vorhandenes Rezept (Kopie)' && document.querySelectorAll('.recipe-builder-ingredient').length === 1");
  await clickText("Rezept speichern");
  await waitFor("document.querySelectorAll('.recipe-card').length === 502");
  assert.ok(await evaluate("Array.from(document.querySelectorAll('.recipe-card h3')).some(heading => heading.textContent.includes('Vorhandenes Rezept (Kopie)'))"));
  console.log("Large recipe collection: all pages loaded; new copy remains editable and visible after saving");
  assert.ok(confirmations.some(message => message.includes("Datenbereich")));
  assert.ok(requests.some(url => url.endsWith("/recipes/import/preview")));
  assert.ok(requests.some(url => url.endsWith("/recipes/import")));
  assert.equal(requests.some(url => url.includes("/database/recipes/")), false);
} finally {
  socket.close();
  await rm(directory, { recursive: true, force: true });
}
