"""Duration-weighted language votes over the union of diarized speech."""
import json
import math
from .backends import InvalidOutput

SUPPORTED = ('ko', 'en')


def fixed_language(settings, override=None):
    value = override or settings.get('language_override') or settings.get('language.mode', 'auto')
    if value == 'auto':
        return None
    if value not in SUPPORTED:
        raise InvalidOutput('invalid fixed language')
    return value


def processing_language(settings, detection, override=None):
    return (fixed_language(settings, override) or
            (detection.get('top') if detection.get('status') == 'decided' else None) or
            settings.get('language.default', 'ko'))


def job_settings(ctx):
    """Run settings plus the job's own language override (contract 6.1 precedence)."""
    return {**ctx.settings, 'language_override': ctx.job['language_override']}


def context_language(ctx):
    """The processing language every stage of a run uses: model stages and text stages alike."""
    path = ctx.paths.get('language')
    detection = json.loads(path.read_text(encoding='utf-8')) if path else {}
    return processing_language(job_settings(ctx), detection)


def speech_windows(segments, duration):
    merged = []
    for seg in segments:
        start, end = seg['start'], seg['end']
        if start == end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    windows = []
    for i in range(6):
        lo, hi = duration * i / 6, duration * (i + 1) / 6
        pieces = [(max(lo, start), min(hi, end)) for start, end in merged
                  if max(lo, start) < min(hi, end)]
        if pieces:
            start, end = max(pieces, key=lambda p: p[1] - p[0])
            windows.append({'start': start, 'end': min(end, start + 20)})
    return windows


def decide_language(windows, scores, default='ko'):
    result = {'status': 'no_speech', 'top': None, 'shares': {}, 'windows': windows}
    if not windows:
        return result
    if len(scores) != len(windows):
        raise InvalidOutput('language score/window count mismatch')
    votes = {}
    for window, candidates in zip(windows, scores):
        if not isinstance(candidates, dict) or not candidates:
            raise InvalidOutput('empty language scores')
        if any(not isinstance(lang, str) or not isinstance(score, (float, int)) or
               not math.isfinite(score) or not 0 <= score <= 1 for lang, score in candidates.items()):
            raise InvalidOutput('invalid language scores')
        top = min(candidates, key=lambda lang: (-candidates[lang], lang != default, lang))
        votes[top] = votes.get(top, 0) + window['end'] - window['start']
    total = sum(votes.values())
    shares = {lang: value / total for lang, value in sorted(votes.items())}
    top = min(shares, key=lambda lang: (-shares[lang], lang != default, lang))
    status = ('uncertain' if total < 15 or shares[top] < 0.6 else
              'decided' if top in SUPPORTED else 'unsupported')
    return {**result, 'status': status, 'top': top, 'shares': shares}


def detect(backend, wav, segments, duration, settings):
    if fixed_language(settings):
        return {'status': 'not_run', 'top': None, 'shares': {}, 'windows': []}
    windows = speech_windows(segments, duration)
    return decide_language(windows, backend.detect_language(wav, windows) if windows else [],
                           settings.get('language.default', 'ko'))
