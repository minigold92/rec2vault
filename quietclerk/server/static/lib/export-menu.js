// Export menu of the minutes screen (contract §10.8 D): SRT, VTT, TXT, Markdown and Word files of the meeting as the
// engine holds it (line edits and confirmed names included), with or without speaker names and times. A plain download:
// the engine answers with Content-Disposition: attachment, and nothing is written into the vault.
import {h, replace} from './dom.js';
import {L} from './i18n.js';
import {announce, btn} from './ui.js';
import {jobPath} from './api.js';
import {syncEngineControls} from './shell.js';
import {live} from './live.js';

export const FORMATS = [
  {id: 'srt', name: 'SRT', ext: '.srt', ko: '자막 파일 · 영상 편집기와 플레이어', en: 'Subtitles · video editors and players'},
  {id: 'vtt', name: 'VTT', ext: '.vtt', ko: '웹 자막 파일 · 브라우저 영상', en: 'Web subtitles · browser video'},
  {id: 'txt', name: 'TXT', ext: '.txt', ko: '제목·요약·대화록을 글로', en: 'Title, summary and transcript as plain text'},
  {id: 'md', name: 'Markdown', ext: '.md', ko: '같은 내용 · 제목 서식 포함', en: 'The same, with headings'},
  {id: 'docx', name: 'Word', ext: '.docx', ko: 'Word · Pages에서 열기', en: 'Opens in Word and Pages'},
];

// Names and times are on by default, as the engine's own default is.
export const exportUrl = (jobId, format, {names = true, timestamps = true} = {}) =>
  `${jobPath(jobId, 'export')}?format=${encodeURIComponent(format)}&names=${names ? 1 : 0}&timestamps=${timestamps ? 1 : 0}`;

export function createExport({jobId}) {
  const state = {open: false, names: true, timestamps: true};
  const caption = h('span');
  const toggle = btn({small: true, engine: true, icon: 'down', act: 'export', label: caption, on: {click: () => show(!state.open)}});
  const panel = h('section', {class: 'card tight export-panel', id: 'export-panel', 'aria-labelledby': 'export-h', hidden: true,
    on: {keydown: (event) => { if (event.key === 'Escape' && state.open) { event.preventDefault(); show(false); toggle.focus(); } }}});
  toggle.setAttribute('aria-controls', 'export-panel');
  toggle.setAttribute('aria-expanded', 'false');
  let links = [];

  function show(open) {
    state.open = open;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      const first = links[0];
      if (first) first.focus();
    }
  }

  const link = (format) => h('a', {class: 'btn export-item', href: exportUrl(jobId, format.id, state), download: true, 'data-format': format.id,
    'aria-label': L(`${format.name} 내려받기 (${format.ext})`, `Download ${format.name} (${format.ext})`),
    on: {click: (event) => {
      if (live.failed) { event.preventDefault(); return; }
      announce(L(`${format.name} 파일을 내려받아요`, `Downloading the ${format.name} file`));
    }}},
  h('b', null, format.name, ' ', h('span', {class: 'muted fw7'}, format.ext)), h('span', {class: 'small muted'}, L(format.ko, format.en)));

  function repoint() {
    for (const el of links) el.setAttribute('href', exportUrl(jobId, el.getAttribute('data-format'), state));
  }

  const option = (key, ko, en) => h('label', {class: 'check small'},
    h('input', {type: 'checkbox', checked: state[key], on: {change: (event) => { state[key] = event.target.checked; repoint(); }}}), h('span', null, L(ko, en)));

  function render() {
    caption.textContent = L('내보내기', 'Export');
    links = FORMATS.map(link);
    replace(panel,
      h('div', {class: 'card-head'}, h('h3', {id: 'export-h'}, L('내보내기', 'Export')),
        btn({small: true, kind: 'ghost', label: L('닫기', 'Close'), on: {click: () => { show(false); toggle.focus(); }}})),
      h('div', {class: 'stack tight'},
        option('names', '화자 이름 넣기', 'Include speaker names'),
        option('timestamps', '시각 넣기 (TXT·Markdown·Word)', 'Include times (TXT, Markdown, Word)'),
        h('p', {class: 'small muted'}, L('자막 파일(SRT·VTT)에는 시각이 늘 들어가요.', 'Subtitle files (SRT, VTT) always have times.'))),
      h('ul', {class: 'export-list', 'aria-label': L('파일 형식', 'File formats')}, links.map((a) => h('li', null, a))),
      h('p', {class: 'small muted'}, L('고친 줄과 확정한 이름이 그대로 들어가요. 파일은 내려받기만 하고 볼트에는 만들지 않아요.', 'Your line edits and confirmed names are in the file. It is only downloaded; nothing is written to your vault.')));
    syncEngineControls(panel);
  }

  render();
  return {toggle, panel, render};
}
