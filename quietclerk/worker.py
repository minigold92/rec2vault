"""One stage per process. stdout is JSONL only; settings are an immutable snapshot."""
import argparse
import contextlib
import json
import sys
import wave
from pathlib import Path

from .backends import BackendUnavailable, AudioDecodeError, ModelMissing, InvalidOutput, validate_output
from .backends.mlx import MLXBackend, STAGE_MODELS
from .language import detect, processing_language, fixed_language

ERRORS = (ModelMissing, BackendUnavailable, AudioDecodeError, InvalidOutput)


def run(stage, inputs, output, settings, backend):
    try:
        with wave.open(str(inputs[0]), 'rb') as audio:
            if (audio.getframerate() != 16000 or audio.getnchannels() != 1 or
                    audio.getsampwidth() != 2 or audio.getnframes() == 0):
                raise AudioDecodeError('expected nonempty 16kHz mono PCM s16 WAV')
            duration = audio.getnframes() / audio.getframerate()
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioDecodeError(str(exc)) from exc
    if stage != 'detect_language' or not fixed_language(settings):
        availability = backend.available()
        if not availability.available:
            raise BackendUnavailable(availability.reason)
    if stage == 'diarize':
        result = validate_output(backend.diarize(inputs[0]), duration)
    elif stage == 'detect_language':
        segments = validate_output(json.loads(inputs[1].read_text()), duration)
        result = detect(backend, inputs[0], segments, duration, settings)
    else:
        detection = json.loads(inputs[1].read_text())
        lang = processing_language(settings, detection)
        result = validate_output(getattr(backend, stage)(inputs[0], lang), duration, words=True)
    temporary = Path(str(output) + '.part')
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(output)
    return result


def main(argv=None, *, backend_factory=MLXBackend):
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-settings', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=('diarize', 'detect_language', 'transcribe', 'second_pass'))
    parser.add_argument('--in', dest='inputs', action='append', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        settings = json.loads(args.run_settings.read_text(encoding='utf-8'))
        if not isinstance(settings, dict):
            raise InvalidOutput('run settings must be an object')
        if len(args.inputs) != (1 if args.stage == 'diarize' else 2):
            raise InvalidOutput('wrong number of stage inputs')
        print(json.dumps({'type': 'progress', 'stage': args.stage}), flush=True)
        with contextlib.redirect_stdout(sys.stderr):
            backend = backend_factory(settings)
            result = run(args.stage, args.inputs, args.out, settings, backend)
            roles = STAGE_MODELS[args.stage]
            if args.stage == 'detect_language' and result['status'] in ('not_run', 'no_speech'):
                roles = ()
            models = backend.model_ids(roles)
        print(json.dumps({'type': 'result', 'models': models, 'output': str(args.out)}), flush=True)
        return 0
    except ERRORS as exc:
        print(json.dumps({'error': type(exc).__name__, 'detail': str(exc)}), file=sys.stderr, flush=True)
        return 1
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(json.dumps({'error': 'InvalidOutput', 'detail': str(exc)}), file=sys.stderr, flush=True)
        return 1
    except ImportError as exc:
        print(json.dumps({'error': 'BackendUnavailable', 'detail': str(exc)}), file=sys.stderr, flush=True)
        return 1
    except Exception as exc:
        print(json.dumps({'error': 'InvalidOutput', 'detail': str(exc)}), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
