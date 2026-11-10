"""MLX implementation; model paths are pinned to local HF snapshot commits."""
import importlib.util
import platform
import os
from pathlib import Path

from . import Availability, AudioDecodeError, ModelMissing, InvalidOutput, validate_output

MODELS = {'diarize': 'mlx-community/Nemotron-3-Diarization',
          'asr': 'mlx-community/Qwen3-ASR-1.7B-8bit',
          'aligner': 'mlx-community/Qwen3-ForcedAligner-0.6B-8bit',
          'whisper': 'mlx-community/whisper-large-v3-turbo'}
QWEN_LANGUAGES = {'ko': 'Korean', 'en': 'English'}
STAGE_MODELS = {'diarize': ('diarize',), 'detect_language': ('whisper',),
                'transcribe': ('asr', 'aligner'), 'second_pass': ('whisper',)}


def balanced_chunks(samples, sample_rate):
    """Exactly ceil(duration/60) equal sample ranges; no tiny tail chunks."""
    count = max(1, (samples + sample_rate * 60 - 1) // (sample_rate * 60))
    return [(samples * i // count, samples * (i + 1) // count) for i in range(count)]


def model_snapshot(repo, revision=None):
    try:
        from huggingface_hub import snapshot_download
        options = {'local_files_only': True}
        if revision is not None:
            options['revision'] = revision
        path = Path(snapshot_download(repo, **options)).resolve()
    except (ImportError, OSError) as exc:
        raise ModelMissing(f'{repo}: {exc}') from exc
    revision = path.name
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ModelMissing(f'{repo}: cache snapshot has no commit revision')
    return path, f'{repo}@{revision}'


def read_audio(wav):
    try:
        import soundfile as sf
        audio, sr = sf.read(wav, dtype='float32')
        if sr != 16000 or audio.ndim != 1 or len(audio) == 0:
            raise ValueError('expected nonempty 16kHz mono WAV')
        return audio, sr
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise AudioDecodeError(str(exc)) from exc


JITTER_SEC = 0.1


def smooth_order(words):
    """Pull a word that starts at most JITTER_SEC before the previous one up to it.

    Real aligner output (56-min meeting, 2026-11-10) stepped back 0.02 s twice at segment
    seams, which failed the whole recording. Larger steps back stay invalid."""
    out, previous = [], None
    for word in words:
        if previous is not None and previous - JITTER_SEC <= word['start'] < previous:
            word = {**word, 'start': previous, 'end': max(word['end'], previous)}
        out.append(word)
        previous = word['start']
    return out


class MLXBackend:
    name = 'mlx'

    def __init__(self, settings=None):
        self.settings = settings or {}
        self._used = {}

    def available(self):
        if platform.system() != 'Darwin' or platform.machine() != 'arm64':
            return Availability(False, 'MLX requires Apple Silicon macOS')
        missing = [name for name in ('mlx', 'mlx_audio', 'mlx_whisper', 'soundfile')
                   if importlib.util.find_spec(name) is None]
        if missing:
            return Availability(False, 'missing dependencies: ' + ', '.join(missing))
        import mlx.core as mx
        if not mx.metal.is_available():
            return Availability(False, 'Metal device unavailable')
        return Availability(True, f'Apple Silicon; memory={os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")}')

    def _model(self, role):
        expected = self.settings.get('model_ids', {}).get(role)
        revision = expected.rsplit('@', 1)[1] if expected else None
        path, identity = model_snapshot(MODELS[role], revision)
        if expected and identity != expected:
            raise InvalidOutput('model revision differs from run settings')
        self._used[role] = identity
        return str(path)

    def model_ids(self, roles=None):
        roles = MODELS if roles is None else roles
        return {role: self._used[role] if role in self._used else model_snapshot(MODELS[role])[1]
                for role in roles}

    def diarize(self, wav):
        import mlx.core as mx
        from mlx_audio.vad import load
        audio, sr = read_audio(wav)
        result = load(self._model('diarize')).generate(mx.array(audio), sample_rate=sr)
        return [{'start': float(s.start), 'end': float(s.end), 'speaker': str(s.speaker)}
                for s in result.segments]

    def detect_language(self, wav, windows):
        if not windows:
            return []
        import mlx.core as mx
        audio, sr = read_audio(wav)
        from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim
        from mlx_whisper.load_models import load_model
        from mlx_whisper.decoding import detect_language
        model = load_model(self._model('whisper'), dtype=mx.float16)
        scores = []
        for window in windows:
            piece = audio[int(window['start'] * sr):int(window['end'] * sr)]
            mel = log_mel_spectrogram(pad_or_trim(mx.array(piece)), n_mels=model.dims.n_mels)
            _, probabilities = detect_language(model, mel)
            scores.append({lang: float(score) for lang, score in probabilities.items()})
        return scores

    def transcribe(self, wav, lang):
        import numpy as np
        from mlx_audio.stt import load
        if lang not in QWEN_LANGUAGES:
            raise InvalidOutput('unsupported transcription language')
        audio, sr = read_audio(wav)
        language = QWEN_LANGUAGES[lang]
        asr = load(self._model('asr'))
        aligner = load(self._model('aligner'))
        words = []
        for first, last in balanced_chunks(len(audio), sr):
            chunk = audio[first:last]
            result = asr.generate(chunk, language=language, chunk_duration=60.0, max_tokens=200000)
            segments = validate_output([
                {'start': float(segment['start']), 'end': float(segment['end']),
                 'text': segment.get('text') or ''} for segment in result.segments],
                len(chunk) / sr, words=True)
            for segment in segments:
                start, end = segment['start'], segment['end']
                piece = np.ascontiguousarray(chunk[int(start * sr):int(end * sr)])
                for word in aligner.generate(audio=piece, text=segment['text'], language=language):
                    words.append({'start': first / sr + start + float(word.start_time),
                                  'end': first / sr + start + float(word.end_time), 'text': word.text})
        return smooth_order(words)

    def second_pass(self, wav, lang):
        import mlx_whisper
        if lang not in QWEN_LANGUAGES:
            raise InvalidOutput('unsupported transcription language')
        result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=self._model('whisper'),
                    language=lang, word_timestamps=True, condition_on_previous_text=False)
        return smooth_order([{'start': w['start'], 'end': w['end'], 'text': w['word']}
                             for segment in result['segments'] for w in segment.get('words', [])])
