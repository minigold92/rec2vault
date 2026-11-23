"""Subscription CLI adapters; prompts never appear in argv or logs."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from .. import procs, tool_checks
from . import (AuthExpired, Completion, ContextTooLong, NotInstalled, ProviderError,
               ProviderStatus, RateLimited, Timeout, ToolUseDetected, events, serial_call)

# The whole version string a CLI prints, suffix included: `0.171.0-beta.1` is not `0.171.0`.
VERSION = re.compile(r'\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]*)?')
_hashes = {}


def environment():
    return {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'TMPDIR', 'CODEX_HOME')
            if key in os.environ}


def executable(name):
    """Respect PATH first, then known per-user package-manager bin directories."""
    found = shutil.which(name, path=environment().get('PATH', ''))
    if found:
        return found
    home = Path.home()
    for directory in ('.local/bin', '.bun/bin', '.npm-global/bin', '.volta/bin', '.cargo/bin'):
        found = shutil.which(name, path=str(home / directory))
        if found:
            return found
    return None


def file_identity(path, fresh=False):
    """SHA-256 of an executable. Cached on (path, size, mtime, ctime, inode): changing the content moves ctime,
    which a user-level process cannot set back. `fresh` always reads the file (the check right before a call)."""
    stat = os.stat(path)
    key = (path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    if fresh or key not in _hashes:
        digest = hashlib.sha256()
        with open(path, 'rb') as stream:
            for block in iter(lambda: stream.read(1 << 20), b''):
                digest.update(block)
        if len(_hashes) > 32:
            _hashes.clear()
        _hashes[key] = digest.hexdigest()
    return _hashes[key]


def failure(message):
    text = message.lower()
    if any(s in text for s in ('not logged in', 'unauthorized', 'authentication', '401', 'login required')):
        return AuthExpired('authentication required')
    if any(s in text for s in ('rate limit', 'quota', '429')):
        return RateLimited('provider rate limit')
    if any(s in text for s in ('context length', 'context window', 'context_length', 'too many tokens')):
        return ContextTooLong('context too long')
    return ProviderError('provider request failed')


class CLI:
    name = ''

    def __init__(self, settings):
        self.settings = settings
        self.seen = None   # (version, real path, sha256) of the executable the last status() read

    def endpoint_class(self):
        return 'external'

    @serial_call
    def run(self, args, *, prompt=None, timeout=15, cwd=None, exe=None):
        """Run the CLI. `exe` pins the file that was checked; without it PATH is searched."""
        exe = exe or executable(self.name)
        if not exe:
            raise NotInstalled(self.name)
        try:
            return procs.run([exe, *args], input=prompt, timeout=timeout, cwd=cwd,
                             capture_output=True, text=True, env=environment())
        except procs.TimeoutExpired as exc:
            raise Timeout('provider timeout') from exc
        except OSError as exc:
            raise ProviderError('cannot execute provider') from exc

    def status(self):
        self.seen = None
        try:
            found = executable(self.name)
            if not found:
                raise NotInstalled(self.name)
            exe = os.path.realpath(found)   # version, login and later calls all use this one file
            with tempfile.TemporaryDirectory() as cwd:
                result = self.run(['--version'], cwd=cwd, exe=exe)
                match = VERSION.search(result.stdout)
                version = match.group(0) if match else ''
                login = None
                if self.name in ('codex', 'claude'):
                    auth = self.run(['login', 'status'] if self.name == 'codex' else ['auth', 'status'], cwd=cwd, exe=exe)
                    login = auth.returncode == 0
            self.seen = (version, exe, file_identity(exe))
            return ProviderStatus(True, login, version, self.verification(version))
        except NotInstalled:
            return ProviderStatus(False, False, '', self.verification(''))
        except (ProviderError, OSError):
            return ProviderStatus(True, None, '', 'unverified', 'status probe failed')

    def pinned(self):
        """The executable the last status() checked, after proving it is still the same file; None if none was read."""
        if self.seen is None:
            return None
        if file_identity(self.seen[1], fresh=True) != self.seen[2]:
            raise ProviderError('executable changed after it was checked')
        return self.seen[1]

    def verification(self, version):
        return 'unverified'


VERIFIED_CODEX_MINORS = frozenset(range(163, 168)) | {170}


class Codex(CLI):
    name = 'codex'

    def verification(self, version):
        # Fixed minors were checked by hand with a real canary (contract 8.5), by exact `0.minor.patch` only.
        parts = tuple(map(int, version.split('.'))) if re.fullmatch(r'\d+\.\d+\.\d+', version or '') else ()
        if len(parts) == 3 and parts[0] == 0 and parts[1] in VERIFIED_CODEX_MINORS:
            return 'verified'
        # Any other version is verified only by a stored pass of the decoy test for this exact version, file path
        # and file content (providers/decoy.py).
        if self.seen is None or self.seen[0] != version:
            return 'unverified'
        row = tool_checks.recorded(self.settings.get('root'), self.name, version, self.seen[1], self.seen[2])
        return 'verified' if row and row['passed'] else 'unverified'

    def command(self, last):
        """The one command line for every Codex call, including the decoy test (contract 8.5)."""
        args = ['exec', '--skip-git-repo-check', '--sandbox', 'read-only', '--ephemeral',
                '--ignore-user-config', '--ignore-rules', '--json']
        for setting in ('features.shell_tool=false', 'web_search="disabled"', 'features.apps=false',
                        'features.plugins=false', 'features.view_image=false',
                        'features.image_generation=false', 'features.hooks=false'):
            args += ['-c', setting]
        args += ['-c', 'model_reasoning_effort=' + json.dumps(self.settings.get('providers.codex.effort', 'low'))]
        if self.settings.get('providers.codex.speed', 'standard') == 'fast':
            # Codex Fast mode: ~1.5x faster on supported models, uses subscription limits at 2.5x.
            args += ['-c', 'service_tier="fast"', '-c', 'features.fast_mode=true']
        args += ['-o', str(last), '-']
        return args

    def tool_check(self, clock=time.time):
        from . import decoy
        return decoy.run(self, self.command, events.codex_events, clock=clock)

    def complete(self, prompt, *, timeout):
        started = time.monotonic()
        exe = self.pinned()
        with tempfile.TemporaryDirectory() as cwd:
            last = Path(cwd) / 'last.txt'
            args = self.command(last)
            result = self.run(args, prompt=prompt, timeout=timeout, cwd=cwd, exe=exe)
            self.last_events = []
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError as exc:
                    raise ProviderError('invalid Codex event') from exc
                if not isinstance(event, dict):
                    raise ProviderError('invalid Codex event')
                self.last_events.append(event)
            # The same strict check as the decoy test. A tool or unknown item stops the call whatever the exit
            # code was; a missing turn.completed or an unknown event only counts when the CLI said it succeeded
            # (a failed sign-in prints error events and must stay a sign-in problem).
            reason, _ = events.codex_events(self.last_events)
            if events.is_tool_reason(reason):
                raise ToolUseDetected()
            if result.returncode or not last.exists():
                raise failure(result.stderr + result.stdout)
            if reason:
                raise ToolUseDetected()
            return Completion(last.read_text(encoding='utf-8'), '', 'external', time.monotonic() - started)


class Claude(CLI):
    name = 'claude'

    def verification(self, version):
        return 'verified' if version == '2.1.319' else 'unverified'

    def complete(self, prompt, *, timeout):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as cwd:
            result = self.run(['-p', '--tools', '', '--strict-mcp-config', '--safe-mode',
                               '--disable-slash-commands', '--setting-sources', '',
                               '--permission-mode', 'dontAsk', '--no-session-persistence',
                               '--output-format', 'stream-json', '--verbose'],
                              prompt=prompt, timeout=timeout, cwd=cwd)
        text, model = '', ''
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ProviderError('invalid Claude event') from exc
            if event.get('tools') or event.get('mcp_servers') or event.get('permission_denials'):
                raise ToolUseDetected()
            for block in event.get('message', {}).get('content', []):
                if block.get('type') == 'tool_use':
                    raise ToolUseDetected()
            if event.get('type') == 'result':
                if event.get('is_error'):
                    raise failure(event.get('result', ''))
                text = event.get('result', '')
            model = event.get('model', model)
        if result.returncode or not text:
            raise failure(result.stderr + result.stdout)
        return Completion(text, model, 'external', time.monotonic() - started)


class Omp(CLI):
    name = 'omp'

    def complete(self, prompt, *, timeout):
        started = time.monotonic()
        profile = self.settings.get('providers.omp.profile', 'quietclerk')
        if not profile or profile == 'default':
            raise ProviderError('omp requires a dedicated MCP-free profile')
        with tempfile.TemporaryDirectory() as cwd:
            result = self.run(['--profile', profile, '-p', '--no-session', '--no-tools',
                               '--no-extensions', '--no-skills', '--no-rules', '--no-context-files',
                               '--no-lsp', '--no-title'], prompt=prompt, timeout=timeout, cwd=cwd)
        if result.returncode or not result.stdout.strip():
            raise failure(result.stderr)
        return Completion(result.stdout.strip(), '', 'external', time.monotonic() - started)
