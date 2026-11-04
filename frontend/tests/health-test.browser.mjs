import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';

// Separate headless browser and in-memory API fixture; no production data.
const api = process.env.HEALTH_TEST_API_URL ?? 'http://127.0.0.1:8028';
const frontend = process.env.HEALTH_TEST_FRONTEND_URL ?? 'http://127.0.0.1:5188';
const cdp = process.env.HEALTH_TEST_CDP_URL ?? 'http://127.0.0.1:9238';
const pages = await (await fetch(`${cdp}/json/list`)).json();
const page = pages.find(item => item.type === 'page');
assert.ok(page, 'Start a separate headless Chrome for the test');
const socket = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true });
  socket.addEventListener('error', reject, { once: true });
});
let sequence = 0;
const pending = new Map();
let fixture = null;
let nonAdmin = false;
let lastHealthUrl = '';
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
socket.addEventListener('message', ({ data }) => {
  const message = JSON.parse(data);
  if (message.id) {
    const call = pending.get(message.id);
    pending.delete(message.id);
    message.error ? call.reject(new Error(JSON.stringify(message.error))) : call.resolve(message.result);
  } else if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params;
    if (request.url.includes('/health-connect/test')) lastHealthUrl = request.url;
    const answer = nonAdmin && request.url.endsWith('/session')
      ? { status: 200, body: { is_admin: false, user_id: 1, ha_user_id: 'test-user', ha_username: 'test', admin_configured: true } }
      : request.url.includes('/health-connect/test') ? fixture : null;
    if (answer) {
      void send('Fetch.fulfillRequest', {
        requestId, responseCode: answer.status,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }],
        body: Buffer.from(JSON.stringify(answer.body)).toString('base64'),
      });
    } else {
      void send('Fetch.continueRequest', { requestId, url: request.url.replace('http://127.0.0.1:8000', api) });
    }
  }
});
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true });
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
async function click(selector) {
  await waitFor(`!!document.querySelector(${JSON.stringify(selector)})`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
const checked_at = '2026-11-04T12:00:00+00:00';
const reading = (kind, value, unit, suffix, extra = {}) => ({
  entity_id: `sensor.testphone_health_connect_${suffix}`, name: 'Testhandy', kind,
  value, unit, state: 'available', last_updated: checked_at, selection: 'automatic', ...extra,
});
const healthy = { status: 200, body: { status: 'connected', message: 'Verbindung zu Home Assistant hergestellt.', checked_at,
  sensors: [reading('steps', 9876, 'steps', 'daily_steps'), reading('heart_rate', 72, 'bpm', 'heart_rate'), reading('sleep', 450, 'min', 'sleep_duration')] } };
async function refresh() {
  await click('.health-test-intro button');
  await waitFor("!document.querySelector('.health-test [aria-busy=true]')");
}
try {
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Fetch.enable', { patterns: [{ urlPattern: 'http://127.0.0.1:8000/*' }] });
  const reset = await (await fetch(`${api}/__calendar_test__/reset`, { method: 'POST' })).json();
  assert.equal(reset.fixture, 'calendar-create-memory');
  for (const width of [390, 1440]) {
    fixture = null;
    await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 760 });
    await send('Page.navigate', { url: frontend });
    await waitFor("document.body.innerText.includes('Kalendertest') && !document.querySelector('.loading-bar')");
    await click('[title="Test Health dashboard"]');
    await waitFor("document.querySelector('.health-test-status')?.textContent.includes('Lokal besteht keine Verbindung')");
    assert.equal(await evaluate("document.querySelector('.topbar h1').textContent"), 'Test Health dashboard');
    fixture = healthy;
    await refresh();
    assert.equal(await evaluate("document.querySelectorAll('.health-test-card').length"), 3);
    assert.match(await evaluate("document.querySelector('.health-test-grid').textContent"), /9\.876/);
    assert.ok(await evaluate("document.querySelector('.health-test-grid').textContent.includes('72')"));
    assert.ok(await evaluate("document.querySelector('.health-test-grid').textContent.includes('450')"));
    assert.ok(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), `${width}px layout overflows`);
    if (process.env.HEALTH_TEST_SCREENSHOTS) {
      const { data } = await send('Page.captureScreenshot', { format: 'png' });
      await writeFile(join(process.env.HEALTH_TEST_SCREENSHOTS, `health-test-${width}.png`), Buffer.from(data, 'base64'));
    }
    fixture = { ...healthy, body: { ...healthy.body, sensors: [reading('steps', 0, 'steps', 'daily_steps'), reading('heart_rate', null, 'bpm', 'heart_rate', { state: 'unavailable' })] } };
    await refresh();
    assert.match(await evaluate("document.querySelector('[data-entity$=daily_steps] .health-reading-value').textContent"), /^0/);
    assert.match(await evaluate("document.querySelector('[data-entity$=heart_rate]').textContent"), /Sensor nicht verfügbar/);
    await click('.health-test details summary');
    await evaluate(`(() => {
      const input = document.querySelectorAll('.health-test-inputs input')[1];
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, 'sensor.mein_puls');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    })()`);
    fixture = { ...healthy, body: { ...healthy.body, sensors: [reading('heart_rate', 65, 'bpm', 'heart_rate', { entity_id: 'sensor.mein_puls', selection: 'manual' })] } };
    await click('.health-test form button');
    await waitFor("!!document.querySelector('[data-entity=\"sensor.mein_puls\"]')");
    assert.equal(new URL(lastHealthUrl).searchParams.get('pulse_entity'), 'sensor.mein_puls');
    fixture = { status: 502, body: { detail: 'Home Assistant ist momentan nicht erreichbar.' } };
    await refresh();
    assert.match(await evaluate("document.querySelector('.health-test [role=alert]').textContent"), /nicht erreichbar/);
    assert.equal(await evaluate("document.querySelectorAll('.health-reading').length"), 0, 'Failed refresh must not display old values');
    fixture = { status: 200, body: { status: 'empty', message: 'Keine passenden Health-Connect-Sensoren gefunden.', checked_at, sensors: [] } };
    await refresh();
    assert.equal(await evaluate("document.querySelectorAll('.health-reading').length"), 0);
    assert.ok(await evaluate("document.querySelector('.health-test').textContent.includes('Sensoren verwalten')"));
    console.log(`PASS ${width}px: local status, readings, zero/unavailable, manual selection, safe errors and recovery, layout`);
  }
  nonAdmin = true;
  await send('Page.navigate', { url: frontend });
  await waitFor("document.body.innerText.includes('Kalendertest') && !document.querySelector('.loading-bar')");
  assert.equal(await evaluate("document.querySelector('[title=\"Test Health dashboard\"]')"), null);
  console.log('PASS non-admin: health test navigation hidden');
} finally {
  await send('Fetch.disable');
  socket.close();
}
