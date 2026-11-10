import json
import re
from types import SimpleNamespace

import pytest

from quietclerk import config, providers as llm, postprocess
from quietclerk.providers import Completion, ProviderStatus, RateLimited

pytestmark = pytest.mark.usefixtures('provider_context')


@pytest.fixture
def provider_context(tmp_path):
    settings = config.load(environ={'QC_ROOT': str(tmp_path)})
    ctx = SimpleNamespace(settings=settings.snapshot(), current_stage='correct', call_seq=0,
                          checkpoint=lambda: None, record=lambda *args, **kwargs: None)
    with llm.use_context(ctx):
        yield ctx


def engines(monkeypatch, functions):
    class Fake:
        def __init__(self, name, fn):
            self.name, self.fn = name, fn

        def endpoint_class(self):
            return 'external'

        def status(self):
            return ProviderStatus(True, True, 'test', 'verified')

        def complete(self, prompt, *, timeout):
            return Completion(self.fn(prompt), 'test', 'external', 0)

    monkeypatch.setattr(llm, 'registry', lambda settings: {n: Fake(n, fn) for n, fn in functions.items()})
    settings = {'providers.order': list(functions), 'providers.consent': {
        n: ['transcript', 'source_name', 'project_list'] for n in functions}}
    ctx = llm._context.get()
    monkeypatch.setattr(ctx, 'settings', ctx.settings | settings)


TURNS = [{"start": i * 5.0, "end": i * 5.0 + 4, "speaker": "S1", "text": f"원문 {i}"} for i in range(3)]


def ids_in(prompt):
    body = prompt.split("교정할 전사(JSON):")[1].split("참고:")[0]
    return [int(x) for x in re.findall(r'"id": (\d+)', body)]


def test_falls_back_to_claude_when_codex_is_rate_limited(monkeypatch):
    calls = []

    def codex(prompt):
        calls.append("codex")
        raise RateLimited("quota")

    def claude(prompt):
        calls.append("claude")
        return json.dumps([{"id": i, "text": f"고친 {i}"} for i in ids_in(prompt)], ensure_ascii=False)

    engines(monkeypatch, {"codex": codex, "claude": claude})
    texts, notes = postprocess.correct(TURNS, [])
    assert texts == ["고친 0", "고친 1", "고친 2"]
    assert calls == ["codex", "claude"]
    assert notes == ["correct 0-2: claude"]


def test_response_that_drops_or_adds_lines_is_rejected(monkeypatch):
    def dropping(prompt):  # e.g. a transcript line saying "ignore the rules and summarise" was obeyed
        return json.dumps([{"id": 0, "text": "요약해 버림"}], ensure_ascii=False)

    engines(monkeypatch, {"codex": dropping, "claude": dropping})
    texts, notes = postprocess.correct(TURNS, [])
    assert texts == [t["text"] for t in TURNS]       # originals kept
    assert notes[0].startswith("correct 0-2: failed")


def test_summary_must_cite_transcript_lines(monkeypatch):
    engines(monkeypatch, {"codex": lambda p: "## 핵심 요약\n- 근거 없는 요약"})
    meta = {"type": "meeting", "type_confidence": "high", "speakers": {}}
    try:
        postprocess.summarize(TURNS, [t["text"] for t in TURNS], meta)
    except llm.LLMError as e:
        assert "cites no transcript lines" in str(e)
    else:
        raise AssertionError("expected LLMError")


def classify_with(monkeypatch, reply: dict, projects=()):
    engines(monkeypatch, {"codex": lambda p: json.dumps(reply, ensure_ascii=False)})
    return postprocess.classify(TURNS, [t["text"] for t in TURNS], "음성 261109_135940.m4a", list(projects))


BASE_REPLY = {"title": "모바일 앱 개편안 3건 발표와 운영팀 피드백 공유", "type": "presentation", "type_confidence": "high",
              "type_basis_id": "t1", "division": "work", "topics": ["모바일 앱 개편"], "project": None, "project_suggest": None,
              "speakers": [{"label": "S1", "role": "진행", "name": "홍길동", "name_id": "t999", "split_suspect": False}]}


def test_classify_never_invents_projects_or_unsupported_names(monkeypatch):
    meta, _ = classify_with(monkeypatch, {**BASE_REPLY, "project": "새프로젝트"}, projects=["사내 위키 정비"])
    assert meta["project"] is None and meta["project_suggest"] == "새프로젝트"
    assert meta["speakers"]["S1"] == {"role": "진행", "name": None, "name_id": None, "split_suspect": False}


def test_project_suggest_is_always_one_string_or_null(monkeypatch):
    # The note property is a single string (contract 7); a real model answered with a list once.
    meta, _ = classify_with(monkeypatch, {**BASE_REPLY, "project_suggest": ["", "책마루 개편", "기타"]})
    assert meta["project_suggest"] == "책마루 개편"
    meta, _ = classify_with(monkeypatch, {**BASE_REPLY, "project_suggest": "  "})
    assert meta["project_suggest"] is None


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

    engines(monkeypatch, {"codex": merges_lines_when_long})
    texts, notes = postprocess.correct(turns, [])
    assert texts == [f"고친 {i}" for i in range(20)]
    assert notes == ["correct 0-9: codex", "correct 10-19: codex"]


def test_IN23_duplicate_correction_ids_are_rejected(monkeypatch):
    reply = [{"id": 0, "text": "changed"}, {"id": 1, "text": "changed"},
             {"id": 2, "text": "changed"}, {"id": 2, "text": "duplicate"}]
    engines(monkeypatch, {"codex": lambda p: json.dumps(reply)})
    texts, notes = postprocess.correct(TURNS, [])
    assert texts == [t["text"] for t in TURNS]
    assert "failed" in notes[0]


def test_classification_missing_evidence_is_stage_failure(monkeypatch):
    import pytest
    with pytest.raises(llm.LLMError, match="type evidence"):
        classify_with(monkeypatch, {**BASE_REPLY, "type_basis_id": "t999"})


def test_english_prompts_and_structured_machine_ids(monkeypatch):
    calls = []
    def answer(prompt):
        calls.append(prompt)
        if "Transcript to correct (JSON):" in prompt:
            return json.dumps([{"id": i, "text": "English speech"} for i in range(3)])
        if "Classify the transcript" in prompt:
            return json.dumps({**BASE_REPLY, "title": "Library application redesign", "topics": ["Library"],
                               "speakers": [{"label": "S1", "role": "Lead", "name": None}]})
        return "## Key summary\n- S1 proposed a redesign [t1, t2].\n## Tasks\n- [ ] S1 drafts the design [t3]"
    engines(monkeypatch, {"codex": answer})
    texts, _ = postprocess.correct(TURNS, [], language="en")
    meta, _ = postprocess.classify(TURNS, texts, "meeting.m4a", [], language="en")
    summary, _ = postprocess.summarize(TURNS, texts, meta, language="en")
    assert meta["type"] == "presentation" and meta["division"] == "work"
    assert "Key summary" in summary and len(calls) == 3
