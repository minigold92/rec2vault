"""Combine ASR words with diarization segments into speaker turns."""


def artifact_rows(value, key='words'):
    """Read legacy list caches and current metadata envelopes without rewriting."""
    from .backends import InvalidOutput
    if isinstance(value, dict):
        value = value.get(key)
    if not isinstance(value, list):
        raise InvalidOutput(f'expected {key} artifact rows')
    return value


def assign_speakers(words, diar):
    """Give each word the diarization speaker it overlaps most; zero-overlap words take the nearest segment."""
    words, diar = artifact_rows(words), artifact_rows(diar, 'segments')
    out = []
    for w in words:
        best, best_ov = None, 0.0
        for d in diar:
            ov = min(w["end"], d["end"]) - max(w["start"], d["start"])
            if ov > best_ov:
                best, best_ov = d["speaker"], ov
        if best is None and diar:
            mid = (w["start"] + w["end"]) / 2
            best = min(diar, key=lambda d: min(abs(mid - d["start"]), abs(mid - d["end"])))["speaker"]
        out.append({**w, "speaker": best})
    return out


def turns(words, diar, gap=1.5):
    """Consecutive words of one speaker (pause < gap s) form a turn. Speakers become S1, S2, … by first appearance."""
    names: dict = {}
    result = []
    for w in assign_speakers(words, diar):
        text = w["text"].strip()
        if not text:
            continue
        spk = names.setdefault(w["speaker"], f"S{len(names) + 1}")
        if result and result[-1]["speaker"] == spk and w["start"] - result[-1]["end"] < gap:
            result[-1]["end"] = w["end"]
            result[-1]["text"] += " " + text
        else:
            result.append({"start": w["start"], "end": w["end"], "speaker": spk, "text": text})
    return result


def window_text(words, start, end, pad=5.0) -> str:
    return " ".join(w["text"].strip() for w in artifact_rows(words)
                    if start - pad <= w["start"] < end + pad).strip()


def stamp(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"
