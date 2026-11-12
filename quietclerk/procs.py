"""Bounded POSIX child processes. A timeout always reaps the whole process group."""
import os
import signal
import subprocess
import sys
import time

TimeoutExpired = subprocess.TimeoutExpired


class StageTimeout(subprocess.TimeoutExpired):
    def __init__(self, command, timeout, stage, output=None, stderr=None):
        super().__init__(command, timeout, output=output, stderr=stderr)
        self.stage = stage

    def __str__(self):
        return f'timeout:{self.stage}'


def timeout_for(stage, duration=0):
    return {'convert': max(300, .2 * duration), 'diarize': max(600, .5 * duration),
            'detect_language': 300, 'transcribe': max(1200, 1.5 * duration),
            'second_pass': max(1200, 1.5 * duration)}.get(stage, 900)


def _signal(group, sig):
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        pass


def terminate(process, grace=10):
    _signal(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(min(.05, max(0, deadline - time.monotonic())))
    _signal(process.pid, signal.SIGKILL)
    process.communicate()


def run(args, *, timeout=900, stage='external', grace=10, input=None, capture_output=False,
        text=False, check=False, cwd=None, env=None, **kwargs):
    if args and args[0] in ('ffmpeg', 'ffprobe'):
        executable = os.environ.get('QC_' + args[0].upper())
        if executable:
            if not os.path.isabs(executable):
                raise ValueError('QC media tool paths must be absolute')
            args = [executable, *args[1:]]
    if input is not None:
        kwargs['stdin'] = subprocess.PIPE
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # The UI server is Interactive; heavy pipeline work keeps Darwin background
    # scheduling/I/O policy. taskpolicy execs in place, preserving group cleanup.
    command = ['/usr/sbin/taskpolicy', '-b', *args] if sys.platform == 'darwin' else args
    process = subprocess.Popen(command, cwd=cwd, env=env, text=text, start_new_session=True, **kwargs)
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate(process, grace)
        raise StageTimeout(args, timeout, stage, exc.output, exc.stderr) from exc
    except BaseException:
        terminate(process, grace)
        raise
    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
