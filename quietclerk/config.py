"""Contract v2 settings: QC environment > settings.toml > installation defaults.

load() returns an independent snapshot; never mutate it during a run. File values and
locked environment keys are retained for the settings UI. REC_* is not consulted.
Installation defaults live in root/installation.json, atomically initialized under
an advisory lock so separate tick processes share one cutoff, port and language.
Importing this module is read-only; only an explicit load() initializes a root.
"""
import copy
import fcntl
import json
import locale
import os
import socket
import tempfile
import tomllib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ENV_KEYS = {'root': 'QC_ROOT', 'inbox': 'QC_INBOX', 'output': 'QC_OUTPUT',
            'since': 'QC_SINCE', 'min_duration_sec': 'QC_MIN_DURATION_SEC',
            'stable_sec': 'QC_STABLE_SEC', 'language.mode': 'QC_LANGUAGE',
            'providers.local_only': 'QC_LOCAL_ONLY', 'server.port': 'QC_PORT'}
DEFAULTS = {'root': str(Path.home() / 'QuietClerk'), 'inbox': None, 'output': None,
            'since': '', 'min_duration_sec': 300, 'stable_sec': 60,
            'language.mode': 'auto', 'language.default': 'en',
            'notes.output_language': 'same', 'providers.order': [],
            'providers.local_only': False, 'providers.consent': {},
            'providers.allow_unverified': [], 'providers.ollama.model': '',
            'providers.ollama.endpoint': 'http://127.0.0.1:11434',
            'providers.omp.profile': 'quietclerk', 'providers.codex.effort': 'low', 'providers.codex.speed': 'standard',
            'server.port': 0, 'retention.wav_days': 7, 'ui.language': 'en',
            'updates.check': True, 'vocabulary.terms': [], 'vocabulary.replace': []}
PROVIDERS = ('codex', 'claude', 'gemini', 'ollama', 'omp')


class SettingsError(ValueError):
    def __init__(self, field, error):
        self.field = field
        super().__init__(f'{field}: {error}')


def _flatten(data, prefix=''):
    result = {}
    for key, value in data.items():
        name = f'{prefix}.{key}' if prefix else key
        if name == 'providers.agy' or name.startswith('providers.agy.'):
            _validate(name, value)  # Reject even an empty removed-provider table.
        if isinstance(value, dict) and name not in ('providers.consent', 'vocabulary.terms', 'vocabulary.replace'):
            result.update(_flatten(value, name))
        else:
            result[name] = _validate(name, value) if name.startswith('vocabulary.') else value
    return result


def _vocabulary_text(key, value):
    # Same rule as backends.quality._term: any Unicode "other" character (controls, format
    # characters such as zero-width or bidi marks, private use, surrogates) is refused.
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 40 or
            any(unicodedata.category(c).startswith('C') for c in value.strip())):
        raise SettingsError(key, 'expected 1–40 characters without control characters')
    return value.strip()


def _validate(key, value):
    if (key.startswith('providers.agy') or
            (key in ('providers.order', 'providers.allow_unverified', 'providers.consent') and
             isinstance(value, (list, dict)) and 'agy' in value)):
        raise SettingsError(key, 'agy was removed: its tool execution cannot be disabled safely; choose a supported provider')
    if key not in DEFAULTS:
        raise SettingsError(key, 'unknown setting')
    default = DEFAULTS[key]
    if key in ('root', 'inbox', 'output'):
        if not isinstance(value, str) or not value:
            raise SettingsError(key, 'expected a nonempty path')
        return str(Path(value).expanduser())
    if type(value) is not type(default):
        raise SettingsError(key, f'expected {type(default).__name__}')
    options = {'language.mode': ('auto', 'ko', 'en'), 'language.default': ('ko', 'en'),
               'notes.output_language': ('same', 'ko', 'en'), 'ui.language': ('ko', 'en')}
    if key in options and value not in options[key]:
        raise SettingsError(key, 'invalid language')
    if key.startswith('vocabulary.'):
        if len(value) > 200:
            raise SettingsError(key, 'expected at most 200 entries')
        if key == 'vocabulary.terms':
            return list(dict.fromkeys(_vocabulary_text(key, term) for term in value))
        result, seen = [], {}
        for row in value:
            if not isinstance(row, dict) or set(row) != {'from', 'to'}:
                raise SettingsError(key, 'expected {from, to} entries')
            source, target = (_vocabulary_text(key, row[field]) for field in ('from', 'to'))
            if source in seen and seen[source] != target:
                raise SettingsError(key, 'conflicting replacements')
            if source not in seen:
                result.append({'from': source, 'to': target})
            seen[source] = target
        return result
    if key == 'providers.codex.speed' and value not in ('standard', 'fast'):
        raise SettingsError(key, 'expected standard or fast')
    if key == 'since':
        try:
            datetime.strptime(value, '%Y-%m-%d %H:%M')
        except ValueError as exc:
            raise SettingsError(key, 'expected YYYY-MM-DD HH:MM') from exc
    if type(value) is int and (value < 0 or (key == 'server.port' and not 1 <= value <= 65535)):
        raise SettingsError(key, 'out of range')
    if key in ('providers.order', 'providers.allow_unverified') and (
            any(not isinstance(x, str) or x not in PROVIDERS for x in value) or
            len(set(value)) != len(value)):
        raise SettingsError(key, 'expected distinct provider names')
    if key == 'providers.consent':
        for provider, fields in value.items():
            if provider not in PROVIDERS or not isinstance(fields, list) or any(
                    field not in ('transcript', 'source_name', 'project_list', 'vocabulary') for field in fields):
                raise SettingsError(key, 'expected provider field lists')
    return value


@dataclass(frozen=True)
class Settings:
    _values: dict
    file_values: dict
    environment_keys: frozenset
    path: Path

    def get(self, key):
        return copy.deepcopy(self._values[key])

    def snapshot(self):
        return copy.deepcopy(self._values)

    @property
    def root(self):
        return Path(self._values['root'])


def _installation_defaults(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'installation.json'
    with (root / 'installation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            try:
                values = json.loads(path.read_text(encoding='utf-8'))
                return {key: _validate(key, values[key]) for key in
                        ('since', 'server.port', 'language.default', 'ui.language')}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise SettingsError('installation', 'invalid persisted defaults') from exc
        language = 'ko' if (locale.getlocale()[0] or '').startswith('ko') else 'en'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        values = {'since': datetime.now().strftime('%Y-%m-%d %H:%M'), 'server.port': port,
                  'language.default': language, 'ui.language': language}
        fd, temporary = tempfile.mkstemp(prefix='.installation-', suffix='.part', dir=root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(values, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return values


def load(path=None, environ=None):
    env = dict(os.environ if environ is None else environ)
    # QC_SETTINGS selects the configuration file, not a persisted setting.
    root = Path(env.get('QC_ROOT', DEFAULTS['root'])).expanduser()
    path = Path(path or env.get('QC_SETTINGS', root / 'settings.toml')).expanduser()
    file_values = _flatten(tomllib.loads(path.read_text(encoding='utf-8'))) if path.is_file() else {}
    values = copy.deepcopy(DEFAULTS)
    for key, value in file_values.items():
        values[key] = _validate(key, value)
    locked = set()
    for key, name in ENV_KEYS.items():
        if name not in env:
            continue
        value = env[name]
        if type(DEFAULTS[key]) is int:
            try:
                value = int(value)
            except ValueError as exc:
                raise SettingsError(key, 'expected integer') from exc
        elif type(DEFAULTS[key]) is bool:
            if value.lower() not in ('true', 'false'):
                raise SettingsError(key, 'expected true or false')
            value = value.lower() == 'true'
        values[key] = _validate(key, value)
        locked.add(key)
    for key, suffix in (('inbox', 'inbox'), ('output', 'notes')):
        if values[key] is None:
            values[key] = str(Path(values['root']) / suffix)
    defaults = _installation_defaults(Path(values['root']))
    for key, value in defaults.items():
        if key not in file_values and key not in locked:
            values[key] = value
    return Settings(values, copy.deepcopy(file_values), frozenset(locked), path)


MAX_DURATION_SEC = 3 * 3600
MAX_BYTES = 1 << 30
CORRECT_CHUNK_TURNS = 60
