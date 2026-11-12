"""Consent-only conversion of one migrated note using its latest verified run.

Preview is read-only. The existing publication journal owns both the file move and
commit; a durable store claim restores the prior waiting state on interrupted preparation.
"""
import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .. import artifacts, render, store, store_ops, syncthing
from ..executor import Context
from ..stages.note import render_values
from ..stages.text import output_language
from . import (NoteConflict, digest, durable_write, find_existing, merge_fields, parse_note,
               publish, record_span, safe_path, sync_directory)

CORE = {'turns': 'turns.json', 'correct': 'corrected.json', 'classify': 'classification.json', 'summarize': 'summary.json'}
OPTIONAL = {'language': ('detect_language', 'language.json'), 'transcribe': ('transcribe', 'asr.json'),
            'second_pass': ('second_pass', 'alt.json'), 'diarize': ('diarize', 'diarize.json')}


def _verified(con, root, directory, name, stage, job_id):
    path = directory / name
    try:
        meta_path = artifacts.metadata(path)
        if not safe_path(root, path) or not safe_path(root, meta_path):
            raise ValueError('unsafe artifact')
        if path.stat().st_size > 16 << 20 or meta_path.stat().st_size > 1 << 20:
            raise ValueError('oversized artifact')
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if not artifacts.reusable(path, stage, meta.get('inputs'), artifacts.ANY_PARAMS):
            raise ValueError('unverified artifact')
        producer = con.execute('SELECT job_id FROM runs WHERE run_id=?', (meta['producer']['run_id'],)).fetchone()
        if producer is None or producer['job_id'] != job_id:
            raise ValueError('foreign artifact')
        return path, meta, json.loads(path.read_bytes())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise NoteConflict('artifact_unavailable:' + stage) from exc


def _plan(con, settings, job_id):
    job = store.job(con, job_id)
    if store_ops.deleted(con, job_id):
        raise NoteConflict('processing_data_deleted')
    if job['status'] not in ('done', 'failed', 'retry_wait') or job['exclude_requested']:
        raise NoteConflict('job_running' if job['status'] == 'running' else 'job_not_ready')
    output, root = Path(settings.get('output')).absolute(), Path(settings.get('root')).absolute()
    if not store.vault_migrated(con, output):
        raise NoteConflict('vault_migration')
    if not store.note_was_migrated(con, job_id, output):
        raise NoteConflict('note_not_migrated')
    source = find_existing(output, job)
    if source is None:
        raise NoteConflict('note_missing')
    old = source.read_bytes()
    current, body = parse_note(old)
    try:
        record_span(body)
    except NoteConflict:
        pass
    else:
        raise NoteConflict('note_already_current')
    run = con.execute('SELECT * FROM runs WHERE job_id=? ORDER BY started_at DESC,rowid DESC LIMIT 1', (job_id,)).fetchone()
    if run is None:
        raise NoteConflict('artifact_unavailable')
    directory = root / 'work' / job_id / 'runs' / run['run_id']
    snapshot = json.loads(run['settings_json'])
    snapshot.update({'root': str(root), 'output': str(output)})
    snapshot.update({k: v for k, v in (settings.snapshot() if hasattr(settings, 'snapshot') else settings).items()
                     if k.startswith('daily_note.')})
    ctx = Context(con, job, '', snapshot, run['run_id'], directory)
    metas, values = {}, {}
    for stage, name in CORE.items():
        path, meta, value = _verified(con, root, directory, name, stage, job_id)
        ctx.paths[stage], metas[stage], values[stage] = path, meta, value
    for alias, (stage, name) in OPTIONAL.items():
        if (directory / name).exists():
            path, meta, _ = _verified(con, root, directory, name, stage, job_id)
            ctx.paths[alias], metas[alias] = path, meta
    # The core outputs must describe one coherent execution, not individually valid stale files.
    for stage, dependencies in {'correct': ('turns',), 'classify': ('correct',), 'summarize': ('correct', 'classify')}.items():
        if any(metas[stage].get('inputs', {}).get(CORE[dep]) != metas[dep]['output_sha256'] for dep in dependencies):
            raise NoteConflict('artifact_inputs_mismatch:' + stage)
    if metas['classify'].get('inputs', {}).get('source_name') != artifacts.value_hash(job['source_name']):
        raise NoteConflict('artifact_inputs_mismatch:classify')
    turns, corrected, classification, summary = (values[k] for k in CORE)
    if (not isinstance(turns, list) or not turns or not isinstance(corrected, dict)
            or not isinstance(corrected.get('texts'), list) or len(corrected['texts']) != len(turns)
            or not all(isinstance(t, dict) and isinstance(t.get('speaker'), str)
                       and isinstance(t.get('start'), (int, float)) and isinstance(t.get('end'), (int, float)) for t in turns)
            or not all(isinstance(t, str) for t in corrected['texts'])
            or not isinstance(classification, dict) or not isinstance(classification.get('meta'), dict)
            or not isinstance(summary, dict) or not isinstance(summary.get('text'), str)):
        raise NoteConflict('artifact_invalid')
    props, generated, tasks = render_values(ctx)
    merged, _ = merge_fields(props, current, store.note_field_records(con, job_id))
    target = source.with_name(render.note_name(datetime.strptime(job['recorded_at'], '%Y%m%d-%H%M%S'),
                                              merged.get('title'), 'Recording', mtype=merged.get('type')))
    if not safe_path(output, target) or (target != source and (target.exists() or target.is_symlink())):
        raise NoteConflict('note_name_conflict')
    token = artifacts.value_hash({'job': dict(job), 'run': dict(run), 'source': str(source), 'target': str(target),
                                  'old': hashlib.sha256(old).hexdigest(), 'metas': metas,
                                  'overrides': getattr(ctx, 'override_state', {}), 'settings': snapshot})
    return ctx, source, target, old, body, (props, generated, tasks), token, summary['text']


def preview(con, settings, job_id):
    ctx, source, target, old, body, values, token, summary = _plan(con, settings, job_id)
    return {'job_id': job_id, 'run_id': ctx.run_id, 'current_path': str(source), 'new_path': str(target),
            'summary': summary, 'previous_body': body.decode('utf-8', errors='replace'),
            'previous_body_b64': base64.b64encode(body).decode('ascii'), 'preview_token': token}


def preserved_body(body, language, now):
    title = f'Previous format body ({now:%Y-%m-%d} replaced)' if language == 'en' else f'이전 형식 본문 ({now:%Y-%m-%d} 교체)'
    # Every ASCII punctuation character becomes an entity before Markdown/plugins see it.
    # The exact original bytes live in the outside-vault backup; the vault copy is for reading.
    text = body.decode('utf-8', errors='replace')
    inert = ''.join(c if c.isalnum() or c in ' \t\n' else f'&#x{ord(c):x};' for c in text)
    lines = '\n'.join('> ' + line for line in inert.split('\n'))
    return f'\n> [!note]- {title}\n{lines}\n'.encode('utf-8')


def apply(con, settings, job_id, *, consent=False, preview_token=None):
    if consent is not True or not isinstance(preview_token, str) or not preview_token:
        raise ValueError('consent and preview_token required')
    ctx, source, target, old, body, values, token, _ = _plan(con, settings, job_id)
    if not secrets.compare_digest(token, preview_token):
        raise NoteConflict('conversion_changed')
    root, output = Path(ctx.settings['root']), Path(ctx.settings['output'])
    backups = root / 'note-backups'
    if backups.resolve().is_relative_to(output.resolve()) or not safe_path(root, backups):
        raise NoteConflict('backup_inside_vault')
    now = datetime.now(timezone.utc)
    backup_dir = backups / (now.strftime('%Y%m%dT%H%M%S.%fZ') + '-convert')
    language = output_language(ctx)
    ctx.boot = 'convert-' + secrets.token_hex(16)
    ctx.job = store.begin_note_conversion(con, job_id, ctx.run_id, ctx.boot, ctx.job['updated_at'])
    try:
        # Recheck after taking the job claim and immediately before the durable outside-vault backup.
        if digest(source) != hashlib.sha256(old).hexdigest():
            raise NoteConflict('conversion_changed')
        backup_dir.mkdir(parents=True)
        backup = backup_dir / source.name
        durable_write(backup, old)
        sync_directory(backup_dir)
        sync_directory(backups)
        sync_directory(root)
        target, reasons = publish(ctx, *values, language, conversion={
            'source': source, 'target': target, 'previous_hash': hashlib.sha256(old).hexdigest(),
            'preserved': preserved_body(body, language, now)})
    except BaseException:
        publication = con.execute('SELECT * FROM publications WHERE run_id=?', (ctx.run_id,)).fetchone()
        if publication is not None and publication['state'] == 'renamed':
            from . import recover_publication
            recover_publication(con, publication)
        if not store.publication_committed(con, ctx.run_id):
            store.abort_note_conversion(con, ctx.run_id)
        raise
    syncthing.rescan(target.parent)
    return {'job_id': job_id, 'note_path': str(target), 'backup_path': str(backup), 'status': 'done'}
