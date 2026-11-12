"""10.8 C/D input policy and evidence (synthetic/demo artifacts only).

Input                         Policy / exercised test
Empty/1/101 chars, C controls  reject 400 / test_query_input_policy
FTS quotes/operators, %/_     literal, no SQL/FTS syntax / test_literal_search
Korean 2 chars, substrings    LIKE / trigram; whitespace significant / same
Unknown/other job IDs         404 or isolated current run / test_boundaries
Traversal / symlink          no outside artifact reads / test_boundaries
Running meeting              read published run only / test_boundaries
Concurrent requests          independent connections; atomic replacement / test_concurrent
srt/vtt/txt/md/docx flags     bounded enums; valid timestamps/OOXML / test_formats
Korean filenames             RFC5987, ASCII fallback; no header controls / same
Demo ko/en                    live loopback HTTP + textutil / test_live_demo

No private recordings, production roots, providers or vault writes are used.
Known limit: spacing is significant ('대출 연장' != '대출연장').
"""
import hashlib
import io
import json
import shutil
import socket
import subprocess
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

import httpx
import pytest
import uvicorn
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from quietclerk import artifacts, cli, config, search, store, store_ops
from quietclerk.bootstrap_file import read_bootstrap
from quietclerk.export import download
from quietclerk.serve import Runtime
from quietclerk.server import create_app


def put(directory, name, value):
    path = directory / name
    artifacts.write_json(path, value)
    artifacts.write_json(artifacts.metadata(path), {'ok': True, 'output_sha256': artifacts.sha256(path)})


def seed(root, job_id='ko', demo=None, envelope=False):
    with closing(store.connect(root / 'state.sqlite3')) as con:
        search.ensure_schema(con)
        store.add_job(con, job_id, hashlib.sha256(job_id.encode()).hexdigest(), '가상 회의.m4a', None, 600, recorded_at='20261110-100000')
        con.execute("INSERT INTO runs(run_id,job_id,mode,settings_json,consent_json,status,started_at) VALUES(?,?,'auto','{}','{}','done',0)", ('run-' + job_id, job_id))
        con.execute("UPDATE jobs SET status='done',current_run_id=? WHERE job_id=?", ('run-' + job_id, job_id))
    directory = root / 'work' / job_id / 'runs' / ('run-' + job_id)
    directory.mkdir(parents=True)
    if demo:
        source = Path(__file__).parents[1] / 'docs/examples' / demo / 'work'
        for target, name in [('turns.json', 'turns.json'), ('corrected.json', 'correct.json'), ('classification.json', 'classify.json'), ('summary.json', 'summarize.json')]:
            value = json.loads((source / name).read_text())
            put(directory, target, {'turns': value} if envelope and target == 'turns.json' else value)
    else:
        put(directory, 'turns.json', [{'start': 1.234, 'end': 62.567, 'speaker': 'S1', 'text': 'raw'}])
        put(directory, 'corrected.json', {'texts': ['대출연장 대출 연장 인용 "OR" 100% a_b']})
        put(directory, 'classification.json', {'meta': {'title': '한글 회의 제목'}})
        put(directory, 'summary.json', {'text': 'S1 summary'})
    return directory


@pytest.fixture
def fixture(tmp_path):
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path)})
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    seed(tmp_path)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    base = f"http://127.0.0.1:{settings.get('server.port')}"
    with TestClient(app, base_url=base) as client:
        assert client.get('/api/search?q=대출').status_code == 401
        token = read_bootstrap(runtime.support)['token']
        assert client.post('/api/session', json={'token': token}, headers={'Origin': base}).status_code == 204
        yield tmp_path, client, app


@pytest.mark.parametrize('q', ['', ' ', 'a', '가' * 101, '가\x00나', '가\u200b나'])
def test_query_input_policy(fixture, q):
    _, client, _ = fixture
    assert client.get('/api/search', params={'q': q}).status_code == 400


def test_literal_search(fixture):
    root, client, _ = fixture
    # Spacing never matters: ASR and people space Korean words differently.
    for q in ['대출', '출연', '대출연장', '대출 연장', '대출  연장', '대 출', '"OR"', '100%', 'a_b']:
        response = client.get('/api/search', params={'q': q})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['total'] == 1, (q, result)
        assert any(s['hit'] for s in result['items'][0]['snippet'])
    for q in ['" OR *', 'NOT NEAR()', '없는말']:
        assert client.get('/api/search', params={'q': q}).json()['total'] == 0
    for params in [{'limit': 0}, {'offset': -1}, {'limit': 'bad'}]:
        assert client.get('/api/search', params={'q': '대출', **params}).status_code == 400
    schema = json.loads((Path(__file__).parents[1] / 'quietclerk/server/schema.json').read_text())
    Draft202012Validator({'$ref': '#/$defs/Search', '$defs': schema['$defs']}).validate(client.get('/api/search', params={'q': '대출'}).json())
    with closing(store.connect(root / 'state.sqlite3')) as con:
        search.reindex(con, 'ko', root)
        search.reindex(con, 'ko', root)
        assert search.query(con, '대출')['total'] == 1
        assert search.query(con, '대출', offset=1)['items'] == []
        store_ops.request_delete_local(con, 'ko')
        assert search.query(con, '대출')['total'] == 0
        search.reindex(con, 'ko', root)
        assert con.execute('SELECT COUNT(*) FROM search').fetchone()[0] == 0
    assert client.get('/api/jobs/ko/export').status_code == 404


def test_edits_and_confirmed_names(fixture):
    root, client, _ = fixture
    with closing(store.connect(root / 'state.sqlite3')) as con:
        original = search.meeting(con, 'ko', root)['lines'][0]['text']
        con.execute('INSERT INTO transcript_edits VALUES(?,?,?,?,0)', ('ko', 't1', '수정 내용', hashlib.sha256(original.encode()).hexdigest()))
        con.execute("INSERT INTO speaker_overrides VALUES('ko','S1','확정이름',1,NULL,0)")
        search.reindex(con, 'ko', root)
        assert search.query(con, '수정')['items'][0]['speaker'] == '확정이름'
        data = download(con, 'ko', root, {'format': 'txt'}).body.decode()
        assert '확정이름: 수정 내용' in data and '확정이름 summary' in data
        con.execute("UPDATE transcript_edits SET original_sha256='stale'")
        assert search.meeting(con, 'ko', root)['lines'][0]['text'] == original
        con.execute("UPDATE speaker_overrides SET confirmed=0")
        assert search.meeting(con, 'ko', root)['lines'][0]['name'] is None
        con.execute("INSERT INTO speaker_overrides VALUES('ko','S2','병합이름',1,NULL,0)")
        con.execute("UPDATE speaker_overrides SET merged_into='S2' WHERE label='S1'")
        assert search.meeting(con, 'ko', root)['lines'][0]['name'] == '병합이름'
        assert search.meeting(con, 'ko', root)['summary'] == '병합이름 summary'


def test_boundaries(fixture):
    root, client, _ = fixture
    assert client.get('/api/jobs/unknown/export').status_code == 404
    for path in ['/api/jobs/..%2Foutside/export', '/api/jobs/%2E%2E/export']:
        assert client.get(path).status_code == 404
    with closing(store.connect(root / 'state.sqlite3')) as con:
        con.execute("UPDATE jobs SET status='running' WHERE job_id='ko'")
        assert search.meeting(con, 'ko', root)['lines']
        seed(root, 'en')
        con.execute("UPDATE jobs SET current_run_id='run-en' WHERE job_id='ko'")
        with pytest.raises(ValueError, match='belong'):
            search.meeting(con, 'ko', root)
        con.execute("UPDATE jobs SET current_run_id='run-ko' WHERE job_id='ko'")
        directory = root / 'work/ko/runs/run-ko'
        target = directory / 'corrected.json'
        target.rename(directory / 'saved.json')
        target.symlink_to(directory / 'saved.json')
        with pytest.raises(OSError):
            search.meeting(con, 'ko', root)
        target.unlink()
        shutil.rmtree(directory)
        directory.symlink_to(root / 'work/en/runs/run-en', target_is_directory=True)
        with pytest.raises(ValueError, match='unsafe'):
            search.meeting(con, 'ko', root)
        directory.unlink()
        work = root / 'work'
        work.rename(root / 'moved-work')
        work.symlink_to(root / 'moved-work', target_is_directory=True)
        with pytest.raises(ValueError, match='unsafe'):
            search.meeting(con, 'ko', root)


def test_formats(fixture, tmp_path):
    root, client, _ = fixture
    for format in ['srt', 'vtt', 'txt', 'md', 'docx']:
        response = client.get('/api/jobs/ko/export', params={'format': format})
        assert response.status_code == 200, response.text
        header = response.headers['content-disposition']
        assert header.startswith('attachment; filename=') and "filename*=UTF-8''" in header
        assert '\r' not in header and '\n' not in header
        assert unquote(header).endswith(f'2026-11-10_1000_한글_회의_제목.{format}')
        if format == 'srt':
            assert '1\n00:00:01,234 --> 00:01:02,567\n' in response.text
        elif format == 'vtt':
            assert response.text.startswith('WEBVTT\n\n1\n00:00:01.234 --> 00:01:02.567\n')
        elif format == 'docx':
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert set(archive.namelist()) == {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'}
                for name in archive.namelist():
                    ElementTree.fromstring(archive.read(name))
        elif format == 'md':
            assert response.text.startswith('# 한글 회의 제목')
        else:
            assert '[00:01] S1:' in response.text
    without = client.get('/api/jobs/ko/export?names=0&timestamps=0').text
    assert '[00:01]' not in without and 'S1:' not in without
    for params in [{'format': '../../txt'}, {'format': ''}, {'names': 'yes'}, {'timestamps': '2'}]:
        assert client.get('/api/jobs/ko/export', params=params).status_code == 400
    with closing(store.connect(root / 'state.sqlite3')) as con:
        directory = root / 'work/ko/runs/run-ko'
        put(directory, 'classification.json', {'meta': {'title': '한글\\r\\nX-Injected: yes/../../\"'}})
        response = download(con, 'ko', root, {'format': 'txt'})
        assert '\\r' not in response.headers['content-disposition']
        assert '\\n' not in response.headers['content-disposition']
        assert response.headers['content-disposition'].isascii()
    assert not (root / 'output').exists()


def test_memo_export_filename_has_time_before_prefix(fixture):
    root, client, _ = fixture
    put(root / 'work/ko/runs/run-ko', 'classification.json',
        {'meta': {'title': '설계 생각', 'type': 'memo'}})
    response = client.get('/api/jobs/ko/export', params={'format': 'md'})
    assert response.status_code == 200
    assert unquote(response.headers['content-disposition']).endswith(
        '2026-11-10_1000_메모_설계_생각.md')


def test_concurrent(fixture):
    root, _, _ = fixture
    def request(index):
        with closing(store.connect(root / 'state.sqlite3')) as con:
            if index % 2:
                search.reindex(con, 'ko', root)
            else:
                assert search.query(con, '대출')['total'] == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(request, range(20)))


def test_live_demo(tmp_path, capsys):
    """Actual uvicorn/HTTP and macOS textutil, both public fictional demos."""
    seed(tmp_path, 'ko', 'demo-meeting')
    seed(tmp_path, 'en', 'demo-meeting-en', envelope=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    settings = config.load(tmp_path / 'settings.toml', environ={'QC_ROOT': str(tmp_path), 'QC_PORT': str(port)})
    runtime = Runtime(settings, support=tmp_path / 'support', label_check=lambda _: False)
    app = create_app(runtime, start_runtime=False, provider_registry=lambda _: {})
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        base = f'http://127.0.0.1:{port}'
        with httpx.Client(base_url=base) as client:
            token = read_bootstrap(runtime.support)['token']
            assert client.post('/api/session', json={'token': token}, headers={'Origin': base}).status_code == 204
            for job, q in [('ko', '대출 연장'), ('en', 'the')]:
                result = client.get('/api/search', params={'q': q})
                assert result.status_code == 200 and result.json()['total'] > 0
                for format in ['srt', 'vtt', 'txt', 'md', 'docx']:
                    response = client.get(f'/api/jobs/{job}/export', params={'format': format})
                    assert response.status_code == 200
                    if format == 'docx':
                        path = tmp_path / (job + '.docx')
                        path.write_bytes(response.content)
                        if shutil.which('textutil') is None:  # macOS only; CI runs on Linux
                            continue
                        opened = subprocess.run(['textutil', '-convert', 'txt', '-stdout', str(path)], capture_output=True, check=True)
                        assert len(opened.stdout.decode('utf-8')) > 100
        app.state.auth.refresh()
        assert cli.main(['--support', str(runtime.support), 'search', '대출']) == 0
        assert '책마루' in capsys.readouterr().out
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_word_and_text_exports_are_readable_outside_obsidian():
    """Real export (2026-11-10) showed raw '## 핵심 요약' and [t3] in Word: outside Obsidian
    line IDs mean nothing, so they become times and headings become headings."""
    from quietclerk import export
    lines = [{'id': 't3', 'start': 23.0}, {'id': 't16', 'start': 142.0}]
    out = export._readable('## 핵심 요약\n- 문의가 38%였다. [t3]\n- 시안 [[#^t16|02:22]] [t3, t16]\n> [!warning] 확인 필요\n> - 숫자', lines)
    assert '[t' not in out and '(00:23)' in out and '(00:23, 02:22)' in out and '>' not in out
    xml = export._paragraph('## 핵심 요약') + export._paragraph('- [ ] 할 일 <b>')
    assert '<w:b/>' in xml and '핵심 요약' in xml and '## ' not in xml and '• 할 일 &lt;b&gt;' in xml
