/* eslint-disable @typescript-eslint/no-require-imports -- Node test harness transpiles the real TypeScript module to CommonJS. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../lib/plans.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020},
}).outputText;

function helpers(fetch) {
  const exports = {};
  vm.runInNewContext(compiled, {exports, fetch, require(name) {
    assert.equal(name, './auth');
    return {API_BASE: '/api'};
  }});
  return exports;
}

const plan = (overrides = {}) => ({
  key: 'scale', name: 'Quy mô mới', monthly_price: 7_350_000, vat_rate: 8,
  display_features: ['Hạn mức từ catalog'], limits: {}, display_order: 10,
  is_public: true, is_active: true, allow_new_signup: true, requires_contact: false,
  badge: 'Gói mới', cta_label: 'Chọn Quy mô mới', ...overrides,
});

test('catalog reads a changed admin price again without a browser cache or fixed plan keys', async () => {
  let price = 7_350_000;
  const requests = [];
  const api = helpers(async (url, options) => {
    requests.push({url, options});
    return {ok: true, json: async () => [plan({monthly_price: price})]};
  });
  const first = (await api.fetchPlanCatalog())[0];
  assert.equal(api.planPresentation(first).price, '7.350.000');
  price = 8_900_000;
  const second = (await api.fetchPlanCatalog())[0];
  const view = api.planPresentation(second);
  assert.equal(view.price, '8.900.000');
  assert.equal(view.href, '/checkout?plan=scale');
  assert.equal(view.title, 'Quy mô mới');
  assert.equal(view.badge, 'Gói mới');
  assert.equal(view.features[0], 'Hạn mức từ catalog');
  assert.equal(view.action, 'Chọn Quy mô mới');
  assert.equal(requests.length, 2);
  assert.ok(requests.every(item => item.url === '/api/plans/public' && item.options.cache === 'no-store'));
});

test('catalog hides archived/private plans and retains admin display ordering', async () => {
  const api = helpers(async () => ({ok: true, json: async () => [
    plan({key: 'last', display_order: 40}), plan({key: 'hidden', is_public: false}),
    plan({key: 'archived', is_active: false}), plan({key: 'first', display_order: 5}),
  ]}));
  assert.equal((await api.fetchPlanCatalog()).map(item => item.key).join(','), 'first,last');
});

test('free, contact-only and paused-signup plans have distinct prices and actions', () => {
  const api = helpers();
  assert.equal(api.planPresentation(plan({monthly_price: 0})).price, 'Miễn phí');
  assert.equal(api.planPresentation(plan({monthly_price: null})).price, 'Liên hệ');
  assert.equal(api.planPresentation(plan({monthly_price: null})).href, '/#contact');
  assert.equal(api.planPresentation(plan({requires_contact: true})).href, '/#contact');
  assert.equal(api.planPresentation(plan({allow_new_signup: false})).href, null);
});

test('API failure or invalid payload rejects instead of returning hardcoded prices', async () => {
  await assert.rejects(helpers(async () => ({ok: false})).fetchPlanCatalog(), /Không thể tải/);
  await assert.rejects(helpers(async () => ({ok: true, json: async () => ({})})).fetchPlanCatalog(), /không hợp lệ/);
  await assert.rejects(helpers(async () => ({ok: false})).fetchPlan('missing'), /không khả dụng/);
});

test('checkout plan fetch supports a dynamic key and forwards abort/no-store', async () => {
  const signal = new AbortController().signal;
  const api = helpers(async (url, options) => {
    assert.equal(url, '/api/plans/scale%2Fnew');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.signal, signal);
    return {ok: true, json: async () => plan()};
  });
  assert.equal((await api.fetchPlan('scale/new', signal)).monthly_price, 7_350_000);
});
