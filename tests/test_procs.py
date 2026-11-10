import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quietclerk import procs


def test_capture_and_nonzero_check():
    result = procs.run([sys.executable, '-c', 'print(input().upper())'], input='hello',
                       capture_output=True, text=True, timeout=5)
    assert result.stdout == 'HELLO\n'
    with pytest.raises(subprocess.CalledProcessError):
        procs.run([sys.executable, '-c', 'raise SystemExit(4)'], check=True, timeout=5)


def alive(pid):
    # A reparented zombie is terminated, although kill(pid, 0) still finds it.
    status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return status.returncode == 0 and not status.stdout.strip().startswith('Z')


def test_timeout_terminates_child_and_sigterm_resistant_grandchild(tmp_path):
    pids = tmp_path / 'pids.json'
    grandchild = '''import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'''
    script = '''
import json,os,signal,subprocess,sys,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-c',sys.argv[2]])
with open(sys.argv[1],'w') as f: json.dump([os.getpid(),child.pid],f)
time.sleep(60)
'''
    try:
        with pytest.raises(procs.StageTimeout, match='timeout:transcribe'):
            procs.run([sys.executable, '-c', script, str(pids), grandchild], capture_output=True,
                      timeout=1, grace=.15, stage='transcribe')
        parent_pid, grandchild_pid = json.loads(pids.read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (alive(parent_pid) or alive(grandchild_pid)):
            time.sleep(.02)
        assert not alive(parent_pid)
        assert not alive(grandchild_pid)
    finally:
        if pids.exists():
            for pid in json.loads(pids.read_text()):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_grandchild_killed_even_if_parent_exits_on_term(tmp_path):
    pids = tmp_path / 'pids.json'
    script = '''
import json,os,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
with open(sys.argv[1],'w') as f: json.dump([os.getpid(),child.pid],f)
time.sleep(60)
'''
    with pytest.raises(procs.StageTimeout):
        procs.run([sys.executable, '-c', script, str(pids)], capture_output=True, timeout=1, grace=.15)
    parent_pid, child_pid = json.loads(pids.read_text())
    assert not alive(parent_pid)
    assert not alive(child_pid)


def test_contract_timeouts():
    assert procs.timeout_for('convert', 2100) == 420
    assert procs.timeout_for('diarize', 2100) == 1050
    assert procs.timeout_for('detect_language', 2100) == 300
    assert procs.timeout_for('transcribe', 2100) == 3150
    assert procs.timeout_for('second_pass', 2100) == 3150
    assert procs.timeout_for('correct', 2100) == 900
