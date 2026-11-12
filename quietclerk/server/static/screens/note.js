// Minutes view: read the draft, press an evidence time to hear just that turn (design: docs/ui/note.html).
// Data: the server embeds the minutes text as JSON in the page (no /api endpoint serves note text yet:
// proposal GET /api/notes/{job_id}); /api/jobs/{id} gives the job, runs and stages (what was sent where);
// /api/jobs/{id}/audio plays with Range. Every string from the transcript or summary goes in as text.
import {flag, h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post, jobPath} from '../lib/api.js';
import {live, subscribe} from '../lib/live.js';
import {btn, chip, code, empty, banner, problemBlock} from '../lib/ui.js';
import {describe} from '../lib/jobs.js';
import {makeActions, languageSelect, problemBanner, jobCard} from '../lib/cards.js';
import {dur, fullDate, stamp} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';
import {nameSpeakers} from '../lib/note-text.js';
import {createSpeakers} from '../lib/speakers.js';
import {createTranscript} from '../lib/transcript.js';
import {createExport} from '../lib/export-menu.js';

const TYPE = {meeting: ['회의', 'Meeting'], status_update: ['현황 공유', 'Status update'], presentation: ['발표', 'Presentation'],
  lecture: ['강의', 'Lecture'], one_on_one: ['1:1', '1:1'], brainstorm: ['브레인스토밍', 'Brainstorm'], other: ['기타', 'Other']};
const DIVISION = {work: ['업무', 'Work'], personal: ['개인', 'Personal']};
const LANGUAGE = {ko: ['한국어', 'Korean'], en: ['영어', 'English'], uncertain: ['불확실', 'Uncertain']};
const FIELD = {transcript: ['대화록', 'transcript'], source_name: ['파일 이름', 'file name'], project_list: ['프로젝트 목록', 'project list'], vocabulary: ['단어장', 'word list']};
const fieldName = (field, i) => (Object.prototype.hasOwnProperty.call(FIELD, field) ? FIELD[field][i] : String(field));

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

// The engine's review codes in words. Same meaning as the "Review needed" lines render.py writes into the note
// (and the marks quality.py puts in the text: ‘check source’ / ‘근거 확인’, ‘Check numbers’ / ‘숫자 확인’). The last two codes
// (contract §10.8 A/B, "Redo from scratch" dropping your names, merges or edited lines) have no line in the note, only this one.
const REASONS = {
  type_uncertain: ['회의 유형이 확실하지 않아요', 'The meeting type is uncertain'],
  language_uncertain: ['언어가 섞여 있어요', 'Mixed languages'],
  summary_review: ['요약에 확인 필요 항목이 있어요', 'The summary has items to check'],
  asr_dropped: ['받아쓰기에서 환각·반복이 의심되는 구간을 뺐어요. 원음을 확인해 주세요', 'Transcription left out parts that looked like hallucination or repetition. Check the recording'],
  speaker_review: ['화자 구분을 확인해 주세요 (아주 짧은 화자를 합쳤거나, 화자 수가 상한에 닿았거나, 확신이 낮아요)', 'Check the speaker labels (tiny speakers were merged, the speaker cap was reached or confidence was low)'],
  unsupported_owner: ['할 일 담당이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였어요', 'A task owner is not backed by the lines it cites; it is marked ‘check source’'],
  unsupported_deadline: ['할 일 기한이 인용한 대화록으로 뒷받침되지 않아 ‘근거 확인’을 붙였어요', 'A task deadline is not backed by the lines it cites; it is marked ‘check source’'],
  unsupported_number: ['숫자나 단위가 인용한 대화록과 달라요. ‘숫자 확인’ 표시를 확인해 주세요', 'Some numbers or units differ from the lines they cite. Check the ‘Check numbers’ marks'],
  weak_citation: ['일부 문장이 인용한 대화록과 겹치는 낱말이 적어요. 근거를 확인해 주세요', 'Some sentences share few words with the lines they cite. Check the evidence'],
  speaker_overrides_dropped: ['처음부터 다시 처리하면서 화자 번호가 바뀌어, 직접 확정한 이름과 합치기를 버렸어요. 화자에서 다시 정해 주세요', 'Reprocessing renumbered the speakers, so the names you confirmed and the merges were dropped. Set them again under Speakers'],
  transcript_edits_dropped: ['처음부터 다시 처리하면서 받아쓰기 글이 달라져, 직접 고친 줄을 버렸어요. 필요하면 다시 고쳐 주세요', 'Reprocessing changed the transcript, so the lines you edited were dropped. Edit them again if you need to'],
};

const REASON = (reason) => {
  const miss = /^unknown_citation:(t\d+)$/.exec(reason);
  if (miss) return L(`근거 번호 [?${miss[1]}]이 대화록에 없어요`, `Evidence ID [?${miss[1]}] isn't in the transcript`);
  if (Object.prototype.hasOwnProperty.call(REASONS, reason)) return L(...REASONS[reason]);
  if (/failed/.test(reason)) return L('일부 교정이 실패했어요', 'Some corrections failed');
  return String(reason);
};

// Six chips at most. The engine's own quality flags come first, so a note with many missing evidence IDs
// cannot push them out of sight; what is left out is counted.
const reasonChips = (reasons) => {
  const missing = (reason) => /^unknown_citation:/.test(reason);
  const ordered = [...reasons.filter((reason) => !missing(reason)), ...reasons.filter(missing)];
  const rest = ordered.length - 6;
  return h('p', {class: 'row small'}, ordered.slice(0, 6).map((reason) => chip('warn multi', '!', REASON(reason))),
    rest > 0 ? chip('line', null, L(`외 ${rest}개`, `+${rest} more`)) : null);
};

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const SPEED_KEY = 'qc.note.speed';
const rememberedSpeed = () => {
  try {
    const value = Number(sessionStorage.getItem(SPEED_KEY));
    return SPEEDS.includes(value) ? value : 1;
  } catch (_) {
    return 1;
  }
};

export async function mount({content, jobId}) {
  const data = readData();
  const state = {job: null, runs: [], notice: null, confirm: false, audio: 'checking', speed: rememberedSpeed(), follow: true, tab: 'sum', fresh: false};
  const audioUrl = jobPath(jobId, 'audio');
  const turns = data.found ? data.turns : [];
  let stopAt = null;
  let frame = 0;
  let loading = false;
  let regen = null;   // set when this page asked for a new summary: whether the job was seen running since

  // Containers that live as long as the page: the player must never be detached while it plays, and a line being edited
  // or a speaker name being typed must never be redrawn by an unrelated update.
  const audio = h('audio', {controls: true, preload: 'metadata', src: audioUrl, 'data-engine': ''});
  const parts = {
    crumb: h('div', {class: 'slot'}), notices: h('div', {class: 'slot'}),
    head: h('div', {class: 'slot'}), confirm: h('div', {class: 'slot'}), tabs: h('div', {class: 'slot'}), summary: h('div', {class: 'slot'}),
    speakers: h('div', {class: 'slot'}), records: h('div', {class: 'slot'}), missing: h('div', {class: 'slot'}),
    playerTitle: h('h2', {id: 'pl-h'}), playerBody: h('div', {class: 'slot'}), playerTools: h('div', {class: 'row player-tools'}), playerHint: h('p', {class: 'small muted'}),
  };
  const running = () => !!state.job && state.job.status === 'running';
  const target = () => state.job || {job_id: jobId};
  const actions = makeActions({after: load, notice: (node) => { state.notice = node; render(); }});
  const rerun = (mode) => {   // a new summary (or a new run) was asked for here: say when it is ready
    regen = {ran: false};
    state.fresh = false;
    return actions.run(target(), mode);
  };

  // The speaker panel, the transcript card and the export menu exist only for minutes that were found.
  let speakers = null, transcript = null, exporter = null;
  if (data.found) {
    speakers = createSpeakers({jobId, hints: data.speakers, audioOk: () => state.audio === 'ok' || state.audio === 'checking',
      isRunning: running, onRunning: markRunning, onChange: namesChanged});
    transcript = createTranscript({jobId, fallback: turns, names: () => speakers.names(), isRunning: running, onRunning: markRunning,
      resummarize: () => rerun('resummarize')});
    exporter = createExport({jobId});
    parts.speakers.append(speakers.node);
  }
  const playerCard = h('section', {class: 'card tight player player-card', 'aria-labelledby': 'pl-h'}, parts.playerTitle, parts.playerBody, parts.playerTools, parts.playerHint);
  const main = h('div', {class: 'stack gap4'}, parts.head, exporter ? exporter.panel : null, parts.confirm, parts.tabs, parts.summary, transcript ? transcript.node : null);
  const layout = h('div', {class: 'split note-split'}, main, h('div', {class: 'note-side'}, playerCard, parts.speakers, parts.records));
  layout.hidden = !data.found;
  content.replaceChildren(parts.crumb, h('div', {class: 'topbar'}, h('h1', {id: 'note-title'})), parts.notices, layout, parts.missing);

  async function load() {
    loading = true;
    const was = running();
    try {
      const detail = await get(jobPath(jobId));
      state.job = detail.job;
      state.runs = detail.runs;
    } catch (_) { /* keep what we have */ }
    loading = false;
    render();
    if (!speakers || was === running()) return;
    speakers.render();
    transcript.render();
    if (was) {   // processing ended: what it left may differ from what is shown
      speakers.load();
      transcript.load();
    }
  }

  // A write was refused with job_running before the page knew: lock the editors now and read the job again.
  function markRunning() {
    if (state.job) state.job = {...state.job, status: 'running'};
    speakers.render();
    transcript.render();
    load();
  }

  // Names or merges changed: the speaker column of the transcript and the summary show them.
  async function namesChanged() {
    await transcript.load();
    transcript.render();
    render();
  }

  // The stream names every job's state: read this job again when it moved, and say when a new summary is ready.
  function watchJob() {
    const row = ((live.snapshot && live.snapshot.jobs) || []).find((job) => job.job_id === jobId);
    if (!row || !state.job) return;
    let ready = false;
    if (regen) {
      if (row.status === 'running') regen.ran = true;
      else if (row.status === 'done' && regen.ran) {
        regen = null;
        state.fresh = true;
        ready = true;
      }
    }
    if (!loading && (row.status !== state.job.status || row.updated_at !== state.job.updated_at)) load();
    else if (ready) render();
  }

  // Probe with a 1-byte Range request so a deleted copy (410) is explained instead of a silent dead player.
  async function probeAudio() {
    try {
      const response = await fetch(audioUrl, {headers: {Range: 'bytes=0-0'}, credentials: 'same-origin'});
      state.audio = response.status === 200 || response.status === 206 ? 'ok' : String(response.status);
    } catch (_) {
      state.audio = '0';
    }
    render();
    if (speakers) speakers.render();
  }
  audio.addEventListener('error', () => { if (state.audio === 'ok') { state.audio = 'error'; render(); if (speakers) speakers.render(); } });

  // The speed sticks to the element: load() would put it back to the default, so both are set.
  function applySpeed() {
    audio.defaultPlaybackRate = state.speed;
    audio.playbackRate = state.speed;
  }

  function play(start, end, button) {
    for (const el of content.querySelectorAll('.playing')) flag(el, 'playing', false);
    if (button) flag(button, 'playing', true);
    stopAt = end;
    applySpeed();
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
    // Before the first play the audio sits at 0:00: nothing is "being played" yet.
    if (transcript) transcript.setPlayhead(audio.currentTime, {playing: !audio.paused, idle: audio.paused && audio.currentTime === 0});
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
    for (const el of content.querySelectorAll('.playing')) flag(el, 'playing', false);
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

  function sectionView(section, names) {
    const list = h('ul', null, section.items.map((item) => h('li', {class: item.task ? 'task' : null},
      nameSpeakers(item.text, names), ' ', item.cites.map((cite) => [evidence(cite), ' ']))));
    if (section.kind === 'review') return h('div', {class: 'callout'}, h('h2', null, section.heading), list);
    return h('div', {class: 'sec'}, h('h2', null, section.heading), list,
      section.kind === 'tasks' ? h('p', {class: 'small muted'}, names.size
        ? L('이름을 확정한 화자는 이름으로, 나머지는 화자 번호로 적혀요. 노트의 할 일 목록은 고친 그대로 남아요.', 'Speakers whose names you confirmed show by name, the rest by speaker number. Your edits to the note\'s task list are kept.')
        : L('담당은 화자 번호로 적혀요. 화자에서 이름을 확정하면 이름으로 바뀌어요. 노트의 할 일 목록은 고친 그대로 남아요.', 'Owners are speaker numbers. Confirm a name under Speakers and it shows by name. Your edits to the note\'s task list are kept.')) : null);
  }

  function summaryCard() {
    const names = speakers ? speakers.names() : new Map();
    const bad = [...new Set(data.sections.flatMap((s) => s.items.flatMap((i) => i.cites.filter((c) => !c.ok).map((c) => c.id))))];
    return h('section', {class: 'card', id: 'sum', 'aria-label': L('요약', 'Summary')},
      bad.length ? h('p', {class: 'banner warn small'}, h('span', {class: 'ic', 'aria-hidden': 'true'}, h('span', null, '!')),
        h('span', null, L(`근거 번호 ${bad.map((id) => `[?${id}]`).join(', ')}은 대화록에 없어요. 지우지 않고 남겨 두었으니 원문과 맞는지 확인해 주세요.`,
          `Evidence ID ${bad.map((id) => `[?${id}]`).join(', ')} isn't in the transcript. It's kept, not removed — please check it against the transcript.`), ' ', code('review: missing_evidence'))) : null,
      data.sections.map((section) => sectionView(section, names)),
      h('p', {class: 'small muted'}, L('근거 시각이 달렸다고 내용이 맞다는 뜻은 아니에요. 눌러서 들어 보세요.', 'A linked time doesn\'t prove the sentence is right. Press it and listen.')));
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
        ? L(`보낸 것: ${fields.map((f) => fieldName(f, 0)).join(', ')}`, `Sent: ${fields.map((f) => fieldName(f, 1)).join(', ')}`)
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
    parts.playerTools.hidden = !ok || !data.found;
    replace(parts.playerTools,
      h('label', {class: 'small row gap6'}, h('span', null, L('재생 속도', 'Speed')),
        h('select', {class: 'input compact', id: 'pl-speed', value: String(state.speed), on: {change: (event) => {
          state.speed = Number(event.target.value);
          applySpeed();
          try { sessionStorage.setItem(SPEED_KEY, String(state.speed)); } catch (_) { /* the speed is just not remembered */ }
        }}}, SPEEDS.map((rate) => h('option', {value: String(rate)}, `${rate}×`)))),
      h('label', {class: 'check small'},
        h('input', {type: 'checkbox', id: 'pl-follow', checked: state.follow, on: {change: (event) => { state.follow = event.target.checked; if (transcript) transcript.setFollow(state.follow); }}}),
        h('span', null, L('재생 따라가기', 'Follow while playing'))));
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
      reasons.length ? reasonChips(reasons) : null);
  }

  function notFound() {
    const job = state.job;
    const view = job ? describe(job, {}) : null;
    let bubble = L('이 회의록을 찾지 못했어요.', 'Couldn\'t find these minutes.');
    let text = L('같은 작업 번호의 회의록이 없어요.', 'There are no minutes for this job ID.');
    if (data.unknown) text = L('이 작업 번호를 엔진이 몰라요. 주소를 다시 확인하거나 목록에서 골라 주세요.', 'The engine does not know this job ID. Check the address or pick one from the list.');
    else if (job && (job.blocked_reason === 'note_update_blocked' || (job.legacy && job.note_path))) {
      bubble = L('노트 교체 동의를 기다려요.', 'Waiting for note conversion consent.');
      text = L('위의 새 형식으로 바꾸기에서 새 결과를 미리보고 교체해 주세요. 이전 노트는 동의 전까지 그대로예요.',
        'Use Convert to new format above to review the new result and replace the note. Until you consent, the old note stays untouched.');
    }
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

  // The section links (#sum, #tx, #spk) are anchors in one page: the current one is only marked. Moving the mark touches
  // nothing else, so the page is not redrawn under a click.
  function markTab(id) {
    state.tab = id;
    for (const link of parts.tabs.querySelectorAll('a')) {
      if (link.getAttribute('href') === `#${id}`) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    }
  }
  const tabLink = (id, ko, en) => h('a', {href: `#${id}`, 'aria-current': state.tab === id ? 'true' : null, on: {click: () => markTab(id)}}, L(ko, en));

  // /notes/<job>#t12 (a link from search) opens the transcript section on that line and marks it for a moment; #sum, #tx
  // and #spk open their sections. Anything else in the address is ignored. Only exact ids are looked up (no selector is built
  // from the address).
  function openHash(flash) {
    const hash = String(location.hash || '');
    const line = /^#(t[1-9]\d*)$/.exec(hash);
    const section = /^#(sum|tx|spk)$/.exec(hash);
    if (line) {
      if (transcript && transcript.showLine(line[1], {flash})) markTab('tx');   // an id the transcript does not have changes nothing
    } else if (section) {
      markTab(section[1]);
    }
  }

  function render() {
    const job = state.job;
    const title = data.title || (job && job.source_name) || jobId;
    setTitle(`${title} · QuietClerk`, `${title} · QuietClerk`);
    document.getElementById('note-title').textContent = title;
    replace(parts.crumb, h('nav', {class: 'crumb', 'aria-label': L('위치', 'Breadcrumb')}, h('a', {href: '/notes'}, L('회의록', 'Notes')),
      h('span', null, '›'), h('span', null, title.length > 24 ? title.slice(0, 24) + '…' : title)));
    replace(parts.notices, state.notice,
      job && ['blocked', 'failed'].includes(describe(job).group) ? jobCard(job, describe(job), actions) : null,
      state.fresh ? banner('info', 'i', [h('b', null, L('회의록을 새로 만들었어요.', 'The minutes were made again.')), ' ', L('새로 고치면 새 요약이 보여요.', 'Reload to see the new summary.')],
        [btn({small: true, icon: 'refresh', label: L('새로 고침', 'Reload'), on: {click: () => location.reload()}})]) : null,
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
    const refocus = document.activeElement === exporter.toggle;
    replace(parts.head,
      noteHeader(),
      h('p', {class: 'promise'}, L('회의록은 초안이에요. 중요한 결정과 할 일은 근거를 확인해 주세요.', 'Minutes are drafts. Check the evidence before relying on decisions and tasks.')),
      h('div', {class: 'actions'},
        data.note_path ? btn({small: true, icon: 'external', href: 'obsidian://open?path=' + encodeURIComponent(data.note_path), label: L('Obsidian에서 열기', 'Open in Obsidian')}) : null,
        exporter.toggle,
        btn({small: true, engine: true, label: L('요약만 다시', 'Re-summarize only'), on: {click: () => rerun('resummarize')}}),
        btn({small: true, engine: true, label: L('처음부터 다시', 'Redo from scratch'), on: {click: () => rerun('from_transcribe')}}),
        job ? languageSelect(job, actions, {auto: true}) : null,
        btn({small: true, kind: 'danger', engine: true, label: L('처리 데이터 삭제', 'Delete processing data'), on: {click: () => { state.confirm = true; render(); }}})));
    if (refocus) exporter.toggle.focus();
    replace(parts.confirm, state.confirm ? deleteConfirm() : null);
    replace(parts.tabs, h('nav', {class: 'tabs', 'aria-label': L('회의록 구역', 'Sections')}, tabLink('sum', '요약', 'Summary'), tabLink('tx', '대화록', 'Transcript'), tabLink('spk', '화자', 'Speakers')));
    replace(parts.summary, summaryCard());
    replace(parts.records, recordsCard());
    syncEngineControls(content);
  }

  onLang(() => {
    render();
    if (!speakers) return;
    speakers.render();
    transcript.render();
    exporter.render();
  });
  subscribe(() => {
    syncEngineControls(content);
    watchJob();
  });
  render();
  if (data.found) {
    applySpeed();
    speakers.render();
    probeAudio();
    openHash(true);   // the lines are on the page from the first draw (the page data), so a link from search lands at once
    // Names are known only when both lists are in: draw the transcript and the summary again with them, then make sure
    // the linked line is still in view (the page may have moved under it) without marking it again.
    Promise.all([speakers.load(), transcript.load()]).then(() => {
      transcript.render();
      render();
      openHash(false);
    });
    if (typeof addEventListener === 'function') addEventListener('hashchange', () => openHash(true));
  }
  await load();
}
