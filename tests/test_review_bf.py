"""F01–F11: synthetic/barrier-injected acceptance, no real input/provider access.

Invariants: exclusion/deletion wins state transitions; journals close on cancellation;
only identified engine notes migrate, with vault-scoped consent; executor entry and
provider calls are exclusive; auth refresh and resolved-block recovery stay live.
Malformed structured replies must follow validation retry/fallback, never TypeError.
"""
import fcntl
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from quietclerk import artifacts, backfill, config, executor, notes, postprocess, providers, store, store_ops, tick
from quietclerk.notes import migration
from quietclerk.serve import Runtime
from quietclerk.server import integrations
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.server.auth import Auth
from quietclerk.server.settings import save
from quietclerk.stages import note
from test_notes import context, values, publish, again
from test_note_migration import vault, stage_context, legacy_note
from test_postprocess import BASE_REPLY, TURNS, engines, provider_context


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('recovery', [False, True])
def test_F01_exclusion_wins_renamed_publication(context, monkeypatch, recovery, existing):
    ctx = context
    if existing:
        publish(ctx)
        ctx = again(ctx)
    previous_run = store.job(ctx.con, ctx.job['job_id'])['current_run_id']
    commit = store.commit_publication
    def exclude_then_commit(con, job_id, run_id, boot, pending):
        with closing(store.connect(Path(ctx.settings['root']) / 'state.sqlite3')) as other:
            store.exclude(other, job_id)
        if recovery:
            raise KeyboardInterrupt()
        return commit(con, job_id, run_id, boot, pending)
    monkeypatch.setattr(store, 'commit_publication', exclude_then_commit)
    if recovery:
        with pytest.raises(KeyboardInterrupt):
            publish(ctx)
        store.recover(ctx.con, 'new', recover_publication=notes.recover_publication)
    else:
        publish(ctx)
    row = store.job(ctx.con, ctx.job['job_id'])
    assert row['status'] == 'skipped' and row['skip_reason'] == 'user_excluded'
    assert not row['exclude_requested'] and row['current_run_id'] == previous_run
    assert store.publication_committed(ctx.con, ctx.run_id)
    assert not list((Path(ctx.settings['output']) / '.quietclerk-tmp').glob('*'))


@pytest.mark.parametrize('operation', ['process', 'promote', 'claim'])
@pytest.mark.parametrize('pending_only', [False, True])
def test_F02_deleted_work_never_requeues_or_claims(tmp_path, operation, pending_only):
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        audio = tmp_path / 'source.m4a'
        audio.write_bytes(b'synthetic archive')
        row = store.add_job(con, 'job', artifacts.sha256(audio), 'test.m4a', str(audio), 100)
        assert not store_ops.deleted(con, 'job')  # API's stale preflight result.
        store_ops.request_delete_local(con, 'job')
        if pending_only:
            con.execute('DELETE FROM tombstones')
        if operation == 'claim':
            con.execute("UPDATE jobs SET status='queued' WHERE job_id='job'")
            assert store.claim(con, 'boot', {}) is None
        else:
            with pytest.raises(store.Conflict):
                if operation == 'process':
                    store.request_process(con, 'job')
                else:
                    store.promote(con, 'job', row['sha256'], audio)


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize('failure', ['exclude', 'exception', 'closed'])
def test_F03_prepared_cleanup_and_hidden_candidates(context, monkeypatch, existing, failure):
    ctx = context
    audio = Path(ctx.settings['root']) / 'synthetic.m4a'
    audio.write_bytes(b'synthetic archive')
    ctx.con.execute('UPDATE jobs SET sha256=?,archive_path=? WHERE job_id=?',
                    (artifacts.sha256(audio), str(audio), ctx.job['job_id']))
    ctx.job = store.job(ctx.con, ctx.job['job_id'])
    target = publish(ctx) if existing else None
    before = target.read_bytes() if target else None
    if existing:
        ctx = again(ctx)
    prepare = store.prepare_publication
    def inject(*args, **kwargs):
        prepare(*args, **kwargs)
        if failure == 'exclude':
            with closing(store.connect(Path(ctx.settings['root']) / 'state.sqlite3')) as other:
                store.exclude(other, ctx.job['job_id'])
        elif failure == 'closed':
            store.exclude(ctx.con, ctx.job['job_id'])
            ctx.checkpoint()
        else:
            raise RuntimeError('injected after prepare')
    monkeypatch.setattr(store, 'prepare_publication', inject)
    with pytest.raises((executor.Excluded, RuntimeError)):
        publish(ctx)
    assert ctx.con.execute("SELECT 1 FROM publications WHERE state='prepared'").fetchone() is None
    store.recover(ctx.con, 'restart', recover_publication=notes.recover_publication)
    assert ctx.con.execute("SELECT 1 FROM publications WHERE state IN ('prepared','renamed')").fetchone() is None
    assert not list((Path(ctx.settings['output']) / '.quietclerk-tmp').glob('*'))
    if target:
        assert target.read_bytes() == before
    hidden = Path(ctx.settings['output']) / '.quietclerk-tmp' / 'rogue.md'
    hidden.write_text(notes.dump_frontmatter({'job_id': ctx.job['job_id'], 'qc_schema': 2,
                                             'source_sha256': ctx.job['sha256'], 'project': ['hidden']}))
    assert hidden not in notes.safe_notes(hidden.parent.parent)
    store.request_process(ctx.con, ctx.job['job_id'])
    row = store.claim(ctx.con, 'boot', ctx.settings)
    next_ctx = executor.Context(ctx.con, row, 'boot', ctx.settings, row['active_run_id'], ctx.work)
    monkeypatch.setattr(store, 'prepare_publication', prepare)
    assert publish(next_ctx).parent == Path(ctx.settings['output'])


class Idle:
    def __init__(self, *args): pass
    def run_one(self, **kwargs): return None


def settings_at(tmp_path):
    return config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path)})


def test_F04_serve_and_tick_share_execution_lock(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=Idle, scan=lambda *a, **k: None)
    with (tmp_path / 'tick.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            with pytest.raises(RuntimeError):
                runtime.start()
        finally:
            runtime.close()
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=Idle, scan=lambda *a, **k: None)
    runtime.start()
    try:
        monkeypatch.setattr(tick.intake, 'scan', lambda *a, **k: pytest.fail('tick entered live executor'))
        assert tick.main(settings=settings, registry=[]) == 0
    finally:
        runtime.close()


def test_F05_personal_markdown_is_not_migration_candidate(vault):
    con, root, output = vault
    personal = output / 'personal.md'
    personal.write_text('# Personal memo\nNo engine identity.\n')
    assert migration.preview(con, root, output)['entries'] == []
    ctx = stage_context(con, root, output)
    note._publish(ctx, ctx.work / 'note.json.part')
    assert ctx.note_path.exists() and personal.read_text().startswith('# Personal')
    # A DB-associated corrupted engine file still blocks.
    con.execute('UPDATE jobs SET note_path=? WHERE job_id=?', (str(personal), ctx.job['job_id']))
    assert migration.preview(con, root, output)['conflicts'][0]['blocking']


def test_F06_consent_does_not_follow_output_change(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    note._publish(ctx, ctx.work / 'note.json.part')
    other = output.parent / 'other-vault'
    other.mkdir()
    legacy = legacy_note(other, ctx.job['job_id'])
    before = legacy.read_bytes()
    ctx.settings['output'] = str(other)
    store.request_process(con, ctx.job['job_id'])
    row = store.claim(con, 'boot', ctx.settings)
    ctx = executor.Context(con, row, 'boot', ctx.settings, row['active_run_id'], ctx.work, paths=ctx.paths)
    with pytest.raises(executor.Blocked, match='vault_migration'):
        note._publish(ctx, ctx.work / 'next.json.part')
    assert legacy.read_bytes() == before and list(other.iterdir()) == [legacy]
    migration.migrate(con, root, other, apply=True, consent=True)
    assert notes.parse_note(legacy.read_bytes())[0]['qc_schema'] == 2


def test_F07_bootstrap_refresh_while_executor_is_blocked(tmp_path):
    clock, entered, release, refreshed = [1000.0], threading.Event(), threading.Event(), threading.Event()
    class Blocking(Idle):
        def run_one(self, **kwargs):
            entered.set()
            assert release.wait(4)
            return None
    class ObservedAuth(Auth):
        def refresh(self):
            super().refresh()
            if clock[0] == 1061:
                refreshed.set()
    runtime = Runtime(settings_at(tmp_path), support=tmp_path / 'support', label_check=lambda _: False,
                      executor_factory=Blocking, scan=lambda *a, **k: None)
    auth = runtime.auth = ObservedAuth(runtime.support, 8000, clock=lambda: clock[0])
    auth.refresh()
    old = auth.token
    runtime.start()
    try:
        assert entered.wait(1)
        clock[0] = 1061
        assert refreshed.wait(2), 'executor blocks bootstrap refresh'
        data = read_bootstrap(runtime.support, clock=lambda: clock[0])
        assert data['token'] != old and data['expires'] == 1121
        assert auth.exchange(old) is None
        assert auth.exchange(data['token']) and auth.exchange(data['token']) is None
    finally:
        release.set()
        runtime.close()


def test_F08_backfill_serializes_whole_remote_and_include_update(tmp_path, monkeypatch):
    entered, release, overlap = threading.Event(), threading.Event(), threading.Event()
    state = {'names': {'one.m4a', 'two.m4a'}}
    def unignore(inbox, names):
        snapshot = set(state['names'])
        if names == ['one.m4a']:
            entered.set()
            assert release.wait(3)
        else:
            overlap.set()
        state['names'] = snapshot - set(names)
        return names
    monkeypatch.setattr(backfill.syncthing, 'unignore', unignore)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(backfill.request, ['one.m4a'], settings=settings_at(tmp_path))
        assert entered.wait(1)
        second = pool.submit(backfill.request, ['two.m4a'], settings=settings_at(tmp_path))
        try:
            assert not overlap.wait(.2), 'second request entered remote read/modify/write'
        finally:
            release.set()
        first.result()
        second.result()
    assert state['names'] == set()
    assert backfill.included(tmp_path / 'include.txt') == {'one.m4a', 'two.m4a'}
    assert not list(tmp_path.glob('*.part'))


class Available:
    name = 'codex'
    def status(self): return providers.ProviderStatus(True, True, 'test', 'verified')
    def endpoint_class(self): return 'external'
    def complete(self, prompt, *, timeout): return providers.Completion('OK', 'test', 'external', 0)


@pytest.mark.parametrize('action', ['settings', 'check'])
def test_F09_resolved_blocks_only_requeue(tmp_path, monkeypatch, action):
    settings = settings_at(tmp_path)
    monkeypatch.setattr(providers, 'registry', lambda _: {'codex': Available()})
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        for reason in ('auth', 'no_verified_provider', 'no_local_provider', 'disk_low'):
            store.add_job(con, reason, reason, 'test.m4a', '/unused', 100)
            row = store.claim(con, 'boot', settings)
            store.fail(con, row['job_id'], row['active_run_id'], 'boot', reason, blocked_reason=reason)
        changes = {'providers.order': ['codex'], 'providers.consent': {
            'codex': ['transcript', 'source_name', 'project_list']}}
        if action == 'check':
            settings = config.Settings(settings.snapshot() | changes, {}, frozenset(), settings.path)
            assert integrations.check_provider(settings, 'codex', providers.registry)['ok']
        else:
            save(settings, changes)
        assert store.job(con, 'auth')['status'] == 'queued'
        assert store.job(con, 'no_verified_provider')['status'] == 'queued'
        assert store.job(con, 'no_local_provider')['blocked_reason'] == 'no_local_provider'
        assert store.job(con, 'disk_low')['blocked_reason'] == 'disk_low'


@pytest.mark.parametrize('field,value', [(field, value) for field in ('type_basis_id', 'label', 'name_id')
                                       for value in ([], {}, 123, None) if field != 'name_id' or value is not None])
def test_F10_malformed_classifier_fields_retry_then_fallback(monkeypatch, field, value, provider_context):
    bad = json.loads(json.dumps(BASE_REPLY))
    if field == 'type_basis_id':
        bad[field] = value
    else:
        bad['speakers'][0][field] = value
    calls = []
    def first(prompt):
        calls.append('first')
        return json.dumps(bad)
    def second(prompt):
        calls.append('second')
        return json.dumps(BASE_REPLY)
    engines(monkeypatch, {'codex': first, 'claude': second})
    result, provider = postprocess.classify(TURNS, [t['text'] for t in TURNS], 'synthetic.m4a', [])
    assert provider == 'claude' and result['type_basis_id'] == 't1'
    assert calls == ['first', 'first', 'second']


@pytest.mark.parametrize('name,check_name', [('codex', 'codex'), ('codex', 'claude'), ('ollama', 'ollama')])
def test_F11_check_is_busy_during_executor_provider_call(tmp_path, monkeypatch, name, check_name):
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Blocking(Available):
        def complete(self, prompt, *, timeout):
            calls.append(prompt)
            if prompt == 'engine synthetic':
                entered.set()
                assert release.wait(3)
            return super().complete(prompt, timeout=timeout)
    provider = Blocking()
    provider.name = name
    other = Available()
    other.name = check_name
    registry = lambda _: {name: provider, **({check_name: other} if name != check_name else {})}
    monkeypatch.setattr(providers, 'registry', registry)
    settings = settings_at(tmp_path)
    settings = config.Settings(settings.snapshot() | {'providers.order': [name],
        'providers.consent': {name: ['transcript'], check_name: ['transcript']}}, {}, frozenset(), settings.path)
    def run():
        ctx = SimpleNamespace(settings=settings.snapshot(), current_stage='summarize', call_seq=1,
                              checkpoint=lambda: None, record=lambda *a, **k: None)
        with providers.use_context(ctx):
            return providers.complete('engine synthetic')
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run)
        assert entered.wait(1)
        try:
            result = integrations.check_provider(settings, check_name, registry)
            assert result['ok'] is False and result['reason'] == 'busy'
            assert calls == ['engine synthetic']
        finally:
            release.set()
        assert future.result()[0] == 'OK'


def test_F03_startup_recovers_prepared_journal_of_closed_job(context, monkeypatch):
    ctx = context
    prepare = store.prepare_publication
    def interrupt(*args, **kwargs):
        prepare(*args, **kwargs)
        raise KeyboardInterrupt()
    monkeypatch.setattr(store, 'prepare_publication', interrupt)
    with pytest.raises(KeyboardInterrupt):
        publish(ctx)
    store.exclude(ctx.con, ctx.job['job_id'])
    with pytest.raises(executor.Excluded):
        ctx.checkpoint()
    store.recover(ctx.con, 'restart', recover_publication=notes.recover_publication)
    assert ctx.con.execute('SELECT 1 FROM publications').fetchone() is None
    assert not list((Path(ctx.settings['output']) / '.quietclerk-tmp').glob('*'))


def test_F06_each_vault_has_separate_manifest_and_normalized_identity(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    first = legacy_note(output, ctx.job['job_id'])
    migration.migrate(con, root, output, apply=True, consent=True)
    assert store.vault_migrated(con, output / 'sub' / '..')
    second = output.parent / 'second'
    second.mkdir()
    target = legacy_note(second, ctx.job['job_id'])
    assert not store.vault_migrated(con, second)
    assert not store.note_was_migrated(con, ctx.job['job_id'], second)
    migration.migrate(con, root, second, apply=True, consent=True)
    assert store.vault_migrated(con, second)
    assert notes.parse_note(first.read_bytes())[0]['qc_schema'] == 2
    assert notes.parse_note(target.read_bytes())[0]['qc_schema'] == 2
    assert len(list((root / 'note-backups').glob('migration-*.json'))) == 2


def test_F06_old_global_state_binds_to_historical_output_only(vault):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    # Old successful run is durable evidence for the old automatic empty-vault gate.
    store.complete(con, ctx.job['job_id'], ctx.run_id, 'boot', output / 'old.md')
    con.execute("INSERT INTO meta VALUES('vault_migration','done')")
    con.execute("INSERT INTO meta VALUES(?, 'done')", ('note_migrated:' + ctx.job['job_id'],))
    with closing(store.connect(root / 'state.sqlite3')) as reopened:
        assert store.vault_migrated(reopened, output)
        assert store.note_was_migrated(reopened, ctx.job['job_id'], output)
        assert not store.vault_migrated(reopened, output.parent / 'new')
        assert reopened.execute("SELECT 1 FROM meta WHERE key='vault_migration'").fetchone() is None


@pytest.mark.parametrize('stage', ['correct', 'summarize'])
@pytest.mark.parametrize('response', [[], {}, 1, None])
def test_F10_non_text_responses_follow_validation_fallback(monkeypatch, stage, response, provider_context):
    calls = []
    def invalid(prompt):
        calls.append('first')
        return response
    def valid(prompt):
        calls.append('second')
        return (json.dumps([{'id': i, 'text': 'fixed'} for i in range(len(TURNS))]) if stage == 'correct'
                else '## 핵심 요약\n- 합성 요약 [t1]')
    engines(monkeypatch, {'codex': invalid, 'claude': valid})
    if stage == 'correct':
        assert postprocess.correct(TURNS, [])[0] == ['fixed'] * len(TURNS)
    else:
        assert postprocess.summarize(TURNS, [t['text'] for t in TURNS], BASE_REPLY)[1] == 'claude'
    assert calls == ['first', 'first', 'second']


def test_F09_release_checks_blocked_stage_fields_and_deletion(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    monkeypatch.setattr(providers, 'registry', lambda _: {'codex': Available()})
    with closing(store.connect(tmp_path / 'state.sqlite3')) as con:
        for stage in ('correct', 'classify', 'summarize'):
            store.add_job(con, stage, stage, 'test.m4a', '/unused', 100)
            row = store.claim(con, 'boot', settings)
            store.start_stage(con, row['job_id'], row['active_run_id'], 'boot', stage)
            store.fail(con, row['job_id'], row['active_run_id'], 'boot',
                       'no_verified_provider', blocked_reason='no_verified_provider')
        # A tombstone also wins automatic unblocking, even if a stale retry row remains.
        con.execute("INSERT INTO tombstones VALUES('summarize',0)")
        save(settings, {'providers.order': ['codex'], 'providers.consent': {'codex': ['transcript']}})
        assert store.job(con, 'correct')['status'] == 'queued'
        assert store.job(con, 'classify')['blocked_reason'] == 'no_verified_provider'
        assert store.job(con, 'summarize')['blocked_reason'] == 'no_verified_provider'


def test_F11_parallel_checks_report_busy_without_second_probe(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class Probe(Available):
        def complete(self, prompt, *, timeout):
            entered.set()
            assert release.wait(3)
            return super().complete(prompt, timeout=timeout)
    provider = Probe()
    settings = settings_at(tmp_path)
    settings = config.Settings(settings.snapshot() | {'providers.order': ['codex'],
        'providers.consent': {'codex': ['transcript']}}, {}, frozenset(), settings.path)
    registry = lambda _: {'codex': provider}
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(integrations.check_provider, settings, 'codex', registry)
        assert entered.wait(1)
        try:
            assert integrations.check_provider(settings, 'codex', registry)['reason'] == 'busy'
        finally:
            release.set()
        assert first.result()['ok']


@pytest.mark.parametrize('done', [False, True])
def test_F06_old_manifest_only_transfers_completed_consent(vault, done):
    con, root, output = vault
    ctx = stage_context(con, root, output)
    store.complete(con, ctx.job['job_id'], ctx.run_id, 'boot', output / 'old.md')
    con.execute("INSERT INTO meta VALUES('vault_migration','done')")
    backup_root = root / 'note-backups'
    backup_root.mkdir()
    other = output.parent / 'other'
    (backup_root / 'migration.json').write_text(json.dumps({'output': str(other), 'done': done}))
    with closing(store.connect(root / 'state.sqlite3')) as reopened:
        assert store.vault_migrated(reopened, other) is done
        assert store.vault_migrated(reopened, output) is not done


def test_serve_reports_heartbeat_to_an_ops_board_only_when_one_exists(tmp_path, monkeypatch):
    # After the upgrade the old 60 s tick (which sent heartbeats) is gone; without this the
    # operator's "pipeline heartbeat stale" alert fires although the service is healthy.
    log = tmp_path / 'ops-calls'
    exe = tmp_path / 'bin' / 'ops'
    exe.parent.mkdir()
    exe.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    exe.chmod(0o755)
    monkeypatch.setenv('PATH', f"{exe.parent}:{os.environ['PATH']}")
    class Idle:
        def __init__(self, *args): pass
        def run_one(self, **kwargs): return None
    def run(root):
        runtime = Runtime(config.load(environ={'QC_ROOT': str(root)}), support=root / 'support',
                          label_check=lambda _: False, executor_factory=Idle, scan=lambda *a, **k: None)
        runtime.start()
        time.sleep(1)
        runtime.close()
    run(tmp_path / 'plain')
    assert not log.exists()
    (tmp_path / 'boarded' / '.ops').mkdir(parents=True)
    run(tmp_path / 'boarded')
    assert f"heartbeat --source rec-pipeline --dir {tmp_path / 'boarded'}" in log.read_text()
