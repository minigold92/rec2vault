"""Local checks after ONE summary call; never regenerate or delete a model claim.

Cited lines are the only evidence for task fields and quantities. Calendar dates
are resolved from the recording date (Monday-start weeks), not the processing
clock. Lexical overlap is a conservative warning, not an entailment proof.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from ..postprocess import CITATION

TASK = re.compile(r'^\s*- \[[ xX]\]\s+')
TASK_FIELDS = re.compile(r'\(([^()/\n]+)\s*/\s*([^/\n]+)\)(?=\s*(?:\[t\d|$|[.!]))')
UNASSIGNED = {'담당 미정', '미정', '없음', 'owner unassigned', 'unassigned', 'unknown', 'tbd', 'none'}
NO_DEADLINE = {'기한 미정', '미정', '없음', 'deadline unset', 'no deadline', 'not set', 'unknown', 'tbd', 'none'}
TENTATIVE = re.compile(r'가능하면|대략|상황\s*봐서|잠정|아마|목표|tentative|maybe|if possible|aim|around', re.I)
WEEKDAYS = ('월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일')
EN_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
DATE_EXPR = re.compile(
    r'\d{4}-\d{2}-\d{2}|\d{1,2}월\s*\d{1,2}일|'
    r'(?:(?:다다음|다음|이번)\s*주\s*)?[월화수목금토일]요일|모레|내일|오늘|'
    r'(?:(?:this|next|following)\s+week\s+|(?:this|next|following)\s+)?'
    r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|'
    r'day after tomorrow|tomorrow|today', re.I)
# A date in a cited line counts as the task's date unless it is told as past ("수요일이었고").
PAST = re.compile(r'[었았였]|했(?!으면)|\b(?:was|were|did|had|last)\b', re.I)
# A speaker label is only an owner if that speaker took the task on in a cited line:
# first-person commitment (제가, ~겠습니다, ~할게요) or assent (네, 알겠습니다) to a request.
VOLUNTEER = re.compile(r'제가|내가|저희가|겠습니다|겠어요|겠고|[가-힣]게요|[할볼줄갈올]게(?![가-힣])|드릴게|'
                       r'하기로|할 건데|할 거예요|맡|'
                       r'\bI(?:\s+will|[’\']ll|\s+can)\b|\bwe(?:\s+will|[’\']ll)\b', re.I)
ASSENT = re.compile(r'^\s*(?:네|예|넵|알겠습니다|알겠어요|좋아요|좋습니다|그럴게요|ok|okay|sure|yes)\b', re.I)
UNVERIFIED = {'ko': '근거 확인', 'en': 'check source'}
# Spoken-English numerals in Korean ASR ("스프린트 포") and clock times said as "네 시 반".
TRANSLITERATED = {'원': 1, '투': 2, '쓰리': 3, '스리': 3, '포': 4, '파이브': 5, '식스': 6, '세븐': 7, '에잇': 8,
                  '나인': 9, '텐': 10}
SPOKEN_ENGLISH = re.compile(r'(?<![가-힣])(?P<value>' + '|'.join(sorted(TRANSLITERATED, key=len, reverse=True))
                            + r')(?=$|[\s.,!?]|에서|에|까지|부터|[은는이가을를도로의](?![가-힣]))')
HALF_HOUR = re.compile(r'(?P<hour>[0-9]{1,2}|' + '|'.join(sorted(
    ('한', '두', '세', '네', '다섯', '여섯', '일곱', '여덟', '아홉', '열', '열한', '열두'), key=len, reverse=True))
    + r')\s*시\s*반')

# Unit aliases only: do not convert scales/currencies or invent missing units.
UNIT_ALIASES = {'퍼센트': '%', '프로': '%', 'percent': '%', 'percentage': '%',
                'seconds': '초', 'second': '초', 'sec': '초', 'minutes': '분', 'minute': '분',
                'hours': '시간', 'hour': '시간', 'days': '일', 'day': '일',
                'months': '개월', 'month': '개월', 'won': '원', 'people': '명'}
UNITS = tuple(sorted((*UNIT_ALIASES, '%', '개월', '시간', '명', '건', '분', '초', '일', '주', '월', '년',
                      '세', '원', '만', '억', '조', '천', '백', '개', '회', '배', '차', '시', '점', '위',
                      '쪽', '호', '층', '대', '장', '가지', '번', 'kg', 'km', 'ms', 'MB', 'GB'), key=len, reverse=True))
UNIT_PATTERN = '|'.join(map(re.escape, UNITS))
NUMBER = re.compile(r'(?<![\dA-Za-z_.])(?P<value>[-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>' + UNIT_PATTERN + r')?', re.I)
SINO = {'영': 0, '공': 0, '일': 1, '이': 2, '삼': 3, '사': 4, '오': 5, '육': 6, '칠': 7, '팔': 8, '구': 9}
SMALL = {'십': 10, '백': 100, '천': 1000}
LARGE = {'만': 10000, '억': 100000000, '조': 1000000000000}
NATIVE = {'한': 1, '하나': 1, '두': 2, '둘': 2, '세': 3, '셋': 3, '네': 4, '넷': 4, '다섯': 5, '여섯': 6,
          '일곱': 7, '여덟': 8, '아홉': 9, '열': 10, '스무': 20, '스물': 20, '서른': 30, '마흔': 40}
KO_NUMBER = re.compile(r'(?<![가-힣])(?P<value>[영공일이삼사오육칠팔구십백천만억조]+|'
                       + '|'.join(sorted(NATIVE, key=len, reverse=True))
                       + r'(?:한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉)?)\s*(?P<unit>' + UNIT_PATTERN + r')')
NATIVE_WORD = re.compile(r'(?<![가-힣])(?P<value>' + '|'.join(sorted(NATIVE, key=len, reverse=True))
                         + r')(?=$|\s|[만은는이가을를도에의씩])')
SINO_LIST = re.compile(r'(?<![가-힣])[일이삼사오육칠팔구십](?:\s+[일이삼사오육칠팔구십](?=$|[\s.,]|에|의|까지|부터|번))+|'
                       r'(?<![가-힣])[일이삼사오육칠팔구십백]+(?=부터|까지|번)')
SINO_ALONE = re.compile(r'(?<![가-힣])(?P<value>[일삼사오육칠팔구십])(?=\s|$|[.,])')
ISO_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')


def recording_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ('%Y%m%d-%H%M%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
    return None


def calendar_table(recorded, language='ko'):
    day = recording_date(recorded)
    if day is None:
        return ''
    monday = day - timedelta(days=day.weekday())
    rows = []
    for offset in range(21):
        current = day + timedelta(days=offset)
        week = (current - monday).days // 7
        relative = (('이번 주', '다음 주', '다다음 주', '3주 뒤')[week] if language == 'ko' else
                    ('this week', 'next week', 'following week', 'three weeks ahead')[week])
        label = WEEKDAYS[current.weekday()] if language == 'ko' else EN_WEEKDAYS[current.weekday()]
        near = (('오늘', '내일', '모레') if language == 'ko' else ('today', 'tomorrow', 'day after tomorrow'))
        rows.append(f'{current.isoformat()} {label} {relative}' + (f' ({near[offset]})' if offset < 3 else ''))
    return '\n'.join(rows)


def resolve_date(expression, recorded):
    day = recording_date(recorded)
    expression = expression.strip().lower()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', expression):
            return date.fromisoformat(expression)
        if day is None:
            return None
        match = re.fullmatch(r'(\d{1,2})월\s*(\d{1,2})일', expression)
        if match:
            return date(day.year, int(match[1]), int(match[2]))
        offsets = {'오늘': 0, 'today': 0, '내일': 1, 'tomorrow': 1, '모레': 2, 'day after tomorrow': 2}
        if expression in offsets:
            return day + timedelta(days=offsets[expression])
        compact = re.sub(r'\s+', '', expression)
        for index, names in enumerate(zip(WEEKDAYS, EN_WEEKDAYS)):
            if any(compact.endswith(name.lower()) for name in names):
                if compact.startswith(('다다음주', 'following')):
                    week = 2
                elif compact.startswith(('다음주', 'next')):
                    week = 1
                elif compact.startswith(('이번주', 'this')):
                    week = 0
                else:
                    return day + timedelta(days=(index - day.weekday()) % 7)
                return day - timedelta(days=day.weekday()) + timedelta(days=7 * week + index)
    except ValueError:
        return None
    return None


def _sino_number(text):
    if text in NATIVE:
        return NATIVE[text]
    for tens in ('열', '스물', '서른', '마흔'):
        if text.startswith(tens) and text[len(tens):] in NATIVE:
            return NATIVE[tens] + NATIVE[text[len(tens):]]
    if any(c not in SINO and c not in SMALL and c not in LARGE for c in text):
        return None
    total = section = digit = 0
    for char in text:
        if char in SINO:
            digit = SINO[char]
        elif char in SMALL:
            section += (digit or 1) * SMALL[char]
            digit = 0
        else:
            total += (section + digit or 1) * LARGE[char]
            section = digit = 0
    return total + section + digit


def digit_quantities(text):
    """Figures written with digits: what an engine's summary uses. Hangul numerals in
    model prose are not parsed — "조사 대상" would read as 조+사 대."""
    values = set()
    for match in NUMBER.finditer(CITATION.sub('', text)):
        value = format(Decimal(match['value'].replace(',', '')).normalize(), 'f')
        unit = (match['unit'] or '').lower()
        values.add((value, UNIT_ALIASES.get(unit, unit)))
    return values


def quantities(text):
    text = CITATION.sub('', text)
    values = set()
    for match in NUMBER.finditer(text):
        value = format(Decimal(match['value'].replace(',', '')).normalize(), 'f')
        unit = (match['unit'] or '').lower()
        values.add((value, UNIT_ALIASES.get(unit, unit)))
    for match in KO_NUMBER.finditer(text):
        # Single-syllable numerals glued to units are ambiguous ordinary words
        # (구분, 일시, 공조). Require a separator instead of guessing their meaning.
        if match['value'] == '이' or (len(match['value']) == 1 and
                                      not any(c.isspace() for c in match.group())):
            continue
        number = _sino_number(match['value'])
        if number is not None:
            unit = match['unit'].lower()
            values.add((format(Decimal(number).normalize(), 'f'), UNIT_ALIASES.get(unit, unit)))
    return values


def evidence_quantities(text):
    """Quantities the cited lines support, including spoken forms. Adding evidence
    forms can only remove false warnings; it never creates one."""
    values = set(quantities(text))
    for match in SPOKEN_ENGLISH.finditer(CITATION.sub('', text)):
        values.add((str(TRANSLITERATED[match['value']]), ''))
    plain = CITATION.sub('', text)
    # Native numerals before any noun ("여섯 자리", "탑 하나만", "한 두 장").
    for match in NATIVE_WORD.finditer(plain):
        values.add((str(NATIVE[match['value']]), ''))
    # A lone sino numeral word ("스프린트 삼 목표"); 이 is skipped, it is mostly "this".
    for match in SINO_ALONE.finditer(plain):
        values.add((str(SINO.get(match['value']) or SMALL[match['value']]), ''))
    # Sino numerals read out as a list or range ("일 이 삼 사", "일부터 십까지").
    for match in SINO_LIST.finditer(plain):
        for numeral in re.findall(r'[영공일이삼사오육칠팔구십백]+', match.group()):
            number = _sino_number(numeral)
            if number is not None:
                values.add((str(number), ''))
    for match in HALF_HOUR.finditer(text):
        hour = int(match['hour']) if match['hour'].isdigit() else _sino_number(match['hour'])
        if hour:
            values.update({(str(hour), '시'), ('30', '분')})
    for value, unit in list(values):
        # "네 시" in a meeting is 4 or 16 o'clock; both readings are evidence.
        if unit == '시' and value.isdigit() and 1 <= int(value) <= 12:
            values.add((str(int(value) + 12), '시'))
    return values


def unsupported_quantities(claim, evidence):
    have = evidence_quantities(evidence)
    numbers = {value for value, _ in have}
    missing = set()
    # Calendar dates are checked as deadlines; in prose they are the engine's own
    # conversions from the recording-date table, not spoken figures.
    for value, unit in digit_quantities(ISO_DATE.sub('', claim)):
        if (value, unit) in have:
            continue
        # A unitless figure (a range start "10~15분", "스프린트 4") needs only the number;
        # a number spoken without a unit supports it with any unit. 38명 ≠ 38%.
        if (unit == '' and value in numbers) or (value, '') in have:
            continue
        missing.add((value, unit))
    return missing


def _grams(text):
    text = re.sub(r'[^\w가-힣]', '', text.lower())
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _owner_supported(owner, evidence, cited, turns, texts, meta):
    if owner.lower() in UNASSIGNED:
        return True
    # A whole name/label, not a substring of another person's name.
    if re.search(r'(?<![\w])' + re.escape(owner)
                 + r'(?:님|씨)?(?:은|는|이|가|에게|께서|을|를)?(?=$|[\s.,:;!?])', evidence):
        return True
    for index in cited:
        label = turns[index]['speaker']
        speaker = meta.get('speakers', {}).get(label, {})
        if owner == label or (owner == speaker.get('name') and speaker.get('name_id')):
            if VOLUNTEER.search(texts[index]) or ASSENT.search(texts[index]):
                return True
    return False


def _deadline(deadline, evidence, recorded, language):
    """Normalize a supported deadline; never erase what the model wrote."""
    unset = 'deadline unset' if language == 'en' else '기한 미정'
    if deadline.lower().strip() in NO_DEADLINE:
        return unset, True
    bare = re.sub(r'\s*·\s*(?:확정|잠정|confirmed|tentative)\s*$', '', deadline.strip())
    unverified = f"{bare} · {UNVERIFIED['en' if language == 'en' else 'ko']}"
    requested = DATE_EXPR.search(deadline)
    if requested is None:
        # Free phrases ("배포 전", "필요 발생 시"): keep them when the cited lines say them.
        grams = _grams(re.sub(r'[·]\s*(?:확정|잠정|confirmed|tentative)', '', deadline))
        if grams and len(grams & _grams(evidence)) / len(grams) >= .5:
            return deadline.strip(), True
        return unverified, False
    rest = (deadline[:requested.start()] + deadline[requested.end():])
    rest = re.sub(r'\s*·\s*(?:확정|잠정|confirmed|tentative)\s*$', '', rest).strip(' ,·')
    wanted = resolve_date(requested.group(), recorded)
    for candidate in DATE_EXPR.finditer(evidence):
        # Mentioning a past date or weekday is not itself a deadline.
        nearby = evidence[max(0, candidate.start() - 32):candidate.end() + 32]
        if PAST.search(evidence[candidate.start():candidate.end() + 8]):
            continue
        found = resolve_date(candidate.group(), recorded)
        if (wanted is not None and wanted == found or
                wanted is None and requested.group().lower() == candidate.group().lower()):
            line_start = evidence.rfind('\n', 0, candidate.start()) + 1
            line_end = evidence.find('\n', candidate.end())
            tentative = bool(TENTATIVE.search(evidence[line_start:line_end if line_end >= 0 else len(evidence)]))
            label = ('tentative' if tentative else 'confirmed') if language == 'en' else ('잠정' if tentative else '확정')
            when = found.isoformat() if found else candidate.group()
            return f"{when}{' ' + rest if rest else ''} · {label}", True
    return unverified, False


def verify_summary(summary, turns, texts, meta, recorded=None, language='ko'):
    """Return marked text and stable review codes. Do not change the transcript."""
    reasons, output = [], []
    def flag(code):
        if code not in reasons:
            reasons.append(code)
    for original in summary.splitlines():
        line = original
        if not line.strip() or line.lstrip().startswith('#'):
            output.append(line)
            continue
        identifiers = [int(ident[1:]) - 1 for cite in CITATION.findall(line) for ident in re.findall(r't\d+', cite)]
        cited = sorted({i for i in identifiers if 0 <= i < len(texts)})
        evidence = '\n'.join(texts[i] for i in cited)
        claim = CITATION.sub('', line)
        fields = TASK_FIELDS.search(line) if TASK.match(line) else None
        if TASK.match(line):
            if fields:
                owner, due = fields[1].strip(), fields[2].strip()
                if not _owner_supported(owner, evidence, cited, turns, texts, meta):
                    # Keep the engine's guess visible but marked, like a deadline.
                    owner = f"{owner} · {UNVERIFIED['en' if language == 'en' else 'ko']}"
                    flag('unsupported_owner')
                due, supported = _deadline(due, evidence, recorded, language)
                if not supported:
                    flag('unsupported_deadline')
                line = line[:fields.start()] + f'({owner} / {due})' + line[fields.end():]
                claim = CITATION.sub('', original[:fields.start()] + original[fields.end():])
            else:
                # Missing/malformed fields must never look like a verified assignment.
                line += ' (owner unassigned / deadline unset)' if language == 'en' else ' (담당 미정 / 기한 미정)'
                flag('unsupported_owner')
                flag('unsupported_deadline')
        if unsupported_quantities(claim, evidence):
            line += ' ⚠ Check numbers' if language == 'en' else ' ⚠ 숫자 확인'
            flag('unsupported_number')
        grams = _grams(re.sub(r'^\s*[-*\d.]+\s*(?:\[[ xX]\])?', '', claim))
        # Below 15% of character bigrams: unrelated evidence, not a paraphrase
        # quality score. No neighbouring turns: those were not actually cited.
        if len(grams) >= 3 and (not evidence or len(grams & _grams(evidence)) / len(grams) < .15):
            flag('weak_citation')
        output.append(line)
    return '\n'.join(output), reasons
