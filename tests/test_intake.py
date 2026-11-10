"""§5 acceptance with generated AAC only; no installed paths or real recordings.

Policy map: unsupported names ignored, incomplete/empty sources wait; unsafe
containers/limits reject without jobs; policy skips retain only hash identity.
"""
import os
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

from quietclerk import backfill, config, executor, intake, probe, quarantine, store


def tone(path, seconds=1, *, noise=False, silence=False):
    source = ('anullsrc=r=16000:cl=mono' if silence else
              'anoisesrc=r=16000:seed=42' if noise else 'sine=frequency=440')
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', source,
                    '-t', str(seconds), '-c:a', 'aac', str(path)], check=True)
    os.utime(path, (1000, 1000))
    return path


@pytest.fixture
def env(tmp_path):
    (tmp_path / 'INBOX').mkdir()
    (tmp_path / 'archive').mkdir()
    settings = config.load(environ={'QC_ROOT': str(tmp_path), 'QC_INBOX': str(tmp_path / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '0', 'QC_STABLE_SEC': '0',
                                   'QC_SINCE': '1970-01-01 00:00'})
    con = store.connect(tmp_path / 'state.sqlite3')
    yield tmp_path, con, settings
    con.close()


def file_row(con, path):
    return con.execute('SELECT * FROM files WHERE path=?', (path.name,)).fetchone()


def assert_clean(tmp):
    root = tmp / 'quarantine'
    assert not root.exists() or not list(root.iterdir())


def test_in03_duration_boundary(env, monkeypatch):
    tmp, con, settings = env
    settings = config.load(environ={'QC_ROOT': str(tmp), 'QC_INBOX': str(tmp / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '300', 'QC_STABLE_SEC': '0',
                                   'QC_SINCE': '1970-01-01 00:00'})
    for duration in (299, 300):
        path = tone(tmp / 'INBOX' / f'{duration}.m4a', duration)
        [job_id] = intake.scan(con, now=1100, settings=settings)
        job = store.job(con, job_id)
        assert job['status'] == ('skipped' if duration == 299 else 'queued')
        assert job['skip_reason'] == ('too_short' if duration == 299 else None)
        assert file_row(con, path)['sha256'] == intake.sha256(path)
        assert (job['archive_path'] is None) == (duration == 299)
    assert_clean(tmp)


def test_in04_before_cutoff_and_in18_nfc_include(env, monkeypatch):
    tmp, con, settings = env
    settings = config.load(environ={'QC_ROOT': str(tmp), 'QC_INBOX': str(tmp / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '0', 'QC_STABLE_SEC': '0',
                                   'QC_SINCE': '2026-11-09 10:59'})
    names = ['음성 261106_142617.m4a', '음성 261105_083634.m4a']
    (settings.root / 'include.txt').write_text(names[0] + '\n', encoding='utf-8')
    for i, name in enumerate(names):
        path = tone(tmp / 'INBOX' / unicodedata.normalize('NFD', name), i + 1)
        [job_id] = intake.scan(con, now=1100, settings=settings)
        job = store.job(con, job_id)
        assert job['status'] == ('queued' if i == 0 else 'skipped')
        assert job['skip_reason'] == (None if i == 0 else 'before_cutoff')
        assert job['source_name'] == file_row(con, path)['name_nfc'] == name


@pytest.mark.parametrize('change', ['same', 'missing', 'changed', 'renamed'])
def test_in05_promote_revalidates_original(env, monkeypatch, change):
    tmp, con, settings = env
    settings = config.load(environ={'QC_ROOT': str(tmp), 'QC_INBOX': str(tmp / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '10', 'QC_STABLE_SEC': '0',
                                   'QC_SINCE': '1970-01-01 00:00'})
    path = tone(tmp / 'INBOX' / 'short.m4a')
    [job_id] = intake.scan(con, now=1100, settings=settings)
    old_sha = store.job(con, job_id)['sha256']
    if change == 'missing':
        path.unlink()
    elif change == 'changed':
        tone(path, 2)
    elif change == 'renamed':
        path = path.rename(path.with_name('다른 이름.m4a'))
    calls = []
    original = probe.duration
    def observed(private):
        assert private.parent == tmp / 'quarantine'
        calls.append(private)
        return original(private)
    monkeypatch.setattr(probe, 'duration', observed)
    assert intake.promote(con, job_id, now=1200, settings=settings) == (change in ('same', 'renamed'))
    job = store.job(con, job_id)
    assert job['sha256'] == old_sha
    assert job['status'] == ('queued' if change in ('same', 'renamed') else 'skipped')
    if job['status'] == 'queued':
        assert intake.sha256(Path(job['archive_path'])) == old_sha
        assert file_row(con, path)['sha256'] == old_sha
    elif change == 'changed':
        assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 2
        assert file_row(con, path)['sha256'] != old_sha
    assert bool(calls) == (change != 'missing')
    assert_clean(tmp)


def test_in05_nonpolicy_promotion_cannot_override_validation(env):
    tmp, con, settings = env
    row = store.add_job(con, 'legacy', 'a' * 64, 'old.m4a', None, 3, 'skipped', 'too_short')
    # An ineligible state must not trigger any source reads or become queued.
    with store.transaction(con):
        con.execute("UPDATE jobs SET skip_reason='legacy_rejected',legacy=1,last_error='format' WHERE job_id=?", (row['job_id'],))
    with pytest.raises(store.Conflict):
        intake.promote(con, row['job_id'], settings=settings)
    assert store.job(con, row['job_id'])['status'] == 'skipped'


def test_in06_in07_ignored_paths_leave_no_records(env):
    tmp, con, settings = env
    inbox = tmp / 'INBOX'
    for name in ('통화 홍길동.m4a', unicodedata.normalize('NFD', '통화 녹음.m4a'), '.hidden.m4a',
                 'clip.mp3', 'notes.txt'):
        (inbox / name).write_bytes(b'ignored')
    outside = tone(tmp / 'outside.m4a')
    (inbox / 'link.m4a').symlink_to(outside)
    (inbox / 'nested').mkdir()
    shutil.copyfile(outside, inbox / 'nested' / 'recording.m4a')
    assert intake.scan(con, now=1100, settings=settings) == []
    assert con.execute('SELECT COUNT(*) FROM files').fetchone()[0] == 0
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0


def test_in08_zero_byte_waits_and_late_growth_is_accepted(env):
    tmp, con, settings = env
    path = tmp / 'INBOX' / 'empty.m4a'
    path.touch()
    intake.scan(con, now=1100, settings=settings)
    row = file_row(con, path)
    assert row['intake_status'] == 'waiting'
    assert intake.waiting_info(row, now=4699) is None
    assert intake.waiting_info(row, now=4700) == 'empty_file'
    tone(path)
    assert len(intake.scan(con, now=4800, settings=settings)) == 1
    assert intake.waiting_info(file_row(con, path), now=5000) is None


def test_in09_stability_restarts_after_growth(env, monkeypatch):
    tmp, con, settings = env
    settings = config.load(environ={'QC_ROOT': str(tmp), 'QC_INBOX': str(tmp / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '0', 'QC_STABLE_SEC': '60',
                                   'QC_SINCE': '1970-01-01 00:00'})
    path = tone(tmp / 'INBOX' / 'growing.m4a')
    assert intake.scan(con, now=1010, settings=settings) == []
    with path.open('ab') as output:
        # A valid free atom, rather than invalid trailing bytes.
        output.write(b'\0\0\0\x08free')
    os.utime(path, (1065, 1065))
    assert intake.scan(con, now=1070, settings=settings) == []
    assert intake.scan(con, now=1129, settings=settings) == []
    assert len(intake.scan(con, now=1130, settings=settings)) == 1
    assert intake.scan(con, now=1200, settings=settings) == []


def test_in10_truncated_m4a_is_decode_rejection_without_job(env):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'truncated.m4a')
    data = path.read_bytes()
    path.write_bytes(data[:-17])
    os.utime(path, (1000, 1000))
    assert intake.scan(con, now=1100, settings=settings) == []
    row = file_row(con, path)
    assert (row['intake_status'], row['reject_reason'], row['sha256']) == ('rejected', 'decode', None)
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    assert_clean(tmp)


def test_in11_disguised_format_and_unsupported_codec(env):
    tmp, con, settings = env
    fake = tmp / 'INBOX' / 'fake.m4a'
    fake.write_bytes(b'RIFF' + b'not an MP4' * 10)
    os.utime(fake, (1000, 1000))
    codec = tmp / 'INBOX' / 'alac.m4a'
    subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i',
                    'sine=duration=1', '-c:a', 'alac', str(codec)], check=True)
    os.utime(codec, (1000, 1000))
    assert intake.scan(con, now=1100, settings=settings) == []
    assert file_row(con, fake)['reject_reason'] == 'format'
    assert file_row(con, codec)['reject_reason'] == 'codec'
    assert file_row(con, fake)['sha256'] is file_row(con, codec)['sha256'] is None
    assert_clean(tmp)


def test_in13_sparse_oversized_file_never_hashed_or_probed(env, monkeypatch):
    tmp, con, settings = env
    path = tmp / 'INBOX' / 'huge.m4a'
    with path.open('wb') as output:
        output.truncate(config.MAX_BYTES + 1)
    os.utime(path, (1000, 1000))
    def forbidden(*args, **kwargs):
        pytest.fail('oversized input was read, hashed or probed')
    monkeypatch.setattr(quarantine.hashlib, 'sha256', forbidden)
    monkeypatch.setattr(quarantine.os, 'read', forbidden)
    monkeypatch.setattr(probe, 'duration', forbidden)
    assert intake.scan(con, now=1100, settings=settings) == []
    row = file_row(con, path)
    assert (row['reject_reason'], row['sha256']) == ('too_big', None)
    assert_clean(tmp)


@pytest.mark.parametrize('duration,reason', [(10801, 'too_long'), (float('nan'), 'decode'),
                                           (float('inf'), 'decode'), (0, 'decode'), (-1, 'decode')])
def test_in14_invalid_probe_lengths(env, monkeypatch, duration, reason):
    import json
    from types import SimpleNamespace
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'duration.m4a')
    def result(*args, **kwargs):
        assert kwargs['timeout'] == 30
        assert args[0][args[0].index('-protocol_whitelist') + 1] == 'file'
        assert args[0][args[0].index('-f') + 1] == 'mov'
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2', 'duration': duration},
            'streams': [{'codec_type': 'audio', 'codec_name': 'aac'}]}))
    monkeypatch.setattr(probe.procs, 'run', result)
    assert intake.scan(con, now=1100, settings=settings) == []
    assert file_row(con, path)['reject_reason'] == reason
    assert file_row(con, path)['sha256'] is None
    assert_clean(tmp)


@pytest.mark.parametrize('stop_at', ['copy', 'rename'])
def test_in15_disk_low_stops_copy_or_archive(env, stop_at):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'disk.m4a')
    calls = []
    def available(root):
        calls.append(root)
        return (2 << 30) if stop_at == 'rename' and len(calls) == 1 else (2 << 30) - 1
    result = intake.scan(con, now=1100, free_space=available, settings=settings)
    assert result == [] and result.blocked_reason == 'disk_low'
    assert len(calls) == (1 if stop_at == 'copy' else 2)
    assert file_row(con, path)['intake_status'] == 'waiting'
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    assert not list((tmp / 'archive').iterdir())
    assert_clean(tmp)
    assert len(intake.scan(con, now=1200, free_space=lambda _: 2 << 30, settings=settings)) == 1


def test_in15_promotion_disk_low_keeps_skipped(env, monkeypatch):
    tmp, con, settings = env
    settings = config.load(environ={'QC_ROOT': str(tmp), 'QC_INBOX': str(tmp / 'INBOX'),
                                   'QC_MIN_DURATION_SEC': '10', 'QC_STABLE_SEC': '0',
                                   'QC_SINCE': '1970-01-01 00:00'})
    tone(tmp / 'INBOX' / 'short.m4a')
    [job_id] = intake.scan(con, now=1100, settings=settings)
    with pytest.raises(intake.DiskLow):
        intake.promote(con, job_id, free_space=lambda _: 0, settings=settings)
    assert store.job(con, job_id)['status'] == 'skipped'
    assert_clean(tmp)


def test_in16_duplicate_and_tombstone(env):
    tmp, con, settings = env
    first = tone(tmp / 'INBOX' / 'one.m4a')
    [job_id] = intake.scan(con, now=1100, settings=settings)
    second = tmp / 'INBOX' / 'renamed.m4a'
    shutil.copy2(first, second)
    assert intake.scan(con, now=1200, settings=settings) == []
    assert file_row(con, second)['intake_status'] == 'duplicate'
    other = tone(tmp / 'INBOX' / 'deleted.m4a', 2)
    with store.transaction(con):
        con.execute('INSERT INTO tombstones VALUES(?,?)', (intake.sha256(other), 1000))
    assert intake.scan(con, now=1300, settings=settings) == []
    assert file_row(con, other)['reject_reason'] == 'deleted_by_user'
    assert store.job(con, job_id)['status'] == 'queued'
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 1
    assert_clean(tmp)


def test_in17_same_name_different_contents_creates_new_job(env):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'same.m4a')
    [first] = intake.scan(con, now=1100, settings=settings)
    first_sha = store.job(con, first)['sha256']
    tone(path, 2)
    [second] = intake.scan(con, now=1200, settings=settings)
    assert first != second
    assert store.job(con, second)['sha256'] != first_sha
    assert intake.sha256(Path(store.job(con, first)['archive_path'])) == first_sha


@pytest.mark.parametrize('noise', [False, True])
def test_in19_synthetic_silence_noise_no_speech_transition(env, noise):
    """Assumed detector decision; real synthetic audio intake + executor/store transition."""
    tmp, con, settings = env
    tone(tmp / 'INBOX' / 'quiet.m4a', noise=noise, silence=not noise)
    [job_id] = intake.scan(con, now=1100, settings=settings)
    def no_speech(ctx, out):
        raise executor.NoSpeech()
    registry = (executor.Stage('detect_language', 'language.json', ('archive',), {}, no_speech),)
    result = executor.Executor(con, 'test', settings, registry).run_one()
    assert (result['status'], result['skip_reason']) == ('skipped', 'no_speech')
    assert result['job_id'] == job_id and result['attempts'] == 0


@pytest.mark.parametrize('prefixes,length', [(0, 8), (1, 16), (2, 32)])
def test_job_id_collision_expands_hash(env, prefixes, length):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / '음성 261109_101500.m4a')
    digest = intake.sha256(path)
    for size in (8, 16)[:prefixes]:
        store.add_job(con, '20261109-101500-' + digest[:size], str(size) * 32,
                      'seed.m4a', '/synthetic/source.m4a', 1)
    [job_id] = intake.scan(con, now=1100, settings=settings)
    assert job_id == '20261109-101500-' + digest[:length]
    assert store.job(con, job_id)['recorded_at'] == '20261109-101500'


@pytest.mark.parametrize('replacement', ['symlink', 'regular', 'growing'])
def test_midcopy_replacement_stays_waiting(env, monkeypatch, replacement):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'race.m4a')
    bait = tmp / 'bait'
    bait.write_bytes(b'never read')
    original = quarantine.os.read
    replaced = False
    def racing(descriptor, size):
        nonlocal replaced
        data = original(descriptor, size)
        if not replaced:
            replaced = True
            if replacement == 'growing':
                with path.open('ab') as output:
                    output.write(b'changed')
            else:
                path.unlink()
                if replacement == 'symlink':
                    path.symlink_to(bait)
                else:
                    path.write_bytes(b'replacement')
        return data
    monkeypatch.setattr(quarantine.os, 'read', racing)
    monkeypatch.setattr(probe, 'duration', lambda _: pytest.fail('raced file was probed'))
    assert intake.scan(con, now=1100, settings=settings) == []
    assert file_row(con, path)['intake_status'] == 'waiting'
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
    assert_clean(tmp)


@pytest.mark.parametrize('name', ['../escape.m4a', '/absolute.m4a', 'nested/a.m4a', '..\\escape.m4a', 'bad\0.m4a'])
def test_quarantine_rejects_path_escape_names(env, name):
    tmp, con, settings = env
    with pytest.raises(probe.Rejected, match='path'):
        quarantine.copy(tmp / 'INBOX', name, tmp / 'quarantine', 100)
    assert not (tmp / 'quarantine').exists()


def test_probe_timeout_is_decode_and_cleans_quarantine(env, monkeypatch):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'timeout.m4a')
    def timeout(*args, **kwargs):
        raise probe.procs.StageTimeout(args[0], 30, 'probe')
    monkeypatch.setattr(probe.procs, 'run', timeout)
    assert intake.scan(con, now=1100, settings=settings) == []
    assert file_row(con, path)['reject_reason'] == 'decode'
    assert_clean(tmp)


def test_quarantine_enforces_limit_during_growth(env, monkeypatch):
    tmp, con, settings = env
    path = tmp / 'INBOX' / 'grows.m4a'
    path.write_bytes(b'initial!')
    original = quarantine.os.read
    counts = []
    def growing(descriptor, size):
        data = original(descriptor, size)
        counts.append(len(data))
        if len(counts) == 1:
            with path.open('ab') as output:
                output.write(b'x' * 32)
        return data
    monkeypatch.setattr(quarantine.os, 'read', growing)
    with pytest.raises(probe.Rejected, match='too_big'):
        quarantine.copy(tmp / 'INBOX', path.name, tmp / 'quarantine', 16)
    assert sum(counts) == 17  # At most the limit plus one sentinel byte is read.
    assert_clean(tmp)


@pytest.mark.parametrize('name', ['bad\\name.m4a', 'bad\nname.m4a'])
def test_unsafe_filename_is_rejected_not_a_job(env, name):
    tmp, con, settings = env
    path = tmp / 'INBOX' / name
    path.write_bytes(b'unsafe name')
    os.utime(path, (1000, 1000))
    assert intake.scan(con, now=1100, settings=settings) == []
    row = file_row(con, path)
    assert (row['intake_status'], row['reject_reason'], row['sha256']) == ('rejected', 'path', None)
    assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
