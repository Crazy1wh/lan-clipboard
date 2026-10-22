const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'static', 'index.html'), 'utf8');
const inlineScript = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].at(-1)[1];

class FakeClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach(name => this.values.add(name)); }
  remove(...names) { names.forEach(name => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : force;
    enabled ? this.values.add(name) : this.values.delete(name);
    return enabled;
  }
}

class FakeElement {
  constructor() {
    this.style = {};
    this.classList = new FakeClassList();
    this.listeners = {};
    this.children = [];
    this.dataset = {};
    this.textContent = '';
    this.innerHTML = '';
    this.value = '';
  }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); }
  removeChild(child) { this.children = this.children.filter(x => x !== child); }
  remove() {}
  querySelector() { return null; }
  getBoundingClientRect() { return {bottom: 0, left: 0}; }
}

function createRuntime(XHR = class {}) {
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, new FakeElement());
    return elements.get(selector);
  };
  const documentListeners = {};
  const body = new FakeElement();
  const document = {
    body,
    addEventListener(name, handler) {
      (documentListeners[name] ||= []).push(handler);
    },
    querySelector: element,
    querySelectorAll() { return []; },
    createElement() { return new FakeElement(); },
    execCommand() { return true; },
  };
  const context = {
    console,
    document,
    window: {isSecureContext: false, innerWidth: 800, scrollX: 0, scrollY: 0},
    navigator: {userAgent: 'Node test'},
    location: {origin: 'http://test'},
    URL,
    URLSearchParams,
    XMLHttpRequest: XHR,
    FormData: class {
      constructor() { this.parts = []; }
      append(...part) { this.parts.push(part); }
    },
    fetch: async () => ({ok: true, status: 200, json: async () => ({disk_used: 0, disk_limit: 1})}),
    setTimeout,
    clearTimeout,
    setInterval() { return 1; },
    isFinite,
    confirm() { return true; },
    prompt() { return null; },
  };
  vm.createContext(context);
  vm.runInContext(inlineScript, context, {filename: 'static/index.html'});
  return {context, element, documentListeners};
}

function file(name, type = 'application/octet-stream', size = 10, lastModified = 1) {
  return {name, type, size, lastModified};
}

function pasteEvent(clipboardData) {
  return {
    clipboardData,
    prevented: false,
    preventDefault() { this.prevented = true; },
  };
}

async function until(check) {
  for (let i = 0; i < 50; i++) {
    if (check()) return;
    await new Promise(resolve => setImmediate(resolve));
  }
  throw new Error('condition was not reached');
}

test('picker is a real transparent overlay inside a native label', () => {
  assert.match(html, /\.dropzone\s+input\[type=file\]\s*\{[^}]*position:\s*absolute[^}]*inset:\s*0[^}]*opacity:\s*0/s);
  assert.doesNotMatch(html, /\.dropzone\s+input\[type=file\]\s*\{[^}]*display:\s*none/s);
  assert.match(html, /<label class="dropzone" id="dzFile">[\s\S]*?<input type="file" id="fileFile" multiple>[\s\S]*?<\/label>/);
  assert.doesNotMatch(inlineScript, /\.click\(\)[\s\S]{0,100}(?:fileImage|fileFile)/);
});

test('change handler snapshots a live FileList before clearing input', () => {
  const {context, element} = createRuntime();
  const chosen = [file('mobile.txt')];
  const input = element('#fileFile');
  let currentFiles = chosen;
  Object.defineProperty(input, 'files', {get: () => currentFiles});
  Object.defineProperty(input, 'value', {
    get: () => '',
    set: value => { if (value === '') currentFiles = []; },
  });
  let uploaded = null;
  context.uploadFiles = files => { uploaded = files; };
  context.bindDropzone('#dzFile', '#fileFile');
  input.listeners.change();
  assert.deepEqual(Array.from(uploaded), chosen);
  assert.equal(currentFiles.length, 0);
});

test('paste handles general files, image fallback, multiple files, and deduplicates sources', () => {
  const {context, documentListeners} = createRuntime();
  const onPaste = documentListeners.paste[0];
  let uploaded = null;
  context.uploadFiles = files => { uploaded = Array.from(files); };

  const pdf = file('report.pdf', 'application/pdf', 42, 9);
  const general = pasteEvent({files: [pdf], items: []});
  onPaste(general);
  assert.equal(general.prevented, true);
  assert.deepEqual(uploaded, [pdf]);

  const image = file('pasted.png', 'image/png', 24, 10);
  uploaded = null;
  const fallback = pasteEvent({files: [], items: [{kind: 'file', getAsFile: () => image}]});
  onPaste(fallback);
  assert.equal(fallback.prevented, true);
  assert.deepEqual(uploaded, [image]);

  const other = file('notes.txt', 'text/plain', 5, 11);
  uploaded = null;
  const multiple = pasteEvent({
    files: [pdf, other],
    items: [
      {kind: 'file', getAsFile: () => ({...pdf})},
      {kind: 'file', getAsFile: () => other},
    ],
  });
  onPaste(multiple);
  assert.equal(multiple.prevented, true);
  assert.deepEqual(uploaded, [pdf, other]);
});

test('plain-text paste remains browser-native', () => {
  const {context, documentListeners} = createRuntime();
  let uploadCalls = 0;
  context.uploadFiles = () => { uploadCalls++; };
  const event = pasteEvent({
    files: [],
    items: [{kind: 'string', type: 'text/plain', getAsFile: () => null}],
  });
  documentListeners.paste[0](event);
  assert.equal(event.prevented, false);
  assert.equal(uploadCalls, 0);
});

test('single upload immediately shows filename and preparing state, then cleans up network errors', async () => {
  class ManualXHR {
    static instances = [];
    constructor() {
      this.upload = {};
      ManualXHR.instances.push(this);
    }
    open() {}
    send() {}
  }
  const {context, element} = createRuntime(ManualXHR);
  const pending = context.uploadFiles([file('single.bin')]);
  assert.equal(element('#uploadBar').style.display, 'block');
  assert.match(element('#ubInfo').textContent, /single\.bin.*准备上传/);
  const xhr = ManualXHR.instances[0];
  const onerror = xhr.onerror;
  onerror();
  const result = await pending;
  assert.deepEqual(JSON.parse(JSON.stringify(result)), {okCount: 0, total: 1});
  assert.equal(element('#uploadBar').style.display, 'none');
  assert.match(element('#toast').textContent, /失败.*网络错误/);
  assert.equal(xhr.onerror, null);
  assert.equal(xhr.onabort, null);
  assert.equal(xhr.upload.onprogress, null);
});

test('aborted and synchronous upload failures are visible and leave the queue usable', async () => {
  class ThrowingXHR {
    constructor() { this.upload = {}; }
    open() {}
    send() { throw new Error('send exploded'); }
  }
  const first = createRuntime(ThrowingXHR);
  await first.context.uploadFiles([file('sync.bin')]);
  assert.match(first.element('#toast').textContent, /失败.*send exploded/);
  assert.equal(first.element('#uploadBar').style.display, 'none');

  class AbortXHR {
    static instances = [];
    constructor() { this.upload = {}; AbortXHR.instances.push(this); }
    open() {}
    send() {}
  }
  const second = createRuntime(AbortXHR);
  const pending = second.context.uploadFiles([file('abort.bin')]);
  const onabort = AbortXHR.instances[0].onabort;
  onabort();
  await pending;
  assert.match(second.element('#toast').textContent, /失败.*已中止/);
  assert.equal(second.element('#uploadBar').style.display, 'none');
});

test('overlapping upload requests are serialized and cannot overwrite active progress', async () => {
  class ManualXHR {
    static instances = [];
    constructor() {
      this.upload = {};
      this.status = 503;
      this.responseText = '{"ok":false,"error":"test failure"}';
      ManualXHR.instances.push(this);
    }
    open() {}
    send() {}
  }
  const {context, element} = createRuntime(ManualXHR);
  const first = context.uploadFiles([file('first.bin')]);
  const second = context.uploadFiles([file('second.bin')]);
  assert.equal(ManualXHR.instances.length, 1);
  assert.match(element('#ubInfo').textContent, /first\.bin/);

  const firstLoad = ManualXHR.instances[0].onload;
  firstLoad();
  await until(() => ManualXHR.instances.length === 2);
  assert.match(element('#ubInfo').textContent, /second\.bin/);
  const secondLoad = ManualXHR.instances[1].onload;
  secondLoad();
  await Promise.all([first, second]);
  assert.equal(element('#uploadBar').style.display, 'none');
});

test('version area labels commit/build dates and only marks behind as an update', async () => {
  const {context, element} = createRuntime();
  context.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      branch: 'main',
      short_sha: 'abc1234',
      commit_date: '2026-10-20T01:02:03Z',
      build_time: '2026-10-21T04:05:06Z',
      upstream_url: 'https://github.com/Crazy1wh/lan-clipboard/tree/main',
      update: {status: 'available', available: true, behind_by: 2},
    }),
  });
  await context.refreshVersion();
  assert.match(element('#versionBuild').textContent, /分支 main.*提交 abc1234.*提交日期.*构建日期/);
  assert.match(element('#versionUpdate').textContent, /上游有更新.*2 个提交/);
  assert.equal(element('#versionUpdate').className, 'update-available');
});

test('unknown and failed update checks show a GitHub link without warnings', async () => {
  const {context, element} = createRuntime();
  context.fetch = async () => ({ok: true, json: async () => ({
    repository_url: 'https://github.com/Crazy1wh/lan-clipboard',
    update: {status: 'unknown'},
  })});
  await context.refreshVersion();
  assert.equal(element('#versionUpdate').textContent, 'GitHub');
  assert.equal(element('#versionUpdate').href, 'https://github.com/Crazy1wh/lan-clipboard');
  context.fetch = async () => { throw new Error('offline'); };
  await context.refreshVersion();
  assert.equal(element('#versionUpdate').textContent, 'GitHub');
  assert.equal(element('#versionUpdate').className, '');
});
