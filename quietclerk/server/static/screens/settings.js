// Settings: contract §3.3 keys with their effective value, file value and lock (design: docs/ui/settings.html).
// Data: GET/PUT /api/settings (flat dotted keys; one invalid key rejects the whole save), GET /api/providers,
// POST /api/logout, GET /api/notes/migration (how many old-format notes are left), and the update state
// (lib/update.js: Check now, installed version). The list of deleted recordings and restoring them are not served, so the
// screen has no card for them.
// The word list (contract §10.7) edits vocabulary.terms, vocabulary.replace and the `vocabulary` entry of
// providers.consent through the same drafts, save bar and 400 display as every other key.
// The summary layout (headings per meeting type and a preference), the short-recording memo and the daily-note path (contract §10.8 E-G)
// are edited the same way; their rules and the headings editor are in settings-summary.js. The engine's default headings
// (postprocess.TYPE_SECTIONS) are not served by any API, so that file carries a copy that the tests compare with the engine.
import {h, icon, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, put, post} from '../lib/api.js';
import {btn, chip, code, banner, announce} from '../lib/ui.js';
import {providerLabel} from '../lib/jobs.js';
import {problemBanner} from '../lib/cards.js';
import {setTitle, syncEngineControls, langSwitch} from '../lib/shell.js';
import {updateCheckControl, updateVersions} from '../lib/update.js';
import {sectionsEditor, sectionsIssue, normalizeSections, instructionsIssue, dailyIssue, problemText as summaryProblem, serverReason, MEMO_RANGE, MAX_INSTRUCTIONS} from './settings-summary.js';

const ENV = {root: 'QC_ROOT', inbox: 'QC_INBOX', output: 'QC_OUTPUT', since: 'QC_SINCE', min_duration_sec: 'QC_MIN_DURATION_SEC',
  stable_sec: 'QC_STABLE_SEC', 'language.mode': 'QC_LANGUAGE', 'providers.local_only': 'QC_LOCAL_ONLY', 'server.port': 'QC_PORT'};
const APPLY = {
  rec: () => L('다음 녹음부터 적용', 'Applies from the next recording'),
  scan: () => L('다음 확인부터 적용', 'Applies from the next scan'),
  clean: () => L('다음 정리부터 적용', 'Applies at next cleanup'),
  restart: () => L('엔진 다시 시작 후 적용', 'Applies after engine restart'),
  now: () => L('바로 적용', 'Applies now'),
  sum: () => L('다음 요약부터 적용', 'Applies from the next summary'),
};
const FIELD_NAMES = {transcript: ['대화록', 'transcript'], source_name: ['파일 이름', 'file name'], project_list: ['프로젝트 목록', 'project list'], vocabulary: ['단어장', 'word list']};
// Summary layout, memo and daily-note keys (contract §10.8 E-G): same drafts, save bar and 400 display as every other key.
const SECTIONS = 'summary.sections';
const INSTRUCTIONS = 'summary.instructions';
const MEMO_ON = 'memo.enabled';
const MEMO_MIN = 'memo.min_sec';
const DAILY = 'daily_note.path';

// ---- word list rules (contract §10.7): up to 200 entries of 1-40 characters. The engine counts characters (not UTF-16
// units) and refuses every Unicode "other" character (control, zero-width, bidirectional, private use), while the save
// check only refuses ASCII and C1 controls. The stricter rule is applied here so nothing the engine would refuse is sent.
const TERMS = 'vocabulary.terms';
const FIXES = 'vocabulary.replace';
const MAX_ENTRIES = 200;
const MAX_CHARS = 40;
const OTHER = /\p{C}/u;
const CONSENT_FIELDS = ['transcript', 'source_name', 'project_list', 'vocabulary'];
const isVocabulary = (key) => key === TERMS || key === FIXES;
const size = (text) => Array.from(text).length;

// null when the trimmed entry is fine, else the reason.
function entryProblem(text) {
  if (!text) return {why: 'empty'};
  if (OTHER.test(text)) return {why: 'chars'};
  const n = size(text);
  return n > MAX_CHARS ? {why: 'long', n} : null;
}

const problemText = ({why, n}) => ({
  empty: () => L('비어 있어요.', 'It\'s empty.'),
  chars: () => L('제어문자나 보이지 않는 글자는 쓸 수 없어요.', 'Control and invisible characters aren\'t allowed.'),
  long: () => L(`${n}자예요. ${MAX_CHARS}자까지 쓸 수 있어요.`, `That is ${n} characters; the limit is ${MAX_CHARS}.`),
  half: () => L('틀린 표기와 바른 표기를 모두 적어 주세요.', 'Fill in both the wrong and the correct spelling.'),
  conflict: () => L('같은 틀린 표기에 바른 표기가 둘이에요. 하나만 남겨 주세요.', 'This wrong spelling has two different corrections. Keep one.'),
}[why]());

// Several entries at once: line breaks or commas. Pieces are trimmed and empty ones vanish.
const BREAKS = /[\r\n\v\f\u0085\u2028\u2029,;，；、]/u;
const splitEntries = (raw) => String(raw).split(/[\r\n\v\f\u0085\u2028\u2029]+|\s*[,;，；、]\s*/u).map((piece) => piece.trim()).filter(Boolean);

// Adds what can be added to `list` (nothing is dropped silently): `keep` are the pieces to fix and try again.
function addEntries(list, raw) {
  const next = [...list];
  const out = {added: 0, dup: 0, full: 0, bad: [], keep: []};
  for (const piece of splitEntries(raw)) {
    const bad = entryProblem(piece);
    if (bad) {
      out.bad.push(bad);
      out.keep.push(piece);
    } else if (next.includes(piece)) {
      out.dup += 1;
    } else if (next.length >= MAX_ENTRIES) {
      out.full += 1;
      out.keep.push(piece);
    } else {
      next.push(piece);
      out.added += 1;
    }
  }
  return {next, ...out};
}

// What to say after an add (a function, so it follows the display language): nothing when everything went in.
function addSaid(out) {
  const total = out.added + out.dup + out.full + out.bad.length;
  if (!total) return () => L('낱말을 적어 주세요.', 'Type a word first.');
  const skipped = total - out.added;
  if (!skipped) return null;
  if (total === 1) {
    if (out.bad.length) return () => problemText(out.bad[0]);
    if (out.dup) return () => L('이미 있어요.', 'Already in the list.');
    return () => L(`${MAX_ENTRIES}개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_ENTRIES}). Remove one to add more.`);
  }
  return () => {
    const why = [out.bad.length ? L(`길이·글자 문제 ${out.bad.length}`, `${out.bad.length} with a length or character problem`) : null,
      out.dup ? L(`중복 ${out.dup}`, `${out.dup} duplicate${out.dup === 1 ? '' : 's'}`) : null,
      out.full ? L(`자리 없음 ${out.full}`, `${out.full} over the limit`) : null].filter(Boolean).join(', ');
    return L(`${out.added}개를 넣고 ${skipped}개는 건너뛰었어요 (${why}).`, `Added ${out.added}, skipped ${skipped} (${why}).`);
  };
}

// One verdict per row of the replacement editor (null = fine). A row left completely empty is not a problem.
function fixIssues(rows) {
  const targets = new Map();   // wrong spelling -> the distinct corrections typed for it
  for (const row of rows) {
    const from = row.from.trim(), to = row.to.trim();
    if (!from || !to) continue;
    if (!targets.has(from)) targets.set(from, new Set());
    targets.get(from).add(to);
  }
  return rows.map((row) => {
    const from = row.from.trim(), to = row.to.trim();
    if (!from && !to) return null;
    if (!from || !to) return {why: 'half'};
    return entryProblem(from) || entryProblem(to) || (targets.get(from).size > 1 ? {why: 'conflict'} : null);
  });
}

// The pairs the server gets: the rows that are fine, in the order typed, an identical pair once. Key order matches
// the server's own answer so an unchanged list compares equal.
function fixPairs(rows, issues) {
  const pairs = [];
  rows.forEach((row, i) => {
    if (issues[i] || (!row.from.trim() && !row.to.trim())) return;
    const pair = {from: row.from.trim(), to: row.to.trim()};
    if (!pairs.some((p) => p.from === pair.from && p.to === pair.to)) pairs.push(pair);
  });
  return pairs;
}

// The server's reasons for a list it refuses, in words (anything else is shown as it came).
const SERVER_WHY = [
  [/at most/, () => L(`최대 ${MAX_ENTRIES}개까지 둘 수 있어요.`, `At most ${MAX_ENTRIES} entries are allowed.`)],
  [/control characters/, () => L(`${MAX_CHARS}자까지, 제어문자 없이 적어 주세요.`, `Up to ${MAX_CHARS} characters, with no control characters.`)],
  [/conflicting/, () => L('같은 틀린 표기에 바른 표기가 둘이에요. 하나만 남겨 주세요.', 'A wrong spelling has two different corrections. Keep one.')],
];
const serverWhy = (message) => {
  const hit = SERVER_WHY.find(([pattern]) => pattern.test(message));
  return hit ? hit[1]() : message;
};

export async function mount({content}) {
  setTitle('설정 · QuietClerk', 'Settings · QuietClerk');
  const state = {server: null, identity: null, providers: [], draft: {}, errors: {}, notice: null, loadError: null, migration: null};
  const barHost = h('div', {class: 'slot'});


  async function loadIdentity() {
    try {
      state.identity = await get('/api/status');
    } catch (_) { /* version information remains explicitly unknown */ }
  }
  async function load() {
    await loadIdentity();
    try {
      state.server = await get('/api/settings');
      state.loadError = null;
    } catch (error) {
      state.loadError = error;
    }
    try {
      state.providers = (await get('/api/providers')).items;
    } catch (_) { /* provider rows say "unknown" */ }
    try {
      state.migration = await get('/api/notes/migration');
    } catch (_) { /* the card just links to the conversion screen */ }
    render();
    if (location.hash) {
      const target = document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView();
    }
  }

  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const effective = (key) => state.server.effective[key];
  const value = (key) => (key in state.draft ? state.draft[key] : effective(key));
  const isLocked = (key) => state.server.environment_keys.includes(key) || key === 'root' || key === 'inbox';
  const changed = () => Object.keys(state.draft).filter((key) => !same(state.draft[key], effective(key)));

  let memoNote = null;   // the sentence under the memo length: which recordings become memos; follows both lengths

  function setDraft(key, next) {
    if (same(next, effective(key))) delete state.draft[key];
    else state.draft[key] = next;
    delete state.errors[key];
    renderBar();
    if (memoNote) paintMemoNote();
  }

  const show = (v) => (typeof v === 'string' ? v : JSON.stringify(v));

  function lockNote(key) {
    const env = ENV[key];
    const file = state.server.file[key];
    return h('p', {class: 'small note'}, icon('lock'), h('span', null, env
      ? L(`환경 변수 ${env}로 정해져 있어 여기서 바꿀 수 없어요. 지금 값 ${show(effective(key))} · 파일 값 ${file === undefined ? '없음' : show(file)}.`,
        `Set by the environment variable ${env}, so it can't be changed here. In effect: ${show(effective(key))} · file value: ${file === undefined ? 'none' : show(file)}.`)
      : key === 'root' ? L('여기서 바꿀 수 없어요. 옮기려면 유지보수 명령 quietclerk을 써요.', 'Can\'t be changed here. Use the quietclerk maintenance command to move it.')
        : L('실행 중에는 바꿀 수 없어요.', 'Can\'t be changed while running.')));
  }

  // A setting's key is for people editing settings.toml: it is the label's tooltip (field), not part of the page.
  const tags = (apply) => h('div', {class: 'tags'},
    apply === 'now' ? chip('ok', '✓', APPLY.now()) : apply === 'restart' ? chip('warn', '↻', APPLY.restart()) : chip('line', '↻', APPLY[apply]()));

  const lockChip = () => chip('lock', '⊘', L('잠김', 'Locked'));

  function field({id, key, label, help, control, apply, locked, extra, wide}) {
    const error = state.errors[key];
    return h('div', {class: 'field' + (locked ? ' locked' : '') + (wide ? ' wide' : ''), 'data-key': key},
      h('div', {class: 'lab'}, h('label', {for: id, title: extra || key}, label), help ? h('span', {class: 'help'}, help) : null),
      h('div', {class: 'ctl'}, control, locked ? lockNote(key) : null,
        error ? h('p', {class: 'err-text', id: `${id}-err`}, error, ' ', code(`400 ${key}`)) : null,
        apply ? tags(apply) : null));
  }

  function textField(key, id, label, help, apply, cls) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('input', {class: `input ${cls || ''}`, id, value: String(value(key) ?? ''), disabled: locked,
      'aria-invalid': state.errors[key] ? 'true' : null, 'aria-describedby': state.errors[key] ? `${id}-err` : null, 'data-engine': locked ? null : '',
      on: {input: (event) => setDraft(key, event.target.value)}})});
  }

  function numberField(key, id, label, help, apply, unit, cls) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('div', {class: 'row'},
      h('input', {class: `input ${cls || 'narrow'}`, id, inputmode: 'numeric', value: String(value(key) ?? ''), disabled: locked,
        'aria-invalid': state.errors[key] ? 'true' : null, 'aria-describedby': state.errors[key] ? `${id}-err` : null, 'data-engine': locked ? null : '',
        on: {input: (event) => setDraft(key, /^\d+$/.test(event.target.value.trim()) ? Number(event.target.value.trim()) : event.target.value)}}),
      unit ? h('span', {class: 'small'}, unit) : null, locked ? lockChip() : null)});
  }

  function segField(key, id, label, help, apply, options) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('div', {class: 'seg', role: 'radiogroup', 'aria-labelledby': `${id}-l`},
      options.map(([v, text], index) => h('label', null,
        h('input', {type: 'radio', name: key, id: index ? null : id, value: v, checked: value(key) === v, disabled: locked, 'data-engine': locked ? null : '',
          on: {change: () => setDraft(key, v)}}), h('span', null, text))))});
  }

  function switchField(key, id, label, help, apply) {
    const locked = isLocked(key);
    const on = !!value(key);
    const text = h('span', null, on ? L('켬', 'On') : L('끔', 'Off'));
    return field({id, key, label, help, apply, locked, control: h('label', {class: 'switch'},
      h('input', {type: 'checkbox', role: 'switch', id, checked: on, disabled: locked, 'data-engine': locked ? null : '',
        on: {change: (event) => { setDraft(key, event.target.checked); text.textContent = event.target.checked ? L('켬', 'On') : L('끔', 'Off'); }}}), text)});
  }

  // ---- providers: the order list (enabling and consent live in setup step 4)
  const providersHost = h('div', {class: 'slot'});
  function providerRows() {
    const order = value('providers.order') || [];
    const consent = value('providers.consent') || {};
    const by = Object.fromEntries(state.providers.map((p) => [p.name, p]));
    const known = state.providers.map((p) => p.name);
    const rows = [...order, ...known.filter((name) => !order.includes(name))];
    const status = (name) => {
      const p = by[name];
      if (!p) return [chip('idle', '?', L('확인 못 함', 'Unknown'))];
      const out = [];
      if (!p.installed) out.push(chip('idle', '—', L('설치 안 됨', 'Not installed')));
      else if (p.logged_in === false) out.push(chip('err', '!', L('로그인 필요', 'Sign-in needed')));
      else if (p.tool_block === 'verified') out.push(chip('ok', '✓', L('사용 가능', 'Ready')));
      else out.push(chip('warn', '!', p.tool_block === 'unsupported' ? L('쓸 수 없음', 'Unavailable') : L('확인 전', 'Unverified')));
      if (p.endpoint_class === 'external') out.push(chip('warn', '↗', L('외부', 'External')));
      else if (p.endpoint_class === 'local') out.push(chip('ok', '✓', L('이 Mac', 'This Mac')));
      else out.push(chip('idle', '?', L('로컬 확인 전', 'Local not verified')));
      return out;
    };
    const move = (name, by_) => {
      const next = [...order];
      const i = next.indexOf(name);
      next.splice(i, 1);
      next.splice(i + by_, 0, name);
      setDraft('providers.order', next);
      renderProviders();
    };
    const items = rows.map((name) => {
      const index = order.indexOf(name);
      const on = index >= 0;
      const sends = (field) => (FIELD_NAMES[field] ? FIELD_NAMES[field] : [field, field]);
      // Every engine has the same grid: name and state chips / one sentence, with the action link at the right end of it.
      return h('li', {class: 'provider-row' + (on ? '' : ' off')},
        h('div', {class: 'pr-name'}, on ? code(String(index + 1)) : null, h('b', null, providerLabel(name)), status(name)),
        on ? h('div', {class: 'pr-move'},
          btn({small: true, engine: true, disabled: index === 0, icon: 'up', aria: L(`${providerLabel(name)} 위로`, `Move ${providerLabel(name)} up`), on: {click: () => move(name, -1)}}),
          btn({small: true, engine: true, disabled: index === order.length - 1, icon: 'down', aria: L(`${providerLabel(name)} 아래로`, `Move ${providerLabel(name)} down`), on: {click: () => move(name, 1)}})) : null,
        h('p', {class: 'pr-state small muted'}, on ? L(`보낼 것: ${(consent[name] || []).map((f) => sends(f)[0]).join('·') || '없음'}`,
          `Sends: ${(consent[name] || []).map((f) => sends(f)[1]).join(', ') || 'nothing'}`) : L('꺼짐 · 순서에 없음', 'Off · not in order')),
        h('div', {class: 'pr-link'}, btn({small: true, kind: 'ghost', href: '/setup/4', label: on ? L('동의 바꾸기', 'Edit consent') : L('켜기', 'Turn on')})));
    });
    items.push(h('li', {class: 'provider-row off'}, h('div', {class: 'pr-name'}, h('b', null, 'Gemini CLI'), chip('err', '⊘', L('쓸 수 없음', 'Unavailable'))),
      h('p', {class: 'pr-state small muted'}, L('개인 구독 로그인을 서버가 거절해요', 'Server rejects personal subscription sign-in'))));
    return h('ol', {class: 'stack tight', id: 'f-order'}, items);
  }

  function renderProviders() {
    replace(providersHost, providerRows());
    syncEngineControls(providersHost);
  }

  // ---- word list (contract §10.7): the names and terms, the exact fixes, and which engines may receive the list. Each is a
  // draft like any other key. Whatever is typed (or came from the file) is only ever put in the page as text.
  const termsHost = h('div', {class: 'slot'});
  const fixesHost = h('div', {class: 'slot'});
  const consentHost = h('div', {class: 'slot'});
  const typed = {add: '', said: null};   // the add box, and the last thing it said (a function: it follows the language)
  let termsUi = null;                    // the parts of the terms editor that change without redrawing the box
  let fixUi = null;
  let fixRows = null;                    // [{from, to, touched}] as typed: half-filled rows live here, not in the draft
  let fixRefs = [];                      // the inputs and message of each drawn row, repainted in place while typing

  const termList = () => (Array.isArray(value(TERMS)) ? value(TERMS).map(String) : []);
  const rows = () => {
    if (!fixRows) {
      const list = Array.isArray(value(FIXES)) ? value(FIXES) : [];
      fixRows = list.filter((pair) => pair && typeof pair === 'object').map((pair) => ({from: String(pair.from ?? ''), to: String(pair.to ?? ''), touched: false}));
    }
    return fixRows;
  };
  const off = (el, on) => {
    el.disabled = on;
    if (on) el.setAttribute('aria-disabled', 'true');
    else el.removeAttribute('aria-disabled');
  };
  // The red line under a field is about the last save; once that list is edited it no longer applies.
  const dropError = (id) => {
    const el = document.getElementById(`${id}-err`);
    if (el) el.remove();
  };

  function termChip(term, index) {
    const bad = !!entryProblem(term.trim());
    return h('li', {class: 'term' + (bad ? ' bad' : '')}, bad ? h('i', {'aria-hidden': 'true'}, '!') : null, h('span', {class: 'term-t'}, term),
      btn({small: true, kind: 'ghost', engine: true, icon: 'x', aria: L(`삭제: ${term}`, `Remove: ${term}`), disabled: isLocked(TERMS), on: {click: () => removeTerm(index)}}));
  }

  function refreshTerms() {
    const terms = termList();
    const full = terms.length >= MAX_ENTRIES;
    const said = typed.said ? typed.said() : '';
    replace(termsUi.list, terms.map(termChip));
    termsUi.list.hidden = !terms.length;
    termsUi.empty.hidden = terms.length > 0;
    termsUi.warn.hidden = !terms.some((term) => entryProblem(term.trim()));
    termsUi.count.textContent = `${terms.length} / ${MAX_ENTRIES}`;
    termsUi.why.hidden = !full;
    off(termsUi.add, full || isLocked(TERMS));
    termsUi.said.textContent = said;
    termsUi.input.value = typed.add;
    if (said) termsUi.input.setAttribute('aria-invalid', 'true');
    else termsUi.input.removeAttribute('aria-invalid');
    syncEngineControls(termsHost);
  }

  function addTerms(raw, fromBox) {
    const out = addEntries(termList(), raw);
    if (out.added) {
      setDraft(TERMS, out.next);
      dropError('f-vt');
    }
    if (fromBox) typed.add = out.keep.join(', ');
    typed.said = addSaid(out);
    refreshTerms();
    if (out.added) announce(L(`추가했어요 (${out.next.length}개)`, `Added (${out.next.length} in the list)`));
    else if (typed.said) announce(typed.said());
    termsUi.input.focus();
  }

  function removeTerm(index) {
    setDraft(TERMS, termList().filter((_, i) => i !== index));
    typed.said = null;   // what the last add said (e.g. "full") no longer holds once something is removed
    dropError('f-vt');
    refreshTerms();
    const buttons = termsUi.list.querySelectorAll('button');
    (buttons[index] || buttons[index - 1] || termsUi.input).focus();
    announce(L(`삭제했어요 (${termList().length}개 남음)`, `Removed (${termList().length} left)`));
  }

  // Several entries pasted at once (a column from a sheet, a comma list) go in as they are; a single entry is typed as usual.
  function pasteTerms(event) {
    const text = event.clipboardData ? event.clipboardData.getData('text') : '';
    if (!BREAKS.test(text)) return;
    event.preventDefault();
    addTerms(text, false);
  }

  function renderTerms() {
    const locked = isLocked(TERMS);
    termsUi = {
      input: h('input', {class: 'input', id: 'f-vt', placeholder: L('예: 책마루', 'e.g. Kubernetes'), disabled: locked, autocomplete: 'off', spellcheck: 'false',
        'aria-describedby': 'f-vt-said', 'data-engine': locked ? null : '',
        on: {input: (event) => { typed.add = event.target.value; }, paste: pasteTerms}}),
      list: h('ul', {class: 'terms', 'aria-label': L('단어장 낱말', 'Word list entries')}),
      empty: h('p', {class: 'small muted'}, L('아직 없어요. 자주 틀리게 적히는 이름이나 용어를 넣어 보세요.', 'Nothing yet. Add names or terms that often come out wrong.')),
      warn: h('p', {class: 'err-text small', id: 'f-vt-marked'}, L('! 표시한 낱말에는 쓸 수 없는 글자가 있어요. 지우고 다시 넣어 주세요.', 'Entries marked ! contain characters that aren\'t allowed. Remove them and add them again.')),
      count: h('span', {class: 'small muted num'}),
      why: h('span', {class: 'why', id: 'f-vt-full'}, L(`${MAX_ENTRIES}개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_ENTRIES}). Remove one to add more.`)),
      said: h('p', {class: 'err-text small', id: 'f-vt-said'}),
      add: btn({type: 'submit', small: true, engine: true, icon: 'plus', label: L('추가', 'Add')}),
    };
    replace(termsHost, termsUi.empty, termsUi.list, termsUi.warn,
      h('form', {class: 'add-row', 'aria-label': L('낱말 추가', 'Add an entry'), on: {submit: (event) => { event.preventDefault(); addTerms(typed.add, true); }}}, termsUi.input, termsUi.add),
      termsUi.said, h('div', {class: 'row'}, termsUi.count, termsUi.why),
      h('p', {class: 'small muted'}, L('쉼표나 줄바꿈으로 나누면 여러 개를 한 번에 넣어요. 같은 낱말은 한 번만 남아요.', 'Separate entries with commas or line breaks to add several at once. A repeated entry is kept once.')));
    refreshTerms();
  }

  // The wrong -> correct rows. The inputs are never redrawn while typing: only their invalid marks and message change.
  function paintFixes() {
    const list = rows();
    const issues = fixIssues(list);
    fixRefs.forEach((ref, i) => {
      // "fill in both" waits until the row was left; every other problem shows at once
      const issue = issues[i] && (issues[i].why !== 'half' || list[i].touched) ? issues[i] : null;
      const marks = {from: !!issue && (issue.why !== 'half' || !list[i].from.trim()), to: !!issue && (issue.why !== 'half' || !list[i].to.trim())};
      for (const [name, bad] of Object.entries(marks)) {
        if (bad) ref[name].setAttribute('aria-invalid', 'true');
        else ref[name].removeAttribute('aria-invalid');
      }
      ref.said.textContent = issue ? problemText(issue) : '';
    });
  }

  const syncFixes = () => setDraft(FIXES, fixPairs(rows(), fixIssues(rows())));

  function editFix(i, name, text) {
    rows()[i][name] = text;
    dropError('f-vr');
    syncFixes();
    paintFixes();
  }

  function addFix() {
    rows().push({from: '', to: '', touched: false});
    dropError('f-vr');
    renderFixes();
    fixRefs[fixRefs.length - 1].from.focus();
  }

  function removeFix(i) {
    rows().splice(i, 1);
    dropError('f-vr');
    syncFixes();
    renderFixes();
    const next = fixRefs[i] || fixRefs[i - 1];
    (next ? next.from : fixUi.add).focus();
    announce(L(`행을 지웠어요 (${rows().length}개 남음)`, `Row removed (${rows().length} left)`));
  }

  function renderFixes() {
    const list = rows();
    const locked = isLocked(FIXES);
    const full = list.length >= MAX_ENTRIES;
    fixRefs = [];
    const items = list.map((row, i) => {
      const msgId = `f-vr-${i}-m`;
      const side = (name, cls, label, example) => h('input', {class: `input ${cls}`, id: !i && name === 'from' ? 'f-vr' : null, value: row[name], placeholder: example,
        autocomplete: 'off', spellcheck: 'false', disabled: locked, 'aria-label': label, 'aria-describedby': msgId, 'data-engine': locked ? null : '',
        on: {input: (event) => editFix(i, name, event.target.value)}});
      const from = side('from', 'vf', L(`틀린 표기 ${i + 1}`, `Wrong spelling ${i + 1}`), L('틀린 표기 (예: 책 마루)', 'Wrong spelling (e.g. cubernetes)'));
      const to = side('to', 'vt', L(`바른 표기 ${i + 1}`, `Correct spelling ${i + 1}`), L('바른 표기 (예: 책마루)', 'Correct spelling (e.g. Kubernetes)'));
      const said = h('p', {class: 'err-text small vmsg', id: msgId});
      fixRefs.push({from, to, said});
      return h('li', {class: 'vrow', on: {focusout: (event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) { row.touched = true; paintFixes(); }
      }}}, from, h('span', {class: 'arrow', 'aria-hidden': 'true'}, '→'), to,
      h('span', {class: 'vdel'}, btn({small: true, kind: 'ghost', engine: true, icon: 'x', disabled: locked, aria: L(`행 ${i + 1} 삭제`, `Remove row ${i + 1}`), on: {click: () => removeFix(i)}})), said);
    });
    fixUi = {add: btn({small: true, engine: true, icon: 'plus', disabled: full || locked, label: L('행 추가', 'Add a row'), on: {click: addFix}})};
    replace(fixesHost,
      list.length ? h('ul', {class: 'vrows', 'aria-label': L('틀린 표기를 바른 표기로', 'Wrong spelling to correct spelling')}, items) : h('p', {class: 'small muted'}, L('아직 없어요.', 'Nothing yet.')),
      h('div', {class: 'row'}, fixUi.add, h('span', {class: 'small muted num'}, `${list.length} / ${MAX_ENTRIES}`),
        full ? h('span', {class: 'why'}, L(`${MAX_ENTRIES}개를 모두 채웠어요. 한 줄을 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_ENTRIES}). Remove a row to add more.`)) : null),
      h('p', {class: 'small muted'}, L('한 낱말 단위로 바꾸고, 뒤에 조사가 붙어도 돼요 (책 마루가 → 책마루가). 같은 틀린 표기에 바른 표기를 둘 줄 수는 없어요.',
        'Whole words are replaced, and a Korean particle after the word is fine (책 마루가 → 책마루가). One wrong spelling can have only one correction.')));
    paintFixes();
    syncEngineControls(fixesHost);
  }

  // Which engines get the list: the `vocabulary` entry of providers.consent, for the engines that are on.
  function setSendVocabulary(name, on) {
    const consent = {...(value('providers.consent') || {})};
    const next = new Set(consent[name] || []);
    if (on) next.add('vocabulary');
    else next.delete('vocabulary');
    consent[name] = CONSENT_FIELDS.filter((field) => next.has(field));
    setDraft('providers.consent', consent);
    dropError('f-vc');
    renderProviders();
  }

  function renderConsent() {
    const order = value('providers.order') || [];
    const consent = value('providers.consent') || {};
    const said = (can, on) => (!can ? L('먼저 설치 마법사 4단계에서 이 엔진에 대화록을 보내도록 허용해야 해요.', 'First allow the transcript for this engine in setup step 4.')
      : on ? L('교정·분류·요약 때 단어장도 함께 보내요.', 'The word list is sent along when correcting, classifying and summarising.') : L('단어장 없이 교정해요.', 'Corrects without the word list.'));
    replace(consentHost,
      order.length ? h('div', {class: 'stack tight', role: 'group', 'aria-label': L('단어장을 보낼 엔진', 'Engines that get the word list')}, order.map((name) => {
        const list = consent[name] || [];
        const can = list.includes('transcript');
        const status = h('span', {class: 'muted'}, said(can, list.includes('vocabulary')));
        return h('label', {class: 'check small'},
          h('input', {type: 'checkbox', checked: list.includes('vocabulary'), disabled: !can, 'data-engine': can ? '' : null,
            on: {change: (event) => { setSendVocabulary(name, event.target.checked); status.textContent = said(true, event.target.checked); }}}),
          h('span', {title: 'vocabulary'}, h('b', {class: 'ink'}, providerLabel(name)), h('br'), status));
      })) : h('p', {class: 'small muted'}, L('켜 둔 요약 엔진이 없어요. 엔진을 켜면 여기서 단어장을 보낼지 고를 수 있어요. ', 'No summary engine is on. Once one is, you can choose here whether it gets the word list. '),
        h('a', {href: '/setup/4'}, L('요약 엔진 켜기', 'Turn on an engine'))),
      h('p', {class: 'small muted'}, L('받아쓰기는 이 Mac 안에서 하니 단어장을 늘 써요. 교정·분류·요약 엔진에는 동의한 곳에만 보내고, 동의하지 않으면 단어장 없이 교정해요. 틀린 표기 → 바른 표기는 어디에도 보내지 않아요.',
        'Transcription runs on this Mac and always uses the word list. Correction, classification and summary engines get it only if you agree; otherwise they work without it. Wrong → correct spellings are never sent anywhere.')));
    syncEngineControls(consentHost);
  }

  function renderVocabulary() {
    renderTerms();
    renderFixes();
    renderConsent();
  }

  // ---- summary headings and preference, memo, daily note (contract §10.8 E-G). Typed text is only ever put in the page as text.
  let editor = null;   // the headings editor: built when the settings are loaded, then redrawn in place

  function sectionsField() {
    if (!editor) {
      editor = sectionsEditor({get: () => { const v = value(SECTIONS); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; },
        set: (next) => { setDraft(SECTIONS, next); dropError('f-sections'); }, locked: isLocked(SECTIONS), sync: syncEngineControls});
    }
    return field({id: 'f-sections', key: SECTIONS, label: L('유형별 제목', 'Headings by type'), help: L('핵심 요약은 고정 · 나머지는 1~12개, 40자까지', 'Key summary is fixed · 1–12 others, 40 characters each'),
      apply: 'sum', locked: isLocked(SECTIONS), control: editor.el});
  }

  // 500 characters, one line: the engine refuses control characters and line breaks, so a break is turned into a space (and said) instead of dropped.
  function instructionsField() {
    const locked = isLocked(INSTRUCTIONS);
    const note = h('span', {class: 'why', id: 'f-instr-note'});
    const count = h('span', {class: 'small muted num', id: 'f-instr-n'});
    const said = h('p', {class: 'err-text small', id: 'f-instr-m'});
    const area = h('textarea', {class: 'input area', id: 'f-instr', rows: 4, value: String(value(INSTRUCTIONS) ?? ''), autocomplete: 'off', spellcheck: 'false', disabled: locked,
      placeholder: L('예: 결정 사항을 먼저 쓰고, 숫자에는 단위를 붙여 주세요.', 'e.g. Put decisions first and keep units next to numbers.'),
      'aria-describedby': 'f-instr-n f-instr-m', 'data-engine': locked ? null : '',
      on: {keydown: (event) => { if (event.key === 'Enter' && !event.isComposing) event.preventDefault(); },
        input: () => {
          const flat = area.value.replace(/[\r\n\u2028\u2029]+/g, ' ');
          note.textContent = flat === area.value ? '' : L('줄바꿈은 공백으로 바꿨어요.', 'Line breaks were turned into spaces.');
          if (flat !== area.value) area.value = flat;
          setDraft(INSTRUCTIONS, area.value);
          dropError('f-instr');
          paint();
        }}});
    function paint() {
      const issue = instructionsIssue(area.value);
      count.textContent = `${Array.from(area.value.trim()).length} / ${MAX_INSTRUCTIONS}`;
      said.textContent = issue ? summaryProblem(issue) : '';
      if (issue || state.errors[INSTRUCTIONS]) area.setAttribute('aria-invalid', 'true');   // the engine's refusal of the last save keeps the red border until the text is edited
      else area.removeAttribute('aria-invalid');
    }
    paint();
    return field({id: 'f-instr', key: INSTRUCTIONS, label: L('요약 선호', 'Summary preferences'), help: L('500자까지 · 한 줄', 'Up to 500 characters · one line'),
      apply: 'sum', locked, control: h('div', {class: 'stack tight'}, area, said, h('div', {class: 'row'}, count, note),
        h('p', {class: 'small muted'}, L('요약에 바라는 점을 적어요. 규칙과 부딪치면 무시돼요. 근거를 다는 규칙과 안전 규칙은 바꿀 수 없어요.',
          'Say what you want from the summary. It is ignored where it clashes with the rules; the evidence and safety rules can\'t be changed.')))});
  }

  function paintMemoNote() {
    const min = value(MEMO_MIN), max = value('min_duration_sec');
    let said = '';
    if (value(MEMO_ON) && typeof min === 'number' && typeof max === 'number') {
      said = min >= max
        ? L(`메모 최소 길이(${min}초)가 위의 최소 길이(${max}초)와 같거나 커서, 메모가 될 녹음이 없어요.`, `The shortest memo (${min} s) is not below the minimum length above (${max} s), so no recording would become a memo.`)
        : L(`${min}초 이상 ${max}초 미만 녹음을 메모로 남겨요.`, `Recordings from ${min} s up to ${max} s become memos.`);
    }
    memoNote.textContent = said;
  }

  // The switch and its length. The length is off (with its reason) while the switch is off.
  function memoFields() {
    const on = switchField(MEMO_ON, 'f-memo', L('짧은 녹음을 메모로', 'Short recordings as memos'),
      L('최소 길이보다 짧은 녹음을 건너뛰지 않고 짧은 메모로 남겨요. 한 사람이 말한 메모로 보고, 요약은 핵심 요약과 할 일만 써요.',
        'Keep recordings shorter than the minimum length as short memos instead of skipping them. A memo is taken as one speaker, and its summary has only the key summary and tasks.'), 'scan');
    const min = numberField(MEMO_MIN, 'f-memo-min', L('메모로 남길 최소 길이', 'Shortest memo'),
      L(`이보다 짧으면 메모로도 남기지 않고 건너뛰어요 (${MEMO_RANGE[0]}~${MEMO_RANGE[1]}초)`, `Anything shorter is still skipped (${MEMO_RANGE[0]}–${MEMO_RANGE[1]} seconds)`), 'scan', L('초', 'seconds'));
    const box = on.querySelector('input');
    const input = min.querySelector('input');
    const why = h('span', {class: 'why'}, L('메모를 켜면 쓸 수 있어요', 'Available once memos are on'));
    const gate = () => {
      if (!isLocked(MEMO_MIN)) {
        input.disabled = !box.checked;
        if (box.checked) input.removeAttribute('aria-disabled');
        else input.setAttribute('aria-disabled', 'true');
      }
      why.hidden = box.checked;
    };
    box.addEventListener('change', gate);
    memoNote = h('p', {class: 'small ink', 'aria-live': 'polite'});
    min.querySelector('.ctl').append(why, memoNote);
    gate();
    paintMemoNote();
    return [on, min];
  }

  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

  function dailyField() {
    const locked = isLocked(DAILY);
    const said = h('p', {class: 'err-text small', id: 'f-daily-m'});
    const example = h('p', {class: 'small ink', id: 'f-daily-eg', 'aria-live': 'polite'});
    const input = h('input', {class: 'input wide', id: 'f-daily', value: String(value(DAILY) ?? ''), placeholder: 'Daily/{date}.md', autocomplete: 'off', spellcheck: 'false',
      disabled: locked, 'aria-describedby': 'f-daily-m f-daily-eg', 'data-engine': locked ? null : '',
      on: {input: (event) => { setDraft(DAILY, event.target.value); dropError('f-daily'); paint(); }}});
    function paint() {
      const text = input.value.trim();
      const issue = dailyIssue(input.value);
      said.textContent = issue ? summaryProblem(issue) : '';
      if (issue || state.errors[DAILY]) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
      const path = text.split('{date}').join(today());
      example.textContent = !text ? L('지금은 꺼져 있어요.', 'It\'s off now.') : issue ? '' : L(`오늘 녹음이라면 ${path} 에 링크를 더해요.`, `A recording made today adds its link to ${path}.`);
    }
    paint();
    return field({id: 'f-daily', key: DAILY, label: L('데일리 노트에 연결', 'Link from the daily note'), help: L('비워 두면 꺼요', 'Leave empty to turn it off'), apply: 'rec', locked,
      control: h('div', {class: 'stack tight'}, input, said, example,
        h('p', {class: 'small muted'}, L('녹음한 날의 데일리 노트에 회의록 링크를 한 줄(‘- 10:00 [[노트 이름|제목]]’) 더해요. 그 노트의 ‘## 회의록’ 제목(영어 노트는 ‘## Meetings’) 아래에만 쓰고, 다른 줄은 바꾸지 않아요. 파일이 없으면 그 제목만 있는 파일을 만들어요.',
          'Adds one line (‘- 10:00 [[note name|title]]’) to the daily note of the recording\'s day, under its ‘## Meetings’ heading (‘## 회의록’ for Korean notes). No other line is changed. A missing file is created with just that heading.')),
        h('p', {class: 'small muted'}, L('{date}는 녹음한 날(YYYY-MM-DD)로 바뀌어요. 볼트 기준 경로(Daily/{date}.md)나 ~로 시작하는 전체 경로를 쓸 수 있고, 회의록 폴더가 속한 Obsidian 볼트 안이어야 해요.',
          '{date} becomes the day of the recording (YYYY-MM-DD). Use a path from the vault root (Daily/{date}.md) or a full path starting with ~; it must be inside the Obsidian vault that holds the notes folder.')))});
  }

  // ---- sections
  function section(id, title, ...body) {
    return h('section', {class: 'card', id, 'aria-labelledby': `${id}-h`}, h('div', {class: 'card-head'}, h('h2', {id: `${id}-h`}, title)), h('div', null, body));
  }

  function sections() {
    return [
      section('s-out', L('회의록', 'Notes'),
        field({id: 'f-out', key: 'output', label: L('회의록 폴더', 'Notes folder'), help: L('볼트 안의 폴더', 'A folder in your vault'), apply: 'rec', locked: isLocked('output'),
          control: h('div', {class: 'row'}, h('input', {class: 'input fill', id: 'f-out', value: String(value('output') ?? ''), disabled: isLocked('output'), 'data-engine': isLocked('output') ? null : '',
            'aria-invalid': state.errors.output ? 'true' : null, on: {input: (event) => setDraft('output', event.target.value)}}),
          h('span', {class: 'row gap6'}, btn({small: true, disabled: true, label: L('바꾸기', 'Change')}),
            h('span', {class: 'why'}, L('폴더 선택 창은 Mac 앱에서만 열려요', 'The folder picker opens only in the Mac app'))))}),
        segField('notes.output_language', 'f-ol', L('회의록 언어', 'Minutes language'), L('대화록 언어와 다르게 쓸 수 있어요', 'Can differ from the spoken language'), 'rec',
          [['same', L('녹음과 같게', 'Same as recording')], ['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]]),
        dailyField()),
      section('s-rec', L('처리할 녹음', 'Recordings to process'),
        textField('since', 'f-since', L('이 시각 이후 녹음만', 'Only recordings after'), L('그 전 녹음은 ‘기존 녹음’에서 골라요', 'Earlier ones are under ‘Older recordings’'), 'scan', 'mid'),
        numberField('min_duration_sec', 'f-min', L('최소 길이', 'Minimum length'), L('이보다 짧으면 건너뛰어요', 'Shorter recordings are skipped'), 'scan', L('초', 'seconds')),
        numberField('stable_sec', 'f-stable', L('도착 확인 시간', 'Arrival settle time'), L('파일 크기가 이만큼 그대로면 다 왔다고 봐요', 'A file is complete once its size holds this long'), 'scan', L('초', 'seconds')),
        memoFields()),
      section('s-lang', L('언어', 'Language'),
        segField('language.mode', 'f-lm', L('녹음 언어', 'Recording language'), L('고정하면 언어 감지를 건너뛰어요', 'Pinning skips language detection'), 'rec',
          [['auto', L('자동 감지', 'Auto-detect')], ['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]]),
        segField('language.default', 'f-ld', L('애매할 때 쓸 언어', 'Fallback language'), L('자동 감지가 한쪽으로 정해지지 않을 때', 'Used when detection is inconclusive'), 'rec',
          [['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]]),
        field({id: 'f-ui', key: 'ui.language', label: L('화면 언어', 'Display language'), help: L('이 화면에만 적용돼요', 'Affects this screen only'), apply: 'now', control: h('div', {id: 'f-ui'}, langSwitch())})),
      section('s-vocab', L('단어장', 'Word list'),
        h('div', {class: 'stack small ink'},
          h('p', null, L('자주 틀리게 받아 적는 이름·용어를 적어 두세요. 받아쓰기가 그 철자를 따라가고, 교정할 때도 그 철자를 써요.',
            'List names and terms that often come out wrong. Transcription follows those spellings, and so does correction.')),
          h('p', {class: 'muted'}, L('다음 녹음부터 적용돼요. 이미 만든 회의록에 적용하려면 그 회의록에서 ‘처음부터 다시’를 눌러요. ‘요약만 다시’는 새 단어장을 쓰지 않아요.',
            'Applies from the next recording. To apply it to minutes you\'ve already made, press ‘Redo from scratch’ on that note; ‘Re-summarize only’ doesn\'t pick up the new word list.'))),
        field({id: 'f-vt', key: TERMS, label: L('이름·용어', 'Names & terms'), help: L('최대 200개 · 한 개당 40자까지', 'Up to 200 entries · 40 characters each'),
          apply: 'rec', locked: isLocked(TERMS), control: termsHost}),
        field({id: 'f-vr', key: FIXES, label: L('틀린 표기 → 바른 표기', 'Wrong → correct spelling'), help: L('받아쓰기 직후 이 Mac에서만 바꿔요', 'Applied on this Mac right after transcription'),
          apply: 'rec', locked: isLocked(FIXES), control: fixesHost}),
        field({id: 'f-vc', key: 'providers.consent', label: L('단어장을 보낼 엔진', 'Engines that get the word list'), help: L('동의한 엔진에만 보내요', 'Only engines you allow'),
          apply: 'rec', control: consentHost})),
      section('s-sum', L('요약 구성', 'Summary layout'),
        h('div', {class: 'stack small ink'},
          h('p', null, L('회의 유형마다 요약에 넣을 제목을 정해요. 핵심 요약은 늘 맨 앞에 있고 바꿀 수 없어요. 근거를 다는 규칙도 그대로예요.',
            'Choose the headings of the summary for each type of meeting. The key summary always comes first and can\'t be changed, and neither can the rule to cite evidence.')),
          h('p', {class: 'muted'}, L('다음 요약부터 적용돼요. 이미 만든 회의록에 적용하려면 그 회의록에서 ‘요약만 다시’를 눌러요.',
            'Applies from the next summary. To apply it to minutes you\'ve already made, press ‘Re-summarize only’ on that note.'))),
        sectionsField(), instructionsField()),
      section('providers', L('요약 엔진', 'Summary engines'),
        switchField('providers.local_only', 'f-lo', L('로컬 전용 모드', 'Local-only mode'),
          L('켜면 이 Mac 밖으로 글자를 보내지 않고, 외부로 넘어가는 대체도 막아요. 로컬로 확인된 엔진이 없으면 요약 단계에서 기다리게 돼요.', 'When on, no text leaves this Mac and external fallback is blocked. If no engine is verified local, jobs wait at summarising.'), 'rec'),
        field({id: 'f-order', key: 'providers.order', label: L('순서와 보낼 것', 'Order and data sent'), help: L('위에서부터 쓰고, 실패하면 다음으로 넘어가요. 동의한 엔진만 써요.', 'Used top to bottom; on failure the next is tried. Only engines you agreed to are used.'),
          apply: 'rec', extra: 'providers.order · providers.consent', wide: true, control: providersHost}),
        textField('providers.ollama.model', 'f-om', L('Ollama 모델', 'Ollama model'), L('설치된 모델 이름을 적어요.', 'Type an installed model name.'), 'rec', 'mid'),
        segField('providers.codex.effort', 'f-ce', L('Codex 생각 정도', 'Codex reasoning effort'), L('높일수록 느려요', 'Higher is slower'), 'rec',
          [['low', L('낮음', 'Low')], ['medium', L('보통', 'Medium')], ['high', L('높음', 'High')]]),
        segField('providers.codex.speed', 'f-cs', L('Codex 속도', 'Codex speed'), L('빠르게는 약 1.5배 빠르지만 구독 사용량을 2.5배 써요', 'Fast is about 1.5x quicker but uses 2.5x of your plan limits'), 'rec',
          [['standard', L('보통', 'Standard')], ['fast', L('빠르게', 'Fast')]])),
      section('retention', L('저장과 삭제', 'Storage & deletion'),
        field({id: 'f-root', key: 'root', label: L('데이터 폴더', 'Data folder'), help: L('엔진의 모든 파일이 여기 있어요', 'All engine files live here'), locked: true, extra: 'root',
          control: h('div', {class: 'row'}, h('input', {class: 'input mid', id: 'f-root', value: String(effective('root')), disabled: true}), lockChip())}),
        field({id: 'f-inbox', key: 'inbox', label: L('받는 폴더', 'Inbox'), help: L('Syncthing이 녹음을 넣는 곳 · 엔진은 읽기만 해요', 'Where Syncthing drops recordings · read-only for the engine'), locked: true, extra: 'inbox',
          control: h('div', {class: 'row'}, h('input', {class: 'input mid', id: 'f-inbox', value: String(effective('inbox')), disabled: true}), lockChip())}),
        numberField('retention.wav_days', 'f-wav', L('변환한 음성 보관', 'Keep converted audio'), L('회의록을 쓰고 며칠 뒤 지울지', 'Days after the note is written'), 'clean', L('일', 'days')),
        retentionTable()),
      section('s-ui', L('화면과 연결', 'Screen & access'),
        numberField('server.port', 'f-port', L('화면 주소 포트', 'Screen port'), null, 'restart', `127.0.0.1:${effective('server.port')}`, 'narrow'),
        state.server.restart_required ? banner('info', 'i', L('포트를 바꿨어요. 엔진을 다시 시작하면 새 주소로 열려요.', 'The port was changed. After the engine restarts it opens at the new address.')) : null,
        field({id: 'f-remote', key: 'remote', label: L('다른 기기에서 접속', 'Access from other devices'), help: L('지금 버전은 이 Mac에서만 열려요.', 'This version opens only on this Mac.'),
          control: chip('idle', '—', L('꺼짐 · 설정 없음', 'Off · no setting'))}),
        field({id: 'f-out2', key: 'logout', label: L('이 브라우저에서 로그아웃', 'Sign out of this browser'), help: L('다시 열려면 메뉴 막대 아이콘에서 ‘QuietClerk 열기’를 누르거나 터미널에서 quietclerk open을 실행해요.', 'To come back, choose Open QuietClerk from the menu bar icon or run quietclerk open in Terminal.'),
          control: btn({small: true, engine: true, label: L('로그아웃', 'Sign out'), on: {click: logout}})})),
      section('s-version', L('버전', 'Version'),
        field({id: 'f-engine-version', key: 'engine_version', label: L('엔진 버전', 'Engine version'),
          control: h('span', {id: 'f-engine-version'}, state.identity?.engine_version || L('확인할 수 없음', 'Unavailable'))}),
        field({id: 'f-install-method', key: 'installation_method', label: L('설치 방식', 'Installation method'),
          control: h('span', {id: 'f-install-method'}, state.identity?.installation_method === 'app' ? L('앱', 'App')
            : state.identity?.installation_method === 'cli' ? 'CLI' : L('확인할 수 없음', 'Unavailable'))}),
        state.identity?.last_updated_at ? field({id: 'f-last-update', key: 'last_updated_at', label: L('마지막 업데이트', 'Last updated'),
          control: h('time', {id: 'f-last-update', datetime: state.identity.last_updated_at}, state.identity.last_updated_at)}) : null,
        h('p', {class: 'small muted'}, L('앱 버전은 Mac 메뉴 막대의 QuietClerk 메뉴에서 확인하세요.', 'Find the app version in the QuietClerk menu in the Mac menu bar.'))),
      section('s-upd', L('업데이트', 'Updates'),
        switchField('updates.check', 'f-uc', L('하루 한 번 새 버전 확인', 'Check for a new version once a day'),
          L('GitHub에 새 버전이 있는지만 묻고, 녹음·회의록은 보내지 않아요', 'Only asks GitHub whether a new version exists; no recordings or minutes are sent'), 'now'),
        field({id: 'f-ucheck', key: 'update_check', label: L('직접 확인', 'Manual check'),
          help: L('눌러서 바로 물어봐요. 하루 한 번 확인이 꺼져 있어도 돼요', 'Asks right away, even when the daily check is off'), control: updateCheckControl('f-ucheck')}),
        field({id: 'f-uver', key: 'update_version', label: L('소스 변경', 'Source revision'), control: updateVersions('f-uver')})),
      section('consent', L('녹음 동의와 회사 정책', 'Recording consent & company policy'),
        h('div', {class: 'stack small ink'},
          h('p', null, L('녹음 전에 함께 있는 사람에게 알리고 동의를 받아 주세요. 녹음에 대한 법은 나라와 상황마다 달라요. QuietClerk는 녹음이 허용되는지 판단하지 않아요.', 'Tell everyone present and get their consent before recording. Recording laws differ by country and situation. QuietClerk doesn\'t judge whether a recording is allowed.')),
          h('p', null, L('회사 회의라면 회사 정책을 먼저 확인해 주세요. 외부 AI 사용을 막는 회사라면 로컬 전용 모드를 켜세요. 이 설정은 녹음을 보내기 전에 적용돼요.', 'For work meetings, check your company\'s policy first. If external AI is not allowed, turn on local-only mode. It applies before anything is sent.')),
          h('p', null, L('오디오는 내 폰과 이 Mac 사이에서만 오가요. 외부 요약 엔진에는 위에서 동의한 글자만 가요.', 'Audio moves only between your phone and this Mac. External engines receive only the text fields you agreed to above.')),
          h('p', {class: 'muted'}, L('처음 설정할 때 본 안내와 같은 내용이에요.', 'Same notice as during setup.')))),
      h('section', {class: 'card tight', 'aria-labelledby': 'mg-h'},
        h('div', {class: 'card-head'}, h('h2', {id: 'mg-h'}, L('이전 형식 노트 옮기기', 'Convert old-format notes')), migrationChip()),
        h('p', {class: 'small'}, L('볼트에 한국어 속성을 쓰는 이전 형식 노트가 있으면, 옮기기 전까지 새 회의록을 볼트에 넣지 않아요.', 'If your vault has notes with the old Korean properties, new minutes are not written to it until they are converted.')),
        h('div', {class: 'actions'}, btn({small: true, href: '/migrate', label: L('미리보기', 'Preview')}))),
    ];
  }

  // The conversion card's state comes from the real preview: notes left, nothing to do, or unknown.
  function migrationChip() {
    const m = state.migration;
    if (!m) return chip('idle', '?', L('확인 못 함', 'Unknown'));
    const left = m.preview.entries.filter((entry) => !entry.skip).length;
    if (left) return chip('warn', '!', L(`${left}개 남음`, `${left} left`));
    return m.migrated ? chip('ok', '✓', L('옮김', 'Converted')) : chip('line', '=', L('옮길 노트 없음', 'Nothing to convert'));
  }

  function retentionTable() {
    const days = value('retention.wav_days');
    const rows = [
      [L('원본 사본', 'Recording copy'), 'archive/', L('지울 때까지', 'Until you delete it')],
      [L('변환한 음성(WAV)', 'Converted audio (WAV)'), 'work/', L(`회의록을 쓰고 ${days}일`, `${days} days after the note`)],
      [L('중간 결과(대화록 등)', 'Working files (transcripts etc.)'), 'work/', L('새 회의록이 성공하면 이전 것 정리', 'Older ones cleaned after a new success')],
      [L('로그', 'Logs'), 'logs/', L('14일 · 작업 번호만, 회의 내용은 안 남겨요', '14 days · job IDs only, no meeting content')],
      [L('DB 백업', 'Database backups'), 'state.sqlite3.bak-*', L('최근 3개', 'Latest 3')],
      [L('노트 옮기기 백업', 'Note conversion backup'), 'note-backups/', L('지울 때까지', 'Until you delete it')],
      [L('회의록 노트', 'Notes'), null, L('내 것 · 엔진은 지우지 않아요', 'Yours · the engine never deletes them')],
    ];
    return [
      h('h3', {class: 'mt4'}, L('무엇을 얼마나 두나요', 'What\'s kept and for how long')),
      h('div', {class: 'table-wrap'}, h('table', {class: 'table'},
        h('thead', null, h('tr', null, h('th', null, L('데이터', 'Data')), h('th', null, L('어디에', 'Where')), h('th', null, L('얼마나', 'Kept')))),
        h('tbody', null, rows.map(([what, where, kept]) => h('tr', null, h('td', {'data-k': L('데이터', 'Data')}, what),
          h('td', {'data-k': L('어디에', 'Where')}, where ? h('code', null, where) : L('볼트', 'Vault')), h('td', {'data-k': L('얼마나', 'Kept')}, kept)))))),
      h('div', {class: 'grid g2 mt4'},
        h('div', {class: 'card tight'}, h('h3', null, L('‘처리 데이터 삭제’가 지우는 것', 'What ‘Delete processing data’ removes')), h('ul', {class: 'sec small'},
          h('li', null, L('원본 사본과 중간 결과', 'The recording copy and working files')),
          h('li', null, L('대화 관련 기록, 할 일·필드 소유 기록', 'Transcript-related records and note ownership data')),
          h('li', null, L('같은 파일이 다시 와도 처리하지 않도록 지문(해시)만 남겨요', 'A fingerprint (hash) so the same file isn\'t processed again')))),
        h('div', {class: 'card tight'}, h('h3', null, L('지우지 못하는 것', 'What it can\'t remove')), h('ul', {class: 'sec small'},
          h('li', null, L('폰의 원본 녹음과 받는 폴더의 파일', 'The original on the phone and the file in the inbox')),
          h('li', null, L('볼트의 회의록 노트 (직접 지워 주세요)', 'The note in your vault (delete it yourself)')),
          h('li', null, L('외부 요약 엔진(Codex 등) 쪽에 남은 기록 — 각 서비스 정책을 따라요', 'Anything kept by external engines (Codex etc.) — their policies apply'))))),
      h('p', {class: 'small mt3'}, L('녹음마다 회의록 보기나 작업 화면에서 지워요. 처리 중이면 지금 단계를 마친 뒤 지워요.', 'Delete per recording from the note or Jobs screen. If it\'s running, deletion waits for the current step.')),
    ];
  }

  async function logout() {
    try {
      await post('/api/logout');
    } catch (_) { /* leaving anyway */ }
    location.replace('/');
  }

  // ---- save bar
  function renderBar() {
    const keys = changed();
    replace(barHost, h('div', {class: 'card tight hero stickybar'},
      h('div', {class: 'row'},
        h('b', {class: 'ink', 'aria-live': 'polite'}, keys.length ? L(`바꾼 항목 ${keys.length}개`, `${keys.length} change${keys.length === 1 ? '' : 's'}`) : L('바꾼 항목이 없어요', 'No changes')),
        h('span', {class: 'small muted'}, L('처리 중인 녹음은 시작할 때의 설정으로 끝까지 가요.', 'A recording already in progress finishes with the settings it started with.')),
        h('span', {class: 'spacer'}),
        btn({small: true, engine: true, disabled: !keys.length, label: L('되돌리기', 'Revert'), on: {click: () => { state.draft = {}; state.errors = {}; state.notice = null; fixRows = null; typed.add = ''; typed.said = null; render(); }}}),
        btn({small: true, kind: 'primary', engine: true, disabled: !keys.length, label: L('저장', 'Save'), on: {click: save}})),
      h('p', {class: 'small muted'}, L('저장하면 settings.toml을 통째로 다시 써요. 파일에 직접 단 주석은 남지 않아요.', 'Saving rewrites settings.toml entirely; comments you added are not kept.'))));
    syncEngineControls(barHost);
  }

  async function save() {
    const keys = changed();
    state.errors = {};
    state.notice = null;
    const body = {};
    for (const key of keys) {
      const v = state.draft[key];
      if (['min_duration_sec', 'stable_sec', 'retention.wav_days', 'server.port', MEMO_MIN].includes(key) && typeof v !== 'number') {
        state.errors[key] = L('숫자로 적어 주세요.', 'Enter a whole number.');
      } else if (key === MEMO_MIN && (!Number.isInteger(v) || v < MEMO_RANGE[0] || v > MEMO_RANGE[1])) {
        state.errors[key] = L(`${MEMO_RANGE[0]}~${MEMO_RANGE[1]}초 사이로 적어 주세요.`, `Enter ${MEMO_RANGE[0]}–${MEMO_RANGE[1]} seconds.`);
      } else if (key === 'since' && !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(String(v))) {
        state.errors[key] = L('형식이 맞지 않아요. 예: 2026-11-09 23:00', 'Wrong format. Example: 2026-11-09 23:00');
      } else if (key === SECTIONS) {
        // headings the engine would refuse are shown in their rows, never sent
        const issue = sectionsIssue(v);
        if (issue) state.errors[key] = [L('고쳐야 할 제목이 있어요. 빨간 줄을 고치거나 지워 주세요.', 'Some headings need fixing. Correct or remove the ones in red.'), issue.row < 0 ? summaryProblem(issue) : ''].join(' ').trim();
        else body[key] = normalizeSections(v);
      } else if (key === INSTRUCTIONS || key === DAILY) {
        const issue = key === INSTRUCTIONS ? instructionsIssue(v) : dailyIssue(v);
        if (issue) state.errors[key] = summaryProblem(issue);
        else body[key] = String(v).trim();
      } else {
        body[key] = v;
      }
    }
    // The word list editors: rows that are half-filled or invalid, and entries the engine would refuse, are shown instead of sent.
    for (const row of rows()) row.touched = true;
    if (fixIssues(rows()).some(Boolean)) state.errors[FIXES] = L('고쳐야 할 행이 있어요. 빨간 행을 고치거나 지워 주세요.', 'Some rows need fixing. Correct or remove the ones in red.');
    if (keys.includes(TERMS) && state.draft[TERMS].some((term) => entryProblem(term.trim()))) {
      state.errors[TERMS] = L('쓸 수 없는 글자가 든 낱말이 있어요. ! 표시한 낱말을 지우고 다시 넣어 주세요.', 'Some entries contain characters that aren\'t allowed. Remove the ones marked ! and add them again.');
    }
    if (Object.keys(state.errors).length) {
      state.notice = banner('err', '!', [h('b', null, L('저장하지 못했어요.', 'Not saved.')), ' ',
        L(`빨간 항목 ${Object.keys(state.errors).length}개를 고쳐 주세요. 나머지는 아직 바뀌지 않았어요.`, `Fix the ${Object.keys(state.errors).length} item(s) in red. Nothing else has changed yet.`)]);
      render();
      return;
    }
    try {
      state.server = await put('/api/settings', body);
      state.draft = {};
      fixRows = null;
      state.notice = banner('info', '✓', [h('b', null, L('저장했어요.', 'Saved.'))]);
      announce(L('저장했어요.', 'Saved.'));
    } catch (error) {
      const field = error.body && error.body.field;
      if ((error.status === 400 || error.status === 409) && field) {
        state.errors[field] = error.status === 409 ? L('환경 변수로 정해져 있어 바꿀 수 없어요.', 'Fixed by an environment variable; it can\'t be changed.')
          : field === 'since' ? L('형식이 맞지 않아요. 예: 2026-11-09 23:00', 'Wrong format. Example: 2026-11-09 23:00') : isVocabulary(field) ? serverWhy(String(error.body.error)) : serverReason(field, String(error.body.error));
        state.notice = banner('err', '!', [h('b', null, L('저장하지 못했어요.', 'Not saved.')), ' ',
          L('빨간 항목 1개를 고쳐 주세요. 나머지는 아직 바뀌지 않았어요.', 'Fix the 1 item in red. Nothing else has changed yet.'), ' ', code(`${error.status} {field: ${field}}`)]);
      } else {
        state.notice = problemBanner(error);
      }
    }
    render();
  }

  function render() {
    if (!state.server) {
      replace(content, h('div', {class: 'topbar'}, h('h1', null, L('설정', 'Settings'))), state.loadError ? problemBanner(state.loadError) : null);
      return;
    }
    const keep = document.activeElement && document.activeElement.id;
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('설정', 'Settings'))),
      state.notice,
      h('nav', {class: 'row', 'aria-label': L('설정 구역', 'Settings sections')}, [
        ['s-out', L('회의록', 'Notes')], ['s-rec', L('처리할 녹음', 'Recordings')], ['s-lang', L('언어', 'Language')], ['s-vocab', L('단어장', 'Word list')], ['s-sum', L('요약 구성', 'Summary layout')], ['providers', L('요약 엔진', 'Summary engines')],
        ['retention', L('저장·삭제', 'Storage & deletion')], ['s-ui', L('화면', 'Screen')], ['s-version', L('버전', 'Version')], ['s-upd', L('업데이트', 'Updates')], ['consent', L('녹음 동의', 'Recording consent')]]
        .map(([id, text]) => h('a', {class: 'chip line', href: `#${id}`}, text))),
      sections(), barHost);
    renderProviders();
    renderVocabulary();
    editor.refresh({strict: !!state.errors[SECTIONS]});
    renderBar();
    syncEngineControls(content);
    if (keep && document.getElementById(keep)) document.getElementById(keep).focus();
  }

  onLang(render);
  await load();
}
