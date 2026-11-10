"""Validate only self-contained MP4/M4A, before any demuxer can open a reference.

The atom walk reads headers, not media payloads. Unknown atoms remain opaque;
only the standard container path to data references is descended into.
"""
import json
import math
import struct

from . import procs


class Rejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


_CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'dinf'}


def _atoms(stream, start, end):
    position = start
    while position < end:
        if end - position < 8:
            raise Rejected('decode')
        stream.seek(position)
        size, kind = struct.unpack('>I4s', stream.read(8))
        header = 8
        if size == 1:
            raw = stream.read(8)
            if len(raw) != 8:
                raise Rejected('decode')
            size = struct.unpack('>Q', raw)[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or size > end - position:
            raise Rejected('decode')
        yield kind, position + header, position + size
        position += size


def _references(stream, start, end, depth=0):
    if depth > 8:
        raise Rejected('format')
    for kind, body, stop in _atoms(stream, start, end):
        if kind in _CONTAINERS:
            _references(stream, body, stop, depth + 1)
        elif kind in (b'cmov', b'rmra'):
            # Compressed headers and reference movies can hide reference tables.
            raise Rejected('format')
        elif kind == b'dref':
            if stop - body < 8:
                raise Rejected('decode')
            stream.seek(body)
            version_flags, count = struct.unpack('>II', stream.read(8))
            if version_flags != 0:
                raise Rejected('format')
            seen = 0
            for entry, payload, limit in _atoms(stream, body + 8, stop):
                seen += 1
                stream.seek(payload)
                # Only a self-contained URL reference with no URL is safe.
                if entry != b'url ' or limit - payload != 4 or stream.read(4) != b'\0\0\0\1':
                    raise Rejected('format')
            if seen != count:
                raise Rejected('decode')


def self_contained(path):
    with path.open('rb') as stream:
        header = stream.read(8)
        if len(header) < 8 or header[4:8] not in (b'ftyp', b'moov', b'mdat', b'free', b'wide', b'skip'):
            raise Rejected('format')
        stream.seek(0, 2)
        _references(stream, 0, stream.tell())


def duration(path):
    """Return a finite positive duration; reject references before running ffprobe."""
    self_contained(path)
    try:
        result = procs.run(
            ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov',
             '-enable_drefs', '0', '-use_absolute_path', '0', '-show_entries',
             'format=format_name,duration:stream=codec_type,codec_name', '-of', 'json', str(path)],
            timeout=30, stage='probe', capture_output=True, text=True)
    except procs.TimeoutExpired as exc:
        raise Rejected('decode') from exc
    if result.returncode:
        raise Rejected('decode')
    try:
        data = json.loads(result.stdout)
        if 'mov' not in data['format']['format_name'].split(','):
            raise Rejected('format')
        audio = [s for s in data['streams'] if s['codec_type'] == 'audio']
        if len(audio) != 1:
            raise Rejected('format')
        if audio[0].get('codec_name') != 'aac':
            raise Rejected('codec')
        value = float(data['format']['duration'])
        if not math.isfinite(value) or value <= 0:
            raise Rejected('decode')
        return value
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected('decode') from exc
