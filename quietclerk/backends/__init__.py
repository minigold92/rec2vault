"""Model backend contract and worker-visible errors (no settings imports)."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ModelMissing(RuntimeError):
    pass


class BackendUnavailable(RuntimeError):
    pass


class AudioDecodeError(RuntimeError):
    pass


class InvalidOutput(RuntimeError):
    pass


@dataclass(frozen=True)
class Availability:
    available: bool
    reason: str


class Backend(Protocol):
    name: str

    def available(self) -> Availability: ...
    def diarize(self, wav: Path) -> list[dict]: ...
    def detect_language(self, wav: Path, windows: list[dict]) -> list[dict]: ...
    def transcribe(self, wav: Path, lang: str) -> list[dict]: ...
    def second_pass(self, wav: Path, lang: str) -> list[dict]: ...
    def model_ids(self, roles=None) -> dict[str, str]: ...


def validate_output(rows, duration, *, words=False):
    """Clamp only <=0.5 s end overshoot; reject all other malformed timing."""
    import math

    if not isinstance(rows, list) or not math.isfinite(duration) or duration < 0:
        raise InvalidOutput('invalid output or audio duration')
    result = []
    previous = -1.0
    for row in rows:
        if not isinstance(row, dict):
            raise InvalidOutput('segment must be an object')
        if words:
            if not isinstance(row.get('text'), str):
                raise InvalidOutput('text must be a string')
            if not row['text'].strip():
                continue
        try:
            start, end = row['start'], row['end']
            if (isinstance(start, bool) or isinstance(end, bool) or
                    not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or
                    not math.isfinite(start) or not math.isfinite(end) or
                    not 0 <= start <= end or end - duration > 0.5):
                raise InvalidOutput('invalid or unordered segment timing')
        except KeyError as exc:
            raise InvalidOutput('missing segment timing') from exc
        except OverflowError as exc:
            raise InvalidOutput('segment timing overflows finite seconds') from exc
        start, end = min(start, duration), min(end, duration)
        if start < previous:
            raise InvalidOutput('unordered segment timing')
        if not words and not isinstance(row.get('speaker'), str):
            raise InvalidOutput('speaker must be a string')
        previous = start
        result.append({**row, 'start': start, 'end': end,
                       **({'text': row['text'].strip()} if words else {})})
    return result
