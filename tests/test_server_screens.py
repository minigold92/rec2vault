"""F2 web screens: input policy and abnormal/malicious input evidence (synthetic data, no real recordings).

| Input | Policy | Test |
|---|---|---|
| Any screen path or /static file without a session (none, forged, logged out, wrong Host) | 303 to / (screen) or 401 (file); no markup, no data | test_screen_paths_give_no_data_without_a_session, test_static_files_need_a_session |
| Request path used as a file name (../, %2e%2e, %00, directories) | static files come from an exact-name index, never a path join | test_static_lookup_is_an_exact_name_index |
| Job ID in /notes/<id> (unknown, path-like) | SQL parameter only; unknown = 404 with the same shell | test_note_screen_unknown_job_and_path_like_ids |
| Transcript/summary/title text with HTML, script, links, instructions (IN-22) | JSON in an HTML-safe data block, put in the page with textContent | test_note_data_block_is_html_safe_and_text_is_verbatim, test_front_end_has_no_markup_sinks |
| Artifacts that are tampered, unsigned, symlinked or malformed | not shown; the screen says the minutes were not found | test_unverified_artifacts_are_never_shown |
| Inline script/style, external URLs in the served pages and assets (CSP default-src 'self') | none exist | test_screens_are_one_fixed_shell_without_inline_code, test_front_end_has_no_markup_sinks |
| Note migration: no/odd consent, no CSRF, no session | 400 / 403 / 401 and nothing changed on disk | test_migration_policy_* |
| Note migration preview | read-only: vault bytes, backup dir and DB unchanged | test_migration_preview_changes_nothing |
| Migration that cannot be applied (blocking conflict) | 409 with a reason code, notes untouched | test_migration_conflict_is_409_with_reason |
| Update answers (GET /api/update, check/apply/dismiss bodies, the `update` part of the event stream) with markup, links, bidi/control characters, 5000-character text, impossible counts or dates, an unknown state or reason, or no JSON object at all | text nodes only, controls removed, length bounded; an unknown state shows no band, an unknown reason one plain sentence, a count or date that does not parse is dropped | test_update_ui_treats_api_text_as_text |
| An update request that fails (network, 409 with a reason) or a session that did not survive the restart | the sentence and status code sit beside the button, the state is read again, the button works again; a lost session shows the sign-in notice and no stale band | test_update_click_sends_one_request, test_update_result_is_confirmed_once, test_update_band_is_gone_when_the_session_is_lost |
| Update / Check now / OK clicked twice, or a key held | one request per action while one is out; the buttons are off meanwhile; every POST carries the CSRF token and a fresh Idempotency-Key | test_update_click_sends_one_request, test_settings_update_toggle_and_check |
| The engine restarting during an update | the band says "updating" (no connection-lost alarm) for 3 minutes, then the normal engine notice; when it is back the result is read once and stays until confirmed | test_update_survives_the_engine_restart |
| Word list entries typed or pasted in settings (empty, 41 characters, control / zero-width / bidi characters, HTML tags, `__proto__`, a duplicate, the 201st, several at once split by commas or line breaks) | trimmed, then judged by the rule the transcription stage applies (1-40 characters, no Unicode "other" character); a refusal says why beside the box and the text stays there to fix; a refused entry is never sent; at 200 the Add button is off with its reason; commas and line breaks split, one plain word is typed as usual | test_word_list_add_remove_and_save_body, test_word_list_stops_at_200_and_says_why, test_word_list_rules_match_the_transcription_stage |
| Replacement rows (empty, half-filled, one wrong spelling with two corrections, identical rows, removed rows) | an empty row is ignored; a half-filled row is judged once it is left and then blocks Save; a clashing pair is marked at once, is not part of the change and blocks Save; an identical pair goes once; the body is `[{from, to}]` | test_word_list_replacement_rows |
| Word list read from the server or settings.toml with markup, bidi / zero-width / NUL characters, a 5000-character entry, `constructor`, or no word list keys at all | text nodes only (no element, no script), the remove button is named with the entry; entries the engine would refuse are marked `!` and block saving the list; a missing key is an empty list | test_word_list_text_is_inert, test_word_list_without_engines_or_keys |
| PUT /api/settings refusing the word list (the real server's answers: control character, 41 characters, 201 entries, conflicting pair, wrong shape) | the field shows the reason in the display language (an answer with no sentence of ours: as the server wrote it) and the status code; the draft stays; editing the list clears the stale line | test_word_list_server_errors_are_shown_in_words |
| `vocabulary` in `providers.consent` (box in settings, checkbox in setup step 4) | off when an engine is turned on, in the request only after the tick, never for an engine without the transcript (box off, with the reason); the sentence says what yes and no do | test_word_list_consent_box_in_settings, test_setup_step_4_has_the_word_list_checkbox, test_every_consent_field_the_server_accepts_is_named_on_every_screen |
| Review codes and sent fields on the minutes screen (`asr_dropped`, `speaker_review`, `unsupported_owner` / `_deadline` / `_number`, `weak_citation`; an unknown code, tags as a code, 37 reasons; `vocabulary` and an unknown name in `sent_fields`) | every code the engine writes has a Korean and an English sentence that means what render.py writes into the note; an unknown code is shown as text; six chips at most, the engine's own flags first and the rest counted; field names by name, never "undefined" | test_review_reasons_have_sentences_in_both_languages, test_many_review_reasons_keep_the_engines_flags_in_view, test_sent_fields_name_the_word_list |
| Search text typed or restored from the address (`?q=`): empty, one character, spaces around or inside, `대 출` (two characters), 100 / 101 characters, control and zero-width characters, markup | the rule of `search.query` (2..100 characters without spaces counted, no Unicode "other" characters): nothing outside it is ever sent, and the box says why; a valid text is asked for after a 300 ms pause (at once on Enter), once, and only the newest answer is shown | test_search_waits_for_a_pause_and_needs_two_characters, test_search_box_sends_exactly_what_the_engine_accepts, test_search_text_comes_back_from_the_address |
| GET /api/search answers with markup, `javascript:` or quote-carrying job and line ids, bidi / NUL characters, a 5000-character title, missing fields, a wrong `total`, non-objects among the items | text nodes only (hits in `<mark>`), controls removed, lengths bounded; links are only `/notes/<id>` with `#t<n>` or `#sum` (a bad line id adds no anchor); items without a job id are dropped; a wrong total ends the list | test_search_result_text_is_inert, test_search_answers_the_screens_read_match_the_schema |
| A search that fails (400 with the engine's sentence, the engine down), a slow answer overtaken by a newer text, a second page that fails | the sentence and its status code with a Try again button; the old results stay when only "more" fails; an older answer never replaces a newer one | test_search_results_are_grouped_by_meeting_and_link_to_the_line, test_search_waits_for_a_pause_and_needs_two_characters |
| `/`, ⌘K and Ctrl+K on a screen: in a text box, with a modifier or `?`, while composing, on a checkbox, with another dialog open | the box opens (Notes: the inline box; elsewhere a dialog that Esc closes and hands the focus back from); a slash typed in a field, composing text, a modifier, and a second dialog are left alone | test_slash_and_cmd_k_open_the_search_on_every_screen, test_on_the_notes_screen_the_keys_go_to_the_box_not_a_dialog |
| Summary headings typed or read from settings: empty, 41 characters, control / zero-width / bidi characters, markup, a 5000-character heading, the 13th, removing the last one, a type with no key | the rule of `config._validate` (1-40 characters, 1-12 per type, no "other" characters); an empty row says so once it was left, the others at once; a list that cannot be sent blocks Save (types with problems open, rows in red) and is never sent; a type with no key shows the engine's default headings, which are compared with `postprocess.TYPE_SECTIONS` | test_summary_layout_memo_and_daily_note_are_edited_and_saved, test_summary_layout_defaults_and_rules_match_the_engine, test_summary_layout_text_is_inert, test_summary_layout_without_the_keys_is_defaults_and_saves_only_the_change |
| Summary preference: 501 characters, a line break typed or pasted, control characters, markup | counted in characters (not UTF-16 units); a line break becomes a space and says so; over 500 or invisible characters block Save with the count; the text is a value, never markup | test_summary_layout_memo_and_daily_note_are_edited_and_saved, test_summary_layout_text_is_inert |
| Short-memo minimum: 3, 400, letters, minimum not below the minimum length | 5-299 seconds, a whole number; a wrong value blocks Save with the field's sentence; a minimum at or above the minimum length is said in words (no recording would become a memo); the field is off, with its reason, while memos are off | test_summary_layout_memo_and_daily_note_are_edited_and_saved |
| Daily-note path: `../x.md`, `a{x}.md`, `a\b.md`, not `.md`, invisible characters, 4097 characters, empty; a notes folder with no Obsidian vault or under a symbolic link (only the engine can tell) | the syntax rule of `daily.template_path` (compared with the engine on a corpus); empty means off; the engine's refusal is shown in words with the status code; editing the path takes the old line away | test_summary_layout_defaults_and_rules_match_the_engine, test_summary_layout_server_refusals_are_shown_in_words, test_summary_layout_memo_and_daily_note_are_edited_and_saved |

The update UI tests run the real front-end modules in node against a fake DOM, fake fetch and fake EventSource. Their API answers are
fixtures shaped like selfupdate.Updates.snapshot() (7-character hashes, ISO dates with offsets, Korean error sentences) and are
validated against schema.json when it defines Update: verification level is "assumed answers", not a running engine.

The search and summary layout tests (tests/ui_find_scenarios.js, spliced into the same harness) run the same way. The search answers, the 400 bodies, and the
rules (compared with search.query and config._validate) are the real engine's; the bodies the settings screen sends are accepted by the real PUT /api/settings
and land in settings.toml. Verification level: assumed answers in a fake DOM plus real engine answers on synthetic meetings. A real run (headless Chromium
against `quietclerk serve` on a temporary root holding the two demo meetings, docs/examples) covered search ("대출", "ride pass", a third synthetic meeting for
"more"), the dialog and shortcuts, and saving every new setting into settings.toml; no real recording and no samples/ file was used.

The word list tests (settings, setup step 4, minutes) run the real front-end modules in node the same way. Where it is cheap the answers they
read are real: the 400 bodies come from PUT /api/settings on the real app, the minutes page data and GET /api/jobs/{id} from the real app, the
review codes from render.components, and the entry rule is compared with backends/quality.py. Verification level of these tests: assumed
answers in a fake DOM (no browser, no running engine). They use typed text, not recordings, so no samples/ file is involved.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import artifacts, backfill, config, notes, render, store
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.serve import Runtime
from quietclerk.server import SCREENS, STATIC, create_app

SCREEN_PATHS = ['/home', '/jobs', '/notes', '/notes/some-job', '/backlog', '/settings', '/migrate',
                *(f'/setup/{n}' for n in range(1, 7))]
SCHEMA = json.loads((Path(__file__).parents[1] / 'quietclerk/server/schema.json').read_text())


class UnavailableSync:
    def __init__(self, settings):
        pass

    def folder(self):
        raise FileNotFoundError('synthetic unavailable')

    backlog = pairing = folder


class IdleExecutor:
    def __init__(self, *args):
        pass

    def run_one(self, **kwargs):
        return None


@pytest.fixture
def settings(tmp_path):
    return config.load(tmp_path / 'settings.toml', environ={
        'QC_ROOT': str(tmp_path), 'QC_SINCE': '1970-01-01 00:00', 'QC_STABLE_SEC': '0', 'QC_MIN_DURATION_SEC': '0'})


@pytest.fixture
def api(settings, tmp_path):
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, sync_factory=UnavailableSync, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        yield client, runtime, base


@pytest.fixture
def live(settings, tmp_path):
    """A started runtime (execution lock held, executor idle) so migration can run on its thread."""
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=IdleExecutor, scan=lambda *a, **k: None)
    app = create_app(runtime, sync_factory=UnavailableSync, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        yield client, runtime, base


def login(client, runtime, base):
    token = read_bootstrap(runtime.support)['token']
    response = client.post('/api/session', json={'token': token}, headers={'Origin': base})
    assert response.status_code == 204
    client.headers.update({'Origin': base, 'X-CSRF-Token': response.headers['X-CSRF-Token']})
    return response


def minutes(runtime, job_id='20261110-100000-abc12345', texts=('hello <b>one</b>', 'two'), summary=None, skip_meta=(), tamper=()):
    """A published job with verified run artifacts, as the pipeline writes them."""
    root = runtime.settings.root
    run_id = 'run-1'
    with closing(store.connect(runtime.db)) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'meeting.m4a', str(root / 'archive' / job_id / 'source.m4a'), 120)
        con.execute('INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at,finished_at) '
                    "VALUES(?,?,'auto',?,?,'done',1,2)", (run_id, job_id, json.dumps({}), json.dumps({})))
        con.execute("UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons=? WHERE job_id=?",
                    (run_id, str(root / 'notes' / 'x.md'), json.dumps(['unknown_citation:t9']), job_id))
    directory = root / 'work' / job_id / 'runs' / run_id
    directory.mkdir(parents=True)
    payloads = {
        'turns.json': [{'start': 1.0 + i, 'end': 2.0 + i, 'speaker': 'S1', 'text': text} for i, text in enumerate(texts)],
        'corrected.json': {'texts': list(texts), 'notes': []},
        'classification.json': {'meta': {'title': 'T', 'type': 'meeting', 'division': 'work', 'speakers': {
            'S1': {'role': 'host', 'name': None, 'name_id': None, 'split_suspect': False}}}},
        'summary.json': {'text': summary or '## 핵심 요약\n- first point [t1]\n- second [t2, t9]\n'},
    }
    for name, payload in payloads.items():
        part = directory / (name + '.part')
        artifacts.write_json(part, payload)
        artifacts.commit(directory / name, part, stage=name, run_id=run_id, inputs={}, params={})
        if name in skip_meta:
            artifacts.metadata(directory / name).unlink()
        if name in tamper:
            (directory / name).write_text(json.dumps(payload) + ' ')
    return job_id, directory


def island(html):
    match = re.search(r'<script type="application/json" id="qc-data">(.*?)</script>', html, re.S)
    return match and match.group(1)


# ---- authentication boundary

def test_screen_paths_give_no_data_without_a_session(api):
    client, runtime, base = api
    job_id, _ = minutes(runtime, texts=('SECRET-TRANSCRIPT',))
    for path in [*SCREEN_PATHS, f'/notes/{job_id}']:
        for forged in (None, 'forged'):
            client.cookies.clear()
            if forged:
                client.cookies.set('qc_session', forged)
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303 and response.headers['location'] == '/', path
            assert response.content == b'' and 'SECRET' not in response.text
            assert "default-src 'self'" in response.headers['content-security-policy']
    # The bootstrap shell the redirect lands on is data-free; it is the only HTML before sign-in.
    shell = client.get('/')
    assert shell.status_code == 200 and 'qc-data' not in shell.text and 'SECRET' not in shell.text
    # A rebinding Host is refused even for a signed-in browser.
    login(client, runtime, base)
    assert client.get('/home', headers={'Host': 'attacker.test'}).status_code == 403
    assert client.get('/notes/' + job_id, headers={'Host': 'attacker.test'}).status_code == 403
    # Signing out takes the screens away again.
    assert client.post('/api/logout').status_code == 204
    client.cookies.clear()
    assert client.get('/notes/' + job_id, follow_redirects=False).status_code == 303


def test_static_files_need_a_session(api):
    client, runtime, base = api
    names = sorted(path.relative_to(STATIC).as_posix() for path in STATIC.rglob('*') if path.is_file())
    assert {'qc.css', 'app.js', 'seogi.svg', 'lib/dom.js', 'screens/home.js'} <= set(names)
    for name in names:
        response = client.get('/static/' + name, follow_redirects=False)
        assert response.status_code == 401 and response.json() == {'error': 'unauthorized'}, name
    login(client, runtime, base)
    types = {'.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml'}
    for name in names:
        response = client.get('/static/' + name)
        assert response.status_code == 200 and response.content, name
        assert response.headers['content-type'].split(';')[0] == types[Path(name).suffix]
        assert response.headers['cache-control'] == 'no-store' and response.headers['x-content-type-options'] == 'nosniff'
        assert "default-src 'self'" in response.headers['content-security-policy']


@pytest.mark.parametrize('path', ['/static/../auth.py', '/static/%2e%2e/auth.py', '/static/..%2fauth.py', '/static/lib/../../auth.py',
                                  '/static/lib', '/static/lib/', '/static/', '/static', '/static//etc/passwd', '/static/qc.css%00',
                                  '/static/app.js/', '/static/%2Fetc%2Fpasswd', '/static/LIB/DOM.JS', '/static/.hidden'])
def test_static_lookup_is_an_exact_name_index(api, path):
    client, runtime, base = api
    login(client, runtime, base)
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (307, 308, 404), (path, response.status_code)
    assert b'import ' not in response.content and b'class Auth' not in response.content


def test_screens_are_one_fixed_shell_without_inline_code(api):
    client, runtime, base = api
    login(client, runtime, base)
    job_id, _ = minutes(runtime)
    for path in [*(p for p in SCREEN_PATHS if p != '/notes/some-job'), f'/notes/{job_id}']:
        response = client.get(path)
        html = response.text
        assert response.status_code == 200, path
        assert response.headers['content-security-policy'] == ("default-src 'self'; object-src 'none'; base-uri 'none'; "
                                                               "frame-ancestors 'none'; form-action 'self'")
        assert response.headers['cache-control'] == 'no-store' and response.headers['referrer-policy'] == 'no-referrer'
        scripts = re.findall(r'<script\b([^>]*)>', html)
        expected = [' type="module" src="/static/app.js"'] + ([' type="application/json" id="qc-data"'] if path.startswith('/notes/') else [])
        assert scripts == expected, (path, scripts)
        assert not re.search(r'\sstyle\s*=', html) and not re.search(r'\son\w+\s*=', html) and 'javascript:' not in html
        assert not re.search(r'(?:src|href)\s*=\s*"(?:https?:)?//', html) and 'http://' not in html.replace('http://www.w3.org', '')
        assert 'qc-data' not in html or path.startswith('/notes/')
    assert client.get('/setup/7').status_code == 404 and client.get('/setup/0').status_code == 404


def test_language_attribute_follows_the_ui_language_setting(api):
    client, runtime, base = api
    login(client, runtime, base)
    assert client.put('/api/settings', json={'ui.language': 'en'}).status_code == 200
    assert '<html lang="en">' in client.get('/home').text
    assert client.put('/api/settings', json={'ui.language': 'ko'}).status_code == 200
    assert '<html lang="ko">' in client.get('/home').text


def test_unauthenticated_regex_covers_exactly_the_screen_routes():
    for path in SCREEN_PATHS:
        assert SCREENS.fullmatch(path), path
    for path in ['/', '/api/status', '/static/app.js', '/setup/7', '/notes/a/b', '/notes/', '/home/x', '/homepage']:
        assert not SCREENS.fullmatch(path), path


# ---- the minutes screen (the only one that carries text the engine or a speaker produced)

def test_note_data_block_is_html_safe_and_text_is_verbatim(api):
    client, runtime, base = api
    hostile = '</script><script>window.pwned=1</script><img src=x onerror=alert(1)> [x](https://evil.example) [[#^t1|x]] {{7*7}} \u2028'
    job_id, _ = minutes(runtime, texts=(hostile, 'second'), summary='## 핵심 요약\n- <b>bold</b> point [t1, t9]\n## 할 일\n- [ ] do it [t2]\n')
    login(client, runtime, base)
    response = client.get('/notes/' + job_id)
    assert response.status_code == 200
    block = island(response.text)
    assert block is not None and '<' not in block and '>' not in block and '</script' not in block
    assert response.text.count('<script') == 2   # the module and the data block only
    data = json.loads(block)
    assert data['found'] is True and data['turns'][0]['text'] == hostile and data['turns'][1]['id'] == 't2'
    first = data['sections'][0]['items'][0]
    assert first['text'] == '<b>bold</b> point' and [c['ok'] for c in first['cites']] == [True, False]
    assert first['cites'][0] == {'id': 't1', 'ok': True, 'start': 1.0, 'end': 2.0}
    assert data['sections'][1]['kind'] == 'tasks' and data['sections'][1]['items'][0]['task'] is True
    assert data['review_reasons'] == ['unknown_citation:t9'] and data['note_state'] == 'missing'


def test_note_screen_unknown_job_and_path_like_ids(api):
    client, runtime, base = api
    login(client, runtime, base)
    for job_id in ('nope', "x'; DROP TABLE jobs;--", 'a' * 5000):
        response = client.get('/notes/' + job_id)
        assert response.status_code == 404, job_id
        data = json.loads(island(response.text))
        assert data['found'] is False and data['unknown'] is True and 'turns' not in data
    # An encoded slash makes it two path segments: no screen route matches, so there is not even a shell.
    for job_id in ('..%2f..%2fetc%2fpasswd', 'a%2fb'):
        response = client.get('/notes/' + job_id)
        assert response.status_code == 404 and island(response.text) is None
    assert client.get('/notes/a/b').status_code == 404
    with closing(store.connect(runtime.db)) as con:
        assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0   # the table still exists and nothing was written


@pytest.mark.parametrize('how', ['no-meta', 'tampered', 'symlink', 'malformed', 'wrong-shape'])
def test_unverified_artifacts_are_never_shown(api, tmp_path, how):
    client, runtime, base = api
    job_id, directory = minutes(runtime, skip_meta=('turns.json',) if how == 'no-meta' else (),
                                tamper=('summary.json',) if how == 'tampered' else ())
    if how == 'symlink':
        outside = tmp_path / 'outside.json'
        outside.write_text('{"text": "## 핵심 요약\\n- leaked [t1]"}')
        (directory / 'summary.json').unlink()
        (directory / 'summary.json').symlink_to(outside)
    if how == 'malformed':
        (directory / 'turns.json').write_text('{not json')
    if how == 'wrong-shape':
        part = directory / 'corrected.json.part'
        artifacts.write_json(part, {'texts': ['only one'], 'notes': []})   # fewer texts than turns
        artifacts.commit(directory / 'corrected.json', part, stage='corrected', run_id='run-1', inputs={}, params={})
    login(client, runtime, base)
    data = json.loads(island(client.get('/notes/' + job_id).text))
    assert data == {'job_id': job_id, 'found': False}


def test_deleted_and_legacy_jobs_show_no_minutes(api):
    client, runtime, base = api
    job_id, _ = minutes(runtime)
    with closing(store.connect(runtime.db)) as con:
        con.execute("UPDATE jobs SET legacy=1 WHERE job_id=?", (job_id,))
    login(client, runtime, base)
    assert json.loads(island(client.get('/notes/' + job_id).text)) == {'job_id': job_id, 'found': False}


# ---- the front-end sources are part of the policy

def test_front_end_has_no_markup_sinks(api):
    sinks = [r'\.innerHTML', r'\.outerHTML', r'insertAdjacentHTML', r'document\.write', r'\beval\s*\(', r'new\s+Function', r'setAttribute\(\s*[\'"]style',
             r'srcdoc', r'javascript:', r'createContextualFragment', r'DOMParser', r'\.srcObject', r'importScripts', r'new\s+Worker', r'XMLHttpRequest']
    for path in sorted(STATIC.rglob('*.js')):
        source = path.read_text()
        for sink in sinks:
            assert not re.search(sink, source), (path.name, sink)
        # No absolute URLs: only same-origin paths and the SVG namespace may appear.
        assert not re.findall(r'https?://(?!www\.w3\.org/2000/svg)', source), path.name
        assert not re.search(r'(?<![\w.])fetch\(\s*[\'"`]https?:', source), path.name
    css = (STATIC / 'qc.css').read_text()
    assert '@import' not in css and not re.search(r'url\(\s*[\'"]?(?:https?:|//|data:)', css)
    bootstrap = (Path(__file__).parents[1] / 'quietclerk/server/bootstrap.js').read_text()
    assert bootstrap.index("fetch('/api/session'") < bootstrap.index("location.replace(")


# ---- note migration API

def legacy_note(output, job_id, filename='old.md', kind='회의'):
    path = output / filename
    path.write_text('---\nsource: "meeting.m4a"\nrecorded: 2026-11-10 10:00\nduration_min: 1.7\n'
                    f'speakers: 2\njob_id: {job_id}\ntranscribe: asr\npostprocess: codex\ntags: [회의록, 자동전사]\n유형: {kind}\n'
                    '---\n# My original title\n\n## 메모\nOriginal user body\r\n')
    return path


def vault_state(root, output):
    files = {str(p.relative_to(output)): (p.read_bytes(), p.stat().st_mtime_ns) for p in output.rglob('*') if p.is_file()}
    with closing(sqlite3.connect(root / 'state.sqlite3')) as con:
        meta = sorted(con.execute('SELECT key,value FROM meta').fetchall())
    return files, meta, (root / 'note-backups').exists()


def seed_legacy(runtime, kind='회의'):
    output = Path(runtime.settings.get('output'))
    output.mkdir(parents=True, exist_ok=True)
    with closing(store.connect(runtime.db)) as con:
        job = store.add_job(con, '20261110-100000-abc', 'abc', 'meeting.m4a', '/unused', 100)
    return output, legacy_note(output, job['job_id'], kind=kind)


def test_migration_policy_unauthenticated_is_401_and_no_csrf_is_403(api):
    client, runtime, base = api
    output, target = seed_legacy(runtime)
    before = vault_state(runtime.settings.root, output)
    assert client.get('/api/notes/migration').status_code == 401
    assert client.post('/api/notes/migration', json={'consent': True}, headers={'Origin': base}).status_code == 401
    login(client, runtime, base)
    headers = {'X-CSRF-Token': ''}
    assert client.post('/api/notes/migration', json={'consent': True}, headers=headers).status_code == 403
    assert client.post('/api/notes/migration', json={'consent': True}, headers={'Origin': 'http://attacker.test'}).status_code == 403
    assert vault_state(runtime.settings.root, output) == before


@pytest.mark.parametrize('body', [{}, {'consent': False}, {'consent': 'true'}, {'consent': 1}, {'consent': None},
                                  {'consent': True, 'extra': 1}, {'consent': [True]}, {'apply': True}])
def test_migration_policy_without_exact_consent_is_400_and_changes_nothing(live, body):
    client, runtime, base = live
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.post('/api/notes/migration', json=body)
    assert response.status_code == 400 and 'consent' in response.json()['error']
    assert vault_state(runtime.settings.root, output) == before
    assert client.post('/api/notes/migration', content=b'not json', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.post('/api/notes/migration', content=b'[true]', headers={'Content-Type': 'application/json'}).status_code == 400
    assert vault_state(runtime.settings.root, output) == before


def test_migration_preview_changes_nothing(api):
    client, runtime, base = api
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.get('/api/notes/migration')
    assert response.status_code == 200
    body = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationState'}).validate(body)
    entry = body['preview']['entries'][0]
    assert body['migrated'] is False and body['task'] is None and entry['job_id'] == '20261110-100000-abc'
    assert {'from_key': 'recorded', 'from_value': '2026-11-10 10:00', 'to_key': 'started_at', 'to_value': '2026-11-10T10:00:00'} in entry['mapping']
    assert not body['preview']['conflicts'] or all(not c['blocking'] for c in body['preview']['conflicts'])
    assert vault_state(runtime.settings.root, output) == before and notes.parse_note(target.read_bytes())[0].get('qc_schema') is None


def test_migration_runs_on_the_executor_thread_and_reports_completion(live):
    client, runtime, base = live
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    original = target.read_bytes()
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 200
    manifest = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationDone'}).validate(manifest)
    assert manifest['done'] is True and manifest['entries'][0]['state'] == 'done' and 'mapping' not in manifest['entries'][0]
    props, body = notes.parse_note(target.read_bytes())
    assert props['qc_schema'] == 2 and body == notes.parse_note(original)[1]
    backup = Path(manifest['backup_dir']) / 'old.md'
    assert backup.read_bytes() == original and not backup.is_relative_to(output)
    state = client.get('/api/notes/migration').json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/MigrationState'}).validate(state)
    assert state['migrated'] is True and state['task'] == {'state': 'done'}
    assert not [e for e in state['preview']['entries'] if not e.get('skip')]
    assert client.post('/api/notes/migration', json={'consent': True}).status_code == 200   # idempotent: nothing left to convert


def test_migration_still_waiting_is_202_and_a_later_get_shows_it_running(api):
    client, runtime, base = api   # the runtime is not started: nothing ever runs the queued task
    output, target = seed_legacy(runtime)
    login(client, runtime, base)
    before = target.read_bytes()
    started = time.monotonic()
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 202 and response.content == b'' and 0.9 < time.monotonic() - started < 5
    assert target.read_bytes() == before
    state = client.get('/api/notes/migration').json()
    assert state['migrated'] is False and state['task'] == {'state': 'running'}


def test_migration_conflict_is_409_with_reason(live):
    client, runtime, base = live
    output, target = seed_legacy(runtime, kind='워크숍')   # a type value the table does not know: blocking
    login(client, runtime, base)
    before = vault_state(runtime.settings.root, output)
    response = client.post('/api/notes/migration', json={'consent': True})
    assert response.status_code == 409
    body = response.json()
    Draft202012Validator(SCHEMA | {'$ref': '#/$defs/NoteConflictError'}).validate(body)
    assert body['error'] == 'note_conflict' and body['reason'] == 'migration_conflicts'
    assert vault_state(runtime.settings.root, output)[0] == before[0]
    assert client.get('/api/notes/migration').json()['task'] == {'state': 'failed', 'reason': 'migration_conflicts'}


def test_migration_preview_of_a_vault_inside_the_backup_root_is_409(api, tmp_path):
    client, runtime, base = api
    login(client, runtime, base)
    # The backup root (<root>/note-backups) may not be inside the vault.
    assert client.put('/api/settings', json={'output': str(tmp_path)}).status_code == 200
    response = client.get('/api/notes/migration')
    assert response.status_code == 409 and response.json()['reason'] == 'backup_must_be_outside_vault'


# ---- other API behaviour found while wiring the screens

def test_integration_runtime_error_is_503_not_500(api, monkeypatch):
    client, runtime, base = api
    login(client, runtime, base)

    def refuse(names, settings=None):
        raise RuntimeError('no Syncthing folder at the inbox')
    monkeypatch.setattr(backfill, 'request', refuse)
    response = client.post('/api/backlog/request', json={'names': ['a.m4a']})
    assert response.status_code == 503 and response.json() == {'error': 'local integration unavailable'}


# ---- update band, "what's new" dialog and the settings card: the real front-end modules run in node

NODE = shutil.which('node') or shutil.which('bun')
needs_node = pytest.mark.skipif(NODE is None, reason='the update UI tests run the front-end modules in node (or bun)')

OLD = {'commit': '3018b39', 'date': '2026-11-09T10:00:00+09:00'}
NEW = {'commit': '5383fb0', 'date': '2026-11-10T11:30:00+09:00'}
CHANGES = [{'commit': '5383fb0', 'date': '2026-11-10T11:30:00+09:00', 'title': 'update band on every screen'},
           {'commit': 'bf268aa', 'date': '2026-11-10T09:12:44+09:00', 'title': 'show the saved port after a restart'},
           {'commit': '37811ba', 'date': '2026-11-09T22:01:10+09:00', 'title': '긴 회의에서 요약이 멈추지 않게 했어요'}]
UPDATE_REASONS = ['local_changes', 'wheel_install', 'no_checkout', 'diverged', 'no_remote', 'offline', 'check_disabled', 'job_running']


def update_body(**changes):
    """GET /api/update as selfupdate.Updates.snapshot() writes it (short hashes, ISO dates, UTC check time)."""
    return {'state': 'current', 'reason': None, 'installed': OLD, 'latest': OLD, 'behind': 0, 'changes': [],
            'checked_at': '2026-11-10T04:10:57.065368+00:00', 'finished_at': None, 'last_error': None} | changes


UPDATE_BODIES = {
    'current': update_body(),
    'available': update_body(state='available', latest=NEW, behind=3, changes=CHANGES),
    'scheduled': update_body(state='scheduled', reason='job_running', latest=NEW, behind=3, changes=CHANGES),
    'updating': update_body(state='updating', latest=NEW, behind=3, changes=CHANGES),
    # The backend leaves the applied changes in the body after the update.
    'done': update_body(state='done', installed=NEW, latest=NEW, changes=CHANGES, finished_at='2026-11-10T04:10:58.086695+00:00'),
    'failed': update_body(state='failed', latest=NEW, behind=3, changes=CHANGES, finished_at='2026-11-10T04:10:58.604222+00:00',
                          last_error='업데이트하지 못해 이전 버전으로 돌아왔어요.'),
    'unavailable': update_body(state='unavailable', reason='local_changes', latest=None),
}
TEXT = {
    'ko': {'available': '새 버전이 있어요 · 변경 3개', 'many': '새 버전이 있어요 · 변경 20개', 'plain': '새 버전이 있어요',
           'scheduled': '처리 중인 녹음이 끝나면 업데이트해요', 'updating': '업데이트 중…', 'keep': '잠시 화면이 끊겨도 괜찮아요',
           'done': '업데이트했어요 (3018b39 → 5383fb0)', 'done_bare': '업데이트했어요', 'failed': '업데이트하지 못해 이전 버전으로 되돌렸어요',
           'update': '업데이트', 'changes': '변경 내용', 'ok': '확인', 'starting': '시작하는 중…', 'lost': '엔진과 연결이 끊겼어요.',
           'engine_restarting': '업데이트 중 · 다시 연결하는 중', 'engine_lost': '엔진 연결 끊김', 'unreachable': '엔진에 닿지 못했어요.',
           'dialog': '변경 내용', 'update_now': '지금 업데이트', 'close': '닫기',
           'label': '하루 한 번 새 버전 확인', 'help': 'GitHub에 새 버전이 있는지만 묻고, 녹음·회의록은 보내지 않아요', 'section': '업데이트',
           'check': '지금 확인', 'checking': '확인 중…', 'current': '최신 버전이에요', 'generic': '지금은 업데이트할 수 없어요',
           'not_checked': '아직 새 버전을 확인하지 않았어요', 'blocked': '위 결과를 먼저 확인해 주세요',
           'local_changes': '설치 폴더에 직접 고친 파일이 있어 자동 업데이트를 멈췄어요', 'wheel_install': '이 설치 방식은 화면에서 업데이트할 수 없어요',
           'no_checkout': '설치 폴더에서 버전 기록(git)을 찾지 못해 화면에서 업데이트할 수 없어요'},
    'en': {'available': 'A new version is available · 3 changes', 'many': 'A new version is available · 20 changes', 'plain': 'A new version is available',
           'scheduled': 'The update starts when the recording being processed is done', 'updating': 'Updating…', 'keep': "It's fine if the screen drops for a moment",
           'done': 'Updated (3018b39 → 5383fb0)', 'done_bare': 'Updated', 'failed': "Couldn't update, so I went back to the previous version",
           'update': 'Update', 'changes': "What's new", 'ok': 'OK', 'starting': 'Starting…', 'lost': 'Lost connection to the engine.',
           'engine_restarting': 'Updating · reconnecting', 'engine_lost': 'Engine unreachable', 'unreachable': 'Could not reach the engine.',
           'dialog': "What's new", 'update_now': 'Update now', 'close': 'Close',
           'label': 'Check for a new version once a day', 'help': 'Only asks GitHub whether a new version exists; no recordings or minutes are sent', 'section': 'Updates',
           'check': 'Check now', 'checking': 'Checking…', 'current': "You're on the latest version", 'generic': "Updates aren't available right now",
           'not_checked': "Haven't checked for a new version yet", 'blocked': 'Please confirm the result first',
           'local_changes': 'Automatic updates are paused because a file in the install folder was edited by hand',
           'wheel_install': "This kind of install can't be updated from the screen",
           'no_checkout': "The install folder has no version history (git), so it can't be updated from the screen"},
}


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    path = tmp_path_factory.mktemp('update-ui') / 'harness.mjs'
    path.write_text(UPDATE_UI_HARNESS, encoding='utf-8')
    return path


def run_ui(harness, scenario, **params):
    params.setdefault('bodies', UPDATE_BODIES)
    done = subprocess.run([NODE, str(harness), str(STATIC), scenario, json.dumps(params)], capture_output=True, text=True,
                          timeout=60, env=os.environ | {'TZ': 'Asia/Seoul'})
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.rsplit('RESULT ', 1)[1])


def labels(band):
    return [button['text'] for button in band['buttons']]


@pytest.mark.skipif('Update' not in SCHEMA['$defs'], reason='schema.json has no Update definition yet')
def test_update_fixtures_match_the_api_schema():
    for name, body in UPDATE_BODIES.items():
        Draft202012Validator(SCHEMA | {'$ref': '#/$defs/Update'}).validate(body)


def test_update_ui_uses_only_the_four_update_endpoints():
    used = set()
    for path in STATIC.rglob('*.js'):
        used |= set(re.findall(r"""['"`](/api/update[^'"`?]*)""", path.read_text()))
    assert used == {'/api/update', '/api/update/check', '/api/update/apply', '/api/update/dismiss'}


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_update_band_follows_every_state(harness, lang):
    t = TEXT[lang]
    result = run_ui(harness, 'bands', lang=lang)
    first, *steps = result['seen']
    by = {step['state']: step for step in steps}
    assert first['band'] is None and by['unavailable']['band'] is None and steps[-1]['state'] == 'current' and steps[-1]['band'] is None
    available = by['available']['band']
    assert (available['state'], available['role'], available['text']) == ('available', 'status', t['available'])
    assert labels(available) == [t['update'], t['changes']] and not any(button['disabled'] for button in available['buttons'])
    scheduled = by['scheduled']['band']
    assert scheduled['text'].startswith(t['scheduled']) and labels(scheduled) == [t['changes']]
    updating = by['updating']['band']
    assert updating['text'].startswith(t['updating']) and t['keep'] in updating['text'] and updating['progress'] and updating['buttons'] == []
    done = by['done']['band']
    assert (done['kind'], done['text'], labels(done)) == ('banner ok', t['done'], [t['ok']])
    failed = by['failed']['band']
    assert failed['role'] == 'alert' and failed['text'].startswith(t['failed']) and '업데이트하지 못해 이전 버전으로 돌아왔어요.' in failed['text']
    assert labels(failed) == [t['ok']]
    # The shell's polite region says each change once.
    assert by['available']['live'] == t['available'] and by['done']['live'] == t['done'] and by['failed']['live'].startswith(t['failed'])
    # No polling: one read at load, then one per change the event stream announced.
    assert result['calls'].count('GET /api/update') == 1 + len(steps)


@needs_node
def test_update_band_is_on_the_setup_wizard_too(harness):
    result = run_ui(harness, 'wizard', lang='ko')
    assert result['inWizard'] and result['band']['text'] == TEXT['ko']['available']


@needs_node
@pytest.mark.parametrize('answer, after', [('updating', 'updating'), ('scheduled', 'scheduled'), ('conflict', 'available'), ('network', 'available')])
def test_update_click_sends_one_request(harness, answer, after):
    t = TEXT['ko']
    result = run_ui(harness, 'apply', lang='ko', answer=answer, after=after)
    assert result['during']['buttons'][0] == {'text': t['starting'], 'act': 'apply', 'disabled': True}
    (post,) = result['posts']   # two clicks on the button and one on the redrawn one: a single request
    assert post['path'] == '/api/update/apply' and post['csrf'] == 'csrf-1' and post['key'] and 'body' not in post
    band = result['after']
    assert band['state'] == after and not any(button['disabled'] for button in band['buttons'])
    if answer == 'updating':
        assert band['progress'] and result['live'] == t['updating'] and result['gets'] == 2
    elif answer == 'scheduled':
        assert band['text'].startswith(t['scheduled']) and result['live'] == t['scheduled'] and result['gets'] == 2
    elif answer == 'conflict':   # the engine said why; the state is read again
        assert t['local_changes'] in band['text'] and '409 {reason: local_changes}' in band['text'] and result['gets'] == 2
        assert result['live'] == t['local_changes']
    else:
        assert t['unreachable'] in band['text'] and 'engine_unreachable' in band['text'] and result['live'] == t['unreachable']


@needs_node
@pytest.mark.parametrize('lang, waited', [('ko', 0), ('en', 4 * 60 * 1000)])
def test_update_survives_the_engine_restart(harness, lang, waited):
    t = TEXT[lang]
    result = run_ui(harness, 'restart', lang=lang, waited=waited)
    assert result['updating']['text'].startswith(t['updating'])
    down = result['down']
    assert down['band']['state'] == 'updating' and t['keep'] in down['band']['text'] and down['band']['progress']
    assert down['offline'] is None   # no "connection lost" alarm while the update restarts the engine
    assert t['engine_restarting'] in down['engine'] and t['updating'].rstrip('…') in down['chip']
    if waited:   # it did not come back in time: the ordinary engine notice takes over
        late = result['late']
        assert late['band'] is None and late['offline'].startswith(t['lost']) and t['engine_lost'] in late['engine']
    else:
        assert result['late'] is None
    assert result['done']['text'] == t['done']   # the old commit was remembered before the restart
    assert result['calls'] == ['GET /api/session', 'GET /api/update', 'POST /api/update/dismiss']   # new CSRF, the result once, no polling
    assert result['posts'] == ['/api/update/apply', '/api/update/dismiss']
    assert result['after'] is None and result['offline'] is None and result['focus'] == 'main'


@needs_node
def test_update_band_is_gone_when_the_session_is_lost(harness):
    result = run_ui(harness, 'sessionLost', lang='ko')
    assert result['before']['state'] == 'updating'
    assert result['band'] is None and result['offline'] is None and 'quietclerk open' in result['notice']


@needs_node
@pytest.mark.parametrize('state, lang, after', [('done', 'ko', None), ('failed', 'en', 'available')])
def test_update_result_is_confirmed_once(harness, state, lang, after):
    result = run_ui(harness, 'dismiss', lang=lang, state=state)
    assert result['before']['state'] == state and labels(result['before']) == [TEXT[lang]['ok']]
    (post,) = result['posts']   # two clicks, one request
    assert post['path'] == '/api/update/dismiss' and post['csrf'] == 'csrf-1' and post['key']
    if after is None:
        assert result['after'] is None and result['focus'] == 'main'
    else:   # the band that replaces it takes the keyboard focus
        assert result['after']['state'] == after and result['after']['focused']


@needs_node
def test_update_dismiss_failure_keeps_the_result_and_says_why(harness):
    result = run_ui(harness, 'dismiss', lang='ko', state='done', fail=True)
    band = result['after']
    assert band['state'] == 'done' and TEXT['ko']['unreachable'] in band['text'] and 'engine_unreachable' in band['text']
    assert result['live'] == TEXT['ko']['unreachable'] and not band['buttons'][0]['disabled']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_update_changes_dialog(harness, lang):
    t = TEXT[lang]
    result = run_ui(harness, 'dialog', lang=lang)
    view = result['view']
    assert view['open'] and view['labelled'] == 'upd-h' and view['title'] == t['dialog']
    for item, change, date in zip(view['items'], CHANGES, ['11-10 11:30', '11-10 09:12', '11-09 22:01']):
        assert change['title'] in item and change['commit'] in item and date in item
    assert '3018b39 · 11-09 10:00' in view['text'] and '5383fb0 · 11-10 11:30' in view['text'] and '11-10 13:10' in view['text']
    assert [(b['text'], b['act']) for b in view['buttons']] == [(t['close'], 'close'), (t['update_now'], 'apply')]
    assert view['focus'] == 'close' and view['modalFocus']   # the safe button first, focus inside the dialog
    applied = result['applied']
    assert not applied['dialog'] and applied['band']['state'] == 'scheduled' and applied['posts'] == ['/api/update/apply']
    for closed in result['closes']:   # the close button, Esc and the backdrop all hand the focus back
        assert closed['gone'] and closed['focusBack'] == 'changes' and closed['same'], closed


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_update_ui_treats_api_text_as_text(harness, lang):
    t = TEXT[lang]
    result = run_ui(harness, 'hostile', lang=lang)
    markup = {'img', 'script', 'a', 'iframe', 'style', 'link'}
    assert set(result['bandTags']) <= {'b', 'button', 'div', 'span', 'code'}   # nothing in the answer became an element
    assert result['bandText']['text'] == t['many']   # behind was "many": it counted the 20 changes it kept
    dialog = result['dialog']
    assert not markup & set(dialog['tags']) and dialog['items'] == 20 and dialog['longest'] <= 200 and not dialog['controlChars']
    assert '<img src=x onerror=alert(1)>' in dialog['text']   # shown as the characters it is
    odd = result['odd']
    for name in ('nullBody', 'arrayBody', 'stringBody', 'unknown', 'upper', 'listState'):
        assert odd[name] is None, name   # no object, or no known state: no band
    assert odd['failedEvil']['state'] == 'failed' and len(odd['failedEvil']['text']) <= len(t['failed']) + 300
    assert odd['doneBad']['text'] == t['done_bare'] and '(DEF5678)' in odd['doneNoPrev']['text']
    assert odd['negative']['text'] == t['plain']   # no count rather than a negative one


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_settings_update_toggle_and_check(harness, lang):
    t = TEXT[lang]
    cases = {reason: {'state': 'unavailable', 'reason': reason, 'latest': None} for reason in UPDATE_REASONS}
    cases['mystery'] = {'state': 'unavailable', 'reason': 'something_new', 'latest': None}
    cases['not_checked'] = {'state': 'unavailable', 'reason': 'no_checkout', 'checked_at': None, 'latest': None}
    cases['no_git'] = cases['not_checked'] | {'installed': {'commit': '', 'date': None}}
    settings = config.DEFAULTS | {'updates.check': True, 'ui.language': lang, 'server.port': 8765, 'since': '2026-11-09 23:00',
                                  'inbox': '/home/me/QuietClerk/inbox', 'output': '/home/me/QuietClerk/notes'}
    result = run_ui(harness, 'settings', lang=lang, settings=settings, cases=cases)
    toggle = result['toggleView']
    assert (toggle['label'], toggle['help'], toggle['role'], toggle['checked']) == (t['label'], t['help'], 'switch', True)
    assert 'updates.check' in toggle['tags'] and toggle['section'] == t['section'] and t['section'] in toggle['nav']
    saved = result['savedView']   # switched off and saved like any other setting
    assert saved['puts'] == [{'updates.check': False}] and saved['checked'] is False and '1' in saved['bar']
    assert t['current'] in result['initial']['status'] and '11-10 13:10' in result['initial']['status']
    assert result['during']['button'] == {'text': t['checking'], 'act': 'check', 'disabled': True} and result['during']['status'] == t['checking']
    assert result['checked']['posts'] == 1 and '11-10 10:30' in result['checked']['status'] and not result['checked']['button']['disabled']
    by = result['byCase']
    for reason in ('local_changes', 'wheel_install', 'no_checkout'):
        assert t[reason] in by[reason], reason
    sentences = {reason: by[reason] for reason in UPDATE_REASONS}
    assert not any(t['generic'] in sentence for sentence in sentences.values()) and len(set(sentences.values())) == len(UPDATE_REASONS)
    assert t['generic'] in by['mystery']   # an unknown reason gets one plain sentence
    assert t['not_checked'] in by['not_checked'] and t['no_checkout'] in by['no_git']
    assert t['unreachable'] in result['failed'] and 'engine_unreachable' in result['failed']
    available = result['available']
    assert t['available'] in available['status'] and [b['text'] for b in available['buttons']] == [t['check'], t['update'], t['changes']]
    assert '5383fb0' in available['versions'] and available['band']['state'] == 'available'   # the band and the card agree
    pending = result['pending']
    assert pending['button']['disabled'] and pending['why'] == t['blocked'] and pending['band']['state'] == 'failed'
    keys = [post['key'] for post in result['posts']]
    assert keys and all(keys) and len(set(keys)) == len(keys)   # a fresh Idempotency-Key each time
    assert {post['csrf'] for post in result['posts']} == {'csrf-1'} and {post['path'] for post in result['posts']} == {'/api/update/check'}


# ---- the word list (settings), its consent box (settings and setup step 4), the review codes and sent fields (minutes)
# These run the real settings, setup-engines and note modules in node like the update tests above. What the server says
# (the 400 bodies, the note payload, the review codes) is taken from the real server and render.py inside the same test.

WORD_TERMS = ['OpenShift', 'GPU']
WORD_ROWS = [{'from': '책 마루', 'to': '책마루'}]
WORD_CONSENT = {'codex': ['transcript', 'source_name', 'project_list'],
                'claude': ['transcript', 'source_name', 'project_list', 'vocabulary']}
WORD_ENGINES = [{'name': name, 'installed': True, 'logged_in': True, 'tool_block': 'verified', 'endpoint_class': 'external', 'version': '1.0'}
                for name in ('codex', 'claude', 'ollama')]
WORD_FIELDS = ['transcript', 'source_name', 'project_list', 'vocabulary']
FINAL_TERMS = ['GPU', '책마루', 'Kubernetes', 'Open', 'Shift', '쿠버네티스', 'Alpha', 'Beta', 'Gamma']
EVIL_TERMS = ['<img src=x onerror=alert(1)>', '<script>window.pwned=1</script>', 'a\u202eb', 'zero\u200bwidth', '__proto__', 'constructor', 'x' * 5000, '\x00nul']
EVIL_ROWS = [{'from': '<b>x</b>', 'to': '<img src=x onerror=alert(1)>'}, {'from': 'a\x00b', 'to': 'c'}]
EVIL_TYPED = ['<iframe src=javascript:alert(1)>', '<svg onload=alert(1)>']
MARKUP = {'img', 'script', 'iframe', 'style', 'link', 'object', 'embed', 'a'}   # nothing the user or the server typed may become one of these

WORDS = {
    'ko': {'nav': '단어장', 'terms': '이름·용어', 'terms_help': '최대 200개 · 한 개당 40자까지', 'fixes': '틀린 표기 → 바른 표기',
           'fixes_help': '받아쓰기 직후 이 Mac에서만 바꿔요', 'send': '단어장을 보낼 엔진', 'send_help': '동의한 엔진에만 보내요',
           'apply': '다음 녹음부터 적용', 'redo': '이미 만든 회의록에 적용하려면 그 회의록에서 ‘처음부터 다시’를 눌러요', 'example': '예: 책마루',
           'dup': '이미 있어요.', 'long': '41자예요. 40자까지 쓸 수 있어요.', 'empty': '낱말을 적어 주세요.',
           'chars': '제어문자나 보이지 않는 글자는 쓸 수 없어요.', 'full': '200개를 모두 채웠어요. 하나를 지우면 더 넣을 수 있어요.',
           'bulk': '3개를 넣고 2개는 건너뛰었어요 (길이·글자 문제 1, 중복 1).',
           'half': '틀린 표기와 바른 표기를 모두 적어 주세요.', 'conflict': '같은 틀린 표기에 바른 표기가 둘이에요. 하나만 남겨 주세요.',
           'rows_block': '고쳐야 할 행이 있어요. 빨간 행을 고치거나 지워 주세요.',
           'terms_block': '쓸 수 없는 글자가 든 낱말이 있어요. ! 표시한 낱말을 지우고 다시 넣어 주세요.',
           'changes': lambda n: f'바꾼 항목 {n}개', 'none': '바꾼 항목이 없어요', 'saved': '저장했어요.', 'not_saved': '저장하지 못했어요.',
           'remove': '삭제: {}', 'add_row': '행 추가', 'to_check': lambda n: f'확인 필요 {n}', 'more': lambda n: f'외 {n}개',
           'server_chars': '40자까지, 제어문자 없이 적어 주세요.', 'server_many': '최대 200개까지 둘 수 있어요.',
           'server_conflict': '같은 틀린 표기에 바른 표기가 둘이에요. 하나만 남겨 주세요.',
           'yes': '교정·분류·요약 때 단어장도 함께 보내요.', 'no': '단어장 없이 교정해요.',
           'needs': '먼저 설치 마법사 4단계에서 이 엔진에 대화록을 보내도록 허용해야 해요.', 'no_engine': '켜 둔 요약 엔진이 없어요.',
           'sends': '보낼 것: {}', 'nothing': '없음', 'names': ['대화록', '파일 이름', '프로젝트 목록', '단어장'], 'join': '·',
           'used': '쓰는 단계: 교정·분류·요약', 'wiz_name': '단어장',
           'wiz': '동의하면 교정할 때 단어장도 함께 보내 이름·용어를 맞춰 줘요. 동의하지 않으면 단어장 없이 교정해요. 지금 단어장에 2개가 있어요. 단어장 보기',
           'sent': '보낸 것: {}', 'sent_names': ['대화록', '파일 이름', '프로젝트 목록', '단어장'], 'stage': ['교정', '분류', '요약']},
    'en': {'nav': 'Word list', 'terms': 'Names & terms', 'terms_help': 'Up to 200 entries · 40 characters each', 'fixes': 'Wrong → correct spelling',
           'fixes_help': 'Applied on this Mac right after transcription', 'send': 'Engines that get the word list', 'send_help': 'Only engines you allow',
           'apply': 'Applies from the next recording', 'redo': 'press ‘Redo from scratch’ on that note', 'example': 'e.g. Kubernetes',
           'dup': 'Already in the list.', 'long': 'That is 41 characters; the limit is 40.', 'empty': 'Type a word first.',
           'chars': 'Control and invisible characters aren\'t allowed.', 'full': 'The list is full (200). Remove one to add more.',
           'bulk': 'Added 3, skipped 2 (1 with a length or character problem, 1 duplicate).',
           'half': 'Fill in both the wrong and the correct spelling.', 'conflict': 'This wrong spelling has two different corrections. Keep one.',
           'rows_block': 'Some rows need fixing. Correct or remove the ones in red.',
           'terms_block': 'Some entries contain characters that aren\'t allowed. Remove the ones marked ! and add them again.',
           'changes': lambda n: f'{n} change' + ('' if n == 1 else 's'), 'none': 'No changes', 'saved': 'Saved.', 'not_saved': 'Not saved.',
           'remove': 'Remove: {}', 'add_row': 'Add a row', 'to_check': lambda n: f'{n} to check', 'more': lambda n: f'+{n} more',
           'server_chars': 'Up to 40 characters, with no control characters.', 'server_many': 'At most 200 entries are allowed.',
           'server_conflict': 'A wrong spelling has two different corrections. Keep one.',
           'yes': 'The word list is sent along when correcting, classifying and summarising.', 'no': 'Corrects without the word list.',
           'needs': 'First allow the transcript for this engine in setup step 4.', 'no_engine': 'No summary engine is on.',
           'sends': 'Sends: {}', 'nothing': 'nothing', 'names': ['transcript', 'file name', 'project list', 'word list'], 'join': ', ',
           'used': 'Used in: correct, classify, summarize', 'wiz_name': 'Word list',
           'wiz': 'If you agree, the word list goes along when correcting, so names and terms come out right. If not, the text is corrected without it. The word list has 2 now. Open the word list',
           'sent': 'Sent: {}', 'sent_names': ['transcript', 'file name', 'project list', 'word list'], 'stage': ['Correct', 'Classify', 'Summarize']},
}


def word_settings(lang, **changes):
    """GET /api/settings `effective` with a word list and three engines (codex and claude on, ollama on without consent)."""
    return config.DEFAULTS | {'updates.check': False, 'ui.language': lang, 'server.port': 8765, 'since': '2026-11-09 23:00',
                              'inbox': '/home/me/QuietClerk/inbox', 'output': '/home/me/QuietClerk/notes',
                              'vocabulary.terms': WORD_TERMS, 'vocabulary.replace': WORD_ROWS,
                              'providers.order': ['codex', 'claude', 'ollama'], 'providers.consent': WORD_CONSENT} | changes


def sends(t, fields):
    """The "Sends: …" line of an engine row for these consent fields."""
    names = dict(zip(WORD_FIELDS, t['names']))
    return t['sends'].format(t['join'].join(names[field] for field in fields))


@pytest.fixture
def refusals(api):
    """What the real PUT /api/settings answers for each way a word list can be wrong."""
    client, runtime, base = api
    login(client, runtime, base)
    wrong = {'long': {'vocabulary.terms': ['x' * 41]}, 'chars': {'vocabulary.terms': ['a\x00b']},
             'many': {'vocabulary.terms': [f't{i}' for i in range(201)]},
             'conflict': {'vocabulary.replace': [{'from': 'a', 'to': 'b'}, {'from': 'a', 'to': 'c'}]},
             'shape': {'vocabulary.replace': [{'from': 'a'}]}}
    answers = {}
    for name, changes in wrong.items():
        response = client.put('/api/settings', json=changes)
        assert response.status_code == 400 and response.json()['field'] == next(iter(changes)), name
        answers[name] = response.json()
    assert not runtime.settings.path.exists()   # nothing was written
    return answers


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_add_remove_and_save_body(harness, lang):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabAdd', lang=lang, settings=word_settings(lang))
    assert seen['nav'][3] == t['nav'] == seen['section'] and t['redo'] in seen['intro']   # after Language, before Summary engines
    assert [(f['key'], f['label'], f['help']) for f in seen['fields']] == [
        ('vocabulary.terms', t['terms'], t['terms_help']), ('vocabulary.replace', t['fixes'], t['fixes_help']), ('providers.consent', t['send'], t['send_help'])]
    assert all(t['apply'] in f['tags'] and f['key'] in f['tags'] for f in seen['fields'])   # "next recording" chip and the key it saves
    assert seen['placeholder'] == t['example']
    initial = seen['initial']
    assert initial['terms'] == WORD_TERMS and initial['count'] == '2 / 200' and initial['bar'] == t['none']
    added = seen['added']   # typed with spaces around it, then Enter
    assert added['terms'] == [*WORD_TERMS, '책마루'] and added['count'] == '3 / 200' and added['bar'] == t['changes'](1)
    assert added['said'] == '' and added['focus'] == 'f-vt'
    for name in ('dup', 'long', 'empty', 'chars'):   # refused: the list does not change, and the box says why
        view = seen[name]
        assert view['terms'] == [*WORD_TERMS, '책마루'] and view['said'] == t[name] and view['invalid'] == 'true', name
    assert seen['dup']['box'] == '' and seen['long']['box'] == 'x' * 41 and seen['chars']['box'] == 'a\u200bb'   # what must be fixed stays
    assert seen['fixed']['terms'][-1] == 'Kubernetes' and seen['fixed']['said'] == '' and seen['fixed']['invalid'] is None
    bulk = seen['bulk']   # commas and line breaks separate entries; the one refused stays in the box
    assert bulk['terms'][-3:] == ['Open', 'Shift', '쿠버네티스'] and bulk['said'] == t['bulk'] and bulk['box'] == 'y' * 41
    assert seen['paste']['taken'] and seen['paste']['after']['terms'][-3:] == ['Alpha', 'Beta', 'Gamma'] and seen['paste']['after']['box'] == ''
    assert not seen['single']['taken'] and seen['single']['after']['terms'] == seen['paste']['after']['terms']   # one plain word: the box takes it as usual
    removed = seen['removed']
    assert removed['terms'] == FINAL_TERMS and removed['focus'] == t['remove'].format('GPU')   # focus moves on to the next remove button
    saved = seen['saved']
    assert saved['bodies'] == [{'vocabulary.terms': FINAL_TERMS}]   # only the key that changed, as a plain list
    assert saved['view']['terms'] == FINAL_TERMS and saved['view']['bar'] == t['none'] and saved['saveOff'] and t['saved'] in saved['banner']
    assert seen['reverted']['terms'] == FINAL_TERMS and seen['reverted']['bar'] == t['none'] and seen['reverted']['box'] == ''


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_stops_at_200_and_says_why(harness, lang):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabLimit', lang=lang, settings=word_settings(lang, **{'vocabulary.terms': [f'term{i:03d}' for i in range(199)]}))
    assert seen['initial']['count'] == '199 / 200' and not seen['initial']['add']['disabled'] and not seen['initial']['full']
    filled = seen['filled']   # the 200th fits; then the button is off and says why
    assert (filled['terms'], filled['count'], filled['last'], filled['full']) == (200, '200 / 200', 'last', True) and filled['add']['disabled']
    over = seen['over']   # the 201st is not taken, and stays in the box
    assert over['terms'] == 200 and over['said'] == t['full'] and over['box'] == 'over' and over['invalid'] == 'true'
    freed = seen['freed']   # one removed: room again, and the old "full" line is gone with it
    assert freed['terms'] == 199 and not freed['add']['disabled'] and not freed['full'] and freed['said'] == '' and freed['invalid'] is None
    assert seen['again']['terms'] == 200 and seen['again']['last'] == 'over' and seen['body'] == 200


# What the transcription stage refuses for an entry (backends/quality.py _term). The save check in config.py is looser (it only
# refuses ASCII and C1 controls), so the box follows the stage: an entry accepted here must never make a recording fail later.
RULE_CORPUS = ['책마루', 'OpenShift', 'a b', 'x' * 40, 'x' * 41, '한' * 40, '한' * 41, '😀' * 40, '😀' * 41, 'a\u200bb', 'a\u202eb', 'a\u2066b', 'co\u00adop',
               'a\ufeffb', '\ue000', 'a\u00a0b', 'a\u3000b', 'a\tb', 'a\x00b', 'a\x7fb', 'a\x9fb', '<img src=x onerror=alert(1)>', '__proto__', 'ａｂｃ',
               '👨\u200d👩', 'e\u0301', '  padded  ', '\ufeff책마루', '책마루\u200b']


@needs_node
def test_word_list_rules_match_the_transcription_stage(harness):
    from quietclerk.backends import InvalidOutput, quality

    def stage_accepts(term):
        # The box trims like a browser does before sending (a byte order mark copied from a file goes with the spaces).
        sent = term.strip().strip('\ufeff').strip()
        try:
            quality._term(sent)
            return True
        except InvalidOutput:
            return False

    accepted = run_ui(harness, 'vocabRules', lang='ko', settings=word_settings('ko', **{'vocabulary.terms': []}), corpus=RULE_CORPUS)
    assert accepted == {term: stage_accepts(term) for term in RULE_CORPUS}
    assert any(accepted.values()) and not all(accepted.values())   # the corpus covers both answers


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_replacement_rows(harness, lang, refusals):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabRows', lang=lang, settings=word_settings(lang), conflictBody=refusals['conflict'])
    ok = {'said': '', 'invalid': [None, None]}
    first = {'from': '책 마루', 'to': '책마루', **ok}
    assert seen['initial'] == [first] and seen['count'] == '1 / 200' and seen['add'] == {'text': t['add_row'], 'disabled': False}
    assert (seen['field']['label'], seen['field']['help']) == (t['fixes'], t['fixes_help']) and t['apply'] in seen['field']['tags']
    empty = seen['empty']   # a new row is empty and focused; an empty row is not a change
    assert empty['rows'] == [first, {'from': '', 'to': '', **ok}] and empty['focusNew'] and empty['bar'] == t['none']
    assert seen['typing']['rows'][1] == {'from': '큐시', 'to': '', **ok}   # half-filled with the cursor still in the row: no scolding yet
    half = {'from': '큐시', 'to': '', 'said': t['half'], 'invalid': [None, 'true']}   # once the row is left, the empty side is marked
    assert seen['left'] == [first, half]
    blocked = seen['blocked']   # another change makes Save possible; the half-filled row stops it, nothing is sent
    assert blocked['puts'] == 0 and t['rows_block'] in blocked['field'] and t['not_saved'] in blocked['banner'] and blocked['rows'] == [first, half]
    done = {'from': '큐시', 'to': 'QC', **ok}
    assert seen['filled'] == {'rows': [first, done], 'bar': t['changes'](2)}
    clash = {'said': t['conflict'], 'invalid': ['true', 'true']}   # the same wrong spelling with two corrections: both rows are marked at once
    assert seen['conflict']['rows'] == [first, {'from': '큐시', 'to': 'QC', **clash}, {'from': '큐시', 'to': 'QCS', **clash}]
    assert seen['conflict']['bar'] == t['changes'](1)   # the clashing rows are not part of the change
    assert seen['conflictSave']['puts'] == 0 and t['rows_block'] in seen['conflictSave']['field']
    assert seen['identical']['rows'] == [first, done, done] and seen['identical']['bar'] == t['changes'](2)
    saved = seen['saved']   # an identical pair goes once; the body is a list of {from, to}
    assert saved['bodies'] == [{'vocabulary.terms': [*WORD_TERMS, 'Temp'], 'vocabulary.replace': [WORD_ROWS[0], {'from': '큐시', 'to': 'QC'}]}]
    assert saved['rows'] == [first, done] and t['saved'] in saved['banner']
    assert seen['removed']['rows'] == [done] and seen['removed']['focus'] == 'f-vr' and seen['removed']['bar'] == t['changes'](1)
    refused = seen['refused']   # the real server's "conflicting replacements", in words, with the code; the draft stays
    assert refused['field'] == f"{t['server_conflict']} 400 vocabulary.replace"
    assert t['not_saved'] in refused['banner'] and '400 {field: vocabulary.replace}' in refused['banner']
    assert [row['from'] for row in refused['rows']] == ['큐시', 'A'] and refused['bar'] == t['changes'](1)
    assert seen['edited']['field']   # editing the rows clears the stale line


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_server_errors_are_shown_in_words(harness, lang, refusals):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabServer', lang=lang, settings=word_settings(lang), refusals=refusals)
    for step, (name, sentence) in enumerate([('chars', t['server_chars']), ('long', t['server_chars']), ('many', t['server_many'])], start=1):
        entry = seen[name]
        assert entry['field'] == f'{sentence} 400 vocabulary.terms' and entry['replaceField'] is None, name
        assert t['not_saved'] in entry['banner'] and '400 {field: vocabulary.terms}' in entry['banner'], name
        assert entry['terms'][-1] == 'Okay' and entry['bar'] == t['changes'](1) and entry['puts'] == step   # the draft stays, nothing else changed
    shape = seen['shape']   # an answer with no sentence of ours is shown as the server wrote it
    assert shape['field'] is None and shape['replaceField'] == f"{refusals['shape']['error']} 400 vocabulary.replace"
    assert seen['edited'] == {'gone': True, 'terms': ['GPU', 'Okay']}   # editing the list clears the stale line
    saved = seen['saved']
    assert saved['bodies'] == [{'vocabulary.terms': ['GPU', 'Okay']}] and t['saved'] in saved['banner'] and saved['field']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_consent_box_in_settings(harness, lang):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabConsent', lang=lang, settings=word_settings(lang), providers=WORD_ENGINES)
    first = seen['initial']
    assert [(b['checked'], b['disabled']) for b in first['boxes']] == [(False, False), (True, False), (False, True)]
    assert t['no'] in first['boxes'][0]['text'] and t['yes'] in first['boxes'][1]['text'] and t['needs'] in first['boxes'][2]['text']
    assert all('vocabulary' in box['text'] for box in first['boxes'])   # the field name is shown as the code tag
    assert sends(t, WORD_CONSENT['codex']) in first['engines'][0] and sends(t, WORD_CONSENT['claude']) in first['engines'][1]
    assert t['sends'].format(t['nothing']) in first['engines'][2] and first['bar'] == t['none']
    assert (seen['field']['label'], seen['field']['help']) == (t['send'], t['send_help']) and t['apply'] in seen['field']['tags']
    ticked = seen['ticked']   # the engine row follows the box at once; one change
    assert ticked['boxes'][0]['checked'] and t['yes'] in ticked['boxes'][0]['text'] and ticked['bar'] == t['changes'](1)
    assert sends(t, [*WORD_CONSENT['codex'], 'vocabulary']) in ticked['engines'][0]
    assert seen['back']['boxes'] == first['boxes'] and seen['back']['bar'] == t['none'] and seen['back']['engines'] == first['engines']   # ticked and unticked: nothing to save
    saved = seen['saved']
    assert saved['bodies'] == [{'providers.consent': {'codex': [*WORD_CONSENT['codex'], 'vocabulary'], 'claude': WORD_CONSENT['codex']}}]
    assert [box['checked'] for box in saved['boxes']] == [True, False, False] and saved['bar'] == t['none']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_without_engines_or_keys(harness, lang):
    t = WORDS[lang]
    settings = word_settings(lang, **{'providers.order': [], 'providers.consent': {}})
    del settings['vocabulary.terms'], settings['vocabulary.replace']
    seen = run_ui(harness, 'vocabMissing', lang=lang, settings=settings)
    words = seen['words']
    assert words['terms'] == [] and words['listHidden'] and words['count'] == '0 / 200' and seen['rows'] == []
    assert t['no_engine'] in seen['consent'] and seen['links'] == ['/setup/4']
    assert seen['body'] == [{'vocabulary.terms': ['책마루']}]   # the key that was missing is created; the other one is left alone


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_word_list_text_is_inert(harness, lang):
    t = WORDS[lang]
    seen = run_ui(harness, 'vocabHostile', lang=lang, typed=EVIL_TYPED,
                  settings=word_settings(lang, **{'vocabulary.terms': EVIL_TERMS, 'vocabulary.replace': EVIL_ROWS}))
    shown = lambda values: [{'text': value[:60], 'length': len(value)} for value in values]   # noqa: E731
    assert not MARKUP & set(seen['tags']) and seen['links'] == 0   # no entry became an element
    assert seen['typed']['tags'] == seen['tags'] and seen['typed']['pwned'] is None and seen['saved']['tags'] == seen['tags']
    assert seen['chips'] == shown(EVIL_TERMS) and seen['labels'] == [t['remove'].format(term)[:60] for term in EVIL_TERMS]   # shown as the characters they are
    assert seen['typed']['terms'] == shown(EVIL_TYPED)
    assert seen['initial']['marked'] == 4 and seen['initial']['markedNote']   # the entries the engine would refuse are marked "!"
    assert seen['rows'][0] == {'from': '<b>x</b>', 'to': '<img src=x onerror=alert(1)>', 'said': '', 'invalid': [None, None]}
    assert seen['rows'][1]['said'] == t['chars'] and seen['rows'][1]['invalid'] == ['true', 'true']
    blocked = seen['blocked']   # saving with such entries on the screen sends nothing
    assert blocked['puts'] == 0 and t['terms_block'] in blocked['field'] and t['rows_block'] in blocked['rowsField']
    kept = [EVIL_TERMS[i] for i in (0, 1, 4, 5)] + EVIL_TYPED   # tags and prototype names are fine as text
    cleaned = seen['cleaned']['view']
    assert cleaned['marked'] == 0 and cleaned['terms'] == kept
    assert seen['saved']['bodies'] == [{'vocabulary.terms': kept, 'vocabulary.replace': [EVIL_ROWS[0]]}]


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_setup_step_4_has_the_word_list_checkbox(harness, lang):
    t = WORDS[lang]
    only_codex = WORD_CONSENT['codex']
    seen = run_ui(harness, 'wizardConsent', lang=lang, providers=WORD_ENGINES[:2],
                  settings=word_settings(lang, **{'providers.order': ['codex'], 'providers.consent': {'codex': only_codex}}))
    assert [(box['code'], box['checked']) for box in seen['codex']] == [(field, field != 'vocabulary') for field in WORD_FIELDS]
    assert seen['codex'][3]['text'] == f"{t['wiz_name']} vocabulary{t['used']}"
    assert t['wiz'] in seen['codexNote'] and seen['codexLink'] == '/settings#s-vocab' and not seen['claudeHasBoxes']
    enabled = seen['enabled']   # turning an engine on agrees to what it cannot work without, not to the word list
    assert enabled['put'] == [{'providers.order': ['codex', 'claude'], 'providers.consent': {'codex': only_codex, 'claude': only_codex}}]
    assert [box['checked'] for box in enabled['claude']] == [True, True, True, False]
    ticked = seen['ticked']
    assert ticked['put'] == [{'providers.order': ['codex', 'claude'], 'providers.consent': {'codex': only_codex, 'claude': [*only_codex, 'vocabulary']}}]
    assert [box['checked'] for box in ticked['claude']] == [True, True, True, True]
    assert seen['unticked']['put'] == [{'providers.order': ['codex', 'claude'], 'providers.consent': {'codex': only_codex, 'claude': only_codex}}]
    assert seen['noTranscript']['put'] == [{'providers.order': ['codex'], 'providers.consent': {'codex': only_codex}}]   # without the transcript the engine is off
    assert not seen['noTranscript']['claudeOn']


def test_every_consent_field_the_server_accepts_is_named_on_every_screen():
    fields = SCHEMA['$defs']['ProviderConsent']['additionalProperties']['items']['enum']
    assert fields == WORD_FIELDS
    tables = {'screens/settings.js': 'const FIELD_NAMES', 'screens/note.js': 'const FIELD =', 'screens/setup-phone.js': 'const FIELD_NAME',
              'screens/setup-engines.js': 'const FIELDS'}
    for path, anchor in tables.items():
        source = (STATIC / path).read_text()
        lines = []
        for line in source[source.index(anchor):].splitlines():
            lines.append(line)
            if line.rstrip().endswith(';'):
                break
        declaration = '\n'.join(lines)
        assert all(field in declaration for field in fields), (path, fields)


def test_classes_the_word_list_and_review_chips_add_are_styled():
    css = (STATIC / 'qc.css').read_text()
    sources = ''.join((STATIC / 'screens' / name).read_text() for name in ('settings.js', 'note.js'))
    for name in ('terms', 'term', 'term-t', 'bad', 'add-row', 'vrows', 'vrow', 'vf', 'vt', 'vdel', 'vmsg', 'arrow', 'multi'):
        assert re.search(rf'[\'" ]{re.escape(name)}[\'" ]', sources), name   # the screens use it
        assert re.search(rf'\.{re.escape(name)}(?![\w-])', css), name   # and the stylesheet has a rule for it
    assert not re.search(r"chip\('[^']*\bwrap\b", sources)   # `.wrap` is the page layout box (a flex column): a chip must not borrow the name


# The review codes the engine writes, in words. The meaning must match what render.py writes into the note ("Review needed"):
# the words in SAME_MEANING are used by both sentences, so a change on either side shows up here.
REASON_WORDS = {
    'asr_dropped': ('받아쓰기에서 환각·반복이 의심되는 구간을 뺐어요. 원음을 확인해 주세요',
                    'Transcription left out parts that looked like hallucination or repetition. Check the recording'),
    'speaker_review': ('화자 구분을 확인해 주세요 (아주 짧은 화자를 합쳤거나, 화자 수가 상한에 닿았거나, 확신이 낮아요)',
                       'Check the speaker labels (tiny speakers were merged, the speaker cap was reached or confidence was low)'),
    'unsupported_owner': ('할 일 담당이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였어요', 'A task owner is not backed by the lines it cites; it is marked ‘check source’'),
    'unsupported_deadline': ('할 일 기한이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였어요', 'A task deadline is not backed by the lines it cites; it is marked ‘check source’'),
    'unsupported_number': ('숫자나 단위가 인용한 대화록과 달라요. ‘숫자 확인’ 표시를 확인해 주세요',
                           'Some numbers or units differ from the lines they cite. Check the ‘Check numbers’ marks'),
    'weak_citation': ('일부 문장이 인용한 대화록과 겹치는 낱말이 적어요. 근거를 확인해 주세요', 'Some sentences share few words with the lines they cite. Check the evidence'),
    'type_uncertain': ('회의 유형이 확실하지 않아요', 'The meeting type is uncertain'),
    'language_uncertain': ('언어가 섞여 있어요', 'Mixed languages'),
    'summary_review': ('요약에 확인 필요 항목이 있어요', 'The summary has items to check'),
}
SAME_MEANING = {
    'asr_dropped': (['환각·반복'], ['hallucination', 'repetition']),
    'speaker_review': (['화자', '상한'], ['speaker', 'cap', 'confidence']),
    'unsupported_owner': (['담당', '근거 확인'], ['owner', 'check source']),
    'unsupported_deadline': (['기한', '근거 확인'], ['deadline', 'check source']),
    'unsupported_number': (['숫자', '단위', '인용한 대화록'], ['numbers or units', 'cite']),
    'weak_citation': (['인용한 대화록', '근거'], ['cite', 'evidence']),
}
OLDER_REASONS = ['language_uncertain', 'summary_review', 'unknown_citation:t9', 'correct 0-9: failed (x)', 'something_new', '<img src=x onerror=alert(1)>']


def engine_sentence(code, language):
    """The sentence render.py writes in the note's "Review needed" callout for exactly this code."""
    when = datetime(2026, 11, 10, 10)
    job = {'source_name': 'fiction.m4a', 'sha256': 'abc', 'job_id': 'fake', 'duration_sec': 10}
    kwargs = {'asr_dropped': {'dropped': [{'why': 'repetition'}]}, 'speaker_review': {'speaker_review': [{'why': 'ghost'}]}}.get(code, {'review_reasons': [code]})
    props, generated, _ = render.components(job, when, [], [], {'type': 'meeting', 'type_confidence': 'high', 'speakers': {}}, '', [], {}, when, language=language, **kwargs)
    assert props['review_reasons'] == [code]
    return generated.split('[!warning] Review needed' if language == 'en' else '[!warning] 확인 필요', 1)[1].split('\n\n', 1)[0]


def reason_sentence(reason, index):
    if reason.startswith('unknown_citation:'):
        return (f'근거 번호 [?{reason[17:]}]이 대화록에 없어요', f"Evidence ID [?{reason[17:]}] isn't in the transcript")[index]
    if reason in REASON_WORDS:
        return REASON_WORDS[reason][index]
    return ('일부 교정이 실패했어요', 'Some corrections failed')[index] if 'failed' in reason else reason


@pytest.fixture
def note_job(api):
    """A published job whose runs sent text to engines; returns payload(reasons): the minutes page data and GET /api/jobs/{id}."""
    client, runtime, base = api
    login(client, runtime, base)
    job_id, _ = minutes(runtime)
    stages = [('correct', 'codex', 'external', ['transcript', 'vocabulary']),
              ('classify', 'codex', 'external', ['transcript', 'source_name', 'project_list', 'vocabulary']),
              ('summarize', 'claude', 'local', ['transcript', 'constructor'])]
    with closing(store.connect(runtime.db)) as con:
        for stage, provider, endpoint, fields in stages:
            con.execute("INSERT INTO stage_runs(run_id,stage,seq,status,provider,endpoint_class,sent_fields,started_at,finished_at) "
                        "VALUES('run-1',?,1,'done',?,?,?,1,2)", (stage, provider, endpoint, json.dumps(fields)))

    def payload(reasons):
        with closing(store.connect(runtime.db)) as con:
            con.execute('UPDATE jobs SET review_reasons=? WHERE job_id=?', (json.dumps(reasons), job_id))
        return {'jobId': job_id, 'island': island(client.get('/notes/' + job_id).text), 'detail': client.get('/api/jobs/' + job_id).json()}
    return payload


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_review_reasons_have_sentences_in_both_languages(harness, note_job, lang):
    t, i = WORDS[lang], ['ko', 'en'].index(lang)
    for code, (ko_words, en_words) in SAME_MEANING.items():   # the screen says what the engine says
        engine, screen = engine_sentence(code, lang), REASON_WORDS[code][i]
        assert all(word in engine and word in screen for word in (ko_words, en_words)[i]), code
    reasons = [*SAME_MEANING, 'type_uncertain', *OLDER_REASONS]
    for start in range(0, len(reasons), 6):   # six chips are shown at a time: every reason is seen in one chunk or another
        chunk = reasons[start:start + 6]
        missing = [reason for reason in chunk if reason.startswith('unknown_citation:')]
        shown = [reason for reason in chunk if reason not in missing] + missing   # missing evidence IDs go last
        seen = run_ui(harness, 'minutes', lang=lang, **note_job(chunk))
        assert seen['count'].lstrip('!') == t['to_check'](len(chunk))
        assert [chip['text'] for chip in seen['chips']] == [reason_sentence(reason, i) for reason in shown]
        assert all(chip['wrap'].split() == ['chip', 'warn', 'multi'] for chip in seen['chips']) and not MARKUP & set(seen['tags']) and seen['pwned'] is None
        assert not [chip for chip in seen['chips'] if chip['text'] in SAME_MEANING]   # no raw code is left on the screen


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_many_review_reasons_keep_the_engines_flags_in_view(harness, note_job, lang):
    t, i = WORDS[lang], ['ko', 'en'].index(lang)
    reasons = [*(f'unknown_citation:t{n}' for n in range(30)), *SAME_MEANING, 'type_uncertain']   # 31 missing IDs first, as the engine appends them last
    seen = run_ui(harness, 'minutes', lang=lang, **note_job(reasons))
    assert seen['count'].lstrip('!') == t['to_check'](37)
    assert [chip['text'] for chip in seen['chips']] == [reason_sentence(code, i) for code in SAME_MEANING] + [t['more'](31)]   # six shown, the rest counted


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_sent_fields_name_the_word_list(harness, note_job, lang):
    t = WORDS[lang]
    seen = run_ui(harness, 'minutes', lang=lang, **note_job([]))
    rows = dict(seen['sent'])
    correct, classify, summarize = (rows[name] for name in t['stage'])
    sent = lambda *indexes: t['sent'].format(', '.join(t['sent_names'][n] for n in indexes))   # noqa: E731
    assert sent(0, 3) in correct and sent(0, 1, 2, 3) in classify
    assert t['sent'].format(f"{t['sent_names'][0]}, constructor") in summarize   # a name we do not know is shown as text, not as undefined
    assert 'codex' in correct and 'claude' in summarize and 'undefined' not in ''.join(rows.values())


# ---- meeting search and summary layout (contract 10.8 C, E, F, G). The scenarios are in tests/ui_find_scenarios.js and are spliced into the
# harness below when a test runs; the answers the screens read are the real server's wherever that is cheap (search results, 400 bodies).
FIND_SCENARIOS = Path(__file__).with_name('ui_find_scenarios.js')


@pytest.fixture(scope='module')
def find_harness(tmp_path_factory):
    marker = 'const out = await scenarios[scenario](params);'
    assert UPDATE_UI_HARNESS.count(marker) == 1
    path = tmp_path_factory.mktemp('find-ui') / 'harness.mjs'
    path.write_text(UPDATE_UI_HARNESS.replace(marker, FIND_SCENARIOS.read_text(encoding='utf-8') + '\n' + marker), encoding='utf-8')
    return path


def search_meeting(runtime, job_id, title, rows, summary):
    """A published meeting with these (speaker, text) lines and verified run artifacts, indexed for search."""
    from quietclerk import search
    root = runtime.settings.root
    run_id = 'run-' + job_id[-4:]
    with closing(store.connect(runtime.db)) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'meeting.m4a', str(root / 'archive' / job_id / 'source.m4a'), 120)
        con.execute('INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at,finished_at) '
                    "VALUES(?,?,'auto',?,?,'done',1,2)", (run_id, job_id, json.dumps({}), json.dumps({})))
        con.execute("UPDATE jobs SET status='done',current_run_id=?,note_path=?,review_reasons=? WHERE job_id=?",
                    (run_id, str(root / 'notes' / (job_id + '.md')), '[]', job_id))
    directory = root / 'work' / job_id / 'runs' / run_id
    directory.mkdir(parents=True)
    payloads = {
        'turns.json': [{'start': 1.0 + 3 * i, 'end': 3.0 + 3 * i, 'speaker': speaker, 'text': text} for i, (speaker, text) in enumerate(rows)],
        'corrected.json': {'texts': [text for _, text in rows], 'notes': []},
        'classification.json': {'meta': {'title': title, 'type': 'meeting', 'division': 'work', 'speakers': {}}},
        'summary.json': {'text': summary},
    }
    for name, payload in payloads.items():
        part = directory / (name + '.part')
        artifacts.write_json(part, payload)
        artifacts.commit(directory / name, part, stage=name, run_id=run_id, inputs={}, params={})
    with closing(store.connect(runtime.db)) as con:
        search.reindex(con, job_id, root)
    return job_id


KO_TITLE = '책마루 홈 화면 개편과 대출 연장 기능 논의'
EN_TITLE = 'Arbor Bikes App First-Screen Review'


@pytest.fixture
def find_data(api):
    """A Korean and an English meeting, and what the real GET /api/search answers for the searches the screens make."""
    from urllib.parse import quote
    client, runtime, base = api
    login(client, runtime, base)
    ko = search_meeting(runtime, '20261110-100000-aaaa1111', KO_TITLE,
                        [('S1' if i % 2 else 'S2', f'대출 연장 버튼 {i}번 안건을 봅니다 API 응답 시간 확인') for i in range(24)],
                        '## 핵심 요약\n- 대출 연장 버튼을 홈으로 올린다. [t3]\n- API 응답 시간을 잰다. [t5]\n')
    en = search_meeting(runtime, '20261112-140000-bbbb2222', EN_TITLE,
                        [('S1', 'Buying a ride pass takes two taps'), ('S2', 'The ride pass button is hidden two levels deep'), ('S1', 'Leo will measure the unlock API latency')],
                        '## Key summary\n- Ride passes move to the first screen. [t2]\n')
    given = {}
    for text, offset in [('API', 0), ('API', 20), ('ride pass', 0), ('zzzz', 0), ('대 출', 0), ('연장', 0)]:
        response = client.get('/api/search', params={'q': text, 'limit': 20, 'offset': offset})
        assert response.status_code == 200, text
        given[f"/api/search?q={quote(text, safe='')}&limit=20&offset={offset}"] = {'body': response.json()}
    jobs = [{'job_id': job_id, 'source_name': name, 'recorded_at': job_id[:15], 'duration_sec': 157, 'status': 'done', 'note_path': '/v/' + job_id + '.md', 'review_reasons': '[]'}
            for job_id, name in ((ko, '음성 261110_100000.m4a'), (en, 'Recording 261112_140000.m4a'))]
    return {'ko': ko, 'en': en, 'given': given, 'jobs': jobs}


FIND = {
    'ko': {'idle': '제목·대화·요약 안에서 찾아요. 두 글자 이상 입력해 주세요.', 'short': '한 글자만으로는 찾지 않아요. 한 글자 더 입력해 주세요.',
           'bad': '제어문자나 보이지 않는 글자는 찾을 수 없어요.', 'long': '검색어는 100자까지예요.', 'searching': '찾는 중…',
           'part': '일치하는 곳 {total}개 중 {shown}개를 보여 줘요.', 'all': '일치하는 곳 {total}개', 'none': '‘{q}’ 검색 결과가 없어요.', 'nothing': '못 찾았어요.',
           'more': '더 보기 ({left}개 남음)', 'loading': '불러오는 중…', 'moreFailed': '더 가져오지 못했어요. 다시 눌러 주세요.', 'retry': '다시 시도',
           'refused': '요청을 받지 않았어요.', 'down': '엔진에 닿지 못했어요.', 'summary': '요약', 'title': '제목', 'trigger': '회의록 검색', 'foot': 'Esc로 닫아요'},
    'en': {'idle': 'Searches titles, transcripts and summaries. Type at least two characters.', 'short': 'One character is too short to search. Add one more.',
           'bad': 'Control and invisible characters can\'t be searched.', 'long': 'The search text can be up to 100 characters.', 'searching': 'Searching…',
           'part': '{total} matches, showing {shown}.', 'all': '{total} matches', 'none': 'No matches for “{q}”.', 'nothing': 'Nothing found.',
           'more': 'Show more ({left} left)', 'loading': 'Loading…', 'moreFailed': 'Couldn\'t load more. Press it again.', 'retry': 'Try again',
           'refused': 'Request not accepted.', 'down': 'Could not reach the engine.', 'summary': 'Summary', 'title': 'Title', 'trigger': 'Search notes', 'foot': 'Esc to close'},
}


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_search_waits_for_a_pause_and_needs_two_characters(find_harness, find_data, lang):
    t = FIND[lang]
    seen = run_ui(find_harness, 'findRules', lang=lang, jobs=find_data['jobs'], given=find_data['given'])
    assert seen['initial']['status'] == t['idle'] and seen['initial']['requests'] == [] and not seen['initial']['listHidden'] and seen['initial']['rows'] == 2
    assert seen['label'] == t['trigger'] and seen['placeholder']
    for name, said in [('oneChar', 'short'), ('spaces', 'short'), ('control', 'bad'), ('invisible', 'bad'), ('tooLong', 'long')]:
        view = seen[name]
        assert view['status'] == t[said] and view['requests'] == [] and not view['listHidden'], name   # nothing is asked; the list stays
        assert (view['invalid'] == 'true') == (said in ('bad', 'long')) and ('err-text' in view['tone']) == (said in ('bad', 'long')), name
    # three keystrokes inside the pause: no request yet, "searching" is said once, and one request goes out after the pause
    assert seen['typing'] == {'status': t['searching'], 'requests': 0, 'listHidden': True, 'live': 'polite', 'role': 'status'}
    assert seen['settled']['requests'] == ['/api/search?q=API&limit=20&offset=0'] and seen['settled']['url'] == '/notes?q=API'
    assert seen['settled']['status'] == t['part'].format(total=26, shown=20) and seen['settled']['busy'] == 'false' and not seen['settled']['dim']
    assert seen['clear']['status'] == t['idle'] and not seen['clear']['listHidden'] and seen['clear']['requests'] == [] and seen['clear']['url'] == '/notes' and not seen['clear']['groups']
    assert seen['spacedPair']['requests'] == ['/api/search?q=%EB%8C%80%20%EC%B6%9C&limit=20&offset=0'] and seen['spacedPair']['groups']   # '대 출' is two characters
    assert seen['enter']['requests'] == ['/api/search?q=%EC%97%B0%EC%9E%A5&limit=20&offset=0']   # Enter does not wait for the pause
    assert seen['overtaken']['titles'] == ['NEW']   # the slow answer for older text is dropped


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_search_results_are_grouped_by_meeting_and_link_to_the_line(find_harness, find_data, lang):
    t, ko, en = FIND[lang], find_data['ko'], find_data['en']
    seen = run_ui(find_harness, 'findResults', lang=lang, jobs=find_data['jobs'], given=find_data['given'])
    first = seen['first']
    assert first['status'] == t['part'].format(total=26, shown=20) and first['listHidden'] and first['requests'] == ['/api/search?q=API&limit=20&offset=0']
    newest, older = first['groups']   # newest meeting first, one group per meeting
    assert (newest['title'], newest['href']) == (EN_TITLE, f'/notes/{en}') and (older['title'], older['href']) == (KO_TITLE, f'/notes/{ko}')
    assert '2026' in newest['when'] and '14:00' in newest['when'] and '10:00' in older['when']
    assert [h['href'] for h in newest['hits']] == [f'/notes/{en}#t3'] and newest['hits'][0]['where'] == '00:07 S1'
    summary, *lines = older['hits']
    assert summary['href'] == f'/notes/{ko}#sum' and summary['where'].endswith(t['summary']) and '[t5]' not in summary['snip'] and '\n' not in summary['snip']
    assert [h['href'] for h in lines[:3]] == [f'/notes/{ko}#t1', f'/notes/{ko}#t2', f'/notes/{ko}#t3'] and lines[0]['where'] == '00:01 S2' and lines[1]['where'] == '00:04 S1'
    assert all(h['marks'] == ['API'] for g in first['groups'] for h in g['hits']) and len(lines) == 18
    assert first['more'] == {'text': t['more'].format(left=6), 'act': 'more', 'disabled': False}
    assert seen['loading'] == {'more': {'text': t['loading'], 'act': 'more', 'disabled': True}, 'status': t['part'].format(total=26, shown=20)}
    second = seen['second']
    assert second['requests'] == ['/api/search?q=API&limit=20&offset=20'] and [g['title'] for g in second['groups']] == [EN_TITLE, KO_TITLE]   # the second page joins the same meeting
    assert len(second['groups'][1]['hits']) == 25 and second['more'] is None and second['status'] == t['all'].format(total=26)
    assert second['focus'] == second['groups'][1]['hits'][19]['href']   # the first new result has the keyboard
    assert [h['marks'] for h in seen['ride']['groups'][0]['hits']] == [['Ride pass'], ['ride pass'], ['ride pass']] and seen['ride']['groups'][0]['hits'][0]['where'].endswith(t['summary'])
    none = seen['none']
    assert none['status'] == t['none'].format(q='zzzz') and t['nothing'] in none['none'] and none['listHidden'] and not none['groups']
    assert t['refused'] in seen['refused']['alert'] and '400' in seen['refused']['alert'] and 'q must contain' in seen['refused']['alert'] and seen['refused']['retry']['text'] == t['retry']
    assert t['down'] in seen['down']['alert'] and 'engine_unreachable' in seen['down']['alert']
    assert len(seen['retried']['groups']) == 2 and seen['retried']['requests'] == ['/api/search?q=down&limit=20&offset=0']
    assert seen['moreFailed'] == {'more': {'text': t['more'].format(left=6), 'act': 'more', 'disabled': False}, 'said': t['moreFailed'], 'groups': 2}


@needs_node
def test_search_text_comes_back_from_the_address(find_harness, find_data):
    seen = run_ui(find_harness, 'findRestore', lang='ko', jobs=find_data['jobs'], given=find_data['given'], search='?q=API')
    assert seen['value'] == 'API' and seen['requests'] == ['/api/search?q=API&limit=20&offset=0'] and len(seen['view']['groups']) == 2
    assert seen['listHidden'] and seen['urls'] == ['/notes?q=API']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_search_result_text_is_inert(find_harness, find_data, lang):
    seen = run_ui(find_harness, 'findHostile', lang=lang, jobs=find_data['jobs'])
    assert not (MARKUP - {'a'}) & set(seen['tags']) and seen['pwned'] is None   # nothing the engine sent became an element or ran (links are checked below)
    assert seen['requests'] == ['/api/search?q=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E&limit=20&offset=0']   # the typed text is only ever encoded
    ok = re.compile(r'^/notes/[A-Za-z0-9%._-]+(#(t[1-9][0-9]*|sum))?$')
    assert seen['links'] and all(ok.fullmatch(href) for href in seen['links']), seen['links']   # same-origin /notes/... only, a bad line id adds no anchor
    assert not any('javascript' in href or '"' in href or '<' in href for href in seen['links'])
    assert seen['groups'] == 4 and seen['hits'] == 6 and seen['longest'] <= 200 and not seen['controls'] and len(seen['speaker']) <= 40   # junk items are dropped, text is bounded
    assert '<i>hit</i>' in seen['marks'] and '\u202e' not in json.dumps(seen['view'], ensure_ascii=False)


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_slash_and_cmd_k_open_the_search_on_every_screen(find_harness, find_data, lang):
    t = FIND[lang]
    seen = run_ui(find_harness, 'findKeys', lang=lang, jobs=find_data['jobs'], given=find_data['given'])
    assert seen['trigger']['side'].startswith(t['trigger']) and seen['trigger']['keys'] == 'Meta+K Control+K /' and seen['trigger']['mobile'] == t['trigger']
    assert seen['slash'] == {'prevented': True, 'open': True, 'label': t['trigger'], 'focusId': 'fq', 'status': t['idle'], 'foot': seen['slash']['foot']} and t['foot'] in seen['slash']['foot']
    assert seen['found']['groups'] == 2 and seen['found']['requests'] == 1 and seen['found']['hrefs'][0].endswith('#t3')
    assert seen['whileOpen'] == {'slashPrevented': False, 'dialogs': 1, 'cmdK': True}   # a slash typed into the box is a character; ⌘K keeps the one dialog
    assert seen['arrows'] == {'prevented': True, 'focus': 'find-title', 'next': 'find-hit', 'back': 'fq'}   # arrows walk the results and back to the box
    assert seen['closed'] == {'dialogs': 0, 'focusBack': True}   # Esc: the dialog goes and the button that opened it has the focus again
    assert seen['noMod'] == [False, False, False, False]   # ctrl+/, shift+/ (?), composing, a bare k do nothing
    assert seen['typing'] == {'slashInInput': False, 'dialogs': 0} and seen['checkbox'] == {'prevented': True, 'dialogs': 1}   # not while typing; a checkbox is not typing
    assert seen['ctrlK'] == {'prevented': True, 'dialogs': 1}   # Ctrl+K works even in a text box
    assert seen['onTopOfAnother'] == {'slash': False, 'dialogs': 1}   # never on top of another dialog


@needs_node
def test_on_the_notes_screen_the_keys_go_to_the_box_not_a_dialog(find_harness, find_data):
    seen = run_ui(find_harness, 'findKeysNotes', lang='ko', jobs=find_data['jobs'])
    assert seen['afterSlash'] == {'prevented': True, 'dialogs': 0, 'focusId': 'q'} and seen['clicked'] == {'dialogs': 0, 'focusId': 'q'} and seen['box']


@needs_node
def test_search_box_sends_exactly_what_the_engine_accepts(find_harness, find_data, api):
    from quietclerk import search
    client, runtime, base = api
    corpus = ['', ' ', 'a', 'ab', 'a b', 'a  ', '  ab  ', '대', '대출', '대 출', '😀😀', '😀', 'x' * 100, 'x' * 101, 'a\x00b', 'a\u200bb', 'a\tb', '\t\t', '한' * 100, '한' * 101]
    sent = dict(run_ui(find_harness, 'findCorpus', lang='ko', jobs=find_data['jobs'], corpus=corpus))
    with closing(store.connect(runtime.db)) as con:
        for text in corpus:
            try:
                search.query(con, text, 20, 0)
                accepted = True
            except ValueError:
                accepted = False
            assert sent[text] == accepted, repr(text)   # a text the engine refuses is never sent, and one it takes is


@pytest.mark.parametrize('offset', [0, 20])
def test_search_answers_the_screens_read_match_the_schema(find_data, offset):
    for path, answer in find_data['given'].items():
        Draft202012Validator(SCHEMA | {'$ref': '#/$defs/Search'}).validate(answer['body'])
    assert find_data['given'][f'/api/search?q=API&limit=20&offset={offset}']['body']['total'] == 26


def test_search_ui_uses_only_the_search_endpoint():
    source = (STATIC / 'lib/search.js').read_text()
    assert re.findall(r"""['"`](/api/[^'"`?]*)""", source) == ['/api/search']
    assert 'POST' not in source and 'put(' not in source and 'post(' not in source   # reading only


# summary layout, memo and daily note (settings)
SUM = {
    'ko': {'nav': '요약 구성', 'types': ['회의', '현황공유', '발표회', '강의', '1:1', '브레인스토밍', '기타'], 'default': '기본', 'custom': '직접 정함', 'fixed': '핵심 요약', 'fixed2': '바꿀 수 없어요',
           'chars': '제어문자나 보이지 않는 글자는 쓸 수 없어요. 줄바꿈도 안 돼요.', 'empty': '비어 있어요.', 'long': '{n}자예요. {max}자까지 쓸 수 있어요.', 'many': '12개를 모두 채웠어요',
           'fix': '고쳐야 할 제목이 있어요. 빨간 줄을 고치거나 지워 주세요.', 'tag': '다음 요약부터 적용', 'lines': '줄바꿈은 공백으로 바꿨어요.', 'off': '지금은 꺼져 있어요.',
           'window': '{min}초 이상 {max}초 미만 녹음을 메모로 남겨요.', 'above': '메모 최소 길이(300초)가 위의 최소 길이(300초)와 같거나 커서', 'range': '5~299초 사이로 적어 주세요.', 'number': '숫자로 적어 주세요.',
           'dots': '‘..’ 없이 볼트 안의 경로를 적어 주세요.', 'braces': '{date}만 쓸 수 있어요.', 'ext': '.md로 끝나는 파일 경로를 적어 주세요.', 'example': '오늘 녹음이라면 Daily/{today}.md 에 링크를 더해요.',
           'sections': '제목은 1~40자, 제어문자 없이 적어 주세요.', 'instructions': '500자까지, 제어문자(줄바꿈 포함) 없이 적어 주세요.', 'memo': '5~299초 사이로 적어 주세요.',
           'daily': '회의록 폴더가 Obsidian 볼트 안에 있어야 해요.', 'banner': '저장하지 못했어요.', 'saved': '저장했어요.', 'reset': '기본값으로 초기화'},
    'en': {'nav': 'Summary layout', 'types': ['Meeting', 'Status update', 'Presentation', 'Lecture', 'One-on-one', 'Brainstorm', 'Other'], 'default': 'Default', 'custom': 'Custom', 'fixed': 'Key summary',
           'fixed2': 'can\'t be changed', 'chars': 'Control and invisible characters aren\'t allowed, and neither are line breaks.', 'empty': 'It\'s empty.', 'long': 'That is {n} characters; the limit is {max}.',
           'many': 'The list is full (12)', 'fix': 'Some headings need fixing. Correct or remove the ones in red.', 'tag': 'Applies from the next summary', 'lines': 'Line breaks were turned into spaces.',
           'off': 'It\'s off now.', 'window': 'Recordings from {min} s up to {max} s become memos.', 'above': 'The shortest memo (300 s) is not below the minimum length above (300 s)', 'range': 'Enter 5–299 seconds.',
           'number': 'Enter a whole number.', 'dots': 'Write a path inside the vault, without ‘..’.', 'braces': 'Only {date} may be in braces', 'ext': 'Write a path to a Markdown file ending in .md',
           'example': 'A recording made today adds its link to Daily/{today}.md.', 'sections': 'Headings are 1–40 characters with no control characters.',
           'instructions': 'Up to 500 characters, with no control characters or line breaks.', 'memo': 'Enter 5–299 seconds.', 'daily': 'The notes folder has to be inside an Obsidian vault',
           'banner': 'Not saved.', 'saved': 'Saved.', 'reset': 'Reset to default'},
}


@needs_node
def test_summary_layout_defaults_and_rules_match_the_engine(find_harness):
    from quietclerk import postprocess
    corpus = {'headings': ['책마루', 'x' * 40, 'x' * 41, '한' * 41, '😀' * 40, '😀' * 41, 'a\u200bb', 'a\x00b', 'a\nb', '  padded  ', '', '   ', '\ufeff책마루', '<img src=x onerror=alert(1)>', '1:1', '__proto__'],
              'instructions': ['', '  ', 'a' * 500, 'a' * 501, '가' * 500, '가' * 501, '😀' * 501, 'a\nb', 'a\tb', 'a\u200bb', '  결정 사항을 먼저  ', '<svg onload=alert(1)>'],
              'daily': ['', '  ', 'Daily/{date}.md', '{date}.md', '~/Notes/Daily/{date}.md', '/abs/{date}.md', '../x.md', 'a/../b.md', 'a/..b.md', 'x.txt', 'x.MD', 'a{b}.md', '{date}{date}.md', '{ date }.md',
                        'a\\b.md', '.md', 'Daily/.md', 'a/', 'x\u200b.md', 'x' * 4097 + '.md', 'Daily/{date}']}
    seen = run_ui(find_harness, 'summaryRules', corpus=corpus)
    assert [row[0] for row in seen['types']] == list(postprocess.MEETING_TYPES)
    for key, ko, en in seen['types']:   # the labels and the default headings are the engine's own
        assert (ko, en) == (postprocess.TYPE_LABELS['ko'][key], postprocess.TYPE_LABELS['en'][key]), key
        assert ', '.join(seen['defaults']['ko'][key]) == postprocess.TYPE_SECTIONS['ko'][key], key
        assert ', '.join(seen['defaults']['en'][key]) == postprocess.TYPE_SECTIONS['en'][key], key
    assert seen['limits'] == [12, 40, 500, 5, 299]

    def engine(key, value):
        try:
            config._validate(key, value)
            return True
        except config.SettingsError:
            return False
    for original, sent, issue in seen['headings']:
        assert engine('summary.sections', {'meeting': [sent]}) == (issue is None), repr(original)
    for original, sent, issue in seen['instructions']:
        assert engine('summary.instructions', sent) == (issue is None), repr(original)
    for original, sent, issue in seen['daily']:
        assert engine('daily_note.path', sent) == (issue is None), repr(original)   # what the screen lets through, the engine takes: and the other way round


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_summary_layout_memo_and_daily_note_are_edited_and_saved(find_harness, api, tmp_path, lang):
    t = SUM[lang]
    seen = run_ui(find_harness, 'summarySave', lang=lang, settings=word_settings(lang))
    nav = seen['nav']
    assert nav[3:5] == [WORDS[lang]['nav'], t['nav']] and seen['section'] == t['nav']   # after the word list, before the engines
    assert t['tag'] in seen['fields'][0]['tags'] and all(v['chip'] == t['default'] and not v['rows'] for v in seen['initial'])
    assert [v['name'] for v in seen['initial']] == t['types'] and seen['bar'] == WORDS[lang]['none']
    defaults = {'ko': '안건별 논의 · 결정 사항 · 할 일 · 미해결', 'en': 'Agenda · Decisions · Tasks · Open issues'}[lang]
    assert seen['initial'][0]['peek'] == defaults and defaults in seen['defaultView']['defaults'] and seen['defaultView']['open'] and seen['defaultView']['buttons'] == ['own']
    listed = defaults.split(' · ')
    own = seen['own']
    assert own['view']['rows'] == listed and own['view']['chip'].endswith(t['custom']) and t['fixed'] in own['fixed'] and t['fixed2'] in own['fixed'] and own['view']['count'] == '4 / 12'
    assert 'heading 1' in own['focus'] or '제목 1' in own['focus']   # the first row has the keyboard
    edited = seen['edited']['view']   # row 2 retyped, a new one typed and moved up, the first removed: the rows are as typed (trimmed when sent)
    assert edited['rows'] == ['  결정과 근거  ', listed[2], '다음 주 일정', listed[3]] and edited['count'] == '4 / 12'
    assert edited['peek'] == ' · '.join(row.strip() for row in edited['rows']) and 'remove' in edited['buttons']
    full = seen['full']
    assert full['count'] == '12 / 12' and 'add:off' in full['buttons']   # the 13th heading is not offered
    assert seen['lastRow']['rows'] and len(seen['lastRow']['rows']) == 1 and 'remove:off' in seen['lastRow']['buttons']   # the last heading cannot be removed
    assert seen['reset']['view']['chip'] == t['default'] and not seen['reset']['view']['rows'] and seen['reset']['view']['peek'] == defaults and seen['reset']['puts'] == 0
    assert seen['peek']['expanded'] == 'true' and seen['peek']['view']['defaults'] and seen['afterReset']['lecture']['chip'] == t['default'] and seen['afterReset']['meeting']['chip'].endswith(t['custom'])
    blocked = seen['emptyBlocked']
    assert blocked['puts'] == 0 and t['fix'] in blocked['field'] and t['banner'] in blocked['banner'] and 'other' in blocked['open']   # an empty row is shown, not sent
    assert t['empty'] in blocked['view']['said'] and seen['newRow']['said'] == []
    bad = seen['badRows']['said']
    assert t['chars'] in bad and t['long'].format(n=41, max=40) in bad
    instr = seen['instr']
    assert instr['count'] == '27 / 500' and instr['said'] == '' and seen['lines']['prevented'] and seen['lines']['value'] == '첫 줄 둘째 줄' and seen['lines']['note'] == t['lines']
    assert seen['long']['count'] == '501 / 500' and seen['long']['said'] == t['long'].format(n=501, max=500) and seen['long']['invalid'] == 'true'
    assert seen['longBlocked']['puts'] == 0 and seen['longBlocked']['field'].startswith(t['long'].format(n=501, max=500)) and seen['limit']['said'] == '' and seen['limit']['invalid'] is None
    memo = seen['memo']
    assert memo['off']['disabled'] and memo['off']['note'] == '' and {'ko': '다음 확인부터 적용', 'en': 'Applies from the next scan'}[lang] in memo['field']['tags']
    assert not memo['on']['disabled'] and memo['on']['note'] == t['window'].format(min=10, max=300) and memo['set'] == t['window'].format(min=20, max=300) and t['above'] in memo['over']
    for bad, said in [('bad3', 'range'), ('bad400', 'range'), ('badx', 'number')]:   # refused before sending; the field's own code follows the sentence
        assert memo[bad]['puts'] == 0 and memo[bad]['error'] == f"{t[said]} 400 memo.min_sec", bad
    daily = seen['daily']
    assert daily['off'] == t['off'] and daily['placeholder'] == 'Daily/{date}.md' and {'ko': '다음 녹음부터 적용', 'en': 'Applies from the next recording'}[lang] in daily['field']['tags']
    for name, said in [('dots', 'dots'), ('braces', 'braces'), ('ext', 'ext'), ('slash', 'braces'), ('invisible', 'chars')]:
        assert daily[name]['said'].startswith(t[said]) and daily[name]['invalid'] == 'true' and daily[name]['example'] == '', name
    assert daily['ok'] == {'said': '', 'example': t['example'].format(today=daily['ok']['today']), 'invalid': None, 'today': daily['ok']['today']}
    sections = {'meeting': ['결정과 근거', listed[0], listed[2], '다음 주 일정', listed[3]], 'other': ['잡담']}
    body = seen['saved']['bodies'][0]
    assert body == {'summary.sections': sections, 'summary.instructions': '결정 사항을 먼저, 숫자에는 단위를 붙여 주세요.', 'memo.enabled': True, 'memo.min_sec': 20, 'daily_note.path': 'Daily/{date}.md'}
    assert len(seen['saved']['bodies']) == 1   # one request, and only what changed (lecture was customised and reset: it is not in it)
    assert t['saved'] in seen['saved']['banner'] and seen['saved']['bar'] == WORDS[lang]['none'] and seen['saved']['memo'] == [True, '20'] and seen['saved']['daily'] == 'Daily/{date}.md'
    assert [v['type'] for v in seen['saved']['view'] if v['rows']] == ['meeting', 'other']   # the saved lists are what the screen shows now
    # the very body the screen sent is accepted by the real API and lands in settings.toml
    import tomllib
    client, runtime, base = api
    login(client, runtime, base)
    (tmp_path / '.obsidian').mkdir()   # the notes folder (root/notes) is inside an Obsidian vault
    response = client.put('/api/settings', json=body)
    assert response.status_code == 200, response.text
    on_disk = tomllib.loads((tmp_path / 'settings.toml').read_text(encoding='utf-8'))
    assert on_disk['summary.sections'] == body['summary.sections'] and on_disk['summary.instructions'] == body['summary.instructions']
    assert (on_disk['memo.enabled'], on_disk['memo.min_sec'], on_disk['daily_note.path']) == (True, 20, 'Daily/{date}.md')
    assert runtime.settings.get('summary.sections') == body['summary.sections'] and runtime.settings.get('memo.min_sec') == 20


@pytest.fixture
def summary_refusals(api):
    """What the real PUT /api/settings answers for each of the four when it refuses them."""
    client, runtime, base = api
    login(client, runtime, base)
    wrong = {'sections': {'summary.sections': {'meeting': ['x' * 41]}}, 'instructions': {'summary.instructions': 'line one\nline two'}, 'memo': {'memo.min_sec': 3},
             'daily': {'daily_note.path': 'Daily/{date}.md'}}   # the test notes folder has no Obsidian vault around it
    answers = {}
    for name, changes in wrong.items():
        response = client.put('/api/settings', json=changes)
        assert response.status_code == 400 and response.json()['field'] == next(iter(changes)), name
        answers[name] = response.json()
    assert not runtime.settings.path.exists()   # nothing was written
    return answers


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_summary_layout_server_refusals_are_shown_in_words(find_harness, summary_refusals, lang):
    t = SUM[lang]
    seen = run_ui(find_harness, 'summaryRefused', lang=lang, settings=word_settings(lang), refusals=summary_refusals)
    for name, key in [('sections', 'sections'), ('instructions', 'instructions'), ('memo', 'memo'), ('daily', 'daily')]:
        view = seen[name]
        assert view['error'].startswith(t[key]) and ('400' in view['error']), name   # the sentence in the display language, then the status code
        assert t['banner'] in view['banner'] and '400' in view['banner'] and view['bar'] not in (WORDS[lang]['none'],), name   # the draft is kept
    assert seen['staleLine'] is None   # editing the field takes the old line away


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_summary_layout_text_is_inert(find_harness, lang):
    hostile = {'meeting': ['<img src=x onerror=alert(1)>', 'a\u202eb', 'x' * 5000], 'other': ['<script>window.pwned=1</script>']}
    settings = word_settings(lang, **{'summary.sections': hostile, 'summary.instructions': '<svg onload=alert(1)>' + 'y' * 600, 'daily_note.path': '<img src=x onerror=alert(1)>.md'})
    seen = run_ui(find_harness, 'summaryHostile', lang=lang, settings=settings)
    assert not MARKUP & set(seen['tags']) and seen['links'] == 0 and seen['pwned'] is None and not MARKUP & set(seen['daily']['tags'])
    meeting, other = seen['rows']
    assert meeting['rows'][0] == '<img src=x onerror=alert(1)>' and meeting['peekLength'] < 5200 and len(meeting['said']) == 2 and other['said'] == []   # the bad ones are marked, the text is a value
    assert seen['instr']['count'] == '621 / 500' and seen['daily']['value'] == '<img src=x onerror=alert(1)>.md' and seen['daily']['said'] == ''
    assert seen['blocked']['puts'] == 0 and SUM[lang]['banner'] in seen['blocked']['banner'] and seen['blocked']['sections']   # an edited bad heading is not sent


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_summary_layout_without_the_keys_is_defaults_and_saves_only_the_change(find_harness, lang):
    settings = word_settings(lang)
    for key in ('summary.sections', 'summary.instructions', 'memo.enabled', 'memo.min_sec', 'daily_note.path'):
        del settings[key]
    seen = run_ui(find_harness, 'summaryMissing', lang=lang, settings=settings)
    assert all(chip == SUM[lang]['default'] for _, chip in seen['view']) and seen['instr'] == '' and seen['daily'] == '' and seen['memo'] == [False, '', True]
    assert seen['body'] == [{'daily_note.path': 'Daily/{date}.md'}]


def test_classes_the_search_and_summary_layout_add_are_styled():
    css = (STATIC / 'qc.css').read_text()
    sources = ''.join((STATIC / name).read_text() for name in ('lib/search.js', 'lib/shell.js', 'screens/settings-summary.js', 'screens/settings.js'))
    for name in ('find-trigger', 'find-icon', 'find', 'find-form', 'find-input', 'find-status', 'find-results', 'is-busy', 'find-groups', 'find-group', 'find-gh', 'find-title', 'find-hits', 'find-hit',
                 'find-where', 'find-ts', 'find-sp', 'find-snip', 'find-more', 'find-dlg', 'find-bar', 'sumtypes', 'sumtype', 'sumhead', 'sumname', 'sumpeek', 'sumbody', 'sumfixed', 'sumrows',
                 'sumrow', 'sumn', 'sumctl', 'sumsaid', 'sumdl', 'area'):
        assert re.search(rf'[\'" ]{re.escape(name)}[\'" ]', sources), name   # the screens use it
        assert re.search(rf'\.{re.escape(name)}(?![\w-])', css), name   # and the stylesheet has a rule for it


# The harness: it imports the real modules from quietclerk/server/static and drives them with fake browser parts.
UPDATE_UI_HARNESS = r'''// Runs the real front-end modules (quietclerk/server/static) against a small fake DOM, a fake fetch and a fake
// EventSource: no browser, no server. Usage: node harness.mjs <static dir> <scenario> <json params>.
import {pathToFileURL} from 'node:url';
import {webcrypto} from 'node:crypto';

const [staticDir, scenario, raw] = process.argv.slice(2);
const params = JSON.parse(raw || '{}');
const load = (path) => import(pathToFileURL(`${staticDir}/${path}`).href);
if (!globalThis.crypto) globalThis.crypto = webcrypto;

// ---- fake DOM: only what dom.js, shell.js, ui.js, update.js and settings.js touch
const kebab = (s) => s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
class FakeNode {
  constructor() { this.parentNode = null; }
  get isConnected() { let n = this; while (n.parentNode) n = n.parentNode; return n === document; }
  remove() { if (this.parentNode) { this.parentNode.childNodes = this.parentNode.childNodes.filter((c) => c !== this); this.parentNode = null; } }
}
class FakeText extends FakeNode {
  constructor(data) { super(); this.nodeType = 3; this.data = data; }
  get textContent() { return this.data; }
}
function compound(s) {
  const c = {tag: null, id: null, classes: [], attrs: []};
  const re = /([a-z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|([^\]]*)))?\]/gy;
  for (let m; (m = re.exec(s));) {
    if (m[1]) c.tag = m[1]; else if (m[2]) c.id = m[2]; else if (m[3]) c.classes.push(m[3]);
    else c.attrs.push([m[4], m[5] ?? m[6]]);
  }
  return c;
}
function matches(el, c) {
  if (c.tag && el.localName !== c.tag) return false;
  if (c.id && el.getAttribute('id') !== c.id) return false;
  const classes = (el.getAttribute('class') || '').split(/\s+/);
  if (c.classes.some((k) => !classes.includes(k))) return false;
  return c.attrs.every(([k, v]) => el.hasAttribute(k) && (v === undefined || el.getAttribute(k) === v));
}
class FakeElement extends FakeNode {
  constructor(tag) {
    super();
    this.nodeType = 1; this.localName = tag; this.tagName = tag.toUpperCase();
    this.attrs = new Map(); this.childNodes = []; this.listeners = {}; this.open = false; this.checked = false;
    this.style = {setProperty() {}};
    this.dataset = new Proxy({}, {
      get: (_, k) => this.attrs.get('data-' + kebab(String(k))),
      set: (_, k, v) => { this.attrs.set('data-' + kebab(String(k)), String(v)); return true; },
      deleteProperty: (_, k) => { this.attrs.delete('data-' + kebab(String(k))); return true; },
    });
  }
  get children() { return this.childNodes.filter((n) => n.nodeType === 1); }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(''); }
  set textContent(v) { this.replaceChildren(String(v)); }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  hasAttribute(k) { return this.attrs.has(k); }
  removeAttribute(k) { this.attrs.delete(k); }
  append(...nodes) {
    for (const n of nodes) {
      const node = typeof n === 'string' ? new FakeText(n) : n;
      node.remove();
      node.parentNode = this;
      this.childNodes.push(node);
    }
  }
  replaceChildren(...nodes) { for (const c of this.childNodes) c.parentNode = null; this.childNodes = []; this.append(...nodes); }
  contains(node) { for (let n = node; n; n = n.parentNode) if (n === this) return true; return false; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(ev) {
    ev.target ||= this;
    for (let n = this; n; n = n.parentNode) {
      ev.currentTarget = n;
      for (const fn of (n.listeners && n.listeners[ev.type]) || []) fn.call(n, ev);
      if (ev.bubbles === false) break;
    }
  }
  click() { if (!this.disabled) { this.focus(); this.dispatchEvent({type: 'click'}); } }
  focus() { if (!this.disabled && this.isConnected) document.activeElement = this; }
  scrollIntoView() {}
  showModal() { this.open = true; }
  close() { this.open = false; this.dispatchEvent({type: 'close', bubbles: false}); }
  querySelectorAll(sel) {
    const chains = sel.split(',').map((part) => part.trim().split(/\s+/).map(compound));
    const out = [];
    const inside = (el, chain) => {
      if (!matches(el, chain.at(-1))) return false;
      let i = chain.length - 2;
      for (let n = el.parentNode; i >= 0 && n && n !== this.parentNode; n = n.parentNode) if (n.nodeType === 1 && matches(n, chain[i])) i -= 1;
      return i < 0;
    };
    const walk = (node) => { for (const c of node.children) { if (chains.some((chain) => inside(c, chain))) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
const document = new FakeElement('#document');
document.nodeType = 9;
document.documentElement = new FakeElement('html');
document.body = new FakeElement('body');
document.documentElement.append(document.body);
document.append(document.documentElement);
document.title = '';
document.activeElement = document.body;
document.createElement = (tag) => new FakeElement(tag);
document.createElementNS = (ns, tag) => new FakeElement(tag);
document.createTextNode = (data) => new FakeText(data);
document.getElementById = (id) => document.querySelector('#' + id);
Object.assign(globalThis, {document, Node: FakeNode, location: {host: '127.0.0.1:8765', hash: '', replace() {}}});
const store = new Map();
globalThis.sessionStorage = {getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k)};

// ---- fake network and event stream
const calls = [];
const routes = {};
const reply = (status, body) => ({status, ok: status >= 200 && status < 300,
  headers: {get: (n) => (n.toLowerCase() === 'content-type' && body !== undefined ? 'application/json' : null)}, json: async () => body});
globalThis.fetch = async (path, init = {}) => {
  const method = init.method || 'GET';
  const call = {method, path, headers: {...(init.headers || {})}, body: init.body ? JSON.parse(init.body) : undefined};
  calls.push(call);
  const handler = routes[`${method} ${path}`];
  return handler ? handler(call) : reply(404, {error: 'not found'});
};
class FakeEventSource {
  static CONNECTING = 0; static OPEN = 1; static CLOSED = 2;
  static instances = [];
  constructor(url) { this.url = url; this.readyState = 0; this.handlers = {}; FakeEventSource.instances.push(this); }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  close() { this.readyState = 2; }
  open() { this.readyState = 1; if (this.onopen) this.onopen({}); }
  send(snapshot) { for (const fn of this.handlers.state || []) fn({data: JSON.stringify(snapshot)}); }
  drop() { this.readyState = 0; if (this.onerror) this.onerror({}); }
}
globalThis.EventSource = FakeEventSource;

// Timers longer than a minute (the restart grace) are held back so a scenario can "wait" them out.
const longTimers = [];
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...rest) => (ms >= 60000 ? (longTimers.push(fn), longTimers.length) : realSetTimeout(fn, ms, ...rest));
let skew = 0;
const realNow = Date.now;
Date.now = () => realNow() + skew;
const wait = async (ms) => { skew += ms; for (const fn of longTimers.splice(0)) fn(); await settle(); };

// ---- helpers
const tick = () => new Promise((resolve) => realSetTimeout(resolve, 0));
const settle = async () => { for (let i = 0; i < 6; i += 1) await tick(); };
const text = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : null);
const button = (b) => ({text: text(b), act: b.dataset.act, disabled: !!b.disabled});
const band = () => {
  const el = document.querySelector('[data-update]');
  return el && {state: el.getAttribute('data-update'), role: el.getAttribute('role'), kind: el.getAttribute('class'), text: text(el.children[1]),
    buttons: el.querySelectorAll('button').map(button), progress: !!el.querySelector('[role="progressbar"]'), focused: document.activeElement === el};
};
const offline = () => { const el = document.querySelector('.banner.off'); return el ? text(el.children[1]) : null; };
const announced = () => text(document.getElementById('live'));
const click = (sel, root = document) => { const el = root.querySelector(sel); if (!el) throw new Error('no element ' + sel); el.click(); return el; };

// The update bodies come from the caller: the test passes fixtures shaped like the real backend's.
const BODIES = params.bodies;
const body = (over) => ({...BODIES.current, ...over});
const summary = (b) => ({state: b && b.state, behind: b && b.behind});
const snapshot = (update) => ({engine: 'ready', paused: false, counts: {queued: 0, failed: 0, retry_wait: 0}, current_job: null, stage: null,
  elapsed_sec: null, last_progress: null, jobs: [], ...(update ? {update} : {})});

// Starts what app.js starts: the shell, the session, the stream, and the status. The update body is what GET /api/update answers.
async function boot({lang = 'ko', first = BODIES.current, screen = 'home', wizardStep = 0} = {}) {
  let current = first;
  const world = {es: null, calls, routes, set: (b) => { current = b; }, get body() { return current; }};
  routes['GET /api/session'] = () => reply(200, {csrf_token: 'csrf-1'});
  routes['GET /api/status'] = () => reply(200, {engine: 'ready', paused: false, counts: {}, current_job: null, providers: [], sync: {state: 'connected'}});
  routes['GET /api/update'] = () => reply(200, current);
  const i18n = await load('lib/i18n.js');
  i18n.setLang(lang);
  const api = await load('lib/api.js');
  const liveModule = await load('lib/live.js');
  api.authEvents.addEventListener('lost', liveModule.markAuthLost);   // as app.js does
  const shell = await load('lib/shell.js');
  const app = new FakeElement('div');
  app.setAttribute('id', 'app');
  document.body.append(app);
  world.shell = shell.mountShell(screen, {wizardStep});
  await api.openSession();
  liveModule.connect();
  world.es = FakeEventSource.instances.at(-1);
  world.es.open();
  await liveModule.refreshStatus();
  await settle();
  // The engine moved to another state: the stream says so and the page asks what it is.
  world.move = async (b) => { current = b; world.es.send(snapshot(summary(b))); await settle(); };
  world.api = api; world.live = liveModule; world.i18n = i18n;
  return world;
}

const posts = () => calls.filter((c) => c.method === 'POST')
  .map((c) => ({path: c.path, csrf: c.headers['X-CSRF-Token'], key: c.headers['Idempotency-Key'], body: c.body}));
const tags = (root) => [...new Set(root.querySelectorAll('*').map((el) => el.localName))].sort();

// ---- the word list: the settings screen as the real modules draw it, and what a typed word, a paste or a click does
const q = (sel) => document.querySelector(sel);
const qa = (sel) => document.querySelectorAll(sel);
const typeInto = (el, value) => { el.value = value; el.dispatchEvent({type: 'input'}); };
const addWord = (word) => {   // type it and press Enter (or the Add button: it is type=submit in a form)
  typeInto(q('#f-vt'), word);
  q('#s-vocab form.add-row').dispatchEvent({type: 'submit', preventDefault() {}});
};
const pasteWords = (words) => {
  const event = {type: 'paste', clipboardData: {getData: () => words}, prevented: false, preventDefault() { this.prevented = true; }};
  q('#f-vt').dispatchEvent(event);
  return event.prevented;
};
const saveButton = () => qa('.stickybar button').find((b) => /저장|Save$/.test(text(b)));
const revertButton = () => qa('.stickybar button').find((b) => /되돌리기|Revert/.test(text(b)));
const savedBodies = () => calls.filter((c) => c.method === 'PUT').map((c) => c.body);
const barText = () => text(q('.stickybar b'));
const addRowButton = () => q('[data-key="vocabulary.replace"] .row .btn');
const leaveRow = (i) => qa('#s-vocab .vrow')[i].dispatchEvent({type: 'focusout', relatedTarget: null});
const errorOf = (id) => text(document.getElementById(id));
const wordView = () => {
  const input = q('#f-vt');
  return {terms: qa('#s-vocab .term-t').map(text), marked: qa('#s-vocab .term.bad').length, listHidden: q('#s-vocab ul.terms').hidden,
    count: text(q('[data-key="vocabulary.terms"] .num')), said: text(q('#f-vt-said')), invalid: input.getAttribute('aria-invalid'), box: input.value,
    add: button(q('#s-vocab form.add-row button')), full: !q('#f-vt-full').hidden, markedNote: !q('#f-vt-marked').hidden, bar: barText()};
};
const rowView = () => qa('#s-vocab .vrow').map((row) => {
  const from = row.querySelector('.vf'), to = row.querySelector('.vt');
  return {from: from.value, to: to.value, said: text(row.querySelector('.vmsg')), invalid: [from.getAttribute('aria-invalid'), to.getAttribute('aria-invalid')]};
});
const consentView = () => qa('[data-key="providers.consent"] label.check').map((label) => {
  const box = label.querySelector('input');
  return {text: text(label), checked: box.checked, disabled: !!box.disabled};
});
const engineLines = () => qa('#providers .provider-row').map(text);

// The settings screen with the word list. `w.fail` is a {status, body} the next PUT answers with (once).
async function openSettings({lang, settings, providers = []}) {
  const w = await boot({lang, screen: 'settings', first: BODIES.current});
  w.saved = {...settings};
  w.fail = null;
  const answer = () => reply(200, {effective: w.saved, file: {}, environment_keys: [], restart_required: false});
  routes['GET /api/settings'] = answer;
  routes['PUT /api/settings'] = (call) => {
    if (w.fail) { const fail = w.fail; w.fail = null; return reply(fail.status, fail.body); }
    w.saved = {...w.saved, ...call.body};
    return answer();
  };
  routes['GET /api/providers'] = () => reply(200, {items: providers});
  routes['GET /api/notes/migration'] = () => reply(200, {preview: {entries: [], conflicts: []}, migrated: false, task: null});
  await (await load('screens/settings.js')).mount(w.shell);
  await settle();
  return w;
}
const save = async () => { saveButton().click(); await settle(); };

const scenarios = {
  // Every state in turn, as the stream announces it.
  async bands({lang}) {
    const w = await boot({lang});
    const seen = [{state: 'current', band: band()}];
    for (const state of ['available', 'scheduled', 'updating', 'done', 'failed', 'unavailable', 'current']) {
      await w.move(BODIES[state]);
      seen.push({state, band: band(), live: announced()});
    }
    return {seen, calls: calls.map((c) => `${c.method} ${c.path}`)};
  },

  // Update clicked twice while the request is out; the engine answers `answer`, and then says `after`.
  async apply({lang, answer, after}) {
    const w = await boot({lang, first: BODIES.available});
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    routes['POST /api/update/apply'] = async () => {
      await gate;
      if (answer === 'network') throw new TypeError('network down');
      if (answer === 'conflict') return reply(409, {error: 'update not available', reason: 'local_changes'});
      return reply(202, {state: answer});
    };
    const first = click('[data-act="apply"]');
    first.click();                       // a double click lands on the same element
    await settle();
    const during = band();
    document.querySelector('[data-act="apply"]')?.click();   // and on the one drawn since
    w.set(BODIES[after]);
    release();
    await settle();
    return {during, after: band(), live: announced(), posts: posts(), gets: calls.filter((c) => c.path === '/api/update').length};
  },

  // The engine is swapped by the update: the stream breaks, then comes back (after `waited` ms, or never in time).
  async restart({lang, waited}) {
    const w = await boot({lang, first: BODIES.available});
    routes['POST /api/update/apply'] = () => reply(202, {state: 'updating'});
    routes['POST /api/update/dismiss'] = () => reply(200, BODIES.current);
    w.set(BODIES.updating);
    click('[data-act="apply"]');
    await settle();
    const updating = band();
    w.es.drop();
    await settle();
    const down = {band: band(), offline: offline(), engine: text(document.querySelector('.engine')), chip: text(document.querySelector('.mobile-top .chip'))};
    let late = null;
    if (waited) {
      await wait(waited);
      late = {band: band(), offline: offline(), engine: text(document.querySelector('.engine'))};
    }
    w.set(BODIES.done);
    const before = calls.length;
    w.es.open();
    await settle();
    const done = band();
    click('[data-act="dismiss"]');
    await settle();
    return {updating, down, late, done, after: band(), offline: offline(), calls: calls.slice(before).map((c) => `${c.method} ${c.path}`),
      posts: posts().map((p) => p.path), focus: document.activeElement.getAttribute('id')};
  },

  // OK on a result; the engine answers (or the network fails).
  async dismiss({lang, state, fail}) {
    const w = await boot({lang, first: BODIES[state]});
    routes['POST /api/update/dismiss'] = () => {
      if (fail) throw new TypeError('down');
      return reply(200, state === 'failed' ? BODIES.available : BODIES.current);
    };
    const before = band();
    const b = click('[data-act="dismiss"]');
    b.click();
    await settle();
    return {before, after: band(), posts: posts(), live: announced(), focus: document.activeElement.getAttribute('id') || document.activeElement.getAttribute('data-act')};
  },

  // What's new: the list, the facts, Update now, and closing (button, Esc, backdrop).
  async dialog({lang}) {
    const w = await boot({lang, first: BODIES.available});
    routes['POST /api/update/apply'] = () => reply(202, {state: 'scheduled'});
    const opener = click('[data-act="changes"]');
    const el = document.querySelector('dialog');
    const view = {open: el.open, labelled: el.getAttribute('aria-labelledby'), title: text(el.querySelector('h2')), text: text(el),
      items: el.querySelectorAll('li').map((li) => text(li)), buttons: el.querySelectorAll('button').map(button), focus: document.activeElement.dataset.act, modalFocus: el.contains(document.activeElement)};
    w.set(BODIES.scheduled);
    click('[data-act="apply"]', el);
    await settle();
    const applied = {dialog: !!document.querySelector('dialog'), band: band(), posts: posts().map((p) => p.path)};
    const closes = [];
    for (const how of ['button', 'esc', 'backdrop']) {
      const again = click('[data-act="changes"]');
      const d = document.querySelector('dialog');
      if (how === 'button') click('[data-act="close"]', d);
      else if (how === 'esc') d.close();
      else d.dispatchEvent({type: 'click'});
      closes.push({how, gone: !document.querySelector('dialog'), focusBack: document.activeElement.dataset.act, same: document.activeElement === again});
    }
    return {view, applied, closes, opened: opener.dataset.act};
  },

  // The setup wizard has its own frame; the band is in it too.
  async wizard({lang}) {
    await boot({lang, first: BODIES.available, screen: 'setup', wizardStep: 2});
    return {band: band(), inWizard: !!document.querySelector('.wiz [data-update]')};
  },

  // The engine comes back after an update restart but the session did not survive it.
  async sessionLost({lang}) {
    const w = await boot({lang, first: BODIES.updating});
    const before = band();
    w.es.drop();
    await settle();
    routes['GET /api/session'] = () => reply(401, {error: 'unauthorized'});
    w.es.open();
    await settle();
    const notice = document.querySelector('.banner.err');
    return {before, band: band(), notice: notice ? text(notice.children[1]) : null, offline: offline()};
  },

  // Text from the engine is text, whatever it looks like; impossible bodies show nothing or a plain sentence.
  async hostile({lang}) {
    const evil = '<img src=x onerror=alert(1)><script>window.pwned=1</script> [x](https://evil.example) \u202egnp.exe\u202c \u2028\u0000 ' + 'A'.repeat(600);
    const many = Array.from({length: 40}, (_, i) => ({commit: i % 2 ? 'zz<b>' : 'abc' + (1000 + i), title: `${i} ${evil}`, date: i % 3 ? 'not a date' : '2026-11-10T11:30:00+09:00'}));
    const w = await boot({lang, first: {...BODIES.available, behind: 'many', changes: many, last_error: evil, reason: evil,
      installed: {commit: '<script>', date: '1'}, latest: {commit: 'DEF5678', date: '9999-99-99'}}});
    const bandTags = tags(document.querySelector('[data-update]'));
    const bandText = band();
    click('[data-act="changes"]');
    const el = document.querySelector('dialog');
    const dialog = {tags: tags(el), items: el.querySelectorAll('li').length, longest: Math.max(...el.querySelectorAll('li .t').map((t) => text(t).length)),
      controlChars: /[\u0000-\u001f\u2028\u202a-\u202e]/.test(el.textContent), text: text(el).slice(0, 400), note: text(el.querySelector('.small.muted'))};
    click('[data-act="close"]', el);
    const odd = {};
    let n = 0;
    for (const [name, b] of Object.entries({nullBody: null, arrayBody: [], stringBody: 'available', unknown: {state: 'exploding', behind: 1}, upper: {state: 'AVAILABLE'},
      listState: {state: ['available']}, failedEvil: {state: 'failed', last_error: evil, reason: 'diverged'}, doneBad: {state: 'done', installed: {commit: 'zzzz'}},
      doneNoPrev: {state: 'done', installed: {commit: 'DEF5678'}}, negative: {state: 'available', behind: -4, changes: []}})) {
      w.set(b);
      w.es.send(snapshot({state: (b && b.state) || 'x', behind: ++n}));
      await settle();
      odd[name] = band();
    }
    return {bandTags, bandText, dialog, odd};
  },

  // The settings card: the toggle, saving it, Check now (twice while out), every reason, a failure.
  async settings({lang, settings, cases}) {
    const w = await boot({lang, screen: 'settings', first: BODIES.current});
    let saved = {...settings};
    const answer = () => reply(200, {effective: saved, file: {}, environment_keys: [], restart_required: false});
    routes['GET /api/settings'] = answer;
    routes['PUT /api/settings'] = (call) => { saved = {...saved, ...call.body}; return answer(); };
    routes['GET /api/providers'] = () => reply(200, {items: []});
    routes['GET /api/notes/migration'] = () => reply(200, {preview: {entries: [], conflicts: []}, migrated: false, task: null});
    await (await load('screens/settings.js')).mount(w.shell);
    await settle();
    const field = document.querySelector('[data-key="updates.check"]');
    const toggle = field.querySelector('input');
    const toggleView = {label: text(field.querySelector('label')), help: text(field.querySelector('.help')), role: toggle.getAttribute('role'), checked: toggle.checked,
      tags: text(field.querySelector('.tags')), section: text(document.querySelector('#s-upd h2')), nav: document.querySelectorAll('a.chip').map((a) => text(a))};
    toggle.checked = !toggle.checked;
    toggle.dispatchEvent({type: 'change'});
    const bar = text(document.querySelector('.stickybar'));
    document.querySelectorAll('.stickybar button').find((b) => /저장|Save$/.test(text(b))).click();
    await settle();
    const savedView = {puts: calls.filter((c) => c.method === 'PUT').map((c) => c.body), checked: document.querySelector('[data-key="updates.check"] input').checked, bar};

    const card = () => document.getElementById('f-ucheck');
    const status = () => text(card().querySelector('[role="status"]'));
    const check = () => card().querySelector('[data-act="check"]');
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    routes['POST /api/update/check'] = async () => { await gate; return reply(200, body({checked_at: '2026-11-10T10:30:00+09:00'})); };
    const first = check();
    const initial = {status: status(), versions: text(document.getElementById('f-uver'))};
    first.click();
    first.click();
    await settle();
    const during = {button: button(check()), status: status()};
    check().click();
    release();
    await settle();
    const checked = {status: status(), button: button(check()), posts: posts().filter((p) => p.path === '/api/update/check').length};

    const byCase = {};
    for (const [name, over] of Object.entries(cases)) {
      routes['POST /api/update/check'] = () => reply(200, body(over));
      check().click();
      await settle();
      byCase[name] = status();
    }
    routes['POST /api/update/check'] = () => { throw new TypeError('down'); };
    check().click();
    await settle();
    const failed = status();
    routes['POST /api/update/check'] = () => reply(200, BODIES.available);
    check().click();
    await settle();
    const available = {status: status(), buttons: card().querySelectorAll('button').map(button), versions: text(document.getElementById('f-uver')), band: band()};
    await w.move(BODIES.failed);
    const pending = {button: button(check()), why: text(card().querySelector('.why')), band: band()};
    return {toggleView, savedView, initial, during, checked, byCase, failed, available, pending, posts: posts()};
  },

  // The word list in settings: typing, refusing, pasting, removing, saving, reverting.
  async vocabAdd({lang, settings}) {
    await openSettings({lang, settings});
    const seen = {nav: qa('nav a.chip').map(text), section: text(q('#s-vocab h2')), intro: text(q('#s-vocab .stack')),
      fields: qa('#s-vocab .field').map((f) => ({key: f.getAttribute('data-key'), label: text(f.querySelector('label')), help: text(f.querySelector('.help')), tags: text(f.querySelector('.tags'))})),
      placeholder: q('#f-vt').getAttribute('placeholder'), initial: wordView()};
    addWord('  책마루  ');
    seen.added = {...wordView(), focus: document.activeElement.getAttribute('id')};
    addWord('책마루');
    seen.dup = wordView();
    addWord('x'.repeat(41));
    seen.long = wordView();
    addWord('');
    seen.empty = wordView();
    addWord('a\u200bb');
    seen.chars = wordView();
    addWord('Kubernetes');
    seen.fixed = wordView();
    addWord('Open, Shift\n쿠버네티스, 책마루, ' + 'y'.repeat(41));
    seen.bulk = wordView();
    typeInto(q('#f-vt'), '');
    seen.paste = {taken: pasteWords('Alpha\nBeta;Gamma'), after: wordView()};
    seen.single = {taken: pasteWords('Delta'), after: wordView()};
    qa('#s-vocab .term button')[0].click();
    seen.removed = {...wordView(), focus: document.activeElement.getAttribute('aria-label')};
    await save();
    seen.saved = {bodies: savedBodies(), view: wordView(), saveOff: saveButton().disabled, banner: text(q('.banner.info'))};
    addWord('Temp');
    revertButton().click();
    seen.reverted = wordView();
    return seen;
  },

  // 199 entries: the 200th fits, the 201st says why not, one removed makes room again.
  async vocabLimit({lang, settings}) {
    await openSettings({lang, settings});
    const brief = () => { const view = wordView(); return {...view, terms: view.terms.length, last: view.terms.at(-1)}; };
    const seen = {initial: brief()};
    addWord('last');
    seen.filled = brief();
    addWord('over');
    seen.over = brief();
    qa('#s-vocab .term button')[0].click();
    seen.freed = brief();
    addWord('over');
    seen.again = brief();
    await save();
    seen.body = savedBodies()[0]['vocabulary.terms'].length;
    return seen;
  },

  // Which entries the box takes: the answer for each one typed alone.
  async vocabRules({lang, settings, corpus}) {
    await openSettings({lang, settings});
    const answers = [];   // pairs, not an object: "__proto__" is one of the entries
    for (const term of corpus) {
      addWord(term);
      const view = wordView();
      answers.push([term, view.terms.length === 1]);
      if (view.terms.length) qa('#s-vocab .term button')[0].click();
      typeInto(q('#f-vt'), '');
    }
    return Object.fromEntries(answers);
  },

  // The wrong -> correct rows: empty, half-filled, conflicting, identical, removed, refused by the server.
  async vocabRows({lang, settings, conflictBody}) {
    const w = await openSettings({lang, settings});
    const seen = {initial: rowView(), field: {label: text(q('[data-key="vocabulary.replace"] label')), help: text(q('[data-key="vocabulary.replace"] .help')), tags: text(q('[data-key="vocabulary.replace"] .tags'))},
      add: button(addRowButton()), count: text(q('[data-key="vocabulary.replace"] .row .num'))};
    addRowButton().click();
    seen.empty = {rows: rowView(), focusNew: document.activeElement === qa('#s-vocab .vf')[1], bar: barText()};
    typeInto(qa('#s-vocab .vf')[1], '큐시');
    seen.typing = {rows: rowView(), bar: barText()};
    leaveRow(1);
    seen.left = rowView();
    addWord('Temp');      // another change, so that Save can be pressed with the half-filled row still there
    await save();
    seen.blocked = {puts: savedBodies().length, field: errorOf('f-vr-err'), banner: text(q('.banner.err')), rows: rowView()};
    typeInto(qa('#s-vocab .vt')[1], 'QC');
    seen.filled = {rows: rowView(), bar: barText()};
    addRowButton().click();
    typeInto(qa('#s-vocab .vf')[2], '큐시');
    typeInto(qa('#s-vocab .vt')[2], 'QCS');
    seen.conflict = {rows: rowView(), bar: barText()};
    await save();
    seen.conflictSave = {puts: savedBodies().length, field: errorOf('f-vr-err')};
    typeInto(qa('#s-vocab .vt')[2], 'QC');
    seen.identical = {rows: rowView(), bar: barText()};
    await save();
    seen.saved = {bodies: savedBodies(), rows: rowView(), banner: text(q('.banner.info'))};
    qa('#s-vocab .vdel button')[0].click();
    seen.removed = {rows: rowView(), focus: document.activeElement.getAttribute('id') || document.activeElement.getAttribute('aria-label'), bar: barText()};
    addRowButton().click();
    typeInto(qa('#s-vocab .vf')[1], 'A');
    typeInto(qa('#s-vocab .vt')[1], 'B');
    w.fail = {status: 400, body: conflictBody};
    await save();
    seen.refused = {field: errorOf('f-vr-err'), banner: text(q('.banner.err')), rows: rowView(), bar: barText()};
    typeInto(qa('#s-vocab .vt')[1], 'C');
    seen.edited = {field: document.getElementById('f-vr-err') === null};
    return seen;
  },

  // What the server says about the list, in words: answers taken from the real server by the test.
  async vocabServer({lang, settings, refusals}) {
    const w = await openSettings({lang, settings});
    const seen = {};
    addWord('Okay');
    for (const name of ['chars', 'long', 'many', 'shape']) {
      w.fail = {status: 400, body: refusals[name]};
      await save();
      seen[name] = {field: errorOf('f-vt-err'), replaceField: errorOf('f-vr-err'), banner: text(q('.banner.err')), terms: wordView().terms, bar: barText(), puts: savedBodies().length};
    }
    qa('#s-vocab .term button')[0].click();
    seen.edited = {gone: document.getElementById('f-vt-err') === null, terms: wordView().terms};
    await save();
    seen.saved = {bodies: savedBodies().slice(-1), banner: text(q('.banner.info')), field: document.getElementById('f-vt-err') === null};
    return seen;
  },

  // The consent box for the list: per engine, only where the transcript is allowed.
  async vocabConsent({lang, settings, providers}) {
    await openSettings({lang, settings, providers});
    const boxes = () => qa('[data-key="providers.consent"] label.check input');
    const tick = (i, on) => { boxes()[i].checked = on; boxes()[i].dispatchEvent({type: 'change'}); };
    const seen = {initial: {boxes: consentView(), engines: engineLines(), bar: barText()},
      field: {label: text(q('[data-key="providers.consent"] label')), help: text(q('[data-key="providers.consent"] .help')), tags: text(q('[data-key="providers.consent"] .tags')),
        note: text(q('[data-key="providers.consent"] .ctl > .small'))}};
    tick(0, true);
    seen.ticked = {boxes: consentView(), engines: engineLines(), bar: barText()};
    tick(0, false);
    seen.back = {boxes: consentView(), engines: engineLines(), bar: barText()};
    tick(0, true);
    tick(1, false);
    await save();
    seen.saved = {bodies: savedBodies(), boxes: consentView(), engines: engineLines(), bar: barText()};
    return seen;
  },

  // Nothing on: no engines to ask about, and no word list keys at all.
  async vocabMissing({lang, settings}) {
    await openSettings({lang, settings});
    const links = qa('[data-key="providers.consent"] a').map((a) => a.getAttribute('href'));
    const seen = {words: wordView(), rows: rowView(), consent: text(q('[data-key="providers.consent"] .ctl')), links, hint: text(q('[data-key="vocabulary.replace"] .ctl > .small'))};
    addWord('책마루');
    await save();
    seen.body = savedBodies();
    return seen;
  },

  // Text from the file or the server is text: tags, bidi and zero-width characters, a 5000-character entry, prototype names.
  async vocabHostile({lang, settings, typed}) {
    await openSettings({lang, settings});
    const used = () => [...new Set(q('#s-vocab').querySelectorAll('*').map((el) => el.localName))].sort();
    const shown = (el) => ({text: el.textContent.slice(0, 60), length: el.textContent.length});
    const seen = {tags: used(), links: q('#s-vocab').querySelectorAll('a').length, initial: {...wordView(), terms: null}, rows: rowView()};
    seen.chips = qa('#s-vocab .term-t').map(shown);
    seen.labels = qa('#s-vocab .term button').map((el) => el.getAttribute('aria-label').slice(0, 60));
    for (const word of typed) addWord(word);
    seen.typed = {terms: qa('#s-vocab .term-t').slice(-typed.length).map(shown), tags: used(), pwned: globalThis.pwned ?? null};
    await save();
    seen.blocked = {puts: savedBodies().length, field: errorOf('f-vt-err'), banner: text(q('.banner.err')), rowsField: errorOf('f-vr-err')};
    for (let i = qa('#s-vocab .term.bad').length; i > 0; i -= 1) qa('#s-vocab .term.bad button')[0].click();
    seen.cleaned = {view: wordView(), rows: rowView()};
    qa('#s-vocab .vdel button')[1].click();
    await save();
    seen.saved = {bodies: savedBodies(), tags: used()};
    return seen;
  },

  // Setup step 4: the fourth checkbox, off when an engine is first turned on, and what it says.
  async wizardConsent({lang, settings, providers}) {
    const w = await boot({lang, screen: 'setup', wizardStep: 4, first: BODIES.current});
    let saved = {...settings};
    const answer = () => reply(200, {effective: saved, file: {}, environment_keys: [], restart_required: false});
    routes['GET /api/settings'] = answer;
    routes['PUT /api/settings'] = (call) => { saved = {...saved, ...call.body}; return answer(); };
    routes['GET /api/providers'] = () => reply(200, {items: providers});
    await (await load('screens/setup-engines.js')).mount(w.shell);
    await settle();
    const card = (name) => qa('li.card').find((c) => text(c.querySelector('h3')) === name);
    const fieldset = (name) => card(name).querySelector('fieldset');
    const boxes = (name) => fieldset(name).querySelectorAll('label.check').map((label) => ({code: text(label.querySelector('code')), checked: label.querySelector('input').checked, text: text(label)}));
    const seen = {codex: boxes('Codex CLI'), codexNote: text(fieldset('Codex CLI').querySelector('p.small')), codexLink: fieldset('Codex CLI').querySelector('a').getAttribute('href'),
      claudeHasBoxes: !!card('Claude Code').querySelector('fieldset')};
    card('Claude Code').querySelector('label.switch input').checked = true;
    card('Claude Code').querySelector('label.switch input').dispatchEvent({type: 'change'});
    await settle();
    seen.enabled = {claude: boxes('Claude Code'), put: savedBodies().slice(-1)};
    const claudeBox = (code) => fieldset('Claude Code').querySelectorAll('label.check').find((label) => text(label.querySelector('code')) === code).querySelector('input');
    claudeBox('vocabulary').checked = true;
    claudeBox('vocabulary').dispatchEvent({type: 'change'});
    await settle();
    seen.ticked = {claude: boxes('Claude Code'), put: savedBodies().slice(-1)};
    claudeBox('vocabulary').checked = false;
    claudeBox('vocabulary').dispatchEvent({type: 'change'});
    await settle();
    seen.unticked = {claude: boxes('Claude Code'), put: savedBodies().slice(-1)};
    claudeBox('transcript').checked = false;
    claudeBox('transcript').dispatchEvent({type: 'change'});
    await settle();
    seen.noTranscript = {put: savedBodies().slice(-1), claudeOn: !!card('Claude Code').querySelector('fieldset')};
    return seen;
  },

  // The minutes screen: review reasons and what was sent, from the real server's payloads.
  async minutes({lang, island, detail, jobId}) {
    const w = await boot({lang, screen: 'note'});
    routes[`GET /api/jobs/${jobId}`] = () => reply(200, detail);
    const data = new FakeElement('script');
    data.setAttribute('id', 'qc-data');
    data.append(island);
    document.body.append(data);
    await (await load('screens/note.js')).mount({...w.shell, jobId});
    await settle();
    const panel = q('#pv-h').parentNode;
    const head = q('.note-head');
    return {count: text(head.querySelector('.chip.warn')), chips: head.querySelectorAll('p.row .chip').map((c) => ({text: text(c).replace(/^[!]/, ''), wrap: c.getAttribute('class')})),
      sent: panel.querySelectorAll('dt').map((dt, i) => [text(dt), text(panel.querySelectorAll('dd')[i])]),
      tags: [...new Set(head.querySelectorAll('*').map((el) => el.localName))].sort(), pwned: globalThis.pwned ?? null};
  },
};

const out = await scenarios[scenario](params);
console.log('RESULT ' + JSON.stringify(out));
process.exit(0);
'''
