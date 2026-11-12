from datetime import datetime

import pytest

from quietclerk import notes, render


def test_IN24_citations_keep_unknown_ids_and_review_reasons():
    reasons = []
    out = render.link_citations('근거 [t1, t12345]. 없는 줄 [t777].', {'t1': 0, 't12345': 140.5}, reasons)
    assert out == '근거 [[#^t1|00:00]] [[#^t12345|02:20]]. 없는 줄 [?t777].'
    assert reasons == ['unknown_citation:t777']
    assert render.line_id(0) == 't1' and render.line_id(1000) == 't1001'


def test_note_name_strips_unsafe_characters():
    when = datetime(2026, 11, 9, 13, 59, 40)
    assert render.note_name(when, '모바일 앱 개편: 성과 #공유', '발표회') == '2026-11-09_1359_모바일_앱_개편_성과_공유.md'


def test_find_requires_all_db_identity_fields_and_excludes_links(tmp_path):
    job = {'job_id': 'job', 'sha256': 'abc', 'note_path': str(tmp_path / 'outside.md')}
    text = render.frontmatter({'qc_schema': 2, 'job_id': 'job', 'source_sha256': 'abc'})
    (tmp_path / 'old.md').write_text('---\njob_id: job\n---\n')
    assert notes.find_existing(tmp_path, job) is None
    path = tmp_path / 'renamed.md'
    path.write_text(text)
    assert notes.find_existing(tmp_path, job) == path
    (tmp_path / 'link.md').symlink_to(path)
    assert notes.find_existing(tmp_path, job) == path
    (tmp_path / 'copy.md').write_text(text)
    with pytest.raises(notes.NoteConflict, match='note_conflict'):
        notes.find_existing(tmp_path, job)


def test_projects_read_only_neutral_user_values(tmp_path):
    (tmp_path / 'a.md').write_text('---\nproject: ["[[사내 위키 정비]]"]\n---\n')
    (tmp_path / 'b.md').write_text('---\nproject: [unassigned]\n---\n')
    assert render.known_projects(tmp_path) == ['[[사내 위키 정비]]']


def test_speaker_count_ignores_fragments():
    assert render.speaker_count([{'speaker': 'S1'}, {'speaker': 'S2'}, {'speaker': 'S1'}],
                                ['이 2기는 이제 다양한 주제로 포럼을 진행해 왔습니다', '성과 공개를', '시작하도록 하겠습니다']) == 1


def test_adjacent_citations_are_separated():
    assert render.link_citations('x [t1][t2]', {'t1': 0, 't2': 60}) == 'x [[#^t1|00:00]] [[#^t2|01:00]]'


def test_malformed_yaml_duplicate_keys_and_alias_cycles_rejected():
    for data in (b'---\ntitle: a\ntitle: b\n---\n', b'---\na: &a [*a]\n---\n', b'---\na: [\n---\n'):
        with pytest.raises(notes.NoteConflict):
            notes.parse_note(data)


def test_user_body_bytes_stay_exact_and_markers_are_strict():
    body, _ = notes.new_body('old', 'old generated', [], 'en')
    body = body.replace(b'## Tasks\n', b'## Tasks\r\n- [x] User task\r\n') + '메모\r\n\t  bytes  '.encode()
    merged = notes.merge_body(body, 'new', 'new generated', ['proposed'], 'en')
    assert b'## Tasks\r\n- [x] User task\r\n' in merged
    assert merged.endswith('메모\r\n\t  bytes  '.encode())
    assert b'Newly proposed tasks' in merged
    record = render.RECORD_HEADINGS['en'].encode()
    for invalid in (body.replace(record, b''), body.replace(b'## Notes', b'## Memo'),
                    body.replace(b'## Tasks', record)):
        with pytest.raises(notes.NoteConflict):
            notes.merge_body(invalid, 'new', 'new', [], 'en')


def test_bases_v2_never_overwrites_old_view(tmp_path):
    old = tmp_path / '회의록.base'
    old.write_bytes(b'user base')
    render.ensure_base(tmp_path)
    assert old.read_bytes() == b'user base'
    view = (tmp_path / render.BASE_FILE).read_text()
    assert 'qc_schema == 2' in view and 'displayName: 제목' in view and 'formula.type_ko' in view


def test_speaker_table_link_and_marker_layout_render_in_obsidian_markdown():
    # A real note (2026-11-10) showed a broken speaker table: the name cell's
    # [[#^t99|04:53]] link split the row; tasks showed 32-hex block IDs.
    import re
    job = {'source_name': 'meeting.m4a', 'sha256': 'abc', 'job_id': '20261105-083634-abc', 'duration_sec': 60}
    turns = [{'start': 0, 'end': 4, 'speaker': 'S1', 'text': '안녕하세요 홍길동입니다'}]
    meta = {'title': '회의', 'type': 'meeting', 'type_confidence': 'high',
            'speakers': {'S1': {'role': '진행 | 소개', 'name': '홍길동', 'name_id': 't1'}}}
    text = render.render(job, datetime(2026, 11, 5, 8, 36), turns, [turns[0]['text']], meta,
                         '## 핵심 요약\n- 소개 [t1]\n## 할 일\n- [ ] S1 자료 공유 [t1]', [], {}, datetime(2026, 11, 5, 9))
    row = next(line for line in text.splitlines() if line.startswith('| S1 '))
    assert len(re.split(r'(?<!\\)\|', row)) == 5  # 3 cells between 4 unescaped pipes
    assert ' ^task-1\n' in text and not re.search(r'\^task-[0-9a-f]{32}', text)
    # No comment markers at all: Obsidian shows them in Live Preview (user report 2026-11-10).
    assert '<!--' not in text and '%%' not in text
    assert text.index('## 할 일') < text.index('## 회의 내용') < text.index('## 메모')


def test_model_text_cannot_fake_the_record_boundaries():
    body, _ = notes.new_body('info', 'summary\n## 메모\nmore\n## 회의 내용', [], 'ko')
    assert notes.record_span(body)  # still exactly one record heading and a real notes heading after it
    assert body.count(b'\n## \xeb\xa9\x94\xeb\xaa\xa8\n') == 1


def test_quotes_stay_readable_while_html_is_neutralised():
    # English demo (2026-11-10): "Let's" became "Let&#x27;s" in every transcript line.
    assert render.safe_text("Let's say \"hi\" <b>") == "Let's say \"hi\" &lt;b&gt;"
    assert render.safe_summary('- He said "ok" <img src=x>') == '- He said "ok" &lt;img src=x&gt;'
