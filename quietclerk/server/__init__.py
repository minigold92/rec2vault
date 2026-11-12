"""Contract §9 API and the web screens; all mutations cross store/store_ops, never inline SQL.

Input policy: JSON objects only (64 KiB); unknown settings and wrong types fail
before writes; job IDs are opaque SQL parameters, never filesystem fragments;
audio opens only a DB-authorized archive. Missing files are 410, malformed or
multi-ranges 416. Endpoint/data schemas and scope exclusions live in schema.json.

Screens (F2): every screen path and every /static file needs the session cookie; without it a
screen navigation is redirected to the data-free bootstrap shell (303 to /) and anything else is
401, so no application markup or data leaves before sign-in. Screens are one fixed HTML shell
(templates/app.html, Jinja2 with autoescape) plus same-origin ES modules; the CSP forbids inline
script and style, so nothing is inlined. Static files are looked up by exact name in an index
built from the static directory, never joined from the request path. Text the engine or a
speaker produced (titles, transcripts, summaries) reaches the browser only as JSON and is put
into the page with textContent. The one data-bearing screen path, /notes/<job>, embeds the minutes
(read from the job's verified run artifacts and the vault note's header) as a JSON data block
because no /api endpoint serves note text yet; the JSON is HTML-safe (<, >, & escaped) so
hostile transcript text cannot end the block, and an unknown job answers 404 with the same
shell. Artifacts are read bounded, without following a final symlink, and only when their
metadata says ok and their bytes still match.
"""
import asyncio
import hashlib
import json
import os
import re
import stat
import secrets
import time
from concurrent.futures import wait
from contextlib import asynccontextmanager, closing
from importlib import metadata
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import Route

from .. import artifacts, backfill, config, intake, install, providers, selfupdate, store, store_ops
from ..notes import NoteConflict, conversion, migration
from . import integrations
from .. import overrides
from .auth import Auth, COOKIE
from .settings import LockedSetting, save

CSP = "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
BOOTSTRAP_HTML = '<!doctype html><meta charset="utf-8"><title>QuietClerk</title><script src="/bootstrap.js" defer></script><p id="bootstrap-status">QuietClerk</p>'
STATIC = Path(__file__).with_name('static')
TEMPLATES = Path(__file__).with_name('templates')
STATIC_TYPES = {'.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml'}
SCREENS = re.compile(r'/(?:home|jobs|notes|backlog|settings|migrate|setup/[1-6])|/notes/[^/]+')
ARTIFACT_LIMIT = 16 << 20
CITATION = re.compile(r'\[(t\d+(?:\s*,\s*t\d+)*)\]')
SECTION_KIND = {'핵심 요약': 'summary', 'Key summary': 'summary', '할 일': 'tasks', '합의·할 일': 'tasks',
                'Tasks': 'tasks', '확인 필요': 'review', 'Review needed': 'review'}


class Security:
    def __init__(self, app, *, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        hosts = [value.decode('latin1') for key, value in scope['headers'] if key.lower() == b'host']
        origins = [value.decode('latin1') for key, value in scope['headers'] if key.lower() == b'origin']
        host = hosts[0] if len(hosts) == 1 else ''
        allowed = (f'127.0.0.1:{self.auth.port}', f'localhost:{self.auth.port}')
        error = None
        if host not in allowed:
            error = 403
        mutating = request.method not in ('GET', 'HEAD', 'OPTIONS')
        if mutating and (len(origins) != 1 or origins[0] != 'http://' + host):
            error = 403
        public = ((scope['path'] in ('/', '/bootstrap.js') and request.method == 'GET') or
                  (scope['path'] == '/api/session' and request.method == 'POST'))
        session = self.auth.session(request.cookies.get(COOKIE)) if not public else None
        if not public and not session:
            error = error or 401
        if mutating and not public and session:
            supplied = request.headers.get('x-csrf-token', '')
            if not supplied.isascii() or not secrets.compare_digest(supplied, session.csrf):
                error = 403
        if error:
            if error == 401 and request.method == 'GET' and SCREENS.fullmatch(scope['path']):
                # A browser navigation without a session gets no screen and no data.
                response = RedirectResponse('/', 303)
            else:
                response = JSONResponse({'error': 'forbidden' if error == 403 else 'unauthorized'}, error)
        else:
            response = None
            scope['qc.session'] = session
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] += [(b'content-security-policy', CSP.encode()),
                                       (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'),
                                       (b'x-content-type-options', b'nosniff')]
            await send(message)
        if response:
            return await response(scope, receive, secure_send)
        await self.app(scope, receive, secure_send)


def engine_identity(runtime):
    try:
        version = metadata.version('quietclerk')
    except metadata.PackageNotFoundError:
        version = None
    try:
        install.read_app_installation(runtime.support / install.APP_RECORD)
        method = 'app'
    except install.InstallError:
        method = 'cli'
    update = runtime.updates.snapshot()
    return {'engine_version': version, 'installation_method': method,
            'last_updated_at': update.get('finished_at') if update['state'] == 'done' else None}


def status_snapshot(runtime):
    with closing(store.connect(runtime.db)) as con:
        current = con.execute("SELECT * FROM jobs WHERE status='running' ORDER BY claimed_at LIMIT 1").fetchone()
        stage = None
        if current:
            stage = con.execute("SELECT * FROM stage_runs WHERE run_id=? AND status='running' ORDER BY started_at DESC LIMIT 1",
                                (current['active_run_id'],)).fetchone()
        started = stage['started_at'] if stage else (current['claimed_at'] if current else None)
        update = runtime.updates.snapshot()
        return {'boot_id': runtime.boot, 'engine': store.engine_state(con) or 'ready',
                'paused': store_ops.paused(con), 'counts': store.counts(con),
                'current_job': dict(current) if current else None,
                'stage': dict(stage) if stage else None,
                'elapsed_sec': max(0, time.time() - started) if started else None,
                'last_progress': None,
                'update': {key: update[key] for key in ('state', 'behind')}}


def audio_response(runtime, con, job_id, range_header):
    row = store.job(con, job_id)
    if store_ops.deleted(con, job_id) or not row['archive_path']:
        return Response(status_code=410)
    path = Path(row['archive_path'])
    root = (runtime.settings.root / 'archive').resolve()
    try:
        if not path.resolve().is_relative_to(root):
            return Response(status_code=410)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        file = os.fdopen(fd, 'rb')
        import stat
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode):
            file.close()
            return Response(status_code=410)
    except OSError:
        return Response(status_code=410)
    size, start, end = info.st_size, 0, info.st_size - 1
    code = 200
    if range_header is not None:
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header)
        try:
            if not match or not size or not any(match.groups()):
                raise ValueError
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                if suffix <= 0:
                    raise ValueError
                start, end = max(0, size - suffix), size - 1
            if start >= size or start > end:
                raise ValueError
            code = 206
        except ValueError:
            file.close()
            return Response(status_code=416, headers={'Content-Range': f'bytes */{size}'})
    length = max(0, end - start + 1)
    headers = {'Accept-Ranges': 'bytes', 'Content-Length': str(length)}
    if code == 206:
        headers['Content-Range'] = f'bytes {start}-{end}/{size}'
    def chunks():
        try:
            file.seek(start)
            remaining = length
            while remaining:
                block = file.read(min(64 * 1024, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
        finally:
            file.close()
    return StreamingResponse(chunks(), status_code=code, media_type='audio/mp4', headers=headers)


def static_index():
    base = STATIC.resolve()
    return {path.relative_to(base).as_posix(): path for path in sorted(base.rglob('*'))
            if path.suffix in STATIC_TYPES and path.is_file() and not path.is_symlink()}


def _read_regular(path, limit):
    """Bounded read of a regular file; a final symlink is refused."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise OSError('not a bounded regular file')
        return stream.read()


def _artifact(directory, name):
    """A run artifact only if its metadata says ok and the bytes still match (contract §4.1)."""
    try:
        data = _read_regular(directory / name, ARTIFACT_LIMIT)
        meta = json.loads(_read_regular(artifacts.metadata(directory / name), 1 << 20))
        if meta.get('ok') is not True or meta.get('output_sha256') != hashlib.sha256(data).hexdigest():
            return None
        return json.loads(data)
    except (OSError, ValueError):
        return None


def _seconds(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 1e7 else None


def _text(value, limit=2000):
    return value[:limit] if isinstance(value, str) else None


def _summary_sections(text, spans):
    """'## heading' + bullet lines; [t1, t2] citations become separate evidence links."""
    sections = []
    for line in text.splitlines()[:3000]:
        line = line.strip()
        if not line:
            continue
        if line.startswith('## '):
            heading = line[3:].strip()[:200]
            sections.append({'heading': heading, 'kind': SECTION_KIND.get(heading, 'section'), 'items': []})
            continue
        if not sections:
            continue
        task = re.match(r'[-*]\s+\[([ xX])\]\s+(.*)', line)
        bullet = re.match(r'[-*]\s+(.*)', line)
        cites = []

        def collect(match):
            for ident in re.findall(r't\d+', match[1]):
                if not any(cite['id'] == ident for cite in cites):
                    start, end = spans.get(ident, (None, None))
                    cites.append({'id': ident, 'ok': ident in spans, 'start': start, 'end': end})
            return ''

        body = re.sub(r'\s{2,}', ' ', CITATION.sub(collect, task[2] if task else bullet[1] if bullet else line)).strip()
        sections[-1]['items'].append({'text': body[:2000], 'task': bool(task), 'done': bool(task and task[1] != ' '),
                                      'cites': cites[:20]})
    return sections[:40]


def _find_note(notes, output, row):
    """(path, header properties, state) of the vault note that belongs to this job (contract §7.2)."""
    def read(path):
        try:
            props, _ = notes.parse_note(_read_regular(path, 8 << 20))
        except (OSError, ValueError):
            return None
        mine = (type(props.get('qc_schema')) is int and props['qc_schema'] == 2 and
                props.get('job_id') == row['job_id'] and props.get('source_sha256') == row['sha256'])
        return props if mine else None

    path = Path(row['note_path']) if row['note_path'] else None
    if path is not None and notes.safe_path(output, path):
        props = read(path)
        if props is not None:
            return path, props, 'found'
    try:
        path = notes.find_existing(output, row)
    except notes.NoteConflict:
        return None, {}, 'conflict'
    props = read(path) if path is not None else None
    return (path, props, 'found') if props is not None else (None, {}, 'missing')


def note_view(runtime, job_id):
    """Minutes screen data no /api endpoint serves yet. None for an unknown job."""
    from .. import notes
    from ..language import processing_language
    with closing(store.connect(runtime.db)) as con:
        try:
            row = store.job(con, job_id)
        except KeyError:
            return None
        deleted = store_ops.deleted(con, job_id)
        run = (con.execute('SELECT settings_json FROM runs WHERE run_id=?', (row['current_run_id'],)).fetchone()
               if row['current_run_id'] else None)
    result = {'job_id': row['job_id'], 'found': False}
    root = runtime.settings.root
    directory = root / 'work' / row['job_id'] / 'runs' / str(row['current_run_id'])
    if deleted or run is None or row['legacy'] or not notes.safe_path(root / 'work', directory):
        return result
    turns, corrected = _artifact(directory, 'turns.json'), _artifact(directory, 'corrected.json')
    classification = _artifact(directory, 'classification.json')
    meta = classification.get('meta') if isinstance(classification, dict) else None
    summary, language = _artifact(directory, 'summary.json'), _artifact(directory, 'language.json')
    texts = corrected.get('texts') if isinstance(corrected, dict) else None
    if (not isinstance(turns, list) or not isinstance(texts, list) or len(texts) != len(turns) or
            not isinstance(meta, dict) or not isinstance(summary, dict) or not isinstance(summary.get('text'), str)):
        return result
    lines, spans = [], {}
    for index, (turn, text) in enumerate(zip(turns[:20000], texts)):
        start, end = (_seconds(turn.get('start')), _seconds(turn.get('end'))) if isinstance(turn, dict) else (None, None)
        if start is None or end is None or not isinstance(text, str):
            return result
        ident = f't{index + 1}'
        spans[ident] = (start, end)
        lines.append({'id': ident, 'start': start, 'end': end, 'speaker': _text(turn.get('speaker'), 32), 'text': text[:4000]})
    path, props, state = _find_note(notes, Path(runtime.settings.get('output')), row)
    speakers = []
    labels = meta.get('speakers') if isinstance(meta.get('speakers'), dict) else {}
    for label, who in sorted(labels.items()):
        who = who if isinstance(who, dict) else {}
        name_id = who.get('name_id') if isinstance(who.get('name_id'), str) and who['name_id'] in spans else None
        speakers.append({'label': _text(label, 32), 'role': _text(who.get('role'), 200), 'name': _text(who.get('name'), 200),
                         'name_start': spans[name_id][0] if name_id else None, 'split_suspect': who.get('split_suspect') is True})
    detection = language if isinstance(language, dict) else {}
    detected = (detection.get('top') if detection.get('status') == 'decided' else
                'uncertain' if detection.get('status') == 'uncertain' else None)
    try:
        run_settings = json.loads(run['settings_json'])
        processed = processing_language(run_settings, detection, override=row['language_override'])
    except Exception:
        run_settings, processed = {}, None
    configured = run_settings.get('notes.output_language', 'same') if isinstance(run_settings, dict) else 'same'
    try:
        reasons = json.loads(row['review_reasons'] or '[]')
    except ValueError:
        reasons = []
    reasons = reasons if isinstance(reasons, list) else []
    status = props.get('status') if props.get('status') in ('draft', 'reviewed') else None
    return result | {
        'found': True, 'note_state': state, 'note_path': str(path) if path else None, 'status': status,
        'title': _text(props.get('title'), 300) or _text(meta.get('title'), 300),
        'type': _text(props.get('type'), 40) or _text(meta.get('type'), 40),
        'division': _text(props.get('division'), 40) or _text(meta.get('division'), 40),
        'language': {'detected': detected, 'processed': processed,
                     'note': processed if configured == 'same' else configured},
        'review_reasons': [_text(reason, 200) for reason in reasons if isinstance(reason, str)][:50],
        'speakers': speakers[:50], 'sections': _summary_sections(summary['text'], spans), 'turns': lines}


def _slim_manifest(manifest):
    """The apply result without each note's property mapping (large; the preview already had it)."""
    entries = [{key: entry[key] for key in ('path', 'job_id', 'state') if key in entry} for entry in manifest.get('entries', [])]
    return {key: manifest[key] for key in ('output', 'backup_root', 'backup_dir', 'done', 'conflicts') if key in manifest} | {'entries': entries}


def _note_conflict(exc):
    text = str(exc)
    return {'error': 'note_conflict', 'reason': text.split(':', 1)[0], 'detail': text[:2000]}


def _task_state(future):
    """What became of the last consented migration request (it may outlive its HTTP request)."""
    if not future.done():
        return {'state': 'running'}
    if future.cancelled():
        return {'state': 'failed', 'reason': 'cancelled'}
    failure = future.exception()
    if failure is None:
        return {'state': 'done'}
    return {'state': 'failed', 'reason': _note_conflict(failure)['reason'] if isinstance(failure, NoteConflict) else type(failure).__name__}


def create_app(runtime=None, *, start_runtime=True, sync_factory=integrations.Syncthing,
               provider_registry=providers.registry, auth_clock=time.time):
    if runtime is None:
        from ..serve import Runtime
        runtime = Runtime()
    auth = Auth(runtime.support, runtime.settings.get('server.port'), clock=auth_clock)
    runtime.auth = auth
    idempotency = {}
    idempotency_lock = asyncio.Lock()
    migration_task = []   # the last consented migration request, so a screen can see how it ended

    def migration_api(con, method, data):
        """GET: read-only preview + whether this output vault is migrated. POST {consent: true}: run the
        migration on the executor thread between jobs; 200 with the manifest if it ends within a second,
        else 202 (the screen asks GET again)."""
        settings = runtime.settings
        output = settings.get('output')
        if method == 'POST':
            if set(data) != {'consent'} or data['consent'] is not True:
                raise ValueError('expected {"consent": true}')
            future = runtime.submit(lambda c: migration.migrate(
                c, settings.root, output, apply=True, consent=True, execution_lock_held=True))
            migration_task[:] = [future]
            if not wait([future], timeout=1).done:   # a task that raised TimeoutError itself is not "still running"
                return Response(status_code=202)
            return JSONResponse(_slim_manifest(future.result()))
        return JSONResponse({'preview': migration.migrate(con, settings.root, output),
                             'migrated': store.vault_migrated(con, output),
                             'task': _task_state(migration_task[0]) if migration_task else None})

    @asynccontextmanager
    async def lifespan(app):
        if start_runtime:
            await run_in_threadpool(runtime.start)
        else:
            with closing(store.connect(runtime.db)):
                pass
        from .. import search
        with closing(store.connect(runtime.db)) as con:
            search.bootstrap(con, runtime.settings.root)
        auth.refresh()
        try:
            yield
        finally:
            if start_runtime:
                await run_in_threadpool(runtime.close)
            else:
                auth.close()

    async def bootstrap(request):
        return HTMLResponse(BOOTSTRAP_HTML)

    async def javascript(request):
        return Response(Path(__file__).with_name('bootstrap.js').read_text(), media_type='text/javascript')

    templates = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined)
    static = static_index()

    async def static_file(request):
        path = static.get(request.path_params['name'])
        if path is None:
            return Response(status_code=404)
        return Response(await run_in_threadpool(path.read_bytes), media_type=STATIC_TYPES[path.suffix])

    def page(screen, *, job_id=None, data=None, status=200):
        html = templates.get_template('app.html').render(
            lang=runtime.settings.get('ui.language'), screen=screen, job_id=job_id, data=data)
        return HTMLResponse(html, status)

    def plain_screen(screen):
        async def handler(request):
            return page(screen)
        return handler

    async def setup_screen(request):
        step = request.path_params['step']
        return page(f'setup-{step}') if 1 <= step <= 6 else Response(status_code=404)

    async def note_screen(request):
        job_id = request.path_params['job_id']
        data = await run_in_threadpool(note_view, runtime, job_id)
        if data is None:
            return page('note', job_id=job_id, data={'job_id': job_id, 'found': False, 'unknown': True}, status=404)
        return page('note', job_id=job_id, data=data)

    async def session(request):
        data = await body(request)
        if isinstance(data, Response):
            return data
        if set(data) != {'token'}:
            return JSONResponse({'error': 'expected token'}, 400)
        result = auth.exchange(data['token'])
        if not result:
            return Response(status_code=401)
        sid, csrf = result
        response = Response(status_code=204, headers={'X-CSRF-Token': csrf})
        response.set_cookie(COOKIE, sid, httponly=True, samesite='strict', path='/')
        return response

    async def body(request):
        data = bytearray()
        async for block in request.stream():
            data.extend(block)
            if len(data) > 65536:
                return JSONResponse({'error': 'request too large'}, 413)
        if not data:
            return {}
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'error': 'expected application/json'}, 400)
        try:
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, UnicodeError):
            return JSONResponse({'error': 'expected JSON object'}, 400)

    def sync_status(settings):
        try:
            return sync_factory(settings).folder()
        except (OSError, ValueError, RuntimeError):
            return {'state': 'unavailable'}

    def dispatch(request, data):
        path, method = request.url.path, request.method
        settings = runtime.settings
        with closing(store.connect(runtime.db)) as con:
            try:
                if path == '/api/meetings' and method == 'GET':
                    from .. import agent_read
                    return JSONResponse(agent_read.listing(con, settings.root,
                        since=request.query_params.get('since'), limit=request.query_params.get('limit', 50)))
                if path.startswith('/api/meetings/') and method == 'GET':
                    from .. import agent_read, export
                    include = request.query_params.get('transcript', '1')
                    format = request.query_params.get('format', 'json')
                    if include not in ('0', '1') or format not in ('json', 'md'):
                        raise ValueError('invalid meeting format or transcript flag')
                    job_id = request.path_params['job_id']
                    if format == 'md':
                        return export.download(con, job_id, settings.root, {'format': 'md'}, include_transcript=include == '1')
                    return JSONResponse(agent_read.show(con, settings.root, job_id, include_transcript=include == '1'))
                if path == '/api/search' and method == 'GET':
                    from .. import search
                    return JSONResponse(search.query(con, request.query_params.get('q'), request.query_params.get('limit', 20), request.query_params.get('offset', 0)))
                if path.startswith('/api/jobs/') and request.path_params.get('action') == 'export' and method == 'GET':
                    from .. import export
                    return export.download(con, request.path_params['job_id'], settings.root, request.query_params)
                if path == '/api/session' and method == 'GET':
                    return JSONResponse({'csrf_token': request.scope['qc.session'].csrf})
                if path == '/api/logout' and method == 'POST':
                    auth.logout(request.cookies.get(COOKIE))
                    response = Response(status_code=204)
                    response.delete_cookie(COOKIE, path='/')
                    return response
                if path == '/api/status' and method == 'GET':
                    return JSONResponse(status_snapshot(runtime) | engine_identity(runtime) | {
                        'providers': integrations.provider_status(settings, provider_registry),
                        'sync': sync_status(settings)})
                if path == '/api/update' and method == 'GET':
                    return JSONResponse(runtime.updates.snapshot())
                if path.startswith('/api/update/') and method == 'POST':
                    if data:
                        raise ValueError('expected an empty object')
                    action = request.path_params['action']
                    if action == 'check':
                        return JSONResponse(runtime.updates.check())
                    if action == 'apply':
                        return JSONResponse(runtime.updates.apply(con), 202)
                    if action == 'dismiss':
                        return JSONResponse(runtime.updates.dismiss())
                if path == '/api/jobs' and method == 'GET':
                    limit = int(request.query_params.get('limit', 50))
                    if not 1 <= limit <= 200:
                        raise ValueError('limit must be 1..200')
                    status = request.query_params.get('status')
                    if status and status not in ('skipped', 'queued', 'running', 'retry_wait', 'failed', 'done'):
                        raise ValueError('invalid status')
                    cursor = request.query_params.get('cursor', '')
                    rows = con.execute('SELECT * FROM jobs WHERE job_id>? AND (? IS NULL OR status=?) ORDER BY job_id LIMIT ?',
                                       (cursor, status, status, limit + 1)).fetchall()
                    return JSONResponse({'items': [dict(row) for row in rows[:limit]],
                                         'next_cursor': rows[limit - 1]['job_id'] if len(rows) > limit else None})
                if path.startswith('/api/jobs/'):
                    job_id = request.path_params['job_id']
                    row = store.job(con, job_id)
                    action = request.path_params.get('action')
                    if action == 'convert-note':
                        if method == 'GET':
                            return JSONResponse(conversion.preview(con, settings, job_id))
                        if method == 'POST':
                            if set(data) != {'consent', 'preview_token'}:
                                raise ValueError('expected consent and preview_token')
                            return JSONResponse(conversion.apply(con, settings, job_id, **data))
                    if action in ('speakers', 'transcript'):
                        return overrides.api(con, settings, job_id, action, request.path_params.get('item'), method, data)
                    if action is None and method == 'GET':
                        runs = []
                        for run in con.execute('SELECT * FROM runs WHERE job_id=? ORDER BY started_at,run_id', (job_id,)):
                            item = dict(run)
                            item['stages'] = [dict(stage) for stage in con.execute(
                                'SELECT * FROM stage_runs WHERE run_id=? ORDER BY started_at,seq', (run['run_id'],))]
                            for stage in item['stages']:
                                stage['sent_fields'] = json.loads(stage['sent_fields'] or '[]')
                            runs.append(item)
                        return JSONResponse({'job': dict(row), 'runs': runs})
                    if action == 'audio' and method == 'GET':
                        return audio_response(runtime, con, job_id, request.headers.get('range'))
                    if method == 'POST' and action in ('process', 'include', 'exclude', 'delete-local'):
                        if action == 'delete-local':
                            if data != {'scope': 'processing_data'}:
                                raise ValueError('expected scope processing_data')
                            store_ops.request_delete_local(con, job_id)
                        elif action == 'exclude':
                            if not (row['skip_reason'] == 'user_excluded' or row['exclude_requested']):
                                store.exclude(con, job_id)
                        else:
                            if store_ops.deleted(con, job_id):
                                raise store.Conflict(row['status'])
                            mode = data.get('mode', 'auto') if action == 'process' else 'auto'
                            if mode not in store.MODES:
                                raise ValueError('invalid mode')
                            if action == 'include' and not (row['skip_reason'] == 'user_excluded' or row['status'] == 'queued'):
                                raise store.Conflict(row['status'])
                            if row['status'] == 'queued':
                                return Response(status_code=204)
                            if row['status'] == 'skipped' and row['skip_reason'] in store.POLICY_REASONS:
                                try:
                                    store.request_process(con, job_id, mode)
                                except store.Conflict:
                                    if not intake.promote(con, job_id, mode, settings=settings):
                                        raise store.Conflict(row['status'])
                            else:
                                store.request_process(con, job_id, mode)
                        runtime.wake.set()
                        return Response(status_code=202)
                    if action == 'language' and method == 'PUT':
                        if set(data) != {'override'}:
                            raise ValueError('expected override')
                        store_ops.set_language_override(con, job_id, data['override'])
                        return Response(status_code=204)
                if path == '/api/settings':
                    if method == 'PUT':
                        with runtime.settings_lock:
                            runtime.settings = save(runtime.settings, data)
                        runtime.wake.set()
                    if method in ('GET', 'PUT'):
                        settings = runtime.settings
                        return JSONResponse({'effective': settings.snapshot(), 'file': settings.file_values,
                                             'environment_keys': sorted(settings.environment_keys),
                                             'restart_required': settings.get('server.port') != auth.port})
                if path in ('/api/pause', '/api/resume', '/api/scan') and method == 'POST':
                    if path == '/api/scan':
                        runtime.request_scan()
                    else:
                        store_ops.set_paused(con, path == '/api/pause')
                        runtime.wake.set()
                    return Response(status_code=204)
                if path == '/api/backlog' and method == 'GET':
                    skipped = [dict(row) for row in con.execute("SELECT * FROM jobs WHERE status='skipped' ORDER BY job_id")]
                    try:
                        names = sync_factory(settings).backlog()
                        return JSONResponse({'names': names, 'skipped': skipped, 'inventory': 'partial'})
                    except (OSError, ValueError, RuntimeError):
                        return JSONResponse({'names': [], 'skipped': skipped, 'inventory': 'unavailable'})
                if path == '/api/backlog/request' and method == 'POST':
                    names = data.get('names')
                    if not isinstance(names, list) or not names or any(not backfill.valid_name(name) for name in names):
                        raise ValueError('expected recording names')
                    backfill.request(names, settings=settings)
                    runtime.request_scan()
                    return Response(status_code=202)
                if path == '/api/setup/checks' and method == 'GET':
                    return JSONResponse(integrations.checks(settings.root))
                if path == '/api/setup/vaults' and method == 'GET':
                    return JSONResponse({'items': integrations.vaults()})
                if path == '/api/providers' and method == 'GET':
                    return JSONResponse({'items': integrations.provider_status(settings, provider_registry)})
                if path.startswith('/api/providers/') and method == 'POST':
                    return JSONResponse(integrations.check_provider(settings, request.path_params['name'], provider_registry))
                if path == '/api/sync/pairing' and method == 'GET':
                    return JSONResponse(sync_factory(settings).pairing())
                if path == '/api/sync/pairing/approve' and method == 'POST':
                    sync_factory(settings).approve(data.get('device_id'))
                    return Response(status_code=204)
                if path == '/api/sync/folder' and method == 'GET':
                    return JSONResponse(sync_factory(settings).folder())
                if path == '/api/notes/migration' and method in ('GET', 'POST'):
                    return migration_api(con, method, data)
                return JSONResponse({'error': 'not found'}, 404)
            except KeyError:
                return JSONResponse({'error': 'not found'}, 404)
            except selfupdate.UpdateConflict as exc:
                return JSONResponse({'error': selfupdate.message('not_available', runtime.settings.get('ui.language')),
                                     'reason': exc.reason}, 409)
            except store.Conflict as exc:
                return JSONResponse({'status': exc.status}, 409)
            except LockedSetting as exc:
                return JSONResponse({'field': exc.field, 'error': 'locked setting'}, 409)
            except config.SettingsError as exc:
                return JSONResponse({'field': exc.field, 'error': str(exc)}, 400)
            except NoteConflict as exc:
                return JSONResponse(_note_conflict(exc), 409)
            except (ValueError, TypeError) as exc:
                return JSONResponse({'error': str(exc)}, 400)
            except (OSError, RuntimeError, providers.ProviderError):  # e.g. no Syncthing folder for the inbox
                return JSONResponse({'error': 'local integration unavailable'}, 503)

    async def api(request):
        data = await body(request) if request.method in ('POST', 'PUT') else {}
        if isinstance(data, Response):
            return data
        key = request.headers.get('idempotency-key')
        if key and request.method in ('POST', 'PUT', 'DELETE'):
            if len(key) > 128:
                return JSONResponse({'error': 'idempotency key too long'}, 400)
            cache_key = (request.cookies.get(COOKIE), key)
            signature = hashlib.sha256((request.method + request.url.path + json.dumps(data, sort_keys=True)).encode()).digest()
            async with idempotency_lock:
                now = time.monotonic()
                for old in [item for item, entry in idempotency.items() if entry[2] < now - 86400]:
                    del idempotency[old]
                if cache_key in idempotency:
                    previous, response, _ = idempotency[cache_key]
                    return response if previous == signature else JSONResponse({'error': 'idempotency key reused'}, 409)
                response = await run_in_threadpool(dispatch, request, data)
                idempotency[cache_key] = (signature, response, now)
                return response
        return await run_in_threadpool(dispatch, request, data)

    async def events(request):
        sid = request.cookies.get(COOKIE)
        async def stream():
            previous, sequence = None, 0
            while not runtime.stopping.is_set() and auth.session(sid, touch=False):
                if await request.is_disconnected():
                    break
                snapshot = await run_in_threadpool(status_snapshot, runtime)
                with closing(store.connect(runtime.db)) as con:
                    snapshot['jobs'] = [dict(row) for row in con.execute(
                        'SELECT job_id,status,stage,updated_at FROM jobs ORDER BY job_id')]
                # Elapsed time is derived in the browser, not a state-change event.
                comparable = dict(snapshot)
                comparable.pop('elapsed_sec', None)
                encoded = json.dumps(comparable, sort_keys=True)
                if encoded != previous:
                    sequence += 1
                    yield f'id: {sequence}\nevent: state\ndata: {json.dumps(snapshot)}\n\n'
                    previous = encoded
                else:
                    yield ': keepalive\n\n'
                await asyncio.sleep(0.25)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    routes = [Route('/', bootstrap, methods=['GET']), Route('/bootstrap.js', javascript, methods=['GET']),
              Route('/api/session', session, methods=['POST']), Route('/api/events', events, methods=['GET']),
              Route('/static/{name:path}', static_file, methods=['GET']), Route('/notes/{job_id}', note_screen, methods=['GET']),
              Route('/setup/{step:int}', setup_screen, methods=['GET'])]
    routes += [Route('/' + name, plain_screen(name), methods=['GET'])
               for name in ('home', 'jobs', 'notes', 'backlog', 'settings', 'migrate')]
    for path, methods in (
        ('/api/session', ['GET']), ('/api/logout', ['POST']), ('/api/status', ['GET']),
        ('/api/update', ['GET']), ('/api/update/{action}', ['POST']),
        ('/api/search', ['GET']),
        ('/api/meetings', ['GET']), ('/api/meetings/{job_id}', ['GET']),
        ('/api/jobs', ['GET']), ('/api/jobs/{job_id}', ['GET']),
        ('/api/jobs/{job_id}/{action}/{item}', ['GET', 'PUT', 'POST', 'DELETE']),
        ('/api/jobs/{job_id}/{action}', ['GET', 'POST', 'PUT']),
        ('/api/settings', ['GET', 'PUT']), ('/api/backlog', ['GET']), ('/api/backlog/request', ['POST']),
        ('/api/pause', ['POST']), ('/api/resume', ['POST']), ('/api/scan', ['POST']),
        ('/api/setup/checks', ['GET']), ('/api/setup/vaults', ['GET']), ('/api/providers', ['GET']),
        ('/api/providers/{name}/check', ['POST']), ('/api/sync/pairing', ['GET']),
        ('/api/sync/pairing/approve', ['POST']), ('/api/sync/folder', ['GET']), ('/api/notes/migration', ['GET', 'POST'])):
        routes.append(Route(path, api, methods=methods))
    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(Security, auth=auth)
    app.state.runtime, app.state.auth = runtime, auth
    return app
