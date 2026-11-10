"""Model stage parameters and subprocess error policy."""
import json
import subprocess
import sys

from .. import procs, store
from ..backends import InvalidOutput, ModelMissing
from ..backends.mlx import MLXBackend, STAGE_MODELS, QWEN_LANGUAGES
from ..executor import Stage, StageFailure, NoSpeech
from ..language import context_language, fixed_language, job_settings


def _identities(roles):
    try:
        return MLXBackend().model_ids(roles)
    except ModelMissing as exc:
        raise StageFailure(f'ModelMissing:{exc}', retryable=False) from exc


def _params(name, ctx):
    roles = STAGE_MODELS[name]
    params = {'backend': 'mlx', 'rule_version': 2,
              'models': {} if name == 'detect_language' and fixed_language(job_settings(ctx)) else
                        _identities(roles)}
    if name == 'detect_language':
        params.update({'language.mode': fixed_language(job_settings(ctx)) or 'auto',
                       'language.default': ctx.settings.get('language.default', 'ko'), 'sampling_rule': 1})
    elif name in ('transcribe', 'second_pass'):
        params['language'] = context_language(ctx)
        if name == 'transcribe':
            params.update({'chunk_max_sec': 60.0, 'chunk_rule_version': 2,
                           'alignment': {'language': QWEN_LANGUAGES[params['language']]}})
    return params


def _model(name):
    def execute(ctx, out):
        ctx.checkpoint()
        params = ctx.stage_params
        snapshot = ctx.work / 'run-settings.json'
        snapshot.write_text(json.dumps({**job_settings(ctx), 'model_ids': params['models']}), encoding='utf-8')
        command = [sys.executable, '-m', 'quietclerk.worker', '--run-settings', str(snapshot),
                   '--stage', name, '--in', str(ctx.paths['convert'])]
        if name == 'detect_language':
            command.extend(['--in', str(ctx.paths['diarize'])])
        elif name in ('transcribe', 'second_pass'):
            command.extend(['--in', str(ctx.paths['language'])])
        command.extend(['--out', str(out)])
        for attempt in range(2):
            try:
                completed = procs.run(command,
                    timeout=procs.timeout_for(ctx.current_stage, ctx.job['duration_sec'] or 0),
                    stage=ctx.current_stage, capture_output=True, text=True, check=True)
                event = json.loads(completed.stdout.splitlines()[-1])
                if event.get('type') != 'result':
                    raise InvalidOutput('missing result event')
                expected_models = params['models']
                if name == 'detect_language' and json.loads(out.read_text())['status'] in ('not_run', 'no_speech'):
                    expected_models = {}
                if event.get('models') != expected_models:
                    raise InvalidOutput('worker model revisions differ from cache parameters')
                ctx.record(store.annotate_stage, name, backend='mlx', model=json.dumps(event['models']))
                break
            except subprocess.CalledProcessError as exc:
                try:
                    error = json.loads(exc.stderr.splitlines()[-1])['error']
                except (ValueError, IndexError, KeyError):
                    error = 'InvalidOutput'
                if error == 'InvalidOutput' and attempt == 0:
                    continue
                raise StageFailure(error, retryable=False) from exc
            except (InvalidOutput, ValueError, IndexError, KeyError) as exc:
                if attempt == 0:
                    continue
                raise StageFailure('InvalidOutput', retryable=False) from exc
        if name == 'detect_language':
            result = json.loads(out.read_text())
            if result['status'] == 'no_speech':
                raise NoSpeech()
            if result['status'] == 'unsupported':
                raise StageFailure('unsupported_language', retryable=False, artifact=True)
            if result['status'] == 'uncertain':
                ctx.review_reasons.append('언어가 섞여 있어요')
            if result['status'] == 'not_run':
                return 'not_run'
    return execute


def stages():
    return (
        Stage('diarize', 'diarize.json', ('convert',), lambda c: _params('diarize', c), _model('diarize')),
        Stage('detect_language', 'language.json', ('convert', 'diarize'),
              lambda c: _params('detect_language', c), _model('detect_language')),
        Stage('transcribe', 'asr.json', ('convert', 'language'),
              lambda c: _params('transcribe', c), _model('transcribe')),
        Stage('second_pass', 'alt.json', ('convert', 'language'),
              lambda c: _params('second_pass', c), _model('second_pass')),
    )
