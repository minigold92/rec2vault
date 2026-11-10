"""Minutes screen, second batch (contract 10.8 A, B, D): speaker panel, line editing, find on the page, export menu, word list suggestions.

Input policy and abnormal/malicious input evidence (typed text and fixtures only; no recording, no samples/ file, no operating vault):

| Input | Policy | Test |
|---|---|---|
| Speaker name typed in the panel (empty, spaces around, 41 characters, zero-width / bidi / control characters, markup, `$&`) | trimmed; 1-40 characters; no Unicode "other" character (the engine's own rule, compared with overrides.clean_string); a refused name is said beside the box and never sent; the body is `{name, confirmed: true}`; the name is text everywhere, and takes the place of S1 in the summary only where the note does (not when a letter touches it) | test_speaker_panel_names_merges_and_request_bodies, test_name_rule_search_and_input_rules_match_the_engine |
| The engine's guessed name `(추정)` | stays a guess until "That's right" confirms that very name; never written as a real name by the screen | test_speaker_panel_names_merges_and_request_bodies |
| Merge choice (itself, an already merged speaker, nothing chosen) | only the other speakers that are not merged away are offered; "Merge" is off until one is chosen; body `{from, into}`, undo `{from, into: null}` | test_speaker_panel_names_merges_and_request_bodies |
| 409 override_conflict (`job_running`, `processing_data_deleted`, `vault_migration`, `note_missing`, `job_changed`, `artifact_unavailable`, `merge_cycle`, an unknown reason), 400, a lost engine | `job_running` locks every control that writes (speaker panel, line editors, restore buttons) with its reason as a sentence, and unlocks when the job is done; every other refusal is told in words with its code, the draft stays, nothing is reloaded behind the user | test_speaker_panel_refusals_job_running_and_unreachable_engine, test_line_editor_keeps_the_draft_when_a_save_is_refused_or_slow |
| Line text typed or pasted (empty, line breaks, 2001 characters, zero-width / bidi / control characters, markup, `[x](url)`) | one line (a break becomes a space); trimmed; 1-2000 characters; no Unicode "other" character; a refused text is said under the editor and never sent; unchanged text sends nothing; the first words again send DELETE, not a PUT | test_line_editing_keys_ime_restore_and_limits |
| Keys in the line editor (Enter, Shift/Ctrl/Meta+Enter, Esc, Enter or Esc of an IME composition, Enter twice, clicking another line meanwhile) | Enter saves and opens the next line; modified Enter only keeps the line break out; Esc cancels; an IME's Enter and Esc (`isComposing`, or keyCode 229 as Safari sends it) are left alone; one request at a time, the editor read-only meanwhile; a dirty line is saved before another opens | test_line_editing_keys_ime_restore_and_limits, test_line_editor_keeps_the_draft_when_a_save_is_refused_or_slow |
| The find box (spacing, case, markup typed as the query, no match, an IME's Enter, Esc) | substring match ignoring case and spaces; marks are text nodes; next / previous wrap; an edit under an open search keeps the place | test_find_on_the_page |
| Export choices | the five formats the engine serves; names and times as `names=0/1&timestamps=0/1`; every URL part is encoded; a plain download link, nothing sent by script; off without the engine | test_export_menu_links_and_choices, test_every_export_format_the_screen_offers_is_one_the_engine_serves |
| Word list suggestions from the engine (identical, 41 characters, invisible character, already listed, same spelling with another correction, locked key, 400, no engine) | only valid pairs get a button; a press reads the current list and saves it again with the pair at the end; the others say why; a failed try can be repeated | test_word_list_suggestions_save_the_whole_list_with_the_pair_added |
| Text the engine or a speaker wrote (names, roles, lines, edits, suggestion words, `</script>`, `<img onerror>`, links, bidi) | text nodes and values only: no element beyond the ones the screen draws, no handler or style attribute, no link except to the engine's export | test_hostile_text_stays_text_on_the_minutes_screen |
| The address of the minutes page (`#t12` from search, `#sum`, `#tx`, `#spk`, `#t0`, `#t999`, `#T2`, markup or a quote after the hash, nothing) | only `#t<N>` of an existing line, `#sum`, `#tx`, `#spk` do anything: the line is scrolled to at the first draw and on hashchange, marked for 2.6 s (it stays marked through a redraw), and the section link is marked; every other address changes nothing; ids are looked up by equality, no selector is built from the address | test_a_link_from_search_opens_the_page_on_that_line |
| Review codes that "Redo from scratch" adds (`speaker_overrides_dropped`, `transcript_edits_dropped`) | a sentence in both languages, never the raw code | test_reasons_for_dropped_names_and_edits_are_in_words |

The tests run the real front-end modules in node against the fake DOM of test_server_screens.py. The answers of GET /speakers, /transcript and
/jobs/{id} are the real app's, from a meeting with three speakers, and are checked against schema.json; the writes are stubs that keep the state
as the engine does. Verification level: assumed answers in a fake DOM (no browser, no running engine, no recording). The real server with the
Korean demo meeting and headless Chromium were exercised by hand (docs/acceptance-v2.md).
"""
import itertools
import re
from contextlib import closing
from pathlib import Path  # noqa: F401

import pytest
from jsonschema import Draft202012Validator

from quietclerk import artifacts, store
# Fixtures and helpers of the other screen tests: the fake DOM harness, the app on a temporary root and the minutes page data.
from test_server_screens import (SCHEMA, STATIC, UPDATE_UI_HARNESS, api, harness, island, login, needs_node, note_job, run_ui, settings)  # noqa: F401


# ---- the minutes screen: speaker panel, line editing, find, export (contract §10.8 A, B, D) ------------------------------
# The real front-end modules run in node against the fake DOM above, plus the few things the minutes screen needs from it (closest,
# scrollIntoView, requestAnimationFrame). The answers of GET /speakers, /transcript and /jobs/{id} are the real app's, taken from a
# meeting with three speakers and checked against schema.json; the writes are small stubs that keep the state, as the engine does.
# Verification level: assumed answers in a fake DOM (no browser, no running engine, no recording).

NOTE_TURNS = [(0.0, 8.0, 'S1', '안녕하세요 책 마루 회의를 시작합니다'), (9.0, 21.0, 'S2', '오지안입니다 홈 화면을 바꾸려고 해요'),
              (22.0, 30.0, 'S1', '대출 연장 버튼을 올려요 GPU 서버도 봐요'), (31.0, 36.0, 'S3', '네 제가 측정하겠습니다'), (37.0, 40.0, 'S2', '알겠습니다 고마워요')]
NOTE_SUMMARY = '## 핵심 요약\n- S1이 S2에게 물었다 [t1, t2]\n- S1 asked S2 [t1, t2]\n## 할 일\n- [ ] S3 측정 [t4]\n'


def speaker_meeting(runtime, job_id, turns=NOTE_TURNS, roles=('진행', '디자인', None), summary=NOTE_SUMMARY):
    """A published job with three speakers (S2 has a name the engine guessed), written as the pipeline writes its run artifacts."""
    root = runtime.settings.root
    run_id = 'run-' + job_id
    with closing(store.connect(runtime.db)) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'talk.m4a', str(root / 'archive' / job_id / 'source.m4a'), 120)
        con.execute("INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at,finished_at) VALUES(?,?,'auto','{}','{}','done',1,2)", (run_id, job_id))
        con.execute("UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons='[]' WHERE job_id=?", (run_id, str(root / 'notes' / 'x.md'), job_id))
    directory = root / 'work' / job_id / 'runs' / run_id
    directory.mkdir(parents=True)
    labels = sorted({speaker for _, _, speaker, _ in turns})
    guess = {label: {'role': roles[i], 'name': '오지안' if label == 'S2' else None, 'name_id': 't2' if label == 'S2' else None, 'split_suspect': label == 'S1'}
             for i, label in enumerate(labels)}
    payloads = {'turns.json': [{'start': a, 'end': b, 'speaker': s, 'text': x} for a, b, s, x in turns],
                'corrected.json': {'texts': [t[3] for t in turns], 'notes': []},
                'classification.json': {'meta': {'title': 'T', 'type': 'meeting', 'division': 'work', 'speakers': guess}},
                'summary.json': {'text': summary}}
    for name, payload in payloads.items():
        part = directory / (name + '.part')
        artifacts.write_json(part, payload)
        artifacts.commit(directory / name, part, stage=name, run_id=run_id, inputs={}, params={})
    return job_id


@pytest.fixture
def note_ui(api):
    """build(**changes) -> the minutes page data and the real GET answers for a three-speaker meeting."""
    client, runtime, base = api
    login(client, runtime, base)
    counter = itertools.count(1)

    def build(**changes):
        job_id = speaker_meeting(runtime, **({'job_id': f'20261110-110000-{next(counter):08x}'} | changes))
        speakers, lines = client.get(f'/api/jobs/{job_id}/speakers').json(), client.get(f'/api/jobs/{job_id}/transcript').json()
        Draft202012Validator(SCHEMA | {'$ref': '#/$defs/Speakers'}).validate(speakers)
        Draft202012Validator(SCHEMA | {'$ref': '#/$defs/Transcript'}).validate(lines)
        return {'jobId': job_id, 'island': island(client.get('/notes/' + job_id).text), 'detail': client.get('/api/jobs/' + job_id).json(),
                'speakers': speakers['speakers'], 'lines': lines['lines']}
    return build


NOTE_UI_SCENARIOS = r'''// ---- the minutes screen (screens/note.js with lib/speakers.js, transcript.js, export-menu.js, vocab-suggest.js): scenarios
// added to the harness above. The answers of GET /speakers, /transcript and /jobs/{id} are the real app's (the test passes them in);
// the writes are answered by small stubs that keep the state, as the engine does.
const press = (el, key, extra = {}) => {
  const event = {type: 'keydown', key, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra};
  el.dispatchEvent(event);
  return event;
};
const typeInto2 = (el, value) => { el.value = value; el.dispatchEvent({type: 'input'}); };
const byId = (id) => document.getElementById(id);
const submit = (form) => form.dispatchEvent({type: 'submit', preventDefault() {}});
const writes = () => calls.filter((c) => c.method !== 'GET').map((c) => ({method: c.method, path: c.path.replace(/^\/api\/jobs\/[^/]+/, ''),
  body: c.body, csrf: c.headers['X-CSRF-Token'], key: c.headers['Idempotency-Key']}));
const tagsIn = (...roots) => [...new Set(roots.flatMap((root) => [root, ...root.querySelectorAll('*')]).map((el) => el.localName))].sort();

// The page with its real modules. What the small fake DOM lacks and the screen uses is added here.
async function openNote({lang = 'ko', island, jobId, detail, speakers, lines, suggestions = [], settings = {}, hash = '', holdTranscript = false}) {
  const w = await boot({lang, screen: 'note'});
  location.hash = hash;
  const listeners = {};
  globalThis.addEventListener = (type, fn) => { (listeners[type] ||= []).push(fn); };
  const timers = [];   // the highlight of a linked line (2600 ms): the test lets it run out by hand
  const harnessTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn, ms, ...rest) => (ms === 2600 ? (timers.push(fn), timers.length) : harnessTimeout(fn, ms, ...rest));
  let release = () => {};
  const held = holdTranscript ? new Promise((resolve) => { release = resolve; }) : null;
  FakeElement.prototype.closest = function (selector) {
    const parsed = compound(selector);
    for (let node = this; node; node = node.parentNode) if (node.nodeType === 1 && matches(node, parsed)) return node;
    return null;
  };
  const scrolls = [];
  FakeElement.prototype.scrollIntoView = function (options) { scrolls.push({id: this.getAttribute('id') || this.localName, ...options}); };
  const frames = [];
  globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
  const server = {speakers: structuredClone(speakers), lines: structuredClone(lines), suggestions: structuredClone(suggestions), job: structuredClone(detail),
    settings: structuredClone(settings)};
  routes[`GET /api/jobs/${jobId}`] = () => reply(200, structuredClone(server.job));   // a fresh copy each time, as parsed JSON is
  routes[`GET /api/jobs/${jobId}/speakers`] = () => reply(200, structuredClone({speakers: server.speakers}));
  routes[`GET /api/jobs/${jobId}/transcript`] = async () => { if (held) await held; return reply(200, structuredClone({lines: server.lines, vocabulary_suggestions: server.suggestions})); };
  routes[`GET /api/jobs/${jobId}/audio`] = () => ({status: 206, ok: true, headers: {get: () => null}});
  routes['GET /api/settings'] = () => reply(200, structuredClone({effective: server.settings, file: server.settings, environment_keys: [], restart_required: false}));
  const data = new FakeElement('script');
  data.setAttribute('id', 'qc-data');
  data.append(island);
  document.body.append(data);
  await (await load('screens/note.js')).mount({...w.shell, jobId});
  await settle();
  return {w, server, scrolls, frames, jobId, timers, release, fire: (type) => (listeners[type] || []).forEach((fn) => fn({type}))};
}

// Writes that behave like the engine: they change what the next GET answers.
function stubWrites(n) {
  const id = n.jobId;
  const find = (label) => n.server.speakers.find((s) => s.label === label);
  const home = Object.fromEntries(n.server.lines.map((l) => [l.id, l.speaker]));
  for (const s of n.server.speakers) {
    routes[`PUT /api/jobs/${id}/speakers/${s.label}`] = (call) => {
      Object.assign(find(s.label), {name: call.body.name, confirmed: call.body.confirmed, name_source: call.body.name ? 'user' : null});
      return reply(204);
    };
  }
  routes[`POST /api/jobs/${id}/speakers/merge`] = (call) => {
    find(call.body.from).merged_into = call.body.into;
    for (const l of n.server.lines) if (home[l.id] === call.body.from) l.speaker = call.body.into || home[l.id];
    return reply(204);
  };
  const edit = (line, value) => { const l = n.server.lines.find((x) => x.id === line); l.text = value; l.edited = value !== l.original; };
  for (const l of n.server.lines) {
    routes[`PUT /api/jobs/${id}/transcript/${l.id}`] = (call) => { edit(l.id, call.body.text); return reply(204); };
    routes[`DELETE /api/jobs/${id}/transcript/${l.id}`] = () => { edit(l.id, l.original); return reply(204); };
  }
}

const running = (n, on) => {
  n.server.job.job.status = on ? 'running' : 'done';
  n.server.job.job.updated_at += 1;
  n.w.es.send({...snapshot(), jobs: [{job_id: n.jobId, status: on ? 'running' : 'done', stage: null, updated_at: n.server.job.job.updated_at}]});
};

Object.assign(scenarios, {
  // The speaker panel: what each row shows, naming, "that's right", merge and undo, clearing, the body of every request.
  async noteSpeakers({lang, ...params}) {
    const n = await openNote({lang, ...params});
    stubWrites(n);
    const li = (label) => byId(`spk-${label}`);
    const row = (label) => ({text: text(li(label)), buttons: li(label).querySelectorAll('button').map(button),
      focus: document.activeElement.dataset ? `${document.activeElement.dataset.act}/${document.activeElement.dataset.label}` : null});
    const seen = {head: text(q('#spk .card-head')), initial: Object.fromEntries(['S1', 'S2', 'S3'].map((label) => [label, row(label)])),
      bars: qa('#spk .share i').length, lock: !!q('#spk .spk-lock'), nameInput: !!q('#spk-S1 input'), evidence: q('#spk-S2 .ts') && q('#spk-S2 .ts').getAttribute('data-seek'),
      listen: Object.fromEntries(['S1', 'S2', 'S3'].map((label) => [label, q(`#spk-${label} [data-act="listen"]`).getAttribute('data-seek')]))};
    // naming S1: the button is off until there is a name, the request is trimmed, the page shows the name at once
    seen.empty = button(q('#spk-S1 [data-act="confirm"]'));
    typeInto2(q('#spk-S1 input'), 'x'.repeat(41));
    seen.tooLong = {confirm: button(q('#spk-S1 [data-act="confirm"]')), said: text(q('#spk-S1 .err-text')), invalid: q('#spk-S1 input').getAttribute('aria-invalid')};
    typeInto2(q('#spk-S1 input'), 'a\u200bb');
    seen.invisible = {confirm: button(q('#spk-S1 [data-act="confirm"]')), said: text(q('#spk-S1 .err-text'))};
    typeInto2(q('#spk-S1 input'), '  한서윤  ');
    seen.typed = {confirm: button(q('#spk-S1 [data-act="confirm"]')), said: text(q('#spk-S1 .err-text'))};
    submit(q('#spk-S1 form'));
    await settle();
    seen.afterS1 = {row: row('S1'), writes: writes(), said: text(q('#spk .spk-said')), live: announced(), summary: text(q('#sum')), line: text(byId('t1').querySelector('.sp')),
      named: byId('t1').parentNode.getAttribute('class')};
    // "That's right" confirms what the engine guessed, under that very name
    q('#spk-S2 [data-act="agree"]').click();
    await settle();
    seen.afterS2 = {row: row('S2'), writes: writes().slice(-1)};
    // merge S3 into S2, then undo
    q('#spk-S3 [data-act="merge"]').click();
    const select = q('#spk-S3 select');
    seen.mergeForm = {options: select.querySelectorAll('option').map(text), go: button(q('#spk-S3 [data-act="go"]')), focus: document.activeElement === select};
    select.value = 'S2';
    select.dispatchEvent({type: 'change'});
    seen.mergeReady = button(q('#spk-S3 [data-act="go"]'));
    q('#spk-S3 [data-act="go"]').click();
    await settle();
    seen.afterMerge = {s3: row('S3'), s2: row('S2').text, writes: writes().slice(-1), lines: qa('#tx .tx li .sp').map(text), merged: !!q('#spk-S3 .share')};
    q('#spk-S3 [data-act="unmerge"]').click();
    await settle();
    seen.afterUndo = {s3: row('S3'), writes: writes().slice(-1), lines: qa('#tx .tx li .sp').map(text)};
    // a named speaker can be renamed (the box opens with the name, Cancel goes back) or have the name cleared
    q('#spk-S1 [data-act="rename"]').click();
    seen.renaming = {value: q('#spk-S1 input').value, buttons: li('S1').querySelectorAll('button').map(button), focus: document.activeElement === q('#spk-S1 input')};
    q('#spk-S1 [data-act="cancel"]').click();
    seen.cancelled = row('S1').text;
    q('#spk-S1 [data-act="rename"]').click();
    q('#spk-S1 [data-act="clear"]').click();
    await settle();
    seen.cleared = {row: row('S1'), writes: writes().slice(-1), line: text(byId('t1').querySelector('.sp'))};
    seen.allWrites = writes();
    return seen;
  },

  // 409 job_running locks the panel with its reason (and comes back when the job is done); every other refusal is told in words.
  async noteRefusals({lang, reasons, ...params}) {
    const n = await openNote({lang, ...params});
    stubWrites(n);
    const writeButtons = () => [...qa('#spk .spk button'), ...qa('#tx [data-act="restore"]')].filter((b) => b.dataset.act && b.dataset.act !== 'listen').map((b) => !!b.disabled);   // the buttons that change something
    const trySave = async (answer) => {
      routes[`PUT /api/jobs/${n.jobId}/speakers/S3`] = answer;
      typeInto2(q('#spk-S3 input'), '문태오');
      submit(q('#spk-S3 form'));
      await settle();
    };
    const seen = {before: {lock: !!q('#spk .spk-lock'), off: writeButtons().filter(Boolean).length}};
    seen.by = {};
    for (const reason of reasons) {
      await trySave(() => reply(409, {error: 'override_conflict', reason}));
      if (reason === 'job_running') continue;
      seen.by[reason] = {banner: text(q('#spk .banner.err .grow') || q('#spk .banner.err')), link: q('#spk .banner.err a') && q('#spk .banner.err a').getAttribute('href'),
        reload: !!q('#spk .banner.err button'), lock: !!q('#spk .spk-lock'), draft: q('#spk-S3 input').value};
    }
    await trySave(() => { throw new TypeError('down'); });
    seen.network = text(q('#spk .banner.err'));
    await trySave(() => reply(400, {error: 'text must have 1..40 characters'}));
    seen.bad = text(q('#spk .banner.err'));
    n.server.job.job.status = 'running';   // what the engine answers when it refuses with job_running
    await trySave(() => reply(409, {error: 'override_conflict', reason: 'job_running'}));
    await settle();
    seen.running = {lock: text(q('#spk .spk-lock')), off: writeButtons(), banner: !!q('#spk .banner.err'), draft: q('#spk-S3 input').value,
      hint: text(q('#tx-hint')), textDisabled: qa('.tx-text').map((t) => t.getAttribute('aria-disabled')), confirm: button(q('#spk-S3 [data-act="confirm"]'))};
    running(n, false);
    await settle();
    seen.done = {lock: !!q('#spk .spk-lock'), off: writeButtons().filter(Boolean).length, textDisabled: qa('.tx-text').map((t) => t.getAttribute('aria-disabled'))};
    return seen;
  },

  // Fixing lines: click or Enter opens, Enter saves and moves on, Esc cancels, an IME's Enter does nothing, restoring, limits.
  async noteLines({lang, ...params}) {
    const n = await openNote({lang, ...params});
    stubWrites(n);
    const area = (line) => byId(line).querySelector('textarea');
    const view = (line) => ({text: text(byId(line).querySelector('.tx-text')), editing: !!area(line), edited: !!byId(line).querySelector('.chip'), restore: !!byId(line).querySelector('[data-act="restore"]'),
      original: text(byId(line).querySelector('.tx-orig'))});
    const active = () => (document.activeElement.localName === 'textarea' ? `textarea@${document.activeElement.closest('li').getAttribute('id')}` : document.activeElement.getAttribute('class'));
    const seen = {head: text(q('#tx .card-head')), initial: {roles: qa('.tx-text[role="button"]').length, tabs: qa('.tx-text[tabindex="0"]').length, hint: text(q('#tx-hint')), lines: qa('#tx .tx li').length}};
    // a click opens the line
    byId('t2').querySelector('.tx-text').click();
    await settle();
    seen.opened = {t2: view('t2'), focus: active(), draft: area('t2').value, keys: text(q('#t2 .tx-keys')), rows: area('t2').getAttribute('rows')};
    // an IME's Enter (isComposing, or keyCode 229 after compositionend) only commits letters; Esc is the IME's too
    typeInto2(area('t2'), area('t2').value + ' 수정');
    const ime = [press(area('t2'), 'Enter', {isComposing: true}), press(area('t2'), 'Enter', {keyCode: 229}), press(area('t2'), 'Escape', {isComposing: true})];
    await settle();
    seen.ime = {prevented: ime.map((e) => e.defaultPrevented), writes: writes().length, editing: !!area('t2')};
    // a line break typed or pasted becomes a space
    typeInto2(area('t2'), '오지안입니다\n홈 화면을\r\n바꿔요');
    seen.oneLine = area('t2').value;
    typeInto2(area('t2'), '오지안입니다 홈 화면을 바꿔요 (고침)');
    // Enter saves and opens the next line
    const enter = press(area('t2'), 'Enter');
    await settle();
    seen.saved = {prevented: enter.defaultPrevented, t2: view('t2'), next: view('t3'), focus: active(), writes: writes(), notice: text(q('#tx .banner.info')), noticeButtons: qa('#tx .banner.info button').map(button),
      said: announced(), head: text(q('#tx .card-head')), gets: calls.filter((c) => c.path.endsWith('/transcript') && c.method === 'GET').length};
    // an unchanged line: Enter sends nothing and still moves on
    const before = writes().length;
    press(area('t3'), 'Enter');
    await settle();
    seen.unchanged = {writes: writes().length - before, next: view('t4'), focus: active(), t3: view('t3')};
    // Shift+Enter and Ctrl+Enter add no line break and do nothing else
    const shifted = [press(area('t4'), 'Enter', {shiftKey: true}), press(area('t4'), 'Enter', {ctrlKey: true}), press(area('t4'), 'Enter', {metaKey: true})];
    seen.modified = {prevented: shifted.map((e) => e.defaultPrevented), writes: writes().length - before, editing: !!area('t4')};
    // Esc cancels without sending and gives the keyboard back to the line
    typeInto2(area('t4'), '버릴 글');
    const escape = press(area('t4'), 'Escape');
    await settle();
    seen.escaped = {prevented: escape.defaultPrevented, t4: view('t4'), writes: writes().length - before, focus: active()};
    // the keyboard alone: Enter on the line opens it; the last line closes after saving
    press(byId('t5').querySelector('.tx-text'), 'Enter');
    await settle();
    seen.byKey = {t5: view('t5'), focus: active()};
    typeInto2(area('t5'), '알겠습니다 감사합니다');
    press(area('t5'), 'Enter');
    await settle();
    seen.last = {t5: view('t5'), editing: qa('#tx textarea').length, writes: writes().slice(-1)};
    // what is not allowed is said, not sent
    byId('t1').querySelector('.tx-text').click();
    await settle();
    const problems = {};
    const count = writes().length;
    for (const [name, value] of [['empty', '   '], ['long', '가'.repeat(2001)], ['invisible', 'a\u200bb'], ['control', 'a\u0007b']]) {
      typeInto2(area('t1'), value);
      press(area('t1'), 'Enter');
      await settle();
      problems[name] = {said: text(q('#t1 .err-text')), invalid: area('t1').getAttribute('aria-invalid'), editing: !!area('t1'), role: q('#t1 .err-text').getAttribute('role')};
    }
    typeInto2(area('t1'), '고치는 중');
    problems.cleared = {said: text(q('#t1 .err-text')), invalid: area('t1').getAttribute('aria-invalid')};
    seen.problems = {...problems, sent: writes().length - count};
    // clicking another line saves the one being edited first
    const lines = writes().length;
    byId('t3').querySelector('.tx-text').click();
    await settle();
    seen.switched = {writes: writes().slice(lines), t1: view('t1'), t3: view('t3')};
    // back to the first text: no edit is kept, the engine is told to restore (and a line that never changed sends nothing)
    byId('t5').querySelector('.tx-text').click();
    await settle();
    const sent = writes().length;
    typeInto2(area('t5'), n.server.lines[4].original);
    press(area('t5'), 'Enter');
    await settle();
    seen.same = {t5: view('t5'), writes: writes().slice(sent), t3: view('t3')};
    // restore original
    seen.restoreButton = {text: text(q('#t2 [data-act="restore"]')), label: q('#t2 [data-act="restore"]').getAttribute('aria-label'), original: view('t2').original};
    q('#t2 [data-act="restore"]').click();
    await settle();
    seen.restored = {t2: view('t2'), writes: writes().slice(-1), head: text(q('#tx .card-head'))};
    seen.writes = writes();
    return seen;
  },

  // A refused or slow save keeps what was typed; two Enters send one request; the page is not redrawn under the editor.
  async noteLineTrouble({lang, ...params}) {
    const n = await openNote({lang, ...params});
    stubWrites(n);
    const area = (line) => byId(line).querySelector('textarea');
    const seen = {};
    byId('t1').querySelector('.tx-text').click();
    await settle();
    typeInto2(area('t1'), '거절될 글');
    routes[`PUT /api/jobs/${n.jobId}/transcript/t1`] = () => reply(409, {error: 'override_conflict', reason: 'job_running'});
    n.server.job.job.status = 'running';
    press(area('t1'), 'Enter');
    await settle();
    seen.refused = {editing: !!area('t1'), draft: area('t1').value, said: text(q('#t1 .err-text')), alert: q('#t1 .err-text').getAttribute('role'), lock: text(q('#tx-hint')),
      focus: document.activeElement === area('t1'), saveButton: button(q('#t1 [type="submit"]'))};
    // while the job runs the editor stays; the lines cannot be opened
    seen.noOpen = {t2: (byId('t2').querySelector('.tx-text').click(), await settle(), !!area('t2'))};
    running(n, false);
    await settle();
    const before = writes().filter((w) => w.method === 'PUT').length;
    // a slow save: Enter twice, one request; the editor is read-only meanwhile
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    routes[`PUT /api/jobs/${n.jobId}/transcript/t1`] = async (call) => { await gate; n.server.lines[0].text = call.body.text; n.server.lines[0].edited = true; return reply(204); };
    typeInto2(area('t1'), '느린 저장');
    press(area('t1'), 'Enter');
    press(area('t1'), 'Enter');
    await settle();
    seen.slow = {readonly: area('t1').hasAttribute('readonly'), buttons: qa('#t1 button').map(button).filter((b) => b.act !== 'listen'), writes: writes().filter((w) => w.method === 'PUT').length - before};
    release();
    await settle();
    seen.after = {writes: writes().filter((w) => w.method === 'PUT').length - before, text: text(byId('t1').querySelector('.tx-text')), next: !!area('t2')};
    // an unrelated redraw (the job moves) leaves an open editor and its draft alone
    typeInto2(area('t2'), '쓰는 중인 글');
    const field = area('t2');
    running(n, true);
    await settle();
    running(n, false);
    await settle();
    seen.redraw = {same: area('t2') === field || area('t2').value === '쓰는 중인 글', draft: area('t2').value};
    // the engine cannot be reached: the editor says so and keeps the draft
    routes[`PUT /api/jobs/${n.jobId}/transcript/t2`] = () => { throw new TypeError('down'); };
    press(area('t2'), 'Enter');
    await settle();
    seen.offline = {said: text(q('#t2 .err-text')), draft: area('t2').value};
    seen.log = writes().map((w) => `${w.method} ${w.path}`);
    return seen;
  },

  // Find on the page: every match marked, the current one distinct, next / previous wrap, spacing and case do not matter.
  async noteFind({lang, queries, ...params}) {
    const n = await openNote({lang, ...params});
    const find = q('#tx-q');
    const state = () => ({count: text(q('.tx-count')), marks: qa('mark.find-hit').map((m) => ({text: text(m), on: /\bon\b/.test(m.getAttribute('class'))})),
      lines: qa('#tx .tx li').filter((li) => li.querySelector('mark')).map((li) => li.getAttribute('id'))});
    const seen = {by: {}};
    for (const query of queries) {
      typeInto2(find, query);
      seen.by[query] = state();
    }
    typeInto2(find, '요');
    seen.many = {first: state(), scrolls: n.scrolls.slice(-1)};
    const walk = [];
    for (let i = 0; i < 6; i += 1) {
      q('#tx [data-act="next"]').click();
      walk.push({count: text(q('.tx-count')), on: qa('mark.find-hit').filter((m) => /\bon\b/.test(m.getAttribute('class'))).map((m) => m.parentNode.parentNode.parentNode.getAttribute('id'))});
    }
    seen.next = walk;
    const back = [];
    for (let i = 0; i < 2; i += 1) {
      q('#tx [data-act="prev"]').click();
      back.push(text(q('.tx-count')));
    }
    seen.prev = back;
    // Enter in the box: next; Shift+Enter: previous; an IME's Enter does nothing; Esc clears
    const enter = [press(find, 'Enter'), press(find, 'Enter', {shiftKey: true}), press(find, 'Enter', {isComposing: true})];
    seen.keys = {count: text(q('.tx-count')), prevented: enter.map((e) => e.defaultPrevented), announced: announced()};
    press(find, 'Escape');
    seen.cleared = {value: find.value, state: state()};
    typeInto2(find, 'zzz');
    seen.none = {state: state(), live: announced()};
    // an edit under an open search keeps the place and sends the page nowhere
    typeInto2(find, '요');
    n.scrolls.length = 0;
    stubWrites(n);
    byId('t2').querySelector('.tx-text').click();
    await settle();
    typeInto2(byId('t2').querySelector('textarea'), '요요 요');
    press(byId('t2').querySelector('textarea'), 'Escape');
    seen.editing = {count: text(q('.tx-count')), scrolls: n.scrolls.filter((s) => s.id !== 't2' && s.localName !== 'textarea').length};
    return seen;
  },

  // The export menu: five formats, the two choices in every link, Escape closes it, nothing is sent from the page.
  async noteExport({lang, ...params}) {
    const n = await openNote({lang, ...params});
    const links = () => qa('#export-panel a.export-item').map((a) => ({format: a.getAttribute('data-format'), href: a.getAttribute('href'), download: a.hasAttribute('download'), label: a.getAttribute('aria-label'), text: text(a)}));
    const toggle = q('[data-act="export"]');
    const seen = {closed: {hidden: q('#export-panel').hidden, expanded: toggle.getAttribute('aria-expanded'), controls: toggle.getAttribute('aria-controls'), label: text(toggle)}};
    toggle.click();
    seen.open = {hidden: q('#export-panel').hidden, expanded: toggle.getAttribute('aria-expanded'), focus: document.activeElement.getAttribute('data-format'), links: links(),
      options: qa('#export-panel label.check').map((l) => ({text: text(l), checked: l.querySelector('input').checked})), head: text(q('#export-h')),
      note: q('#export-panel').children.filter((el) => el.localName === 'p').map(text).join(' ')};
    const boxes = qa('#export-panel input[type="checkbox"]');
    boxes[0].checked = false;
    boxes[0].dispatchEvent({type: 'change'});
    seen.noNames = links().map((l) => l.href.split('?')[1]);
    boxes[1].checked = false;
    boxes[1].dispatchEvent({type: 'change'});
    seen.neither = links().map((l) => l.href.split('?')[1]);
    boxes[0].checked = true;
    boxes[0].dispatchEvent({type: 'change'});
    seen.namesOnly = links().map((l) => l.href.split('?')[1]);
    // a click on a link only starts the download (the link is a plain GET, no script sends anything)
    const click = {type: 'click', defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }};
    q('#export-panel [data-format="docx"]').dispatchEvent(click);
    seen.clicked = {prevented: click.defaultPrevented, announced: announced(), calls: calls.filter((c) => /export/.test(c.path)).length};
    // the engine is gone: the link does not go anywhere
    n.w.es.drop();
    await settle();
    const offline = {type: 'click', defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }};
    q('#export-panel [data-format="srt"]').dispatchEvent(offline);
    seen.offline = {prevented: offline.defaultPrevented, toggle: button(toggle)};
    n.w.es.open();
    await settle();
    const esc = press(q('#export-panel'), 'Escape');
    seen.escaped = {prevented: esc.defaultPrevented, hidden: q('#export-panel').hidden, expanded: toggle.getAttribute('aria-expanded'), focus: document.activeElement === toggle};
    const exportModule = await load('lib/export-menu.js');
    seen.url = [exportModule.exportUrl('a b/c', 'docx', {names: false}), exportModule.exportUrl('x', 'srt'), exportModule.exportUrl('../x', 'md', {timestamps: false}),
      exportModule.exportUrl('x', 'a&b=1', {})];
    seen.formats = exportModule.FORMATS.map((f) => [f.id, f.name, f.ext]);
    n.w.es.drop();
    return seen;
  },

  // Word list suggestions from edits: a press reads the current list and saves it again with the pair at the end.
  async noteVocab({lang, pairs, settings, ...params}) {
    const n = await openNote({lang, suggestions: pairs, settings, ...params});
    const items = () => qa('#tx .sugg-item').map((li) => ({text: text(li), button: li.querySelector('button') ? button(li.querySelector('button')) : null,
      label: li.querySelector('button') && li.querySelector('button').getAttribute('aria-label')}));
    const sugg = q('#tx .sugg');
    const more = () => sugg.children.find((el) => el.localName === 'button');
    const next = (from) => qa('#tx .sugg-item').find((li) => (from ? text(li).startsWith(from) : li.querySelector('button'))).querySelector('button');
    const seen = {head: text(q('#tx .sugg h3')), help: text(sugg.children.find((el) => el.localName === 'p')), hidden: sugg.hidden, initial: items(), more: text(more())};
    const put = (call) => { n.server.settings = {...n.server.settings, ...call.body}; return reply(200, {effective: n.server.settings, file: {}, environment_keys: [], restart_required: false}); };
    routes['PUT /api/settings'] = put;
    const reads = () => calls.filter((c) => c.method === 'GET' && c.path === '/api/settings').length;
    const had = reads();
    next().click();   // 1: goes in
    await settle();
    seen.added = {items: items(), gets: reads() - had, live: announced()};
    next().click();   // 2: its wrong spelling already has another correction in the list
    await settle();
    seen.clash = items()[1];
    more().click();
    seen.expanded = {count: qa('#tx .sugg-item').length, more: !!more()};
    routes['PUT /api/settings'] = () => reply(409, {field: 'vocabulary.replace', error: 'locked setting'});
    next('둘').click();   // 3: the key is set by an environment variable
    await settle();
    seen.locked = items()[5];
    routes['PUT /api/settings'] = () => reply(400, {field: 'vocabulary.replace', error: 'conflicting vocabulary.replace entries'});
    next('셋').click();   // 4: the server refuses the list
    await settle();
    seen.refused = items()[6];
    routes['PUT /api/settings'] = () => { throw new TypeError('down'); };
    next('넷').click();   // 5: the engine cannot be reached
    await settle();
    seen.offline = items()[7];
    seen.left = items().filter((item) => item.button).length;
    seen.puts = calls.filter((c) => c.method === 'PUT').map((c) => c.body);
    seen.saved = n.server.settings;
    return seen;
  },

  // Everything the engine or a speaker wrote is text: names, roles, lines, edits, suggestions, a search for markup.
  async noteHostile({lang, ...params}) {
    const n = await openNote({lang, ...params});
    stubWrites(n);
    const seen = {tags: {initial: tagsIn(q('#spk'), q('#tx'), q('#sum'))}};
    typeInto2(q('#tx-q'), '<img');
    seen.find = {count: text(q('.tx-count')), marks: qa('mark.find-hit').map(text), tags: tagsIn(q('#tx'))};
    qa('.tx-text')[0].click();
    await settle();
    seen.editor = {value: qa('#tx textarea')[0].value, tags: tagsIn(q('#tx'))};
    typeInto2(qa('#tx textarea')[0], '<script>window.pwned=2</script> [x](https://evil.example) \u202egnp.exe');
    press(qa('#tx textarea')[0], 'Enter');
    await settle();
    seen.saved = {write: writes().slice(-1), tags: tagsIn(q('#tx'), q('#spk')), text: text(qa('.tx-text')[0]).slice(0, 80)};
    typeInto2(q('#spk-S1 input'), '<b onmouseover=alert(3)>이름</b>');
    submit(q('#spk-S1 form'));
    await settle();
    seen.named = {write: writes().slice(-1), tags: tagsIn(q('#spk'), q('#tx'), q('#sum')), summary: text(q('#sum')).slice(0, 200), speakerCell: text(byId('t1').querySelector('.sp'))};
    for (const button of qa('#tx .sugg-item button')) button.click();
    await settle();
    const every = [q('#spk'), q('#tx'), q('#sum'), q('#export-panel')].flatMap((root) => [root, ...root.querySelectorAll('*')]);
    seen.final = {tags: tagsIn(q('#spk'), q('#tx'), q('#sum'), q('#export-panel')), links: qa('#tx a, #spk a').length, pwned: globalThis.pwned ?? null, texts: qa('#spk .spk-nm, #spk .spk-role').map(text).slice(0, 6),
      attributes: [...new Set(every.flatMap((el) => [...el.attrs.keys()]))].sort(), hrefs: [...new Set(every.filter((el) => el.hasAttribute('href')).map((el) => el.getAttribute('href').replace(/[?].*/, '')))]};
    return seen;
  },

  // Playback: the speed lasts (also after load()), a voice sample plays its stretch and stops, the current line is followed.
  async notePlayback({lang, ...params}) {
    const n = await openNote({lang, ...params});
    const audio = q('audio');
    Object.assign(audio, {paused: true, currentTime: 0, readyState: 4, played: [], play() { this.paused = false; this.played.push(this.currentTime); this.dispatchEvent({type: 'play'}); return Promise.resolve(); },
      pause() { this.paused = true; this.dispatchEvent({type: 'pause'}); }, load() { this.playbackRate = this.defaultPlaybackRate; }});
    const frame = () => { const run = n.frames.splice(0); for (const fn of run) fn(); };
    const speed = q('#pl-speed');
    const seen = {speeds: speed.querySelectorAll('option').map(text), value: speed.value, follow: q('#pl-follow').checked, label: text(q('#pl-speed').parentNode)};
    speed.value = '1.5';
    speed.dispatchEvent({type: 'change'});
    seen.rate = {rate: audio.playbackRate, def: audio.defaultPlaybackRate, stored: sessionStorage.getItem('qc.note.speed')};
    // a voice sample (S3: 31.00-36.00): it starts there, follows the lines, stops at the end
    const listen = q('#spk-S3 [data-act="listen"]');
    seen.sample = listen.getAttribute('data-seek');
    audio.readyState = 0;
    listen.click();
    audio.dispatchEvent({type: 'loadedmetadata'});
    await settle();
    seen.started = {time: audio.currentTime, rate: audio.playbackRate, playing: /\bplaying\b/.test(listen.getAttribute('class')), played: audio.played.length};
    n.scrolls.length = 0;
    audio.currentTime = 32;
    frame();
    seen.following = {on: qa('#tx .tx li').filter((li) => /\bon\b/.test(li.getAttribute('class'))).map((li) => li.getAttribute('id')), scrolls: n.scrolls.slice()};
    audio.currentTime = 36.5;
    frame();
    seen.stopped = {paused: audio.paused, playing: /\bplaying\b/.test(listen.getAttribute('class') || ''), on: qa('#tx .tx li').filter((li) => /\bon\b/.test(li.getAttribute('class') || '')).map((li) => li.getAttribute('id'))};
    // following can be switched off, and does not pull the page away from an open editor
    q('#pl-follow').checked = false;
    q('#pl-follow').dispatchEvent({type: 'change'});
    n.scrolls.length = 0;
    audio.paused = false;
    audio.currentTime = 1;
    audio.dispatchEvent({type: 'seeked'});
    seen.off = {on: qa('#tx .tx li').filter((li) => /\bon\b/.test(li.getAttribute('class') || '')).map((li) => li.getAttribute('id')), scrolls: n.scrolls.length};
    q('#pl-follow').checked = true;
    q('#pl-follow').dispatchEvent({type: 'change'});
    stubWrites(n);
    byId('t4').querySelector('.tx-text').click();
    await settle();
    n.scrolls.length = 0;
    audio.currentTime = 10;
    audio.dispatchEvent({type: 'seeked'});
    seen.editing = {on: qa('#tx .tx li').filter((li) => /\bon\b/.test(li.getAttribute('class') || '')).map((li) => li.getAttribute('id')), scrolls: n.scrolls.filter((s) => s.block === 'center' && s.behavior === 'smooth').length};
    // before any play at 0:00 no line is current
    audio.paused = true;
    audio.currentTime = 0;
    audio.dispatchEvent({type: 'seeked'});
    seen.idle = qa('#tx .tx li').filter((li) => /\bon\b/.test(li.getAttribute('class') || '')).length;
    // a line's own time button plays that line
    audio.readyState = 4;
    byId('t2').querySelector('.ts').click();
    seen.lineButton = {time: audio.currentTime, seek: byId('t2').querySelector('.ts').getAttribute('data-seek')};
    return seen;
  },

  // A link from search (/notes/<job>#t4): the line has its id, the page lands on it at the first draw, marks it for a moment,
  // follows hashchange, opens the section links, and ignores any other address.
  async noteLink({lang, ...params}) {
    const n = await openNote({lang, hash: '#t4', holdTranscript: true, ...params});
    const marked = () => qa('#tx .tx li').filter((li) => /\btarget\b/.test(li.getAttribute('class') || '')).map((li) => li.getAttribute('id'));
    const tab = () => qa('.tabs a').filter((a) => a.getAttribute('aria-current')).map((a) => a.getAttribute('href'));
    const seen = {ids: qa('#tx .tx li').map((li) => li.getAttribute('id')), tabs: qa('.tabs a').map((a) => [a.getAttribute('href'), text(a)])};
    // before the engine's lists have arrived, from the page data alone
    seen.first = {marked: marked(), scrolls: n.scrolls.map((s) => s.id), tab: tab(), readOnly: !byId('t4').querySelector('.tx-text').hasAttribute('role')};
    n.release();
    await settle();
    seen.loaded = {marked: marked(), scrolls: [...new Set(n.scrolls.map((s) => s.id))], tab: tab(), editable: byId('t4').querySelector('.tx-text').getAttribute('role') === 'button', timers: n.timers.length};
    n.timers.shift()();
    seen.expired = marked();
    const go = async (address) => { location.hash = address; n.fire('hashchange'); await settle(); };
    const changed = {};
    for (const [name, address] of [['t2', '#t2'], ['sum', '#sum'], ['tx', '#tx'], ['spk', '#spk']]) {
      const before = n.scrolls.length;
      await go(address);
      changed[name] = {marked: marked(), tab: tab(), scrolled: n.scrolls.slice(before).map((s) => s.id), timers: n.timers.length};
    }
    seen.changed = changed;
    n.timers.length = 0;
    const evil = ['#t0', '#t999', '#t1x', '#t01', '#T2', '#t2%20', '#t2 ', '#', '', '#<img src=x onerror=alert(1)>', '#t2"><script>window.pwned=1</script>', '#t2\'];x', '#__proto__', '#sum;t3', '#tx/t3'];
    const before = {scrolls: n.scrolls.length, marked: marked(), tab: tab()};
    for (const address of evil) await go(address);
    seen.ignored = {scrolls: n.scrolls.length - before.scrolls, marked: marked(), before: before.marked, tab: tab(), was: before.tab, timers: n.timers.length, pwned: globalThis.pwned ?? null};
    // the marked line is redrawn (a save) and stays marked until the time is up
    await go('#t3');
    stubWrites(n);
    byId('t3').querySelector('.tx-text').click();
    await settle();
    typeInto2(byId('t3').querySelector('textarea'), '고친 글');
    press(byId('t3').querySelector('textarea'), 'Enter');
    await settle();
    seen.redrawn = {marked: marked(), edited: !!byId('t3').querySelector('.chip')};
    n.timers.at(-1)();
    seen.redrawnExpired = marked();
    return seen;
  },

  // The pure rules: what is a valid name or line, what a search finds, which S1 become names.
  async noteText({names, texts, queries, cleans}) {
    const t = await load('lib/note-text.js');
    return {
      clean: cleans.map(([value, limit]) => t.cleanText(value, limit)),
      names: texts.map((value) => t.nameSpeakers(value, new Map(Object.entries(names)))),
      find: queries.map(([text_, query]) => t.findRanges(text_, query).map(([a, b]) => text_.slice(a, b))),
      ranges: queries.map(([text_, query]) => t.findRanges(text_, query)),
      cut: t.cutAt('abcdef', [[1, 2], [4, 6]]),
      oneLine: t.oneLine('a\nb\r\nc\u2028d'),
      composing: [{isComposing: true}, {keyCode: 229}, {isComposing: false, keyCode: 13}, {}].map((e) => t.isComposing(e)),
    };
  },
});
'''


def note_harness_file(directory):
    marker = 'const out = await scenarios[scenario](params);'
    assert marker in UPDATE_UI_HARNESS
    path = directory / 'note-harness.mjs'
    path.write_text(UPDATE_UI_HARNESS.replace(marker, NOTE_UI_SCENARIOS + '\n' + marker), encoding='utf-8')
    return path


@pytest.fixture(scope='module')
def note_harness(tmp_path_factory):
    return note_harness_file(tmp_path_factory.mktemp('note-ui'))


NOTE_T = {
    'ko': {'guess': '(추정)', 'confirmed': '확정', 'saved': '노트의 전체 대화록에 바로 반영했어요', 'resum': '요약만 다시', 'lock': '처리하는 중이라', 'empty': '내용이 있어야 해요',
           'long': '2001자예요. 2000자까지', 'invisible': '줄바꿈이나 보이지 않는 글자', 'name_long': '41자예요. 40자까지', 'name_chars': '제어문자나 보이지 않는 글자',
           'nomatch': '일치하는 줄이 없어요', 'merged': 'S2에 합쳤어요', 'speed': '재생 속도', 'edited': '고친 줄 1개', 'restore': '원문으로',
           'reasons': {'job_running': '지금 이 회의를 처리하고 있어요', 'processing_data_deleted': '처리 데이터를 지워서', 'vault_migration': '아직 새 형식으로 옮기지 않았어요',
                       'note_missing': '노트를 찾지 못해', 'job_changed': '그새 회의가 바뀌었어요', 'artifact_unavailable': '엔진이 보관한 결과를 읽지 못했어요',
                       'merge_cycle': '이미 합쳐진 화자끼리는', 'weird_new': '요청을 받지 않았어요'}, 'network': '엔진에 닿지 못했어요', 'bad': '400 text must have 1..40 characters'},
    'en': {'guess': '(estimated)', 'confirmed': 'Confirmed', 'saved': 'The note\'s transcript has the change now', 'resum': 'Re-summarize only', 'lock': 'being processed', 'empty': 'A line can\'t be empty',
           'long': 'That is 2001 characters; the limit is 2000', 'invisible': 'Line breaks and invisible characters', 'name_long': 'That is 41 characters; the limit is 40',
           'name_chars': 'Control and invisible characters', 'nomatch': 'No match', 'merged': 'Merged into S2', 'speed': 'Speed', 'edited': '1 edited', 'restore': 'Restore original',
           'reasons': {'job_running': 'This meeting is being processed right now', 'processing_data_deleted': 'The processing data was deleted', 'vault_migration': 'have not been converted',
                       'note_missing': 'is not in your vault', 'job_changed': 'changed in the meantime', 'artifact_unavailable': 'could not read its kept result',
                       'merge_cycle': 'already merged', 'weird_new': 'Request not accepted'}, 'network': 'Could not reach the engine', 'bad': '400 text must have 1..40 characters'},
}
NOTE_TAGS = {'a', 'b', 'button', 'div', 'form', 'h2', 'h3', 'i', 'input', 'label', 'li', 'mark', 'ol', 'option', 'p', 'path', 'section', 'select', 'small', 'span', 'svg', 'textarea', 'ul'}


def sent(writes):
    return [(w['method'], w['path'], w.get('body')) for w in writes]


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_speaker_panel_names_merges_and_request_bodies(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    seen = run_ui(note_harness, 'noteSpeakers', lang=lang, **note_ui())
    initial = seen['initial']
    assert '3' in seen['head'] and seen['bars'] == 3 and not seen['lock'] and seen['nameInput']
    assert t['guess'] in initial['S2']['text'] and '오지안' in initial['S2']['text'] and t['guess'] not in initial['S1']['text']   # a guess stays a guess
    assert [b.get('act') for b in initial['S2']['buttons']] == ['agree', 'rename', None, 'listen', 'merge'] and seen['evidence'] == '9.00-12.00'   # None: the time where the name was said
    assert [b['act'] for b in initial['S1']['buttons']] == ['confirm', 'listen', 'merge']
    assert seen['listen'] == {'S1': '0.00-8.00', 'S2': '9.00-21.00', 'S3': '31.00-36.00'}   # each speaker's `sample`, played as it is
    assert seen['empty']['disabled'] and seen['tooLong']['confirm']['disabled'] and seen['invisible']['confirm']['disabled'] and not seen['typed']['confirm']['disabled']
    assert t['name_long'] in seen['tooLong']['said'] and seen['tooLong']['invalid'] == 'true' and t['name_chars'] in seen['invisible']['said'] and seen['typed']['said'] == ''
    assert [(w['method'], w['path'], w['body']) for w in seen['allWrites']] == [
        ('PUT', '/speakers/S1', {'name': '한서윤', 'confirmed': True}),   # trimmed
        ('PUT', '/speakers/S2', {'name': '오지안', 'confirmed': True}),   # "That's right": the guess, now confirmed
        ('POST', '/speakers/merge', {'from': 'S3', 'into': 'S2'}),
        ('POST', '/speakers/merge', {'from': 'S3', 'into': None}),
        ('PUT', '/speakers/S1', {'name': None, 'confirmed': False})]
    assert all(w['csrf'] == 'csrf-1' and w['key'] for w in seen['allWrites']) and len({w['key'] for w in seen['allWrites']}) == 5
    after = seen['afterS1']
    assert '한서윤' in after['row']['text'] and t['confirmed'] in after['row']['text'] and after['row']['focus'] == 'rename/S1'   # the keyboard stays on this row
    assert '한서윤' in after['live'] and '한서윤' in after['said'] and after['line'] == '한서윤S1' and after['named'] == 'tx named'
    assert '한서윤 asked S2' in after['summary'] and '한서윤이 S2에게' in after['summary']   # as in the note: a confirmed label takes the name even with a particle attached
    assert t['guess'] not in seen['afterS2']['row']['text'] and '오지안' in seen['afterS2']['row']['text'] and t['confirmed'] in seen['afterS2']['row']['text']
    form = seen['mergeForm']
    assert [option.split(' · ')[0] for option in form['options'][1:]] == ['S1', 'S2'] and form['go']['disabled'] and form['focus'] and not seen['mergeReady']['disabled']
    merged = seen['afterMerge']
    assert t['merged'] in merged['s3']['text'] and not merged['merged'] and [b['act'] for b in merged['s3']['buttons']] == ['unmerge'] and merged['s3']['focus'] == 'unmerge/S3'
    assert ('S3 합침' if lang == 'ko' else 'S3 merged in') in merged['s2'] and merged['lines'][3] == '오지안S2'   # S2 says what it took in; the line shows its new speaker
    assert seen['afterUndo']['lines'][3] == 'S3' and seen['afterUndo']['s3']['buttons'][0]['act'] == 'confirm' and seen['afterUndo']['s3']['focus'] == 'merge/S3'
    assert seen['renaming']['value'] == '한서윤' and seen['renaming']['focus'] and [b['act'] for b in seen['renaming']['buttons']] == ['confirm', 'cancel', 'clear', 'listen', 'merge']
    assert '한서윤' in seen['cancelled'] and '한서윤' not in seen['cleared']['row']['text'] and seen['cleared']['line'] == 'S1' and seen['cleared']['row']['buttons'][0]['act'] == 'confirm'


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_speaker_panel_refusals_job_running_and_unreachable_engine(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    reasons = list(t['reasons'])
    seen = run_ui(note_harness, 'noteRefusals', lang=lang, reasons=reasons, **note_ui())
    assert not seen['before']['lock'] and seen['before']['off'] == 2   # the two boxes with no name typed yet
    for reason in reasons[1:]:
        said = seen['by'][reason]
        assert t['reasons'][reason] in said['banner'] and f'409 {reason}' in said['banner'], reason   # in words, with the code
        assert not said['lock'] and said['draft'] == '문태오', reason   # nothing is locked, and what was typed is still there
    assert seen['by']['vault_migration']['link'] == '/migrate' and seen['by']['job_changed']['reload'] and not seen['by']['merge_cycle']['reload']
    assert t['network'] in seen['network'] and 'engine_unreachable' in seen['network'] and seen['bad'].endswith(t['bad'])
    running = seen['running']
    assert t['lock'] in running['lock'] and not running['banner'] and running['draft'] == '문태오'   # the lock is a sentence, not an error banner
    assert all(running['off']) and running['confirm']['disabled'] and t['lock'] in running['hint'] and set(running['textDisabled']) == {'true'}
    assert not seen['done']['lock'] and seen['done']['off'] == 1 and set(seen['done']['textDisabled']) == {None}   # done again: unlocked (the empty box stays off)


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_line_editing_keys_ime_restore_and_limits(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    data = note_ui()
    seen = run_ui(note_harness, 'noteLines', lang=lang, **data)
    originals = [line['text'] for line in data['lines']]
    assert {k: v for k, v in seen['initial'].items() if k != 'hint'} == {'roles': 5, 'tabs': 5, 'lines': 5} and 'Enter' in seen['initial']['hint'] and 'Esc' in seen['initial']['hint']
    assert seen['opened']['t2']['editing'] and seen['opened']['focus'] == 'textarea@t2' and seen['opened']['draft'] == originals[1] and seen['opened']['rows'] == '2'
    assert 'Enter' in seen['opened']['keys'] and 'Esc' in seen['opened']['keys']
    # an IME's Enter (isComposing, or keyCode 229 after compositionend) and its Esc belong to the input method: nothing sent, nothing closed, not even prevented
    assert seen['ime'] == {'prevented': [False, False, False], 'writes': 0, 'editing': True}
    assert seen['oneLine'] == '오지안입니다 홈 화면을 바꿔요'   # a line has no line break
    saved, new_text = seen['saved'], '오지안입니다 홈 화면을 바꿔요 (고침)'
    assert saved['prevented'] and sent(saved['writes']) == [('PUT', '/transcript/t2', {'text': new_text})] and saved['writes'][0]['csrf'] == 'csrf-1' and saved['writes'][0]['key']
    assert saved['t2']['text'] == new_text and saved['t2']['edited'] and saved['t2']['restore'] and originals[1] in saved['t2']['original'] and not saved['t2']['editing']
    assert saved['next']['editing'] and saved['focus'] == 'textarea@t3' and saved['gets'] == 2   # Enter moved on; the list was read again after the save
    assert t['saved'] in saved['notice'] and t['resum'] in saved['notice'] and saved['noticeButtons'][0]['text'] == t['resum'] and saved['said'] and t['edited'] in saved['head']
    unchanged = seen['unchanged']
    assert unchanged['writes'] == 0 and unchanged['next']['editing'] and unchanged['focus'] == 'textarea@t4' and not unchanged['t3']['edited']   # nothing changed: nothing sent, still on to the next
    assert seen['modified'] == {'prevented': [True, True, True], 'writes': 0, 'editing': True}   # Shift/Ctrl/Meta+Enter: no line break and no save
    assert seen['escaped']['prevented'] and seen['escaped']['writes'] == 0 and seen['escaped']['t4']['text'] == originals[3] and 'tx-text' in seen['escaped']['focus']
    assert seen['byKey']['t5']['editing'] and seen['byKey']['focus'] == 'textarea@t5'   # Enter on a line opens it, without a mouse
    assert seen['last']['t5']['text'] == '알겠습니다 감사합니다' and seen['last']['editing'] == 0 and seen['last']['writes'][0]['path'] == '/transcript/t5'   # the last line closes after saving
    problems = seen['problems']
    assert problems['sent'] == 0   # what is not allowed is said, never sent
    for name, said in (('empty', t['empty']), ('long', t['long']), ('invisible', t['invisible']), ('control', t['invisible'])):
        assert said in problems[name]['said'] and problems[name]['invalid'] == 'true' and problems[name]['editing'] and problems[name]['role'] == 'alert', name
    assert problems['cleared'] == {'said': '', 'invalid': None}   # typing again clears the stale message
    switched = seen['switched']
    assert sent(switched['writes']) == [('PUT', '/transcript/t1', {'text': '고치는 중'})] and switched['t1']['text'] == '고치는 중' and switched['t3']['editing']   # clicking another line saves this one first
    assert sent(seen['same']['writes']) == [('DELETE', '/transcript/t5', None)] and not seen['same']['t5']['edited'] and seen['same']['t5']['text'] == originals[4]   # back to the first words: restore, not a PUT
    assert seen['restoreButton']['text'] == t['restore'] and '00:09' in seen['restoreButton']['label'] and originals[1] in seen['restoreButton']['original']
    assert sent(seen['restored']['writes']) == [('DELETE', '/transcript/t2', None)] and not seen['restored']['t2']['edited'] and seen['restored']['t2']['text'] == originals[1]
    assert all(w['csrf'] == 'csrf-1' and w['key'] for w in seen['writes']) and len({w['key'] for w in seen['writes']}) == len(seen['writes'])


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_line_editor_keeps_the_draft_when_a_save_is_refused_or_slow(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    seen = run_ui(note_harness, 'noteLineTrouble', lang=lang, **note_ui())
    refused = seen['refused']
    assert refused['editing'] and refused['draft'] == '거절될 글' and refused['alert'] == 'alert' and refused['focus'] and not refused['saveButton']['disabled']
    assert t['reasons']['job_running'] in refused['said'] and '409 job_running' in refused['said'] and t['lock'] in refused['lock']
    assert not seen['noOpen']['t2']   # while the job runs no other line can be opened
    assert seen['slow']['readonly'] and seen['slow']['writes'] == 1 and all(b['disabled'] for b in seen['slow']['buttons'] if b['text'] != '00:00')   # two Enters, one request; the editor waits
    assert seen['after'] == {'writes': 1, 'text': '느린 저장', 'next': True}
    assert seen['redraw'] == {'same': True, 'draft': '쓰는 중인 글'}   # a redraw elsewhere (the job moved) leaves the editor and its draft alone
    assert t['network'] in seen['offline']['said'] and 'engine_unreachable' in seen['offline']['said'] and seen['offline']['draft'] == '쓰는 중인 글'
    assert seen['log'] == ['PUT /transcript/t1', 'PUT /transcript/t1', 'PUT /transcript/t2']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_find_on_the_page(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    queries = ['책마루', '책 마루', 'gpu', '  GPU  ', '해요', 'zzz', '', '<img src=x onerror=alert(1)>']
    seen = run_ui(note_harness, 'noteFind', lang=lang, queries=queries, **note_ui())
    by = seen['by']
    assert by['책마루']['lines'] == ['t1'] and by['책마루']['marks'] == [{'text': '책 마루', 'on': True}] and by['책마루']['count'] == '1 / 1'   # spacing does not matter, either way
    assert by['책 마루'] == by['책마루'] and by['gpu']['marks'] == [{'text': 'GPU', 'on': True}] and by['  GPU  '] == by['gpu']   # nor case, nor spaces around the query
    assert by['해요']['lines'] == ['t2'] and by['zzz']['count'] == t['nomatch'] and by['zzz']['marks'] == [] and by['']['count'] == '' and by['']['marks'] == []
    assert by['<img src=x onerror=alert(1)>']['marks'] == [] and by['<img src=x onerror=alert(1)>']['count'] == t['nomatch']
    many = seen['many']
    assert many['first']['count'] == '1 / 5' and many['first']['lines'] == ['t1', 't2', 't3', 't5'] and [m['on'] for m in many['first']['marks']] == [True, False, False, False, False]
    assert many['scrolls'] == [{'id': 'mark', 'block': 'center', 'behavior': 'auto'}]   # the current match is brought into view
    assert [(step['count'], step['on']) for step in seen['next']] == [('2 / 5', ['t2']), ('3 / 5', ['t3']), ('4 / 5', ['t3']), ('5 / 5', ['t5']), ('1 / 5', ['t1']), ('2 / 5', ['t2'])]   # and round again
    assert seen['prev'] == ['1 / 5', '5 / 5']   # backwards wraps too
    assert seen['keys']['prevented'] == [True, True, False] and seen['keys']['count'] == '5 / 5' and seen['keys']['announced']   # Enter next, Shift+Enter previous, an IME's Enter nothing
    assert seen['cleared']['value'] == '' and seen['cleared']['state'] == {'count': '', 'marks': [], 'lines': []}   # Esc clears the box and the marks
    assert seen['none']['state']['count'] == t['nomatch'] and seen['none']['live'] == t['nomatch']
    assert seen['editing'] == {'count': '1 / 5', 'scrolls': 0}   # an edit under an open search keeps the place and sends the page nowhere


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_export_menu_links_and_choices(note_harness, note_ui, lang):
    data = note_ui()
    seen = run_ui(note_harness, 'noteExport', lang=lang, **data)
    formats = ('srt', 'vtt', 'txt', 'md', 'docx')
    assert seen['closed'] == {'hidden': True, 'expanded': 'false', 'controls': 'export-panel', 'label': '내보내기' if lang == 'ko' else 'Export'}
    opened = seen['open']
    assert not opened['hidden'] and opened['expanded'] == 'true' and opened['focus'] == 'srt'   # the keyboard lands on the first format
    assert [(link['format'], link['href']) for link in opened['links']] == [(f, f"/api/jobs/{data['jobId']}/export?format={f}&names=1&timestamps=1") for f in formats]
    assert all(link['download'] and link['label'] for link in opened['links']) and [o['checked'] for o in opened['options']] == [True, True]
    assert any('Word' in link['text'] and '.docx' in link['text'] for link in opened['links']) and any('Markdown' in link['text'] for link in opened['links'])
    assert seen['noNames'] == [f'format={f}&names=0&timestamps=1' for f in formats]
    assert seen['neither'] == [f'format={f}&names=0&timestamps=0' for f in formats]
    assert seen['namesOnly'] == [f'format={f}&names=1&timestamps=0' for f in formats]
    assert seen['clicked']['prevented'] is False and seen['clicked']['calls'] == 0 and 'Word' in seen['clicked']['announced']   # a plain download: the page sends nothing itself
    assert seen['offline']['prevented'] and seen['offline']['toggle']['disabled']   # without the engine the link goes nowhere
    assert seen['escaped'] == {'prevented': True, 'hidden': True, 'expanded': 'false', 'focus': True}
    assert seen['url'] == ['/api/jobs/a%20b%2Fc/export?format=docx&names=0&timestamps=1', '/api/jobs/x/export?format=srt&names=1&timestamps=1',
                           '/api/jobs/..%2Fx/export?format=md&names=1&timestamps=0', '/api/jobs/x/export?format=a%26b%3D1&names=1&timestamps=1']   # every part is encoded
    assert seen['formats'] == [['srt', 'SRT', '.srt'], ['vtt', 'VTT', '.vtt'], ['txt', 'TXT', '.txt'], ['md', 'Markdown', '.md'], ['docx', 'Word', '.docx']]


def test_every_export_format_the_screen_offers_is_one_the_engine_serves():
    from quietclerk import export
    assert re.findall(r"\{id: '(\w+)'", (STATIC / 'lib/export-menu.js').read_text()) == list(export.FORMATS)


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_suggestions_save_the_whole_list_with_the_pair_added(note_harness, note_ui, lang):
    pairs = [{'from': '책 마루', 'to': '책마루'}, {'from': 'GPU', 'to': '지피유'}, {'from': 'a' * 41, 'to': 'b'}, {'from': 'x', 'to': 'x'}, {'from': 'k\u200bq', 'to': 'kq'},
             {'from': '둘', 'to': 'two'}, {'from': '셋', 'to': 'three'}, {'from': '넷', 'to': 'four'}]
    listed = [{'from': '큐시', 'to': 'QC'}, {'from': 'GPU', 'to': '그래픽'}]
    seen = run_ui(note_harness, 'noteVocab', lang=lang, pairs=pairs, settings={'vocabulary.replace': listed}, **note_ui())
    assert seen['head'] == ('단어장에 추가할까요?' if lang == 'ko' else 'Add to the word list?') and not seen['hidden'] and len(seen['initial']) == 5 and seen['more']
    first = seen['initial']
    assert [item['button'] is not None for item in first] == [True, True, False, False, False]   # too long, identical, or an invisible character: cannot go in
    assert '책 마루' in first[0]['text'] and '책마루' in first[0]['text'] and '책 마루' in first[0]['label']
    assert seen['added']['gets'] == 1 and seen['added']['live'] and seen['added']['items'][0]['button'] is None
    assert seen['saved'] == {'vocabulary.replace': [*listed, {'from': '책 마루', 'to': '책마루'}]}   # the list as it was, plus the pair; nothing else was saved
    assert seen['puts'] == [{'vocabulary.replace': [*listed, {'from': '책 마루', 'to': '책마루'}]},
                            {'vocabulary.replace': [*listed, {'from': '책 마루', 'to': '책마루'}, {'from': '둘', 'to': 'two'}]},   # refused with 409: locked by an environment variable
                            {'vocabulary.replace': [*listed, {'from': '책 마루', 'to': '책마루'}, {'from': '셋', 'to': 'three'}]},   # refused with 400
                            {'vocabulary.replace': [*listed, {'from': '책 마루', 'to': '책마루'}, {'from': '넷', 'to': 'four'}]}]   # engine unreachable
    assert seen['clash']['button'] is None and 'GPU' in seen['clash']['text'] and seen['expanded'] == {'count': 8, 'more': False}   # GPU already has another correction: not sent at all
    assert seen['locked']['button'] is None and seen['refused']['button'] and '400' in seen['refused']['text'] and seen['offline']['button'] and 'engine_unreachable' in seen['offline']['text']
    assert seen['left'] == 2   # a refusal or a lost connection can be tried again


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_hostile_text_stays_text_on_the_minutes_screen(note_harness, note_ui, lang):
    evil = '</script><script>window.pwned=1</script><img src=x onerror=alert(1)> [x](https://evil.example) {{7*7}} \u202e\u2028'
    turns = [(0.0, 8.0, 'S1', evil), (9.0, 21.0, 'S2', '<img src=x onerror=alert(2)> 두번째'), (22.0, 30.0, 'S1', 'ok'), (31.0, 36.0, 'S3', '네'), (37.0, 40.0, 'S2', '끝')]
    data = note_ui(turns=turns, roles=(evil, '<b>x</b>', None), summary='## 핵심 요약\n- S1 <img src=x onerror=alert(3)> [t1]\n')
    data['speakers'][1]['name'] = '<svg onload=alert(4)>'
    data['speakers'][1]['role'] = evil
    data['lines'][2]['text'] += '<iframe src=javascript:alert(5)>'
    pairs = [{'from': '<script>', 'to': '<img src=x>'}, {'from': 'a', 'to': evil[:30]}]
    seen = run_ui(note_harness, 'noteHostile', lang=lang, suggestions=pairs, **data)
    for tags in (*seen['tags'].values(), seen['find']['tags'], seen['editor']['tags'], seen['saved']['tags'], seen['named']['tags'], seen['final']['tags']):
        assert set(tags) <= NOTE_TAGS, set(tags) - NOTE_TAGS   # nothing but the elements the screen itself draws: no img, script, iframe, style, link, object, embed
    assert seen['find']['count'] == '1 / 2' and seen['find']['marks'] == ['<img', '<img']   # a search for markup finds the text of the line and of its neighbour
    assert seen['editor']['value'] == evil   # the editor holds the line as a value
    assert seen['saved']['write'] == [] and seen['saved']['text'].startswith('<img src=x onerror=alert(2)>')   # a text with an invisible character is refused, not sent
    assert seen['named']['write'][0]['body'] == {'name': '<b onmouseover=alert(3)>이름</b>', 'confirmed': True}
    assert '<b onmouseover=alert(3)>이름</b> <img src=x onerror=alert(3)>' in seen['named']['summary'] and seen['named']['speakerCell'] == '<b onmouseover=alert(3)>이름</b>S1'   # shown as the letters it is
    final = seen['final']
    assert final['links'] == 0 and final['pwned'] is None and '<svg onload=alert(4)>' in final['texts']
    assert not [name for name in final['attributes'] if name.startswith('on') or name in ('style', 'srcdoc', 'src')] and all(re.fullmatch(r'/api/jobs/[^/]+/export', href) for href in final['hrefs'])   # no handler or inline style attribute; links go only to the engine's export


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_a_link_from_search_opens_the_page_on_that_line(note_harness, note_ui, lang):
    seen = run_ui(note_harness, 'noteLink', lang=lang, **note_ui())
    assert seen['ids'] == ['t1', 't2', 't3', 't4', 't5'] and [href for href, _ in seen['tabs']] == ['#sum', '#tx', '#spk']   # a line's id is its line ID, as in the note (^t4)
    first = seen['first']
    assert first == {'marked': ['t4'], 'scrolls': ['t4'], 'tab': ['#tx'], 'readOnly': True}   # at the first draw, from the page data, before the engine's lists arrive
    loaded = seen['loaded']
    assert loaded == {'marked': ['t4'], 'scrolls': ['t4'], 'tab': ['#tx'], 'editable': True, 'timers': 1} and seen['expired'] == []   # the mark outlives the redraw and runs out by itself
    changed = seen['changed']
    assert changed['t2'] == {'marked': ['t2'], 'tab': ['#tx'], 'scrolled': ['t2'], 'timers': 1}   # hashchange: the new line is marked, the old mark is gone
    assert changed['sum']['tab'] == ['#sum'] and changed['tx']['tab'] == ['#tx'] and changed['spk']['tab'] == ['#spk'] and not any(changed[name]['scrolled'] for name in ('sum', 'tx', 'spk'))
    ignored = seen['ignored']
    assert ignored['scrolls'] == 0 and ignored['marked'] == ignored['before'] and ignored['tab'] == ignored['was'] and ignored['timers'] == 0 and ignored['pwned'] is None   # any other address changes nothing
    assert seen['redrawn'] == {'marked': ['t3'], 'edited': True} and seen['redrawnExpired'] == []   # a save redraws the row: still marked until the time is up


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_playback_speed_sample_and_following(note_harness, note_ui, lang):
    t = NOTE_T[lang]
    seen = run_ui(note_harness, 'notePlayback', lang=lang, **note_ui())
    assert seen['speeds'] == ['0.75×', '1×', '1.25×', '1.5×', '2×'] and seen['value'] == '1' and seen['follow'] and t['speed'] in seen['label']
    assert seen['rate'] == {'rate': 1.5, 'def': 1.5, 'stored': '1.5'}
    assert seen['sample'] == '31.00-36.00' and seen['started'] == {'time': 31, 'rate': 1.5, 'playing': True, 'played': 1}   # the voice sample starts where it says, at the chosen speed (also after load())
    assert seen['following']['on'] == ['t4'] and seen['following']['scrolls'] == [{'id': 't4', 'block': 'center', 'behavior': 'smooth'}]   # the current line is marked and followed
    assert seen['stopped'] == {'paused': True, 'playing': False, 'on': []}   # and it stops where the sample ends
    assert seen['off'] == {'on': ['t1'], 'scrolls': 0}   # not following: the line is marked, the page stays
    assert seen['editing'] == {'on': ['t2'], 'scrolls': 0}   # a line being edited is never scrolled away
    assert seen['idle'] == 0 and seen['lineButton'] == {'time': 9, 'seek': '9-21'}   # at 0:00 before any play no line is current; a line's own time plays that line


@needs_node
def test_name_rule_search_and_input_rules_match_the_engine(note_harness):
    import unicodedata
    from quietclerk import render
    corpus = ['S1 / S10 / S1a / aS1 / 한S1글 / (S1), S1, S1. S1\n', 'S1이 S2를 S1/S2 S1S2 S10 S1_ _S1', 'S1: S1은 S1과 S1 S1', 'S1\u00a0S2', 'S1 가 S11', 'S1\tS2\nS3']
    names = {'S1': '한서윤', 'S10': '열', 'S2': 'Priya Rao'}
    cleans = [['  책마루  ', 40], ['', 40], ['   ', 40], ['a' * 40, 40], ['a' * 41, 40], ['가' * 40, 40], ['😀' * 40, 40], ['😀' * 41, 40], ['a\nb', 40], ['a\tb', 40], ['a\u200bb', 40],
              ['a\u202eb', 40], ['a\ue000b', 40], ['a\u00a0b', 40], ['ＡＢ', 40], ['e\u0301', 40], ['x' * 2000, 2000], ['x' * 2001, 2000]]
    queries = [['안녕 책 마루 회의', '책마루'], ['안녕 책마루 회의', '책 마루'], ['GPU gpu Gpu', 'gpu'], ['ababab', 'aba'], ['İstanbul', 'i̇'], ['aaa', 'aa'], ['', 'a'], ['abc', '']]
    seen = run_ui(note_harness, 'noteText', names={**names, 'S3': '$& $1'}, texts=corpus, queries=queries, cleans=cleans)
    speakers = {label: {'confirmed': True, 'name': name} for label, name in names.items()}
    for text, got in zip(corpus, seen['names']):
        assert got == render.replace_speaker_names(text, speakers).replace('S3', '$& $1'), text   # the screen replaces S1 where the note does, and only there
    assert seen['names'][-1].endswith('$& $1')   # a name is never read as a replacement pattern
    for (value, limit), got in zip(cleans, seen['clean']):
        wanted = value.strip()
        ok = bool(wanted) and not any(unicodedata.category(c).startswith('C') for c in wanted) and len(wanted) <= limit   # the engine's own rule (overrides.clean_string)
        assert got['ok'] == ok, (value, got)
    assert [found for found in seen['find']] == [['책 마루'], ['책마루'], ['GPU', 'gpu', 'Gpu'], ['aba'], ['İ'], ['aa'], [], []] and seen['ranges'][0] == [[3, 7]]
    assert seen['cut'] == [{'text': 'a', 'hit': False}, {'text': 'b', 'hit': True, 'index': 0}, {'text': 'cd', 'hit': False}, {'text': 'ef', 'hit': True, 'index': 1}]
    assert seen['oneLine'] == 'a b c d' and seen['composing'] == [True, True, False, False]


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_reasons_for_dropped_names_and_edits_are_in_words(harness, note_job, lang):
    codes = ['speaker_overrides_dropped', 'transcript_edits_dropped']
    seen = run_ui(harness, 'minutes', lang=lang, **note_job(codes))
    texts = [chip['text'] for chip in seen['chips']]
    assert len(texts) == 2 and not set(codes) & set(texts) and all(len(text) > 30 for text in texts)   # sentences, not the raw codes
    assert ('화자' in texts[0] and '줄' in texts[1]) if lang == 'ko' else ('speakers' in texts[0] and 'lines' in texts[1])


def test_classes_the_minutes_screen_adds_are_styled_and_its_modules_are_served(api):
    client, runtime, base = api
    login(client, runtime, base)
    css = (STATIC / 'qc.css').read_text()
    sources = ''.join((STATIC / name).read_text() for name in ('screens/note.js', 'lib/speakers.js', 'lib/transcript.js', 'lib/vocab-suggest.js', 'lib/export-menu.js'))
    for name in ('spk-list', 'spk', 'spk-top', 'spk-share', 'share', 'spk-name', 'spk-form', 'spk-actions', 'spk-merge', 'spk-lock', 'tx-body', 'tx-text', 'tx-meta', 'tx-orig', 'tx-form', 'tx-edit',
                 'tx-find', 'tx-count', 'find-hit', 'sugg', 'sugg-list', 'sugg-item', 'sugg-pair', 'export-panel', 'export-list', 'export-item', 'player-tools', 'playing', 'named', 'editing', 'target'):
        assert re.search(rf'[\'" ]{re.escape(name)}[\'" ]', sources), name   # the screen uses it
        assert re.search(rf'\.{re.escape(name)}(?![\w-])', css), name   # and the stylesheet has a rule for it
    for name in ('lib/note-text.js', 'lib/overrides.js', 'lib/speakers.js', 'lib/transcript.js', 'lib/vocab-suggest.js', 'lib/export-menu.js'):
        assert client.get('/static/' + name).status_code == 200, name
    assert not re.search(r'\.classList\b', sources)   # the node harness has no classList; the screen sets classes through dom.flag
