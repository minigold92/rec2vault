"""Non-cacheable note merge and journaled vault publication."""
import json
from datetime import datetime
from pathlib import Path

from .. import artifacts, notes, providers, render, store, syncthing
from ..notes.migration import preview as legacy_preview
from ..executor import Blocked, Stage, StageFailure
from .text import output_language, processing_language


def _model_ids(value):
    """stage_runs.model holds a role -> 'repo@revision' JSON object; plain strings pass through."""
    try:
        parsed = json.loads(value)
    except ValueError:
        return [value]
    return list(parsed.values()) if isinstance(parsed, dict) else [value]


def _legacy_notes_present(ctx):
    """A vault with no v1 engine notes has nothing to back up or convert, so it is
    marked migrated without consent. Any candidate (even a blocked one) keeps the gate."""
    if legacy_preview(ctx.con, ctx.settings['root'], ctx.settings['output'])['entries']:
        return True
    store.record_vault_migration(ctx.con, [], ctx.settings['output'])
    return False


def _publish(ctx, out):
    turns, corrected = ctx.load('turns'), ctx.load('correct')
    classification, summary = ctx.load('classify'), ctx.load('summarize')
    records = store.provenance_rows(ctx.con, ctx.run_id)
    engines = {'transcribe': sorted({model for r in records if r['stage'] in ('transcribe', 'second_pass') and r['model']
                                     for model in _model_ids(r['model'])}),
               'postprocess': sorted({r['provider'] for r in records if r['provider']}),
               'external_text_to': providers.external_text_to(records)}
    language = ctx.load('language') if 'language' in ctx.paths else {}
    detected = ('uncertain' if language.get('status') == 'uncertain' else
                language.get('top') if language.get('status') == 'decided' else None)
    recorded = datetime.strptime(ctx.job['recorded_at'], '%Y%m%d-%H%M%S')
    props, generated, tasks = render.components(
        ctx.job, recorded, turns, corrected['texts'], classification['meta'], summary['text'], corrected['notes'],
        engines, datetime.now(), processing_language(ctx), detected, output_language(ctx))
    body, _ = notes.new_body(render.header(props, output_language(ctx)), generated, tasks, output_language(ctx))
    draft = ctx.work / 'note.md'
    render.write_atomic(draft, render.frontmatter(props) + body.decode())
    result = {'note_artifact': str(draft), 'review_reasons': props['review_reasons']}
    if not store.vault_migrated(ctx.con, ctx.settings['output']) and _legacy_notes_present(ctx):
        # Waiting for the user's migration consent is not a failure: no attempt is used,
        # and finishing the migration requeues the job (contract 7.5). The draft stays in the run.
        raise Blocked('vault_migration')
    try:
        render.ensure_base(Path(ctx.settings['output']))
        target, reasons = notes.publish(ctx, props, generated, tasks, output_language(ctx))
    except notes.NoteConflict as exc:
        result['error'] = str(exc)
        artifacts.write_json(out, result)
        raise StageFailure(str(exc), artifact=True) from exc
    ctx.note_path, ctx.review_reasons = target, reasons
    # The macOS watcher can miss files written by a background service; without this the
    # note reached other devices only at Syncthing's next full scan (found 2026-11-10).
    syncthing.rescan(Path(target).parent)
    artifacts.write_json(out, {**result, 'note_path': str(target), 'review_reasons': reasons})


def stages():
    return (Stage('note', 'note.json', ('summarize',), lambda c: {}, _publish, cache=False),)
