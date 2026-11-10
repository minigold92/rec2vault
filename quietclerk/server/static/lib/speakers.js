// Speaker panel of the minutes screen (contract §10.8 A): how much each speaker said, a short stretch of their voice,
// a name only you confirm (an engine guess stays "(추정)" until you say it is right), and merging two speaker numbers
// that are one person (undoable). The server is the truth: every change is followed by reading the list again.
import {h, replace} from './dom.js';
import {L} from './i18n.js';
import {announce, banner, btn, chip, code} from './ui.js';
import {dur, stamp} from './fmt.js';
import {readSpeakers, nameSpeaker, mergeSpeaker, refusal} from './overrides.js';
import {cleanText} from './note-text.js';
import {syncEngineControls} from './shell.js';

export const NAME_LIMIT = 40;

const off = (el, on) => {
  el.disabled = on;
  if (on) el.setAttribute('aria-disabled', 'true');
  else el.removeAttribute('aria-disabled');
};

const nameProblem = (check) => (check.why === 'chars'
  ? L('제어문자나 보이지 않는 글자는 쓸 수 없어요.', 'Control and invisible characters aren\'t allowed.')
  : check.why === 'long' ? L(`${check.n}자예요. ${NAME_LIMIT}자까지 쓸 수 있어요.`, `That is ${check.n} characters; the limit is ${NAME_LIMIT}.`) : '');

// hints: the engine's own notes per speaker from the page data ({label, role, name, name_start, split_suspect}).
// play(start, end, button) plays a stretch through the page's one audio element.
export function createSpeakers({jobId, hints = [], audioOk, isRunning, onRunning, onChange}) {
  const state = {list: null, failure: null, editing: new Set(), drafts: new Map(), merging: null, choice: new Map(),
    busy: false, problem: null, said: '', focus: null};
  const node = h('section', {class: 'card tight', id: 'spk', 'aria-labelledby': 'sp-h'});

  // Confirmed names of speakers that still stand on their own: what the note writes in place of S1, S2…
  const names = () => new Map((state.list || []).filter((s) => s.confirmed && s.name && !s.merged_into).map((s) => [s.label, s.name]));

  async function load() {
    try {
      state.list = (await readSpeakers(jobId)).speakers;
      state.failure = null;
    } catch (error) {
      state.failure = refusal(error);
    }
    render();
  }

  // One change at a time. `done` is what to say afterwards, `next` the control to put the keyboard on when it worked and
  // `back` where it stays when it did not; a refusal stays on screen with its code.
  async function write(label, next, back, task, done) {
    state.busy = true;
    state.problem = null;
    state.said = '';
    render();
    try {
      await task();
      state.said = done;
      announce(done);
      state.editing.delete(label);
      state.drafts.delete(label);
      state.merging = null;
      state.choice.delete(label);
    } catch (error) {
      state.problem = refusal(error);
      if (state.problem.running) onRunning();
    }
    state.busy = false;
    if (!state.problem) {
      try { state.list = (await readSpeakers(jobId)).speakers; } catch (_) { /* the change is saved; the list is read again next time */ }
      onChange();
    }
    state.focus = {label, act: state.problem ? back : next};
    render();
  }

  const act = (label, name, o) => {
    const el = btn({...o, act: name});
    el.setAttribute('data-label', label);
    return el;
  };
  const blocked = () => isRunning() || state.busy;

  const confirmNote = (name) => L(`이름을 확정했어요 (${name}). 노트의 화자 표·대화록·요약에도 넣었어요.`, `Name confirmed (${name}). It is in the note's speaker table, transcript and summary too.`);
  const confirmName = (s, name, back) => write(s.label, 'rename', back, () => nameSpeaker(jobId, s.label, name, true), confirmNote(name));
  const clearName = (s) => write(s.label, 'name', 'clear', () => nameSpeaker(jobId, s.label, null, false), L('이름을 지웠어요. 노트에도 이름이 빠졌어요.', 'Name cleared. It is out of the note too.'));
  const merge = (s, into) => write(s.label, 'unmerge', 'go', () => mergeSpeaker(jobId, s.label, into),
    L(`합치기: ${s.label} → ${into}. 대화록 줄의 화자만 바뀌었고, 언제든 되돌릴 수 있어요.`, `Merged ${s.label} into ${into}. Only the speaker on the lines changed, and you can undo it any time.`));
  const unmerge = (s) => write(s.label, 'merge', 'unmerge', () => mergeSpeaker(jobId, s.label, null), L(`합치기를 되돌렸어요 (${s.label}).`, `Undid the merge of ${s.label}.`));

  function nameForm(s) {
    const label = s.label;
    const msg = h('p', {class: 'err-text small', id: `spk-${label}-msg`});
    const named = !!s.name;
    const input = h('input', {class: 'input', type: 'text', autocomplete: 'off', spellcheck: 'false', 'data-engine': '', 'data-act': 'name', 'data-label': label,
      value: state.drafts.has(label) ? state.drafts.get(label) : (s.name || ''), placeholder: L('이름 (예: 오지안)', 'Name (e.g. Alex Kim)'),
      'aria-label': L(`${label}의 이름`, `Name of ${label}`), 'aria-describedby': `spk-${label}-msg`, disabled: blocked(),
      on: {input: (event) => { state.drafts.set(label, event.target.value); check(); },
        keydown: (event) => { if (event.key === 'Enter' && !event.isComposing && event.keyCode === 229) event.preventDefault(); }}});
    const ok = act(label, 'confirm', {type: 'submit', small: true, kind: 'primary', engine: true, label: L('확정', 'Confirm')});
    const check = () => {
      const result = cleanText(input.value, NAME_LIMIT);
      const said = result.ok || result.why === 'empty' ? '' : nameProblem(result);
      msg.textContent = said;
      if (said) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
      off(ok, !result.ok || blocked());
    };
    check();
    return h('form', {class: 'spk-form', 'aria-label': L(`${label} 이름 확정`, `Confirm the name of ${label}`), on: {submit: (event) => {
      event.preventDefault();
      const result = cleanText(input.value, NAME_LIMIT);
      if (result.ok && !blocked()) confirmName(s, result.text, 'confirm');
    }}},
    h('div', {class: 'add-row'}, input, ok),
    msg,
    named ? h('div', {class: 'actions'},
      state.editing.has(label) ? act(label, 'cancel', {small: true, label: L('취소', 'Cancel'), on: {click: () => { state.editing.delete(label); state.drafts.delete(label); state.focus = {label, act: 'rename'}; render(); }}}) : null,
      act(label, 'clear', {small: true, kind: 'danger', engine: true, disabled: blocked(), label: L('이름 지우기', 'Clear name'), on: {click: () => clearName(s)}})) : null);
  }

  function nameBlock(s, hint) {
    const label = s.label;
    if (s.merged_into) {
      return h('p', {class: 'spk-merged small'}, L(`${s.merged_into}에 합쳤어요. 이 화자의 줄은 ${s.merged_into} 화자로 보여요.`, `Merged into ${s.merged_into}. Its lines show as ${s.merged_into}.`), ' ',
        act(label, 'unmerge', {small: true, engine: true, disabled: blocked(), label: L('되돌리기', 'Undo'), on: {click: () => unmerge(s)}}));
    }
    if (state.editing.has(label)) return nameForm(s);
    if (s.confirmed && s.name) {
      return h('div', {class: 'spk-name'}, h('b', {class: 'spk-nm'}, s.name), chip('ok', '✓', L('확정', 'Confirmed')),
        act(label, 'rename', {small: true, kind: 'ghost', engine: true, disabled: blocked(), label: L('이름 바꾸기', 'Rename'), on: {click: () => { state.editing.add(label); state.focus = {label, act: 'name'}; render(); }}}));
    }
    if (s.name && s.name_source === 'engine') {
      const at = typeof hint.name_start === 'number' ? stamp(hint.name_start) : null;
      return h('div', {class: 'spk-name stack tight'},
        h('p', {class: 'spk-guess'}, h('b', {class: 'spk-nm'}, s.name), ' ', h('span', {class: 'muted'}, L('(추정)', '(estimated)'))),
        h('div', {class: 'actions'},
          act(label, 'agree', {small: true, kind: 'primary', engine: true, disabled: blocked(), label: L('맞아요', 'That\'s right'), on: {click: () => confirmName(s, s.name, 'agree')}}),
          act(label, 'rename', {small: true, engine: true, disabled: blocked(), label: L('다르게 입력', 'Type another'), on: {click: () => { state.editing.add(label); state.focus = {label, act: 'name'}; render(); }}}),
          at ? h('button', {class: 'ts', type: 'button', 'data-engine': '', 'data-seek': `${hint.name_start.toFixed(2)}-${(hint.name_start + 3).toFixed(2)}`,
            'aria-label': L(`이름이 나온 ${at} 구간 듣기`, `Hear where the name comes up (${at})`)}, at) : null));
    }
    return nameForm(s);
  }

  function mergeForm(s) {
    const label = s.label;
    const targets = state.list.filter((o) => o.label !== label && !o.merged_into);
    const select = h('select', {class: 'input compact', 'data-engine': '', 'data-act': 'target', 'data-label': label, 'aria-label': L(`합칠 대상 화자 (${label})`, `Speaker to merge ${label} into`),
      value: state.choice.get(label) || '', on: {change: (event) => { state.choice.set(label, event.target.value); off(go, !event.target.value || blocked()); }}},
    h('option', {value: ''}, L('화자 고르기', 'Choose a speaker')),
    targets.map((o) => h('option', {value: o.label}, o.confirmed && o.name ? `${o.label} · ${o.name}` : o.role ? `${o.label} · ${o.role}` : o.label)));
    const go = act(label, 'go', {small: true, kind: 'primary', engine: true, label: L('합치기', 'Merge'), disabled: !state.choice.get(label) || blocked(),
      on: {click: () => merge(s, select.value)}});
    return h('div', {class: 'spk-merge stack tight'},
      h('p', {class: 'small muted'}, L('화자 분리가 한 사람을 둘로 나눴다고 생각할 때 합쳐요. 대화록 줄의 화자만 바뀌고 글자는 그대로예요.', 'Merge when the split put one person under two numbers. Only the speaker on the lines changes; the words stay as they are.')),
      h('div', {class: 'add-row'}, select, go,
        act(label, 'merge', {small: true, label: L('취소', 'Cancel'), on: {click: () => { state.merging = null; state.focus = {label, act: 'merge'}; render(); }}})));
  }

  function row(s) {
    const label = s.label;
    const hint = hints.find((x) => x && x.label === label) || {};
    const absorbed = state.list.filter((o) => o.merged_into === label).map((o) => o.label);
    const pct = s.share > 0 && s.share < 0.005 ? '<1' : String(Math.round(s.share * 100));
    const sample = s.sample;
    const noVoice = !sample ? L('5초 넘게 이어서 말한 곳이 없어요', 'No stretch of speech over 5 seconds')
      : !audioOk() ? L('녹음 사본이 없어 들을 수 없어요', 'The recording copy is gone') : null;
    const listen = act(label, 'listen', {small: true, icon: 'play', label: L('목소리 듣기', 'Hear this voice'), engine: !noVoice, disabled: !!noVoice});
    if (!noVoice) listen.setAttribute('data-seek', `${sample.start.toFixed(2)}-${sample.end.toFixed(2)}`);
    const canMerge = state.list.some((o) => o.label !== label && !o.merged_into);
    return h('li', {class: 'spk' + (s.merged_into ? ' merged' : ''), id: `spk-${label}`},
      h('div', {class: 'spk-top'}, h('b', {class: 'spk-id'}, label), s.role ? h('span', {class: 'small muted spk-role'}, s.role) : null,
        hint.split_suspect ? chip('warn', '!', L('분리 오류 의심', 'Split suspected')) : null,
        absorbed.length ? chip('line', null, L(`${absorbed.join(', ')} 합침`, `${absorbed.join(', ')} merged in`)) : null),
      s.merged_into ? null : h('div', {class: 'spk-share'},
        h('div', {class: 'share', 'aria-hidden': 'true'}, h('i', {vars: {'--v': Math.max(0, Math.min(1, s.share))}})),
        h('span', {class: 'small num spk-pct'}, `${pct}% · ${dur(s.talk_sec)}`)),
      nameBlock(s, hint),
      s.merged_into ? null : h('div', {class: 'actions spk-actions'}, listen,
        state.merging === label ? null : act(label, 'merge', {small: true, engine: canMerge, disabled: !canMerge || blocked(), label: L('다른 화자와 합치기', 'Merge with another speaker'),
          on: {click: () => { state.merging = label; state.focus = {label, act: 'target'}; render(); }}}),
        noVoice ? h('span', {class: 'why'}, noVoice) : null,
        !canMerge ? h('span', {class: 'why'}, L('합칠 다른 화자가 없어요', 'There is no other speaker to merge with')) : null),
      !s.merged_into && state.merging === label ? mergeForm(s) : null);
  }

  // What the page data alone says, when the engine's list can't be read.
  const fallback = () => h('ul', {class: 'spk-list'}, hints.map((x) => h('li', {class: 'spk'},
    h('b', {class: 'spk-id'}, x.label), ' ', x.role ? h('span', {class: 'small muted'}, x.role) : null,
    x.name ? h('p', {class: 'small'}, x.name, ' ', h('span', {class: 'muted'}, L('(추정)', '(estimated)'))) : null)));

  function problem(why) {
    return banner('err', '!', [h('b', null, why.text), ' ',
      why.reason === 'vault_migration' ? [h('a', {href: '/migrate'}, L('이전 형식 노트 옮기기', 'Convert old-format notes')), ' '] : null, code(why.code)],
    why.reload ? [btn({small: true, label: L('새로 고침', 'Reload'), on: {click: () => location.reload()}})] : null);
  }

  function render() {
    const active = document.activeElement;
    const key = state.focus || (active && node.contains(active) && active.dataset && active.dataset.act ? {label: active.dataset.label, act: active.dataset.act} : null);
    state.focus = null;
    const count = state.list ? state.list.filter((s) => !s.merged_into).length : hints.length;
    replace(node,
      h('div', {class: 'card-head'}, h('h2', {id: 'sp-h'}, L('화자', 'Speakers')), h('span', {class: 'small muted'}, L(`${count}명`, count === 1 ? '1 speaker' : `${count} speakers`))),
      isRunning() ? h('p', {class: 'why spk-lock', role: 'status'}, L('이 회의를 처리하는 중이라 지금은 이름과 합치기를 바꿀 수 없어요. 끝나면 다시 쓸 수 있어요.', 'This meeting is being processed, so names and merges are off for now. They come back when it is done.')) : null,
      state.problem && !state.problem.running ? problem(state.problem) : null,
      state.list ? h('ul', {class: 'spk-list', 'aria-label': L('화자 목록', 'Speaker list')}, state.list.map(row))
        : state.failure ? [problem(state.failure), fallback(), btn({small: true, label: L('다시 불러오기', 'Try again'), on: {click: load}})]
          : [h('p', {class: 'small muted'}, L('화자 정보를 불러오는 중이에요…', 'Loading speakers…')), fallback()],
      state.busy ? h('p', {class: 'small muted', role: 'status'}, L('저장하는 중이에요…', 'Saving…')) : null,
      state.said ? h('p', {class: 'small spk-said'}, state.said) : null,
      h('p', {class: 'small muted'}, L('이름은 직접 확정한 것만 노트에 실명으로 들어가요. ‘(추정)’은 엔진 짐작이라 맞다고 눌러야 확정돼요. S1…은 자동으로 나눈 번호이고 실제 이름이 아니에요.',
        'Only names you confirm go into the note as real names. “(estimated)” is the engine\'s guess until you say it is right. S1… are automatic numbers, not names.')));
    syncEngineControls(node);
    if (key) {
      const target = Array.from(node.querySelectorAll('[data-act]')).find((el) => el.getAttribute('data-label') === key.label && el.getAttribute('data-act') === key.act);
      if (target && !target.disabled) target.focus();
    }
  }

  return {node, load, render, names, list: () => state.list};
}
