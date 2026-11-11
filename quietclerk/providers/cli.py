"""Subscription CLI adapters; prompts never appear in argv or logs."""
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from .. import procs
from . import (AuthExpired, Completion, ContextTooLong, NotInstalled, ProviderError,
               ProviderStatus, RateLimited, Timeout, ToolUseDetected, serial_call)


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

    def endpoint_class(self):
        return 'external'

    @serial_call
    def run(self, args, *, prompt=None, timeout=15, cwd=None):
        exe = executable(self.name)
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
        try:
            with tempfile.TemporaryDirectory() as cwd:
                result = self.run(['--version'], cwd=cwd)
                match = re.search(r'\d+\.\d+\.\d+', result.stdout)
                version = match.group(0) if match else ''
                login = None
                if self.name in ('codex', 'claude'):
                    auth = self.run(['login', 'status'] if self.name == 'codex' else ['auth', 'status'], cwd=cwd)
                    login = auth.returncode == 0
            return ProviderStatus(True, login, version, self.verification(version))
        except NotInstalled:
            return ProviderStatus(False, False, '', self.verification(''))
        except ProviderError:
            return ProviderStatus(True, None, '', 'unverified', 'status probe failed')

    def verification(self, version):
        return 'unverified'


class Codex(CLI):
    name = 'codex'

    def verification(self, version):
        parts = tuple(map(int, version.split('.'))) if version else ()
        return 'verified' if len(parts) == 3 and parts[0] == 0 and 163 <= parts[1] <= 167 else 'unverified'

    def complete(self, prompt, *, timeout):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as cwd:
            last = Path(cwd) / 'last.txt'
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
            result = self.run(args, prompt=prompt, timeout=timeout, cwd=cwd)
            self.last_events = []
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError as exc:
                    raise ProviderError('invalid Codex event') from exc
                self.last_events.append(event)
                if event.get('item', {}).get('type') in {'command_execution', 'file_change', 'mcp_tool_call', 'web_search'}:
                    raise ToolUseDetected()
            if result.returncode or not last.exists():
                raise failure(result.stderr + result.stdout)
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
