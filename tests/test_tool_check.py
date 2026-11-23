"""Decoy tool-block verification for new Codex versions (contract 8.5) and the stuck-recording metric (contract 10.11).

All data is synthetic. The Codex CLI is a fake executable on PATH that behaves as the mode file says; its calls are
logged to a file so "ran once", "not again" and "same command line" are observed, not assumed.
"""
import json
import logging
import shutil
import sqlite3
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from quietclerk import config, providers, store, store_ops, stuck, tool_checks
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.providers import decoy, events
from quietclerk.providers.cli import Codex
from quietclerk.serve import Runtime
from quietclerk.server import create_app, integrations
from test_executor import engine, rerun  # noqa: F401
from test_server_screens import UPDATE_UI_HARNESS, WORD_ENGINES, needs_node, run_ui, word_settings

NEW = '0.171.0'
HOUR = 3600

FAKE_CODEX = r"""
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
Path(D / 'prompts.txt').open('a').write(prompt.replace('\n', ' ') + '\n')
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
if mode == 'signin':
    print(json.dumps({'type': 'error', 'message': 'not logged in'}))
    sys.stderr.write('not logged in'); sys.exit(1)
ev({'type': 'thread.started', 'thread_id': 't'})
ev({'type': 'turn.started'})
text = 'I have no shell tool and cannot read the file.' if decoy else 'OK'
if mode == 'leak_message':
    ev({'type': 'item.completed', 'item': {'id': 'a', 'type': 'agent_message', 'text': 'the file says ' + secret}})
else:
    ev({'type': 'item.completed', 'item': {'id': 'a', 'type': 'agent_message', 'text': 'checking'}})
if mode in ('command', 'file_change', 'web_search', 'todo_list', 'file_read'):
    ev({'type': 'item.completed', 'item': {'id': 'c', 'type': {'command': 'command_execution'}.get(mode, mode)}})
n = len((D / 'calls.txt').read_text().splitlines())   # which call of the test this is (the fake logs each one)
if mode == 'mcp_listing':
    mcp('list_mcp_resource_templates', 'resourceTemplates', [])
    mcp('list_mcp_resources', 'resources', [])
if mode == 'mcp_once' and n == 1:
    mcp('list_mcp_resources', 'resources', [])
if mode == 'mcp_then_command':
    if n == 1:
        mcp('list_mcp_resources', 'resources', [])
    else:
        ev({'type': 'item.completed', 'item': {'id': 'c', 'type': 'command_execution'}})
if mode == 'mcp_then_leak':
    if n == 1:
        mcp('list_mcp_resources', 'resources', [])
    else:
        text += ' ' + secret
if mode == 'mcp_and_command':
    mcp('list_mcp_resources', 'resources', [])
    ev({'type': 'item.completed', 'item': {'id': 'c', 'type': 'command_execution'}})
if mode == 'mcp_and_write':
    mcp('list_mcp_resources', 'resources', [])
    Path('new.txt').write_text('x')
if mode == 'mcp_and_weird':
    mcp('list_mcp_resources', 'resources', [])
    ev({'type': 'turn.weird'})
if mode == 'mcp_read':
    mcp('read_mcp_resource', 'contents', [])
if mode == 'mcp_nonempty':
    mcp('list_mcp_resources', 'resources', [{'uri': 'file:///x'}])
if mode == 'incomplete_item':
    ev({'type': 'item.started', 'item': {'id': 'r', 'type': 'reasoning'}})
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
if mode == 'rewrite_self':
    Path(__file__).write_text(Path(__file__).read_text() + '\n# changed while running\n')
if mode != 'no_turn':
    ev({'type': 'turn.completed', 'usage': {}})
if mode != 'no_last':
    last.write_text(text)
sys.exit(1 if mode == 'rc1' else 0)
"""

SECURITY = [('leak_message', 'canary_exposed'), ('leak_in_last', 'canary_exposed'), ('leak_stderr', 'canary_exposed'),
            ('leak_spaced', 'canary_exposed'), ('command', 'tool_event:command_execution'),
            ('file_change', 'tool_event:file_change'), ('web_search', 'tool_event:web_search'),
            ('file_read', 'unknown_item'), ('todo_list', 'unknown_item'), ('weird_event', 'unknown_event'),
            ('mcp_listing', 'tool_event:mcp_tool_call'), ('mcp_read', 'tool_event:mcp_tool_call'),
            ('mcp_nonempty', 'tool_event:mcp_tool_call'), ('write_new', 'cwd_changed'), ('edit_secret', 'cwd_changed'),
            ('bad_json', 'invalid_event'), ('no_turn', 'no_turn_completed'), ('incomplete_item', 'incomplete_item')]
TRANSIENT = [('rc1', 'exit_1'), ('timeout', 'timeout'), ('no_last', 'no_output'), ('signin', 'exit_1')]


class Setup:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp, self.monkeypatch = tmp_path, monkeypatch
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

    def provider(self):
        return providers.registry(self.snapshot)['codex']

    def status(self):
        return self.provider().status()

    def verify(self, **kwargs):
        return decoy.auto_verify(self.snapshot, notify=self.notify, **kwargs)

    def record(self, version=NEW):
        provider = self.provider()
        provider.status()
        seen = provider.seen
        return tool_checks.recorded(self.root, 'codex', version, seen[1], seen[2])


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
    assert record['passed'] and record['source'] == 'auto' and not record['transient']
    assert record['events']['item.completed/agent_message'] == 1 and not any('mcp' in kind for kind in record['events'])
    assert 'text' not in json.dumps(record)  # kinds and counts only, never a response
    assert codex.job(job)['status'] == 'queued' and codex.job(job)['blocked_reason'] is None
    assert [e[0] for e in codex.events] == ['tool_check_passed'] and not codex.events[0][2]
    assert codex.verify() == [] and len(codex.calls()) == 1  # verified now: no second test


def test_the_decoy_prompt_never_leads_the_model_to_an_mcp_tool(codex):
    assert 'mcp' not in decoy.DECOY_PROMPT.lower()
    codex.verify()
    assert 'mcp' not in (codex.dir / 'prompts.txt').read_text().lower()


def test_the_decoy_runs_the_exact_command_line_of_a_real_call(codex):
    codex.verify()
    [args] = codex.calls()
    last = Path('/x/last.txt')
    expected = Codex(codex.snapshot).command(last)
    assert args[:args.index('-o')] == expected[:expected.index('-o')] and args[-1] == '-'
    assert 'features.shell_tool=false' in args and '--ignore-user-config' in args and '--sandbox' in args


@pytest.mark.parametrize('mode, reason', SECURITY)
def test_a_security_failure_is_permanent_for_that_version_and_file(codex, mode, reason):
    job = codex.blocked_job()
    codex.set(mode=mode)
    [check] = codex.verify()
    assert not check.passed and check.reason == reason and not check.transient
    assert codex.status().tool_block == 'unverified'
    assert codex.job(job)['status'] == 'retry_wait'
    record = codex.record()
    assert record['passed'] is False and record['reason'] == reason and not record['transient'] and record['retry_at'] is None
    assert codex.events == [('tool_check_failed', f'codex {NEW}: not verified ({reason})', True)]
    # one call, except an MCP-only failure which is tested once more at once (below); then never again, however long we wait
    calls = 2 if reason == 'tool_event:mcp_tool_call' else 1
    assert len(codex.calls()) == calls
    year = time.time() + 365 * 24 * HOUR
    assert codex.verify(clock=lambda: year) == [] and len(codex.calls()) == calls


def same_command(first, second):
    """Two logged command lines are equal except for the temporary output file (`-o <file>`) each run gets."""
    cut = lambda args: args[:args.index('-o')] + args[args.index('-o') + 2:]
    return cut(first) == cut(second)


@pytest.mark.parametrize('mode', ['command', 'file_change', 'web_search', 'file_read', 'weird_event', 'leak_message', 'leak_in_last',
                                  'write_new', 'edit_secret', 'bad_json', 'no_turn', 'incomplete_item', 'mcp_and_command',
                                  'mcp_and_write', 'mcp_and_weird'])
def test_any_security_failure_other_than_mcp_alone_is_never_tested_again(codex, mode):
    codex.blocked_job()
    codex.set(mode=mode)
    [check] = codex.verify()
    assert not check.passed and not check.transient
    assert len(codex.calls()) == 1
    assert [e[0] for e in codex.events] == ['tool_check_failed']


@pytest.mark.parametrize('mode', ['mcp_listing', 'mcp_read', 'mcp_nonempty'])
def test_an_mcp_only_failure_is_tested_once_more_with_the_same_command_and_then_is_permanent(codex, mode):
    job = codex.blocked_job()
    codex.set(mode=mode)
    [check] = codex.verify()
    assert not check.passed and check.reason == 'tool_event:mcp_tool_call' and not check.transient
    first, second = codex.calls()
    assert same_command(first, second)                       # the same version, path and command line
    record = codex.record()
    assert record['passed'] is False and record['reason'] == 'tool_event:mcp_tool_call' and not record['transient']
    assert codex.status().tool_block == 'unverified' and codex.job(job)['status'] == 'retry_wait'
    assert codex.events == [('tool_check_failed', f'codex {NEW}: not verified (tool_event:mcp_tool_call)', True)]   # one verdict, one message
    assert codex.verify(clock=lambda: time.time() + 365 * 24 * HOUR) == [] and len(codex.calls()) == 2


def test_an_mcp_only_failure_that_passes_the_second_time_verifies_the_version(codex):
    job = codex.blocked_job()
    codex.set(mode='mcp_once')
    [check] = codex.verify()
    assert check.passed and check.reason == 'ok'
    assert len(codex.calls()) == 2 and same_command(*codex.calls())
    record = codex.record()
    assert record['passed'] and record['source'] == 'auto' and not any('mcp' in kind for kind in record['events'])
    assert codex.status().tool_block == 'verified' and codex.job(job)['status'] == 'queued'
    assert [e[0] for e in codex.events] == ['tool_check_passed']   # the first attempt is not announced
    assert codex.verify() == [] and len(codex.calls()) == 2


@pytest.mark.parametrize('mode, reason', [('mcp_then_command', 'tool_event:command_execution'), ('mcp_then_leak', 'canary_exposed')])
def test_the_second_test_decides_whatever_it_finds_and_there_is_no_third(codex, mode, reason):
    codex.set(mode=mode)
    [check] = codex.verify()
    assert not check.passed and check.reason == reason and not check.transient
    assert len(codex.calls()) == 2 and codex.record()['reason'] == reason
    assert codex.verify(clock=lambda: time.time() + 365 * 24 * HOUR) == [] and len(codex.calls()) == 2


def test_a_real_summary_call_with_an_mcp_event_is_refused_without_a_retry(codex):
    codex.set(mode='mcp_listing')
    provider = codex.provider()
    provider.status()
    with pytest.raises(providers.ToolUseDetected):
        provider.complete('synthetic', timeout=5)
    assert len(codex.calls()) == 1


def test_a_manual_test_call_gets_the_same_one_extra_test(codex):
    codex.set(mode='mcp_once')
    answer = integrations.check_provider(codex.settings, 'codex')
    assert answer['ok'] and answer['tool_check']['passed'] and answer['tool_check']['source'] == 'manual'
    assert len(codex.calls()) == 3   # failed attempt, passing attempt, the synthetic call


@pytest.mark.parametrize('mode, reason', TRANSIENT)
def test_a_transient_failure_is_not_a_verdict_and_is_retried_with_a_backoff(codex, monkeypatch, mode, reason):
    monkeypatch.setattr(decoy, 'DECOY_TIMEOUT', 2)
    job = codex.blocked_job()
    codex.set(mode=mode)
    now = time.time()
    [check] = codex.verify(clock=lambda: now)
    assert not check.passed and check.reason == reason and check.transient
    assert codex.status().tool_block == 'unverified' and codex.job(job)['status'] == 'retry_wait'
    record = codex.record()
    assert record['transient'] and record['attempts'] == 1 and record['retry_at'] == pytest.approx(now + 30 * 60)
    assert codex.events == [('tool_check_retry', f'codex {NEW}: not finished ({reason}), will retry', False)]
    assert codex.verify(clock=lambda: now + 29 * 60) == []          # still inside the back-off
    [again] = codex.verify(clock=lambda: now + 31 * 60)
    assert again.transient and codex.record()['attempts'] == 2
    assert codex.record()['retry_at'] == pytest.approx(now + 31 * 60 + 2 * HOUR)


def test_a_file_that_changes_while_the_decoy_runs_is_not_verified_and_is_retried(codex):
    job = codex.blocked_job()
    codex.set(mode='rewrite_self')
    [check] = codex.verify()
    assert not check.passed and check.transient and check.reason == 'executable_changed'
    assert codex.status().tool_block == 'unverified' and codex.job(job)['status'] == 'retry_wait'
    assert [e[0] for e in codex.events] == ['tool_check_retry']


def test_the_backoff_is_30_minutes_then_2_hours_then_6_hours_forever_and_a_pass_ends_it(codex):
    codex.set(mode='rc1')
    now, waits = time.time(), []
    for _ in range(5):
        [check] = codex.verify(clock=lambda: now)
        waits.append(codex.record()['retry_at'] - now)
        now = codex.record()['retry_at'] + 1
    assert [round(w / 60) for w in waits] == [30, 120, 360, 360, 360]
    codex.set(mode='ok')
    [check] = codex.verify(clock=lambda: now)
    assert check.passed and codex.status().tool_block == 'verified'
    assert codex.record()['attempts'] == 0 and codex.record()['retry_at'] is None


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


def test_a_stored_failure_replaces_an_earlier_pass_of_the_same_file(codex):
    codex.verify()
    assert codex.status().tool_block == 'verified'
    provider = codex.provider()
    provider.status()
    with closing(store.connect(codex.root / 'state.sqlite3')) as con:
        tool_checks.record(con, 'codex', NEW, provider.seen[1], provider.seen[2], False, 'x', {}, 'manual', 1.0)
    assert codex.status().tool_block == 'unverified'


@pytest.mark.parametrize('change', [
    {'providers.consent': {}}, {'providers.consent': {'codex': ['source_name']}}, {'providers.order': []},
    {'providers.order': ['claude']}, {'providers.local_only': True}])
def test_without_consent_order_or_with_local_only_nothing_runs(codex, change):
    codex.snapshot = codex.snapshot | change
    assert codex.verify() == [] and codex.calls() == []


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
    assert codex.status().tool_block == 'unverified' and len(codex.calls()) == 2
    codex.set(version=NEW)
    assert codex.status().tool_block == 'verified'


def test_the_record_is_bound_to_the_whole_version_string_the_file_path_and_the_file_content(codex, tmp_path):
    codex.verify()
    assert codex.status().tool_block == 'verified'
    codex.set(version='0.171.0-beta.1')                                  # a pre-release is another version
    status = codex.status()
    assert status.version == '0.171.0-beta.1' and status.tool_block == 'unverified'
    codex.set(version='0.170.0-beta.1')                                  # and never rides on a hand-verified minor
    assert codex.status().tool_block == 'unverified'
    codex.set(version='0.171.0+build.7')
    assert codex.status().tool_block == 'unverified'
    codex.set(version=NEW)
    assert codex.status().tool_block == 'verified'
    other = tmp_path / 'other'                                           # same content, other place
    other.mkdir()
    shutil.copy(codex.dir / 'codex', other / 'codex')
    for name in ('version', 'login', 'mode'):
        shutil.copy(codex.dir / name, other / name)
    codex.monkeypatch.setenv('PATH', str(other))
    assert codex.status().tool_block == 'unverified'
    codex.monkeypatch.setenv('PATH', str(codex.dir))
    assert codex.status().tool_block == 'verified'
    with (codex.dir / 'codex').open('a') as stream:                      # same place, other content
        stream.write('\n# replaced\n')
    assert codex.status().tool_block == 'unverified'


def test_the_file_is_hashed_again_right_before_a_call_and_that_exact_file_runs(codex, tmp_path):
    codex.verify()
    provider = codex.provider()
    assert provider.status().tool_block == 'verified'
    decoy_calls = len(codex.calls())
    rival = tmp_path / 'rival'
    rival.mkdir()
    (rival / 'codex').write_text('#!' + sys.executable + '\nraise SystemExit("PATH was searched again")\n')
    (rival / 'codex').chmod(0o755)
    codex.monkeypatch.setenv('PATH', str(rival) + ':' + str(codex.dir))
    assert provider.complete('synthetic', timeout=5).text == 'OK' and len(codex.calls()) == decoy_calls + 1
    provider = codex.provider()
    codex.monkeypatch.setenv('PATH', str(codex.dir))
    provider.status()
    with (codex.dir / 'codex').open('a') as stream:                      # replaced between the check and the call
        stream.write('\n# swapped\n')
    with pytest.raises(providers.ProviderError, match='changed'):
        provider.complete('synthetic', timeout=5)
    assert len(codex.calls()) == decoy_calls + 1


def test_a_real_call_applies_the_same_strict_event_check_as_the_decoy(codex, monkeypatch):
    for mode in ('file_read', 'todo_list', 'mcp_listing', 'mcp_read', 'weird_event', 'no_turn', 'incomplete_item'):
        codex.set(mode=mode)
        provider = codex.provider()
        provider.status()
        with pytest.raises(providers.ToolUseDetected):
            provider.complete('synthetic', timeout=5)
    codex.set(mode='ok')
    provider = codex.provider()
    provider.status()
    assert provider.complete('synthetic', timeout=5).text == 'OK'
    seen = []
    def verdict(stream):
        seen.append(len(stream))
        return 'tool_event:file_change', {}
    monkeypatch.setattr(events, 'codex_events', verdict)   # one function serves both: replacing it changes both
    with pytest.raises(providers.ToolUseDetected):
        provider.complete('synthetic', timeout=5)
    check = provider.tool_check()
    assert check.reason == 'tool_event:file_change' and len(seen) == 2


def test_a_failed_sign_in_is_still_a_sign_in_problem_not_a_tool_event(codex):
    codex.set(mode='signin')
    provider = codex.provider()
    provider.status()
    with pytest.raises(providers.AuthExpired):
        provider.complete('synthetic', timeout=5)


@pytest.mark.parametrize('change', [
    {'providers.consent': {}}, {'providers.order': []}, {'providers.local_only': True}])
def test_blocked_recordings_are_released_by_the_settings_at_that_moment_not_at_the_start(codex, change):
    job = codex.blocked_job()
    [check] = codex.verify(latest=lambda: codex.settings.snapshot() | change)
    assert check.passed and codex.record()['passed']                    # the file passed; the policy is read again
    assert codex.job(job)['status'] == 'retry_wait'
    assert codex.verify() == []
    with closing(store.connect(codex.root / 'state.sqlite3')) as con:
        providers.release_resolved_blocks(con, codex.settings)
    assert codex.job(job)['status'] == 'queued'


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


def test_a_check_that_raises_never_stops_the_executor(codex, tmp_path, monkeypatch):
    runtime = Runtime(codex.settings, support=tmp_path / 'support', label_check=lambda _: False)
    monkeypatch.setattr(decoy, 'auto_verify', lambda *a, **k: 1 / 0)
    assert runtime._verify_providers(None) == []


def test_the_status_read_never_creates_a_database(tmp_path):
    assert tool_checks.recorded(tmp_path / 'absent', 'codex', NEW, '/x', 'abc') is None
    assert not (tmp_path / 'absent').exists()
    assert Codex({}).verification(NEW) == 'unverified'


def test_provider_status_shows_the_stored_verdict_without_path_or_hash(codex):
    codex.set(mode='command')
    codex.verify()
    [item] = integrations.provider_status(codex.settings, lambda s: {'codex': providers.registry(s)['codex']})
    assert item['name'] == 'codex' and item['tool_block'] == 'unverified' and item['tool_check']['reason'] == 'tool_event:command_execution'
    assert item['tool_check']['passed'] is False and item['tool_check']['source'] == 'auto'
    assert str(codex.dir) not in json.dumps(item)


def test_an_old_unbound_record_table_is_replaced(tmp_path):
    path = tmp_path / 'state.sqlite3'
    with closing(store.connect(path)) as con:
        con.execute('DROP TABLE provider_tool_checks')
        con.execute('CREATE TABLE provider_tool_checks (provider TEXT, version TEXT, checked_at REAL, passed INTEGER, '
                    'reason TEXT, events TEXT, source TEXT)')
        con.execute("INSERT INTO provider_tool_checks VALUES('codex','0.171.0',1,1,'ok','{}','auto')")
    with closing(store.connect(path)) as con:
        assert [r[1] for r in con.execute("SELECT * FROM pragma_table_info('provider_tool_checks')")].count('sha256') == 1
        assert con.execute('SELECT COUNT(*) FROM provider_tool_checks').fetchone()[0] == 0


# ---- stuck recordings (operations metric stuck_jobs)
def waiting_job(root, job_id, status='retry_wait', reason='no_verified_provider', updated=0.0):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        store.add_job(con, job_id, 'sha-' + job_id, 'private-name.m4a', None, 600, now=updated)
        con.execute('UPDATE jobs SET status=?,blocked_reason=?,updated_at=? WHERE job_id=?', (status, reason, updated, job_id))
        if status in ('queued', 'retry_wait'):   # the date a transition made at this updated_at
            con.execute('UPDATE job_state_since SET since=? WHERE job_id=?', (updated, job_id))


def observe(root, now, hours=12):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        return stuck.observe(con, hours, now)


def sql(root, statement, *args):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        con.execute(statement, args)


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
    sql(tmp_path, "UPDATE jobs SET status='running',blocked_reason=NULL,updated_at=? WHERE job_id='20261123-090006-aaaaaaaa'", 13 * HOUR + 30)
    assert observe(tmp_path, 13 * HOUR + 60)['count'] == 2
    sql(tmp_path, "UPDATE jobs SET status='retry_wait',blocked_reason='auth',updated_at=? WHERE job_id='20261123-090006-aaaaaaaa'", 13 * HOUR + 120)
    assert observe(tmp_path, 13 * HOUR + 180)['count'] == 2
    assert observe(tmp_path, 25 * HOUR + 120)['count'] == 3


def test_progress_between_two_observations_still_restarts_the_clock(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    assert observe(tmp_path, 11 * HOUR)['count'] == 0
    # retry_wait -> running -> retry_wait (same reason) happened while nobody looked
    sql(tmp_path, "UPDATE jobs SET status='running',blocked_reason=NULL,updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", 11.2 * HOUR)
    sql(tmp_path, "UPDATE jobs SET status='retry_wait',blocked_reason='no_verified_provider',updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", 11.5 * HOUR)
    assert observe(tmp_path, 12 * HOUR)['count'] == 0       # waiting for 30 minutes, not 12 hours
    assert observe(tmp_path, 23.5 * HOUR)['count'] == 1


def test_the_transition_date_is_written_by_the_transition_itself(tmp_path):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path), 'QC_SINCE': '1970-01-01 00:00'})
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        row = store.add_job(con, '20261123-090000-aaaaaaaa', 'sha', 'x.m4a', None, 600, now=100.0)
        assert stuck.since_map(con) == {row['job_id']: ('queued:', 100.0)}
        claimed = store.claim(con, 'boot', settings, now=200.0)
        assert stuck.since_map(con) == {}                                    # running: not waiting
        store.fail(con, row['job_id'], claimed['active_run_id'], 'boot', 'auth', blocked_reason='auth', now=300.0)
        assert stuck.since_map(con) == {row['job_id']: ('retry_wait:auth', 300.0)}
        store.requeue_resolved_blocks(con, {'auth'}, now=400.0)
        assert stuck.since_map(con) == {row['job_id']: ('queued:', 400.0)}
        con.execute("UPDATE jobs SET status='skipped',skip_reason='user_excluded' WHERE job_id=?", (row['job_id'],))
        assert stuck.since_map(con) == {}
    # a writer that did not move updated_at still gets the clock, not a stale date
    waiting_job(tmp_path, '20261123-090001-aaaaaaaa', 'queued', None, updated=10.0)
    sql(tmp_path, "UPDATE jobs SET status='retry_wait',blocked_reason='auth' WHERE job_id='20261123-090001-aaaaaaaa'")
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        assert stuck.since_map(con)['20261123-090001-aaaaaaaa'][1] == pytest.approx(time.time(), abs=60)


def test_a_paused_engine_does_not_count_queued_waits_but_counts_blocked_ones_and_resume_restarts_them(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', 'queued', None, updated=0.0)
    waiting_job(tmp_path, '20261123-090001-aaaaaaaa', 'retry_wait', None, updated=0.0)
    waiting_job(tmp_path, '20261123-090002-aaaaaaaa', 'retry_wait', 'no_verified_provider', updated=0.0)
    assert observe(tmp_path, 13 * HOUR)['count'] == 3
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        store_ops.set_paused(con, True)
    found = observe(tmp_path, 13 * HOUR)
    assert found['count'] == 1 and found['reasons'] == {'no_verified_provider': 1}
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        known, rows = stuck.since_map(con), con.execute('SELECT * FROM jobs ORDER BY job_id').fetchall()
        assert [stuck.hours_waiting(r, known, 12, 13 * HOUR, paused=True) for r in rows] == [None, None, 13]
        store_ops.set_paused(con, False)
    now = time.time()
    assert observe(tmp_path, now + 11 * HOUR)['count'] == 1                 # the queued waits start over at resume
    assert observe(tmp_path, now + 12 * HOUR + 60)['count'] == 3


def test_a_changed_reason_is_a_new_state_but_a_write_that_keeps_the_state_is_not_progress(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    assert observe(tmp_path, 11 * HOUR)['count'] == 0
    sql(tmp_path, "UPDATE jobs SET updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", 11.5 * HOUR)   # e.g. a language override
    assert observe(tmp_path, 12 * HOUR)['count'] == 1
    sql(tmp_path, "UPDATE jobs SET blocked_reason='auth',updated_at=? WHERE job_id='20261123-090000-aaaaaaaa'", 12 * HOUR)
    assert observe(tmp_path, 13 * HOUR)['count'] == 0


def test_recordings_that_waited_before_the_triggers_existed_are_dated_from_updated_at(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=100.0)
    sql(tmp_path, 'DELETE FROM job_state_since')
    assert observe(tmp_path, 100.0 + 12 * HOUR)['count'] == 1


def test_an_excluded_recording_is_not_counted(tmp_path):
    waiting_job(tmp_path, '20261123-090000-aaaaaaaa', updated=0.0)
    sql(tmp_path, "UPDATE jobs SET exclude_requested=1")
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


def test_a_failing_stuck_calculation_is_logged_and_the_monitor_keeps_running(tmp_path, caplog):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path / 'root'), 'QC_SINCE': '1970-01-01 00:00'})
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False, fatal=lambda code: pytest.fail('fatal'))
    runtime._ops = lambda *args: None
    runtime.monitor_interval = 0
    runtime.tool_check_interval = 10**6
    rounds = []
    def broken(con, now=None):
        rounds.append(1)
        if len(rounds) == 3:
            runtime.stopping.set()
        raise sqlite3.OperationalError('database is locked: private-name.m4a')
    runtime._report_stuck = broken
    runtime._monitor()
    assert len(rounds) == 3 and runtime.failure is None
    assert 'stuck metric error: OperationalError' in caplog.text and 'private-name' not in caplog.text


def test_ops_events_name_the_job_and_a_code_never_the_file(tmp_path):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path / 'root'), 'QC_SINCE': '1970-01-01 00:00'})
    results = [{'status': 'done', 'job_id': '20261123-090000-aaaaaaaa', 'source_name': 'private-name.m4a', 'last_error': None},
               {'status': 'failed', 'job_id': '20261123-090001-aaaaaaaa', 'source_name': 'private-name.m4a', 'last_error': 'max_attempts'}]
    class Runs:
        def run_one(self, paused=False):
            if not results:
                runtime.stopping.set()
                return None
            return results.pop(0)
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=lambda con, boot, settings: Runs())
    sent = []
    runtime._ops = lambda *args: sent.append(args)
    runtime._executor()
    emitted = [a for a in sent if a[0] == 'emit']
    assert emitted == [('emit', 'job_done', '--source', 'rec-pipeline', '--message', '20261123-090000-aaaaaaaa'),
                       ('emit', 'job_failed', '--kind', 'error', '--source', 'rec-pipeline', '--message',
                        '20261123-090001-aaaaaaaa: max_attempts')]
    assert 'private-name' not in json.dumps(sent)


def test_the_service_log_names_the_job_not_the_file(engine, caplog):
    con, settings, row = engine
    caplog.set_level(logging.INFO)
    rerun(con, settings, row, [])
    assert row['job_id'] in caplog.text and 'sample.m4a' not in caplog.text


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
