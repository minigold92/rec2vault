"""Consent-only, resumable legacy frontmatter migration; bodies stay byte-exact."""
import fcntl
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .. import render, store
from . import NoteConflict, dump_frontmatter, durable_write, parse_note, safe_notes, safe_path, sync_directory

KEY_MAP = {
    '구분': 'division', '유형': 'type', '상태': 'status', '프로젝트': 'project',
    '날짜': 'date', '녹음시작': 'started_at', '길이분': 'duration_min',
    '원본파일': 'source_file', '원본해시': 'source_sha256', '처리_작업ID': 'job_id',
    '주제': 'topics', '프로젝트_제안': 'project_suggest', '참석자': 'attendees',
    '화자': 'speakers', '화자수': 'speaker_count', '검토필요': 'needs_review',
    '처리_전사': 'pipeline_asr', '처리_후처리': 'pipeline_llm', '처리일시': 'processed_at',
    '처리_기록': 'review_reasons', '제목': 'title', '검토사유': 'review_reasons',
    # The original pre-2026-11-09 renderer already used job_id (not 처리_작업ID).
    'job_id': 'job_id', 'source': 'source_file', 'recorded': 'started_at',
    'duration_min': 'duration_min', 'speakers': 'speaker_count',
    'transcribe': 'pipeline_asr', 'postprocess': 'pipeline_llm', 'tags': 'tags', 'aliases': 'aliases',
}
VALUE_MAP = {
    'division': {'업무': 'work', '개인': 'personal'},
    'type': dict(zip(('회의', '현황공유', '발표회', '강의', '1:1', '브레인스토밍', '기타'),
                     ('meeting', 'status_update', 'presentation', 'lecture', 'one_on_one', 'brainstorm', 'other'))),
    'status': {'AI초안': 'draft', '검토함': 'reviewed'},
    'project': {'미분류': 'unassigned'},
}
V2_KEYS = {'qc_schema', 'title', 'aliases', 'date', 'started_at', 'duration_min', 'language', 'language_detected',
           'type', 'division', 'topics', 'project', 'project_suggest', 'attendees', 'speakers', 'speaker_count',
           'status', 'needs_review', 'review_reasons', 'source_file', 'source_sha256', 'job_id', 'pipeline_asr',
           'pipeline_llm', 'external_text_to', 'processed_at', 'tags'}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def convert(data, job):
    props, body = parse_note(data)
    converted, mapping, conflicts = {}, [], []
    old_format = 'source' in props or 'recorded' in props
    for key, old_value in props.items():
        target = KEY_MAP.get(key, key)
        if key == 'speakers' and not old_format:
            target = 'speakers'
        value = old_value
        if target in VALUE_MAP:
            values = value if isinstance(value, list) else [value]
            new_values = []
            for item in values:
                table = VALUE_MAP[target]
                if not isinstance(item, str):
                    conflicts.append({'key': key, 'value': item, 'reason': 'custom_value', 'blocking': True})
                    new_values.append(item)
                elif item in table:
                    new_values.append(table[item])
                elif item in table.values():
                    new_values.append(item)
                else:
                    conflicts.append({'key': key, 'value': item, 'reason': 'custom_value', 'blocking': target != 'project'})
                    new_values.append(item)
            value = new_values if target == 'project' or isinstance(value, list) else new_values[0]
        if key not in KEY_MAP and key not in V2_KEYS:
            conflicts.append({'key': key, 'value': old_value, 'reason': 'custom_key', 'blocking': False})
        if target in ('pipeline_asr', 'pipeline_llm') and not isinstance(value, list):
            value = [value] if value else []
        if target == 'started_at' and key == 'recorded':
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M').isoformat(timespec='seconds')
            except (TypeError, ValueError):
                conflicts.append({'key': key, 'value': old_value, 'reason': 'invalid_date', 'blocking': True})
        if target == 'tags' and isinstance(value, list):
            value = ['meeting-notes' if v == '회의록' else v for v in value]
        if target in converted and converted[target] != value:
            conflicts.append({'key': key, 'reason': 'key_collision', 'blocking': True})
        converted[target] = value
        mapping.append({'from_key': key, 'from_value': old_value, 'to_key': target, 'to_value': value})
    for key, expected in (('job_id', job['job_id']), ('source_sha256', job['sha256'])):
        if key in converted and converted[key] != expected:
            conflicts.append({'key': key, 'reason': 'identity_mismatch', 'blocking': True})
        converted.setdefault(key, expected)
    title_match = re.search(rb'(?m)^# ([^\r\n]+)', body)
    title = title_match[1].decode('utf-8') if title_match else Path(job['source_name']).stem
    converted.setdefault('title', title)
    converted.setdefault('division', 'work')
    converted.setdefault('type', 'other')
    converted.setdefault('status', 'draft')
    converted.setdefault('project', ['unassigned'])
    converted.setdefault('attendees', [])
    converted.setdefault('source_file', job['source_name'])
    converted['qc_schema'] = 2
    mapped = {row['to_key'] for row in mapping}
    mapping += [{'from_key': None, 'from_value': None, 'to_key': key, 'to_value': value}
                for key, value in converted.items() if key not in mapped]
    result = dump_frontmatter(converted).encode() + body
    return result, mapping, conflicts


def preview(con, root, output):
    root, output = Path(root).absolute(), Path(output).absolute()
    backup_root = root / 'note-backups'
    if backup_root.resolve().is_relative_to(output.resolve()) or not safe_path(root, backup_root):
        raise NoteConflict('backup_must_be_outside_vault')
    entries, by_job = [], {}
    known_paths = {Path(row['note_path']).resolve() for row in
                   con.execute('SELECT note_path FROM jobs WHERE note_path IS NOT NULL')}
    for path in safe_notes(output):
        try:
            props, _ = parse_note(path.read_bytes())
        except ValueError:
            if path.resolve() in known_paths:
                entries.append({'path': str(path), 'conflicts': [{'reason': 'invalid_frontmatter', 'blocking': True}], 'skip': True})
            continue
        identity = props.get('처리_작업ID', props.get('job_id'))
        if identity is None:
            if path.resolve() in known_paths:
                entries.append({'path': str(path), 'conflicts': [{'reason': 'identity_missing', 'blocking': True}], 'skip': True})
            continue
        if not isinstance(identity, str):
            entries.append({'path': str(path), 'conflicts': [{'reason': 'invalid_identity', 'blocking': True}], 'skip': True})
            continue
        row = con.execute('SELECT * FROM jobs WHERE job_id=?', (identity,)).fetchone()
        if row is None:
            entries.append({'path': str(path), 'job_id': identity,
                            'conflicts': [{'reason': 'job_missing', 'blocking': True}], 'skip': True})
            continue
        if props.get('qc_schema') == 2:
            if props.get('source_sha256') != row['sha256']:
                entries.append({'path': str(path), 'job_id': identity,
                                'conflicts': [{'reason': 'identity_mismatch', 'blocking': True}], 'skip': True})
            continue
        data = path.read_bytes()
        result, mapping, conflicts = convert(data, row)
        entry = {'path': str(path), 'relative_path': str(path.relative_to(output)), 'job_id': identity,
                 'mapping': mapping, 'conflicts': conflicts, 'old_hash': _hash(data), 'new_hash': _hash(result),
                 'ownership': {k: 'user' for k in ('title', 'division', 'project', 'attendees', 'status')}}
        entries.append(entry)
        by_job.setdefault(identity, []).append(entry)
    for group in by_job.values():
        if len(group) > 1:
            for entry in group:
                entry['conflicts'].append({'reason': 'duplicate_job', 'blocking': True})
    return {'output': str(output), 'backup_root': str(backup_root), 'key_map': KEY_MAP,
            'value_map': VALUE_MAP, 'entries': entries,
            'conflicts': [dict(path=e['path'], **c) for e in entries for c in e['conflicts']]}


def _write_manifest(path, manifest):
    temp = path.with_suffix('.part')
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with temp.open('rb') as stream:
        import os
        os.fsync(stream.fileno())
    temp.replace(path)
    sync_directory(path.parent)


@contextmanager
def _execution(root, held):
    """Migration and processing never overlap: take the execution lock, or run inside
    the serve executor thread that already holds it (held=True)."""
    if held:
        yield
        return
    with (root / 'tick.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise NoteConflict('engine_running: migrate from the QuietClerk screen, '
                               'or stop the service first') from exc
        yield


def migrate(con, root, output, *, apply=False, consent=False, execution_lock_held=False):
    root, output = Path(root).absolute(), Path(store.vault_identity(output))
    if not apply:
        return preview(con, root, output)
    if not consent:
        raise ValueError('explicit --consent is required')
    plan = preview(con, root, output)
    backup_root = Path(plan['backup_root'])
    backup_root.mkdir(parents=True, exist_ok=True)
    manifest_path = backup_root / ('migration-' + _hash(str(output).encode()) + '.json')
    with _execution(root, execution_lock_held):
        plan = preview(con, root, output)
        legacy_manifest = backup_root / 'migration.json'
        if not manifest_path.exists() and legacy_manifest.is_file():
            old = json.loads(legacy_manifest.read_text())
            if store.vault_identity(old['output']) == str(output):
                old['output'] = str(output)
                _write_manifest(manifest_path, old)
                legacy_manifest.unlink()
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            if manifest['output'] != str(output):
                raise NoteConflict('migration_output_changed')
        else:
            if any(c['blocking'] for c in plan['conflicts']):
                raise NoteConflict('migration_conflicts: ' + json.dumps(plan['conflicts'], ensure_ascii=False))
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            directory = backup_root / timestamp
            directory.mkdir()
            manifest = {**plan, 'backup_dir': str(directory), 'done': False}
            _write_manifest(manifest_path, manifest)
        jobs = []
        for entry in manifest['entries']:
            if entry.get('skip'):
                continue
            path = Path(entry['path'])
            if not safe_path(output, path):
                raise NoteConflict('migration_path_changed')
            data = path.read_bytes()
            if _hash(data) == entry['new_hash']:
                entry['state'] = 'done'
                jobs.append(entry['job_id'])
                _write_manifest(manifest_path, manifest)
                continue
            if _hash(data) != entry['old_hash']:
                raise NoteConflict('migration_note_changed')
            row = store.job(con, entry['job_id'])
            result, mapping, conflicts = convert(data, row)
            if mapping != entry['mapping'] or _hash(result) != entry['new_hash']:
                raise NoteConflict('migration_plan_changed')
            backup = Path(manifest['backup_dir']) / entry['relative_path']
            if not safe_path(backup_root, backup):
                raise NoteConflict('migration_backup_path_changed')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                durable_write(backup, data)
            elif _hash(backup.read_bytes()) != entry['old_hash']:
                raise NoteConflict('migration_backup_changed')
            sync_directory(backup.parent)
            entry['state'] = 'backed_up'
            _write_manifest(manifest_path, manifest)
            temp = path.with_name('.' + path.name + '.migration-part')
            if temp.exists():
                if temp.is_symlink():
                    raise NoteConflict('migration_path_changed')
                temp.unlink()
            durable_write(temp, result)
            if path.read_bytes() != data:
                temp.unlink()
                raise NoteConflict('migration_note_changed')
            temp.replace(path)
            sync_directory(path.parent)
            entry['state'] = 'done'
            jobs.append(entry['job_id'])
            _write_manifest(manifest_path, manifest)
        # A new legacy note appearing during an interrupted migration still needs consent.
        remaining = preview(con, root, output)
        if any(not e.get('skip') for e in remaining['entries']) or any(c['blocking'] for c in remaining['conflicts']):
            raise NoteConflict('migration_new_candidates')
        render.ensure_base(output)
        store.record_vault_migration(con, jobs, output)
        store.requeue_resolved_blocks(con, {'vault_migration'})
        manifest['done'] = True
        _write_manifest(manifest_path, manifest)
        return manifest
