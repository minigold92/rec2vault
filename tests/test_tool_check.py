"""Decoy tool-block verification for new Codex versions (contract 8.5) and the stuck-recording metric (contract 10.11).

All data is synthetic. The Codex CLI is a fake executable on PATH that behaves as the mode file says; its calls are
logged to a file so "ran once", "not again" and "same command line" are observed, not assumed.
"""
import json
import sqlite3
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from quietclerk import config, providers, store, stuck, tool_checks
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.providers import decoy
from quietclerk.providers.cli import Codex
from quietclerk.serve import Runtime
from quietclerk.server import create_app, integrations
from test_server_screens import UPDATE_UI_HARNESS, WORD_ENGINES, needs_node, run_ui, word_settings

NEW = '0.171.0'

FAKE_CODEX = r'''
import json, sys, time
from pathlib import Path
D = Path(%(directory)r)
args = sys.argv[1:]
if args[:1] == ['--version']:
    print('codex-cli ' + (D / 'version').read_text().strip()); sys.exit(0)
if args[:2] == ['login', 'status']:
    sys.exit(int((D / 'login').read_text()))
mode = (D / 'mode').read_text().strip()
prompt = sys.stdin.read()
Path(D / 'calls.txt').open('a').write(json.dumps(args) + '\n')
last = Path(args[args.index('-o') + 1])
decoy = 'secret.txt' in prompt
secret = Path('secret.txt').read_text().strip() if decoy else ''
def ev(value):
    print(json.dumps(value), flush=True)
def mcp(tool, key, listing, status='completed', error=None):
    base = {'id': 'm', 'type': 'mcp_tool_call', 'server': 'codex', 'tool': tool, 'arguments': {}}
    ev({'type': 'item.started', 'item': base | {'result': None, 'error': None, 'status': 'in_progress'}})
    result = {'content': [{'type': 'text', 'text': json.dumps({key: listing})}], 'structured_content': None}
    ev({'type': 'item.completed', 'item': base | {'result': result, 'error': error, 'status': status}})
if mode == 'timeout':
    time.sleep(60)
ev({'type': 'thread.started', 'thread_id': 't'})
ev({'type': 'turn.started'})
text = 'I have no shell tool and cannot read the file.' if decoy else 'OK'
if mode == 'leak_message':
    ev({'type': 'item.completed', 'item': {'id': 'a', 'type': 'agent_message', 'text': 'the file says ' + secret}})
else:
    ev({'type': 'item.completed', 'item': {'id': 'a', 'type': 'agent_message', 'text': 'checking'}})
if mode == 'ok' and decoy:
    mcp('list_mcp_resource_templates', 'resourceTemplates', [])
    mcp('list_mcp_resources', 'resources', [])
if mode in ('command', 'file_change', 'web_search', 'todo_list'):
    ev({'type': 'item.completed', 'item': {'id': 'c', 'type': {'command': 'command_execution'}.get(mode, mode)}})
if mode == 'mcp_read':
    mcp('read_mcp_resource', 'contents', [])
if mode == 'mcp_nonempty':
    mcp('list_mcp_resources', 'resources', [{'uri': 'file:///x'}])
if mode == 'mcp_error':
    mcp('list_mcp_resources', 'resources', [], status='failed', error={'message': 'x'})
if mode == 'weird_event':
    ev({'type': 'turn.weird'})
if mode == 'bad_json':
    print('not json')
if mode == 'write_new':
    Path('new.txt').write_text('x')
if mode == 'edit_secret':
    Path('secret.txt').write_text('changed')
if mode == 'leak_in_last':
    text += ' ' + secret
if mode == 'leak_spaced':
    text += ' ' + ' '.join(secret)
if mode == 'leak_stderr':
    sys.stderr.write(secret)
if mode == 'slow':
    time.sleep(1.5)
if mode != 'no_turn':
    ev({'type': 'turn.completed', 'usage': {}})
if mode != 'no_last':
    last.write_text(text)
sys.exit(1 if mode == 'rc1' else 0)
'''

FAILURES = [('leak_message', 'canary_exposed'), ('leak_in_last', 'canary_exposed'), ('leak_stderr', 'canary_exposed'),
            ('leak_spaced', 'canary_exposed'), ('command', 'tool_event:command_execution'),
            ('file_change', 'tool_event:file_change'), ('web_search', 'tool_event:web_search'),
            ('todo_list', 'unknown_item'), ('weird_event', 'unknown_event'), ('mcp_read', 'mcp_tool_call'),
            ('mcp_nonempty', 'mcp_tool_call'), ('mcp_error', 'mcp_tool_call'), ('rc1', 'exit_1'), ('timeout', 'timeout'),
            ('write_new', 'cwd_changed'), ('edit_secret', 'cwd_changed'), ('bad_json', 'invalid_event'),
            ('no_turn', 'no_turn_completed'), ('no_last', 'no_output')]


class Setup:
    def __init__(self, tmp_path, monkeypatch):
        self.dir = tmp_path / 'bin'
        self.dir.mkdir()
        self.root = tmp_path / 'root'
        script = self.dir / 'codex'
        script.write_text('#!' + sys.executable + '\n' + FAKE_CODEX % {'directory': str(self.dir)})
        script.chmod(0o755)
        monkeypatch.setenv('PATH', str(self.dir))
        monkeypatch.setenv('HOME', str(tmp_path / 'home'))
        self.set(mode='ok', version=NEW, login='0')
        self.events = []
        base = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(self.root), 'QC_SINCE': '1970-01-01 00:00'})
        values = base.snapshot() | {'providers.order': ['codex'], 'providers.consent': {
            'codex': ['transcript', 'source_name', 'project_list']}}
        self.settings = config.Settings(values, {}, frozenset(), tmp_path / 'settings.toml')
        self.snapshot = self.settings.snapshot()
        with closing(store.connect(self.root / 'state.sqlite3')):
            pass

    def set(self, **files):
        for name, value in files.items():
            (self.dir / name).write_text(value)

    def calls(self):
        path = self.dir / 'calls.txt'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def notify(self, name, message, error=False):
        self.events.append((name, message, error))

    def blocked_job(self, job_id='20261123-090000-aaaaaaaa'):
        with closing(store.connect(self.root / 'state.sqlite3')) as con:
            store.add_job(con, job_id, 'sha-' + job_id, 'meeting.m4a', None, 600)
            con.execute("UPDATE jobs SET status='retry_wait',blocked_reason='no_verified_provider' WHERE job_id=?", (job_id,))
        return job_id

    def job(self, job_id):
        with closing(store.connect(self.root / 'state.sqlite3')) as con:
            return dict(store.job(con, job_id))

    def status(self):
        return providers.registry(self.snapshot)['codex'].status()

    def verify(self):
        return decoy.auto_verify(self.snapshot, notify=self.notify)

    def record(self, version=NEW):
        return tool_checks.recorded(self.root, 'codex', version)


@pytest.fixture
def codex(tmp_path, monkeypatch):
    return Setup(tmp_path, monkeypatch)


def test_a_new_version_is_unverified_until_the_decoy_passes_then_blocked_recordings_resume(codex):
    job = codex.blocked_job()
    assert codex.status().tool_block == 'unverified'
    [check] = codex.verify()
    assert check.passed and check.reason == 'ok' and check.version == NEW
    assert codex.status().tool_block == 'verified'
    record = codex.record()
    assert record['passed'] and record['source'] == 'auto' and record['events']['item.completed/mcp_tool_call'] == 2
    assert 'text' not in json.dumps(record)  # kinds and counts only, never a response
    assert codex.job(job)['status'] == 'queued' and codex.job(job)['blocked_reason'] is None
    assert [e[0] for e in codex.events] == ['tool_check_passed'] and not codex.events[0][2]
    assert codex.verify() == [] and len(codex.calls()) == 1  # verified now: no second test


def test_a_plain_answer_without_mcp_listing_also_passes(codex):
    codex.set(mode='plain')
    assert codex.verify()[0].passed


def test_the_decoy_runs_the_exact_command_line_of_a_real_call(codex):
    codex.verify()
    [args] = codex.calls()
    last = Path('/x/last.txt')
    expected = Codex(codex.snapshot).command(last)
    assert args[:args.index('-o')] == expected[:expected.index('-o')] and args[-1] == '-'
    assert 'features.shell_tool=false' in args and '--ignore-user-config' in args and '--sandbox' in args


@pytest.mark.parametrize('mode, reason', FAILURES)
def test_every_unsafe_or_unclear_outcome_keeps_the_version_unverified_and_is_not_retried(codex, monkeypatch, mode, reason):
    monkeypatch.setattr(decoy, 'DECOY_TIMEOUT', 2)
    job = codex.blocked_job()
    codex.set(mode=mode)
    [check] = codex.verify()
    assert not check.passed and check.reason == reason
    assert codex.status().tool_block == 'unverified'
    assert codex.job(job)['status'] == 'retry_wait'
    assert codex.record()['passed'] is False and codex.record()['reason'] == reason
    assert codex.events == [('tool_check_failed', f'codex {NEW}: not verified ({reason})', True)]
    assert codex.verify() == [] and len(codex.calls()) == 1   # the same version is not tried again


def test_a_failed_version_can_be_tested_again_by_hand_and_then_resumes_recordings(tmp_path, codex):
    job = codex.blocked_job()
    codex.set(mode='command')
    assert not codex.verify()[0].passed
    codex.set(mode='ok')
    answer = integrations.check_provider(codex.settings, 'codex')
    assert answer['ok'] and answer['tool_check']['passed'] and answer['tool_check']['source'] == 'manual'
    assert codex.status().tool_block == 'verified'
    assert codex.job(job)['status'] == 'queued'
    assert len(codex.calls()) == 3  # failed decoy, passing decoy, the synthetic call


def test_a_manual_test_that_fails_reports_the_reason_and_does_not_send_a_normal_call(codex):
    codex.set(mode='leak_message')
    answer = integrations.check_provider(codex.settings, 'codex')
    assert not answer['ok'] and answer['reason'] == 'tool_check_failed:canary_exposed' and answer['sent_fields'] == []
    assert len(codex.calls()) == 1 and codex.record()['source'] == 'manual'


def test_a_stored_failure_replaces_an_earlier_pass_of_the_same_version(codex):
    codex.verify()
    assert codex.status().tool_block == 'verified'
    with closing(store.connect(codex.root / 'state.sqlite3')) as con:
        tool_checks.record(con, 'codex', NEW, False, 'x', {}, 'manual', 1.0)
    assert codex.status().tool_block == 'unverified'


@pytest.mark.parametrize('change', [
    {'providers.consent': {}}, {'providers.consent': {'codex': ['source_name']}}, {'providers.order': []},
    {'providers.order': ['claude']}, {'providers.local_only': True}])
def test_without_consent_order_or_with_local_only_nothing_runs(codex, change):
    codex.snapshot = codex.snapshot | change
    assert codex.verify() == [] and codex.calls() == [] and codex.record() is None


def test_not_signed_in_or_not_installed_nothing_runs(codex, monkeypatch):
    codex.set(login='1')
    assert codex.verify() == [] and codex.calls() == []
    monkeypatch.setenv('PATH', str(codex.dir / 'missing'))
    assert codex.verify() == [] and codex.calls() == []


def test_a_hand_verified_version_is_not_tested(codex):
    codex.set(version='0.170.0')
    assert codex.verify() == [] and codex.calls() == [] and codex.status().tool_block == 'verified'


def test_a_new_version_is_tested_again_and_a_pass_never_covers_another_version(codex):
    codex.verify()
    codex.set(version='0.172.0')
    assert codex.status().tool_block == 'unverified'
    codex.set(mode='command')
    assert [c.reason for c in codex.verify()] == ['tool_event:command_execution']
    assert codex.record(NEW)['passed'] and not codex.record('0.172.0')['passed'] and len(codex.calls()) == 2


def test_two_simultaneous_triggers_run_the_test_once(codex):
    codex.set(mode='slow')
    barrier, results = threading.Barrier(2), []
    def go():
        barrier.wait()
        results.append(decoy.verify(codex.snapshot, 'codex', source='auto', notify=codex.notify))
    threads = [threading.Thread(target=go) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(codex.calls()) == 1 and sorted(x is None for x in results) == [False, True]


def test_the_background_trigger_runs_on_the_executor_between_jobs_and_only_for_new_versions(codex, tmp_path):
    job = codex.blocked_job()
    runtime = Runtime(codex.settings, support=tmp_path / 'support', label_check=lambda _: False)
    runtime._ops = lambda *args: codex.events.append(args)
    runtime._request_tool_check()
    runtime._request_tool_check()  # one pending pass at a time
    assert runtime.maintenance.qsize() == 1 and codex.calls() == []
    with closing(store.connect(runtime.db)) as con:
        runtime._run_maintenance(con)
    assert len(codex.calls()) == 1 and codex.job(job)['status'] == 'queued'
    assert codex.events[0][:2] == ('emit', 'tool_check_passed') and '--source' in codex.events[0]
    runtime._request_tool_check()
    with closing(store.connect(runtime.db)) as con:
        runtime._run_maintenance(con)
    assert len(codex.calls()) == 1


def test_the_status_read_never_creates_a_database(tmp_path):
    assert tool_checks.recorded(tmp_path / 'absent', 'codex', NEW) is None
    assert not (tmp_path / 'absent').exists()
    assert Codex({}).verification(NEW) == 'unverified'


def test_provider_status_shows_the_stored_verdict(codex):
    codex.set(mode='command')
    codex.verify()
    [item] = integrations.provider_status(codex.settings, lambda s: {'codex': providers.registry(s)['codex']})
    assert item['name'] == 'codex' and item['tool_block'] == 'unverified' and item['tool_check']['reason'] == 'tool_event:command_execution'
    assert item['tool_check']['passed'] is False and item['tool_check']['source'] == 'auto'


# ---- stuck recordings (operations metric stuck_jobs)
HOUR = 3600


def waiting_job(root, job_id, status='retry_wait', reason='no_verified_provider', updated=0.0):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'private-name.m4a', None, 600, now=updated)
        con.execute('UPDATE jobs SET status=?,blocked_reason=?,updated_at=? WHERE job_id=?', (status, reason, updated, job_id))


def observe(root, now, hours=12):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        return stuck.observe(con, hours, now)


def test_the_stuck_count_starts_at_exactly_the_configured_hours(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=1000.0)
    assert observe(tmp_path, 1000.0 + 12 * HOUR - 60)['count'] == 0     # 11 h 59 min
    found = observe(tmp_path, 1000.0 + 12 * HOUR)                         # 12 h
    assert found['count'] == 1 and found['reasons'] == {'no_verified_provider': 1}


def test_only_waiting_recordings_count_and_progress_restarts_the_clock(tmp_path):
    for index, (status, reason) in enumerate([('failed', None), ('done', None), ('running', None), ('skipped', None),
                                             ('queued', None), ('retry_wait', None), ('retry_wait', 'auth')]):
        waiting_job(tmp_path, f'20261123-09000{index}-aaaaaaaa', status, reason, updated=0.0)
    found = observe(tmp_path, 13 * HOUR)
    assert found['count'] == 3 and found['reasons'] == {'queued': 1, 'retry_wait': 1, 'auth': 1}
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:   # progress: the auth-blocked one runs, then waits again
        con.execute("UPDATE jobs SET status='running',blocked_reason=NULL WHERE job_id='20261123-090006-aaaaaaaa'")
    assert observe(tmp_path, 13 * HOUR + 60)['count'] == 2
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        con.execute("UPDATE jobs SET status='retry_wait',blocked_reason='auth',updated_at=? WHERE job_id='20261123-090006-aaaaaaaa'",
                    (13 * HOUR + 120,))
    assert observe(tmp_path, 13 * HOUR + 180)['count'] == 2
    assert observe(tmp_path, 25 * HOUR + 180)['count'] == 3


def test_a_changed_reason_is_a_new_state_but_repeating_the_same_block_is_not_progress(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    assert observe(tmp_path, 11 * HOUR)['count'] == 0
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:   # blocked again for the same reason: updated_at moves, state does not
        con.execute("UPDATE jobs SET updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", (11.5 * HOUR,))
    assert observe(tmp_path, 12 * HOUR)['count'] == 1
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        con.execute("UPDATE jobs SET blocked_reason='auth',updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", (12 * HOUR,))
    assert observe(tmp_path, 13 * HOUR)['count'] == 0


def test_an_excluded_recording_is_not_counted(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        con.execute("UPDATE jobs SET exclude_requested=1")
    assert observe(tmp_path, 20 * HOUR)['count'] == 0


def test_the_event_fires_once_per_zero_to_positive_change_and_survives_a_restart(tmp_path, monkeypatch):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    assert [observe(tmp_path, t)['started'] for t in (11 * HOUR, 12 * HOUR, 13 * HOUR, 14 * HOUR)] == [False, True, False, False]
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        con.execute("UPDATE jobs SET status='done',blocked_reason=NULL")
    assert observe(tmp_path, 15 * HOUR) == {'count': 0, 'reasons': {}, 'started': False}
    waiting_job(tmp_path, '20261123-090001-aaaaaaaa', updated=15 * HOUR)
    assert observe(tmp_path, 27 * HOUR)['started'] is True and observe(tmp_path, 28 * HOUR)['started'] is False


def test_the_service_records_the_metric_and_one_event_with_only_a_count_and_codes(tmp_path):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path / 'root'), 'QC_SINCE': '1970-01-01 00:00'})
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    sent = []
    runtime._ops = lambda *args: sent.append(args)
    waiting_job(settings.root, '20261123-090000-aaaaaaaa', updated=0.0)
    waiting_job(settings.root, '20261123-090001-aaaaaaaa', 'queued', None, updated=0.0)
    with closing(store.connect(runtime.db)) as con:
        runtime._report_stuck(con, now=11 * HOUR)
        runtime._report_stuck(con, now=12 * HOUR)
        runtime._report_stuck(con, now=13 * HOUR)
    metrics = [a[2] for a in sent if a[:2] == ('metric', 'stuck_jobs')]
    events = [a for a in sent if a[0] == 'emit']
    assert metrics == ['0', '2', '2'] and ('metric', 'stuck_jobs', '2', '--unit', '건', '--source', 'rec-pipeline') in sent
    assert events == [('emit', 'jobs_stuck', '--kind', 'error', '--source', 'rec-pipeline', '--message',
                       '2건 (no_verified_provider:1, queued:1)')]
    assert 'private-name' not in json.dumps(sent)


@pytest.mark.parametrize('value, ok', [(0, False), (1, True), (12, True), (168, True), (169, False), (-1, False), (True, False), ('12', False)])
def test_stuck_hours_setting_range(value, ok):
    assert config.DEFAULTS['alerts.stuck_hours'] == 12
    if ok:
        assert config._validate('alerts.stuck_hours', value) == value
    else:
        with pytest.raises(config.SettingsError):
            config._validate('alerts.stuck_hours', value)


def test_jobs_api_reports_waiting_hours_by_the_same_rule(tmp_path, monkeypatch):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path / 'root'), 'QC_SINCE': '1970-01-01 00:00'})
    now = time.time()
    waiting_job(settings.root, '20261123-090000-aaaaaaaa', updated=now - 13 * HOUR - 30)
    waiting_job(settings.root, '20261123-090001-aaaaaaaa', updated=now - 11 * HOUR)
    waiting_job(settings.root, '20261123-090002-aaaaaaaa', 'failed', None, updated=now - 30 * HOUR)
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        token = read_bootstrap(runtime.support)['token']
        reply = client.post('/api/session', json={'token': token}, headers={'Origin': base})
        client.headers.update({'Origin': base, 'X-CSRF-Token': reply.headers['X-CSRF-Token']})
        items = {i['job_id']: i['stuck_hours'] for i in client.get('/api/jobs').json()['items']}
        assert items == {'20261123-090000-aaaaaaaa': 13, '20261123-090001-aaaaaaaa': None, '20261123-090002-aaaaaaaa': None}
        assert client.get('/api/jobs/20261123-090000-aaaaaaaa').json()['job']['stuck_hours'] == 13
        assert client.put('/api/settings', json={'alerts': {'stuck_hours': 10}}).status_code == 200
        assert client.get('/api/jobs').json()['items'][1]['stuck_hours'] == 11
        assert client.put('/api/settings', json={'alerts.stuck_hours': 0}).status_code == 400


def test_the_stuck_state_table_is_created_in_old_databases(tmp_path):
    path = tmp_path / 'state.sqlite3'
    with closing(store.connect(path)) as con:
        con.execute('DROP TABLE job_state_since')
        con.execute('DROP TABLE provider_tool_checks')
    with closing(store.connect(path)) as con:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'job_state_since', 'provider_tool_checks'} <= names


# ---- screens (run in node like tests/test_server_screens.py; skipped without node)
TOOLCHECK_SCENARIOS = Path(__file__).with_name('ui_toolcheck_scenarios.js')


@pytest.fixture(scope='module')
def toolcheck_harness(tmp_path_factory):
    marker = 'const out = await scenarios[scenario](params);'
    assert UPDATE_UI_HARNESS.count(marker) == 1
    path = tmp_path_factory.mktemp('toolcheck-ui') / 'harness.mjs'
    path.write_text(UPDATE_UI_HARNESS.replace(marker, TOOLCHECK_SCENARIOS.read_text(encoding='utf-8') + '\n' + marker), encoding='utf-8')
    return path


def provider(tool_block, check=None, version='0.171.0'):
    return {'name': 'codex', 'installed': True, 'logged_in': True, 'tool_block': tool_block, 'endpoint_class': 'external',
            'version': version, 'tool_check': check}


PASSED = {'version': '0.171.0', 'checked_at': 1795410008, 'passed': True, 'reason': 'ok', 'events': {}, 'source': 'auto'}
FAILED = PASSED | {'passed': False, 'reason': 'tool_event:command_execution'}


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_codex_card_says_auto_verified_failed_or_unverified_and_a_test_call_refreshes_it(toolcheck_harness, lang):
    ko = lang == 'ko'
    settings = word_settings(lang, **{'providers.order': ['codex']})
    others = WORD_ENGINES[1:]
    date = time.strftime('%m-%d', time.localtime(PASSED['checked_at']))
    verified = run_ui(toolcheck_harness, 'toolBlock', lang=lang, settings=settings, providers=[provider('verified', PASSED), *others])
    assert verified['before'].startswith((f'✓자동 확인됨 ({date})' if ko else f'✓Auto-verified ({date})'))
    fixed = run_ui(toolcheck_harness, 'toolBlock', lang=lang, settings=settings, providers=[provider('verified', None, '0.170.0'), *others])
    assert fixed['before'].startswith('✓확인됨' if ko else '✓Verified')
    failed = run_ui(toolcheck_harness, 'toolBlock', lang=lang, settings=settings, providers=[provider('unverified', FAILED), *others])
    assert ('자동 확인 실패 — 시험 호출로 다시 확인' if ko else 'Auto-check failed — run the test call to check again') in failed['before']
    assert 'tool_event:command_execution' in failed['before']
    fresh = run_ui(toolcheck_harness, 'toolBlock', lang=lang, settings=settings, providers=[provider('unverified'), *others])
    assert ('확인 전' if ko else 'Not verified') in fresh['before'] and 'Auto-check failed' not in fresh['before'] and '자동 확인 실패' not in fresh['before']
    refreshed = run_ui(toolcheck_harness, 'toolBlock', lang=lang, settings=settings, providers=[provider('unverified', FAILED), *others],
                       after={'providers': [provider('verified', PASSED | {'source': 'manual'}), *others],
                              'check': {'ok': True, 'sent_fields': ['transcript'], 'synthetic': True, 'endpoint_class': 'external'}})
    assert 'Auto-check failed' not in refreshed['after'] and '자동 확인 실패' not in refreshed['after']
    assert (f'✓자동 확인됨 ({date})' if ko else f'✓Auto-verified ({date})') in refreshed['after'] and ('성공' if ko else 'Passed') in refreshed['test']


@needs_node
@pytest.mark.parametrize('lang', ['ko', 'en'])
def test_home_shows_how_long_a_recording_has_waited(toolcheck_harness, lang):
    ko = lang == 'ko'
    def job(job_id, status, reason, hours):
        return {'job_id': job_id, 'sha256': 'x', 'source_name': f'{job_id}.m4a', 'recorded_at': '20261120-090000', 'duration_sec': 900,
                'status': status, 'blocked_reason': reason, 'stuck_hours': hours, 'stage': None, 'archive_path': None, 'updated_at': 1795410008,
                'created_at': 1795410008, 'title': None, 'legacy': 0, 'exclude_requested': 0, 'skip_reason': None, 'last_error': None, 'review_reasons': None}
    jobs = [job('blocked-long', 'retry_wait', 'no_verified_provider', 62), job('blocked-short', 'retry_wait', 'no_verified_provider', None),
            job('queued-long', 'queued', None, 15), job('queued-short', 'queued', None, None)]
    seen = run_ui(toolcheck_harness, 'stuckHome', lang=lang, jobs=jobs, settings=word_settings(lang))
    by_title = {c['title']: c['text'] for c in seen['cards']}
    assert set(by_title) == {'blocked-long.m4a', 'blocked-short.m4a', 'queued-long.m4a'}   # a short queue wait is not "needs a look"
    assert ('62시간째' if ko else '62 h and counting') in by_title['blocked-long.m4a']
    assert ('15시간째' if ko else '15 h and counting') in by_title['queued-long.m4a']
    assert '시간째' not in by_title['blocked-short.m4a'] and 'and counting' not in by_title['blocked-short.m4a']
    auth = run_ui(toolcheck_harness, 'stuckHome', lang=lang, jobs=[job('a', 'retry_wait', 'auth', 40), job('b', 'retry_wait', 'auth', 62)],
                  settings=word_settings(lang))
    [card] = auth['cards']
    assert ('(62시간째)' if ko else '(62 h and counting)') in card['text']
