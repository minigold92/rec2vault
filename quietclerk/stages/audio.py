"""Restricted MP4/AAC conversion, with actual PCM duration validation."""
import errno
import math
import subprocess
import wave

from .. import config, procs
from ..executor import Stage, StageFailure


def _convert(ctx, out):
    ctx.checkpoint()
    try:
        procs.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                   '-protocol_whitelist', 'file', '-f', 'mov', '-enable_drefs', '0',
                   '-use_absolute_path', '0', '-i', ctx.job['archive_path'], '-map', '0:a:0',
                   '-t', str(config.MAX_DURATION_SEC + 1),
                   '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'wav', str(out)],
                  timeout=procs.timeout_for('convert', ctx.job['duration_sec'] or 0), stage='convert',
                  check=True, capture_output=True)
        with wave.open(str(out), 'rb') as decoded:
            duration = decoded.getnframes() / decoded.getframerate()
        expected = ctx.job['duration_sec']
        if (not expected or not math.isfinite(expected) or expected <= 0 or duration <= 0
                or duration > config.MAX_DURATION_SEC or abs(duration - expected) > expected * .1):
            raise StageFailure('audio_decode', retryable=False)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or b''
        if isinstance(stderr, str):
            stderr = stderr.encode()
        if b'No space left on device' in stderr:
            raise OSError(errno.ENOSPC, 'audio conversion ran out of space') from exc
        raise StageFailure('audio_decode', retryable=False) from exc
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise StageFailure('audio_decode', retryable=False) from exc


def stages():
    version = procs.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=30, stage='convert').stdout.splitlines()[0]
    return (
        Stage('convert', 'audio.wav', ('archive',), lambda c: {
            'format': '16000/mono/s16', 'ffmpeg': version, 'rule_version': 2}, _convert),
    )
