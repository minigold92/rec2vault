"""V2 note invariants: strict identity, sticky ownership, byte-preserved user body.

Malformed/duplicate frontmatter or markers and ambiguous/unsafe paths never write.
The publication journal and durable payload allow recovery without model calls.
"""
import hashlib
import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path

import yaml

from .. import render, store


class NoteConflict(ValueError):
    def __init__(self, reason='note_conflict'):
        super().__init__(reason)


class Loader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise NoteConflict()
        return super().compose_node(parent, index)

Loader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in values if tag != 'tag:yaml.org,2002:timestamp']
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise NoteConflict()
        result[key] = loader.construct_object(value_node)
    return result


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def parse_note(data):
    match = re.match(rb'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', data, re.S)
    if not match:
        raise NoteConflict()
    try:
        props = yaml.load(match[1].decode('utf-8'), Loader=Loader)
        # Reject cyclic YAML aliases and non-JSON values; they cannot be owned safely.
        json.dumps(props, ensure_ascii=False, allow_nan=False)
    except (yaml.YAMLError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise NoteConflict() from exc
    if not isinstance(props, dict):
        raise NoteConflict()
    return props, data[match.end():]


def dump_frontmatter(props):
    return '---\n' + yaml.safe_dump(props, allow_unicode=True, sort_keys=False, default_flow_style=False) + '---\n'


def safe_path(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    try:
        path.resolve().relative_to(root.resolve())
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    # Only components inside root may not be links; root's own ancestors (e.g. macOS /tmp) may be.
    return not any(root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1))


def safe_notes(root):
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(p for p in root.rglob('*.md') if '.quietclerk-tmp' not in p.relative_to(root).parts
                  and safe_path(root, p) and p.is_file())


def find_existing(output, job):
    matches = []
    for path in safe_notes(Path(output)):
        try:
            props, _ = parse_note(path.read_bytes())
        except ValueError:
            continue
        if (type(props.get('qc_schema')) is int and props['qc_schema'] == 2
                and props.get('job_id') == job['job_id'] and props.get('source_sha256') == job['sha256']):
            matches.append(path)
    if len(matches) > 1:
        raise NoteConflict()
    return matches[0] if matches else None


USER_FIELDS = {'project', 'attendees', 'status'}


def merge_fields(generated, current, records):
    """A changed engine value becomes user-owned until explicitly reset elsewhere."""
    merged = dict(current or {})
    changes = {}
    for field, value in generated.items():
        record = records.get(field)
        owner = record['owner'] if record else ('user' if field in USER_FIELDS or (
            current is not None and field in ('title', 'division')) else 'engine')
        if record and owner == 'engine' and current is not None:
            previous = json.loads(record['last_generated'])
            if field not in current or current[field] != previous:
                owner = 'user'
        if field == 'tags':
            tags = current.get('tags', []) if current else []
            if not isinstance(tags, list):
                raise NoteConflict()
            merged[field] = [t for t in tags if t != 'meeting-notes'] + ['meeting-notes']
            owner = 'engine'
        elif owner == 'engine' or current is None:
            merged[field] = value
        changes[field] = {'owner': owner, 'last_generated': json.dumps(value, ensure_ascii=False)}
    return merged, changes


def _task_key(text):
    """Same task sentence regardless of which transcript lines a re-summary cites."""
    return ' '.join(re.sub(r'\[\[#\^t\d+\\?\|[^\]]*\]\]|\[\?t\d+\]', ' ', text).split())


def record_span(body):
    """(start, end) byte offsets of the engine-owned record: from the single record heading
    line to the first notes heading after it. Anything else in the body is the user's."""
    lines, offset, record, end = body.split(b'\n'), 0, [], None
    record_lines = {h.encode() for h in render.RECORD_HEADINGS.values()}
    notes_lines = {h.encode() for h in render.NOTES_HEADINGS.values()}
    for line in lines:
        text = line.rstrip(b'\r')
        if text in record_lines:
            record.append(offset)
        elif record and end is None and text in notes_lines:
            end = offset
        offset += len(line) + 1
    if len(record) != 1 or end is None:
        raise NoteConflict()
    return record[0], end


def _record(header, generated, language):
    """Engine section; boundary headings inside model text are demoted so the span stays unique."""
    boundaries = {*render.RECORD_HEADINGS.values(), *render.NOTES_HEADINGS.values()}
    generated = '\n'.join('#' + line if line.strip() in boundaries else line for line in generated.split('\n'))
    return f'{render.RECORD_HEADINGS[language]}\n\n{header}\n\n{generated}\n\n'


def new_body(header, generated, task_texts, language='ko'):
    # Short note-local block IDs: Obsidian shows them in Live Preview, so a UUID is noise.
    tasks = [{'task_id': f'task-{i}', 'text': text} for i, text in enumerate(task_texts, 1)]
    task_lines = '\n'.join(f'- [ ] {t["text"]} ^{t["task_id"]}' for t in tasks)
    body = (f'{render.TASK_HEADINGS[language]}\n{task_lines}\n\n'
            f'{_record(header, generated, language)}{render.NOTES_HEADINGS[language]}\n')
    return body.encode('utf-8'), tasks


def merge_body(current, header, generated, tasks, language):
    start, end = record_span(current)
    if tasks:
        generated += '\n\n## ' + ('Newly proposed tasks' if language == 'en' else '새로 제안된 할 일')
        generated += '\n' + '\n'.join('- [ ] ' + task for task in tasks)
    return current[:start] + _record(header, generated, language).encode() + current[end:]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def durable_write(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _payload_path(publication):
    return Path(publication['temp_path'] + '.json')


def publish(ctx, props, generated, tasks, language):
    output = Path(ctx.settings['output']).absolute()
    existing = find_existing(output, ctx.job)
    current, body, old = None, None, None
    if existing:
        old = existing.read_bytes()
        current, body = parse_note(old)
        try:
            record_span(body)
        except NoteConflict:
            if store.note_was_migrated(ctx.con, ctx.job['job_id'], output):
                raise NoteConflict('note_update_blocked')
            raise
    records = store.note_field_records(ctx.con, ctx.job['job_id'])
    merged, fields = merge_fields(props, current, records)
    header = render.header(merged, language)
    if body is None:
        body, new_tasks = new_body(header, generated, tasks, language)
    else:
        # Only tasks the first summary did not already put in the user's list are "new";
        # a plain re-render must not re-propose the same sentences.
        known = {_task_key(row['text']) for row in ctx.con.execute('SELECT text FROM note_tasks WHERE job_id=?', (ctx.job['job_id'],))}
        body, new_tasks = merge_body(body, header, generated, [t for t in tasks if _task_key(t) not in known], language), []
    target = existing or output / render.note_name(datetime.strptime(ctx.job['recorded_at'], '%Y%m%d-%H%M%S'),
                                                  merged.get('title'), 'Recording')
    if not safe_path(output, target) or (not existing and target.exists()):
        raise NoteConflict()
    content = dump_frontmatter(merged).encode() + body
    ctx.checkpoint()
    temp_dir = output / '.quietclerk-tmp'
    if not safe_path(output, temp_dir):
        raise NoteConflict()
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp = temp_dir / (ctx.run_id + '.md')
    pending = {'fields': fields, 'tasks': new_tasks, 'review_reasons': merged.get('review_reasons', []),
               'output': str(output), 'previous_b64': base64.b64encode(old).decode('ascii') if old is not None else None}
    try:
        durable_write(temp, content)
        durable_write(Path(str(temp) + '.json'), json.dumps(pending, ensure_ascii=False).encode())
        sync_directory(temp_dir)
        previous_hash = hashlib.sha256(old).hexdigest() if old is not None else None
        ctx.record(store.prepare_publication, target, previous_hash, hashlib.sha256(content).hexdigest(), temp)
        ctx.checkpoint()
        if not safe_path(output, target) or digest(target) != previous_hash:
            ctx.record(store.publication_conflict)
            raise NoteConflict()
        temp.replace(target)
        sync_directory(target.parent)
        ctx.record(store.rename_publication)
        ctx.record(store.commit_publication, pending)
    except Exception:
        publication = ctx.con.execute('SELECT * FROM publications WHERE run_id=?', (ctx.run_id,)).fetchone()
        if publication is not None and publication['state'] == 'prepared':
            recover_publication(ctx.con, publication)
        elif publication is None or publication['state'] == 'conflict':
            temp.unlink(missing_ok=True)
            Path(str(temp) + '.json').unlink(missing_ok=True)
        raise
    Path(str(temp) + '.json').unlink(missing_ok=True)
    try:
        temp_dir.rmdir()  # leave no empty engine folder in the synced vault
    except OSError:
        pass  # another run's pending publication still lives there
    return target, merged.get('review_reasons', [])


def recover_publication(con, publication):
    """store.recover hook. No provider calls; hash mismatch is never overwritten."""
    target, temp = Path(publication['target_path']), Path(publication['temp_path'])
    pending_path = _payload_path(publication)
    try:
        pending = json.loads(pending_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        store.recover_publication_conflict(con, publication['run_id'])
        return
    output = Path(pending['output'])
    if not safe_path(output, target) or not safe_path(output, temp) or not safe_path(output, pending_path):
        store.recover_publication_conflict(con, publication['run_id'])
        return
    if publication['state'] == 'prepared':
        # A kill between rename and the renamed commit still rolls back prepared.
        if not temp.exists() and digest(target) == publication['new_hash']:
            if pending['previous_b64'] is None:
                target.unlink()
            else:
                durable_write(temp, base64.b64decode(pending['previous_b64'], validate=True))
                temp.replace(target)
            sync_directory(target.parent)
        temp.unlink(missing_ok=True)
        pending_path.unlink(missing_ok=True)
        store.discard_prepared_publication(con, publication['run_id'])
    elif publication['state'] == 'renamed':
        if digest(target) != publication['new_hash']:
            store.recover_publication_conflict(con, publication['run_id'])
            return
        store.finish_recovered_publication(con, publication['run_id'], pending)
        pending_path.unlink(missing_ok=True)
