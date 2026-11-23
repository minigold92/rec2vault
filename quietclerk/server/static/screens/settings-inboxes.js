// "Extra inboxes" of the settings screen (contract §3.3 extra_inboxes): more receiving folders read like the primary inbox, e.g.
// the Galaxy interpreter recordings (Recordings/Interpreter) in a second Syncthing folder. The screen (settings.js) keeps the
// draft, the save bar and the 400 display; this file knows the rules, edits the list and says which folders are not on this Mac.
// Typed paths are only ever put in the page as text.
import {h, replace} from '../lib/dom.js';
import {L} from '../lib/i18n.js';
import {btn, announce} from '../lib/ui.js';

export const MAX_EXTRA = 8;
const OTHER = /\p{C}/u;

// Written like the engine keeps it: no repeated or trailing slash.
export const tidy = (text) => String(text).trim().replace(/\/{2,}/g, '/').replace(/(.)\/+$/, '$1');

// null when the path can be added, else the reason. The same rules as config._extra_inboxes; the engine also compares the
// path with the data and notes folders (and where links point), which only it can see, so its refusal is shown too.
export function inboxProblem(text, list, primary) {
  if (!text) return {why: 'empty'};
  if (OTHER.test(text)) return {why: 'chars'};
  if (!/^(\/|~(\/|$))/.test(text)) return {why: 'relative'};
  if (text.split('/').includes('..')) return {why: 'dots'};
  if (text === tidy(primary || '')) return {why: 'primary'};
  if (list.includes(text)) return {why: 'dup'};
  if (list.length >= MAX_EXTRA) return {why: 'full'};
  return null;
}

export const problemText = ({why}) => ({
  empty: () => L('폴더 경로를 적어 주세요.', 'Type a folder path first.'),
  chars: () => L('제어문자나 보이지 않는 글자는 쓸 수 없어요.', 'Control and invisible characters aren\'t allowed.'),
  relative: () => L('/ 또는 ~/로 시작하는 전체 경로를 적어 주세요.', 'Write a full path starting with / or ~/.'),
  dots: () => L('경로에 ‘..’을 쓸 수 없어요.', 'A path can\'t contain ‘..’.'),
  primary: () => L('기본 받는 폴더와 같은 폴더예요.', 'That is the primary inbox itself.'),
  dup: () => L('이미 있어요.', 'Already in the list.'),
  full: () => L(`${MAX_EXTRA}개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_EXTRA}). Remove one to add more.`),
}[why]());

// The engine's reasons for a list it refuses, in words (anything else is shown as it came).
const SERVER_WHY = [
  [/absolute/, () => problemText({why: 'relative'})],
  [/\.\./, () => problemText({why: 'dots'})],
  [/at most/, () => problemText({why: 'full'})],
  [/duplicate/, () => problemText({why: 'dup'})],
  [/primary inbox/, () => problemText({why: 'primary'})],
  [/data folder|notes folder/, () => L('데이터 폴더 자체나 그 안의 엔진 폴더(archive·work 등), 회의록 폴더 안에는 둘 수 없어요. 다른 폴더를 써 주세요.',
    'It can\'t be the data folder itself, one of its engine folders (archive, work…) or inside the notes folder. Pick another folder.')],
  [/nonempty|list of paths/, () => problemText({why: 'empty'})],
];
export function serverWhy(message) {
  const hit = SERVER_WHY.find(([pattern]) => pattern.test(message));
  return hit ? hit[1]() : message;
}

// `get()` is the current list (the draft or the saved one), `set(next)` makes `next` the draft (never the same array twice),
// `primary()` the primary inbox path, `missing()` the saved folders the engine reported as not on this Mac, `locked()` whether
// QC_EXTRA_INBOXES fixes the list, `sync(el)` re-enables the engine controls inside `el`.
export function inboxesEditor({get, set, primary, missing, locked, sync, id}) {   // nothing is drawn until refresh()
  const host = h('div', {class: 'slot'});
  const typed = {add: '', said: null};   // the add box, and the last thing it said (a function: it follows the language)
  const list = () => (Array.isArray(get()) ? get().map(String) : []);

  function remove(index) {
    set(list().filter((_, i) => i !== index));
    typed.said = null;
    draw();
    const buttons = list().length ? host.querySelector('ul').querySelectorAll('button') : [];
    (buttons[index] || buttons[index - 1] || host.querySelector('input')).focus();
    announce(L(`삭제했어요 (${list().length}개 남음)`, `Removed (${list().length} left)`));
  }

  function add(raw) {
    const text = tidy(raw);
    const bad = inboxProblem(text, list(), primary());
    if (bad) {
      typed.add = raw;
      typed.said = () => problemText(bad);
    } else {
      set([...list(), text]);
      typed.add = '';
      typed.said = null;
    }
    draw();
    if (typed.said) announce(typed.said());
    else announce(L(`추가했어요 (${list().length}개)`, `Added (${list().length} in the list)`));
    host.querySelector('input').focus();
  }

  function row(path, index) {
    const gone = missing().includes(path);
    return h('li', {class: 'term' + (gone ? ' bad' : '')}, gone ? h('i', {'aria-hidden': 'true'}, '!') : null, h('span', {class: 'term-t'}, path),
      btn({small: true, kind: 'ghost', engine: true, icon: 'x', aria: L(`삭제: ${path}`, `Remove: ${path}`), disabled: locked(), on: {click: () => remove(index)}}));
  }

  function draw() {
    const paths = list();
    const full = paths.length >= MAX_EXTRA;
    const said = typed.said ? typed.said() : '';
    const input = h('input', {class: 'input', id, value: typed.add, placeholder: L('예: ~/rec/inbox-interpreter', 'e.g. ~/rec/inbox-interpreter'), disabled: locked(),
      autocomplete: 'off', spellcheck: 'false', 'aria-invalid': said ? 'true' : null, 'aria-describedby': `${id}-said`, 'data-engine': locked() ? null : '',
      on: {input: (event) => { typed.add = event.target.value; }}});
    const lost = paths.filter((path) => missing().includes(path));
    replace(host,
      paths.length ? h('ul', {class: 'terms', 'aria-label': L('추가 받는 폴더', 'Extra inboxes')}, paths.map(row))
        : h('p', {class: 'small muted'}, L('아직 없어요. 통역 앱 녹음처럼 다른 Syncthing 폴더로 받는 녹음을 읽으려면 여기에 폴더를 더해요.', 'None yet. Add a folder to read recordings that arrive in another Syncthing folder, such as the interpreter app\'s.')),
      lost.length ? h('p', {class: 'err-text small', id: `${id}-missing`}, L('! 표시한 폴더는 이 Mac에 아직 없어서 건너뛰어요. Syncthing으로 폴더를 공유하면 읽기 시작해요.', 'Folders marked ! are not on this Mac yet, so they are skipped. They are read once Syncthing shares them.')) : null,
      h('form', {class: 'add-row', 'aria-label': L('폴더 추가', 'Add a folder'), on: {submit: (event) => { event.preventDefault(); add(typed.add); }}},
        input, btn({type: 'submit', small: true, engine: true, icon: 'plus', disabled: full || locked(), label: L('추가', 'Add')})),
      h('p', {class: 'err-text small', id: `${id}-said`}, said),
      h('div', {class: 'row'}, h('span', {class: 'small muted num'}, `${paths.length} / ${MAX_EXTRA}`),
        full ? h('span', {class: 'why'}, L(`${MAX_EXTRA}개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.`, `The list is full (${MAX_EXTRA}). Remove one to add more.`)) : null),
      h('p', {class: 'small muted'}, L('각 폴더는 기본 받는 폴더와 같은 규칙으로 읽어요(바로 아래 .m4a만, 통화 녹음·숨김 파일 제외). 데이터 폴더·그 안의 엔진 폴더·회의록 폴더 안은 쓸 수 없고, 엔진이 폴더를 만들지는 않아요.',
        'Each folder is read by the same rules as the primary inbox (only .m4a files directly inside; call recordings and hidden files are skipped). It can\'t be the data folder, its engine folders or inside the notes folder, and the engine never creates it.')));
    sync(host);
  }

  return {el: host, refresh: draw, reset: () => { typed.add = ''; typed.said = null; }};
}
