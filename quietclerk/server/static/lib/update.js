// Self-update: the shared state, the calls behind the buttons, and the three places that show it - the
// band every screen carries (mounted by the shell), the "what changed" dialog, and the settings card.
// Data: GET /api/update, POST /api/update/{check,apply,dismiss}, and the "update" summary that the
// /api/events snapshot carries, so the band follows the engine without polling.
// Whatever the API says is shown as text only (normalize): no markup, bounded length, and an unknown
// state or reason turns into "nothing to show" or a generic sentence, never into a wrong promise.
import {h, replace} from './dom.js';
import {L, onLang, plural} from './i18n.js';
import {get, post, openSession} from './api.js';
import {live, subscribe} from './live.js';
import {banner, btn, chip, code, announce, apiProblem} from './ui.js';
import {shortIso} from './fmt.js';

const STATES = ['unavailable', 'current', 'available', 'scheduled', 'updating', 'done', 'failed'];
// While an update swaps the engine the stream breaks on purpose; this long it is "restarting", not "lost".
const RESTART_GRACE_MS = 3 * 60 * 1000;
const FROM_KEY = 'qc.update.from';

// ---- what the API may say: text only, bounded, no control or bidirectional-override characters
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u2028\u2029\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;
const clip = (value, max) => (typeof value === 'string'
  ? Array.from(value.replace(CONTROL, ' ').replace(/\s+/g, ' ').trim()).slice(0, max).join('') : '');
const hash = (value) => (typeof value === 'string' && /^[0-9a-f]{4,40}$/i.test(value) ? value.slice(0, 12) : '');
const natural = (value, fallback) => (Number.isInteger(value) && value >= 0 ? value : fallback);

function normalize(body) {
  const b = body && typeof body === 'object' && !Array.isArray(body) ? body : {};
  const commit = (c) => ({commit: hash(c && c.commit), date: shortIso(c && c.date)});
  const changes = (Array.isArray(b.changes) ? b.changes : []).slice(0, 20)
    .filter((c) => c && typeof c === 'object')
    .map((c) => ({...commit(c), title: clip(c.title, 200)}))
    .filter((c) => c.title);
  return {
    state: STATES.includes(b.state) ? b.state : 'unavailable',
    reason: clip(b.reason, 40) || null,
    installed: commit(b.installed), latest: b.latest && typeof b.latest === 'object' ? commit(b.latest) : null,
    behind: natural(b.behind, changes.length), changes,
    checkedAt: shortIso(b.checked_at), lastError: clip(b.last_error, 300) || null,
  };
}

// ---- sentences
const GENERIC = () => L('지금은 업데이트할 수 없어요', 'Updates aren\'t available right now');
const REASON = {
  local_changes: () => L('설치 폴더에 직접 고친 파일이 있어 자동 업데이트를 멈췄어요', 'Automatic updates are paused because a file in the install folder was edited by hand'),
  wheel_install: () => L('이 설치 방식은 화면에서 업데이트할 수 없어요', 'This kind of install can\'t be updated from the screen'),
  no_checkout: () => L('설치 폴더에서 버전 기록(git)을 찾지 못해 화면에서 업데이트할 수 없어요', 'The install folder has no version history (git), so it can\'t be updated from the screen'),
  diverged: () => L('이 설치본에 공식 버전과 다른 변경이 있어 자동 업데이트를 멈췄어요', 'This install differs from the official version, so automatic updates are paused'),
  no_remote: () => L('새 버전을 확인할 GitHub 주소가 정해져 있지 않아요', 'No GitHub address is set to check for new versions'),
  offline: () => L('인터넷에 연결되지 않아 새 버전을 확인하지 못했어요', 'Couldn\'t check for a new version: no connection to GitHub'),
  check_disabled: () => L('하루 한 번 확인이 꺼져 있어요. 지금 확인으로 직접 확인할 수 있어요', 'The daily check is off. Use Check now to look yourself'),
  job_running: () => L('처리 중인 녹음이 있어서 끝나면 업데이트해요', 'A recording is being processed, so the update waits until it is done'),
};
const reasonText = (reason) => (REASON[reason] ? REASON[reason]() : null);

// One description of an update body for every place that shows it: banner colour and glyph, the status
// chip, the words, and which actions make sense. `band` says whether every screen carries it.
function describe(info) {
  const from = store.from;
  const hashes = [from && from !== info.installed.commit ? from : '', info.installed.commit].filter(Boolean);
  switch (info.state) {
    case 'available':
      return {kind: 'info', glyph: '↑', band: true, chip: ['run', '↑', L('새 버전 있음', 'Update available')],
        title: L('새 버전이 있어요', 'A new version is available'),
        suffix: info.behind ? L(`변경 ${info.behind}개`, plural(info.behind, 'change')) : null, actions: ['apply', 'changes']};
    case 'scheduled':
      return {kind: 'info', glyph: '◷', band: true, chip: ['idle', '◷', L('기다리는 중', 'Waiting')],
        title: L('처리 중인 녹음이 끝나면 업데이트해요', 'The update starts when the recording being processed is done'),
        detail: L('끝나면 저절로 시작하고, 그때 화면이 잠시 끊길 수 있어요.', 'It starts by itself, and the screen may drop for a moment.'), actions: ['changes']};
    case 'updating':
      return {kind: 'info', glyph: '↻', band: true, chip: ['run', '●', L('업데이트 중', 'Updating')],
        title: L('업데이트 중…', 'Updating…'),
        detail: L('잠시 화면이 끊겨도 괜찮아요. 다시 연결되면 결과를 알려 드려요.', 'It\'s fine if the screen drops for a moment. I\'ll show the result once it reconnects.'), actions: []};
    case 'done':
      return {kind: 'ok', glyph: '✓', band: true, chip: ['ok', '✓', L('완료', 'Done')],
        title: L('업데이트했어요', 'Updated'), hashes, actions: ['dismiss']};
    case 'failed':
      return {kind: 'err', glyph: '!', band: true, chip: ['err', '!', L('실패', 'Failed')],
        title: L('업데이트하지 못해 이전 버전으로 되돌렸어요', 'Couldn\'t update, so I went back to the previous version'),
        detail: info.lastError || reasonText(info.reason), actions: ['dismiss']};
    case 'current':
      return {kind: 'info', glyph: '✓', band: false, chip: ['ok', '✓', L('최신', 'Up to date')],
        title: L('최신 버전이에요', 'You\'re on the latest version'), actions: []};
    default: {
      // A git checkout nobody has asked about yet reads as "no_checkout" until the first check has run.
      const unchecked = !info.checkedAt && !!info.installed.commit && (!info.reason || info.reason === 'no_checkout');
      return unchecked
        ? {kind: 'info', glyph: '?', band: false, chip: ['idle', '?', L('확인 전', 'Not checked')],
          title: L('아직 새 버전을 확인하지 않았어요', 'Haven\'t checked for a new version yet'), actions: []}
        : {kind: 'info', glyph: '—', band: false, chip: ['idle', '—', L('쓸 수 없음', 'Unavailable')],
          title: reasonText(info.reason) || GENERIC(), actions: []};
    }
  }
}
const line = (v) => [v.title, v.suffix ? ` · ${v.suffix}` : '', v.hashes && v.hashes.length ? ` (${v.hashes.join(' → ')})` : ''].join('');

// Why Check now is off while a run or a result is pending (a check could change neither).
const checkBlock = (info) => (info.state === 'scheduled' || info.state === 'updating'
  ? L('업데이트가 진행 중이에요', 'An update is in progress')
  : info.state === 'done' || info.state === 'failed' ? L('위 결과를 먼저 확인해 주세요', 'Please confirm the result first') : null);

// ---- shared state
const recall = () => {
  try { return hash(sessionStorage.getItem(FROM_KEY)); } catch (_) { return ''; }
};
const store = {
  info: null,         // normalized last answer of GET /api/update (null until the first one)
  busy: null,         // 'check' | 'apply' | 'dismiss' while that request is in flight
  error: null,        // {text, code} of the last request that failed, shown beside the buttons
  from: recall(),     // the commit installed before this update (for "abc1234 → def5678")
  downSince: 0,       // Date.now() when the stream broke during an update; 0 while it is up
  wasFailed: false, seen: '', grace: null,
};
const listeners = new Set();
const notify = () => { for (const fn of [...listeners]) fn(); };
export const subscribeUpdate = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

function remember(commit) {
  store.from = commit;
  try { sessionStorage.setItem(FROM_KEY, commit); } catch (_) { /* storage off: the arrow then shows one commit */ }
}
function forget() {
  store.from = '';
  try { sessionStorage.removeItem(FROM_KEY); } catch (_) { /* nothing was stored */ }
}

// The stream is broken because an update is swapping the engine, not because the engine is gone.
export function restarting() {
  return live.failed && !live.authLost && !!store.info && store.info.state === 'updating'
    && store.downSince > 0 && Date.now() - store.downSince < RESTART_GRACE_MS;
}

function accept(body) {
  const info = normalize(body);
  const before = store.info;
  store.info = info;
  // Until the update is done the installed commit is still the old one: keep it for "old → new".
  if ((info.state === 'scheduled' || info.state === 'updating') && info.installed.commit) remember(info.installed.commit);
  if (before && before.state !== info.state) {
    store.error = null;
    const v = describe(info);
    if (v.band) announce(line(v));
  }
  notify();
}

let inflight = null, stale = false;
async function load() {
  do {
    stale = false;
    try {
      accept(await get('/api/update'));
    } catch (_) { /* an engine that cannot be reached has its own banner; keep what we know */ }
  } while (stale);
}
function refreshUpdate() {
  if (inflight) {
    stale = true;
    return inflight;
  }
  inflight = load().finally(() => { inflight = null; });
  return inflight;
}

function onLive() {
  const failed = live.failed;
  if (failed && !store.wasFailed && store.info && store.info.state === 'updating') {
    store.downSince = Date.now();
    clearTimeout(store.grace);
    store.grace = setTimeout(notify, RESTART_GRACE_MS + 100);   // then the offline banner takes over
  }
  const reconnected = store.wasFailed && !failed;
  store.wasFailed = failed;
  if (reconnected) {
    // Back from a restart: the session may carry a new CSRF token, and the result waits in /api/update.
    store.downSince = 0;
    store.seen = '';
    clearTimeout(store.grace);
    openSession().catch(() => null).then(refreshUpdate);
  } else if (!failed && !live.authLost) {
    const sum = live.snapshot && live.snapshot.update;
    const key = sum && typeof sum === 'object' ? `${sum.state}:${sum.behind}` : '';
    if (key && key !== store.seen) {
      store.seen = key;
      if (!store.info || store.info.state !== sum.state || store.info.behind !== sum.behind) refreshUpdate();
    }
  }
  notify();
}

let started = false;
function start() {
  if (started) return;
  started = true;
  subscribe(onLive);
  onLang(notify);
  refreshUpdate();
}

// ---- actions: one at a time, so a second click (or a held key) while one runs does nothing
function failure(error) {
  if (error.status === 409) {
    const reason = error.body && typeof error.body.reason === 'string' ? clip(error.body.reason, 40) : '';
    return {text: reasonText(reason) || GENERIC(), code: `409${reason ? ` {reason: ${reason}}` : ''}`};
  }
  const problem = apiProblem(error);
  return {text: problem.what, code: problem.code};
}

async function act(name, request, succeeded) {
  if (store.busy) return false;
  store.busy = name;
  store.error = null;
  notify();
  try {
    succeeded(await request());
    return true;
  } catch (error) {
    store.error = failure(error);
    announce(store.error.text);
    if (error.status === 409) refreshUpdate();   // the state moved under us: show what it is now
    return false;
  } finally {
    store.busy = null;
    notify();
  }
}

const checkNow = () => act('check', () => post('/api/update/check'), accept);

function applyNow() {
  const from = store.info && store.info.installed.commit;
  return act('apply', () => post('/api/update/apply'), (body) => {
    const accepted = body && (body.state === 'scheduled' || body.state === 'updating') ? body.state : null;
    if (from) remember(from);
    if (accepted && store.info) {
      store.info = {...store.info, state: accepted, reason: accepted === 'scheduled' ? 'job_running' : null};
      announce(line(describe(store.info)));
    }
    refreshUpdate();
  });
}

const dismissResult = () => act('dismiss', () => post('/api/update/dismiss'), (body) => {
  forget();
  accept(body);
});

// ---- views. A view re-draws only when its model (plain data) changed, so a stream snapshot every few
// seconds neither flickers nor makes a screen reader read the same banner again, and the keyboard focus stays.
function restoreFocus(host, action) {
  const buttons = Array.from(host.querySelectorAll('button'));
  const next = buttons.find((b) => b.dataset.act === action && !b.disabled) || host.querySelector('[tabindex="-1"]')
    || buttons.find((b) => !b.disabled) || document.getElementById('main');
  if (next) next.focus();
}

function follow(host, model, paint) {
  let shown = null;
  const draw = () => {
    if (shown !== null && !host.isConnected) {   // its screen was drawn again: let go
      listeners.delete(draw);
      return;
    }
    const m = model();
    const key = JSON.stringify(m);
    if (key === shown) return;
    shown = key;
    const focused = host.contains(document.activeElement) ? document.activeElement : null;
    replace(host, paint(m));
    if (focused) restoreFocus(host, focused.dataset.act);
  };
  listeners.add(draw);
  draw();
  return host;
}

const hashesNode = (list) => (list && list.length
  ? [' (', list.map((value, index) => [index ? ' → ' : '', h('code', null, value)]), ')'] : null);
const problemLine = (error) => (error ? h('div', {class: 'small err-text'}, error.text, ' ', code(error.code)) : null);
const versionNode = (c) => (c && c.commit ? [h('code', null, c.commit), c.date ? ` · ${c.date}` : null] : '—');

function actionButton(id, m) {
  const off = !!m.busy || !!m.offline;
  if (id === 'apply') {
    return btn({small: true, kind: 'primary', act: 'apply', disabled: off,
      label: m.busy === 'apply' ? L('시작하는 중…', 'Starting…') : L('업데이트', 'Update'), on: {click: applyNow}});
  }
  if (id === 'changes') {
    return btn({small: true, act: 'changes', label: L('변경 내용', 'What\'s new'), on: {click: (event) => openChanges(event.currentTarget)}});
  }
  return btn({small: true, act: 'dismiss', disabled: off, label: m.busy === 'dismiss' ? L('닫는 중…', 'Closing…') : L('확인', 'OK'), on: {click: dismissResult}});
}

// ---- the band at the top of every screen (the shell gives it a place and calls this once)
function bandModel() {
  const info = store.info;
  if (!info || live.authLost) return null;
  const restart = restarting();
  if (live.failed && !restart) return null;   // the engine banner says it; there is nothing to ask of a missing engine
  const v = describe(restart ? {...info, state: 'updating'} : info);
  return v.band ? {...v, state: restart ? 'updating' : info.state, busy: store.busy, offline: live.failed, error: store.error} : null;
}

function paintBand(m) {
  if (!m) return null;
  const node = banner(m.kind, m.glyph, [
    h('b', null, m.title), m.suffix ? ` · ${m.suffix}` : null, hashesNode(m.hashes),
    m.detail ? h('div', {class: 'small'}, m.detail) : null,
    m.state === 'updating' ? h('div', {class: 'meter busy', role: 'progressbar', 'aria-label': m.title}, h('i')) : null,
    problemLine(m.error),
  ], m.actions.map((id) => actionButton(id, m)));
  node.setAttribute('data-update', m.state);
  node.setAttribute('tabindex', '-1');   // where the focus goes when the button that had it is gone
  return node;
}

export function mountUpdateBand(host) {
  start();
  follow(host, bandModel, paintBand);
}

// ---- the "what changed" dialog (native <dialog>: Esc closes, focus is kept inside and handed back)
let dialog = null;

function dialogModel() {
  const info = store.info;
  return info
    ? {v: describe(info), installed: info.installed, latest: info.latest, checkedAt: info.checkedAt, changes: info.changes,
      behind: info.behind, busy: store.busy, offline: live.failed, error: store.error}
    : {v: null, busy: store.busy, offline: live.failed, error: store.error};
}

function paintDialog(m, close) {
  const facts = m.v ? [
    [L('설치된 버전', 'Installed'), versionNode(m.installed)],
    m.latest && m.latest.commit ? [L('최신 버전', 'Latest'), versionNode(m.latest)] : null,
    [L('마지막 확인', 'Last checked'), m.checkedAt || L('아직 안 했어요', 'Not yet')],
  ].filter(Boolean) : [];
  const list = !m.v ? null : m.changes.length
    ? [h('ul', {class: 'list'}, m.changes.map((c) => h('li', {class: 'item full'},
      h('span', {class: 't wrapany'}, c.title),
      h('div', {class: 'meta'}, c.date ? h('span', null, c.date) : null, c.commit ? h('code', {class: 'code-tag'}, c.commit) : null)))),
    m.behind > m.changes.length
      ? h('p', {class: 'small muted'}, L(`가장 최근 ${m.changes.length}개만 보여요 (전체 ${m.behind}개)`, `Showing the latest ${m.changes.length} of ${m.behind}`)) : null]
    : h('p', {class: 'small muted'}, L('보여 줄 변경 내용이 없어요.', 'No changes to show.'));
  const canApply = !!m.v && m.v.actions.includes('apply');
  return [
    h('div', {class: 'dlg-head'}, h('h2', {id: 'upd-h'}, L('변경 내용', 'What\'s new'))),
    h('div', {class: 'dlg-scroll'},
      m.v ? h('p', {class: 'row'}, chip(...m.v.chip), h('b', {class: 'ink'}, line(m.v))) : null,
      m.v && m.v.detail ? h('p', {class: 'small'}, m.v.detail) : null,
      facts.length ? h('dl', {class: 'kv'}, facts.flatMap(([key, value]) => [h('dt', null, key), h('dd', null, value)])) : null,
      list,
      canApply ? h('p', {class: 'small muted'}, L('업데이트하면 화면이 잠시 끊겨요. 처리 중인 녹음이 있으면 끝난 뒤에 시작해요.',
        'The screen drops for a moment while it updates. If a recording is being processed, it starts after that.')) : null,
      problemLine(m.error)),
    h('div', {class: 'dlg-foot'},
      btn({small: true, act: 'close', label: L('닫기', 'Close'), on: {click: close}}),
      canApply ? btn({small: true, kind: 'primary', act: 'apply', disabled: !!m.busy || m.offline,
        label: m.busy === 'apply' ? L('시작하는 중…', 'Starting…') : L('지금 업데이트', 'Update now'),
        on: {click: async () => { if (await applyNow()) close(); }}}) : null),
  ];
}

function openChanges(opener) {
  if (dialog) return;
  const el = h('dialog', {class: 'dlg', 'aria-labelledby': 'upd-h'});
  dialog = el;
  let closed = false;
  const finish = () => {
    if (closed) return;
    closed = true;
    dialog = null;
    el.remove();
    const back = opener && opener.isConnected ? opener : document.querySelector('[data-act="changes"]') || document.getElementById('main');
    if (back) back.focus();
  };
  const close = () => { if (el.open) el.close(); else finish(); };
  el.addEventListener('close', finish);
  el.addEventListener('click', (event) => { if (event.target === el) close(); });   // the backdrop
  document.body.append(el);
  follow(el, dialogModel, (m) => paintDialog(m, close));
  if (typeof el.showModal === 'function') el.showModal();
  else el.setAttribute('open', '');
  const first = el.querySelector('[data-act="close"]');
  if (first) first.focus();
}

// ---- the settings card: the Check now button with the answer in words, and the installed version
export function updateCheckControl(id) {
  const controls = follow(h('div', {class: 'stack tight'}), () => {
    const info = store.info;
    return {v: info ? describe(info) : null, blocked: info ? checkBlock(info) : null, busy: store.busy, offline: live.failed};
  }, (m) => [
    h('div', {class: 'actions'},
      btn({small: true, act: 'check', disabled: !!m.busy || m.offline || !!m.blocked,
        label: m.busy === 'check' ? L('확인 중…', 'Checking…') : L('지금 확인', 'Check now'), on: {click: checkNow}}),
      m.v ? m.v.actions.map((action) => actionButton(action, m)) : null),
    m.blocked ? h('span', {class: 'why'}, m.blocked) : null,
  ]);
  // The sentence sits in one live region that is never rebuilt, so a screen reader hears each change.
  const answer = follow(h('div', {class: 'small row', role: 'status', 'aria-live': 'polite'}), () => {
    const info = store.info;
    return {v: info ? describe(info) : null, checkedAt: info ? info.checkedAt : '', checking: store.busy === 'check', error: store.error};
  }, (m) => (m.checking ? h('span', {class: 'muted'}, L('확인 중…', 'Checking…'))
    : [m.v ? chip(...m.v.chip) : chip('idle', '?', L('확인 못 함', 'Unknown')),
      h('span', null, m.v ? line(m.v) : L('아직 상태를 받지 못했어요', 'No status yet')),
      m.checkedAt ? h('span', {class: 'muted'}, L(`${m.checkedAt} 확인`, `checked ${m.checkedAt}`)) : null,
      m.v && m.v.detail ? h('span', {class: 'muted'}, m.v.detail) : null,
      problemLine(m.error)]));
  return h('div', {class: 'stack', id}, controls, answer);
}

export function updateVersions(id) {
  return follow(h('dl', {class: 'kv', id}), () => {
    const info = store.info;
    return {installed: info ? info.installed : null, latest: info && info.state === 'available' ? info.latest : null};
  }, (m) => [h('dt', null, L('설치된 버전', 'Installed')), h('dd', null, versionNode(m.installed)),
    m.latest && m.latest.commit ? [h('dt', null, L('새 버전', 'New')), h('dd', null, versionNode(m.latest))] : null]);
}
