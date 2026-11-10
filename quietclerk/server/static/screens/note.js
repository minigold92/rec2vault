// Minutes view: read the draft, press an evidence time to hear just that turn (design: docs/ui/note.html).
// Data: the server embeds the minutes text as JSON in the page (no /api endpoint serves note text yet:
// proposal GET /api/notes/{job_id}); /api/jobs/{id} gives the job, runs and stages (what was sent where);
// /api/jobs/{id}/audio plays with Range. Every string from the transcript or summary goes in as text.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post, jobPath} from '../lib/api.js';
import {subscribe} from '../lib/live.js';
import {btn, chip, code, empty, banner, problemBlock} from '../lib/ui.js';
import {describe} from '../lib/jobs.js';
import {makeActions, languageSelect, problemBanner} from '../lib/cards.js';
import {dur, fullDate, stamp} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

const TYPE = {meeting: ['회의', 'Meeting'], status_update: ['현황 공유', 'Status update'], presentation: ['발표', 'Presentation'],
  lecture: ['강의', 'Lecture'], one_on_one: ['1:1', '1:1'], brainstorm: ['브레인스토밍', 'Brainstorm'], other: ['기타', 'Other']};
const DIVISION = {work: ['업무', 'Work'], personal: ['개인', 'Personal']};
const LANGUAGE = {ko: ['한국어', 'Korean'], en: ['영어', 'English'], uncertain: ['불확실', 'Uncertain']};
const FIELD = {transcript: ['대화록', 'transcript'], source_name: ['파일 이름', 'file name'], project_list: ['프로젝트 목록', 'project list']};

const word = (table, key) => (table[key] ? L(table[key][0], table[key][1]) : '—');

function readData() {
  try {
    return JSON.parse(document.getElementById('qc-data').textContent);
  } catch (_) {
    return {found: false};
  }
}

const safeList = (text) => {
  try {
    const list = JSON.parse(text || '[]');
    return Array.isArray(list) ? list : [];
  } catch (_) {
    return [];
  }
};

// What was sent where: follow a reused stage to the run that actually produced it (store.provenance_rows).
function provenance(runs, runId, stage) {
  const run = runs.find((r) => r.run_id === runId);
  if (!run) return [];
  const rows = [];
  for (const row of (run.stages || []).filter((s) => s.stage === stage)) {
    if (row.status === 'reused' && row.reused_from) {
      const cut = row.reused_from.indexOf('/');
      rows.push(...provenance(runs.filter((r) => r.run_id !== runId), row.reused_from.slice(0, cut), row.reused_from.slice(cut + 1)));
    } else {
      rows.push(row);
    }
  }
  return rows;
}

const modelNames = (rows) => {
  const names = new Set();
  for (const row of rows) {
    if (!row.model) continue;
    let value;
    try { value = JSON.parse(row.model); } catch (_) { value = row.model; }
    for (const id of (typeof value === 'object' && value ? Object.values(value) : [value])) {
      if (typeof id === 'string') names.add(id.split('@')[0].split('/').pop());
    }
  }
  return [...names];
};

const REASON = (reason) => {
  const miss = /^unknown_citation:(t\d+)$/.exec(reason);
  if (miss) return L(`근거 번호 [?${miss[1]}]이 대화록에 없어요`, `Evidence ID [?${miss[1]}] isn't in the transcript`);
  if (reason === 'type_uncertain') return L('회의 유형이 확실하지 않아요', 'The meeting type is uncertain');
  if (reason === 'language_uncertain') return L('언어가 섞여 있어요', 'Mixed languages');
  if (reason === 'summary_review') return L('요약에 확인 필요 항목이 있어요', 'The summary has items to check');
  if (/failed/.test(reason)) return L('일부 교정이 실패했어요', 'Some corrections failed');
  return String(reason);
};

export async function mount({content, jobId}) {
  const data = readData();
  const state = {job: null, runs: [], notice: null, confirm: false, audio: 'checking'};
  const audioUrl = jobPath(jobId, 'audio');
  const turns = data.found ? data.turns : [];
  let stopAt = null;
  let activeLine = -1;
  let frame = 0;

  // Containers that live as long as the page: the player must never be detached while it plays.
  const audio = h('audio', {controls: true, preload: 'metadata', src: audioUrl, 'data-engine': ''});
  const parts = {
    crumb: h('div', {class: 'slot'}), notices: h('div', {class: 'slot'}), main: h('div', {class: 'stack gap4'}),
    speakers: h('div', {class: 'slot'}), records: h('div', {class: 'slot'}), missing: h('div', {class: 'slot'}),
    playerTitle: h('h2', {id: 'pl-h'}), playerBody: h('div', {class: 'slot'}), playerHint: h('p', {class: 'small muted'}),
  };
  const playerCard = h('section', {class: 'card tight player player-card', 'aria-labelledby': 'pl-h'}, parts.playerTitle, parts.playerBody, parts.playerHint);
  const layout = h('div', {class: 'split note-split'}, parts.main, h('div', {class: 'note-side'}, playerCard, parts.speakers, parts.records));
  layout.hidden = !data.found;
  content.replaceChildren(parts.crumb, h('div', {class: 'topbar'}, h('h1', {id: 'note-title'})), parts.notices, layout, parts.missing);

  async function load() {
    try {
      const detail = await get(jobPath(jobId));
      state.job = detail.job;
      state.runs = detail.runs;
    } catch (_) { /* keep what we have */ }
    render();
  }

  const actions = makeActions({after: load, notice: (node) => { state.notice = node; render(); }});

  // Probe with a 1-byte Range request so a deleted copy (410) is explained instead of a silent dead player.
  async function probeAudio() {
    try {
      const response = await fetch(audioUrl, {headers: {Range: 'bytes=0-0'}, credentials: 'same-origin'});
      state.audio = response.status === 200 || response.status === 206 ? 'ok' : String(response.status);
    } catch (_) {
      state.audio = '0';
    }
    render();
  }
  audio.addEventListener('error', () => { if (state.audio === 'ok') { state.audio = 'error'; render(); } });

  function play(start, end, button) {
    for (const el of content.querySelectorAll('.ts.playing')) el.classList.remove('playing');
    if (button) button.classList.add('playing');
    stopAt = end;
    const go = () => {
      audio.currentTime = start;
      audio.play().catch(() => {});
    };
    if (audio.readyState >= 1) go();
    else {
      audio.addEventListener('loadedmetadata', go, {once: true});
      audio.load();
    }
  }

  function highlight() {
    const t = audio.currentTime;
    let lo = 0, hi = turns.length - 1, found = -1;
    while (lo <= hi) {   // last line that starts at or before t
      const mid = (lo + hi) >> 1;
      if (turns[mid].start <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    // Before the first play the audio sits at 0:00: nothing is "being played" yet.
    const index = found >= 0 && t < turns[found].end && !(audio.paused && t === 0) ? found : -1;
    if (index === activeLine) return;
    const items = content.querySelectorAll('.tx li');
    if (items[activeLine]) items[activeLine].classList.remove('on');
    if (items[index]) items[index].classList.add('on');
    activeLine = index;
  }

  function watch() {
    if (stopAt !== null && audio.currentTime >= stopAt) {
      audio.pause();
      stopAt = null;
    }
    highlight();
    frame = audio.paused ? 0 : requestAnimationFrame(watch);
  }
  audio.addEventListener('play', () => { if (!frame) frame = requestAnimationFrame(watch); });
  audio.addEventListener('pause', () => {
    for (const el of content.querySelectorAll('.ts.playing')) el.classList.remove('playing');
    highlight();
  });
  audio.addEventListener('seeked', highlight);

  content.addEventListener('click', (event) => {
    const button = event.target.closest('[data-seek]');
    if (!button || button.disabled) return;
    const [start, end] = button.dataset.seek.split('-').map(Number);
    play(start, end, button);
  });

  // ---- pieces
  const evidence = (cite) => {
    if (!cite.ok) {
      return h('span', {class: 'ts bad', tabindex: '0', title: L('없는 근거 번호예요. 원문을 확인해 주세요', 'This evidence ID doesn\'t exist. Check the transcript')}, `[?${cite.id}]`);
    }
    const at = stamp(cite.start);
    return h('button', {class: 'ts', type: 'button', 'data-engine': '', 'data-seek': `${cite.start}-${cite.end}`,
      'aria-label': L(`${at} 구간 듣기 (${cite.id})`, `Play from ${at} (${cite.id})`)}, at);
  };

  function sectionView(section) {
    const list = h('ul', null, section.items.map((item) => h('li', {class: item.task ? 'task' : null},
      item.text, ' ', item.cites.map((cite) => [evidence(cite), ' ']))));
    if (section.kind === 'review') return h('div', {class: 'callout'}, h('h2', null, section.heading), list);
    return h('div', {class: 'sec'}, h('h2', null, section.heading), list,
      section.kind === 'tasks' ? h('p', {class: 'small muted'}, L('담당은 이름이 아닌 화자 번호로 적혀요. 노트의 할 일 목록은 고친 그대로 남아요.', 'Owners are speaker numbers, not names. Your edits to the note\'s task list are kept.')) : null);
  }

  function summaryCard() {
    const bad = [...new Set(data.sections.flatMap((s) => s.items.flatMap((i) => i.cites.filter((c) => !c.ok).map((c) => c.id))))];
    return h('section', {class: 'card', id: 'sum', 'aria-label': L('요약', 'Summary')},
      bad.length ? h('p', {class: 'banner warn small'}, h('span', {class: 'ic', 'aria-hidden': 'true'}, h('span', null, '!')),
        h('span', null, L(`근거 번호 ${bad.map((id) => `[?${id}]`).join(', ')}은 대화록에 없어요. 지우지 않고 남겨 두었으니 원문과 맞는지 확인해 주세요.`,
          `Evidence ID ${bad.map((id) => `[?${id}]`).join(', ')} isn't in the transcript. It's kept, not removed — please check it against the transcript.`), ' ', code('review: missing_evidence'))) : null,
      data.sections.map(sectionView),
      h('p', {class: 'small muted'}, L('근거 시각이 달렸다고 내용이 맞다는 뜻은 아니에요. 눌러서 들어 보세요.', 'A linked time doesn\'t prove the sentence is right. Press it and listen.')));
  }

  function transcriptCard() {
    return h('section', {class: 'card', id: 'tx', 'aria-labelledby': 'tx-h'},
      h('div', {class: 'card-head'}, h('h2', {id: 'tx-h'}, L('전체 대화록', 'Full transcript')),
        h('span', {class: 'small muted'}, L(`AI 받아쓰기 초안 · 발언 ${turns.length}개`, `AI transcript draft · ${turns.length} turns`))),
      h('ol', {class: 'tx'}, turns.map((turn) => {
        const at = stamp(turn.start);
        return h('li', {'data-start': turn.start, 'data-end': turn.end},
          h('span', null, h('button', {class: 'ts', type: 'button', 'data-engine': '', 'data-seek': `${turn.start}-${turn.end}`,
            'aria-label': L(`${at} 구간 듣기`, `Play from ${at}`)}, at), h('span', {class: 'id'}, turn.id)),
          h('span', {class: 'sp'}, turn.speaker || '—'), h('span', null, turn.text));
      })));
  }

  function speakersCard() {
    return h('section', {class: 'card tight', 'aria-labelledby': 'sp-h'},
      h('h2', {id: 'sp-h'}, L('화자', 'Speakers')),
      h('div', {class: 'table-wrap'}, h('table', {class: 'table'},
        h('thead', null, h('tr', null, h('th', null, L('화자', 'Speaker')), h('th', null, L('역할', 'Role')), h('th', null, L('이름', 'Name')))),
        h('tbody', null, data.speakers.map((who) => h('tr', null,
          h('td', {'data-k': L('화자', 'Speaker')}, h('b', null, who.label),
            who.split_suspect ? [h('br'), chip('warn', '!', L('분리 오류 의심', 'Split suspected'))] : null),
          h('td', {'data-k': L('역할', 'Role')}, who.role || '—'),
          h('td', {class: who.name ? null : 'muted', 'data-k': L('이름', 'Name')}, who.name
            ? [h('span', null, who.name), ' ', who.name_start !== null ? evidence({ok: true, id: 'name', start: who.name_start, end: who.name_start + 3}) : null] : '—')))))),
      h('p', {class: 'small muted'}, L('‘분리 오류 의심’은 한 화자 번호에 두 사람 말이 섞였을 수 있다는 뜻이에요. S1…은 자동으로 나눈 번호이고 실제 이름이 아니에요.',
        '‘Split suspected’ means one speaker number may contain two people. S1… are automatic labels, not names.')));
  }

  function recordsCard() {
    const runId = state.job && state.job.current_run_id;
    const row = (label, stage) => {
      const rows = provenance(state.runs, runId, stage).filter((r) => r.provider);
      if (!rows.length) return [h('dt', null, label), h('dd', null, '—')];
      const fields = [...new Set(rows.flatMap((r) => (Array.isArray(r.sent_fields) ? r.sent_fields : [])))];
      return [h('dt', null, label), h('dd', null, [...new Set(rows.map((r) => r.provider))].map((name) => {
        const cls = rows.find((r) => r.provider === name).endpoint_class;
        return [`${name} · `, cls === 'external' ? chip('warn', '↗', L('외부', 'External'))
          : cls === 'local' ? chip('ok', '✓', L('이 Mac', 'This Mac')) : chip('idle', '?', L('확인 전', 'Unverified')), h('br')];
      }), h('span', {class: 'small muted'}, fields.length
        ? L(`보낸 것: ${fields.map((f) => (FIELD[f] ? FIELD[f][0] : f)).join(', ')}`, `Sent: ${fields.map((f) => (FIELD[f] ? FIELD[f][1] : f)).join(', ')}`)
        : L('보낸 것: 없음', 'Sent: nothing')))];
    };
    const models = modelNames(['diarize', 'transcribe', 'second_pass'].flatMap((stage) => provenance(state.runs, runId, stage)));
    const lang = data.language || {};
    return h('section', {class: 'card tight', 'aria-labelledby': 'pv-h'},
      h('h2', {id: 'pv-h'}, L('처리 기록과 외부 전송', 'Processing & data sent')),
      h('dl', {class: 'kv'},
        h('dt', null, L('오디오', 'Audio')), h('dd', null, chip('ok', '✓', L('이 Mac에서만 처리', 'On this Mac only'))),
        row(L('교정', 'Correct'), 'correct'), row(L('분류', 'Classify'), 'classify'), row(L('요약', 'Summarize'), 'summarize'),
        h('dt', null, L('받아쓰기', 'Transcription')), h('dd', {class: 'small'}, models.length ? models.join(' · ') : '—'),
        h('dt', null, L('언어', 'Language')), h('dd', null, L(`감지 ${word(LANGUAGE, lang.detected)} · 처리 ${word(LANGUAGE, lang.processed)} · 노트 ${word(LANGUAGE, lang.note)}`,
          `Detected ${word(LANGUAGE, lang.detected)} · processed ${word(LANGUAGE, lang.processed)} · note ${word(LANGUAGE, lang.note)}`)),
        h('dt', null, L('작업', 'Job')), h('dd', {class: 'mono small'}, jobId)));
  }

  function renderPlayer() {
    const ok = state.audio === 'ok' || state.audio === 'checking';
    parts.playerTitle.textContent = L('녹음 듣기', 'Listen');
    audio.setAttribute('aria-label', L('녹음 듣기', 'Listen'));
    parts.playerHint.hidden = !ok;
    parts.playerHint.textContent = L('근거 시각을 누르면 그 발언 구간만 들려줘요.', 'Press an evidence time to play just that turn.');
    if (ok) {
      if (parts.playerBody.firstChild !== audio) parts.playerBody.replaceChildren(audio);
      return;
    }
    parts.playerBody.replaceChildren(problemBlock({
      what: L('이 녹음을 들을 수 없어요.', 'This recording can\'t be played.'),
      why: state.audio === '410' ? L('처리 데이터를 삭제해 원본 사본이 없어요. 폰 원본은 그대로예요.', 'Processing data was deleted, so the copy is gone. The phone original is untouched.')
        : state.audio === '0' ? L('엔진에 닿지 못했어요.', 'Could not reach the engine.') : L('브라우저가 이 오디오를 열지 못했어요.', 'The browser could not open this audio.'),
      how: L('노트와 대화록은 볼 수 있어요.', 'The note and transcript are still readable.'),
      codes: [state.audio === '410' ? '410 audio' : `audio ${state.audio}`]}));
  }

  function deleteConfirm() {
    return h('div', {class: 'card alert tight'},
      h('h3', null, L('처리 데이터를 지울까요?', 'Delete the processing data?')),
      h('div', {class: 'grid g2'},
        h('div', null, h('b', null, L('지우는 것', 'Removed')), h('ul', {class: 'sec small'},
          h('li', null, L('원본 사본과 중간 결과', 'The recording copy and working files')),
          h('li', null, L('대화 관련 기록, 할 일·필드 소유 기록', 'Transcript-related records and note ownership data')),
          h('li', null, L('같은 파일이 다시 와도 처리하지 않도록 지문(해시)만 남겨요', 'A fingerprint (hash) so the same file isn\'t processed again')))),
        h('div', null, h('b', null, L('지우지 못하는 것', 'Not removed')), h('ul', {class: 'sec small'},
          h('li', null, L('폰의 원본 녹음과 받는 폴더의 파일', 'The original on the phone and the file in the inbox')),
          h('li', null, L('볼트의 회의록 노트 (직접 지워 주세요)', 'The note in your vault (delete it yourself)')),
          h('li', null, L('외부 요약 엔진(Codex 등) 쪽에 남은 기록', 'Anything kept by external engines (Codex etc.)'))))),
      h('div', {class: 'actions'},
        btn({kind: 'danger', small: true, engine: true, label: L('지우기', 'Delete'), on: {click: removeLocal}}),
        btn({small: true, label: L('취소', 'Cancel'), on: {click: () => { state.confirm = false; render(); }}})));
  }

  async function removeLocal() {
    try {
      await post(jobPath(jobId, 'delete-local'), {scope: 'processing_data'});
      state.confirm = false;
      state.notice = banner('info', 'i', [h('b', null, L('삭제를 요청했어요.', 'Deletion requested.')), ' ',
        L('처리 중이면 지금 단계를 마친 뒤 지워요. 끝나면 이 화면의 오디오와 대화록은 사라져요.', 'If it is running, deletion waits for the current step. Afterwards the audio and transcript here will be gone.')]);
      await load();
    } catch (error) {
      state.confirm = false;
      state.notice = problemBanner(error);
      render();
    }
  }

  function noteHeader() {
    const reasons = state.job ? safeList(state.job.review_reasons) : [];
    return h('div', {class: 'note-head'},
      h('div', {class: 'row'},
        data.status === 'reviewed' ? chip('ok', '✓', L('검토함', 'Reviewed')) : data.status === 'draft' ? chip('line', '✎', L('초안', 'Draft')) : null,
        reasons.length ? chip('warn', '!', L(`확인 필요 ${reasons.length}`, `${reasons.length} to check`)) : null,
        data.type ? chip('line', null, word(TYPE, data.type)) : null,
        data.division ? chip('line', null, word(DIVISION, data.division)) : null),
      h('p', {class: 'small muted'}, state.job
        ? [[fullDate(state.job.recorded_at), state.job.duration_sec ? dur(state.job.duration_sec) : null,
          L(`화자 ${data.speakers.length}명`, `${data.speakers.length} speakers`)].filter(Boolean).join(' · '),
        ' · ', L('원본 ', 'source '), h('code', null, state.job.source_name)] : null),
      reasons.length ? h('p', {class: 'row small'}, reasons.slice(0, 6).map((reason) => chip('warn', '!', REASON(reason)))) : null);
  }

  function notFound() {
    const job = state.job;
    const view = job ? describe(job, {}) : null;
    let bubble = L('이 회의록을 찾지 못했어요.', 'Couldn\'t find these minutes.');
    let text = L('같은 작업 번호의 회의록이 없어요.', 'There are no minutes for this job ID.');
    if (data.unknown) text = L('이 작업 번호를 엔진이 몰라요. 주소를 다시 확인하거나 목록에서 골라 주세요.', 'The engine does not know this job ID. Check the address or pick one from the list.');
    else if (job && job.status !== 'done') {
      bubble = L('아직 회의록이 없어요.', 'No minutes yet.');
      text = L('이 녹음은 아직 회의록을 쓰는 중이거나 처리하지 않았어요. 처리 상황은 작업 화면에서 볼 수 있어요.', 'This recording is still being processed or was not processed. See the Jobs screen for its state.');
    } else if (job && job.legacy) {
      text = L('이전 버전이 만든 회의록이라 이 화면에서는 볼 수 없어요. Obsidian에서 열어 주세요.', 'These minutes were made by the previous version, so they can\'t be shown here. Open them in Obsidian.');
    } else if (job) {
      text = L('처리 데이터가 지워졌거나 엔진이 보관한 결과를 읽지 못했어요. 볼트의 노트는 그대로 있을 수 있어요.', 'The processing data was deleted or the engine\'s kept result could not be read. The note in your vault may still exist.');
    }
    return [h('section', {class: 'card'}, empty({mood: 'worry', bubble, text,
      actions: [btn({icon: 'refresh', label: L('다시 찾기', 'Search again'), on: {click: () => location.reload()}}), btn({href: '/notes', label: L('목록으로', 'Back to list')}),
        job && view ? chip(view.chip.kind, view.chip.glyph, view.chip.label) : null]})),
    h('p', {class: 'center'}, code(data.unknown ? 'job_not_found' : 'note_not_found'))];
  }

  function render() {
    const job = state.job;
    const title = data.title || (job && job.source_name) || jobId;
    setTitle(`${title} · QuietClerk`, `${title} · QuietClerk`);
    document.getElementById('note-title').textContent = title;
    replace(parts.crumb, h('nav', {class: 'crumb', 'aria-label': L('위치', 'Breadcrumb')}, h('a', {href: '/notes'}, L('회의록', 'Notes')),
      h('span', null, '›'), h('span', null, title.length > 24 ? title.slice(0, 24) + '…' : title)));
    replace(parts.notices, state.notice,
      data.found && data.note_state === 'missing' ? banner('warn', '!', [h('b', null, L('볼트에서 노트 파일을 찾지 못했어요.', 'Couldn\'t find the note file in your vault.')), ' ',
        L('엔진은 볼트 노트를 지우지 않아요. 아래는 엔진이 만든 초안이에요.', 'The engine never deletes vault notes. Below is the draft the engine made.'), ' ', code('note_not_found')]) : null,
      data.found && data.note_state === 'conflict' ? banner('warn', '!', [h('b', null, L('같은 작업의 노트가 둘 이상이에요.', 'More than one note belongs to this job.')), ' ',
        L('어느 것도 고르지 않았어요. 볼트에서 하나만 남겨 주세요.', 'None was chosen. Keep just one in your vault.'), ' ', code('note_conflict')]) : null);
    if (!data.found) {
      replace(parts.missing, notFound());
      syncEngineControls(content);
      return;
    }
    renderPlayer();
    const target = job || {job_id: jobId};
    replace(parts.main,
      noteHeader(),
      h('p', {class: 'promise'}, L('회의록은 초안이에요. 중요한 결정과 할 일은 근거를 확인해 주세요.', 'Minutes are drafts. Check the evidence before relying on decisions and tasks.')),
      h('div', {class: 'actions'},
        data.note_path ? btn({small: true, icon: 'external', href: 'obsidian://open?path=' + encodeURIComponent(data.note_path), label: L('Obsidian에서 열기', 'Open in Obsidian')}) : null,
        btn({small: true, engine: true, label: L('요약만 다시', 'Re-summarize only'), on: {click: () => actions.run(target, 'resummarize')}}),
        btn({small: true, engine: true, label: L('처음부터 다시', 'Redo from scratch'), on: {click: () => actions.run(target, 'from_transcribe')}}),
        job ? languageSelect(job, actions, {auto: true}) : null,
        btn({small: true, kind: 'danger', engine: true, label: L('처리 데이터 삭제', 'Delete processing data'), on: {click: () => { state.confirm = true; render(); }}})),
      state.confirm ? deleteConfirm() : null,
      h('nav', {class: 'tabs', 'aria-label': L('회의록 구역', 'Sections')},
        h('a', {href: '#sum', 'aria-current': 'true'}, L('요약', 'Summary')), h('a', {href: '#tx'}, L('대화록', 'Transcript'))),
      summaryCard(), transcriptCard());
    replace(parts.speakers, speakersCard());
    replace(parts.records, recordsCard());
    activeLine = -1;
    highlight();
    syncEngineControls(content);
  }

  onLang(render);
  subscribe(() => syncEngineControls(content));
  render();
  if (data.found) probeAudio();
  await load();
}
