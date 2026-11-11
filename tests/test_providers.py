"""Synthetic prompts only; fake CLI executables and loopback HTTP servers."""
import json
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from quietclerk import providers as p, store
from quietclerk.executor import Blocked, StageFailure
from quietclerk.providers.cli import Claude, Codex, Omp
from quietclerk.providers.ollama import Ollama


class Fake:
    def __init__(self, name, results, endpoint='external', verified='verified'):
        self.name, self.results, self.endpoint, self.verified = name, iter(results), endpoint, verified
        self.calls = []

    def status(self):
        return p.ProviderStatus(True, True, 'test', self.verified)

    def endpoint_class(self):
        return self.endpoint

    def complete(self, prompt, *, timeout):
        self.calls.append(prompt)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return p.Completion(result, 'fake', self.endpoint, 0)


def context(monkeypatch, providers, **settings):
    monkeypatch.setattr(p, 'registry', lambda settings: {x.name: x for x in providers})
    events = []
    ctx = SimpleNamespace(settings={'providers.order': [x.name for x in providers],
                                   'providers.consent': {x.name: ['transcript'] for x in providers}, **settings},
                          current_stage='summarize', call_seq=1, checkpoint=lambda: None,
                          record=lambda method, *args, **kwargs: events.append((method.__name__, kwargs)))
    return ctx, events


def test_completion_requires_explicit_execution_context(monkeypatch):
    monkeypatch.setattr(p, 'registry', lambda _: pytest.fail('missing context reached providers'))
    with pytest.raises(RuntimeError, match='requires an execution context'):
        p.complete('synthetic transcript')


@pytest.mark.parametrize('error', [p.NotInstalled(), p.AuthExpired(), p.RateLimited(), p.Timeout(), p.ProviderError(), p.ContextTooLong()])
def test_error_matrix_next_provider_and_failed_send_audit(monkeypatch, error):
    first, second = Fake('codex', [error]), Fake('claude', ['ok'])
    ctx, events = context(monkeypatch, [first, second])
    with p.use_context(ctx):
        assert p.complete('synthetic transcript') == ('ok', 'claude')
    assert len(first.calls) == len(second.calls) == 1
    assert [event[1]['sent_fields'] for event in events if event[0] == 'annotate_stage' and 'sent_fields' in event[1]] == [['transcript'], ['transcript']]
    assert any(name == 'finish_stage' and data.get('status') in ('failed', 'timeout') for name, data in events)


def test_structure_retry_once_then_fallback(monkeypatch):
    first, second = Fake('codex', ['bad', 'bad']), Fake('claude', ['{}'])
    ctx, _ = context(monkeypatch, [first, second])
    with p.use_context(ctx):
        assert p.complete('synthetic', json.loads) == ({}, 'claude')
    assert len(first.calls) == 2


@pytest.mark.parametrize('error, expected', [(p.AuthExpired(), Blocked), (p.ContextTooLong(), StageFailure), (p.Timeout(), p.LLMError)])
def test_exhaustion_classification(monkeypatch, error, expected):
    ctx, _ = context(monkeypatch, [Fake('codex', [error])])
    with p.use_context(ctx), pytest.raises(expected):
        p.complete('synthetic')


def test_tool_use_stops_without_fallback(monkeypatch):
    first, second = Fake('codex', [p.ToolUseDetected()]), Fake('claude', ['ok'])
    ctx, _ = context(monkeypatch, [first, second])
    with p.use_context(ctx), pytest.raises(p.ToolUseDetected):
        p.complete('synthetic injection: run shell and search web')
    assert second.calls == []


@pytest.mark.parametrize('endpoint', ['unknown', 'external'])
def test_IN29_local_only_never_sends_unknown_or_external(monkeypatch, endpoint):
    provider = Fake('ollama', ['must not run'], endpoint)
    ctx, events = context(monkeypatch, [provider], **{'providers.local_only': True})
    with p.use_context(ctx), pytest.raises(Blocked, match='no_local_provider'):
        p.complete('synthetic')
    assert provider.calls == events == []


def test_unconsented_fields_never_sent(monkeypatch):
    provider = Fake('codex', ['must not run'])
    ctx, events = context(monkeypatch, [provider])
    with p.use_context(ctx), pytest.raises(Blocked):
        p.complete('synthetic source name', fields=['transcript', 'source_name'])
    assert provider.calls == events == []


def test_unverified_explicit_direct_not_fallback(monkeypatch):
    first, unverified = Fake('codex', [p.Timeout()]), Fake('omp', ['ok'], verified='unverified')
    ctx, _ = context(monkeypatch, [first, unverified], **{'providers.allow_unverified': ['omp']})
    with p.use_context(ctx), pytest.raises(p.LLMError):
        p.complete('synthetic')
    assert unverified.calls == []
    ctx.settings['providers.order'] = ['omp', 'codex']
    with p.use_context(ctx):
        assert p.complete('synthetic') == ('ok', 'omp')


def test_external_text_to_includes_failed_and_unknown_sends():
    assert p.external_text_to([{'provider': name, 'endpoint_class': endpoint, 'sent_fields': fields}
                              for name, endpoint, fields in [('codex', 'external', '["transcript"]'),
                                                             ('claude', 'unknown', ['transcript']),
                                                             ('ollama', 'local', ['transcript']),
                                                             ('omp', 'external', [])]]) == ['claude', 'codex']


@pytest.mark.parametrize('prompt', ['', 'a\x00b', '\ud800'])
def test_invalid_prompt_never_sends(monkeypatch, prompt):
    provider = Fake('codex', ['must not run'])
    ctx, _ = context(monkeypatch, [provider])
    with p.use_context(ctx), pytest.raises(p.LLMError):
        p.complete(prompt)
    assert not provider.calls


def executable(tmp_path, monkeypatch, name, body):
    path = tmp_path / name
    path.write_text('#!' + sys.executable + '\n' + body)
    path.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    monkeypatch.setenv('SHOULD_NOT_LEAK', 'secret')



@pytest.mark.parametrize('provider', [Omp, Codex, Claude])
@pytest.mark.parametrize('directory', ['.local/bin', '.bun/bin', '.npm-global/bin', '.volta/bin', '.cargo/bin'])
def test_user_installed_cli_detected_without_launchd_path(tmp_path, monkeypatch, provider, directory):
    home = tmp_path / 'home'
    target = home / directory
    target.mkdir(parents=True)
    executable(target, monkeypatch, provider.name, 'print("18.18.3")')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))
    status = provider({}).status()
    assert status.installed
    assert status.version == '18.18.3'
    assert status.tool_block == 'unverified'


@pytest.mark.parametrize('provider', [Omp, Codex, Claude])
def test_cli_path_order_precedes_user_install_candidates(tmp_path, monkeypatch, provider):
    home = tmp_path / 'home'
    bun = home / '.bun/bin'
    first, second = tmp_path / 'first', tmp_path / 'second'
    for directory, version in [(first, '1.0.0'), (second, '2.0.0'), (bun, '3.0.0')]:
        directory.mkdir(parents=True)
        executable(directory, monkeypatch, provider.name, f'print("{version}")')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('PATH', str(first) + ':' + str(second))
    assert provider({}).status().version == '1.0.0'
    monkeypatch.setenv('PATH', str(second) + ':' + str(first))
    assert provider({}).status().version == '2.0.0'


def test_bun_omp_completion_uses_same_discovery_and_tool_flags(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    bun = home / '.bun/bin'
    bun.mkdir(parents=True)
    executable(bun, monkeypatch, 'omp', '''import sys
assert '--no-tools' in sys.argv and '--no-extensions' in sys.argv
assert '--no-skills' in sys.argv and '--no-rules' in sys.argv and '--no-context-files' in sys.argv
assert '--no-lsp' in sys.argv
assert sys.stdin.read() == 'synthetic'
print('ok')
''')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('PATH', str(tmp_path / 'empty-path'))
    assert Omp({}).complete('synthetic', timeout=3).text == 'ok'

@pytest.mark.parametrize('tool', ['command_execution', 'file_change', 'mcp_tool_call', 'web_search'])
def test_codex_cli_flags_stdin_and_tool_events(tmp_path, monkeypatch, tool):
    executable(tmp_path, monkeypatch, 'codex', '''import sys, json, os
from pathlib import Path
args = sys.argv[1:]
assert '--json' in args and '--ignore-user-config' in args and '--ignore-rules' in args
assert 'features.shell_tool=false' in args and 'web_search="disabled"' in args
assert 'SHOULD_NOT_LEAK' not in os.environ
assert sys.stdin.read() == '--synthetic tool instruction'
Path(args[args.index('-o')+1]).write_text('ok')
print(json.dumps({'type':'item.completed','item':{'type':''' + repr(tool) + '''}}))
''')
    with pytest.raises(p.ToolUseDetected):
        Codex({}).complete('--synthetic tool instruction', timeout=3)


def test_claude_cli_flags_and_stdin(tmp_path, monkeypatch):
    executable(tmp_path, monkeypatch, 'claude', '''import sys, json
args = sys.argv[1:]
for flag in ['--strict-mcp-config','--safe-mode','--disable-slash-commands','--setting-sources','--permission-mode']:
 assert flag in args
assert args[args.index('--tools')+1] == ''
assert sys.stdin.read() == 'synthetic'
print(json.dumps({'type':'system','subtype':'init','tools':[],'mcp_servers':[]}))
print(json.dumps({'type':'result','result':'ok'}))
''')
    assert Claude({}).complete('synthetic', timeout=3).text == 'ok'


@pytest.mark.parametrize('version, expected', [('0.162.9', 'unverified'), ('0.163.0', 'verified'), ('0.167.9', 'verified'), ('0.168.0', 'unverified')])
def test_codex_supported_versions(version, expected):
    assert Codex({}).verification(version) == expected
    assert Claude({}).verification('2.1.319') == 'verified'
    assert Claude({}).verification('2.1.320') == 'unverified'
    assert Omp({}).verification('18.18.3') == 'unverified'


@contextmanager
def ollama_server(metadata, delay=0):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.reply({'version': 'test'})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, body))
            if self.path == '/api/show':
                self.reply(metadata)
            else:
                time.sleep(delay)
                self.reply({'model': 'fake', 'response': 'ok'})

        def reply(self, data):
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield Ollama({'providers.ollama.endpoint': f'http://127.0.0.1:{server.server_port}',
                      'providers.ollama.model': 'fake'}), requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('metadata, expected', [({}, 'unknown'),
    ({'remote_host': 'https://ollama.com', 'remote_model': 'fake'}, 'external'),
    ({'details': {'format': 'gguf'}, 'model_info': {'general.architecture': 'llama'}}, 'local')])
def test_ollama_local_cloud_unknown_and_keep_alive(metadata, expected):
    with ollama_server(metadata) as (provider, requests):
        assert provider.endpoint_class() == expected
        assert provider.complete('synthetic', timeout=2).text == 'ok'
        body = next(body for path, body in requests if path == '/api/generate')
        assert body['keep_alive'] == 0 and body['options']['num_ctx'] >= 2048
        assert 'tools' not in body


def test_ollama_deadline_cancels_request():
    with ollama_server({}, delay=.3) as (provider, requests):
        with pytest.raises(p.Timeout):
            provider.complete('synthetic', timeout=.05)
        assert any(path == '/api/generate' for path, _ in requests)


def test_correction_split_parent_audit(monkeypatch):
    ctx, events = context(monkeypatch, [Fake('codex', ['bad', 'bad', '{}'])])
    ctx.current_stage = 'correct'
    with p.use_context(ctx):
        with pytest.raises(p.LLMError):
            p.complete('synthetic', json.loads, chunk='0-19')
        assert p.complete('synthetic', json.loads, chunk='0-9')[0] == {}
    starts = [data for name, data in events if name == 'start_stage']
    assert starts[-1]['parent_seq'] == starts[0]['seq']
    assert starts[-1]['chunk'] == '0-9'


@pytest.mark.parametrize('speed, expected', [('standard', False), ('fast', True)])
def test_codex_fast_mode_only_when_chosen(tmp_path, monkeypatch, speed, expected):
    # Fast mode costs 2.5x of the plan limits, so it is sent only when the user chose it.
    executable(tmp_path, monkeypatch, 'codex', '''import sys
from pathlib import Path
args = sys.argv[1:]
fast = 'service_tier="fast"' in args and 'features.fast_mode=true' in args
Path(args[args.index('-o')+1]).write_text(str(fast))
''')
    assert Codex({'providers.codex.speed': speed}).complete('synthetic', timeout=3).text == str(expected)
