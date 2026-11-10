"""Read-only agent views, derived from the same published artifacts as exports.

Never read a partial run or a vault file. User-confirmed names and matching edits
come from search.meeting; deleted jobs are absent, damaged artifacts fail closed.
No provider calls, stored questions, or write commands are involved.
"""
import re
from datetime import date
from pathlib import Path

from . import search, store


def since_day(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('since must be YYYY-MM-DD')
    return date.fromisoformat(value).strftime('%Y%m%d')


def listing(con, root, *, since=None, limit=50):
    since = since_day(since)
    limit = int(limit)
    if not 1 <= limit <= 200:
        raise ValueError('limit must be 1..200')
    rows = con.execute('''SELECT j.* FROM jobs j WHERE (? IS NULL OR substr(recorded_at,1,8)>=?)
        AND NOT EXISTS (SELECT 1 FROM tombstones t WHERE t.sha256=j.sha256)
        ORDER BY recorded_at DESC,job_id LIMIT ?''', (since, since, limit))
    items = []
    for row in rows:
        title, kind = Path(row['source_name']).stem, None
        if row['current_run_id'] and not row['legacy']:
            try:
                meeting = search.meeting(con, row['job_id'], root)
                title, kind = meeting['title'], meeting['properties'].get('type')
            except (OSError, ValueError, KeyError, TypeError):
                # A job is still useful in a list even when its published output is missing.
                pass
        items.append({'job_id': row['job_id'], 'date': row['recorded_at'], 'title': title,
                      'type': kind, 'duration_sec': row['duration_sec'], 'status': row['status']})
    return {'items': items}


def show(con, root, job_id, *, include_transcript=True):
    if not isinstance(job_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', job_id):
        raise ValueError('invalid job_id')
    data = search.meeting(con, job_id, root)
    row = store.job(con, job_id)
    speakers = {line['speaker']: {'name': line['name']} for line in data['lines'] if line['speaker']}
    # Summary artifacts carry tasks in Markdown; retain their citations verbatim.
    tasks = []
    in_tasks = False
    for line in data['summary'].splitlines():
        if line.startswith('## '):
            in_tasks = line[3:].strip() in ('할 일', '합의·할 일', 'Tasks')
        elif in_tasks and line.lstrip().startswith(('-', '*')):
            tasks.append(line)
    result = {'job_id': job_id, 'date': data['date'], 'title': data['title'],
              'properties': data['properties'] | {'speakers': speakers, 'duration_sec': row['duration_sec'], 'status': row['status']},
              'summary': data['summary'], 'tasks': tasks}
    if include_transcript:
        result['transcript'] = [{**line, 'speaker': line['name'] or line['speaker']} for line in data['lines']]
    return result
