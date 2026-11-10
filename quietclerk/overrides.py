"""User speaker/line overlays over immutable, verified run artifacts (contract 10.8 A/B).

Publication uses the existing journal. A short synthetic run owns only the rewrite;
its committed payload restores the real artifact run and commits overlays together.
"""
import copy
import difflib
import hashlib
import json
import re
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from . import artifacts, notes, render, store


class OverrideConflict(ValueError):
    pass


def ensure_schema(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS speaker_overrides (
      job_id TEXT NOT NULL REFERENCES jobs(job_id), label TEXT NOT NULL,
      name TEXT, confirmed INTEGER NOT NULL, merged_into TEXT, updated_at REAL NOT NULL,
      PRIMARY KEY(job_id,label));
    CREATE TABLE IF NOT EXISTS transcript_edits (
      job_id TEXT NOT NULL REFERENCES jobs(job_id), line_id TEXT NOT NULL,
      text TEXT NOT NULL, original_sha256 TEXT NOT NULL, updated_at REAL NOT NULL,
      PRIMARY KEY(job_id,line_id));
    ''')


def clean_string(value, limit):
    if not isinstance(value, str) or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('expected text without control or format characters')
    value = value.strip()
    if not 1 <= len(value) <= limit:
        raise ValueError(f'text must have 1..{limit} characters')
    return value


def _hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _stored(con, job_id):
    return ({r['label']: dict(r) for r in con.execute('SELECT * FROM speaker_overrides WHERE job_id=?', (job_id,))},
            {r['line_id']: dict(r) for r in con.execute('SELECT * FROM transcript_edits WHERE job_id=?', (job_id,))})


def _artifact(root, row, name):
    # IDs come from the DB, but still never trust them as filesystem components.
    directory = Path(root) / 'work' / row['job_id'] / 'runs' / row['current_run_id']
    path = directory / name
    if not notes.safe_path(Path(root), path) or not notes.safe_path(Path(root), artifacts.metadata(path)):
        raise OverrideConflict('artifact_unavailable')
    try:
        if path.stat().st_size > 16 << 20 or artifacts.metadata(path).stat().st_size > 1 << 20:
            raise ValueError('oversized artifact')
        data = path.read_bytes()
        meta = json.loads(artifacts.metadata(path).read_text())
        if meta.get('ok') is not True or meta.get('output_sha256') != hashlib.sha256(data).hexdigest():
            raise ValueError('unverified artifact')
        return json.loads(data)
    except (OSError, ValueError) as exc:
        raise OverrideConflict('artifact_unavailable') from exc


def load_current(con, job, root):
    if not job['current_run_id']:
        raise OverrideConflict('transcript_unavailable')
    run = con.execute('SELECT job_id FROM runs WHERE run_id=?', (job['current_run_id'],)).fetchone()
    if run is None or run['job_id'] != job['job_id']:
        raise OverrideConflict('artifact_unavailable')
    return {key: _artifact(root, job, name) for key, name in (
        ('turns', 'turns.json'), ('correct', 'corrected.json'), ('classify', 'classification.json'),
        ('summarize', 'summary.json'))}


def _effective(turns, texts, meta, speakers, edits):
    turns, texts, meta = copy.deepcopy(turns), list(texts), copy.deepcopy(meta or {})
    labels = {t['speaker'] for t in turns}
    estimates = meta.setdefault('speakers', {})
    for label in labels:
        item = estimates.setdefault(label, {})
        override = speakers.get(label)
        item['confirmed'] = bool(override and override['confirmed'] and override['name'])
        if override:
            item['name'] = override['name'] if item['confirmed'] else None
            item['name_source'] = 'user' if override['name'] else None
        else:
            item['name_source'] = 'engine' if item.get('name') else None
    for i, turn in enumerate(turns):
        label, seen = turn['speaker'], set()
        while label in speakers and speakers[label]['merged_into']:
            if label in seen:
                raise OverrideConflict('merge_cycle')
            seen.add(label)
            label = speakers[label]['merged_into']
        turn['speaker'] = label
        edit = edits.get(f't{i + 1}')
        if edit and edit['original_sha256'] == _hash(texts[i]):
            texts[i] = edit['text']
    for label, value in speakers.items():
        if value['merged_into']:
            estimates.pop(label, None)
    return turns, texts, meta


def read_view(con, job, turns, texts, meta=None):
    speakers, edits = _stored(con, job['job_id'])
    labels = {t['speaker'] for t in turns}
    speakers = {k: v for k, v in speakers.items() if k in labels and (not v['merged_into'] or v['merged_into'] in labels)}
    edits = {k: v for k, v in edits.items() if re.fullmatch(r't[1-9]\d*', k)
             and int(k[1:]) <= len(texts) and v['original_sha256'] == _hash(texts[int(k[1:]) - 1])}
    return (*_effective(turns, texts, meta, speakers, edits), [])


def stage_view(ctx, meta=None):
    """Scratch changes are detected against the last publication, never cached user text."""
    turns, texts = ctx.load('turns'), ctx.load('correct')['texts']
    speakers, edits = _stored(ctx.con, ctx.job['job_id'])
    dropped = []
    run = ctx.con.execute('SELECT mode FROM runs WHERE run_id=?', (ctx.run_id,)).fetchone()
    if speakers and run and run['mode'] != 'resummarize' and ctx.job['current_run_id']:
        previous = _artifact(ctx.settings['root'], ctx.job, 'turns.json')
        signature = lambda rows: [t['speaker'] for t in rows]
        if signature(previous) != signature(turns):
            speakers = {}
            dropped.append('speaker_overrides_dropped')
    valid = {f't{i + 1}': _hash(value) for i, value in enumerate(texts)}
    filtered = {key: value for key, value in edits.items() if valid.get(key) == value['original_sha256']}
    if len(filtered) != len(edits):
        dropped.append('transcript_edits_dropped')
    ctx.override_state = {'speakers': list(speakers.values()), 'edits': list(filtered.values())}
    return (*_effective(turns, texts, meta, speakers, filtered), dropped)


def fingerprint(ctx):
    speakers, edits = _stored(ctx.con, ctx.job['job_id'])
    return artifacts.value_hash({
        'merges': {label: row['merged_into'] for label, row in speakers.items() if row['merged_into']},
        'edits': {ident: (row['text'], row['original_sha256']) for ident, row in edits.items()}})


def commit_state(con, job_id, state):
    con.execute('DELETE FROM speaker_overrides WHERE job_id=?', (job_id,))
    con.execute('DELETE FROM transcript_edits WHERE job_id=?', (job_id,))
    for value in state['speakers']:
        con.execute('INSERT INTO speaker_overrides VALUES(?,?,?,?,?,?)',
                    (job_id, value['label'], value['name'], value['confirmed'], value['merged_into'], value['updated_at']))
    for value in state['edits']:
        con.execute('INSERT INTO transcript_edits VALUES(?,?,?,?,?)',
                    (job_id, value['line_id'], value['text'], value['original_sha256'], value['updated_at']))


def commit_rewrite(con, publication, pending):
    """Called inside the normal publication commit transaction, including recovery."""
    job_id, run_id = publication['job_id'], publication['run_id']
    commit_state(con, job_id, pending['overrides'])
    for field, record in pending['fields'].items():
        con.execute('''INSERT INTO note_fields VALUES(?,?,?,?) ON CONFLICT(job_id,field)
                       DO UPDATE SET owner=excluded.owner,last_generated=excluded.last_generated''',
                    (job_id, field, record['owner'], record['last_generated']))
    prior = pending['rewrite']
    con.execute('''UPDATE jobs SET status=?,current_run_id=?,note_path=?,review_reasons=?,active_run_id=NULL,
                   claimed_by=NULL,claimed_at=NULL,stage=NULL,updated_at=? WHERE job_id=?''',
                (prior['status'], prior['current_run_id'], publication['target_path'],
                 json.dumps(pending['review_reasons']), time.time(), job_id))
    # A rewrite has no model artifacts and must never be selected as a reusable run.
    con.execute("UPDATE runs SET status='done',finished_at=? WHERE run_id=?", (time.time(), run_id))
    con.execute("UPDATE publications SET state='committed',updated_at=? WHERE run_id=?", (time.time(), run_id))


def speakers_response(turns, texts, meta, speakers, edits):
    effective, _, _ = _effective(turns, texts, meta, speakers, edits)
    stats = {}
    for turn in effective:
        stats[turn['speaker']] = stats.get(turn['speaker'], 0.0) + max(0.0, turn['end'] - turn['start'])
    total = sum(stats.values())
    result = []
    for label in sorted({t['speaker'] for t in turns}, key=lambda s: (len(s), s)):
        estimate = meta.get('speakers', {}).get(label, {})
        override = speakers.get(label)
        name = override['name'] if override else estimate.get('name')
        own = [t for t in effective if t['speaker'] == label]
        longest = max(own, key=lambda t: t['end'] - t['start']) if own else None
        sample = ({'start': longest['start'], 'end': min(longest['end'], longest['start'] + 15.0)}
                  if longest and longest['end'] - longest['start'] >= 5 else None)
        result.append({'label': label, 'role': estimate.get('role'), 'name': name,
                       'name_source': ('user' if override else 'engine') if name else None,
                       'confirmed': bool(override and override['confirmed'] and name),
                       'talk_sec': float(stats.get(label, 0)), 'share': stats.get(label, 0) / total if total else 0.0,
                       'sample': sample, 'merged_into': override['merged_into'] if override else None})
    return {'speakers': result}


def transcript_response(turns, texts, meta, speakers, edits):
    effective, changed, _ = _effective(turns, texts, meta, speakers, edits)
    suggestions = []
    for old, new in zip(texts, changed):
        a, b = old.split(), new.split()
        for tag, lo, hi, start, end in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag == 'replace' and hi - lo == end - start == 1:
                pair = {'from': a[lo], 'to': b[start]}
                if pair not in suggestions:
                    suggestions.append(pair)
    return {'lines': [{'id': f't{i + 1}', 'start': float(t['start']), 'end': float(t['end']),
                       'speaker': t['speaker'], 'text': changed[i], 'edited': changed[i] != texts[i],
                       'original': texts[i]} for i, t in enumerate(effective)], 'vocabulary_suggestions': suggestions}


def commit_overrides(con, publication, pending):
    if 'rewrite' in pending:
        commit_rewrite(con, publication, pending)
        return True
    commit_state(con, publication['job_id'], pending['overrides'])
    return False


def rollback_rewrite(con, run_id, prior):
    with store.transaction(con):
        con.execute("UPDATE runs SET status='failed',finished_at=? WHERE run_id=?", (time.time(), run_id))
        con.execute('''UPDATE jobs SET status=?,active_run_id=NULL,claimed_by=NULL,claimed_at=NULL
                       WHERE active_run_id=?''', (prior['status'], run_id))


def _rewrite(con, job, settings, payload, speakers, edits):
    """Claim only this job, atomically with the prepared journal; never execute a model."""
    from .executor import Context
    output = Path(settings.get('output'))
    if not store.vault_migrated(con, output):
        raise OverrideConflict('vault_migration')
    if notes.find_existing(output, job) is None:
        raise OverrideConflict('note_missing')
    run_id, boot = uuid.uuid4().hex, uuid.uuid4().hex
    snapshot = settings.snapshot() if hasattr(settings, 'snapshot') else dict(settings)
    prior = {'status': job['status'], 'current_run_id': job['current_run_id']}

    class RewriteContext(Context):
        def checkpoint(self):
            current = store.job(con, job['job_id'])
            if current['active_run_id'] == run_id:
                return super().checkpoint()
            if current['status'] == 'running':
                raise OverrideConflict('job_running')
            if current['updated_at'] != job['updated_at'] or current['current_run_id'] != job['current_run_id']:
                raise OverrideConflict('job_changed')

        def record(self, method, *args, **kwargs):
            if method is not store.prepare_publication:
                return super().record(method, *args, **kwargs)
            target, previous_hash, new_hash, temp = args
            with store.transaction(con):
                self.checkpoint()
                con.execute('''INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at)
                               VALUES(?,?,'resummarize',?,'{}','running',?)''',
                            (run_id, job['job_id'], json.dumps(snapshot), time.time()))
                con.execute("UPDATE jobs SET status='running',active_run_id=?,claimed_by=? WHERE job_id=?",
                            (run_id, boot, job['job_id']))
                con.execute("INSERT INTO publications VALUES(?,?,?,?,?,?,'prepared',?)",
                            (run_id, job['job_id'], str(target), previous_hash, new_hash, str(temp), time.time()))

    ctx = RewriteContext(con, job, boot, snapshot, run_id, Path(snapshot['root']) / 'work')
    ctx.publication_extra = {'rewrite': prior,
                             'overrides': {'speakers': list(speakers.values()), 'edits': list(edits.values())}}
    try:
        turns, texts, meta = _effective(payload['turns'], payload['correct']['texts'], payload['classify']['meta'], speakers, edits)
        props, current_body = notes.parse_note(notes.find_existing(output, job).read_bytes())
        language = 'en' if b'## Meeting record' in current_body else 'ko'
        engines = {'transcribe': props.get('pipeline_asr', []), 'postprocess': props.get('pipeline_llm', []),
                   'external_text_to': props.get('external_text_to', [])}
        values = render.components(job, datetime.strptime(job['recorded_at'], '%Y%m%d-%H%M%S'), turns, texts, meta,
                                   payload['summarize']['text'], payload['correct'].get('notes', []), engines,
                                   datetime.now(), props.get('language', 'ko'), props.get('language_detected'), language,
                                   review_reasons=json.loads(job['review_reasons'] or '[]'))
        notes.publish(ctx, *values, language)
    except BaseException:
        publication = con.execute('SELECT * FROM publications WHERE run_id=?', (run_id,)).fetchone()
        if publication and publication['state'] == 'renamed':
            notes.recover_publication(con, publication)
        elif publication is None or publication['state'] != 'committed':
            rollback_rewrite(con, run_id, prior)
        raise


def api(con, settings, job_id, action, item, method, data):
    """Return a Starlette response; shared middleware owns authentication/idempotency."""
    from starlette.responses import JSONResponse, Response
    try:
        job = store.job(con, job_id)
        if method != 'GET' and con.execute('SELECT 1 FROM tombstones WHERE sha256=?', (job['sha256'],)).fetchone():
            raise OverrideConflict('processing_data_deleted')
        if method != 'GET' and job['status'] == 'running':
            raise OverrideConflict('job_running')
        payload = load_current(con, job, settings.get('root'))
        turns, texts, meta = payload['turns'], payload['correct']['texts'], payload['classify']['meta']
        speakers, edits = _stored(con, job_id)
        if method == 'GET' and item is None:
            value = speakers_response(turns, texts, meta, speakers, edits) if action == 'speakers' else transcript_response(turns, texts, meta, speakers, edits)
            return JSONResponse(value)
        labels = {turn['speaker'] for turn in turns}
        now = time.time()
        if action == 'speakers' and item == 'merge' and method == 'POST':
            if set(data) != {'from', 'into'} or data['from'] not in labels or (data['into'] is not None and data['into'] not in labels):
                raise ValueError('expected existing from/into speaker labels')
            source, target = data['from'], data['into']
            if source == target:
                raise ValueError('cannot merge a speaker into itself')
            row = speakers.setdefault(source, {'label': source, 'name': None, 'confirmed': False, 'merged_into': None, 'updated_at': now})
            row.update(merged_into=target, updated_at=now)
            _effective(turns, texts, meta, speakers, edits)  # validates the complete merge graph
        elif action == 'speakers' and method == 'PUT' and item in labels:
            if set(data) != {'name', 'confirmed'} or type(data['confirmed']) is not bool:
                raise ValueError('expected name and boolean confirmed')
            name = clean_string(data['name'], 40) if data['name'] is not None else None
            if name is None and data['confirmed']:
                raise ValueError('a confirmed speaker requires a name')
            row = speakers.setdefault(item, {'label': item, 'merged_into': None})
            row.update(name=name, confirmed=data['confirmed'], updated_at=now)
        elif action == 'transcript' and method in ('PUT', 'DELETE'):
            if not re.fullmatch(r't[1-9]\d*', item or '') or int(item[1:]) > len(turns):
                raise KeyError(item)
            if method == 'DELETE':
                edits.pop(item, None)
            else:
                if set(data) != {'text'}:
                    raise ValueError('expected text')
                edits[item] = {'line_id': item, 'text': clean_string(data['text'], 2000),
                               'original_sha256': _hash(texts[int(item[1:]) - 1]), 'updated_at': now}
        else:
            raise KeyError(item)
        _rewrite(con, job, settings, payload, speakers, edits)
        return Response(status_code=204)
    except OverrideConflict as exc:
        return JSONResponse({'error': 'override_conflict', 'reason': str(exc)}, 409)
