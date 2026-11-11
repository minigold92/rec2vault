"""Local setup observations and Syncthing REST adaptation; no silent fake state."""
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict
from contextlib import closing
from pathlib import Path

from .. import backfill, providers, store, syncthing


class Syncthing:
    def __init__(self, settings, api=None):
        self.settings, self.api = settings, api or syncthing._api

    def pairing(self):
        status = self.api('GET', 'system/status', {})
        pending = self.api('GET', 'cluster/pending/devices', {}) or {}
        return {'device_id': status['myID'], 'qr_data': status['myID'],
                'pending': [{'device_id': key, **value} for key, value in pending.items()]}

    def approve(self, device_id):
        if not isinstance(device_id, str) or not re.fullmatch(r'[A-Z2-7]{7}(?:-[A-Z2-7]{7}){7}', device_id):
            raise ValueError('invalid Syncthing device ID')
        devices = self.api('GET', 'config/devices', {})
        if any(device['deviceID'] == device_id for device in devices):
            return False
        pending = self.api('GET', 'cluster/pending/devices', {}) or {}
        if device_id not in pending:
            raise ValueError('device is not pending approval')
        self.api('PUT', 'config/devices/' + device_id, {},
                 {'deviceID': device_id, 'name': pending[device_id].get('name', ''), 'addresses': ['dynamic']})
        return True

    def folder(self):
        folders = self.api('GET', 'config/folders', {})
        inbox = Path(self.settings.get('inbox')).resolve()
        folder = next((item for item in folders if Path(item['path']).expanduser().resolve() == inbox), None)
        if folder is None:
            return {'state': 'not_shared', 'folder_id': None, 'phone_recordings': None,
                    'count_reason': 'remote_inventory_unavailable'}
        connections = self.api('GET', 'system/connections', {}).get('connections', {})
        peers = [item['deviceID'] for item in folder.get('devices', [])]
        local = self.api('GET', 'system/status', {})['myID']
        peers = [peer for peer in peers if peer != local]
        if not peers:
            state = 'not_shared'
        else:
            # Transport connectivity alone does not prove folder acceptance.
            # https://docs.syncthing.net/rest/db-completion-get.html
            accepted = any(
                connections.get(peer, {}).get('connected') and self.api(
                    'GET', 'db/completion', {'device': peer, 'folder': folder['id']}).get('remoteState') == 'valid'
                for peer in peers)
            state = 'connected' if accepted else 'awaiting_acceptance'
        return {'state': state, 'folder_id': folder['id'], 'phone_recordings': None,
                'count_reason': 'remote_inventory_unavailable'}

    def backlog(self):
        folder = self.folder()
        if not folder['folder_id']:
            return []
        needed = self.api('GET', 'db/need', {'folder': folder['folder_id']})
        names = {entry['name'] for group in ('progress', 'queued', 'rest')
                 for entry in needed.get(group, []) if backfill.valid_name(entry.get('name'))}
        return sorted(names)


def provider_status(settings, registry=providers.registry):
    return [{'name': name, **asdict(provider.status()), 'endpoint_class': provider.endpoint_class()}
            for name, provider in registry(settings.snapshot()).items()]


def check_provider(settings, name, registry=providers.registry):
    available = registry(settings.snapshot())
    if name not in available:
        raise KeyError(name)
    provider = available[name]
    try:
        with providers.execution_slot(provider, blocking=False):
            response = _check_provider(settings, provider)
    except providers.Busy:
        return {'ok': False, 'reason': 'busy', 'sent_fields': [], 'endpoint_class': 'unknown'}
    if response['ok']:
        with closing(store.connect(settings.root / 'state.sqlite3')) as con:
            providers.release_resolved_blocks(con, settings, available, authenticated={name})
    return response


def _check_provider(settings, provider):
    status, endpoint = provider.status(), provider.endpoint_class()
    if ('transcript' not in settings.get('providers.consent').get(provider.name, []) or
            (settings.get('providers.local_only') and endpoint != 'local') or
            not status.installed or status.logged_in is False or
            (status.tool_block != 'verified' and not (
                status.tool_block == 'unverified' and provider.name in settings.get('providers.allow_unverified')))):
        return {'ok': False, 'reason': 'consent_or_provider_policy', 'sent_fields': [],
                'endpoint_class': endpoint}
    # Never accept user text for a setup probe, even when the caller sends it.
    result = provider.complete('Synthetic transcript: Alice says hello. Reply with OK only.', timeout=30)
    return {'ok': bool(result.text.strip()), 'sent_fields': ['transcript'], 'synthetic': True,
            'endpoint_class': result.endpoint_class}


def checks(root):
    memory = None
    if platform.system() == 'Darwin':
        memory = int(subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.memsize'], timeout=5))
    elif hasattr(os, 'sysconf'):
        memory = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    return {'chip': platform.machine(), 'supported': platform.system() == 'Darwin' and platform.machine() == 'arm64',
            'memory_bytes': memory, 'disk_free_bytes': shutil.disk_usage(root).free,
            'ffmpeg': {'installed': bool(shutil.which(os.environ.get('QC_FFMPEG', 'ffmpeg'))), 'remedy': 'brew install ffmpeg'},
            'uv': {'installed': bool(shutil.which(os.environ.get('QC_UV', 'uv'))), 'remedy': 'brew install uv'}}


def vaults(home=None):
    path = (Path(home) if home is not None else Path.home()) / 'Library/Application Support/obsidian/obsidian.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return [{'path': item['path'], 'exists': Path(item['path']).is_dir()}
            for item in data.get('vaults', {}).values() if isinstance(item.get('path'), str)]
