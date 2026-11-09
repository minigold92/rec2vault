from datetime import datetime

from rec import render


def test_citations_become_line_links_and_unknown_ids_are_dropped():
    starts = {"t001": 0.0, "t002": 140.5}
    out = render.link_citations("1팀이 제안함 [t002]. 근거 둘 [t001, t002]. 없는 줄 [t777].", starts)
    assert out == "1팀이 제안함 [[#^t002|02:20]]. 근거 둘 [[#^t001|00:00]] [[#^t002|02:20]]. 없는 줄 ."


def test_note_name_uses_title_and_strips_link_breaking_characters():
    when = datetime(2026, 11, 9, 13, 59, 40)
    assert render.note_name(when, "모바일 앱 개편: 성과 #공유", "발표회") == "2026-11-09_모바일_앱_개편_성과_공유_1359.md"
    assert render.note_name(when, None, "발표회") == "2026-11-09_발표회_1359.md"


def test_existing_note_is_found_by_job_id_in_either_format(tmp_path):
    (tmp_path / "old.md").write_text("---\njob_id: 20261109-135940-6afa73e3\n---\n")
    (tmp_path / "renamed by user.md").write_text("---\n처리_작업ID: 20261103-135921-e4cfa573\n---\n")
    assert render.find_existing(tmp_path, "20261109-135940-6afa73e3") == (tmp_path / "old.md", False)
    assert render.find_existing(tmp_path, "20261103-135921-e4cfa573") == (tmp_path / "renamed by user.md", True)


def test_projects_are_collected_only_from_user_set_values(tmp_path):
    (tmp_path / "a.md").write_text('---\n프로젝트:\n  - "[[사내 위키 정비]]"\n상태: 검토함\n---\n')
    (tmp_path / "b.md").write_text('---\n프로젝트:\n  - "미분류"\n상태: AI초안\n---\n')
    assert render.known_projects(tmp_path) == ["사내 위키 정비"]


def test_speaker_count_ignores_fragment_speakers():
    turns = [{"speaker": "S1"}, {"speaker": "S2"}, {"speaker": "S1"}]
    texts = ["이 2기는 이제 다양한 주제로 포럼을 진행해 왔습니다", "성과 공개를", "시작하도록 하겠습니다"]
    assert render.speaker_count(turns, texts) == 1


def test_adjacent_citations_are_separated():
    assert render.link_citations("x [t001][t002]", {"t001": 0.0, "t002": 60.0}) == "x [[#^t001|00:00]] [[#^t002|01:00]]"
