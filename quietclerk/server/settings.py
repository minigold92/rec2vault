"""API settings writes: validate every key before atomically replacing TOML.

The whole file is rewritten, including removal of comments (§3.3). Runtime root
and inbox are immutable; environment-locked fields cannot be changed via HTTP.
"""
import json
import os
import tempfile
from contextlib import closing

from .. import config, providers, store


class LockedSetting(ValueError):
    def __init__(self, field):
        self.field = field


def save(settings, changes, *, environ=None):
    if not isinstance(changes, dict):
        raise config.SettingsError('', 'expected an object of setting keys')
    changes = config._flatten(changes)
    for key, value in changes.items():
        config._validate(key, value)
        if key in settings.environment_keys or key in ('root', 'inbox'):
            raise LockedSetting(key)
    values = settings.file_values | changes
    # Quoted dotted keys are literal top-level keys; load() accepts this same
    # flat representation, including a nested dictionary for consent.
    def toml(value):
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if type(value) is bool:
            return 'true' if value else 'false'
        if type(value) is int:
            return str(value)
        if isinstance(value, list):
            return '[' + ', '.join(toml(item) for item in value) + ']'
        return '{' + ', '.join(json.dumps(k) + ' = ' + toml(v) for k, v in value.items()) + '}'
    content = ''.join(json.dumps(key) + ' = ' + toml(value) + '\n' for key, value in values.items())
    settings.path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.settings-', suffix='.toml', dir=settings.path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        env = ({config.ENV_KEYS[key]: str(settings.get(key)).lower() if type(settings.get(key)) is bool
                else str(settings.get(key)) for key in settings.environment_keys}
               if environ is None else dict(environ))
        # Preserve the current root when tests or a CLI supplied it explicitly.
        env.setdefault('QC_ROOT', str(settings.root))
        validated = config.load(temporary, environ=env)
        config.check_daily_note(validated.snapshot())
        os.replace(temporary, settings.path)
        updated = config.Settings(validated.snapshot(), validated.file_values,
                                  settings.environment_keys, settings.path)
        with closing(store.connect(settings.root / 'state.sqlite3')) as con:
            providers.release_resolved_blocks(con, updated)
        return updated
    finally:
        from pathlib import Path
        Path(temporary).unlink(missing_ok=True)
