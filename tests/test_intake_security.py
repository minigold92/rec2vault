"""IN-12: real local HTTP receiver + monitored local bait, synthetic containers only."""
import builtins
import http.server
import os
import struct
import threading
from pathlib import Path

import pytest

from quietclerk import intake, probe, quarantine
from test_intake import env, tone, file_row, assert_clean


def atom(kind, payload):
    return struct.pack('>I4s', len(payload) + 8, kind) + payload


def external_reference(original, location, kind=b'url '):
    """Rebuild a generated, otherwise valid MP4 with a non-self-contained dref."""
    def rewrite(data):
        output = bytearray()
        position = 0
        while position < len(data):
            size, name = struct.unpack('>I4s', data[position:position + 8])
            payload = data[position + 8:position + size]
            if name in (b'moov', b'trak', b'mdia', b'minf', b'dinf'):
                payload = rewrite(payload)
            elif name == b'dref':
                payload = b'\0' * 4 + struct.pack('>I', 1) + atom(kind, b'\0' * 4 + location.encode() + b'\0')
            output.extend(atom(name, payload))
            position += size
        return bytes(output)
    return rewrite(original)


@pytest.mark.parametrize('container', ['hls', 'concat', 'mp4_http', 'mp4_file', 'mp4_urn'])
def test_in12_external_references_never_open_network_or_local_bait(env, monkeypatch, container):
    tmp, con, settings = env
    requests = []
    class Receiver(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'bait')
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        remote = f'http://127.0.0.1:{server.server_port}/bait.m4a'
        bait = tmp / 'local-bait.m4a'
        bait.write_bytes(b'private bait: this file must never be opened')
        path = tmp / 'INBOX' / 'attack.m4a'
        if container == 'hls':
            path.write_text(f'#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n{remote}\n{bait}\n#EXT-X-ENDLIST\n')
        elif container == 'concat':
            path.write_text(f"ffconcat version 1.0\nfile '{bait}'\nfile '{remote}'\n")
        else:
            tone(path)
            location = remote if container == 'mp4_http' else str(bait)
            path.write_bytes(external_reference(path.read_bytes(), location,
                                              b'urn ' if container == 'mp4_urn' else b'url '))
        os.utime(path, (1000, 1000))
        opened = []
        process_calls = []
        original_path_open, original_open, original_os_open = Path.open, builtins.open, os.open
        def monitored_path_open(target, *args, **kwargs):
            if target == bait:
                opened.append(str(target))
            return original_path_open(target, *args, **kwargs)
        def monitored_open(target, *args, **kwargs):
            if isinstance(target, (str, os.PathLike)) and Path(target) == bait:
                opened.append(str(target))
            return original_open(target, *args, **kwargs)
        def monitored_os_open(target, *args, **kwargs):
            if isinstance(target, (str, os.PathLike)) and Path(target) == bait:
                opened.append(str(target))
            return original_os_open(target, *args, **kwargs)
        def no_demuxer(*args, **kwargs):
            process_calls.append(args[0])
            pytest.fail('unsafe references reached a subprocess')
        monkeypatch.setattr(Path, 'open', monitored_path_open)
        monkeypatch.setattr(builtins, 'open', monitored_open)
        monkeypatch.setattr(os, 'open', monitored_os_open)
        monkeypatch.setattr(probe.procs, 'run', no_demuxer)
        assert intake.scan(con, now=1100, settings=settings) == []
        assert (file_row(con, path)['intake_status'], file_row(con, path)['reject_reason']) == ('rejected', 'format')
        assert file_row(con, path)['sha256'] is None
        assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] == 0
        assert opened == [] and process_calls == []
        assert_clean(tmp)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert requests == []


def test_link_swap_between_lstat_and_open_never_reads_target(env, monkeypatch):
    tmp, con, settings = env
    path = tone(tmp / 'INBOX' / 'swap.m4a')
    bait = tmp / 'bait'
    bait.write_bytes(b'private')
    original = quarantine.os.open
    def swap(name, flags, *args, **kwargs):
        if name == path.name:
            path.unlink()
            path.symlink_to(bait)
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(quarantine.os, 'open', swap)
    monkeypatch.setattr(quarantine.os, 'read', lambda *_: pytest.fail('symlink target read'))
    assert intake.scan(con, now=1100, settings=settings) == []
    assert file_row(con, path)['intake_status'] == 'waiting'
    assert_clean(tmp)
