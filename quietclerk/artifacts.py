"""Immutable run artifacts with atomic data/metadata and content-verified reuse."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def metadata(path):
    return Path(str(path) + '.meta.json')


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')


def commit(path, part, *, stage, run_id, inputs, params, seq=1, ok=True):
    path, part = Path(path), Path(part)
    # Only the temporary inode is ever modified, including for hardlinked outputs.
    os.replace(part, path)
    meta = {'stage': stage, 'producer': {'run_id': run_id, 'stage_seq': seq},
            'inputs': inputs, 'params': params, 'output_sha256': sha256(path),
            'created_at': datetime.now(timezone.utc).isoformat(), 'ok': ok}
    meta_path = metadata(path)
    temporary = Path(str(meta_path) + '.part')
    write_json(temporary, meta)
    os.replace(temporary, meta_path)
    return meta


ANY_PARAMS = object()


def reusable(path, stage, inputs, params):
    try:
        meta = json.loads(metadata(path).read_text(encoding='utf-8'))
        return meta if (meta.get('ok') is True and meta.get('stage') == stage and
                        meta.get('inputs') == inputs and
                        (params is ANY_PARAMS or meta.get('params') == json.loads(json.dumps(params))) and
                        sha256(path) == meta.get('output_sha256') and
                        isinstance(meta.get('producer', {}).get('run_id'), str)) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def reuse(source, target):
    source, target = Path(source), Path(target)
    for old, new in ((source, target), (metadata(source), metadata(target))):
        part = Path(str(new) + '.part')
        part.unlink(missing_ok=True)
        try:
            os.link(old, part)
        except OSError:
            shutil.copyfile(old, part)
        os.replace(part, new)


# A re-summary keeps the transcript the meeting already has: these stages are reused from
# the newest verified earlier output even if models, rules or settings changed since.
RESUMMARY_KEPT = ('convert', 'diarize', 'detect_language', 'transcribe', 'second_pass', 'turns', 'correct')


def cache_allowed(stage, mode):
    # v1 files have no verified metadata; legacy jobs may nevertheless have valid v2 runs.
    if stage in ('note', 'render'):
        return False
    if mode == 'resummarize' and stage in ('classify', 'summarize'):
        return False
    if mode == 'from_transcribe' and stage not in ('convert', 'diarize'):
        return False
    return True


def find(runs_dir, current_run, name, stage, inputs, params, *, run_ids=None):
    """Verified earlier output for these inputs; params=ANY_PARAMS takes the newest one."""
    hits = []
    for directory in sorted(Path(runs_dir).iterdir(), key=lambda p: p.name, reverse=True):
        if directory.name == current_run or not directory.is_dir() or (run_ids is not None and directory.name not in run_ids):
            continue
        path = directory / name
        meta = reusable(path, stage, inputs, params)
        if meta is not None:
            if params is not ANY_PARAMS:
                return path, meta
            hits.append((meta.get('created_at') or '', path, meta))
    if hits:
        _, path, meta = max(hits, key=lambda hit: hit[0])
        return path, meta
    return None
