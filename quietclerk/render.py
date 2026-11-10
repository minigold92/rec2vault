"""Pure v2 note rendering; publication and user-owned merges live in notes."""
import html
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from .postprocess import CITATION, TYPE_LABELS, line_id
from .transcript import stamp

BASE_FILE = '회의록-v2.base'
BASE_TEMPLATE = '''filters:
  and:
    - file.ext == "md"
    - qc_schema == 2
    - file.hasTag("meeting-notes")
formulas:
  type_ko: 'if(type == "meeting", "회의", if(type == "status_update", "현황공유", if(type == "presentation", "발표회", if(type == "lecture", "강의", if(type == "one_on_one", "1:1", if(type == "brainstorm", "브레인스토밍", "기타"))))))'
  division_ko: 'if(division == "work", "업무", "개인")'
  status_ko: 'if(status == "reviewed", "검토함", "AI초안")'
properties:
  title:
    displayName: 제목
  date:
    displayName: 날짜
  project:
    displayName: 프로젝트
  duration_min:
    displayName: 길이(분)
  needs_review:
    displayName: 검토필요
  formula.type_ko:
    displayName: 유형
  formula.division_ko:
    displayName: 구분
  formula.status_ko:
    displayName: 상태
views:
  - type: table
    name: 최근 회의록
    order: [title, date, formula.type_ko, formula.division_ko, project, duration_min, formula.status_ko]
    sort:
      - property: started_at
        direction: DESC
  - type: table
    name: 검토 대기
    filters:
      or:
        - status == "draft"
        - needs_review == true
    order: [title, date, needs_review, formula.status_ko]
'''
# The engine owns the body from the "meeting record" heading up to the "notes" heading.
# Plain headings instead of comment markers: Obsidian shows comments in Live Preview.
RECORD_HEADINGS = {'ko': '## 회의 내용', 'en': '## Meeting record'}
TASK_HEADINGS = {'ko': '## 할 일', 'en': '## Tasks'}
NOTES_HEADINGS = {'ko': '## 메모', 'en': '## Notes'}


def note_name(recorded, title, fallback, mtype=None):
    slug = re.sub(r'\s+', '_', (title or fallback).strip())
    slug = re.sub(r'[\\/:*?"<>|#^\[\]%]', '', slug)[:160]
    prefix = '메모_' if mtype == 'memo' else ''
    return f'{recorded:%Y-%m-%d}_{prefix}{slug}_{recorded:%H%M}.md'


def frontmatter(props):
    from .notes import dump_frontmatter
    return dump_frontmatter(props)


def find_existing(out_dir, job):
    from .notes import find_existing as find
    return find(out_dir, job)


def known_projects(out_dir):
    from .notes import parse_note, safe_notes
    found = set()
    for path in safe_notes(Path(out_dir)):
        try:
            props, _ = parse_note(path.read_bytes())
        except ValueError:
            continue
        values = props.get('project', [])
        if isinstance(values, list):
            found.update(v for v in values if isinstance(v, str) and v != 'unassigned')
    return sorted(found)


def _inert_plugins(text):
    """Remove executable delimiters before Markdown or Obsidian plugins see them."""
    text = str(text).replace('`', '｀').replace('~', '～')
    text = text.replace('<%', '‹%').replace('%>', '%›').replace('%%', '％％')
    # Dataview inline expressions also occur in table cells and indented quotes.
    return re.sub(r'(?m)(^|[\s|>])=(?!=)', r'\1＝', text)


def _inert_values(value):
    if isinstance(value, str):
        return _inert_plugins(value)
    if isinstance(value, list):
        return [_inert_values(item) for item in value]
    if isinstance(value, dict):
        return {key: _inert_values(item) for key, item in value.items()}
    return value

def safe_text(text):
    """Escape HTML and disable all authored Markdown links, images and block IDs."""
    text = html.escape(_inert_plugins(text), quote=False)
    text = text.replace('\\', '\\\\')
    return re.sub(r'([\[\]`*_!^|])', r'\\\1', text)


def safe_summary(text):
    # Keep structural headings/lists, but only renderer-created links may navigate.
    text = html.escape(_inert_plugins(text), quote=False)
    text = re.sub(r'!?\[([^\]\n]*)\]\([^\n]*?\)', lambda m: m[1], text)
    text = text.replace('[[', '\\[\\[').replace(']]', '\\]\\]')
    return re.sub(r'(?m)^\s*\[[^\]]+\]:.*$', '', text)


def link_citations(text, starts, review_reasons=None):
    def one(match):
        links = []
        for ident in re.findall(r't\d+', match.group()):
            if ident in starts:
                links.append(f'[[#^{ident}|{stamp(starts[ident])}]]')
            else:
                links.append(f'[?{ident}]')
                reason = f'unknown_citation:{ident}'
                if review_reasons is not None and reason not in review_reasons:
                    review_reasons.append(reason)
        return ' '.join(links)
    return re.sub(r'\]\](?=\[\[#\^)', ']] ', CITATION.sub(one, text))


def _callout(kind, title, body):
    return '\n'.join([f'> [!{kind}] {title}'] + ['> ' + line if line else '>' for line in body.splitlines()])


def shape_summary(summary):
    out = []
    for part in re.split(r'(?m)^## ', summary.strip()):
        if not part.strip():
            continue
        head, _, body = part.partition('\n')
        if head in ('핵심 요약', 'Key summary'):
            out.append(_callout('summary', head, body.rstrip()))
        elif head in ('확인 필요', 'Review needed'):
            out.append(_callout('warning', head, body.rstrip()))
        elif body.strip():
            out.append(f'## {head}\n{body.rstrip()}')
    return '\n\n'.join(out)


def speaker_count(turns, texts, min_chars=20):
    chars = {}
    for turn, text in zip(turns, texts):
        chars[turn['speaker']] = chars.get(turn['speaker'], 0) + len(re.sub(r'\s', '', text))
    return sum(value >= min_chars for value in chars.values())


def split_tasks(summary):
    tasks, rest, in_tasks = [], [], False
    for line in summary.splitlines():
        if line.startswith('## '):
            in_tasks = line[3:].strip() in ('할 일', '합의·할 일', 'Tasks')
            if in_tasks:
                continue
        if in_tasks and re.match(r'^\s*- \[[ xX]\] ', line):
            tasks.append(re.sub(r'^\s*- \[[ xX]\] ', '', line))
        else:
            rest.append(line)
    return tasks, '\n'.join(rest)


PARTICLE = r'((?:으로|은|는|이|가|을|를|과|와|로)(?![가-힣]))?'
_PAIRS = {'은': ('은', '는'), '는': ('은', '는'), '이': ('이', '가'), '가': ('이', '가'), '을': ('을', '를'),
          '를': ('을', '를'), '과': ('과', '와'), '와': ('과', '와')}


def particle_for(name, particle):
    """Korean particle agreeing with the name's last syllable ("S2는" -> "오지안은")."""
    if not particle:
        return ''
    last = name[-1:]
    if not '가' <= last <= '힣':
        return particle  # Latin names: keep what the engine wrote
    final = (ord(last) - 0xAC00) % 28
    if particle in ('으로', '로'):
        return '로' if final in (0, 8) else '으로'  # no final consonant or ㄹ
    return _PAIRS[particle][0 if final else 1]


def replace_speaker_names(summary, speakers):
    """Replace whole labels in prose, never inside authored links or their targets."""
    names = {label: re.sub(r'([\\`*_!^|[\]#])', r'\\\1', value['name'])
             for label, value in speakers.items() if value.get('confirmed') and value.get('name')}
    if not names:
        return summary
    # Korean particles follow labels directly ("S2는"): only ASCII letters/digits extend a label.
    tokens = re.compile(r'(?<!\w)(' + '|'.join(re.escape(label) for label in sorted(names, key=len, reverse=True))
                        + r')(?![A-Za-z0-9_])' + PARTICLE)
    def named(match):
        return names[match[1]] + particle_for(names[match[1]], match[2])
    protected = re.compile(r'(?m)^\s*\[[^\]]+\]:[^\n]*|\[\[[^\n]*?\]\]|!?\[(?:\\.|[^\]\\\n])*\](?:\(|\[[^\]\n]*\])|https?://[^\s<>]+|<[^>\n]*>')
    pieces, start = [], 0
    while match := protected.search(summary, start):
        end = match.end()
        if match[0].endswith('('):
            depth = 1
            while end < len(summary) and depth and summary[end] != '\n':
                char = summary[end]
                if char == '\\':
                    end += min(2, len(summary) - end)
                    continue
                depth += (char == '(') - (char == ')')
                end += 1
        pieces.extend((tokens.sub(named, summary[start:match.start()]), summary[match.start():end]))
        start = end
    pieces.append(tokens.sub(named, summary[start:]))
    return ''.join(pieces)


def components(job, recorded, turns, texts, meta, summary, notes, engines, processed_at,
               language='ko', language_detected=None, output_language=None, review_reasons=(),
               dropped=(), speaker_review=()):
    output_language = output_language or language
    en = output_language == 'en'
    starts = {line_id(i): t['start'] for i, t in enumerate(turns)}
    title = meta.get('title') or f'{recorded:%Y-%m-%d %H:%M} ' + ('Recording' if en else '녹음')
    reasons = list(dict.fromkeys([n for n in notes if 'failed' in n] + list(review_reasons)))
    if dropped:
        reasons.append('asr_dropped')
    if speaker_review:
        reasons.append('speaker_review')
    if meta.get('type_confidence') != 'high':
        reasons.append('type_uncertain')
    if language_detected == 'uncertain':
        reasons.append('language_uncertain')
    if '## 확인 필요' in summary or '## Review needed' in summary:
        reasons.append('summary_review')
    reasons = list(dict.fromkeys(reasons))
    summary = replace_speaker_names(summary, meta.get('speakers', {}))
    tasks, summary = split_tasks(safe_summary(summary))
    messages = {
        'asr_dropped': ('ASR omitted suspected hallucination/repetition; check the recording.',
                        '받아쓰기에서 환각·반복 의심 구간을 제외했습니다. 원음을 확인해 주세요.'),
        'speaker_review': ('Speaker labels require review (merged fragments, speaker cap or low confidence).',
                           '화자 병합·화자 수 상한 또는 낮은 신뢰도로 화자 구분을 확인해야 합니다.'),
        'unsupported_owner': ('A task owner is not backed by its cited lines; it is marked "check source".',
                              '할 일 담당이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였습니다.'),
        'unsupported_deadline': ('A task deadline is not backed by its cited lines; it is marked "check source".',
                                 '할 일 기한이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였습니다.'),
        'unsupported_number': ('Some numbers or units differ from the cited lines; check marked figures.',
                               '숫자·단위가 인용한 대화록과 다릅니다. 표시한 수치를 확인해 주세요.'),
        'weak_citation': ('Some claims have little lexical overlap with their cited lines; check the evidence.',
                          '일부 문장이 인용한 대화록과 어휘 겹침이 낮습니다. 근거를 확인해 주세요.'),
    }
    warnings = [messages[reason][0 if en else 1] for reason in dict.fromkeys(reasons) if reason in messages]
    if warnings:
        summary += '\n\n' + ('## Review needed' if en else '## 확인 필요') + '\n' + '\n'.join('- ' + w for w in warnings)
    tasks = [link_citations(t, starts, reasons) for t in tasks]
    summary = link_citations(shape_summary(summary), starts, reasons)
    speakers = meta.get('speakers', {})
    props = {
        'qc_schema': 2, 'title': title, 'aliases': [title, Path(job['source_name']).stem],
        'date': f'{recorded:%Y-%m-%d}', 'started_at': f'{recorded:%Y-%m-%dT%H:%M:%S}',
        'duration_min': round((job['duration_sec'] or 0) / 60, 1),
        'language': language, 'language_detected': language_detected,
        'type': meta.get('type', 'other'), 'division': meta.get('division', 'work'),
        'topics': meta.get('topics', []), 'project': ['unassigned'], 'project_suggest': meta.get('project_suggest'),
        'attendees': [], 'speakers': [f'{label}: ' + ' · '.join(str(v) for v in
                                     ((s.get('name') if s.get('confirmed') else
                                       (s.get('name') + (' (estimated)' if en else ' (추정)')) if s.get('name') else None),
                                      s.get('role')) if v) for label, s in sorted(speakers.items())],
        'speaker_count': speaker_count(turns, texts), 'status': 'draft', 'needs_review': bool(reasons),
        'review_reasons': reasons, 'source_file': job['source_name'], 'source_sha256': job['sha256'], 'job_id': job['job_id'],
        'pipeline_asr': engines.get('transcribe', []), 'pipeline_llm': engines.get('postprocess', []),
        'external_text_to': engines.get('external_text_to', []), 'processed_at': processed_at.isoformat(timespec='seconds'),
        'tags': ['meeting-notes'],
    }
    props = _inert_values(props)
    rows = []
    for label, speaker in sorted(speakers.items()):
        role, name = safe_text(speaker.get('role') or ''), safe_text(speaker.get('name') or '')
        if name and not speaker.get('confirmed'):
            name += ' (estimated)' if en else ' (추정)'
        ident = speaker.get('name_id')
        if name and ident in starts:
            name += f' [[#^{ident}\\|{stamp(starts[ident])}]]'  # a bare | would split the table cell
        rows.append(f'| {safe_text(label)} | {role} | {name} |')
    generated = []
    if rows:
        generated += ['| Speaker | Role | Name |' if en else '| 화자 | 역할 | 이름 |', '|---|---|---|', *rows, '']
    generated += [summary, '', '## Full transcript' if en else '## 전체 대화록', '',
                  '> AI transcript draft. Speaker labels are not real names.' if en else '> AI 전사 초안. 화자 번호는 실제 이름이 아닙니다.', '']
    for i, (turn, text) in enumerate(zip(turns, texts)):
        speaker = speakers.get(turn['speaker'], {})
        label = (f'{speaker["name"]} ({turn["speaker"]})'
                 if speaker.get('confirmed') and speaker.get('name') else turn['speaker'])
        generated += [f'**[{stamp(turn["start"])}] {safe_text(label)}**: {safe_text(text)} ^{line_id(i)}', '']
    return props, '\n'.join(generated).rstrip(), tasks


def header(props, output_language='ko'):
    en = output_language == 'en'
    mtype = props.get('type', 'other')
    info = f'{TYPE_LABELS[output_language].get(mtype, mtype)} · {props.get("duration_min", "")} '
    info += 'min' if en else '분'
    # No H1: Obsidian already shows the file name (which carries the title) as the inline title.
    return _callout('info', 'Overview' if en else '개요', info)


def render(job, recorded, turns, texts, meta, summary, notes, engines, processed_at, **kwargs):
    from .notes import new_body
    props, generated, tasks = components(job, recorded, turns, texts, meta or {}, summary or '', notes, engines, processed_at, **kwargs)
    language = kwargs.get('output_language') or kwargs.get('language', 'ko')
    return frontmatter(props) + new_body(header(props, language), generated, tasks, language)[0].decode()


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.part')
    with tmp.open('x', encoding='utf-8') as stream:
        stream.write(text)
    tmp.replace(path)


def ensure_base(out_dir):
    from .notes import NoteConflict, safe_path
    if not safe_path(out_dir, out_dir):
        raise NoteConflict()
    base = out_dir / BASE_FILE
    if not base.exists():
        write_atomic(base, BASE_TEMPLATE)
