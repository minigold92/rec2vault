"""§5.1-8 / IN-14: PCM duration, rather than container metadata, is authoritative."""
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from quietclerk import config, executor, store
from quietclerk.stages import audio
from test_intake import tone


@pytest.mark.parametrize('expected,valid', [(1, True), (.5, False), (2, False)])
def test_in14_actual_decode_checks_probe_duration(tmp_path, expected, valid):
    source = tone(tmp_path / 'source.m4a')
    ctx = SimpleNamespace(job={'archive_path': str(source), 'duration_sec': expected}, checkpoint=lambda: None)
    out = tmp_path / 'audio.part'
    if valid:
        audio._convert(ctx, out)
        assert out.stat().st_size > 32000
    else:
        with pytest.raises(executor.StageFailure, match='^audio_decode$') as exc:
            audio._convert(ctx, out)
        assert not exc.value.retryable


def sparse_pcm(path, seconds):
    size = seconds * 16000 * 2
    with path.open('wb') as output:
        output.write(struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + size, b'WAVE', b'fmt ',
                                 16, 1, 1, 16000, 32000, 2, 16, b'data', size))
        output.truncate(44 + size)


@pytest.mark.parametrize('decoded,expected', [(10801, 10800), (300, 600)])
def test_in14_false_metadata_or_over_three_hours_is_failed_audio_decode(tmp_path, monkeypatch, decoded, expected):
    settings = config.load(tmp_path / 'settings.toml', {'QC_ROOT': str(tmp_path)})
    con = store.connect(tmp_path / 'state.sqlite3')
    row = store.add_job(con, 'synthetic', 'a' * 64, 'synthetic.m4a', '/synthetic/source.m4a', expected)
    calls = []
    def decode(command, **kwargs):
        calls.append(command)
        assert command[command.index('-protocol_whitelist') + 1] == 'file'
        assert command[command.index('-f') + 1] == 'mov'
        assert command[command.index('-enable_drefs') + 1] == '0'
        sparse_pcm(Path(command[-1]), decoded)
    monkeypatch.setattr(audio.procs, 'run', decode)
    stage = executor.Stage('convert', 'audio.wav', ('archive',), {}, audio._convert)
    result = executor.Executor(con, 'test', settings, (stage,)).run_one()
    assert (result['status'], result['last_error']) == ('failed', 'audio_decode')
    assert result['job_id'] == row['job_id'] and len(calls) == 1
    assert not list((tmp_path / 'work').rglob('*.meta.json'))
    con.close()


def test_convert_enospc_is_retryable_not_audio_decode(tmp_path, monkeypatch):
    import errno
    import subprocess
    ctx = SimpleNamespace(job={'archive_path': '/synthetic/source.m4a', 'duration_sec': 1},
                          checkpoint=lambda: None)
    def full(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=b'No space left on device')
    monkeypatch.setattr(audio.procs, 'run', full)
    with pytest.raises(OSError) as exc:
        audio._convert(ctx, tmp_path / 'audio.part')
    assert exc.value.errno == errno.ENOSPC
