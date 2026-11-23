// ---- extra receiving folders (contract 3.3 extra_inboxes, 9.2 backlog). Spliced into the harness like ui_find_scenarios.js.
async function openInboxSettings({lang, settings, identity, locked = []}) {
  const w = await boot({lang, screen: 'settings', first: BODIES.current});
  w.saved = {...settings};
  w.fail = null;
  const answer = () => reply(200, {effective: w.saved, file: {}, environment_keys: locked, restart_required: false});
  routes['GET /api/settings'] = answer;
  routes['PUT /api/settings'] = (call) => {
    if (w.fail) { const fail = w.fail; w.fail = null; return reply(fail.status, fail.body); }
    w.saved = {...w.saved, ...call.body};
    return answer();
  };
  routes['GET /api/providers'] = () => reply(200, {items: []});
  routes['GET /api/status'] = () => reply(200, identity);
  routes['GET /api/notes/migration'] = () => reply(200, {preview: {entries: [], conflicts: []}, migrated: false, task: null});
  await (await load('screens/settings.js')).mount(w.shell);
  await settle();
  return w;
}

const addFolder = (value) => {
  typeInto(q('#f-extra'), value);
  q('[data-key="extra_inboxes"] form.add-row').dispatchEvent({type: 'submit', preventDefault() {}});
};
const folderView = () => {
  const input = q('#f-extra');
  return {paths: qa('[data-key="extra_inboxes"] .term-t').map(text), marked: qa('[data-key="extra_inboxes"] .term.bad').map((li) => text(li.querySelector('.term-t'))),
    said: text(q('#f-extra-said')), invalid: input.getAttribute('aria-invalid'), box: input.value, missingNote: !!q('#f-extra-missing'),
    count: text(q('[data-key="extra_inboxes"] .num')), add: button(q('[data-key="extra_inboxes"] form.add-row button')), inputDisabled: !!input.disabled,
    errorLine: text(q('#f-extra-err')), bar: barText()};
};

Object.assign(scenarios, {
  async extraInboxes({lang, settings, identity, locked}) {
    const w = await openInboxSettings({lang, settings, identity, locked});
    const field = q('[data-key="extra_inboxes"]');
    const seen = {section: closestSection(field), label: text(field.querySelector('label')), tip: field.querySelector('label').getAttribute('title'), help: text(field.querySelector('.help')),
      tags: text(field.querySelector('.tags')), placeholder: q('#f-extra').getAttribute('placeholder'), initial: folderView(), lock: text(field.querySelector('.note'))};
    if (locked && locked.length) return seen;
    addFolder('  ~/rec/inbox-interpreter/  ');
    seen.added = {...folderView(), focus: document.activeElement.getAttribute('id')};
    for (const [name, value] of [['dup', '~/rec/inbox-interpreter'], ['relative', 'Recordings/Interpreter'], ['dots', '/a/../b'], ['primary', '/home/me/rec/inbox/'],
      ['empty', ''], ['chars', '/a\u202eb']]) {
      addFolder(value);
      seen[name] = folderView();
    }
    typeInto(q('#f-extra'), '');
    for (let i = 0; i < 6; i += 1) addFolder(`/data/more${i}`);
    seen.full = folderView();
    addFolder('/data/over');
    seen.over = folderView();
    qa('[data-key="extra_inboxes"] .term button')[1].click();
    seen.removed = {...folderView(), focus: document.activeElement.getAttribute('aria-label')};
    await save();
    seen.saved = {bodies: savedBodies(), view: folderView(), saveOff: saveButton().disabled, banner: text(q('.banner.info'))};
    // the engine refuses a list the page could not judge (a folder inside the data folder): its reason is shown, the draft stays
    addFolder('/home/me/QuietClerk/work');
    w.fail = {status: 400, body: {field: 'extra_inboxes', error: 'a receiving folder must not be the data folder or one of its engine folders: /home/me/QuietClerk/work'}};
    await save();
    seen.refused = {...folderView(), banner: text(q('.banner.err'))};
    typeInto(q('#f-extra'), '');
    qa('[data-key="extra_inboxes"] .term button').at(-1).click();
    seen.afterRefusal = folderView();
    addFolder('/tmp/again');
    revertButton().click();
    seen.reverted = folderView();
    return seen;
  },

  // The engine's reasons for a refused list, in words.
  async inboxReasons({lang, messages}) {
    await boot({lang});
    const {serverWhy} = await load('screens/settings-inboxes.js');
    return Object.fromEntries(Object.entries(messages).map(([name, message]) => [name, serverWhy(message)]));
  },

  // One request per receiving folder; the same name in two folders stays two rows.
  async backlogFolders({lang, backlog, settings, pick = [1, 2, 0]}) {
    const w = await boot({lang, screen: 'backlog', first: BODIES.current});
    routes['GET /api/backlog'] = () => reply(200, backlog);
    routes['GET /api/settings'] = () => reply(200, {effective: settings, file: {}, environment_keys: [], restart_required: false});
    routes['POST /api/backlog/request'] = () => reply(202, null);
    await (await load('screens/backlog.js')).mount(w.shell);
    await settle();
    const rows = () => qa('.list .item.sel').map((row) => ({name: text(row.querySelector('label')), meta: text(row.querySelector('.meta')), title: (row.querySelector('.meta span[title]') || {getAttribute: () => null}).getAttribute('title')}));
    const seen = {rows: rows()};
    const boxes = qa('input[data-pick="name"]');
    for (const i of pick) { boxes[i].checked = true; boxes[i].dispatchEvent({type: 'change'}); }
    seen.bar = text(q('.stickybar b'));
    qa('.stickybar button').find((b) => /받아서 처리하기|Fetch and process/.test(text(b))).click();
    await settle();
    seen.posts = calls.filter((c) => c.method === 'POST' && c.path === '/api/backlog/request').map((c) => c.body);
    return seen;
  },
});

function closestSection(el) {
  let node = el;
  while (node && node.localName !== 'section') node = node.parentNode;
  return node ? text(node.querySelector('h2')) : null;
}
