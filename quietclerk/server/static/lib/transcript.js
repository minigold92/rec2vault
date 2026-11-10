// Transcript card of the minutes screen (contract §10.8 B): the lines as the engine stores them (your edits and speaker
// merges applied), click or Enter to fix a line (Enter saves and moves on, Esc cancels), "restore original", find on the
// page with highlights, follow the line being played, and word-list suggestions from your edits. Line IDs never change,
// so the evidence links in the summary keep pointing at the same line.
import {flag, h, replace} from './dom.js';
import {L} from './i18n.js';
import {announce, banner, btn, chip, code} from './ui.js';
import {stamp} from './fmt.js';
import {readLines, saveLine, restoreLine, refusal} from './overrides.js';
import {cleanText, cutAt, findRanges, isComposing, oneLine, size} from './note-text.js';
import {createSuggestions} from './vocab-suggest.js';
import {syncEngineControls} from './shell.js';
import {live} from './live.js';

export const LINE_LIMIT = 2000;
export const FLASH_MS = 2600;   // how long a line a link pointed at stays marked

const lineProblem = (check) => (check.why === 'empty' ? L('내용이 있어야 해요. 처음 글로 돌리려면 ‘원문으로’를 눌러요.', 'A line can\'t be empty. To go back to the first text, use “Restore original”.')
  : check.why === 'chars' ? L('줄바꿈이나 보이지 않는 글자는 쓸 수 없어요. 그런 글자가 든 낱말을 지우고 다시 적어 주세요.', 'Line breaks and invisible characters aren\'t allowed. Delete the word that has one and type it again.')
    : L(`${check.n}자예요. ${LINE_LIMIT}자까지 쓸 수 있어요.`, `That is ${check.n} characters; the limit is ${LINE_LIMIT}.`));

const rowsFor = (text) => Math.min(10, Math.max(2, Math.ceil(size(text) / 40)));
const first = (li, selector) => li.querySelectorAll(selector)[0] || null;

// fallback: the lines in the page data [{id, start, end, speaker, text}], shown read-only until the engine's list arrives.
// names(): Map of confirmed speaker names. resummarize(): the page's "Re-summarize only".
export function createTranscript({jobId, fallback, names, isRunning, onRunning, resummarize}) {
  const state = {
    lines: fallback.map((t) => ({id: t.id, start: t.start, end: t.end, speaker: t.speaker, text: t.text, edited: false, original: t.text})),
    live: false, failure: null, problem: null, notice: false,
    edit: null, query: '', hits: [], byLine: new Map(), current: -1, follow: true, active: -1,
  };
  let rows = [];
  let mark = null;   // the line a link pointed at: {id, timer}
  const suggestions = createSuggestions();
  const slots = {head: h('div', {class: 'card-head'}), tools: h('div', {class: 'tx-find', role: 'search'}), hint: h('p', {class: 'small muted', id: 'tx-hint'}),
    top: h('div', {class: 'stack tight tx-top'}), list: h('ol', {class: 'tx', 'aria-labelledby': 'tx-h'}), bar: h('div', {class: 'stickybar'})};
  const count = h('span', {class: 'small muted num tx-count', role: 'status'});
  const finder = h('input', {class: 'input compact', type: 'search', id: 'tx-q', autocomplete: 'off', spellcheck: 'false',
    on: {input: (event) => search(event.target.value),
      keydown: (event) => {
        if (isComposing(event)) return;
        if (event.key === 'Enter') {
          event.preventDefault();
          step(event.shiftKey ? -1 : 1);
        } else if (event.key === 'Escape' && finder.value) {
          finder.value = '';
          search('');
        }
      }}});
  const node = h('section', {class: 'card', id: 'tx', 'aria-labelledby': 'tx-h'}, slots.head, slots.tools, slots.hint, slots.top, suggestions.node, slots.list, slots.bar);

  const editable = () => state.live && !isRunning() && !live.failed;
  const editing = (i) => !!state.edit && state.edit.index === i;

  // ---- one row: [time + id] [speaker] [text or editor]
  function speakerCell(line) {
    const name = names().get(line.speaker);
    return name ? [h('b', null, name), h('small', {class: 'muted'}, line.speaker)] : (line.speaker || '—');
  }

  function viewCell(line, i) {
    const at = state.byLine.get(i) || [];
    const now = state.hits[state.current];
    const body = cutAt(line.text, at).map((piece) => (piece.hit
      ? h('mark', {class: 'find-hit' + (now && now.line === i && now.k === piece.index ? ' on' : '')}, piece.text) : piece.text));
    const text = h('span', {class: 'tx-text', 'aria-describedby': state.live ? 'tx-hint' : null, 'aria-disabled': state.live && !editable() ? 'true' : null,
      role: state.live ? 'button' : null, tabindex: state.live ? '0' : null,
      on: state.live ? {
        click: () => {
          const picked = typeof getSelection === 'function' ? getSelection() : null;
          if (picked && !picked.isCollapsed && text.contains(picked.anchorNode)) return;   // a selection to copy, not a click to edit
          openEdit(i);
        },
        keydown: (event) => {
          if ((event.key === 'Enter' || event.key === ' ') && !isComposing(event) && !event.ctrlKey && !event.metaKey && !event.altKey) {
            event.preventDefault();
            openEdit(i);
          }
        }} : null}, body);
    return h('div', {class: 'tx-body'}, text,
      line.edited ? h('p', {class: 'tx-meta small'}, chip('line', '✎', L('고침', 'Edited')), ' ',
        btn({small: true, kind: 'ghost', engine: true, disabled: !editable(), label: L('원문으로', 'Restore original'), act: 'restore',
          aria: L(`${stamp(line.start)} 줄을 원문으로 되돌리기`, `Restore the original text of the line at ${stamp(line.start)}`), on: {click: () => restore(i)}})) : null,
      line.edited ? h('p', {class: 'tx-orig small muted'}, L('원문: ', 'Original: '), line.original) : null);
  }

  function editCell(line) {
    const edit = state.edit;
    const msgId = `tx-${line.id}-msg`;
    const area = h('textarea', {class: 'input tx-edit', rows: String(rowsFor(edit.draft)), value: edit.draft, readonly: edit.busy, spellcheck: 'false',
      'aria-label': L(`${stamp(line.start)} 줄 고치기`, `Edit the line at ${stamp(line.start)}`), 'aria-describedby': msgId,
      'aria-invalid': edit.error && edit.error.invalid ? 'true' : null, 'data-engine': '', on: {
        input: (event) => {
          const flat = oneLine(event.target.value);
          if (flat !== event.target.value) event.target.value = flat;
          edit.draft = flat;
          edit.error = null;
          area.setAttribute('rows', String(rowsFor(flat)));
          area.removeAttribute('aria-invalid');
          const said = document.getElementById(msgId);
          if (said) said.textContent = '';
        },
        keydown: (event) => {
          if (isComposing(event)) return;   // the Enter or Esc of a Korean composition belongs to the input method
          if (event.key === 'Enter') {
            event.preventDefault();         // a line has no line break
            if (!event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) commit(true);
          } else if (event.key === 'Escape') {
            event.preventDefault();
            cancel();
          }
        }}});
    const why = edit.error;
    return h('form', {class: 'tx-form', 'aria-label': L('줄 고치기', 'Edit line'), on: {submit: (event) => { event.preventDefault(); commit(false); }}},
      area,
      h('p', {class: 'err-text small', id: msgId, role: why ? 'alert' : null}, why ? [why.text, ' ', why.code ? code(why.code) : null] : null),
      h('div', {class: 'actions'},
        btn({type: 'submit', small: true, kind: 'primary', engine: true, disabled: edit.busy, label: edit.busy ? L('저장하는 중…', 'Saving…') : L('저장', 'Save')}),
        btn({small: true, disabled: edit.busy, label: L('취소', 'Cancel'), on: {click: cancel}})),
      h('p', {class: 'small muted tx-keys'}, L('Enter: 저장하고 다음 줄 · Esc: 취소', 'Enter: save and go to the next line · Esc: cancel')));
  }

  function buildRow(i) {
    const line = state.lines[i];
    const at = stamp(line.start);
    return [
      h('span', null, h('button', {class: 'ts', type: 'button', 'data-engine': '', 'data-seek': `${line.start}-${line.end}`, 'aria-label': L(`${at} 구간 듣기`, `Play from ${at}`)}, at),
        h('span', {class: 'id'}, line.id)),
      h('span', {class: 'sp'}, speakerCell(line)),
      editing(i) ? editCell(line) : viewCell(line, i),
    ];
  }

  function paintRow(i, quiet) {
    const row = rows[i];
    if (!row) return;
    const line = state.lines[i];
    row.li.replaceChildren(...buildRow(i));
    flag(row.li, 'edited', line.edited);
    flag(row.li, 'editing', editing(i));
    flag(row.li, 'target', !!mark && mark.id === line.id);
    if (!quiet) syncEngineControls(row.li);
  }

  function paintAll() {
    const was = state.active;
    rows = state.lines.map((line) => ({li: h('li', {id: line.id, 'data-start': line.start, 'data-end': line.end})}));
    rows.forEach((row, i) => paintRow(i, true));
    replace(slots.list, rows.map((row) => row.li));
    flag(slots.list, 'named', names().size > 0);
    state.active = was;
    if (rows[was]) flag(rows[was].li, 'on', true);
    syncEngineControls(slots.list);
  }

  // ---- the head: title, find box, hint, notices
  function paintHead() {
    const edited = state.lines.filter((line) => line.edited).length;
    replace(slots.head, h('h2', {id: 'tx-h'}, L('전체 대화록', 'Full transcript')),
      h('span', {class: 'small muted'}, L(`AI 받아쓰기 초안 · 발언 ${state.lines.length}개`, `AI transcript draft · ${state.lines.length} turns`),
        edited ? L(` · 고친 줄 ${edited}개`, ` · ${edited} edited`) : null));
    replace(slots.hint, isRunning() ? h('span', {class: 'why'}, L('이 회의를 처리하는 중이라 지금은 줄을 고칠 수 없어요. 끝나면 고칠 수 있어요.', 'This meeting is being processed, so lines can\'t be edited for now. You can edit them when it is done.'))
      : state.live ? L('줄을 누르거나 Enter를 누르면 고칠 수 있어요. Enter는 저장하고 다음 줄로, Esc는 취소예요.', 'Press a line, or Enter on it, to edit. Enter saves and goes to the next line; Esc cancels.')
        : L('지금은 대화록을 읽기만 할 수 있어요.', 'The transcript is read-only for now.'));
  }

  function paintTools() {
    finder.setAttribute('placeholder', L('대화록에서 찾기', 'Find in transcript'));
    finder.setAttribute('aria-label', L('대화록 안에서 찾기', 'Find in the transcript'));
    slots.tools.setAttribute('aria-label', L('대화록 찾기', 'Transcript search'));
    replace(slots.tools, finder,
      btn({small: true, icon: 'up', aria: L('이전 일치', 'Previous match'), act: 'prev', on: {click: () => step(-1)}}),
      btn({small: true, icon: 'down', aria: L('다음 일치', 'Next match'), act: 'next', on: {click: () => step(1)}}), count);
    paintCount();
  }

  function paintTop() {
    replace(slots.top,
      !state.live && state.failure ? banner('err', '!', [h('b', null, L('줄을 고칠 수 없어요.', 'Lines can\'t be edited.')), ' ', state.failure.text, ' ', code(state.failure.code)],
        [btn({small: true, label: L('다시 불러오기', 'Try again'), on: {click: refresh}})]) : null,
      state.problem && !state.problem.running ? banner('err', '!', [h('b', null, state.problem.text), ' ', code(state.problem.code)],
        state.problem.reload ? [btn({small: true, label: L('새로 고침', 'Reload'), on: {click: () => location.reload()}})] : null) : null);
    // The nudge stays at the bottom of the screen while the lines go by, as the save bar of the settings does.
    replace(slots.bar, state.notice ? banner('info', 'i', [h('b', null, L('노트의 전체 대화록에 바로 반영했어요.', 'The note\'s transcript has the change now.')), ' ',
      L('요약은 그대로예요. 요약에 반영하려면 ‘요약만 다시’를 눌러요.', 'The summary is unchanged. To bring it in line, press “Re-summarize only”.')],
    [btn({small: true, engine: true, label: L('요약만 다시', 'Re-summarize only'), on: {click: () => { state.notice = false; paintTop(); resummarize(); }}}),
      btn({small: true, kind: 'ghost', label: L('닫기', 'Dismiss'), on: {click: () => { state.notice = false; paintTop(); }}})]) : null);
    syncEngineControls(slots.top);
    syncEngineControls(slots.bar);
  }

  function paintCount() {
    count.textContent = !state.query.trim() ? '' : !state.hits.length ? L('일치하는 줄이 없어요', 'No match') : `${state.current + 1} / ${state.hits.length}`;
  }

  // ---- find on the page. `quiet`: the lines changed under an open search; keep the place, say nothing, do not scroll.
  function search(query, quiet) {
    const before = new Set(state.byLine.keys());
    const keep = state.current;
    state.query = query;
    state.byLine = new Map();
    state.hits = [];
    if (query.trim()) {
      state.lines.forEach((line, i) => {
        const found = findRanges(line.text, query);
        if (!found.length) return;
        state.byLine.set(i, found);
        found.forEach((_, k) => state.hits.push({line: i, k}));
      });
    }
    state.current = !state.hits.length ? -1 : quiet ? Math.min(Math.max(keep, 0), state.hits.length - 1) : 0;
    for (const i of new Set([...before, ...state.byLine.keys()])) if (!editing(i)) paintRow(i);
    paintCount();
    if (quiet || !query.trim()) return;
    announce(state.hits.length ? L(`${state.hits.length}곳에서 찾았어요`, `${state.hits.length} matches`) : L('일치하는 줄이 없어요', 'No match'));
    showCurrent();
  }

  function showCurrent() {
    const at = state.hits[state.current];
    if (!at || !rows[at.line]) return;
    reveal(rows[at.line].li.querySelectorAll('mark')[at.k] || rows[at.line].li);
  }

  function step(direction) {
    if (!state.hits.length) return;
    const was = state.hits[state.current];
    state.current = (state.current + direction + state.hits.length) % state.hits.length;
    const now = state.hits[state.current];
    if (!editing(was.line)) paintRow(was.line);
    if (now.line !== was.line && !editing(now.line)) paintRow(now.line);
    paintCount();
    announce(L(`${state.hits.length}곳 중 ${state.current + 1}번째`, `Match ${state.current + 1} of ${state.hits.length}`));
    showCurrent();
  }

  // ---- keeping a line in view
  const reduced = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  function covered() {   // on a narrow screen the player is stuck to the top and hides what scrolls under it
    const player = document.querySelector('.player-card');
    return player && typeof player.getBoundingClientRect === 'function' && typeof matchMedia === 'function' && matchMedia('(max-width: 1100px)').matches
      ? Math.max(0, player.getBoundingClientRect().bottom) : 0;
  }
  function reveal(el, smooth) {
    if (!el || typeof el.scrollIntoView !== 'function') return;
    const rect = typeof el.getBoundingClientRect === 'function' ? el.getBoundingClientRect() : null;
    const height = globalThis.innerHeight || 0;
    if (rect && height && rect.top >= covered() + 8 && rect.bottom <= height - 8) return;   // already in view
    el.scrollIntoView({block: 'center', behavior: smooth && !reduced() ? 'smooth' : 'auto'});
  }

  // The line being played: the last one that starts at or before `time` (lines are in time order). `idle`: nothing has been
  // played yet, so no line is "current". Follows it while playing, but never pulls the page away from a line being edited.
  function setPlayhead(time, {playing, idle}) {
    let lo = 0, hi = state.lines.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (state.lines[mid].start <= time) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    const index = found >= 0 && time < state.lines[found].end && !idle ? found : -1;
    if (index === state.active) return;
    if (rows[state.active]) flag(rows[state.active].li, 'on', false);
    state.active = index;
    if (!rows[index]) return;
    flag(rows[index].li, 'on', true);
    if (playing && state.follow && !state.edit && document.activeElement !== finder) reveal(rows[index].li, true);
  }

  // ---- editing
  function focusEditor() {
    if (!state.edit || !rows[state.edit.index]) return;
    const area = first(rows[state.edit.index].li, 'textarea');
    if (!area) return;
    area.focus();
    if (typeof area.setSelectionRange === 'function') area.setSelectionRange(area.value.length, area.value.length);
    reveal(rows[state.edit.index].li);
  }

  const focusLine = (i) => { const text = rows[i] && first(rows[i].li, '.tx-text'); if (text) text.focus(); };

  async function openEdit(i) {
    if (!state.live) return;
    if (!editable()) {
      announce(isRunning() ? L('처리 중이라 지금은 고칠 수 없어요.', 'This meeting is being processed, so it can\'t be edited now.') : L('엔진에 연결되면 고칠 수 있어요.', 'You can edit once the engine is connected.'));
      return;
    }
    if (editing(i)) { focusEditor(); return; }
    if (state.edit && !(await commit(false))) return;   // what was typed in the line left behind is saved first
    state.edit = {index: i, draft: state.lines[i].text, busy: false, error: null};
    paintRow(i);
    focusEditor();
  }

  function cancel() {
    if (!state.edit || state.edit.busy) return;
    const i = state.edit.index;
    state.edit = null;
    paintRow(i);
    focusLine(i);
  }

  // Save the open line (nothing is sent when it did not change) and close it; `advance` opens the next line.
  async function commit(advance) {
    const edit = state.edit;
    if (!edit || edit.busy) return false;
    const i = edit.index;
    const line = state.lines[i];
    const check = cleanText(edit.draft, LINE_LIMIT);
    if (!check.ok) {
      edit.error = {text: lineProblem(check), invalid: true};
      paintRow(i);
      focusEditor();
      return false;
    }
    const changed = check.text !== line.text;
    if (changed) {
      edit.busy = true;
      paintRow(i);
      try {
        if (line.edited && check.text === line.original) await restoreLine(jobId, line.id);   // back to the first text: no edit to keep
        else await saveLine(jobId, line.id, check.text);
      } catch (error) {
        edit.busy = false;
        edit.error = refusal(error);
        if (edit.error.running) onRunning();
        paintRow(i);
        focusEditor();
        return false;
      }
      line.text = check.text;
      line.edited = check.text !== line.original;
      state.notice = true;
      state.problem = null;
      announce(L('줄을 저장했어요. 노트에도 반영했어요.', 'Line saved. The note has it too.'));
    }
    state.edit = null;
    paintRow(i);
    if (changed) await refresh();
    if (advance && i + 1 < state.lines.length) await openEdit(i + 1);
    else focusLine(i);
    return true;
  }

  async function restore(i) {
    const line = state.lines[i];
    if (!line.edited || !editable()) return;
    state.problem = null;
    try {
      await restoreLine(jobId, line.id);
    } catch (error) {
      state.problem = refusal(error);
      if (state.problem.running) onRunning();
      paintTop();
      return;
    }
    line.text = line.original;
    line.edited = false;
    state.notice = true;
    announce(L('원문으로 되돌렸어요. 노트에도 반영했어요.', 'Restored the original. The note has it too.'));
    paintRow(i);
    await refresh();
    focusLine(i);
  }

  // ---- the engine's list
  const sig = (line) => [line.text, line.edited, line.original, line.speaker].join('\u0001');
  async function refresh() {
    try {
      const answer = await readLines(jobId);
      const old = state.lines;
      const wasLive = state.live;
      state.lines = answer.lines;
      state.live = true;
      state.failure = null;
      if (!wasLive || answer.lines.length !== old.length || !rows.length) paintAll();   // lines you can edit look different from the read-only ones
      else answer.lines.forEach((line, i) => { if (sig(line) !== sig(old[i]) && !editing(i)) paintRow(i); });
      suggestions.set(answer.vocabulary_suggestions);
    } catch (error) {
      if (!state.live) state.failure = refusal(error);
    }
    paintHead();
    paintTop();
    if (state.query.trim()) search(state.query, true);
  }

  // Drawn again when the display language or the job's state changes; what was typed stays.
  function render() {
    const focused = state.edit && rows[state.edit.index] && document.activeElement === first(rows[state.edit.index].li, 'textarea');
    paintHead();
    paintTools();
    paintTop();
    paintAll();
    suggestions.render();
    syncEngineControls(node);
    if (focused) focusEditor();
  }

  // Put the page on a line (a link from search, /notes/<job>#t12): scroll it into view and mark it for a moment. The mark
  // outlives a redraw of the rows (the lists arrive after the first draw) and runs out by itself. `flash: false` only scrolls.
  function showLine(id, {flash = true} = {}) {
    const at = state.lines.findIndex((line) => line.id === id);
    if (at < 0 || !rows[at]) return false;
    if (flash) {
      const clear = () => {
        const i = state.lines.findIndex((line) => line.id === (mark && mark.id));
        if (rows[i]) flag(rows[i].li, 'target', false);
      };
      if (mark) { clearTimeout(mark.timer); clear(); }
      mark = {id, timer: setTimeout(() => { clear(); mark = null; }, FLASH_MS)};
      flag(rows[at].li, 'target', true);
    }
    reveal(rows[at].li);
    return true;
  }

  paintHead();
  paintTools();
  paintTop();
  paintAll();
  suggestions.render();

  return {node, load: refresh, render, setPlayhead, showLine, setFollow: (on) => { state.follow = !!on; }, editing: () => !!state.edit};
}
