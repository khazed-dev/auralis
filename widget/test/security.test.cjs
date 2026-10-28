const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const acorn = require('acorn');

const source = fs.readFileSync(path.join(__dirname, '../src/chatbot.js'), 'utf8');
const ast = acorn.parse(source, { ecmaVersion: 'latest' });
const functions = new Map();
let configInitializer, initialMarkup;
function walk(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'FunctionDeclaration') functions.set(node.id.name, source.slice(node.start, node.end));
  if (node.type === 'Property' && node.method && node.key.name === 'addAgentMessage') {
    functions.set('addAgentMessage', 'function ' + source.slice(node.key.start, node.end));
  }
  if (node.type === 'VariableDeclarator' && node.id.name === 'config') configInitializer = source.slice(node.init.start, node.init.end);
  if (node.type === 'AssignmentExpression' && node.left.object?.name === 'widgetRoot' && node.left.property?.value === 'innerHTML') initialMarkup = source.slice(node.right.start, node.right.end);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === 'object') walk(value);
  }
}
walk(ast);

// Inert DOM double: records HTML sinks without executing scripts or making requests.
function setup() {
  const elements = [];
  class Element {
    constructor(tag) { this.tag = tag; this.style = {}; this.dataset = {}; this.children = []; this._html = ''; this._text = ''; elements.push(this); }
    set innerHTML(value) { this._html = String(value); this._text = ''; this.children = []; }
    get innerHTML() { return this._html + this.children.map(child => child.innerHTML).join(''); }
    set textContent(value) { this._text = String(value); this.children = []; this._html = this._text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }
    get textContent() { return this._text; }
    appendChild(child) { this.children.push(child); return child; }
    removeAttribute(key) { delete this[key]; }
    replaceChildren(...children) { this.children = children; this._html = ''; }
    querySelector() { return this.anchor; }
  }
  const footer = new Element('div'); footer.anchor = new Element('a');
  const context = {
    URL, window: { location: { href: 'https://shop.example.test/products', origin: 'https://shop.example.test', protocol: 'https:' } },
    document: { createElement: tag => new Element(tag), querySelector: () => footer,
      getElementById: () => null, head: new Element('head') },
    config: { apiUrl: 'https://api.example.test', primaryColor: '#3366cc', showSources: true, quickPrompts: { showAfterResponse: false }, hideBranding: false },
    messagesEl: new Element('div'), lastMessageIndex: 0, persistMessage: () => {}, fillQuickPrompts: () => {},
    scriptEl: { dataset: {} }, embedFallback: null,
  };
  vm.createContext(context);
  const names = ['safeHttpUrl', 'safeHexColor', 'normalizeApiBase', 'defaultEmbedApiUrl', 'escapeHtml', 'markdownToHtml', 'appendSources', 'appendMessage', 'setBotAvatar', 'updateBrandingFooter', 'addAgentMessage', 'restoreChatHistory', 'fetchSiteConfig', 'injectDynamicThemeStyles', 'adjustHexColor'];
  vm.runInContext(names.filter(name => functions.has(name)).map(name => functions.get(name)).join('\n'), context);
  return { context, elements, footer };
}
const payload = '<img src=x onerror="alert(1)">';

test('visitor and model content stay text while supported markdown still works', () => {
  for (const role of ['user', 'bot']) {
    const { context, elements } = setup();
    context.appendMessage(payload, role, [], { persist: false });
    const message = elements.find(element => element.className === 'sitechat-message ' + role);
    assert.ok(!message.innerHTML.includes('<img'), role + ' contains executable markup');
    assert.ok(message.innerHTML.includes('&lt;img'));
  }
  const { context } = setup();
  assert.equal(context.markdownToHtml('**Useful** `code`'), '<p><strong>Useful</strong> <code>code</code></p>');
  assert.match(context.markdownToHtml('- First\n- Second'), /^<ul><li>First<\/li><li>Second<\/li><\/ul>$/);
  assert.ok(!context.markdownToHtml('`' + payload + '`').includes('<img'));
});

test('citations preserve safe links and never interpolate title/URL attributes', () => {
  const { context, elements } = setup();
  context.appendMessage('Answer', 'bot', [
    { url: 'javascript:alert(1)', title: payload },
    { url: 'https://example.test/" onmouseover="alert(1)', title: payload },
    { url: '/help', title: 'Help & guidance' },
  ], { persist: false });
  assert.ok(!elements.some(element => /<img|onmouseover="alert/.test(element._html)));
  const links = elements.filter(element => element.className === 'sitechat-source-link');
  assert.equal(links.length, 2);
  assert.equal(links[0].textContent, payload);
  assert.match(links[0].href, /^https:\/\/example.test\//);
  assert.equal(links[1].href, 'https://shop.example.test/help');
  assert.equal(links[1].rel, 'noopener noreferrer');
});

test('branding and agent names are plain text; invalid branding links are inert', () => {
  const { context, elements, footer } = setup();
  Object.assign(context.config, { hideBranding: true, customBrandingText: payload, customBrandingUrl: 'javascript:alert(1)' });
  context.updateBrandingFooter();
  assert.equal(footer.anchor.textContent, payload);
  assert.equal(footer.anchor.href, undefined);
  context.addAgentMessage(payload, payload);
  assert.ok(!elements.some(element => element._html.includes('<img')));
});

test('URL, color and API bootstrap guards reject active protocols and CSS injection', () => {
  const { context, elements } = setup();
  for (const value of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\nscript:alert(1)', 'data:text/html,x', 'vbscript:x', 'https://user:pass@example.test/']) {
    assert.equal(context.safeHttpUrl(value), null, value);
  }
  assert.equal(context.safeHttpUrl('/avatar.png'), 'https://shop.example.test/avatar.png');
  assert.equal(context.safeHexColor('#aBc'), '#aaBBcc'.toLowerCase());
  assert.equal(context.safeHexColor('#ffffff); } body { display:none } /*'), '#3366cc');
  assert.equal(context.normalizeApiBase('https://api.example.test/prefix/'), 'https://api.example.test/prefix');
  assert.equal(context.normalizeApiBase('https://api.example.test/?token=x'), null);
  context.config.botAvatarUrl = 'javascript:alert(1)';
  context.setBotAvatar(context.messagesEl);
  assert.ok(!elements.some(element => element.tag === 'img'));
  context.scriptEl.dataset = { apiUrl: 'javascript:alert(1)', primaryColor: '#fff;body{display:none}', title: payload };
  context.datasetApi = context.scriptEl.dataset.apiUrl; context.embedApi = '';
  vm.runInContext('globalThis.bootstrap = ' + configInitializer, context);
  assert.equal(context.bootstrap.apiUrl, 'https://shop.example.test');
  assert.equal(context.bootstrap.primaryColor, '#3366cc');
  context.config = context.bootstrap;
  vm.runInContext('globalThis.html = ' + initialMarkup, context);
  assert.ok(!context.html.includes(payload));
});

test('restored history uses the safe renderer and remains isolated by session', () => {
  const stored = { sessionId: 'session-1', expiresAt: Date.now() + 60000, messages: [
    { role: 'user', content: payload }, { role: 'bot', content: payload, sources: [{ url: 'javascript:alert(1)', title: payload }] },
  ] };
  for (const sessionId of ['session-1', 'another-session']) {
    const { context, elements } = setup();
    Object.assign(context, { sessionId, historyStorageKey: 'history', welcomeRemoved: false,
      CHAT_HISTORY_LIMIT: 50, localStorage: { getItem: () => JSON.stringify(stored) } });
    context.restoreChatHistory();
    const messages = elements.filter(element => /^sitechat-message (user|bot)$/.test(element.className));
    assert.equal(messages.length, sessionId === 'session-1' ? 2 : 0);
    assert.ok(messages.every(element => !element.innerHTML.includes('<img')));
    assert.ok(!elements.some(element => element.href?.startsWith('javascript:')));
  }
});

test('remote appearance cannot inject CSS or active avatar URLs and preserves a valid custom accent', async () => {
  const { context, elements } = setup();
  context.config.primaryColor = '#123456';
  context.syncHeaderAndWelcomeText = () => {};
  context.syncQuickPrompts = () => {};
  context.fetch = async () => ({ ok: true, json: async () => ({ appearance: {
    primary_color: '#ffffff); } body { display:none } /*', bot_avatar_url: 'javascript:alert(1)',
  } }) });
  await context.fetchSiteConfig();
  assert.equal(context.config.primaryColor, '#123456');
  assert.equal(context.config.botAvatarUrl, null);
  const style = elements.find(element => element.tag === 'style');
  assert.ok(style.textContent.includes('#123456'));
  assert.ok(!style.textContent.includes('body { display:none'));
});
