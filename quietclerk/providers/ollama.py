"""Ollama HTTP, with positive local-weight evidence and a request-wide deadline.

Metadata: https://docs.ollama.com/api-reference/show-model-details.md
Cloud markers: https://github.com/ollama/ollama/blob/main/api/types.go (ShowResponse).
Cloud aliases alone are insufficient: https://docs.ollama.com/cloud.md
"""
import http.client
import ipaddress
import json
import socket
import threading
import time
from urllib.parse import urlsplit

from . import (AuthExpired, Completion, ContextTooLong, ProviderError, ProviderStatus,
               RateLimited, Timeout, ToolUseDetected, serial_call)


class Ollama:
    name = 'ollama'

    def __init__(self, settings):
        self.model = settings.get('providers.ollama.model', '')
        self.url = urlsplit(settings.get('providers.ollama.endpoint', 'http://127.0.0.1:11434'))

    @serial_call
    def request(self, path, payload=None, timeout=15):
        if self.url.scheme not in ('http', 'https') or not self.url.hostname or self.url.username or self.url.query:
            raise ProviderError('invalid Ollama endpoint')
        cls = http.client.HTTPSConnection if self.url.scheme == 'https' else http.client.HTTPConnection
        connection = cls(self.url.hostname, self.url.port, timeout=timeout)
        expired = threading.Event()

        def cancel():
            expired.set()
            if connection.sock:
                try:
                    connection.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            connection.close()

        timer = threading.Timer(timeout, cancel)
        timer.daemon = True
        timer.start()
        try:
            connection.request('POST' if payload is not None else 'GET',
                               self.url.path.rstrip('/') + path,
                               body=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = json.loads(response.read())
            if expired.is_set():
                raise Timeout('Ollama timeout')
            if response.status in (401, 403):
                raise AuthExpired('Ollama authentication required')
            if response.status == 429:
                raise RateLimited('Ollama rate limit')
            if response.status >= 400 or data.get('error'):
                if 'context' in str(data.get('error', '')).lower():
                    raise ContextTooLong('Ollama context too long')
                raise ProviderError('Ollama request failed')
            return data
        except (OSError, ValueError, http.client.HTTPException) as exc:
            if expired.is_set() or isinstance(exc, socket.timeout):
                raise Timeout('Ollama timeout') from exc
            raise ProviderError('Ollama request failed') from exc
        finally:
            timer.cancel()
            connection.close()

    def endpoint_class(self):
        host = self.url.hostname
        try:
            loopback = host == 'localhost' or ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            loopback = False
        if not loopback:
            return 'external' if host else 'unknown'
        try:
            info = self.request('/api/show', {'model': self.model})
        except ProviderError:
            return 'unknown'
        if info.get('remote_host') or info.get('remote_model') or self.model.endswith((':cloud', '-cloud')):
            return 'external'
        if info.get('details', {}).get('format') == 'gguf' and info.get('model_info', {}).get('general.architecture'):
            return 'local'
        return 'unknown'

    def status(self):
        try:
            version = self.request('/api/version').get('version', '')
            self.request('/api/show', {'model': self.model})
            # No client tools or execution callbacks exist in this HTTP adapter.
            return ProviderStatus(True, True, version, 'verified')
        except AuthExpired:
            return ProviderStatus(True, False, '', 'verified')
        except ProviderError:
            return ProviderStatus(False, None, '', 'verified')

    def complete(self, prompt, *, timeout):
        started = time.monotonic()
        data = self.request('/api/generate', {'model': self.model, 'prompt': prompt, 'stream': False,
                            'keep_alive': 0, 'options': {'num_ctx': max(2048, len(prompt.encode('utf-8')) + 1024)}},
                            timeout=timeout)
        if data.get('tool_calls') or data.get('message', {}).get('tool_calls'):
            raise ToolUseDetected()
        text = data.get('response')
        if not isinstance(text, str) or not text.strip():
            raise ProviderError('empty Ollama response')
        endpoint = 'external' if data.get('remote_host') or data.get('remote_model') else self.endpoint_class()
        return Completion(text, data.get('model', self.model), endpoint, time.monotonic() - started)
