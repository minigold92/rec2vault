// "Add to the word list?" (contract §10.8 B): word pairs that the user's own line edits suggest. Nothing is added by
// itself. A press reads the current vocabulary.replace from the settings and saves it again with the pair at the end, so
// the next recordings get the spelling fixed right after transcription (contract §10.7); this meeting keeps what was edited.
import {h, replace} from './dom.js';
import {L} from './i18n.js';
import {announce, apiProblem, btn, code} from './ui.js';
import {get, put} from './api.js';
import {cleanText} from './note-text.js';
import {syncEngineControls} from './shell.js';

const KEY = 'vocabulary.replace';
const MAX_ENTRIES = 200;
const MAX_CHARS = 40;
const SHOWN = 5;
const id = (pair) => `${pair.from}\u0000${pair.to}`;

// null when the pair can go into the list, else why not.
const unfit = (pair) => (pair.from === pair.to || !cleanText(pair.from, MAX_CHARS).ok || !cleanText(pair.to, MAX_CHARS).ok ? 'bad' : null);

export function createSuggestions() {
  const state = {pairs: [], status: new Map(), all: false};
  const node = h('section', {class: 'sugg', 'aria-labelledby': 'sugg-h', hidden: true});

  const sentence = (pair, status) => ({
    bad: () => L(`${MAX_CHARS}자까지, 보이지 않는 글자 없이 서로 다른 두 낱말만 넣을 수 있어요.`, `Only two different words of up to ${MAX_CHARS} characters, with no invisible characters, can go in.`),
    added: () => L('단어장에 넣었어요. 다음 녹음부터 바로 고쳐져요.', 'Added. The next recordings get it fixed right away.'),
    present: () => L('이미 단어장에 있어요.', 'Already in the word list.'),
    clash: () => L(`이미 ‘${pair.from}’에 다른 바른 표기가 들어 있어요. 단어장에서 정리해 주세요.`, `“${pair.from}” already has another correction. Sort it out in the word list.`),
    full: () => L(`단어장이 가득 찼어요 (${MAX_ENTRIES}개).`, `The word list is full (${MAX_ENTRIES}).`),
    locked: () => L('환경 변수로 정해져 있어 여기서 바꿀 수 없어요.', 'It is set by an environment variable, so it can\'t be changed here.'),
  }[status] || (() => ''))();

  async function add(pair) {
    state.status.set(id(pair), {kind: 'busy'});
    render();
    let done;
    try {
      const settings = await get('/api/settings');
      const current = settings && settings.effective && Array.isArray(settings.effective[KEY]) ? settings.effective[KEY] : [];
      const list = current.filter((p) => p && typeof p.from === 'string' && typeof p.to === 'string').map((p) => ({from: p.from, to: p.to}));
      const same = list.find((p) => p.from === pair.from);
      if (same) done = {kind: same.to === pair.to ? 'present' : 'clash'};
      else if (list.length >= MAX_ENTRIES) done = {kind: 'full'};
      else {
        await put('/api/settings', {[KEY]: [...list, {from: pair.from, to: pair.to}]});
        done = {kind: 'added'};
        announce(sentence(pair, 'added'));
      }
    } catch (error) {
      const problem = apiProblem(error);
      done = error.status === 409 && error.body && error.body.field === KEY ? {kind: 'locked'}
        : {kind: 'error', text: error.status === 400 && error.body && typeof error.body.error === 'string' ? serverWhy(error.body.error) : problem.what, code: problem.code};
    }
    state.status.set(id(pair), done);
    render();
  }

  // The server's reasons for a list it refuses, in words (anything else is shown as it came).
  const serverWhy = (message) => (/conflicting/.test(message) ? L('같은 틀린 표기에 바른 표기가 둘이에요. 단어장에서 정리해 주세요.', 'A wrong spelling has two different corrections. Sort it out in the word list.')
    : /at most/.test(message) ? L(`최대 ${MAX_ENTRIES}개까지 둘 수 있어요.`, `At most ${MAX_ENTRIES} entries are allowed.`)
      : /control characters/.test(message) ? L(`${MAX_CHARS}자까지, 제어문자 없이 적어 주세요.`, `Up to ${MAX_CHARS} characters, with no control characters.`) : message.slice(0, 120));

  function item(pair) {
    const now = state.status.get(id(pair)) || (unfit(pair) ? {kind: 'bad'} : {kind: 'idle'});
    const label = L(`단어장에 추가: ${pair.from} → ${pair.to}`, `Add to the word list: ${pair.from} → ${pair.to}`);
    const again = now.kind === 'idle' || now.kind === 'busy' || now.kind === 'error';   // a failed try can be tried again
    return h('li', {class: 'sugg-item'},
      h('span', {class: 'sugg-pair'}, h('span', {class: 'term-t'}, pair.from), h('span', {class: 'arrow', 'aria-hidden': 'true'}, ' → '), h('span', {class: 'term-t'}, pair.to)),
      again ? btn({small: true, engine: true, icon: 'plus', aria: label, label: L('단어장에 추가', 'Add to word list'), disabled: now.kind === 'busy', on: {click: () => add(pair)}}) : null,
      now.kind === 'idle' || now.kind === 'busy' ? null
        : h('span', {class: now.kind === 'added' ? 'small sugg-ok' : 'small why'}, now.kind === 'error' ? [now.text, ' ', code(now.code)] : sentence(pair, now.kind)));
  }

  function render() {
    node.hidden = !state.pairs.length;
    if (!state.pairs.length) {
      replace(node);
      return;
    }
    const shown = state.all ? state.pairs : state.pairs.slice(0, SHOWN);
    const rest = state.pairs.length - shown.length;
    replace(node,
      h('h3', {id: 'sugg-h'}, L('단어장에 추가할까요?', 'Add to the word list?')),
      h('p', {class: 'small muted'}, L('고친 낱말이에요. 단어장에 넣으면 다음 녹음부터 받아쓰기 직후 바로 고쳐져요. 이미 만든 회의록은 그대로예요.', 'These are words you changed. In the word list they get fixed right after transcription from the next recording on. Minutes already made stay as they are.')),
      h('ul', {class: 'sugg-list', 'aria-label': L('단어장 추가 후보', 'Word list suggestions')}, shown.map(item)),
      rest > 0 ? btn({small: true, kind: 'ghost', label: L(`${rest}개 더 보기`, `Show ${rest} more`), on: {click: () => { state.all = true; render(); }}}) : null);
    syncEngineControls(node);
  }

  // The pairs the server derived from the edits (GET /transcript: vocabulary_suggestions).
  function set(pairs) {
    state.pairs = (Array.isArray(pairs) ? pairs : []).filter((p) => p && typeof p.from === 'string' && typeof p.to === 'string').map((p) => ({from: p.from, to: p.to}));
    const keep = new Set(state.pairs.map(id));
    for (const key of state.status.keys()) if (!keep.has(key)) state.status.delete(key);
    render();
  }

  return {node, set, render};
}
