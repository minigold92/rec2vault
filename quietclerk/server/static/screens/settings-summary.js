// Summary layout, memo and daily-note inputs of the settings screen (contract §10.8 E, F, G): the rules the engine applies to
// them, the engine's own default headings, and the editor for the headings of each meeting type. The screen
// (settings.js) keeps the drafts, the save bar and the 400 display; this file only knows what is valid and how to edit a list.
import {h, icon, replace} from '../lib/dom.js';
import {L, getLang} from '../lib/i18n.js';
import {btn, chip, announce} from '../lib/ui.js';

export const SECTION_TYPES = [['meeting', '회의', 'Meeting'], ['status_update', '현황공유', 'Status update'], ['presentation', '발표회', 'Presentation'],
  ['lecture', '강의', 'Lecture'], ['one_on_one', '1:1', 'One-on-one'], ['brainstorm', '브레인스토밍', 'Brainstorm'], ['other', '기타', 'Other']];

// postprocess.TYPE_SECTIONS: the headings used when a type has no list of its own (the key summary always comes first and is not
// in the list). No API serves them, so the screen carries this copy; tests/test_server_screens.py compares it with TYPE_SECTIONS.
export const DEFAULT_SECTIONS = {
  ko: {meeting: ['안건별 논의', '결정 사항', '할 일', '미해결'], status_update: ['항목별 현황', '할 일'], presentation: ['발표별 정리', '결정 사항', '할 일'],
    lecture: ['주제별 내용', '핵심 개념·용어', '질의응답'], one_on_one: ['논의 주제', '요청·피드백', '할 일'], brainstorm: ['나온 아이디어', '고른 것·다음 단계'],
    other: ['주제별 내용', '할 일']},
  en: {meeting: ['Agenda', 'Decisions', 'Tasks', 'Open issues'], status_update: ['Status by topic', 'Tasks'], presentation: ['Presentations', 'Decisions', 'Tasks'],
    lecture: ['Topics', 'Key concepts', 'Questions and answers'], one_on_one: ['Topics', 'Requests and feedback', 'Tasks'], brainstorm: ['Ideas', 'Choices and next steps'],
    other: ['Topics', 'Tasks']},
};

export const MAX_ROWS = 12;
export const MAX_HEADING = 40;
export const MAX_INSTRUCTIONS = 500;
export const MEMO_RANGE = [5, 299];
const MAX_PATH = 4096;
const OTHER = /\p{C}/u;
const size = (text) => Array.from(text).length;

// ---- rules, the same the engine applies (config._validate, daily.template_path): null when the text is fine, else the reason.
export function headingIssue(text) {
  const t = String(text).trim();
  if (!t) return {why: 'empty'};
  if (OTHER.test(t)) return {why: 'chars'};
  return size(t) > MAX_HEADING ? {why: 'long', n: size(t), max: MAX_HEADING} : null;
}

// {type, row, why, n, max} for the first list that cannot be saved, else null. A type with no key uses the defaults.
export function sectionsIssue(dict) {
  const known = SECTION_TYPES.map(([type]) => type);
  for (const [type, rows] of Object.entries(dict || {})) {
    if (!known.includes(type) || !Array.isArray(rows) || rows.length < 1) return {type, row: -1, why: 'none'};
    if (rows.length > MAX_ROWS) return {type, row: -1, why: 'many'};
    for (let row = 0; row < rows.length; row += 1) {
      const issue = headingIssue(rows[row]);
      if (issue) return {type, row, ...issue};
    }
  }
  return null;
}

export const normalizeSections = (dict) => Object.fromEntries(Object.entries(dict || {}).map(([type, rows]) => [type, rows.map((row) => String(row).trim())]));

export function instructionsIssue(text) {
  const t = String(text).trim();
  if (OTHER.test(t)) return {why: 'chars'};
  return size(t) > MAX_INSTRUCTIONS ? {why: 'long', n: size(t), max: MAX_INSTRUCTIONS} : null;
}

// Only {date} may be in the braces, no backslash, no `..` step, and a Markdown file name; the rest (an Obsidian vault around the
// notes folder, no symbolic links) only the engine can see, so its answer is shown when it refuses.
export function dailyIssue(text) {
  const t = String(text).trim();
  if (!t) return null;
  if (OTHER.test(t)) return {why: 'chars'};
  if (size(t) > MAX_PATH) return {why: 'long', n: size(t), max: MAX_PATH};
  if (/[{}]/.test(t.split('{date}').join('')) || t.includes('\\')) return {why: 'braces'};
  if (t.replace(/\{date\}/g, '2000-01-01').split('/').includes('..')) return {why: 'dots'};
  return /[^/]\.md$/i.test(t) ? null : {why: 'ext'};
}

export const problemText = ({why, n, max}) => ({
  empty: () => L('비어 있어요.', 'It\'s empty.'),
  chars: () => L('제어문자나 보이지 않는 글자는 쓸 수 없어요. 줄바꿈도 안 돼요.', 'Control and invisible characters aren\'t allowed, and neither are line breaks.'),
  long: () => L(`${n}자예요. ${max}자까지 쓸 수 있어요.`, `That is ${n} characters; the limit is ${max}.`),
  none: () => L('제목이 하나는 있어야 해요. 기본 제목으로 돌리려면 ‘기본값으로 초기화’를 눌러요.', 'At least one heading is needed. To go back to the default, press ‘Reset to default’.'),
  many: () => L(`제목은 ${MAX_ROWS}개까지예요.`, `At most ${MAX_ROWS} headings.`),
  braces: () => L('{date}만 쓸 수 있어요. 다른 중괄호와 역슬래시(\\)는 안 돼요.', 'Only {date} may be in braces; other braces and backslashes (\\) aren\'t allowed.'),
  dots: () => L('‘..’ 없이 볼트 안의 경로를 적어 주세요.', 'Write a path inside the vault, without ‘..’.'),
  ext: () => L('.md로 끝나는 파일 경로를 적어 주세요. 예: Daily/{date}.md', 'Write a path to a Markdown file ending in .md, for example Daily/{date}.md'),
}[why]());

// The engine's reasons for a value it refuses, in words (anything else is shown as it came).
const REASONS = {
  'summary.sections': [
    [/existing meeting types/, () => L('알 수 없는 회의 유형이 있어요.', 'There is an unknown meeting type.')],
    [/1.12 headings/, () => L(`유형마다 제목은 1~${MAX_ROWS}개예요.`, `Each type takes 1–${MAX_ROWS} headings.`)],
    [/control characters/, () => L(`제목은 1~${MAX_HEADING}자, 제어문자 없이 적어 주세요.`, `Headings are 1–${MAX_HEADING} characters with no control characters.`)],
  ],
  'summary.instructions': [[/at most 500/, () => L(`${MAX_INSTRUCTIONS}자까지, 제어문자(줄바꿈 포함) 없이 적어 주세요.`, `Up to ${MAX_INSTRUCTIONS} characters, with no control characters or line breaks.`)]],
  'memo.min_sec': [[/5.299/, () => L(`${MEMO_RANGE[0]}~${MEMO_RANGE[1]}초 사이로 적어 주세요.`, `Enter ${MEMO_RANGE[0]}–${MEMO_RANGE[1]} seconds.`)],
    [/expected int/, () => L('숫자로 적어 주세요.', 'Enter a whole number.')]],
  'daily_note.path': [
    [/invalid daily-note path/, () => L('쓸 수 없는 글자가 있거나 너무 길어요.', 'It has characters that aren\'t allowed, or it is too long.')],
    [/only \{date\}/, () => problemText({why: 'braces'})],
    [/Markdown file without|parent traversal/, () => L('‘..’ 없이 .md 파일 경로를 적어 주세요.', 'Write a path to a .md file, without ‘..’.')],
    [/no enclosing Obsidian vault/, () => L('회의록 폴더가 Obsidian 볼트 안에 있어야 해요. 볼트는 .obsidian 폴더가 있는 폴더예요.', 'The notes folder has to be inside an Obsidian vault (a folder with a .obsidian folder).')],
    [/inside the output vault/, () => L('회의록 폴더가 속한 볼트 안의 경로여야 해요.', 'The path has to be inside the vault that holds the notes folder.')],
    [/symbolic/, () => L('경로나 그 위 폴더에 심볼릭 링크가 있어요. 링크가 없는 경로를 써 주세요.', 'The path, or a folder above it, is a symbolic link. Use a path without links.')],
    [/regular file/, () => L('그 경로에 파일이 아닌 것이 이미 있어요.', 'Something that is not a file already sits at that path.')],
  ],
};
export function serverReason(field, message) {
  const hit = (REASONS[field] || []).find(([pattern]) => pattern.test(message));
  return hit ? hit[1]() : message;
}

// ---- the editor: one <details> per meeting type. A type with no list of its own shows the engine's defaults (and offers to start
// a list of its own from them); a type with a list is edited in rows. `get()` is the current value of summary.sections (the
// draft or the saved one), `set(next)` makes `next` the draft; they are never given the same object twice, so nothing is
// changed in place.
export function sectionsEditor({get, set, locked, sync}) {
  const host = h('div', {class: 'sumtypes', role: 'group', 'aria-label': L('유형별 요약 제목', 'Summary headings by type')});
  const open = new Set();         // types left open (kept across redraws)
  const peeking = new Set();      // types whose defaults are shown next to their own list
  const touched = new WeakSet();  // row inputs that were left once: "empty" is said then, not while the row is still new
  let strict = false;             // after a refused save every row says what is wrong with it

  const own = (type) => {
    const dict = get();
    return Object.prototype.hasOwnProperty.call(dict, type) && Array.isArray(dict[type]) ? dict[type] : null;
  };
  const name = (type) => L(...SECTION_TYPES.find(([key]) => key === type).slice(1));
  const fallback = (type) => DEFAULT_SECTIONS[getLang()][type];
  const put = (type, rows) => set({...get(), [type]: rows});
  const drop = (type) => { const next = {...get()}; delete next[type]; set(next); };

  const peekText = (type) => { const rows = own(type); return (rows ? rows.map((row) => String(row).trim()).filter(Boolean) : fallback(type)).join(' · '); };

  function head(type) {
    const rows = own(type);
    return h('summary', {class: 'sumhead'}, h('b', {class: 'sumname'}, name(type)),
      rows ? chip('run', '✎', L('직접 정함', 'Custom')) : chip('line', null, L('기본', 'Default')), h('span', {class: 'sumpeek small muted'}, peekText(type)));
  }

  const fixedRow = () => h('p', {class: 'sumfixed'}, icon('lock'), h('b', null, L('핵심 요약', 'Key summary')), chip('lock', '⊘', L('고정', 'Fixed')),
    h('span', {class: 'small muted'}, L('늘 맨 앞에 나와요. 바꿀 수 없어요.', 'Always comes first and can\'t be changed.')));

  const defaultsView = (type) => h('dl', {class: 'sumdl small'},
    h('dt', null, L('한국어 회의록', 'Korean notes')), h('dd', null, DEFAULT_SECTIONS.ko[type].join(' · ')),
    h('dt', null, L('영어 회의록', 'English notes')), h('dd', null, DEFAULT_SECTIONS.en[type].join(' · ')));

  function row(type, rows, i, details) {
    const label = name(type);
    const said = h('p', {class: 'err-text small sumsaid', id: `sum-${type}-${i}-m`});
    const input = h('input', {class: 'input', value: rows[i], autocomplete: 'off', spellcheck: 'false', disabled: locked, 'data-engine': locked ? null : '',
      'aria-label': L(`${label} 제목 ${i + 1}`, `${label} heading ${i + 1}`), 'aria-describedby': said.id,
      on: {input: (event) => edit(type, i, event.target.value, input, said, details), blur: () => { touched.add(input); mark(input, said); }}});
    mark(input, said);
    const mover = (act, to, glyph, ko, en) => btn({small: true, kind: 'ghost', engine: true, icon: glyph, act, disabled: locked || to < 0 || to >= rows.length,
      aria: L(`${label} 제목 ${i + 1} ${ko}`, `${en} ${label} heading ${i + 1}`), on: {click: () => move(type, i, to - i, details)}});
    return h('li', {class: 'sumrow'}, h('span', {class: 'sumn', 'aria-hidden': 'true'}, String(i + 1)), input,
      h('span', {class: 'sumctl'}, mover('up', i - 1, 'up', '위로', 'Move up'), mover('down', i + 1, 'down', '아래로', 'Move down'),
        btn({small: true, kind: 'ghost', engine: true, icon: 'x', act: 'remove', disabled: locked || rows.length < 2,
          aria: L(`${label} 제목 ${i + 1} 삭제`, `Remove ${label} heading ${i + 1}`), on: {click: () => remove(type, i, details)}})), said);
  }

  // The red line under one row: refused text at once, "empty" once the row was left.
  function mark(input, said) {
    const issue = headingIssue(input.value);
    const show = issue && (issue.why !== 'empty' || strict || touched.has(input));
    said.textContent = show ? problemText(issue) : '';
    if (show) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
  }

  function body(type, details) {
    const rows = own(type);
    const label = name(type);
    if (!rows) {
      return h('div', {class: 'sumbody'}, fixedRow(),
        h('p', {class: 'small ink'}, L('지금은 기본 제목을 써요. 그대로 두거나, 이 목록을 바탕으로 직접 고쳐 쓸 수 있어요.', 'The default headings are used now. Keep them, or start your own list from them.')),
        defaultsView(type),
        h('div', {class: 'actions'}, btn({small: true, engine: true, act: 'own', disabled: locked, label: L('제목 직접 정하기', 'Set my own headings'),
          on: {click: () => { put(type, [...fallback(type)]); fill(details, type); focusRow(details, 0, 'input'); announce(L(`${label} 제목을 직접 고칠 수 있어요.`, `You can now edit the ${label} headings.`)); }}})));
    }
    const full = rows.length >= MAX_ROWS;
    const shown = peeking.has(type);
    const peek = btn({small: true, kind: 'ghost', act: 'peek', label: shown ? L('기본값 숨기기', 'Hide defaults') : L('기본값 보기', 'Show defaults'),
      on: {click: () => { if (peeking.has(type)) peeking.delete(type); else peeking.add(type); fill(details, type); focusAct(details, 'peek'); }}});
    peek.setAttribute('aria-expanded', String(shown));
    return h('div', {class: 'sumbody'}, fixedRow(),
      h('ol', {class: 'sumrows', 'aria-label': L(`${label} 요약 제목`, `${label} summary headings`)}, rows.map((_, i) => row(type, rows, i, details))),
      h('div', {class: 'row'}, btn({small: true, engine: true, icon: 'plus', act: 'add', disabled: locked || full, label: L('제목 추가', 'Add a heading'),
        on: {click: () => add(type, details)}}), h('span', {class: 'small muted num'}, `${rows.length} / ${MAX_ROWS}`),
      full ? h('span', {class: 'why'}, L(`${MAX_ROWS}개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_ROWS}). Remove one to add more.`)) : null),
      h('p', {class: 'small muted'}, L('고친 제목은 한국어·영어 회의록에 그대로 써요. 기본값으로 초기화하면 회의록 언어에 맞는 기본 제목으로 돌아가요.',
        'Your headings are used as written in Korean and English notes alike. Reset to get the default headings of each note language back.')),
      shown ? defaultsView(type) : null,
      h('div', {class: 'actions'}, peek, btn({small: true, engine: true, act: 'reset', disabled: locked, label: L('기본값으로 초기화', 'Reset to default'),
        on: {click: () => { drop(type); fill(details, type); focusAct(details, 'own'); announce(L(`${label}을(를) 기본 제목으로 돌렸어요.`, `${label} is back to the default headings.`)); }}})));
  }

  function focusAct(details, act) {
    const el = details.querySelector(`[data-act="${act}"]`);
    if (el && !el.disabled) el.focus();
  }

  function focusRow(details, i, what) {
    const rows = details.querySelectorAll('.sumrow');
    const target = rows[Math.min(Math.max(i, 0), rows.length - 1)];
    const el = target && (what === 'input' ? target.querySelector('input') : target.querySelector(`[data-act="${what}"]`));
    if (el && !el.disabled) el.focus();
    return !!el && !el.disabled;
  }

  function fill(details, type) {
    replace(details, head(type), body(type, details));
    sync(details);
  }

  function edit(type, i, text, input, said, details) {
    const rows = [...own(type)];
    rows[i] = text;
    put(type, rows);
    mark(input, said);
    details.querySelector('.sumpeek').textContent = peekText(type);
  }

  function add(type, details) {
    put(type, [...own(type), '']);
    fill(details, type);
    focusRow(details, own(type).length - 1, 'input');
    announce(L(`제목 칸을 더했어요 (${own(type).length}개)`, `Heading added (${own(type).length} in the list)`));
  }

  function remove(type, i, details) {
    put(type, own(type).filter((_, index) => index !== i));
    fill(details, type);
    focusRow(details, i, 'input');
    announce(L(`삭제했어요 (${own(type).length}개 남음)`, `Removed (${own(type).length} left)`));
  }

  function move(type, i, by, details) {
    const rows = [...own(type)];
    [rows[i], rows[i + by]] = [rows[i + by], rows[i]];
    put(type, rows);
    fill(details, type);
    if (!focusRow(details, i + by, by < 0 ? 'up' : 'down')) focusRow(details, i + by, by < 0 ? 'down' : 'up');   // the end of the list: the other arrow
    announce(L(`${i + by + 1}번째로 옮겼어요`, `Moved to position ${i + by + 1}`));
  }

  function view(type) {
    const details = h('details', {class: 'sumtype', 'data-type': type, open: open.has(type),
      on: {toggle: () => { if (details.open) open.add(type); else open.delete(type); }}});
    replace(details, head(type), body(type, details));
    return details;
  }

  function refresh(options = {}) {
    strict = !!options.strict;
    if (strict) {   // the types with something to fix are open, so the red lines are in view
      for (const [type] of SECTION_TYPES) if (own(type) && sectionsIssue({[type]: own(type)})) open.add(type);
    }
    replace(host, SECTION_TYPES.map(([type]) => view(type)));
    sync(host);
  }

  refresh();
  return {el: host, refresh};
}
