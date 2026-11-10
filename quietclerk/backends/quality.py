"""Local ASR quality rules. No model, settings, or network dependencies."""
import math
import re
import unicodedata

from . import InvalidOutput

QUALITY_VERSION = 1
MAX_TERMS = 200
MAX_TERM_CHARS = 40
MAX_PROMPT_CHARS = 2048
SILENCE_PHRASES = (
    '시청해 주셔서 감사합니다', '시청해주셔서 감사합니다', 'MBC 뉴스',
    '구독과 좋아요', '자막 제공', 'Thanks for watching', 'Thank you for watching',
    'Please subscribe', 'Vielen Dank fürs Zuschauen',
)
PARTICLES = ('으로부터', '에게서', '이라도', '에서는', '으로는', '에게는', '까지는',
             '이라고', '이라는', '에서', '에게', '한테', '으로', '로부터', '처럼', '보다',
             '까지', '부터', '마저', '조차', '하고', '이랑', '이라', '이나',
             '은', '는', '이', '가', '을', '를', '의', '에', '와', '과', '도', '만', '로', '랑')


def _term(value):
    if not isinstance(value, str):
        raise InvalidOutput('vocabulary entry must be text')
    value = value.strip()
    if not 1 <= len(value) <= MAX_TERM_CHARS or any(unicodedata.category(c).startswith('C') for c in value):
        raise InvalidOutput('invalid vocabulary length or control character')
    return value


def vocabulary(settings):
    values = settings.get('vocabulary.terms', [])
    if not isinstance(values, list) or len(values) > MAX_TERMS:
        raise InvalidOutput('vocabulary.terms must contain at most 200 terms')
    return list(dict.fromkeys(_term(v) for v in values))


def bias_terms(settings):
    result, size = [], 0
    for term in vocabulary(settings):
        # Qwen folds this data into its system prompt: delimiter/prose injection
        # is excluded from ASR bias only, not from the stored vocabulary/cache key.
        if (not re.fullmatch(r'[\w .+&/#-]+', term) or len(term.split()) > 3 or
                re.search(r'(?i)ignore|instruction|system|assistant|previous|지시|무시|프롬프트', term)):
            continue
        size += len(term) + 2
        if size > MAX_PROMPT_CHARS:
            break
        result.append(term)
    return result


def replacements(settings):
    values = settings.get('vocabulary.replace', [])
    if not isinstance(values, list) or len(values) > 200:
        raise InvalidOutput('vocabulary.replace must contain at most 200 pairs')
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != {'from', 'to'}:
            raise InvalidOutput('invalid vocabulary replacement')
        source, target = _term(value['from']), _term(value['to'])
        if source in seen:
            raise InvalidOutput('duplicate replacement source')
        seen.add(source)
        result.append({'from': source, 'to': target})
    return result


def token_limit(seconds, *, whisper=False):
    # Whisper's text context is 448 tokens including the start tokens and any prompt;
    # its own default sample length is half of that. More crashes decoding (2026-11-10).
    return min(224 if whisper else 992, math.ceil(seconds * 16) + 32)


def _joined(rows):
    spans, text = [], ''
    for row in rows:
        start = len(text)
        text += row['text']
        spans.append((start, len(text)))
        text += ' '
    return text.rstrip(), spans


def loop_spans(text):
    """Three repeated >=4-letter n-grams, or ten short acknowledgements."""
    cuts = []
    # Backreferences cover both token n-grams and unspaced Korean output.
    for match in re.finditer(r'(.{1,80}?)(?:\s*\1){2,}', text, re.DOTALL):
        unit = match.group(1)
        letters = sum(c.isalnum() for c in unit)
        copies = len(re.sub(r'\s', '', match.group())) // max(1, len(re.sub(r'\s', '', unit)))
        if letters >= 4 or (letters and copies >= 10):
            cuts.append((match.start() + len(unit), match.end()))
    return cuts


def has_loop(rows):
    return bool(loop_spans(_joined(rows)[0]))


def _remove(rows, cuts, why):
    text, spans = _joined(rows)
    dropped = []
    for lo, hi in cuts:
        covered = [row for row, (a, b) in zip(rows, spans) if a < hi and lo < b]
        if covered:
            dropped.append({'start': min(r['start'] for r in covered),
                            'end': max(r['end'] for r in covered), 'text': text[lo:hi].strip(), 'why': why})
    result = []
    for row, (a, b) in zip(rows, spans):
        keep = ''.join(text[i] for i in range(a, b) if not any(lo <= i < hi for lo, hi in cuts)).strip()
        if keep:
            result.append({**row, 'text': keep})
    return result, dropped


def clean_rows(rows, silent):
    rows, dropped = _remove(rows, loop_spans(_joined(rows)[0]), 'repetition')
    text, spans = _joined(rows)
    cuts = []
    for phrase in SILENCE_PHRASES:
        pattern = r'\s*'.join(re.escape(p) for p in phrase.split())
        for match in re.finditer(pattern + r'[.!?。]*', text, re.IGNORECASE):
            covered = [row for row, (a, b) in zip(rows, spans) if a < match.end() and match.start() < b]
            if covered and silent(min(r['start'] for r in covered), max(r['end'] for r in covered)):
                cuts.append(match.span())
    rows, removed = _remove(rows, sorted(set(cuts)), 'silence_phrase')
    return rows, dropped + removed


def apply_replacements(rows, pairs):
    """One pass over original text, including terms split across aligned words."""
    if not pairs:
        return rows, []
    text, spans = _joined(rows)
    targets = {p['from']: p['to'] for p in pairs}
    suffix = '|'.join(map(re.escape, PARTICLES))
    sources = '|'.join(re.escape(s) for s in sorted(targets, key=len, reverse=True))
    pattern = re.compile(r'(?<!\w)(' + sources + r')(?=(?:(?:' + suffix + r'))?(?!\w))')
    changes = list(pattern.finditer(text))
    counts = {}
    output = []
    for row, (a, b) in zip(rows, spans):
        cursor, pieces = a, []
        for match in changes:
            lo, hi = match.span()
            if lo >= b or hi <= a:
                continue
            pieces.append(text[cursor:max(a, lo)])
            if a <= lo < b:
                pieces.append(targets[match.group()])
                counts[match.group()] = counts.get(match.group(), 0) + 1
            cursor = min(b, hi)
        pieces.append(text[cursor:b])
        # Empty continuation rows keep timing and provenance; worker validation omits
        # these only when reading an input, not when persisting replacement results.
        output.append({**row, 'text': ''.join(pieces)})
    return output, [{**p, 'count': counts[p['from']]} for p in pairs if p['from'] in counts]


def prune_speakers(segments):
    """Merge only sub-second clusters with temporal evidence; never discard speech."""
    totals = {}
    for row in segments:
        totals[row['speaker']] = totals.get(row['speaker'], 0) + row['end'] - row['start']
    review = []
    if len(totals) >= 8:
        review.extend({'speaker': s, 'why': 'cap_reached', 'detail': '8-speaker model capacity reached'} for s in totals)
    for speaker in totals:
        rows = [r for r in segments if r['speaker'] == speaker]
        duration = sum(r['end'] - r['start'] for r in rows if 'confidence' in r)
        if duration and sum(r.get('confidence', 0) * (r['end'] - r['start']) for r in rows) / duration < .60:
            review.append({'speaker': speaker, 'why': 'low_confidence', 'detail': 'Mean speaker activity probability below 0.60'})
    retained = [r for r in segments if totals[r['speaker']] >= 1]
    result = []
    for speaker, total in totals.items():
        if total < 1:
            review.append({'speaker': speaker, 'why': 'ghost', 'detail': 'Total speech below 1 second; merge only within 2 seconds'})
    for row in segments:
        if totals[row['speaker']] < 1 and retained:
            nearest = min(retained, key=lambda r: (max(0, r['start'] - row['end'], row['start'] - r['end']), r['start']))
            if max(0, nearest['start'] - row['end'], row['start'] - nearest['end']) <= 2:
                row = {**row, 'speaker': nearest['speaker']}
        result.append(row)
    return result, review
