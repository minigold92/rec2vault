"""Turn building and LLM text adapters, parameters, and legacy provider bridge."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from .. import artifacts, config, overrides, providers as llm, postprocess, procs, render, store
from ..executor import Blocked, Excluded, Stage
from ..language import context_language
from ..transcript import artifact_rows as _artifact_rows, turns as build_turns


def _providers(ctx):
    consent = ctx.settings.get('providers.consent', {})
    return [p for p in ctx.settings.get('providers.order', []) if p in consent]


processing_language = context_language


def output_language(ctx):
    value = ctx.settings.get('notes.output_language', 'same')
    return processing_language(ctx) if value == 'same' else value


def _llm_params(ctx):
    return {'language': processing_language(ctx), 'providers': _providers(ctx),
            'local_only': ctx.settings.get('providers.local_only', False),
            'consent': ctx.settings.get('providers.consent', {}),
            'vocabulary_terms': ctx.settings.get('vocabulary.terms', []),
            'models': {'codex.effort': ctx.settings.get('providers.codex.effort', 'low'),
                       'codex.speed': ctx.settings.get('providers.codex.speed', 'standard'),
                       'ollama.model': ctx.settings.get('providers.ollama.model', '')}}


@contextmanager
def _legacy_llm(ctx):
    """Bind immutable run settings without mutating module-global providers."""
    from ..providers import use_context
    with use_context(ctx):
        yield


def _turns(ctx, out):
    artifacts.write_json(out, build_turns(_artifact_rows(ctx.load('transcribe')),
                                          _artifact_rows(ctx.load('diarize'), 'segments')))


def _correct(ctx, out):
    with _legacy_llm(ctx):
        texts, notes = postprocess.correct(ctx.load('turns'), _artifact_rows(ctx.load('second_pass')), processing_language(ctx))
    artifacts.write_json(out, {'texts': texts, 'notes': notes, 'turns_sha256': artifacts.sha256(ctx.paths['turns'])})


def _classify(ctx, out):
    turns, texts, _, _ = overrides.stage_view(ctx)
    if config.memo_mode(ctx.settings, ctx.job['duration_sec']):
        artifacts.write_json(out, {'meta': postprocess.memo_metadata(turns, texts, output_language(ctx)),
                                   'engine': None})
        return 'not_run'
    with _legacy_llm(ctx):
        meta, engine = postprocess.classify(turns, texts,
                                            ctx.job['source_name'], render.known_projects(Path(ctx.settings['output'])),
                                            output_language(ctx))
    artifacts.write_json(out, {'meta': meta, 'engine': engine})


def _summarize(ctx, out):
    reasons = []
    meta = ctx.load('classify')['meta']
    turns, texts, _, _ = overrides.stage_view(ctx, meta)
    with _legacy_llm(ctx):
        text, engine = postprocess.summarize(turns, texts, meta, output_language(ctx),
                                             recorded_at=ctx.job['recorded_at'], review_reasons=reasons,
                                             settings=ctx.settings)
    artifacts.write_json(out, {'text': text, 'engine': engine, 'review_reasons': reasons})


def stages():
    return (
        Stage('turns', 'turns.json', ('transcribe', 'diarize'), lambda c: {'rule_version': 1, 'gap_sec': 1.5}, _turns),
        Stage('correct', 'corrected.json', ('turns', 'second_pass'), lambda c: {
            **_llm_params(c), 'prompt_version': postprocess.CORRECT_PROMPT_VERSION,
            'chunk_turns': config.CORRECT_CHUNK_TURNS}, _correct),
        Stage('classify', 'classification.json', ('correct', 'source_name'), lambda c: {
            **_llm_params(c), 'prompt_version': postprocess.CLASSIFY_PROMPT_VERSION, 'overrides': overrides.fingerprint(c),
            'projects_hash': artifacts.value_hash(sorted(render.known_projects(Path(c.settings['output'])))),
            'output_language': output_language(c),
            'memo': config.memo_mode(c.settings, c.job['duration_sec'])}, _classify),
        Stage('summarize', 'summary.json', ('correct', 'classify'), lambda c: {
            **_llm_params(c), 'prompt_version': postprocess.SUMMARY_PROMPT_VERSION, 'overrides': overrides.fingerprint(c),
            'template_version': postprocess.SUMMARY_TEMPLATE_VERSION, 'output_language': output_language(c),
            'recorded_at': c.job['recorded_at'],
            'summary.sections': c.settings.get('summary.sections', {}),
            'summary.instructions': c.settings.get('summary.instructions', '')}, _summarize),
    )
