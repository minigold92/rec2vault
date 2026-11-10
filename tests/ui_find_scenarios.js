// ---- meeting search and summary layout scenarios (spliced into the harness; they use its fake DOM, fake fetch and helpers)
const sleep = (ms) => new Promise((resolve) => realSetTimeout(resolve, ms));
const answers = {};   // /api/search?... -> {status, body} | function | 'drop' (the network fails)
const baseFetch = globalThis.fetch;
globalThis.fetch = async (path, init = {}) => {
  if (!String(path).startsWith('/api/search')) return baseFetch(path, init);
  calls.push({method: init.method || 'GET', path, headers: {...(init.headers || {})}, body: undefined});
  const answer = answers[path] ?? answers['*'];
  if (answer === undefined) return reply(404, {error: 'not found'});
  const done = typeof answer === 'function' ? await answer(path) : answer;
  if (done === 'drop') throw new TypeError('network down');
  return reply(done.status ?? 200, done.body);
};
const searchPaths = () => calls.filter((c) => c.path.startsWith('/api/search')).map((c) => c.path);
const historyLog = [];
globalThis.history = {state: null, replaceState: (...args) => historyLog.push(args[2])};
FakeElement.prototype.select ||= function () {};
const keydown = (target, key, extra = {}) => { const event = {type: 'keydown', key, prevented: false, preventDefault() { this.prevented = true; }, ...extra}; target.dispatchEvent(event); return event; };

async function openNotes({lang, jobs, search = ''}) {
  globalThis.location.search = search;
  const w = await boot({lang, screen: 'notes'});
  routes['GET /api/jobs?limit=200'] = () => reply(200, {items: jobs, next_cursor: null});
  await (await load('screens/notes.js')).mount(w.shell);
  await settle();
  w.parts = w.shell.content.children;   // head, the box with its results, the list
  return w;
}
const resultsView = () => ({
  status: text(q('.find-status')), tone: q('.find-status').getAttribute('class'), invalid: q('#q').getAttribute('aria-invalid'),
  groups: qa('.find-group').map((g) => ({title: text(g.querySelector('.find-title')), when: text(g.querySelector('.find-gh .small')), href: g.querySelector('.find-title').getAttribute('href'),
    hits: g.querySelectorAll('li a.find-hit').map((a) => ({href: a.getAttribute('href'), where: text(a.querySelector('.find-where')), snip: text(a.querySelector('.find-snip')), marks: a.querySelectorAll('mark').map(text)}))})),
  more: q('[data-act="more"]') ? button(q('[data-act="more"]')) : null, none: text(q('.find-results .empty')), alert: text(q('.find-results .banner')),
  retry: q('[data-act="retry"]') ? button(q('[data-act="retry"]')) : null, busy: q('.find-results').getAttribute('aria-busy'), dim: (q('.find-results').getAttribute('class') || '').includes('is-busy'),
});

Object.assign(scenarios, {
  // Typing, pausing, Enter, one character, spaces, control characters, a slow answer overtaken by a newer one, the address.
  async findRules({lang, jobs, given}) {
    Object.assign(answers, given);
    const w = await openNotes({lang, jobs});
    const box = q('#q');
    const seen = {initial: {...resultsView(), listHidden: w.parts[2].hidden, rows: qa('.list .item').length, requests: searchPaths()}, label: text(q('label[for="q"]')), placeholder: box.getAttribute('placeholder')};
    const step = async (name, fn, wait = 480) => { const before = searchPaths().length; fn(); await sleep(wait); await settle(); seen[name] = {...resultsView(), listHidden: w.parts[2].hidden, requests: searchPaths().slice(before), url: historyLog.at(-1) ?? null}; };
    await step('oneChar', () => typeInto(box, '대'));
    await step('spaces', () => typeInto(box, '대   '));
    await step('control', () => typeInto(box, 'a\u0000b'));
    await step('invisible', () => typeInto(box, 'a\u200bb'));
    await step('tooLong', () => typeInto(box, 'x'.repeat(101)));
    typeInto(box, 'A'); await sleep(40); typeInto(box, 'AP'); await sleep(40); typeInto(box, 'API');
    seen.typing = {status: text(q('.find-status')), requests: searchPaths().length, listHidden: w.parts[2].hidden, live: q('.find-status').getAttribute('aria-live'), role: q('.find-status').getAttribute('role')};
    await sleep(480); await settle();
    seen.settled = {...resultsView(), requests: searchPaths(), url: historyLog.at(-1), listHidden: w.parts[2].hidden};
    await step('clear', () => typeInto(box, ''));
    await step('spacedPair', () => typeInto(box, '대 출'), 480);
    const form = q('form[role="search"]');
    typeInto(box, '연장');
    form.dispatchEvent({type: 'submit', preventDefault() {}});   // Enter: no waiting
    await settle();
    seen.enter = {requests: searchPaths().slice(-1), view: resultsView()};
    // a slow answer for 'slow' is overtaken by the newer 'fast': only the newer one is shown
    answers['/api/search?q=slow&limit=20&offset=0'] = async () => { await sleep(300); return {body: {items: [{job_id: 'old', title: 'OLD', date: '', kind: 'title', line_id: null, start: null, speaker: null, snippet: [{text: 'OLD', hit: true}]}], total: 1}}; };
    answers['/api/search?q=fast&limit=20&offset=0'] = {body: {items: [{job_id: 'new', title: 'NEW', date: '', kind: 'title', line_id: null, start: null, speaker: null, snippet: [{text: 'NEW', hit: true}]}], total: 1}};
    typeInto(box, 'slow'); await sleep(340); typeInto(box, 'fast'); await sleep(900); await settle();
    seen.overtaken = {titles: qa('.find-group .find-title').map(text), status: text(q('.find-status'))};
    return seen;
  },

  // Real answers of the engine: grouping, highlight, links, "more" (offset), nothing found, failures and retrying.
  async findResults({lang, jobs, given}) {
    Object.assign(answers, given);
    const w = await openNotes({lang, jobs});
    const box = q('#q');
    const ask = async (value, wait = 480) => { typeInto(box, value); await sleep(wait); await settle(); };
    const seen = {};
    await ask('API');
    seen.first = {...resultsView(), requests: searchPaths(), listHidden: w.parts[2].hidden};
    const more = q('[data-act="more"]');
    answers['/api/search?q=API&limit=20&offset=20'] = async () => { await sleep(120); return given['/api/search?q=API&limit=20&offset=20']; };
    more.click();
    seen.loading = {more: button(q('[data-act="more"]')), status: text(q('.find-status'))};
    await sleep(250); await settle();
    seen.second = {...resultsView(), requests: searchPaths().slice(-1), focus: document.activeElement.getAttribute('href')};
    await ask('ride pass');
    seen.ride = resultsView();
    await ask('zzzz');
    seen.none = {...resultsView(), listHidden: w.parts[2].hidden};
    answers['/api/search?q=boom&limit=20&offset=0'] = {status: 400, body: {error: 'q must contain 2..100 characters without controls'}};
    await ask('boom');
    seen.refused = resultsView();
    answers['/api/search?q=down&limit=20&offset=0'] = 'drop';
    await ask('down');
    seen.down = resultsView();
    answers['/api/search?q=down&limit=20&offset=0'] = given['/api/search?q=API&limit=20&offset=0'];
    q('[data-act="retry"]').click();
    await settle();
    seen.retried = {...resultsView(), requests: searchPaths().slice(-1)};
    answers['/api/search?q=half&limit=20&offset=0'] = given['/api/search?q=API&limit=20&offset=0'];
    await ask('half');
    answers['/api/search?q=half&limit=20&offset=20'] = 'drop';
    q('[data-act="more"]').click();
    await settle();
    seen.moreFailed = {more: button(q('[data-act="more"]')), said: text(q('.find-more .err-text')), groups: resultsView().groups.length};
    return seen;
  },

  // The box remembers its text in the address and reopens it (Back from a result).
  async findRestore({lang, jobs, given, search}) {
    Object.assign(answers, given);
    const w = await openNotes({lang, jobs, search});
    await sleep(60); await settle();
    return {value: q('#q').value, requests: searchPaths(), view: resultsView(), listHidden: w.parts[2].hidden, urls: historyLog.slice()};
  },

  // Text the engine sends is text: tags, quotes, javascript: addresses, bidi marks, 5000 characters, missing fields.
  async findHostile({lang, jobs}) {
    const evil = '<img src=x onerror=alert(1)><script>window.pwned=1</script> [x](https://evil.example) \u202egnp.exe\u202c \u2028\u0000';
    const hit = (extra) => ({job_id: 'j1', title: evil + 'T'.repeat(5000), date: '20261110-100000', kind: 'line', line_id: 't2', start: 61, speaker: '<b>S1</b>' + 'x'.repeat(80), snippet: [{text: evil, hit: false}, {text: '<i>hit</i>', hit: true}, {text: 'tail [t1, t2]', hit: false}], ...extra});
    answers['*'] = {body: {items: [hit({}), hit({line_id: 't3" onmouseover="alert(1)', kind: 'line'}), hit({line_id: 'javascript:alert(1)'}), hit({job_id: '"><script>window.pwned=1</script>', kind: 'summary', line_id: null}),
      hit({job_id: '../../etc/passwd', kind: 'mystery'}), hit({kind: 'title', start: 'NaN', speaker: null, snippet: 'oops'}), {job_id: 7}, null, 'text', {job_id: '', title: 'empty id'}], total: 'many'}};
    await openNotes({lang, jobs});
    typeInto(q('#q'), '<img src=x onerror=alert(1)>');
    await sleep(480); await settle();
    const area = q('.find');
    const links = qa('.find a').map((a) => a.getAttribute('href'));
    return {tags: [...new Set(area.querySelectorAll('*').map((el) => el.localName))].sort(), links, pwned: globalThis.pwned ?? null, requests: searchPaths(),
      groups: qa('.find-group').length, hits: qa('a.find-hit').length, longest: Math.max(...qa('.find-title').map((a) => text(a).length)),
      controls: /[\u0000-\u001f\u2028\u202a-\u202e]/.test(area.textContent), marks: qa('.find mark').map(text), speaker: text(q('.find-sp')), view: resultsView()};
  },

  // `/` and ⌘K: the dialog on any other screen, the box itself on Notes; not while typing; not on top of another dialog.
  async findKeys({lang, jobs, given}) {
    Object.assign(answers, given);
    const seen = {};
    const w = await boot({lang, screen: 'home'});
    seen.trigger = {side: text(q('.side .find-trigger')), keys: q('.find-trigger').getAttribute('aria-keyshortcuts'), mobile: q('.mobile-top .find-icon').getAttribute('aria-label')};
    const opener = q('.find-trigger');
    opener.focus();
    const slash = keydown(opener, '/');
    const dialog = () => document.querySelector('dialog');
    seen.slash = {prevented: slash.prevented, open: !!dialog() && dialog().open, label: dialog() && dialog().getAttribute('aria-label'), focusId: document.activeElement.getAttribute('id'),
      status: text(dialog().querySelector('.find-status')), foot: text(dialog().querySelector('.dlg-foot'))};
    typeInto(q('#fq'), 'API'); await sleep(480); await settle();
    seen.found = {groups: qa('dialog .find-group').length, requests: searchPaths().length, hrefs: qa('dialog a.find-hit').slice(0, 2).map((a) => a.getAttribute('href'))};
    const again = keydown(q('#fq'), '/');                    // typing a slash into the box
    const inBox = keydown(q('#fq'), 'k', {metaKey: true});    // ⌘K again: keeps the one dialog, selects the text
    seen.whileOpen = {slashPrevented: again.prevented, dialogs: qa('dialog').length, cmdK: inBox.prevented};
    const arrow = keydown(q('#fq'), 'ArrowDown');
    seen.arrows = {prevented: arrow.prevented, focus: document.activeElement.getAttribute('class')};
    keydown(document.activeElement, 'ArrowDown');
    seen.arrows.next = document.activeElement.getAttribute('class');
    keydown(document.activeElement, 'ArrowUp'); keydown(document.activeElement, 'ArrowUp');
    seen.arrows.back = document.activeElement.getAttribute('id');
    dialog().close();   // Esc closes a native dialog
    await settle();
    seen.closed = {dialogs: qa('dialog').length, focusBack: document.activeElement === opener};
    seen.noMod = [keydown(document.body, '/', {ctrlKey: true}).prevented, keydown(document.body, '/', {shiftKey: true}).prevented, keydown(document.body, '/', {isComposing: true}).prevented, keydown(document.body, 'k').prevented];
    const field = new FakeElement('input'); field.setAttribute('type', 'text'); document.body.append(field); field.focus();
    seen.typing = {slashInInput: keydown(field, '/').prevented, dialogs: qa('dialog').length};
    const box = new FakeElement('input'); box.setAttribute('type', 'checkbox'); document.body.append(box); box.focus();
    seen.checkbox = {prevented: keydown(box, '/').prevented, dialogs: qa('dialog').length};
    document.querySelector('dialog').close(); await settle();
    const ctrl = keydown(field, 'k', {ctrlKey: true});
    seen.ctrlK = {prevented: ctrl.prevented, dialogs: qa('dialog').length};
    document.querySelector('dialog').close(); await settle();
    const other = new FakeElement('dialog'); other.open = true; document.body.append(other);
    seen.onTopOfAnother = {slash: keydown(document.body, '/').prevented, dialogs: qa('dialog').length};
    other.remove();
    return seen;
  },
  async findKeysNotes({lang, jobs}) {
    const w = await openNotes({lang, jobs});
    const trigger = q('.find-trigger');
    trigger.focus();
    const slash = keydown(trigger, '/');
    const afterSlash = {prevented: slash.prevented, dialogs: qa('dialog').length, focusId: document.activeElement.getAttribute('id')};
    document.body.focus?.(); q('.find-trigger').focus();
    q('.find-trigger').click();
    return {afterSlash, clicked: {dialogs: qa('dialog').length, focusId: document.activeElement.getAttribute('id')}, box: q('#q') !== null};
  },
});

// ---- settings: summary layout, memo, daily note
const sumSec = (type) => q(`#s-sum details[data-type="${type}"]`);
const sumOpen = (type) => { const d = sumSec(type); d.open = true; d.dispatchEvent({type: 'toggle', bubbles: false}); return d; };
const sumView = () => qa('#s-sum details.sumtype').map((d) => ({type: d.getAttribute('data-type'), name: text(d.querySelector('.sumname')), chip: text(d.querySelector('.sumhead .chip')), peek: text(d.querySelector('.sumpeek')),
  open: !!d.open, rows: d.querySelectorAll('.sumrow input').map((i) => i.value), said: d.querySelectorAll('.sumsaid').map(text).filter(Boolean), defaults: text(d.querySelector('.sumdl')),
  count: text(d.querySelector('.sumbody .num')), buttons: d.querySelectorAll('.sumbody button').map((b) => `${b.getAttribute('data-act')}${b.disabled ? ':off' : ''}`)}));
const fieldView = (key) => { const f = q(`[data-key="${key}"]`); return {label: text(f.querySelector('label')), help: text(f.querySelector('.help')), tags: text(f.querySelector('.tags')), error: text(f.querySelector('.err-text'))}; };
const todayText = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };

Object.assign(scenarios, {
  // The rules, with no screen: the defaults and labels the engine has, and the verdict on a corpus of texts.
  async summaryRules({corpus}) {
    const m = await load('screens/settings-summary.js');
    const trimmed = (t) => String(t).trim();
    return {types: m.SECTION_TYPES, defaults: m.DEFAULT_SECTIONS, limits: [m.MAX_ROWS, m.MAX_HEADING, m.MAX_INSTRUCTIONS, ...m.MEMO_RANGE],
      headings: corpus.headings.map((t) => [t, trimmed(t), m.headingIssue(t)]), instructions: corpus.instructions.map((t) => [t, trimmed(t), m.instructionsIssue(t)]),
      daily: corpus.daily.map((t) => [t, trimmed(t), m.dailyIssue(t)])};
  },

  // Which texts the search box sends: Enter on each, then count the requests.
  async findCorpus({lang, jobs, corpus}) {
    answers['*'] = {body: {items: [], total: 0}};
    await openNotes({lang, jobs});
    const out = [];
    for (const text_ of corpus) {
      const before = searchPaths().length;
      typeInto(q('#q'), text_);
      q('form[role="search"]').dispatchEvent({type: 'submit', preventDefault() {}});
      await settle();
      out.push([text_, searchPaths().length > before]);
      typeInto(q('#q'), '');
    }
    return out;
  },

  // Headings, preference, memo and daily note: editing, the checks before sending, the bodies that are sent.
  async summarySave({lang, settings}) {
    await openSettings({lang, settings, providers: []});
    const seen = {nav: qa('nav a.chip').map(text), section: text(q('#s-sum h2')), intro: text(q('#s-sum .stack')), fields: [fieldView('summary.sections'), fieldView('summary.instructions')], initial: sumView(), bar: barText()};
    const meeting = sumOpen('meeting');
    seen.defaultView = sumView()[0];
    meeting.querySelector('[data-act="own"]').click();
    seen.own = {view: sumView()[0], bar: barText(), focus: document.activeElement.getAttribute('aria-label'), fixed: text(meeting.querySelector('.sumfixed'))};
    typeInto(meeting.querySelectorAll('.sumrow input')[1], '  결정과 근거  ');
    meeting.querySelector('[data-act="add"]').click();
    typeInto(meeting.querySelectorAll('.sumrow input')[4], '다음 주 일정');
    meeting.querySelectorAll('.sumrow [data-act="up"]')[4].click();
    meeting.querySelectorAll('.sumrow [data-act="remove"]')[0].click();
    seen.edited = {view: sumView()[0], bar: barText(), focus: document.activeElement.getAttribute('aria-label')};
    for (let i = 0; i < 8; i += 1) meeting.querySelector('[data-act="add"]').click();
    seen.full = sumView()[0];
    for (let i = 0; i < 8; i += 1) meeting.querySelectorAll('.sumrow [data-act="remove"]').at(-1).click();
    const last = sumView()[0];
    while (meeting.querySelectorAll('.sumrow').length > 1) meeting.querySelectorAll('.sumrow [data-act="remove"]').at(-1).click();
    seen.lastRow = sumView()[0];
    meeting.querySelector('[data-act="reset"]').click();
    seen.reset = {view: sumView()[0], bar: barText(), puts: savedBodies().length};
    meeting.querySelector('[data-act="own"]').click();
    typeInto(meeting.querySelectorAll('.sumrow input')[1], '결정과 근거');
    meeting.querySelector('[data-act="add"]').click();
    typeInto(meeting.querySelectorAll('.sumrow input')[4], '다음 주 일정');
    meeting.querySelectorAll('.sumrow [data-act="up"]')[4].click();
    meeting.querySelectorAll('.sumrow [data-act="down"]')[0].click();
    sumOpen('lecture').querySelector('[data-act="own"]').click();
    sumSec('lecture').querySelector('[data-act="peek"]').click();
    seen.peek = {view: sumView()[3], expanded: sumSec('lecture').querySelector('[data-act="peek"]').getAttribute('aria-expanded')};
    sumSec('lecture').querySelector('[data-act="reset"]').click();
    seen.afterReset = {lecture: sumView()[3], meeting: sumView()[0], bar: barText()};
    const emptyRow = sumOpen('other'); emptyRow.querySelector('[data-act="own"]').click();
    emptyRow.querySelector('[data-act="add"]').click();
    seen.newRow = sumView()[6];
    await save();
    seen.emptyBlocked = {puts: savedBodies().length, field: errorOf('f-sections-err'), banner: text(q('.banner.err')), view: sumView()[6], open: sumView().filter((v) => v.open).map((v) => v.type)};
    typeInto(sumSec('other').querySelectorAll('.sumrow input')[2], 'a\u200bb');
    typeInto(sumSec('other').querySelectorAll('.sumrow input')[0], 'x'.repeat(41));
    seen.badRows = sumView()[6];
    sumSec('other').querySelectorAll('.sumrow [data-act="remove"]').at(-1).click();
    sumSec('other').querySelectorAll('.sumrow [data-act="remove"]').at(-1).click();
    typeInto(sumSec('other').querySelectorAll('.sumrow input')[0], '잡담  ');

    const area = q('#f-instr');
    typeInto(area, '  결정 사항을 먼저, 숫자에는 단위를 붙여 주세요.  ');
    seen.instr = {count: text(q('#f-instr-n')), said: text(q('#f-instr-m')), bar: barText(), placeholder: area.getAttribute('placeholder')};
    const enter = keydown(area, 'Enter');
    typeInto(area, '첫 줄\n둘째 줄');
    seen.lines = {prevented: enter.prevented, value: area.value, note: text(q('#f-instr-note'))};
    typeInto(area, '가'.repeat(501));
    seen.long = {count: text(q('#f-instr-n')), said: text(q('#f-instr-m')), invalid: area.getAttribute('aria-invalid')};
    await save();
    seen.longBlocked = {puts: savedBodies().length, field: errorOf('f-instr-err')};
    const again = q('#f-instr');   // the refused save drew the screen again
    typeInto(again, '가'.repeat(500));
    seen.limit = {count: text(q('#f-instr-n')), said: text(q('#f-instr-m')), invalid: again.getAttribute('aria-invalid')};
    typeInto(again, '  결정 사항을 먼저, 숫자에는 단위를 붙여 주세요.  ');

    const box = q('#f-memo'), min = q('#f-memo-min');
    seen.memo = {field: fieldView('memo.enabled'), minField: fieldView('memo.min_sec'), off: {disabled: !!min.disabled, note: text(q('#s-rec .small.ink')), why: text(q('#f-memo-min').parentNode.parentNode.querySelector('.why'))}};
    box.checked = true; box.dispatchEvent({type: 'change'});
    seen.memo.on = {disabled: !!min.disabled, note: text(q('#s-rec .small.ink')), label: text(box.parentNode)};
    typeInto(min, '20');
    seen.memo.set = text(q('#s-rec .small.ink'));
    typeInto(min, '300');
    seen.memo.over = text(q('#s-rec .small.ink'));
    for (const bad of ['3', '400', 'x']) {
      typeInto(q('#f-memo-min'), bad);
      await save();
      seen.memo[`bad${bad}`] = {puts: savedBodies().length, error: errorOf('f-memo-min-err')};
    }
    typeInto(q('#f-memo-min'), '20');

    const daily = q('#f-daily');
    seen.daily = {field: fieldView('daily_note.path'), off: text(q('#f-daily-eg')), placeholder: daily.getAttribute('placeholder')};
    for (const [name, v] of [['dots', '../x.md'], ['braces', 'a{x}.md'], ['ext', 'Daily/{date}.txt'], ['slash', 'a\\b.md'], ['invisible', 'a\u200b.md']]) {
      typeInto(daily, v);
      seen.daily[name] = {said: text(q('#f-daily-m')), example: text(q('#f-daily-eg')), invalid: daily.getAttribute('aria-invalid')};
    }
    typeInto(daily, '  Daily/{date}.md ');
    seen.daily.ok = {said: text(q('#f-daily-m')), example: text(q('#f-daily-eg')), invalid: daily.getAttribute('aria-invalid'), today: todayText()};
    seen.beforeSave = {bar: barText()};
    await save();
    seen.saved = {bodies: savedBodies(), bar: barText(), banner: text(q('.banner.info')), view: sumView(), instr: q('#f-instr').value, daily: q('#f-daily').value, memo: [q('#f-memo').checked, q('#f-memo-min').value]};
    return seen;
  },

  // What the engine says when it refuses each of the four, in words. The answers are the real server's.
  async summaryRefused({lang, settings, refusals}) {
    const w = await openSettings({lang, settings, providers: []});
    const seen = {};
    const refuse = async (name, field, change) => {
      change();
      w.fail = {status: 400, body: refusals[name]};
      await save();
      seen[name] = {error: errorOf(field), banner: text(q('.banner.err')), bar: barText(), invalidSections: sumView().filter((v) => v.open).length};
      revertButton().click();
      await settle();
    };
    await refuse('sections', 'f-sections-err', () => { sumOpen('meeting').querySelector('[data-act="own"]').click(); });
    await refuse('instructions', 'f-instr-err', () => typeInto(q('#f-instr'), 'Decisions first'));
    await refuse('memo', 'f-memo-min-err', () => { const b = q('#f-memo'); b.checked = true; b.dispatchEvent({type: 'change'}); typeInto(q('#f-memo-min'), '20'); });
    await refuse('daily', 'f-daily-err', () => typeInto(q('#f-daily'), 'Daily/{date}.md'));
    w.fail = null;
    typeInto(q('#f-daily'), 'Daily/{date}.md');
    seen.edited = {bar: barText()};
    w.fail = {status: 400, body: refusals.daily};
    await save();
    typeInto(q('#f-daily'), 'Daily/{date}.md ');
    seen.staleLine = errorOf('f-daily-err');
    return seen;
  },

  // Values from settings.toml or the server are text: tags, bidi marks, a 5000-character heading, a missing key.
  async summaryHostile({lang, settings}) {
    await openSettings({lang, settings, providers: []});
    const used = () => [...new Set(q('#s-sum').querySelectorAll('*').map((el) => el.localName))].sort();
    const seen = {tags: used(), links: q('#s-sum').querySelectorAll('a').length, rows: sumView().filter((v) => v.rows.length).map((v) => ({type: v.type, rows: v.rows.map((r) => r.slice(0, 40)), said: v.said, peekLength: v.peek.length}))};
    seen.instr = {value: q('#f-instr').value.slice(0, 40), count: text(q('#f-instr-n')), said: text(q('#f-instr-m'))};
    seen.daily = {value: q('#f-daily').value, said: text(q('#f-daily-m')), example: text(q('#f-daily-eg')), tags: [...new Set(q('#f-daily').parentNode.querySelectorAll('*').map((el) => el.localName))].sort()};
    seen.pwned = globalThis.pwned ?? null;
    typeInto(sumSec('meeting').querySelectorAll('.sumrow input')[1], 'z'.repeat(41));   // a change that the engine would refuse
    await save();
    seen.blocked = {puts: savedBodies().length, banner: text(q('.banner.err')), sections: errorOf('f-sections-err')};
    return seen;
  },

  // No summary keys at all (an older engine): empty lists and defaults, and saving a change still sends only what changed.
  async summaryMissing({lang, settings}) {
    await openSettings({lang, settings, providers: []});
    const seen = {view: sumView().map((v) => [v.type, v.chip]), instr: q('#f-instr').value, daily: q('#f-daily').value, memo: [q('#f-memo').checked, q('#f-memo-min').value, !!q('#f-memo-min').disabled]};
    typeInto(q('#f-daily'), 'Daily/{date}.md');
    await save();
    seen.body = savedBodies();
    return seen;
  },
});
