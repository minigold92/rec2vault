#!/usr/bin/env python3
"""One preparation path for local Tauri builds and both macOS CI jobs.

Downloads are immutable, hash checked before extraction. FFmpeg is a minimal
LGPL static build; its complete license and reproducible inputs ship in Resources.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
TARGET = APP / 'src-tauri'
TRIPLE = 'aarch64-apple-darwin'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def download(spec):
    with urllib.request.urlopen(spec['url'], timeout=120) as response:
        data = response.read()
    if digest(data) != spec['sha256']:
        raise RuntimeError('download checksum mismatch: ' + spec['url'])
    return data


def bootstrap_lock(lock):
    bootstrap = re.search(r'(?mi)^pyyaml==[^\n]*(?:\n[ \t]+[^\n]*)*', lock)
    if bootstrap is None:
        raise RuntimeError('engine lock must include PyYAML for installer database initialization')
    return bootstrap.group() + '\n'


def prepare():
    inputs = json.loads((APP / 'build-inputs.json').read_text())
    cache = APP / '.build-cache'
    binaries = TARGET / 'binaries'
    resources = TARGET / 'engine'
    for directory in (cache, binaries, resources):
        directory.mkdir(parents=True, exist_ok=True)
    uv = binaries / ('uv-' + TRIPLE)
    uv_key = cache / ('uv-' + inputs['uv']['sha256'])
    if not uv_key.is_file():
        with tarfile.open(fileobj=io.BytesIO(download(inputs['uv'])), mode='r:gz') as archive:
            uv_key.write_bytes(archive.extractfile('uv-aarch64-apple-darwin/uv').read())
        uv_key.chmod(0o755)
    shutil.copy2(uv_key, uv)
    ff = inputs['ffmpeg']
    if any('gpl' in arg or 'nonfree' in arg for arg in ff['configure']):
        raise RuntimeError('only LGPL FFmpeg is permitted')
    key = digest(json.dumps(ff, sort_keys=True).encode())
    ff_cache = cache / ('ffmpeg-' + key)
    if not (ff_cache / 'ffprobe').is_file():
        with tempfile.TemporaryDirectory(prefix='quietclerk-ffmpeg-') as temporary:
            source = Path(temporary)
            with tarfile.open(fileobj=io.BytesIO(download(ff)), mode='r:xz') as archive:
                archive.extractall(source, filter='data')
            source = source / ('ffmpeg-' + ff['version'])
            subprocess.run(['./configure', *ff['configure']], cwd=source, check=True)
            subprocess.run(['make', '-j', str(min(os.cpu_count() or 2, 8)), 'ffmpeg', 'ffprobe'], cwd=source, check=True)
            ff_cache.mkdir(exist_ok=True)
            for name in ('ffmpeg', 'ffprobe', 'COPYING.LGPLv2.1'):
                shutil.copy2(source / name, ff_cache / name)
    for name in ('ffmpeg', 'ffprobe'):
        shutil.copy2(ff_cache / name, binaries / (name + '-' + TRIPLE))
    shutil.copy2(ff_cache / 'COPYING.LGPLv2.1', resources / 'COPYING.LGPLv2.1')
    shutil.copy2(APP / 'build-inputs.json', resources / 'build-inputs.json')
    shutil.copy2(APP / 'engine-requirements.txt', resources / 'requirements.txt')
    (resources / 'bootstrap-requirements.txt').write_text(bootstrap_lock((APP / 'engine-requirements.txt').read_text()))
    with tempfile.TemporaryDirectory(prefix='quietclerk-wheel-') as temporary:
        subprocess.run([str(uv), 'build', '--wheel', '--build-constraint', str(APP / 'build-requirements.txt'),
                        '--out-dir', temporary, str(ROOT)], check=True)
        wheels = list(Path(temporary).glob('*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('expected one engine wheel')
        for old in resources.glob('*.whl'):
            old.unlink()
        shutil.copy2(wheels[0], resources / wheels[0].name)
    wheel = resources / wheels[0].name
    manifest = {'schema': 1, 'version': tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version'],
                'wheel': wheel.name, 'wheel_sha256': digest(wheel.read_bytes()),
                'requirements_sha256': digest((resources / 'requirements.txt').read_bytes()),
                'bootstrap_sha256': digest((resources / 'bootstrap-requirements.txt').read_bytes()),
                'inputs_sha256': digest((resources / 'build-inputs.json').read_bytes())}
    (resources / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
    print('Prepared engine ' + manifest['version'] + ', dependency lock ' + manifest['requirements_sha256'])


if __name__ == '__main__':
    prepare()
