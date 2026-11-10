"""Local integrations invoked only after a note's journal commit succeeds.

Both are best effort: a failure is logged and never undoes or blocks the published note.
"""
import logging
from pathlib import Path

log = logging.getLogger('rec')


def _root(con):
    for row in con.execute('PRAGMA database_list'):
        if row[1] == 'main' and row[2]:
            return Path(row[2]).parent
    return None


def after_publish(con, job_id):
    from . import daily, search
    root = _root(con)
    if root is None:
        return
    try:
        search.reindex(con, job_id, root)
    except Exception as exc:  # noqa: BLE001 - search is rebuilt on the next publish or start
        log.warning('search reindex failed for %s: %s', job_id, exc)
    try:
        row = con.execute('SELECT recorded_at, note_path, current_run_id FROM jobs WHERE job_id=?', (job_id,)).fetchone()
        run = con.execute('SELECT settings_json FROM runs WHERE run_id=?', (row['current_run_id'],)).fetchone() if row else None
        if not row or not row['note_path'] or not run:
            return
        import json
        settings = json.loads(run['settings_json'])
        title = Path(row['note_path']).stem
        try:
            from .notes import parse_note
            props, _ = parse_note(Path(row['note_path']).read_bytes())
            title = props.get('title') or title
        except (OSError, ValueError):
            pass
        daily.link(settings, row['note_path'], title, row['recorded_at'])
    except Exception as exc:  # noqa: BLE001 - the note is already published
        log.warning('daily note link failed for %s: %s', job_id, exc)
