"""Obsidian note: Korean properties, content title, summary callouts, line-linked evidence, transcript.

Layout and property keys follow docs/minutes-design.md (§3, §4, §6).
"""
import json
import re
from datetime import datetime
from pathlib import Path

from .transcript import stamp

BASE_FILE = "회의록.base"
BASE_TEMPLATE = """filters:
  and:
    - file.ext == "md"
    - file.hasTag("회의록")
views:
  - type: table
    name: 최근 회의록
    order:
      - file.name
      - 날짜
      - 유형
      - 구분
      - 프로젝트
      - 길이분
      - 상태
    sort:
      - property: 녹음시작
        direction: DESC
  - type: table
    name: 검토 대기
    filters:
      and:
        - 'note["상태"] == "AI초안"'
    order:
      - file.name
      - 날짜
      - 유형
      - 검토필요
    sort:
      - property: 녹음시작
        direction: DESC
  - type: table
    name: 유형별
    groupBy:
      property: 유형
      direction: ASC
    order:
      - file.name
      - 날짜
      - 길이분
"""


def line_id(i: int) -> str:
    return f"t{i + 1:03d}"


def note_name(recorded: datetime, title: str | None, fallback: str) -> str:
    slug = re.sub(r"\s+", "_", (title or fallback).strip())
    slug = re.sub(r'[\\/:*?"<>|#^\[\]%]', "", slug)
    return f"{recorded:%Y-%m-%d}_{slug}_{recorded:%H%M}.md"


def find_existing(out_dir: Path, job_id: str):
    """(path, is_current_format) of the note already written for this job, or (None, False)."""
    if not out_dir.is_dir():
        return None, False
    for p in out_dir.glob("*.md"):
        head = p.read_text(encoding="utf-8", errors="replace")[:4000]
        if re.search(rf"^처리_작업ID: {re.escape(job_id)}$", head, re.M):
            return p, True
        if re.search(rf"^job_id: {re.escape(job_id)}$", head, re.M):
            return p, False
    return None, False


def known_projects(out_dir: Path) -> list[str]:
    """Projects the user has set on earlier notes (anything other than 미분류)."""
    found = set()
    for p in out_dir.glob("*.md") if out_dir.is_dir() else []:
        head = p.read_text(encoding="utf-8", errors="replace")[:4000]
        m = re.search(r"^프로젝트:\s*(.*?)(?=^\S)", head, re.M | re.S)
        if not m:
            continue
        for v in re.findall(r'"?\[\[([^\]|]+)(?:\|[^\]]*)?\]\]"?|^\s*-\s*"?([^"\n\[\]]+)"?\s*$', m.group(1), re.M):
            name = (v[0] or v[1]).strip()
            if name and name != "미분류":
                found.add(name)
    return sorted(found)


class _Raw(str):
    """A property value written without quotes (dates, ids)."""


def _yaml(v) -> str:
    if isinstance(v, _Raw):
        return str(v)
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[]" if not v else "\n" + "\n".join(f"  - {_yaml(x)}" for x in v)
    return json.dumps(str(v), ensure_ascii=False)  # JSON strings are valid YAML scalars


def frontmatter(props: dict) -> str:
    return "---\n" + "\n".join(f"{k}: {_yaml(v)}" for k, v in props.items()) + "\n---\n"


def link_citations(text: str, starts: dict) -> str:
    """[t012] / [t012, t013] → [[#^t012|02:20]] links; ids that are not in the transcript are dropped."""
    def one(m):
        ids = re.findall(r"t\d{3}", m.group(0))
        links = [f"[[#^{i}|{stamp(starts[i])}]]" for i in ids if i in starts]
        return " ".join(links)
    return re.sub(r"\]\](?=\[\[#\^)", "]] ", re.sub(r"\[(?:t\d{3}(?:\s*,\s*)?)+\]", one, text))


def _callout(kind: str, title: str, body: str) -> str:
    lines = [l for l in body.strip("\n").splitlines()]
    return "\n".join([f"> [!{kind}] {title}"] + [f"> {l}" if l.strip() else ">" for l in lines])


def shape_summary(summary: str) -> str:
    """Turn the 핵심 요약 and 확인 필요 sections into callouts; leave the rest as headed sections."""
    parts = re.split(r"(?m)^## ", summary.strip())
    out = []
    for part in parts:
        if not part.strip():
            continue
        head, _, body = part.partition("\n")
        head = head.strip()
        if head.startswith("핵심 요약"):
            out.append(_callout("summary", "핵심 요약", body))
        elif head.startswith("확인 필요"):
            out.append(_callout("warning", "확인 필요", body))
        elif body.strip():
            out.append(f"## {head}\n{body.rstrip()}")
    return "\n\n".join(out)


def speaker_count(turns, texts, min_chars=20) -> int:
    chars: dict = {}
    for t, x in zip(turns, texts):
        chars[t["speaker"]] = chars.get(t["speaker"], 0) + len(re.sub(r"\s", "", x))
    return sum(1 for v in chars.values() if v >= min_chars)


def render(job, recorded: datetime, turns, texts, meta: dict | None, summary: str | None,
           notes: list[str], engines: dict, processed_at: datetime) -> str:
    meta = meta or {}
    starts = {line_id(i): t["start"] for i, t in enumerate(turns)}
    title = meta.get("title") or f"{recorded:%Y-%m-%d %H:%M} {meta.get('type') or '녹음'}"
    speakers = meta.get("speakers") or {}
    n_speakers = speaker_count(turns, texts)
    review = (summary is None or "## 확인 필요" in summary or meta.get("type_confidence") != "high"
              or any("failed" in n for n in notes))
    props = {
        "aliases": [title, Path(job["source_name"]).stem],
        "구분": meta.get("division") or "업무",
        "유형": meta.get("type") or "기타",
        "주제": meta.get("topics") or [],
        "프로젝트": [meta["project"]] if meta.get("project") else ["미분류"],
        "프로젝트_제안": meta.get("project_suggest"),
        "참석자": [],
        "화자": [f"{lbl}: " + " · ".join(x for x in (s.get("name") and f"{s['name']}(추정)", s.get("role")) if x)
                 for lbl, s in sorted(speakers.items(), key=lambda kv: int(kv[0][1:])) if s.get("name") or s.get("role")],
        "tags": ["회의록"],
        "날짜": f"{recorded:%Y-%m-%d}",
        "녹음시작": f"{recorded:%Y-%m-%dT%H:%M:%S}",
        "길이분": round((job["duration_sec"] or 0) / 60, 1),
        "화자수": n_speakers,
        "상태": "AI초안",
        "검토필요": review,
        "원본파일": job["source_name"],
        "원본해시": job["sha256"],
        "처리_작업ID": job["job_id"],
        "처리_전사": engines.get("transcribe", []),
        "처리_후처리": engines.get("postprocess") or None,
        "처리일시": f"{processed_at:%Y-%m-%dT%H:%M:%S}",
        "처리_기록": notes,
    }
    for k in ("날짜", "녹음시작", "처리일시", "처리_작업ID"):
        props[k] = _Raw(props[k])  # unquoted so Obsidian reads dates as dates

    info = [f"{meta.get('type') or '기타'}" + (" (유형 판별 불확실)" if meta.get("type_confidence") == "low" else ""),
            f"{props['길이분']}분", f"화자 {n_speakers}명", f"원본 `{job['source_name']}`"]
    out = [frontmatter(props), f"# {title}", "", _callout("info", "개요", " · ".join(info))]

    rows = []
    for lbl, s in sorted(speakers.items(), key=lambda kv: int(kv[0][1:])):
        if not (s.get("role") or s.get("name") or s.get("split_suspect")):
            continue
        name = f"{s['name']}(추정) [[#^{s['name_id']}|근거]]" if s.get("name") and s.get("name_id") in starts else ""
        role = (s.get("role") or "") + (" · 분리 오류 의심" if s.get("split_suspect") else "")
        rows.append(f"| {lbl} | {role} | {name} |")
    if rows:
        out += ["", "| 화자 | 역할 | 이름 |", "|---|---|---|"] + rows

    out.append("")
    if summary:
        out.append(link_citations(shape_summary(summary), starts))
    else:
        out.append(_callout("warning", "요약 대기", "요약을 아직 만들지 못했다. 다음 주기에 다시 시도한다. 아래 대화록은 로컬 전사 결과다."))

    out += ["", "## 전체 대화록", "", "> AI 전사 초안이다. S1… 은 자동 구분한 화자 번호이며 실제 이름이 아니다.", ""]
    for i, (t, x) in enumerate(zip(turns, texts)):
        safe = x.replace("[[", "[ [").replace("]]", "] ]").replace("^", "ˆ")
        out += [f"**[{stamp(t['start'])}] {t['speaker']}**: {safe} ^{line_id(i)}", ""]
    return "\n".join(out).rstrip() + "\n"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    tmp.rename(path)


def ensure_base(out_dir: Path) -> None:
    base = out_dir / BASE_FILE
    if not base.exists():
        write_atomic(base, BASE_TEMPLATE)
