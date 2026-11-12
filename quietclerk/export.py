"""In-memory meeting downloads; never write export files into the vault."""
import io
import re
import unicodedata
import zipfile
from datetime import datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from . import render, search
from .postprocess import CITATION
from .transcript import stamp

FORMATS = {'srt': 'application/x-subrip', 'vtt': 'text/vtt', 'txt': 'text/plain',
           'md': 'text/markdown', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}


def _clock(seconds, separator):
    milliseconds = round(seconds * 1000)
    seconds, ms = divmod(milliseconds, 1000)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{ms:03d}'


def _paragraph(line):
    """Markdown headings become bold, larger runs; bullets keep a bullet. No styles part needed."""
    heading = re.match(r'^(#{1,3})\s+(.*)$', line)
    if heading:
        size = {1: 36, 2: 28, 3: 24}[len(heading[1])]
        return (f'<w:p><w:pPr><w:spacing w:before="240" w:after="80"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr>'
                f'<w:t xml:space="preserve">{escape(heading[2])}</w:t></w:r></w:p>')
    line = re.sub(r'^(\s*)[-*] (?:\[[ xX]\] )?', lambda m: m[1] + '• ', line)
    return '<w:p><w:r><w:t xml:space="preserve">' + escape(line) + '</w:t></w:r></w:p>'


def _readable(summary, lines):
    """Outside Obsidian, line citations ([t3], [[#^t3|00:23]]) become plain times; callout marks go."""
    starts = {line['id']: line['start'] for line in lines}
    def times(match):
        ids = re.findall(r't\d+', match.group())
        return '(' + ', '.join(stamp(starts[i]) for i in ids if i in starts) + ')' if any(i in starts for i in ids) else ''
    summary = re.sub(r'\[\[#\^(t\d+)\|[^\]]*\]\]', lambda m: '[' + m[1] + ']', summary)
    summary = CITATION.sub(times, summary)
    summary = re.sub(r'^>\s?\[![a-z]+\]\s*', '### ', summary, flags=re.M)
    return re.sub(r'^>\s?', '', summary, flags=re.M)


def _docx(text):
    buffer = io.BytesIO()
    paragraphs = ''.join(_paragraph(line) for line in text.splitlines())
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '<w:sectPr/></w:body></w:document>')
    return buffer.getvalue()


def download(con, job_id, root, params, *, include_transcript=True):
    from starlette.responses import Response
    format = params.get('format', 'txt').strip()
    if format not in FORMATS:
        raise ValueError('invalid export format')
    flags = {}
    for flag in ('names', 'timestamps'):
        value = params.get(flag, '1').strip()
        if value not in ('0', '1'):
            raise ValueError(flag + ' must be 0 or 1')
        flags[flag] = value == '1'
    data = search.meeting(con, job_id, root)
    def label(line):
        return (line['name'] or line['speaker'] or '') if flags['names'] else ''
    if format in ('srt', 'vtt'):
        blocks = []
        for index, line in enumerate(data['lines'], 1):
            prefix = (label(line) + ': ') if label(line) else ''
            separator = ',' if format == 'srt' else '.'
            blocks.append(f"{index}\n{_clock(line['start'], separator)} --> {_clock(line['end'], separator)}\n{prefix}{line['text']}\n")
        text = ('WEBVTT\n\n' if format == 'vtt' else '') + '\n'.join(blocks)
    else:
        title = ('# ' if format == 'md' else '') + data['title']
        lines = []
        for line in data['lines']:
            prefix = ('[' + stamp(line['start']) + '] ') if flags['timestamps'] else ''
            prefix += (label(line) + ': ') if label(line) else ''
            lines.append(prefix + line['text'])
        korean = re.search('[가-힣]', data['title'] + data['summary'])
        heading = '## 전체 대화록' if korean else '## Full transcript'
        if format == 'txt':
            heading = heading[3:]
        summary = _readable(data['summary'], data['lines'])
        if format == 'txt':
            summary = re.sub(r'^#{1,3}\s+', '', summary, flags=re.M)
        text = title + '\n\n' + summary + '\n'
        if include_transcript:
            text += '\n' + heading + '\n' + '\n'.join(lines) + '\n'
    # XML and headers cannot carry controls, including controls in old artifacts.
    text = ''.join(c for c in text if c in '\n\t' or not unicodedata.category(c).startswith('C'))
    body = _docx(text) if format == 'docx' else text.encode('utf-8')
    filename = render.note_name(datetime.strptime(data['date'], '%Y%m%d-%H%M%S'), data['title'], 'Recording', mtype=data['properties'].get('type'))[:-3] + '.' + format
    filename = ''.join(c for c in filename if not unicodedata.category(c).startswith('C'))
    disposition = f'attachment; filename="meeting.{format}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
    return Response(body, media_type=FORMATS[format], headers={'Content-Disposition': disposition})
