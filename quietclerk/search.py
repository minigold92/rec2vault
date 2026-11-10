"""Artifact-backed literal substring search (contract 10.8 C).

Whitespace is significant: '대출 연장' does not match '대출연장'. Search never
interprets FTS operators. Two-character queries use escaped LIKE instead.
"""
import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from pathlib import Path

from . import artifacts, store, store_ops
from .transcript import artifact_rows


def ensure_schema(con):
    # `compact` is the text without whitespace: Korean ASR and people space words
    # differently ("대출 연장" / "대출연장"), so matching ignores spacing.
    columns = [row[1] for row in con.execute("SELECT * FROM pragma_table_info('search')")]
    if columns and 'compact' not in columns:
        con.execute('DROP TABLE search')  # derived data; bootstrap() rebuilds it
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(job_id UNINDEXED, kind UNINDEXED, line_id UNINDEXED, start UNINDEXED, speaker UNINDEXED, text UNINDEXED, compact, tokenize='trigram')")


def _compact(text):
    return re.sub(r'\s+', '', text or '')


def _artifact(directory, name):
    def regular(path, limit):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError('invalid artifact')
            return stream.read()
    data = regular(directory / name, 16 << 20)
    meta = json.loads(regular(artifacts.metadata(directory / name), 1 << 20))
    if meta.get('ok') is not True or meta.get('output_sha256') != hashlib.sha256(data).hexdigest():
        raise ValueError('invalid artifact metadata')
    return json.loads(data)


def meeting(con, job_id, root):
    """Read the current published run, applying only matching user corrections."""
    from .notes import safe_path
    row = store.job(con, job_id)
    if store_ops.deleted(con, job_id) or not row['current_run_id'] or row['legacy']:
        raise KeyError(job_id)
    root = Path(root)
    directory = root / 'work' / job_id / 'runs' / row['current_run_id']
    if (root / 'work').is_symlink() or not safe_path(root / 'work', directory):
        raise ValueError('unsafe artifact path')
    run = con.execute('SELECT job_id FROM runs WHERE run_id=?', (row['current_run_id'],)).fetchone()
    if run is None or run['job_id'] != job_id:
        raise ValueError('run does not belong to meeting')
    turns = artifact_rows(_artifact(directory, 'turns.json'), 'turns')
    texts = artifact_rows(_artifact(directory, 'corrected.json'), 'texts')
    meta = _artifact(directory, 'classification.json')['meta']
    summary = _artifact(directory, 'summary.json')['text']
    if len(turns) != len(texts) or not isinstance(meta, dict) or not isinstance(summary, str):
        raise ValueError('invalid meeting artifacts')
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    edits = {r['line_id']: r for r in con.execute('SELECT * FROM transcript_edits WHERE job_id=?', (job_id,))} if 'transcript_edits' in tables else {}
    overrides = {r['label']: r for r in con.execute('SELECT * FROM speaker_overrides WHERE job_id=?', (job_id,))} if 'speaker_overrides' in tables else {}

    def effective_label(label):
        visited = set()
        while label in overrides and overrides[label]['merged_into'] and label not in visited:
            visited.add(label)
            label = overrides[label]['merged_into']
        return label

    lines = []
    for index, (turn, original) in enumerate(zip(turns, texts), 1):
        if not isinstance(original, str) or not isinstance(turn, dict):
            raise ValueError('invalid transcript')
        start, end = turn['start'], turn['end']
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in (start, end)) or not 0 <= start <= end < 1e7:
            raise ValueError('invalid transcript times')
        ident, label = f't{index}', effective_label(turn.get('speaker'))
        override = overrides.get(label)
        name = override['name'] if override and override['confirmed'] and override['name'] else None
        edit = edits.get(ident)
        text = edit['text'] if edit and edit['original_sha256'] == hashlib.sha256(original.encode()).hexdigest() else original
        lines.append({'id': ident, 'start': start, 'end': end, 'speaker': label, 'name': name, 'text': text})
    replacements = {}
    for label in overrides:
        override = overrides.get(effective_label(label))
        if override and override['confirmed'] and override['name']:
            replacements[label] = override['name']
    if replacements:
        # Korean particles follow labels directly ("S2는"); only ASCII letters/digits extend a label.
        from .render import PARTICLE, particle_for
        pattern = (r'(?<!\w)(' + '|'.join(re.escape(label) for label in sorted(replacements, key=len, reverse=True))
                   + r')(?![A-Za-z0-9_])' + PARTICLE)
        summary = re.sub(pattern, lambda m: replacements[m[1]] + particle_for(replacements[m[1]], m[2]), summary)
    return {'job_id': job_id, 'title': meta.get('title') or Path(row['source_name']).stem,
            'date': row['recorded_at'], 'summary': summary, 'lines': lines, 'properties': meta}


def reindex(con, job_id, root):
    """Atomically replace one meeting's index; safe to call inside a transaction."""
    ensure_schema(con)
    standalone = not con.in_transaction
    if standalone:
        con.execute('BEGIN IMMEDIATE')
    con.execute('SAVEPOINT search_reindex')
    try:
        try:
            data = meeting(con, job_id, root)
        except KeyError:
            data = None
        con.execute('DELETE FROM search WHERE job_id=?', (job_id,))
        if data:
            rows = [(job_id, 'title', None, None, None, data['title']),
                    (job_id, 'summary', None, None, None, data['summary'])]
            rows += [(job_id, 'line', line['id'], line['start'], line['name'] or line['speaker'], line['text']) for line in data['lines']]
            con.executemany('INSERT INTO search(job_id,kind,line_id,start,speaker,text,compact) VALUES(?,?,?,?,?,?,?)',
                            [(*row, _compact(row[-1])) for row in rows])
        con.execute('RELEASE search_reindex')
        if standalone:
            con.commit()
    except BaseException:
        con.execute('ROLLBACK TO search_reindex')
        con.execute('RELEASE search_reindex')
        if standalone:
            con.rollback()
        raise


def bootstrap(con, root):
    """Backfill an empty index on startup; damaged artifacts are not indexed."""
    ensure_schema(con)
    if con.execute('SELECT 1 FROM search LIMIT 1').fetchone():
        return
    for row in con.execute("SELECT job_id FROM jobs WHERE status='done'").fetchall():
        try:
            reindex(con, row['job_id'], root)
        except (OSError, ValueError, KeyError, TypeError):
            continue


def query(con, q, limit=20, offset=0):
    if not isinstance(q, str):
        raise ValueError('q must be text')
    q = q.strip()
    if not 2 <= len(q) <= 100 or any(unicodedata.category(c).startswith('C') for c in q):
        raise ValueError('q must contain 2..100 characters without controls')
    limit, offset = int(limit), int(offset)
    if not 1 <= limit <= 200 or not 0 <= offset <= 2147483647:
        raise ValueError('invalid pagination')
    ensure_schema(con)
    compact = _compact(q)
    if len(compact) < 2:
        raise ValueError('q must contain 2..100 characters without controls')
    clause = 'search MATCH ?' if len(compact) >= 3 else "search.compact LIKE ? ESCAPE '\\'"
    term = ('compact : "' + compact.replace('"', '""') + '"' if len(compact) >= 3 else
            '%' + compact.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    sql = f'''FROM search JOIN jobs j ON j.job_id=search.job_id
              WHERE {clause} AND j.current_run_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM tombstones t WHERE t.sha256=j.sha256)'''
    total = con.execute('SELECT COUNT(*) ' + sql, (term,)).fetchone()[0]
    rows = con.execute('SELECT search.*,j.recorded_at, (SELECT text FROM search s WHERE s.job_id=j.job_id AND s.kind=\'title\' LIMIT 1) title ' + sql + ' ORDER BY j.recorded_at DESC,search.job_id,search.rowid LIMIT ? OFFSET ?', (term, limit, offset))
    items = []
    for row in rows:
        text = row['text']
        loose = r'\s*'.join(re.escape(c) for c in compact)
        matches = list(re.finditer(loose, text, re.IGNORECASE))
        snippet, pos = [], max(0, matches[0].start() - 70) if matches else 0
        stop = min(len(text), (matches[0].end() + 130) if matches else 200)
        for match in matches:
            if match.start() >= stop:
                break
            if match.start() > pos:
                snippet.append({'text': text[pos:match.start()], 'hit': False})
            snippet.append({'text': match.group(), 'hit': True})
            pos = match.end()
        if pos < stop:
            snippet.append({'text': text[pos:stop], 'hit': False})
        items.append({'job_id': row['job_id'], 'title': row['title'], 'date': row['recorded_at'], 'kind': row['kind'], 'line_id': row['line_id'], 'start': float(row['start']) if row['start'] is not None else None, 'speaker': row['speaker'], 'snippet': snippet})
    return {'items': items, 'total': total}
