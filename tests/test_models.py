import json
import math
import wave

import pytest

from quietclerk.backends import Availability, InvalidOutput, ModelMissing, validate_output
from quietclerk.language import decide_language, detect, processing_language, speech_windows
from quietclerk import worker
from quietclerk.transcript import turns


@pytest.mark.parametrize('start,end', [(float('nan'), 1), (0, float('inf')), (-1, 1), (2, 1), (0, 11), (True, 1)])
def test_invalid_output_timing(start, end):
    with pytest.raises(InvalidOutput):
        validate_output([{'start': start, 'end': end, 'text': 'word'}], 10, words=True)


def test_output_order_blank_words_and_equal_starts():
    rows = [{'start': 1, 'end': 2, 'text': ' a '}, {'start': 1, 'end': 3, 'text': 'b'},
            {'start': 0, 'end': 1, 'text': ' '}]
    assert [r['text'] for r in validate_output(rows, 10, words=True)] == ['a', 'b']
    with pytest.raises(InvalidOutput):
        validate_output(rows[:2] + [{'start': 0, 'end': 1, 'text': 'bad'}], 10, words=True)


def test_speech_union_six_bins_max_twenty_seconds():
    windows = speech_windows([{'start': 0, 'end': 180}, {'start': 50, 'end': 300}], 300)
    assert windows == [{'start': i * 50, 'end': i * 50 + 20} for i in range(6)]


def test_silence_and_short_dialogue():
    assert decide_language([], [])['status'] == 'no_speech'
    windows = speech_windows([{'start': i * 10, 'end': i * 10 + 1} for i in range(6)], 60)
    result = decide_language(windows, [{'ko': 1}] * len(windows))
    assert result['status'] == 'uncertain'
    assert result['shares'] == {'ko': 1}


def test_mixed_late_switch_and_ties():
    windows = [{'start': i * 10, 'end': i * 10 + 10} for i in range(6)]
    scores = [{'ko': 1}] * 3 + [{'en': 1}] * 3
    result = decide_language(windows, scores, 'en')
    assert result['status'] == 'uncertain' and result['top'] == 'en'
    assert result['shares'] == {'en': .5, 'ko': .5}
    assert decide_language(windows, [{'ko': 1}] * 2 + [{'en': 1}] * 4)['status'] == 'decided'
    assert decide_language(windows, [{'fr': 1}] * 3 + [{'de': 1}] * 3)['top'] == 'de'


def test_duration_weighting_and_unsupported():
    windows = [{'start': 0, 'end': 10}, {'start': 20, 'end': 40}]
    result = decide_language(windows, [{'ko': 1}, {'ja': 1}])
    assert result['status'] == 'unsupported'
    assert result['shares']['ja'] == 2 / 3
    assert decide_language([{'start': 0, 'end': 15}], [{'ko': 1}])['status'] == 'decided'


def test_fixed_language_not_run_and_priority():
    class NoDetect:
        def detect_language(self, *args):
            raise AssertionError('must not load model')
    settings = {'language.mode': 'en', 'language.default': 'ko', 'language_override': 'ko'}
    assert detect(NoDetect(), None, [], 0, settings) == {
        'status': 'not_run', 'top': None, 'shares': {}, 'windows': []}
    assert processing_language(settings, {'status': 'decided', 'top': 'en'}) == 'ko'
    assert processing_language({'language.mode': 'en'}, {}) == 'en'
    assert processing_language({'language.default': 'en'}, {'status': 'uncertain', 'top': 'ko'}) == 'en'
    assert processing_language({}, {'status': 'decided', 'top': 'en'}) == 'en'


def test_turns_normalize_backend_speaker_labels():
    diar = [{'start': 0, 'end': 1, 'speaker': 'raw-9'}, {'start': 2, 'end': 3, 'speaker': 'raw-2'}]
    words = [{'start': 0, 'end': 1, 'text': 'a'}, {'start': 2, 'end': 3, 'text': 'b'}]
    assert [r['speaker'] for r in turns(words, diar)] == ['S1', 'S2']


def worker_args(tmp_path):
    wav = tmp_path / 'audio.wav'
    with wave.open(str(wav), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b'\0\0' * 16000)
    settings = tmp_path / 'settings.json'
    settings.write_text('{"language.mode":"en"}')
    return ['--run-settings', str(settings), '--stage', 'diarize', '--in', str(wav),
            '--out', str(tmp_path / 'output.json')]


class FakeBackend:
    def __init__(self, settings):
        assert settings == {'language.mode': 'en'}

    def available(self):
        return Availability(True, 'test')

    def diarize(self, wav):
        print('library log, not JSON')
        return [{'start': 0, 'end': 1, 'speaker': 'raw'}]

    def model_ids(self, roles=None):
        return {'diarize': 'test/model@' + 'a' * 40}


def test_worker_json_events_and_stderr_logs(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv('QC_LANGUAGE', 'ko')
    assert worker.main(worker_args(tmp_path), backend_factory=FakeBackend) == 0
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    assert [event['type'] for event in events] == ['progress', 'result']
    assert events[-1]['models'] == {'diarize': 'test/model@' + 'a' * 40}
    assert captured.err == 'library log, not JSON\n'


@pytest.mark.parametrize('error', ['ModelMissing', 'BackendUnavailable', 'AudioDecodeError', 'InvalidOutput'])
def test_worker_error_json(tmp_path, capsys, error):
    class ErrorBackend(FakeBackend):
        def diarize(self, wav):
            raise getattr(worker, error)('failure')
    assert worker.main(worker_args(tmp_path), backend_factory=ErrorBackend) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err.splitlines()[-1]) == {'error': error, 'detail': 'failure'}
    assert all(json.loads(line)['type'] == 'progress' for line in captured.out.splitlines())


@pytest.mark.parametrize('scores', [[], [{}], [{'ko': float('nan')}], [{'ko': 1.1}], [{'ko': '1'}]])
def test_invalid_language_scores(scores):
    with pytest.raises(InvalidOutput):
        decide_language([{'start': 0, 'end': 20}], scores)


def test_stage_worker_retry_and_terminal_errors(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from quietclerk.stages import models
    from quietclerk.executor import StageFailure

    calls = []
    def fail(*args, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(1, args[0], stderr='{"error":"InvalidOutput"}')
    monkeypatch.setattr(models.procs, 'run', fail)
    ctx = SimpleNamespace(checkpoint=lambda: None, work=tmp_path, settings={}, stage_params={'models': {}},
                          job={'language_override': None, 'duration_sec': 1},
                          paths={'convert': tmp_path / 'audio.wav'}, current_stage='diarize')
    with pytest.raises(StageFailure) as error:
        models._model('diarize')(ctx, tmp_path / 'result.part')
    assert str(error.value) == 'InvalidOutput' and not error.value.retryable
    assert len(calls) == 2


@pytest.mark.parametrize('status,exception', [('no_speech', 'NoSpeech'), ('unsupported', 'StageFailure')])
def test_language_stage_policy_failures(tmp_path, monkeypatch, status, exception):
    from types import SimpleNamespace
    from quietclerk.stages import models
    from quietclerk import executor

    out = tmp_path / 'language.json.part'
    def complete(*args, **kwargs):
        out.write_text(json.dumps({'status': status}))
        return SimpleNamespace(stdout='{"type":"result","models":{}}\n')
    monkeypatch.setattr(models.procs, 'run', complete)
    ctx = SimpleNamespace(checkpoint=lambda: None, record=lambda *a, **kw: None,
                          work=tmp_path, settings={}, review_reasons=[], stage_params={'models': {}},
                          job={'language_override': None, 'duration_sec': 1},
                          paths={'convert': tmp_path / 'audio.wav', 'diarize': tmp_path / 'diar.json'},
                          current_stage='detect_language')
    with pytest.raises(getattr(executor, exception)) as error:
        models._model('detect_language')(ctx, out)
    if status == 'unsupported':
        assert str(error.value) == 'unsupported_language' and not error.value.retryable


def test_worker_rejects_malformed_audio(tmp_path, capsys):
    args = worker_args(tmp_path)
    (tmp_path / 'audio.wav').write_bytes(b'not audio')
    assert worker.main(args, backend_factory=FakeBackend) == 1
    assert json.loads(capsys.readouterr().err)['error'] == 'AudioDecodeError'


def test_model_identity_uses_cache_commit(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from quietclerk.backends.mlx import model_snapshot
    revision = 'b' * 40
    snapshot = tmp_path / 'snapshots' / revision
    calls = []
    def cached(repo, **kwargs):
        calls.append((repo, kwargs))
        return str(snapshot)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=cached))
    path, identity = model_snapshot('test/model')
    assert identity == 'test/model@' + revision
    assert path == snapshot
    assert calls == [('test/model', {'local_files_only': True})]


def test_stage_rejects_worker_revision_mismatch(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from quietclerk.stages import models
    from quietclerk.executor import StageFailure
    calls = []
    def complete(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='{"type":"result","models":{"diarize":"wrong@revision"}}\n')
    monkeypatch.setattr(models.procs, 'run', complete)
    ctx = SimpleNamespace(checkpoint=lambda: None, work=tmp_path, settings={},
                          stage_params={'models': {'diarize': 'model@' + 'a' * 40}},
                          job={'language_override': None, 'duration_sec': 1},
                          paths={'convert': tmp_path / 'audio.wav'}, current_stage='diarize')
    with pytest.raises(StageFailure, match='InvalidOutput'):
        models._model('diarize')(ctx, tmp_path / 'result.part')
    assert len(calls) == 2


@pytest.mark.parametrize('mode,segments,status', [
    ('en', [{'start': 0, 'end': 1, 'speaker': 'raw'}], 'not_run'),
    ('auto', [], 'no_speech'),
])
def test_worker_language_json_without_model_inference(tmp_path, capsys, mode, segments, status):
    args = worker_args(tmp_path)
    (tmp_path / 'settings.json').write_text(json.dumps({'language.mode': mode}))
    diar = tmp_path / 'diarize.json'
    diar.write_text(json.dumps(segments))
    args[3] = 'detect_language'
    args.extend(['--in', str(diar)])
    class NoInference:
        def __init__(self, settings):
            pass
        def available(self):
            return Availability(True, 'test')
        def detect_language(self, *args):
            raise AssertionError('no model inference expected')
        def model_ids(self, roles=None):
            return {}
    assert worker.main(args, backend_factory=NoInference) == 0
    assert json.loads((tmp_path / 'output.json').read_text())['status'] == status
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['models'] == {}


def test_backend_model_ids_resolve_without_loading(monkeypatch, tmp_path):
    from quietclerk.backends import mlx
    calls = []
    def snapshot(repo, revision=None):
        calls.append(repo)
        return tmp_path, repo + '@' + 'c' * 40
    monkeypatch.setattr(mlx, 'model_snapshot', snapshot)
    backend = mlx.MLXBackend()
    identities = backend.model_ids()
    assert identities == {role: repo + '@' + 'c' * 40 for role, repo in mlx.MODELS.items()}
    assert calls == list(mlx.MODELS.values())


def test_transcription_params_use_detected_language_and_real_revisions(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from quietclerk.stages import models
    path = tmp_path / 'language.json'
    path.write_text('{"status":"decided","top":"en"}')
    revision = 'test/model@' + 'd' * 40
    monkeypatch.setattr(models, '_identities', lambda roles: {role: revision for role in roles})
    ctx = SimpleNamespace(settings={'language.mode': 'auto', 'language.default': 'ko'},
                          job={'language_override': None}, paths={'language': path})
    primary = models._params('transcribe', ctx)
    secondary = models._params('second_pass', ctx)
    assert primary['language'] == secondary['language'] == 'en'
    assert primary['alignment'] == {'language': 'English'}
    assert primary['models'] == {'asr': revision, 'aligner': revision}
    assert primary['chunk_rule_version'] == 2 and primary['chunk_max_sec'] == 60.0
    assert secondary['models'] == {'whisper': revision}


def test_real_synthetic_aligner_overrun_is_clamped():
    from pathlib import Path
    sample = json.loads((Path(__file__).parent / 'fixtures' / 'aligner-overrun.json').read_text())
    result = validate_output([sample['word']], sample['duration'], words=True)
    assert result[0]['start'] == sample['expected_start']
    assert result[0]['end'] == sample['expected_end']


@pytest.mark.parametrize('duration,count', [(59.999, 1), (60, 1), (60.0000625, 2),
                                         (61.1445, 2), (120, 2), (120.0000625, 3)])
def test_balanced_chunk_boundaries(duration, count):
    from quietclerk.backends.mlx import balanced_chunks
    samples = round(duration * 16000)
    chunks = balanced_chunks(samples, 16000)
    assert len(chunks) == count
    assert chunks[0][0] == 0 and chunks[-1][1] == samples
    assert all(end - start <= 60 * 16000 for start, end in chunks)
    assert all(chunks[i][1] == chunks[i + 1][0] for i in range(len(chunks) - 1))
    sizes = [end - start for start, end in chunks]
    assert max(sizes) - min(sizes) <= 1


@pytest.mark.parametrize('start,end', [(0, 10.49), (10.49, 10.49), (0, 10.5)])
def test_half_second_end_overshoot_clamps(start, end):
    row = validate_output([{'start': start, 'end': end, 'text': 'word'}], 10, words=True)[0]
    assert row['end'] == 10
    assert row['start'] == min(start, 10)


def test_over_half_second_end_overshoot_rejected():
    with pytest.raises(InvalidOutput):
        validate_output([{'start': 0, 'end': 10.51, 'text': 'word'}], 10, words=True)


def test_tiny_backward_steps_at_segment_seams_are_smoothed_but_real_disorder_is_not():
    # 56-min real meeting: two 0.02 s steps back failed the whole recording (2026-11-10).
    from quietclerk.backends.mlx import smooth_order
    words = [{'start': 1485.4, 'end': 1485.6, 'text': '등'}, {'start': 1485.38, 'end': 1485.5, 'text': '을'},
             {'start': 1490.0, 'end': 1490.2, 'text': '다음'}, {'start': 1489.0, 'end': 1489.3, 'text': '역행'}]
    smoothed = smooth_order(words)
    assert smoothed[1]['start'] == 1485.4 and smoothed[1]['end'] == 1485.5
    validate_output(smoothed[:3], 1500, words=True)
    with pytest.raises(InvalidOutput):
        validate_output(smoothed, 1500, words=True)
