import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Use only database_ui_fixture and a dedicated browser, never the normal app DB.
const api = process.env.DATABASE_TEST_API_URL ?? "http://127.0.0.1:8022";
const frontend = process.env.DATABASE_TEST_FRONTEND_URL ?? "http://127.0.0.1:5182";
const cdp = process.env.DATABASE_TEST_CDP_URL ?? "http://127.0.0.1:9232";
const fixture = await (await fetch(`${api}/__database_test__/reset`, { method: "POST" })).json();
assert.equal(fixture.fixture, "database-transfer-disposable");
const directory = await mkdtemp(join(tmpdir(), "noko-transfer-browser-"));
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
    void send("Fetch.continueRequest", { requestId, url: request.url.replace("http://127.0.0.1:8000", api) });
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
async function upload(file) {
  const { root } = await send("DOM.getDocument");
  const { nodeId } = await send("DOM.querySelector", { nodeId: root.nodeId, selector: 'input[type="file"][accept=".db,.sqlite,.sqlite3"]' });
  assert.ok(nodeId);
  await send("DOM.setFileInputFiles", { nodeId, files: [file] });
  await waitFor("!!document.querySelector('.database-import-selection')");
}
async function apiData(path) {
  const response = await fetch(`${api}${path}`);
  assert.ok(response.ok, `${response.status} ${path}`);
  return response.json();
}
try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "http://127.0.0.1:8000/*" }] });
  for (const [name, width, height] of [["desktop", 1440, 1000], ["mobile", 390, 844]]) {
    await fetch(`${api}/__database_test__/reset`, { method: "POST" });
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: name === "mobile" });
    await send("Page.navigate", { url: frontend });
    await waitFor("Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === 'Einstellungen')");
    await clickText("Einstellungen");
    await upload(sourceFile);
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
    // Re-selecting the same file after success must work without refreshing.
    await upload(sourceFile);
    await evaluate("const select = Array.from(document.querySelectorAll('select')).find(el => Array.from(el.options).some(option => option.value === 'recipes')); select.value='recipes'; select.dispatchEvent(new Event('change', { bubbles:true }))");
    await waitFor("document.querySelector('.database-import-selection legend')?.textContent === 'Rezepte auswaehlen'");
    await evaluate("Array.from(document.querySelectorAll('.database-import-selection label')).find(label => label.textContent.trim() === 'Importrezept').querySelector('input').click()");
    if (process.env.DATABASE_TEST_SCREENSHOTS) {
      await evaluate("document.querySelector('.database-import-selection').scrollIntoView({block:'center'})");
      const screenshot = await send("Page.captureScreenshot", { format: "png" });
      await writeFile(join(process.env.DATABASE_TEST_SCREENSHOTS, `database-import-${name}.png`), Buffer.from(screenshot.data, "base64"));
    }
    await clickText("Ausgewaehlte Rezepte hinzufuegen");
    await waitFor("document.querySelector('.database-transfer-result')?.textContent.includes('Ausgewaehlte Rezepte hinzugefuegt.')");
    const recipes = await apiData("/recipes");
    assert.deepEqual(recipes.map(recipe => recipe.name).sort(), ["Importrezept", "Vorhandenes Rezept"]);
    assert.equal(recipes.find(recipe => recipe.name === "Importrezept").ingredients[0].quantity, 125.25);
    await clickText("Gerichte");
    await waitFor("document.querySelectorAll('.recipe-actions button[title=\"Einzelnes Rezept mit Zutaten exportieren\"]').length === 2");
    assert.equal(await evaluate("document.documentElement.scrollWidth > window.innerWidth"), false, `${name} overflows`);
    const recipeId = recipes.find(recipe => recipe.name === "Importrezept").id;
    const response = await fetch(`${api}/database/recipes/${recipeId}/export`);
    assert.ok(response.ok);
    const recipeFile = join(directory, `recipe-${name}.db`);
    await writeFile(recipeFile, Buffer.from(await response.arrayBuffer()));
    await clickText("Rezepte importieren");
    await upload(recipeFile);
    assert.equal(await evaluate("document.querySelector('.database-import-selection').querySelectorAll('input:checked').length"), 1);
    assert.equal(await evaluate("Array.from(document.querySelectorAll('select')).find(el => Array.from(el.options).some(option => option.value === 'recipes')).options.length"), 1);
    console.log(`${name}: weight-only import, cancelled confirmation, recipe selection, repeated file, export and recipe-file detection passed`);
  }
  assert.ok(confirmations.some(message => message.includes("Datenbereich")));
  assert.ok(confirmations.some(message => message.includes("Rezept(e)")));
} finally {
  socket.close();
  await rm(directory, { recursive: true, force: true });
}
