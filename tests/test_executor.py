import json
import errno
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from quietclerk import artifacts, config, executor, store, tick
from quietclerk.stages.text import _legacy_llm

NAMES = ('convert', 'diarize', 'detect_language', 'transcribe', 'second_pass', 'turns', 'correct', 'classify', 'summarize', 'render')
DEPS = {'convert': ('archive',), 'diarize': ('convert',), 'detect_language': ('convert', 'diarize'),
        'transcribe': ('convert', 'language'), 'second_pass': ('convert', 'language'), 'turns': ('transcribe', 'diarize'),
        'correct': ('turns', 'second_pass'), 'classify': ('correct', 'source_name'),
        'summarize': ('correct', 'classify'), 'render': ('summarize',)}


def fake_registry(calls, versions=None, hook=None):
    versions = versions if versions is not None else {}
    stages = []
    for name in NAMES:
        def execute(ctx, out, name=name):
            calls.append(name)
            if hook:
                hook(name, ctx)
            inputs = {key: artifacts.sha256(ctx.paths[key]) for key in DEPS[name] if key in ctx.paths}
            value = {'stage': name, 'version': versions.get(name, 1), 'inputs': inputs}
            if name == 'detect_language':
                value.update(status='decided', language='ko')
            artifacts.write_json(out, value)
            if name == 'render':
                ctx.checkpoint()
                note = Path(ctx.settings['output']) / 'synthetic.md'
                note.parent.mkdir(parents=True, exist_ok=True)
                note.write_text('# synthetic\n', encoding='utf-8')
                ctx.note_path = note
        stages.append(executor.Stage(name, name + '.json', DEPS[name],
                                     lambda ctx, name=name: {'version': versions.get(name, 1)}, execute,
                                     cache=name != 'render'))
    return tuple(stages)


@pytest.fixture
def engine(tmp_path):
    settings = config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path), 'QC_SINCE': '1970-01-01 00:00'})
    con = store.connect(tmp_path / 'state.sqlite3')
    row = store.add_job(con, '20261109-101500-aaaaaaaa', 'a' * 64, 'sample.m4a', '/synthetic/source.m4a', 600)
    yield con, settings, row
    con.close()


def rerun(con, settings, row, calls, versions=None, mode='auto', hook=None):
    if store.job(con, row['job_id'])['status'] != 'queued':
        store.request_process(con, row['job_id'], mode)
    runner = executor.Executor(con, 'boot', settings, fake_registry(calls, versions, hook))
    result = runner.run_one()
    assert result['status'] == 'done'
    return result


def test_reuse_and_hardlink_sent_fields_empty(engine):
    con, settings, row = engine
    calls = []
    first = rerun(con, settings, row, calls)
    assert calls == list(NAMES)
    calls.clear()
    second = rerun(con, settings, row, calls)
    assert calls == ['render']
    records = con.execute('SELECT * FROM stage_runs WHERE run_id=?', (second['current_run_id'],)).fetchall()
    reused = [r for r in records if r['status'] == 'reused']
    assert len(reused) == len(NAMES) - 1
    assert all(r['sent_fields'] == '[]' and r['reused_from'].startswith(first['current_run_id'] + '/') for r in reused)
    base = settings.root / 'work' / row['job_id'] / 'runs'
    assert (base / first['current_run_id'] / 'convert.json').stat().st_ino == (base / second['current_run_id'] / 'convert.json').stat().st_ino


@pytest.mark.parametrize('change', ['params', 'input_hash', 'missing_meta', 'bad_hash'])
def test_cache_invalidation(engine, change):
    con, settings, row = engine
    calls, versions = [], {}
    first = rerun(con, settings, row, calls, versions)
    work = settings.root / 'work' / row['job_id'] / 'runs' / first['current_run_id']
    if change == 'params':
        versions['transcribe'] = 2
    elif change == 'input_hash':
        versions['convert'] = 2
    elif change == 'missing_meta':
        artifacts.metadata(work / 'transcribe.json').unlink()
    elif change == 'bad_hash':
        (work / 'transcribe.json').write_text('corrupted')
    calls.clear()
    rerun(con, settings, row, calls, versions)
    assert 'transcribe' in calls
    if change == 'input_hash':
        assert calls == list(NAMES)
    elif change == 'params':
        assert calls == ['transcribe', 'turns', 'correct', 'classify', 'summarize', 'render']
    else:
        assert calls == ['transcribe', 'render']


@pytest.mark.parametrize('mode,expected', [('resume', ['render']), ('resummarize', ['classify', 'summarize', 'render']),
                                         ('from_transcribe', list(NAMES[2:]))])
def test_reprocessing_mode_boundaries(engine, mode, expected):
    con, settings, row = engine
    calls = []
    rerun(con, settings, row, calls)
    calls.clear()
    rerun(con, settings, row, calls, mode=mode)
    assert calls == expected


def test_resummarize_keeps_the_old_transcript_after_models_or_rules_change(engine):
    # Models, ASR rules or the vocabulary may change after a meeting was transcribed; a
    # re-summary must reuse that transcript instead of transcribing again (2026-11-10).
    con, settings, row = engine
    calls, versions = [], {}
    rerun(con, settings, row, calls, versions)
    versions.update(diarize=2, transcribe=2, second_pass=2, correct=2)
    calls.clear()
    second = rerun(con, settings, row, calls, versions, mode='resummarize')
    assert calls == ['classify', 'summarize', 'render']
    kept = con.execute("SELECT stage FROM stage_runs WHERE run_id=? AND status='reused'",
                       (second['current_run_id'],)).fetchall()
    assert {r['stage'] for r in kept} >= {'diarize', 'transcribe', 'second_pass', 'correct'}


@pytest.mark.parametrize('point', ['next_stage', 'external', 'publish'])
def test_exclusion_finishes_at_next_checkpoint(engine, point):
    con, settings, row = engine
    calls = []

    def hook(name, ctx):
        if (point == 'next_stage' and name == 'diarize') or (point == 'external' and name == 'correct') or (point == 'publish' and name == 'render'):
            store.exclude(con, row['job_id'])
            if point != 'next_stage':
                ctx.checkpoint()

    result = executor.Executor(con, 'boot', settings, fake_registry(calls, hook=hook)).run_one()
    assert (result['status'], result['skip_reason']) == ('skipped', 'user_excluded')
    assert result['attempts'] == 0
    assert con.execute('SELECT status FROM runs').fetchone()[0] == 'skipped'
    assert not (Path(settings.get('output')) / 'synthetic.md').exists()
    if point == 'next_stage':
        assert calls == ['convert', 'diarize']


def test_stage_timeout_and_failure_history(engine):
    from quietclerk.procs import StageTimeout
    con, settings, row = engine

    def timeout(ctx, out):
        raise StageTimeout(['fake'], 1, 'convert')

    registry = (executor.Stage('convert', 'audio.wav', ('archive',), {}, timeout),)
    result = executor.Executor(con, 'boot', settings, registry).run_one()
    assert (result['status'], result['last_error'], result['attempts']) == ('retry_wait', 'timeout:convert', 1)
    assert con.execute('SELECT status FROM stage_runs').fetchone()[0] == 'timeout'
    assert not list((settings.root / 'work').rglob('*.meta.json'))


def test_paused_claim_and_reentrant_guard(engine):
    con, settings, row = engine
    runner = executor.Executor(con, 'boot', settings, ())
    assert runner.run_one(paused=True) is None
    assert store.job(con, row['job_id'])['status'] == 'queued'
    runner.busy = True
    with pytest.raises(RuntimeError, match='already running'):
        runner.run_one()


def test_atomic_replacement_never_mutates_hardlinked_old_run(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    part = tmp_path / 'part'
    part.write_text('old')
    artifacts.commit(first, part, stage='correct', run_id='one', inputs={}, params={})
    artifacts.reuse(first, second)
    assert first.stat().st_ino == second.stat().st_ino
    part.write_text('new')
    artifacts.commit(second, part, stage='correct', run_id='two', inputs={}, params={})
    assert first.read_text() == 'old'
    assert second.read_text() == 'new'
    assert first.stat().st_ino != second.stat().st_ino


def test_artifact_rejects_wrong_inputs_params_missing_data_or_invalid_meta(tmp_path):
    data, part = tmp_path / 'result', tmp_path / 'result.part'
    part.write_bytes(b'payload')
    artifacts.commit(data, part, stage='transcribe', run_id='one', inputs={'audio.wav': 'one'}, params={'model': 'v1'})
    assert artifacts.reusable(data, 'transcribe', {'audio.wav': 'one'}, {'model': 'v1'})
    assert not artifacts.reusable(data, 'transcribe', {'audio.wav': 'two'}, {'model': 'v1'})
    assert not artifacts.reusable(data, 'transcribe', {'audio.wav': 'one'}, {'model': 'v2'})
    data.unlink()
    assert not artifacts.reusable(data, 'transcribe', {'audio.wav': 'one'}, {'model': 'v1'})
    artifacts.metadata(data).write_text('{broken')
    assert not artifacts.reusable(data, 'transcribe', {}, {})


def test_hardlink_copy_fallback(tmp_path, monkeypatch):
    data, part, target = tmp_path / 'data', tmp_path / 'part', tmp_path / 'copy'
    part.write_text('content')
    artifacts.commit(data, part, stage='turns', run_id='one', inputs={}, params={})
    def unavailable(*args):
        raise OSError('different filesystem')
    monkeypatch.setattr(artifacts.os, 'link', unavailable)
    artifacts.reuse(data, target)
    assert target.read_text() == 'content'
    assert artifacts.reusable(target, 'turns', {}, {})


def test_tick_module_synthetic_m4a_end_to_end(tmp_path):
    inbox = tmp_path / 'inbox'
    inbox.mkdir()
    audio = inbox / '음성 261109_101500.m4a'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                    '-c:a', 'aac', str(audio)], check=True)
    environment = {key: value for key, value in os.environ.items() if not key.startswith('QC_')}
    environment.update(QC_ROOT=str(tmp_path), QC_SETTINGS=os.devnull, QC_STABLE_SEC='0', QC_MIN_DURATION_SEC='0',
                       QC_SINCE='1970-01-01 00:00')
    from quietclerk.notes.migration import migrate
    migration_db = store.connect(tmp_path / 'state.sqlite3')
    migrate(migration_db, tmp_path, tmp_path / 'notes', apply=True, consent=True)
    migration_db.close()
    # Inject only model/LLM stages. Real scan, convert, turns, note publication and tick execute.
    script = '''
from quietclerk import artifacts, config, stages
from quietclerk import syncthing
syncthing.CONFIG = config.load().root / 'nonexistent-syncthing.xml'
original = stages.default_registry

def registry():
    def fake(ctx, out):
        name=ctx.current_stage
        if name=='diarize': value=[{'start':0,'end':1,'speaker':'S1'}]
        elif name=='detect_language': value={'status':'decided','language':'ko'}
        elif name in ('transcribe','second_pass'): value=[{'start':0,'end':1,'text':'합성 입력 확인'}]
        elif name=='correct': value={'texts':[t['text'] for t in ctx.load('turns')],'notes':[]}
        elif name=='classify': value={'meta':{'title':'합성 입력','type':'meeting','division':'work','type_confidence':'high','speakers':{}},'engine':'fake'}
        elif name=='summarize': value={'text':'## 핵심 요약\\n- 합성 입력 [t1]','engine':'fake'}
        artifacts.write_json(out,value)
    from dataclasses import replace
    from quietclerk.executor import Stage
    result = []
    for s in original():
        if s.name == 'diarize':
            result.append(replace(s,execute=fake,params={}))
            result.append(Stage('detect_language','language.json',('convert','diarize'),{},fake))
        elif s.name == 'detect_language':
            continue
        else:
            result.append(replace(s,execute=fake,params={}) if s.name in ('transcribe','second_pass','correct','classify','summarize') else s)
    return tuple(result)
stages.default_registry=registry
'''
    # Test-only startup injection keeps the production CLI free of fake-stage switches.
    (tmp_path / 'sitecustomize.py').write_text(script, encoding='utf-8')
    environment['PYTHONPATH'] = os.pathsep.join((str(tmp_path), str(Path(__file__).resolve().parents[1])))
    result = subprocess.run([sys.executable, '-m', 'quietclerk.tick'], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    con = store.connect(tmp_path / 'state.sqlite3')
    job = con.execute('SELECT * FROM jobs').fetchone()
    assert job['status'] == 'done'
    assert job['current_run_id'] is not None and job['active_run_id'] is None
    assert Path(job['note_path']).is_file()
    assert con.execute('SELECT status FROM runs').fetchone()[0] == 'done'
    assert con.execute('SELECT COUNT(*) FROM stage_runs WHERE status="done"').fetchone()[0] == len(NAMES)
    assert list((tmp_path / 'work').rglob('*.meta.json'))
    con.close()


@pytest.mark.parametrize('exclude_between_calls', [False, True])
def test_legacy_external_adapter_records_actual_sent_fields(engine, monkeypatch, exclude_between_calls):
    from quietclerk import providers as llm
    con, settings, row = engine
    snapshot = settings.snapshot()
    snapshot['providers.order'] = ['codex']
    snapshot['providers.consent'] = {'codex': ['transcript']}
    calls = []

    class FakeProvider:
        name = 'codex'

        def endpoint_class(self):
            return 'external'

        def status(self):
            return llm.ProviderStatus(True, True, '0.167.0', 'verified')

        def complete(self, prompt, *, timeout):
            calls.append(prompt)
            if exclude_between_calls:
                store.exclude(con, row['job_id'])
            return llm.Completion('synthetic response', 'fake', 'external', 0)

    monkeypatch.setattr(llm, 'registry', lambda settings: {'codex': FakeProvider()})

    def correct(ctx, out):
        with _legacy_llm(ctx):
            first, _ = llm.complete('synthetic transcript')
            second, _ = llm.complete('synthetic transcript')
        artifacts.write_json(out, [first, second])

    stages = (executor.Stage('correct', 'correct.json', ('archive',), {}, correct),
              fake_registry([])[-1])
    # The final fake stage needs the declared dependency to point to this test's output.
    stages = (stages[0], replace(stages[1], inputs=('correct',), execute=lambda ctx, out: (
        artifacts.write_json(out, {}), setattr(ctx, 'note_path', Path(ctx.settings['output']) / 'fake.md'))))
    result = executor.Executor(con, 'boot', snapshot, stages).run_one()
    subcalls = con.execute('SELECT * FROM stage_runs WHERE parent_seq=1 ORDER BY seq').fetchall()
    assert len(calls) == (1 if exclude_between_calls else 2)
    assert len(subcalls) == len(calls)
    assert all(r['provider'] == 'codex' and json.loads(r['sent_fields']) == ['transcript'] for r in subcalls)
    assert result['status'] == ('skipped' if exclude_between_calls else 'done')


def test_unconsented_and_local_only_legacy_calls_block_without_attempt(engine, monkeypatch):
    from quietclerk import providers as llm
    con, settings, row = engine
    calls = []
    monkeypatch.setattr(llm, 'registry', lambda settings: {})

    def correct(ctx, out):
        with _legacy_llm(ctx):
            llm.complete('must not leave process')

    stages = (executor.Stage('correct', 'correct.json', ('archive',), {}, correct),)
    snapshot = settings.snapshot()
    result = executor.Executor(con, 'boot', snapshot, stages).run_one()
    assert (result['status'], result['blocked_reason'], result['attempts']) == ('retry_wait', 'no_verified_provider', 0)
    store.request_process(con, row['job_id'])
    snapshot['providers.local_only'] = True
    result = executor.Executor(con, 'boot', snapshot, stages).run_one()
    assert (result['status'], result['blocked_reason'], result['attempts']) == ('retry_wait', 'no_local_provider', 0)
    assert calls == []


@pytest.mark.parametrize('kind', ['no_speech', 'unsupported_language'])
def test_stage_policy_skip_and_terminal_failure(engine, kind):
    con, settings, row = engine

    def detect(ctx, out):
        artifacts.write_json(out, {'status': kind})
        if kind == 'no_speech':
            raise executor.NoSpeech()
        raise executor.StageFailure(kind, retryable=False)

    stages = (executor.Stage('detect_language', 'language.json', ('archive',), {}, detect),)
    result = executor.Executor(con, 'boot', settings, stages).run_one()
    if kind == 'no_speech':
        assert (result['status'], result['skip_reason']) == ('skipped', kind)
        assert con.execute('SELECT status FROM stage_runs').fetchone()[0] == 'done'
    else:
        assert (result['status'], result['last_error']) == ('failed', kind)


def test_language_artifact_alias_hash_and_stage_params_reach_consumers(engine):
    con, settings, row = engine
    params = {'asr': {'revision': 'actual-snapshot'}}
    seen = []
    def detect(ctx, out):
        artifacts.write_json(out, {'status': 'decided', 'language': 'en'})
    def consume(ctx, out):
        assert ctx.paths['language'] == ctx.paths['detect_language']
        assert ctx.hashes['language'] == artifacts.sha256(ctx.paths['language'])
        assert ctx.stage_params is params
        seen.append(ctx.load('language')['language'])
        artifacts.write_json(out, {'text': 'English'})
        ctx.note_path = out
    stages = (executor.Stage('detect_language', 'language.json', ('archive',), {}, detect),
              executor.Stage('transcribe', 'asr.json', ('language',), lambda c: params, consume))
    result = executor.Executor(con, 'boot', settings, stages).run_one()
    assert result['status'] == 'done' and seen == ['en']
    work = settings.root / 'work' / row['job_id'] / 'runs' / result['current_run_id']
    meta = json.loads(artifacts.metadata(work / 'asr.json').read_text())
    assert meta['inputs'] == {'language.json': artifacts.sha256(work / 'language.json')}
    assert meta['params'] == params


@pytest.mark.parametrize('rerun_cached', [False, True])
def test_fixed_language_records_not_run_and_retains_artifact(engine, rerun_cached):
    con, settings, row = engine
    def detect(ctx, out):
        artifacts.write_json(out, {'status': 'not_run', 'language': 'en'})
        return 'not_run'
    def finish(ctx, out):
        assert ctx.load('language')['language'] == 'en'
        artifacts.write_json(out, {})
        ctx.note_path = out
    stages = (executor.Stage('detect_language', 'language.json', ('archive',), {}, detect),
              executor.Stage('render', 'note.json', ('language',), {}, finish, cache=False))
    runner = executor.Executor(con, 'boot', settings, stages)
    first = runner.run_one()
    if rerun_cached:
        store.request_process(con, row['job_id'])
        result = runner.run_one()
    else:
        result = first
    assert result['status'] == 'done'
    record = con.execute("SELECT * FROM stage_runs WHERE run_id=? AND stage='detect_language'",
                         (result['current_run_id'],)).fetchone()
    assert record['status'] == 'not_run'
    assert bool(record['reused_from']) == rerun_cached


def test_unsupported_language_commits_nonreusable_failure_artifact(engine):
    con, settings, row = engine
    def detect(ctx, out):
        artifacts.write_json(out, {'status': 'unsupported', 'top': 'fr'})
        raise executor.StageFailure('unsupported_language', retryable=False, artifact=True)
    stages = (executor.Stage('detect_language', 'language.json', ('archive',), {}, detect),)
    result = executor.Executor(con, 'boot', settings, stages).run_one()
    assert (result['status'], result['last_error']) == ('failed', 'unsupported_language')
    record = con.execute('SELECT * FROM stage_runs').fetchone()
    assert (record['status'], record['error']) == ('failed', 'unsupported_language')
    path = settings.root / 'work' / row['job_id'] / 'runs' / record['run_id'] / 'language.json'
    assert json.loads(path.read_text())['status'] == 'unsupported'
    meta = json.loads(artifacts.metadata(path).read_text())
    assert meta['ok'] is False
    assert artifacts.reusable(path, 'detect_language', meta['inputs'], {}) is None


@pytest.mark.parametrize('kind', ['error', 'timeout', 'blocked', 'terminal'])
def test_exclusion_racing_stage_failure_always_skips(engine, kind):
    con, settings, row = engine
    other = store.connect(settings.root / 'state.sqlite3')
    def fail(ctx, out):
        store.exclude(other, row['job_id'])
        if kind == 'timeout':
            raise executor.procs.StageTimeout(['fake'], 1, 'convert')
        if kind == 'blocked':
            raise executor.Blocked('auth')
        if kind == 'terminal':
            raise executor.StageFailure('unsupported_language', retryable=False)
        raise RuntimeError('decode failed')
    try:
        result = executor.Executor(con, 'boot', settings, (
            executor.Stage('convert', 'audio.wav', ('archive',), {}, fail),)).run_one()
    finally:
        other.close()
    assert (result['status'], result['skip_reason'], result['exclude_requested'], result['attempts']) == (
        'skipped', 'user_excluded', 0, 0)
    assert con.execute('SELECT status FROM runs').fetchone()[0] == 'skipped'


def test_disk_low_stops_claim_without_changing_job_then_recovers(engine):
    con, settings, row = engine
    free = [2 * 1024**3 - 1]
    calls = []
    runner = executor.Executor(con, 'boot', settings, fake_registry(calls), free_space=lambda root: free[0])
    assert runner.run_one() is None
    assert store.engine_state(con) == 'disk_low'
    assert store.job(con, row['job_id'])['status'] == 'queued'
    assert con.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 0 and calls == []
    free[0] = 2 * 1024**3
    assert runner.run_one()['status'] == 'done'
    assert store.engine_state(con) is None


def test_enospc_blocks_without_budget_and_releases_only_after_space_recovery(engine):
    con, settings, row = engine
    def fail(ctx, out):
        out.write_bytes(b'partial')
        raise OSError(errno.ENOSPC, 'No space left on device')
    free = [2 * 1024**3]
    runner = executor.Executor(con, 'boot', settings, (
        executor.Stage('convert', 'audio.wav', ('archive',), {}, fail),), free_space=lambda root: free[0])
    failed = runner.run_one()
    assert (failed['status'], failed['blocked_reason'], failed['attempts']) == ('retry_wait', 'disk_low', 0)
    assert store.engine_state(con) == 'disk_low'
    assert not list((settings.root / 'work').rglob('*.meta.json'))
    free[0] -= 1
    assert runner.run_one(now=1e20) is None
    assert store.job(con, row['job_id'])['blocked_reason'] == 'disk_low'
    unrelated = store.add_job(con, '20261109-101500-bbbbbbbb', 'b' * 64, 'other.m4a', '/synthetic/other', 600)
    con.execute("UPDATE jobs SET status='retry_wait',blocked_reason='auth' WHERE job_id=?", (unrelated['job_id'],))
    free[0] += 1
    runner.registry = fake_registry([])
    assert runner.run_one()['status'] == 'done'
    assert store.engine_state(con) is None
    assert store.job(con, unrelated['job_id'])['blocked_reason'] == 'auth'


def test_since_omitted_first_tick_then_new_recording_is_queued(tmp_path, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 11, 9, 10, 0)
        @classmethod
        def now(cls):
            return cls.current
    monkeypatch.setattr(config, 'datetime', Clock)
    # Keep real tick/scan/DB boundaries, pausing only execution so queued is observable.
    monkeypatch.setattr(executor.Executor, 'run_one', lambda self: None)
    environment = {'QC_ROOT': str(tmp_path), 'QC_STABLE_SEC': '0', 'QC_MIN_DURATION_SEC': '0'}
    first = config.load(tmp_path / 'settings.toml', environment)
    assert tick.main(settings=first) == 0
    inbox = tmp_path / 'inbox'
    inbox.mkdir(exist_ok=True)
    audio = inbox / '음성 261109_101500.m4a'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=1', '-c:a', 'aac', str(audio)], check=True)
    Clock.current = datetime(2026, 11, 9, 11, 0)
    second = config.load(tmp_path / 'settings.toml', environment)
    assert second.get('since') == '2026-11-09 10:00'
    assert tick.main(settings=second) == 0
    con = store.connect(tmp_path / 'state.sqlite3')
    job = con.execute('SELECT * FROM jobs').fetchone()
    assert job['status'] == 'queued' and job['skip_reason'] is None
    con.close()
