// ---- tool-block verification and long-waiting recordings (contract 8.5, 10.11). Spliced into the harness like ui_find_scenarios.js.
Object.assign(scenarios, {
  // Setup step 4 / settings: the Tool block row of the Codex card, before and after a manual test call.
  async toolBlock({lang, settings, providers, after}) {
    const w = await boot({lang, screen: 'setup', wizardStep: 4, first: BODIES.current});
    let current = providers;
    routes['GET /api/settings'] = () => reply(200, {effective: settings, file: {}, environment_keys: [], restart_required: false});
    routes['GET /api/providers'] = () => reply(200, {items: current});
    routes['POST /api/providers/codex/check'] = () => { current = after.providers; return reply(200, after.check); };
    await (await load('screens/setup-engines.js')).mount(w.shell);
    await settle();
    const card = () => qa('li.card').find((c) => text(c.querySelector('h3')) === 'Codex CLI');   // the screen redraws its cards
    const row = (label) => text(card().querySelectorAll('dd')[card().querySelectorAll('dt').findIndex((dt) => text(dt) === label)]);
    const names = lang === 'ko' ? ['도구 차단', '시험 호출'] : ['Tool block', 'Test call'];
    const seen = {before: row(names[0])};
    if (after) {
      card().querySelectorAll('button').find((b) => /시험 호출|Test call/.test(text(b))).click();
      await settle();
      seen.after = row(names[0]);
      seen.test = row(names[1]);
    }
    return seen;
  },

  // Home 'Needs a look': a long-waiting recording shows how long; short waits show nothing extra.
  async stuckHome({lang, jobs, settings}) {
    routes['GET /api/jobs?limit=200'] = () => reply(200, {items: jobs, next_cursor: null});
    routes['GET /api/settings'] = () => reply(200, {effective: settings, file: {}, environment_keys: [], restart_required: false});
    const w = await boot({lang, screen: 'home'});
    await (await load('screens/home.js')).mount(w.shell);
    await settle();
    const section = qa('section').find((s) => s.getAttribute('aria-labelledby') === 'att-h');
    return {cards: section ? section.querySelectorAll('article').map((a) => ({title: text(a.querySelector('h3')), text: text(a)})) : null};
  },
});
