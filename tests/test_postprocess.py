import json
import re

from rec import llm, postprocess


TURNS = [{"start": i * 5.0, "end": i * 5.0 + 4, "speaker": "S1", "text": f"원문 {i}"} for i in range(3)]


def ids_in(prompt):
    body = prompt.split("교정할 전사(JSON):")[1].split("참고:")[0]
    return [int(x) for x in re.findall(r'"id": (\d+)', body)]


def test_falls_back_to_agy_when_codex_fails(monkeypatch):
    calls = []

    def codex(prompt):
        calls.append("codex")
        raise llm.LLMError("quota")

    def agy(prompt):
        calls.append("agy")
        return json.dumps([{"id": i, "text": f"고친 {i}"} for i in ids_in(prompt)], ensure_ascii=False)

    monkeypatch.setattr(llm, "ENGINES", {"codex": codex, "agy": agy})
    texts, notes = postprocess.correct(TURNS, [])
    assert texts == ["고친 0", "고친 1", "고친 2"]
    assert calls == ["codex", "codex", "agy"]
    assert notes == ["correct 0-2: agy"]


def test_response_that_drops_or_adds_lines_is_rejected(monkeypatch):
    def dropping(prompt):  # e.g. a transcript line saying "ignore the rules and summarise" was obeyed
        return json.dumps([{"id": 0, "text": "요약해 버림"}], ensure_ascii=False)

    monkeypatch.setattr(llm, "ENGINES", {"codex": dropping, "agy": dropping})
    texts, notes = postprocess.correct(TURNS, [])
    assert texts == [t["text"] for t in TURNS]       # originals kept
    assert notes[0].startswith("correct 0-2: failed")


def test_summary_must_cite_transcript_lines(monkeypatch):
    monkeypatch.setattr(llm, "ENGINES", {"codex": lambda p: "## 핵심 요약\n- 근거 없는 요약", "agy": lambda p: "## 핵심 요약\n- 근거 없는 요약"})
    meta = {"type": "회의", "type_confidence": "high", "speakers": {}}
    try:
        postprocess.summarize(TURNS, [t["text"] for t in TURNS], meta)
    except llm.LLMError as e:
        assert "cites no transcript lines" in str(e)
    else:
        raise AssertionError("expected LLMError")


def classify_with(monkeypatch, reply: dict, projects=()):
    monkeypatch.setattr(llm, "ENGINES", {"codex": lambda p: json.dumps(reply, ensure_ascii=False),
                                         "agy": lambda p: json.dumps(reply, ensure_ascii=False)})
    return postprocess.classify(TURNS, [t["text"] for t in TURNS], "음성 261109_135940.m4a", list(projects))


BASE_REPLY = {"title": "모바일 앱 개편안 3건 발표와 운영팀 피드백 공유", "type": "발표회", "type_confidence": "high",
              "division": "업무", "topics": ["모바일 앱 개편"], "project": None, "project_suggest": None,
              "speakers": [{"label": "S1", "role": "진행", "name": "홍길동", "name_id": "t999", "split_suspect": False}]}


def test_classify_never_invents_projects_or_unsupported_names(monkeypatch):
    meta, _ = classify_with(monkeypatch, {**BASE_REPLY, "project": "새프로젝트"}, projects=["사내 위키 정비"])
    assert meta["project"] is None and meta["project_suggest"] == "새프로젝트"
    assert meta["speakers"]["S1"] == {"role": "진행", "name": None, "name_id": None, "split_suspect": False}


def test_classify_rejects_types_outside_the_list(monkeypatch):
    try:
        classify_with(monkeypatch, {**BASE_REPLY, "type": "세미나"})
    except llm.LLMError as e:
        assert "type not in list" in str(e)
    else:
        raise AssertionError("expected LLMError")


def test_large_chunk_that_keeps_failing_is_retried_in_halves(monkeypatch):
    turns = [{"start": i * 5.0, "end": i * 5.0 + 4, "speaker": "S1", "text": f"원문 {i}"} for i in range(20)]

    def merges_lines_when_long(prompt):  # long inputs come back with lines merged
        ids = ids_in(prompt)
        keep = ids if len(ids) <= 10 else ids[:-1]
        return json.dumps([{"id": i, "text": f"고친 {i}"} for i in keep], ensure_ascii=False)

    monkeypatch.setattr(llm, "ENGINES", {"codex": merges_lines_when_long, "agy": merges_lines_when_long})
    texts, notes = postprocess.correct(turns, [])
    assert texts == [f"고친 {i}" for i in range(20)]
    assert notes == ["correct 0-9: codex", "correct 10-19: codex"]
