// Meeting search (contract §10.8 C): the box, the results grouped by meeting, and the ways in: the shell's button,
// `/` and ⌘K (Ctrl+K) on every screen. A screen with its own box (Notes) registers it; elsewhere the same box opens in a dialog.
// Data: GET /api/search?q=&limit=&offset= -> {items: [{job_id, title, date, kind, line_id, start, speaker, snippet: [{text, hit}]}], total}.
// Everything the API sends is put in the page as text (the hit parts in <mark>). The only things built from it are same-origin
// links: /notes/<job_id>, with #t<number> for a transcript line and #sum for the summary.
import {h, svg, replace} from './dom.js';
import {L, onLang} from './i18n.js';
import {get} from './api.js';
import {subscribe} from './live.js';
import {btn, chip, empty, banner, code, apiProblem} from './ui.js';
import {fullDate, stamp} from './fmt.js';

export const DELAY = 300;       // ms after the last keystroke before a request goes out
const PAGE = 20;
const OTHER = /\p{C}/u;
const CITE = /\[t\d+(?:\s*,\s*t\d+)*\]/g;
const LINE_ID = /^t[1-9]\d*$/;
const BULLET = /(^|\n)[ \t]*(?:#{1,6}|[-*+]|\d{1,2}\.)[ \t]+/g;   // a summary is Markdown: its headings and bullets are not part of what was said
const KINDS = ['line', 'title', 'summary'];
const plain = (text, kind) => { const t = text.replace(CITE, ''); return kind === 'summary' ? t.replace(BULLET, '$1') : t; };

// ---- what the API sent, made safe to show: one line, no control or invisible characters, bounded
const tidy = (text, max) => Array.from(String(text ?? '').replace(/[\r\n\t\u2028\u2029]+/g, ' ').replace(/\p{C}/gu, '')).slice(0, max).join('');

function clean(raw) {
  if (!raw || typeof raw !== 'object' || typeof raw.job_id !== 'string' || !raw.job_id) return null;
  const kind = KINDS.includes(raw.kind) ? raw.kind : 'line';
  const source = (Array.isArray(raw.snippet) ? raw.snippet : []).slice(0, 40).filter((part) => part && typeof part.text === 'string');
  const parts = source.map((part) => ({hit: part.hit === true, text: tidy(part.hit === true ? part.text : plain(part.text, kind), 400)})).filter((part) => part.text);
  // The engine starts a snippet 70 characters before the first hit, which may be in the middle of a word: show it from the next word, with an ellipsis.
  if (parts.length && !parts[0].hit && source[0].hit !== true && Array.from(source[0].text).length === 70) {
    const space = parts[0].text.search(/\s/);
    parts[0].text = '…' + (space >= 0 ? parts[0].text.slice(space).trimStart() : parts[0].text);
  }
  return {
    job_id: raw.job_id, title: tidy(raw.title, 200), date: typeof raw.date === 'string' ? raw.date : '', kind,
    line_id: kind === 'line' && typeof raw.line_id === 'string' && LINE_ID.test(raw.line_id) ? raw.line_id : null,
    start: typeof raw.start === 'number' && Number.isFinite(raw.start) && raw.start >= 0 ? raw.start : null,
    speaker: typeof raw.speaker === 'string' ? tidy(raw.speaker, 40) : '', snippet: parts,
  };
}

// Where a result leads. The minutes screen is /notes/<job_id>; a line is the anchor #t12 (the id the transcript
// uses), the summary card is #sum.
export function hitHref(item) {
  const base = `/notes/${encodeURIComponent(item.job_id)}`;
  if (item.kind === 'summary') return `${base}#sum`;
  return item.line_id ? `${base}#${item.line_id}` : base;
}

// The engine ignores spaces ('대출 연장' = '대출연장') and needs two characters of the rest: the same rule, so nothing it
// would refuse is sent.
function judge(q) {
  if (!q) return 'idle';
  if (OTHER.test(q)) return 'bad';
  if (Array.from(q.replace(/\s+/g, '')).length < 2) return 'short';
  return Array.from(q).length > 100 ? 'long' : 'ok';
}

const searchIcon = () => svg('svg', {width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2,
  'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'}, svg('circle', {cx: 11, cy: 11, r: 7}), svg('path', {d: 'm20 20-3.5-3.5'}));

// ---- the box. `sync` puts engine-offline state on the controls it draws (the shell's syncEngineControls); `onCommit(query)`
// hears the query each time it settles (the screen keeps it in the address); `onChange({active, query})` hears every change of what the box asks.
export function createSearch({id = 'q', initial = '', sync = () => {}, onCommit = () => {}, onChange = () => {}} = {}) {
  const state = {query: '', shown: '', committed: '', verdict: 'idle', view: 'idle', groups: [], offset: 0, total: 0, pending: false,
    loadingMore: false, moreError: false, error: null, seq: 0};
  let timer = null;

  const lock = (el, on) => {
    el.disabled = on;
    if (on) el.setAttribute('aria-disabled', 'true');
    else el.removeAttribute('aria-disabled');
  };

  const label = h('label', {class: 'sr-only', for: id});
  const input = h('input', {class: 'input find-input', id, type: 'search', value: initial, autocomplete: 'off', spellcheck: 'false',
    enterkeyhint: 'search', 'aria-describedby': `${id}-status`, 'data-engine': '',
    on: {input: () => change(false), keydown: (event) => {
      if (event.key !== 'ArrowDown' || event.isComposing) return;
      const first = results.querySelector('a.find-title, a.find-hit');
      if (first) { event.preventDefault(); first.focus(); }
    }}});
  const submit = btn({type: 'submit', kind: 'primary', engine: true, label: ''});
  const form = h('form', {class: 'find-form', role: 'search', on: {submit: (event) => { event.preventDefault(); change(true); }}}, label, input, submit);
  const status = h('p', {class: 'find-status small', id: `${id}-status`, role: 'status', 'aria-live': 'polite'});
  const results = h('div', {class: 'find-results', on: {keydown: (event) => {
    if ((event.key !== 'ArrowDown' && event.key !== 'ArrowUp') || event.isComposing) return;
    const links = Array.from(results.querySelectorAll('a.find-title, a.find-hit'));
    const at = links.indexOf(document.activeElement);
    if (at < 0) return;
    event.preventDefault();
    const next = links[at + (event.key === 'ArrowDown' ? 1 : -1)];
    (next || input).focus();
  }}});

  const quoted = () => tidy(state.query, 40) + (Array.from(state.query).length > 40 ? '…' : '');

  function statusText() {
    switch (state.verdict) {
      case 'idle': return L('제목·대화·요약 안에서 찾아요. 두 글자 이상 입력해 주세요.', 'Searches titles, transcripts and summaries. Type at least two characters.');
      case 'short': return L('한 글자만으로는 찾지 않아요. 한 글자 더 입력해 주세요.', 'One character is too short to search. Add one more.');
      case 'bad': return L('제어문자나 보이지 않는 글자는 찾을 수 없어요.', 'Control and invisible characters can\'t be searched.');
      case 'long': return L('검색어는 100자까지예요.', 'The search text can be up to 100 characters.');
      default:
    }
    if (state.pending && !state.loadingMore) return L('찾는 중…', 'Searching…');
    if (state.view === 'error') return L('찾지 못했어요.', 'The search didn\'t go through.');
    if (state.view === 'none') return L(`‘${quoted()}’ 검색 결과가 없어요.`, `No matches for “${quoted()}”.`);
    if (state.view !== 'ok') return '';
    const shown = state.groups.reduce((sum, group) => sum + group.hits.length, 0);
    return state.offset < state.total
      ? L(`일치하는 곳 ${state.total}개 중 ${shown}개를 보여 줘요.`, `${state.total} matches, showing ${shown}.`)
      : L(`일치하는 곳 ${state.total}개`, `${state.total} match${state.total === 1 ? '' : 'es'}`);
  }

  function paintStatus() {
    const text = statusText();
    if (status.textContent !== text) status.textContent = text;   // the same sentence is not read out again on every keystroke
    const bad = state.verdict === 'bad' || state.verdict === 'long';
    status.setAttribute('class', 'find-status small' + (bad ? ' err-text' : ' muted'));
    if (bad) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
    const dim = state.pending && state.view === 'ok';
    results.setAttribute('aria-busy', state.pending ? 'true' : 'false');
    results.setAttribute('class', 'find-results' + (dim ? ' is-busy' : ''));
    const more = results.querySelector('[data-act="more"]');   // not while another search is being typed or asked: it would ask for the wrong list
    if (more && !more.dataset.offline) lock(more, state.pending);
  }

  const hitView = (item) => {
    const where = item.kind === 'title' ? chip('line', null, L('제목', 'Title')) : item.kind === 'summary' ? chip('line', null, L('요약', 'Summary'))
      : [item.start === null ? null : h('span', {class: 'find-ts'}, stamp(item.start)), ' ', item.speaker ? h('b', {class: 'find-sp'}, item.speaker) : null];
    return h('li', null, h('a', {class: 'find-hit', href: hitHref(item)}, h('span', {class: 'find-where'}, where),
      h('span', {class: 'find-snip'}, item.snippet.map((part) => (part.hit ? h('mark', null, part.text) : part.text)))));
  };

  const groupView = (group) => h('li', {class: 'find-group'},
    h('div', {class: 'find-gh'}, h('a', {class: 'find-title', href: `/notes/${encodeURIComponent(group.job_id)}`}, group.title || group.job_id),
      group.date && fullDate(group.date) ? h('span', {class: 'small muted'}, fullDate(group.date)) : null),
    h('ul', {class: 'find-hits'}, group.hits.map(hitView)));

  function paintResults() {
    let body = null;
    if (state.view === 'ok') {
      const left = state.total - state.offset;
      body = [h('ol', {class: 'find-groups', 'aria-label': L('검색 결과, 회의록별', 'Search results by meeting')}, state.groups.map(groupView)),
        left > 0 ? h('div', {class: 'find-more'},
          btn({small: true, engine: true, act: 'more', disabled: state.loadingMore,
            label: state.loadingMore ? L('불러오는 중…', 'Loading…') : L(`더 보기 (${left}개 남음)`, `Show more (${left} left)`), on: {click: () => run(state.shown, state.offset)}}),
          state.moreError ? h('span', {class: 'err-text small', role: 'alert'}, L('더 가져오지 못했어요. 다시 눌러 주세요.', 'Couldn\'t load more. Press it again.')) : null) : null];
    } else if (state.view === 'none') {
      body = empty({tight: true, mood: 'worry', bubble: L('못 찾았어요.', 'Nothing found.'),
        text: L('띄어쓰기는 달라도 찾아요. 다른 낱말이나 더 짧은 낱말로 찾아 보세요. 이미 쓴 회의록 안에서만 찾아요.',
          'Spacing doesn\'t matter. Try another or a shorter word. Only minutes that are already written are searched.')});
    } else if (state.view === 'error') {
      const problem = apiProblem(state.error);
      const why = state.error.status === 400 && state.error.body && typeof state.error.body.error === 'string' ? tidy(state.error.body.error, 200) : '';
      body = banner('err', '!', [h('b', null, problem.what), ' ', code(problem.code), why ? h('div', {class: 'small'}, why) : null],
        [btn({small: true, engine: true, act: 'retry', label: L('다시 시도', 'Try again'), on: {click: () => run(state.committed, 0)}})]);
    }
    replace(results, body);
    sync(results);
  }

  function paintAll() {
    label.textContent = L('회의록 검색', 'Search notes');
    form.setAttribute('aria-label', L('회의록 검색', 'Search notes'));
    input.setAttribute('placeholder', L('제목·대화·요약에서 찾기 (예: 대출)', 'Search titles, transcripts, summaries (e.g. budget)'));
    submit.textContent = L('찾기', 'Search');
    paintStatus();
    paintResults();
  }

  async function run(q, offset) {
    const mine = ++state.seq;
    state.pending = true;
    if (!offset) state.committed = q;
    if (offset) {
      state.loadingMore = true;
      state.moreError = false;
      paintResults();
    } else {
      onCommit(q);
    }
    paintStatus();
    try {
      const body = await get(`/api/search?q=${encodeURIComponent(q)}&limit=${PAGE}&offset=${offset}`);
      if (mine !== state.seq) return;
      const rows = body && Array.isArray(body.items) ? body.items : [];
      if (!offset) Object.assign(state, {groups: [], offset: 0});
      const before = results.querySelectorAll('a.find-hit').length;
      for (const item of rows.map(clean).filter(Boolean)) {
        const last = state.groups.at(-1);
        if (last && last.job_id === item.job_id) last.hits.push(item);
        else state.groups.push({job_id: item.job_id, title: item.title, date: item.date, hits: [item]});
      }
      state.offset += rows.length;
      state.total = body && Number.isInteger(body.total) && body.total >= 0 ? Math.max(body.total, state.offset) : state.offset;
      if (!rows.length) state.total = state.offset;     // an empty page ends the list, whatever the total says
      state.view = state.groups.length ? 'ok' : 'none';
      if (!offset) state.shown = q;
      state.error = null;
      state.pending = false;
      state.loadingMore = false;
      paintStatus();
      paintResults();
      const links = results.querySelectorAll('a.find-hit');
      if (offset && links[before]) links[before].focus();   // the keyboard carries on with the first new result
    } catch (error) {
      if (mine !== state.seq) return;
      state.pending = false;
      state.loadingMore = false;
      if (offset) {
        state.moreError = true;
      } else {
        state.view = 'error';
        state.error = {status: error && error.status !== undefined ? error.status : 0, body: error && error.body ? error.body : null};
      }
      paintStatus();
      paintResults();
    }
  }

  // The text changed (or Enter was pressed): judge it now, ask the engine once the typing pauses (at once on Enter).
  function change(now) {
    clearTimeout(timer);
    const q = input.value.trim();
    state.verdict = judge(q);
    state.query = q;
    if (state.verdict !== 'ok') {
      state.seq += 1;                  // an answer still on its way is for text that is gone
      Object.assign(state, {view: 'idle', groups: [], offset: 0, total: 0, pending: false, loadingMore: false, moreError: false, error: null});
      timer = setTimeout(() => onCommit(q), DELAY);
      paintStatus();
      paintResults();
      onChange({active: false, query: q});
      return;
    }
    state.seq += 1;                    // what is still on its way answers older text
    state.pending = true;
    state.loadingMore = false;
    paintStatus();
    onChange({active: true, query: q});
    timer = setTimeout(() => run(q, 0), now ? 0 : DELAY);
  }

  const off = onLang(paintAll);
  paintAll();
  if (initial.trim()) change(true);

  return {
    form, status, results, input, id,
    root: h('div', {class: 'find'}, form, status, results),
    focus() { input.focus(); if (input.select) input.select(); },
    active: () => state.verdict === 'ok',
    destroy() { clearTimeout(timer); state.seq += 1; off(); },
  };
}

// ---- the ways in
let overlay = null;        // the open dialog's box, or null
let inline = null;         // set by a screen that has its own box: what `/` and ⌘K do there
let syncControls = () => {};
let installed = false;

export function registerInlineSearch(focus) { inline = focus; }

const NOT_TEXT = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image']);
function editable(el) {
  if (!el || !el.localName) return false;
  if (el.isContentEditable || el.localName === 'textarea' || el.localName === 'select') return true;
  return el.localName === 'input' && !NOT_TEXT.has(String(el.getAttribute('type') || 'text').toLowerCase());
}

export function openSearch(opener) {
  if (inline) { inline(); return; }
  if (overlay) { overlay.focus(); return; }
  if (document.querySelector('dialog')) return;   // another dialog (the update list) is open: not on top of it
  const back = opener || document.activeElement;
  const box = createSearch({id: 'fq', sync: (root) => syncControls(root)});
  const el = h('dialog', {class: 'dlg find-dlg', 'aria-label': L('회의록 검색', 'Search notes')});
  let closed = false;
  const stop = subscribe(() => syncControls(el));
  const finish = () => {
    if (closed) return;
    closed = true;
    overlay = null;
    stop();
    box.destroy();
    el.remove();
    const to = back && back.isConnected ? back : document.getElementById('main');
    if (to) to.focus();
  };
  const close = () => { if (el.open) el.close(); else finish(); };
  el.addEventListener('close', finish);
  el.addEventListener('click', (event) => { if (event.target === el) close(); });   // the backdrop
  el.append(h('div', {class: 'dlg-head find-bar'}, box.form, btn({small: true, kind: 'ghost', icon: 'x', aria: L('닫기', 'Close'), on: {click: close}})),
    h('div', {class: 'dlg-scroll'}, box.status, box.results),
    h('div', {class: 'dlg-foot small muted'}, L('↑ ↓ 로 옮기고 Enter로 열어요 · Esc로 닫아요', '↑ ↓ to move, Enter to open, Esc to close')));
  overlay = box;
  document.body.append(el);
  if (typeof el.showModal === 'function') el.showModal();
  else el.setAttribute('open', '');
  syncControls(el);
  box.focus();
}

function onKey(event) {
  if (event.defaultPrevented || event.isComposing || event.repeat) return;
  const key = String(event.key || '');
  const palette = (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && (key.toLowerCase() === 'k' || event.code === 'KeyK');
  const slash = !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey && (key === '/' || event.code === 'Slash') && !editable(event.target);
  if (!palette && !slash) return;
  if (!overlay && !inline && document.querySelector('dialog')) return;
  event.preventDefault();
  openSearch(event.target);
}

// One listener for the whole page; the shell calls this when it builds the frame.
export function installSearch(sync) {
  syncControls = sync;
  if (installed) return;
  installed = true;
  document.addEventListener('keydown', onKey);
}

// The button the shell puts in the menu (wide) and in the top bar (narrow).
export function searchTrigger(compact) {
  const open = (event) => openSearch(event.currentTarget);
  const shortcuts = 'Meta+K Control+K /';
  return compact
    ? h('button', {type: 'button', class: 'find-icon', 'aria-label': L('회의록 검색', 'Search notes'), 'aria-keyshortcuts': shortcuts, on: {click: open}}, searchIcon())
    : h('button', {type: 'button', class: 'find-trigger', 'aria-keyshortcuts': shortcuts, on: {click: open}},
      searchIcon(), h('span', null, L('회의록 검색', 'Search notes')), h('kbd', {'aria-hidden': 'true'}, '/'));
}
