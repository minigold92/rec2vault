// Setup steps 5 (phone) and 6 (test run) (design: docs/ui/wizard-5.html, wizard-6.html).
// Step 5 data: GET /api/sync/pairing (device ID, QR text, devices waiting), POST /api/sync/pairing/approve,
// GET /api/sync/folder (not_shared / awaiting_acceptance / connected). Not in the API yet: refusing a device,
// creating the folder share, and the phone's recording count (phone_recordings is null), so those are shown
// off or unknown with the reason. Step 6 watches /api/events and /api/jobs/{id}.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post, jobPath} from '../lib/api.js';
import {subscribe, elapsed} from '../lib/live.js';
import {btn, chip, code, banner, say, problemBlock, announce} from '../lib/ui.js';
import {qrSvg} from '../lib/qr.js';
import {describe, loadJobs, STAGES, stageLabel, providerLabel} from '../lib/jobs.js';
import {jobCard, makeActions, problemBanner} from '../lib/cards.js';
import {dur, clock, localTime} from '../lib/fmt.js';
import {footerBar} from './setup.js';
import {syncEngineControls} from '../lib/shell.js';

const FIELD_NAME = {transcript: ['대화록', 'transcript'], source_name: ['파일 이름', 'file name'], project_list: ['프로젝트 목록', 'project list']};

function phonePictures() {
  const shot = (steps) => h('figure', {class: 'ph'}, h('div', {class: 'screen'}, steps.screen), h('figcaption', {class: 'cap'}, h('b', null, steps.n), h('span', null, steps.cap, h('small', null, steps.sub))));
  return h('div', {class: 'phones', tabindex: '0', role: 'region', 'aria-label': L('폰에서 할 일 세 단계 그림', 'Three steps on the phone')},
    shot({n: '1', cap: L('수락', 'Accept'), sub: L('공유 요청 알림에서 수락', 'Accept the share request'), screen: [
      h('div', {class: 'bar'}, 'Syncthing-Fork'),
      h('div', {class: 'box'}, h('span', {class: 'lbl'}, L('새 폴더 공유 요청', 'Folder share request')), h('span', {class: 'fw8'}, L('QuietClerk 녹음', 'QuietClerk recordings')), h('span', {class: 'lbl'}, L('보낸 기기: QuietClerk Mac', 'From: QuietClerk Mac'))),
      h('span', {class: 'tap'}, L('수락', 'Accept'))]}),
    shot({n: '2', cap: L('경로', 'Path'), sub: L('Recordings/Voice Recorder 고르기', 'Pick Recordings/Voice Recorder'), screen: [
      h('div', {class: 'bar'}, L('폴더 편집', 'Edit folder')),
      h('div', {class: 'box'}, h('span', {class: 'lbl'}, L('폴더 경로', 'Folder path')), h('span', {class: 'val'}, '/storage/emulated/0/', h('span', {class: 'hl'}, 'Recordings/Voice Recorder'))),
      h('span', {class: 'tap'}, L('폴더 고르기', 'Choose folder'))]}),
    shot({n: '3', cap: L('보내기 전용', 'Send only'), sub: L('유형을 바꾸고 ✓ 저장', 'Change type, then ✓ Save'), screen: [
      h('div', {class: 'bar'}, L('폴더 유형', 'Folder type')),
      h('div', {class: 'box'}, h('span', {class: 'radio'}, h('i'), L('보내고 받기', 'Send & receive')), h('span', {class: 'radio on'}, h('i'), h('span', {class: 'hl'}, L('보내기 전용', 'Send only'))), h('span', {class: 'radio'}, h('i'), L('받기 전용', 'Receive only'))),
      h('span', {class: 'tap'}, '✓ ', L('저장', 'Save'))]}));
}

// ---- step 5
export async function step5({content, footer}) {
  const state = {pairing: null, folder: null, pairError: null, folderError: null, approved: new Set(), started: Date.now(), notice: null};

  async function poll() {
    const [pairing, folder] = await Promise.allSettled([get('/api/sync/pairing'), get('/api/sync/folder')]);
    state.pairing = pairing.status === 'fulfilled' ? pairing.value : state.pairing;
    state.pairError = pairing.status === 'rejected' ? pairing.reason : null;
    state.folder = folder.status === 'fulfilled' ? folder.value : state.folder;
    state.folderError = folder.status === 'rejected' ? folder.reason : null;
    render();
  }

  async function approve(id) {
    state.notice = null;
    try {
      await post('/api/sync/pairing/approve', {device_id: id});
      state.approved.add(id);
      announce(L('폰을 승인했어요.', 'Phone approved.'));
    } catch (error) {
      state.notice = problemBanner(error);
    }
    await poll();
  }

  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); announce(L('복사했어요', 'Copied')); } catch (_) { /* clipboard blocked */ }
  };

  function pairingPart() {
    const p = state.pairing;
    const folder = state.folder && state.folder.state;
    const done = state.approved.size > 0 || folder === 'awaiting_acceptance' || folder === 'connected';
    const waited = (Date.now() - state.started) / 60000;
    return h('section', {class: 'part ' + (done ? 'done' : 'now'), 'aria-labelledby': 'p1'},
      h('span', {class: 'no'}, done ? '✓' : '1'),
      h('div', null, h('h2', {id: 'p1'}, L('폰과 이 Mac 짝짓기', 'Pair your phone with this Mac')),
        p ? h('div', {class: 'pair'}, h('div', {class: 'qr'}, qrSvg(p.qr_data, 'M', L('이 Mac의 Syncthing 장치 ID', 'This Mac\'s Syncthing device ID'))),
          h('div', null,
            h('ol', {class: 'stack small'},
              h('li', null, L('① 폰에 Syncthing-Fork 앱을 설치해요. 녹음 앱은 지금 쓰는 그대로 둬요.', '① Install the Syncthing-Fork app on the phone. Keep your current recorder app.')),
              h('li', null, L('② 앱에서 장치 추가 → QR 코드로 이 화면을 찍어요.', '② In the app, choose Add device → QR code and scan this screen.')),
              h('li', null, L('③ 이 화면에 연결 요청이 뜨면 승인해요.', '③ When the request shows up here, approve it.'))),
            h('div', {class: 'stack tight'}, h('span', {class: 'small muted'}, L('QR을 못 찍으면 이 Mac의 장치 ID를 직접 입력해요', 'Can\'t scan? Type this Mac\'s device ID instead')),
              h('div', {class: 'row'}, h('span', {class: 'devid grow', id: 'devid'}, p.device_id),
                btn({small: true, icon: 'copy', label: L('복사', 'Copy'), on: {click: () => copy(p.device_id)}})))))
          : state.pairError ? h('article', {class: 'card alert tight'}, problemBlock({
            what: state.pairError.status === 0 ? L('엔진에 닿지 못했어요.', 'Could not reach the engine.') : L('Syncthing에 연결하지 못했어요.', 'Couldn\'t connect to Syncthing.'),
            why: L('Syncthing이 꺼져 있거나 설정 파일을 읽지 못했어요.', 'Syncthing is not running or its configuration could not be read.'),
            how: L('Syncthing이 켜져 있는지 보고 다시 시도해 주세요.', 'Check that Syncthing is running, then try again.'),
            actions: [btn({small: true, icon: 'refresh', engine: true, label: L('다시 시도', 'Try again'), on: {click: poll}})],
            codes: [state.pairError.status === 503 ? 'sync_unavailable' : `${state.pairError.status}`]})) : chip('run', '●', L('장치 ID를 받는 중', 'Getting the device ID')),
        state.notice,
        p && p.pending.length ? h('div', {class: 'card tight hl-card', role: 'status', 'aria-live': 'polite'}, p.pending.map((device) => h('div', {class: 'row'},
          h('div', {class: 'grow'}, h('b', {class: 'ink'}, L('새 기기가 연결을 요청했어요', 'A new device wants to connect')),
            h('div', {class: 'small muted'}, [device.name || null, `${L('기기 ID', 'Device ID')} ${String(device.device_id).slice(0, 7)}-…`].filter(Boolean).join(' · '))),
          btn({small: true, kind: 'primary', engine: true, label: L('이 폰 승인', 'Approve this phone'), on: {click: () => approve(device.device_id)}}),
          h('span', {class: 'row gap6'}, btn({small: true, disabled: true, label: L('내 폰이 아니에요', 'Not my phone')}),
            h('span', {class: 'why'}, L('거절 API가 아직 없어요. Syncthing에서 무시해 주세요.', 'No refuse API yet. Ignore it in Syncthing.')))))) : null,
        p && !p.pending.length && !done ? h('div', {class: 'card tight', role: 'status', 'aria-live': 'polite'},
          h('div', {class: 'row'}, chip('run', '●', L('폰 요청 기다리는 중', 'Waiting for the phone')), h('span', {class: 'small muted'}, L('요청이 오면 여기에 바로 떠요', 'The request appears here as soon as it arrives')))) : null,
        done ? banner('info', '✓', [h('b', null, L('폰과 연결했어요.', 'Paired with the phone.'))], null, 'status') : null,
        p && !done && waited >= 10 ? h('article', {class: 'card alert tight'},
          h('div', {class: 'card-head'}, h('h3', null, L('폰에서 연결 요청이 오지 않았어요', 'No request from the phone yet')), chip('err', '!', L('연결 안 됨', 'Not paired'))),
          problemBlock({what: L('이 화면을 연 뒤 10분 동안 폰 요청이 없었어요.', 'No request arrived in the 10 minutes since this screen opened.'),
            why: L('원인은 아직 몰라요. 폰 앱이 꺼져 있거나, 다른 ID를 입력했거나, 폰과 Mac이 서로 닿지 못하는 경우가 있어요.', 'We don\'t know the cause yet. The phone app may be closed, a different ID may have been entered, or the phone and Mac can\'t reach each other.'),
            how: L(`폰 앱의 장치 목록에 이 Mac이 있는지 먼저 보세요. 장치 ID 끝 7자리가 ${p.device_id.slice(-7)}여야 해요.`, `First check that this Mac is in the phone app's device list. Its ID should end in ${p.device_id.slice(-7)}.`),
            actions: [btn({small: true, icon: 'refresh', engine: true, label: L('계속 기다리기', 'Keep waiting'), on: {click: () => { state.started = Date.now(); render(); }}})], codes: ['pairing_timeout']})) : null));
  }

  function folderPart() {
    const f = state.folder && state.folder.state;
    return h('section', {class: 'part now', 'aria-labelledby': 'p2'}, h('span', {class: 'no'}, f === 'connected' ? '✓' : '2'),
      h('div', null, h('h2', {id: 'p2'}, L('녹음 폴더 보내기 설정', 'Share the recordings folder')),
        h('p', {class: 'small'}, L('폰의 Syncthing-Fork에서 QuietClerk 녹음 폴더 공유를 수락하고, 그림대로 세 번만 고르면 돼요.', 'In Syncthing-Fork on the phone, accept the QuietClerk recordings folder share and make three choices as pictured.')),
        phonePictures(),
        h('p', {class: 'small muted'}, L('그림은 단순화한 화면이에요. 실제 앱의 글자·배치는 버전마다 다를 수 있어요.', 'Pictures are simplified; labels and layout vary by app version.')),
        banner('warn', '!', [h('b', null, L('✓(저장)가 회색이라 눌리지 않으면', 'If ✓ (Save) stays grey')), ' ', L('폰 화면을 한 번 가로로 돌렸다가 돌아오세요. Syncthing-Fork 2.1.3에서 겪은 문제예요.', 'rotate the phone to landscape and back once. We hit this in Syncthing-Fork 2.1.3.')]),
        h('p', {class: 'small'}, L('왜 보내기 전용인가요? 폰은 보내기만 하고 Mac 쪽 변화는 받지 않아야 폰 녹음 원본이 안전해요.', 'Why send only? The phone only sends and ignores changes on the Mac, so your original recordings stay safe.')),
        h('div', {class: 'row', role: 'status', 'aria-live': 'polite'},
          f === 'connected' ? chip('ok', '✓', L('폴더가 연결됐어요', 'Folder connected'))
            : f === 'awaiting_acceptance' ? [chip('run', '●', L('폰에서 수락 기다리는 중', 'Waiting for the phone to accept')), h('span', {class: 'small muted'}, L('수락하면 여기 바로 표시돼요', 'This updates as soon as you accept'))]
              : f === 'not_shared' ? [chip('idle', '—', L('폴더 공유 전', 'Folder not shared yet')),
                h('span', {class: 'small muted'}, L('짝짓기를 마친 뒤, 이 Mac의 받는 폴더가 폰과 공유돼야 해요. 엔진이 공유를 만드는 API는 아직 없어서 Syncthing에서 공유해 주세요.', 'After pairing, the Mac\'s inbox must be shared with the phone. The engine has no API to create the share yet, so share it in Syncthing.')), code('POST /api/sync/folder')]
                : chip('idle', '?', L('확인 못 함', 'Unknown')))));
  }

  function existingPart() {
    return h('section', {class: 'part now', 'aria-labelledby': 'p3'}, h('span', {class: 'no'}, '3'),
      h('div', null, h('h2', {id: 'p3'}, L('폰에 이미 있는 녹음', 'Recordings already on the phone')),
        h('p', {class: 'small'}, L('폰에 있는 전체 녹음 수는 아직 알 수 없어요. Syncthing이 알려 주는 것은 아직 받지 않은 파일 이름뿐이에요.', 'The total number of recordings on the phone is not known yet. Syncthing only reports names of files not yet received.'), ' ', code('remote_inventory_unavailable')),
        h('fieldset', {class: 'stack fieldset-plain'}, h('legend', {class: 'sr-only'}, L('기존 녹음 처리 방식', 'How to handle existing recordings')),
          h('label', {class: 'option'}, h('input', {type: 'radio', name: 'backlog', checked: true}),
            h('span', null, h('b', null, L('새 녹음만 처리 (권장)', 'Only new recordings (recommended)')),
              h('span', {class: 'help'}, L('기존 녹음은 받지 않아요. 목록은 ‘기존 녹음’ 화면에서 보고, 필요한 것만 골라 받을 수 있어요.', 'Existing recordings are not copied. See them under ‘Older recordings’ and pick any to fetch.')))),
          h('label', {class: 'option'}, h('input', {type: 'radio', name: 'backlog', disabled: true}),
            h('span', null, h('b', null, L('기존 녹음도 Mac으로 받아 두기', 'Also copy existing recordings to the Mac')),
              h('span', {class: 'help'}, L('전체를 받는 API가 아직 없어요. ‘기존 녹음’ 화면에서 고른 것만 받을 수 있어요.', 'There is no API to fetch everything yet. Only picks from ‘Older recordings’ can be fetched.'))))),
        h('div', null, btn({small: true, href: '/backlog', label: L('기존 녹음 보기', 'See older recordings')}))));
  }

  function render() {
    replace(content,
      h('h1', null, L('5. 폰 연결', '5. Phone')),
      say('ok', L('이 단계가 가장 손이 많이 가요. 폰 그림을 따라 하나씩 해 주세요.', 'This is the most hands-on step. Follow the phone pictures one at a time.'),
        L('녹음 앱은 그대로 쓰고, 파일을 옮기는 Syncthing-Fork 앱만 있으면 돼요.', 'Keep your recorder app; you only need Syncthing-Fork to move the files.')),
      pairingPart(), folderPart(), existingPart());
    const ready = state.folder && state.folder.state === 'connected';
    footerBar(footer, {step: 5, nextHref: '/setup/6', nextLabel: L('다음: 시험 녹음', 'Next: test run'), nextDisabled: !ready,
      later: btn({kind: 'ghost', href: '/setup/6?later=5', label: L('나중에 연결하기', 'Connect later')}),
      why: ready ? null : L('폰에서 폴더 수락을 마치면 다음으로 갈 수 있어요.', 'You can continue once the phone accepts the folder.')});
    syncEngineControls(content);
  }

  onLang(render);
  await poll();
  setInterval(poll, 3000);
}

// ---- step 6
export async function step6({content, footer}) {
  const state = {jobs: [], detail: null, providers: [], settings: {}, notice: null};
  const began = Date.now() / 1000;
  let signature = null;

  async function load() {
    try {
      state.jobs = await loadJobs();
      const settings = await get('/api/settings');
      state.settings = settings.effective;
      state.providers = (await get('/api/providers')).items;
    } catch (_) { /* waiting state stays */ }
    const job = pick();
    state.detail = null;
    if (job) {
      try {
        state.detail = await get(jobPath(job.job_id));
      } catch (_) { /* no stage times */ }
    }
    render();
  }

  // The test recording is the newest job that arrived after this screen opened, or one already in progress.
  function pick() {
    return state.jobs.filter((j) => j.created_at >= began - 30 || ['running', 'queued'].includes(j.status)).sort((a, b) => b.created_at - a.created_at)[0] || null;
  }

  const actions = makeActions({after: load, notice: (node) => { state.notice = node; render(); }});

  function stageList(job) {
    const runs = state.detail ? state.detail.runs : [];
    const run = runs[runs.length - 1];
    const by = {};
    for (const row of (run ? run.stages : [])) by[row.stage] = row;
    const e = elapsed();
    const received = h('li', {class: 'done'}, h('span', {class: 'mk'}, '✓'), h('span', null, h('span', {class: 'nm'}, L('받기', 'Received')), h('br'),
      h('span', {class: 'muted'}, [job.duration_sec ? dur(job.duration_sec) : null, job.source_name].filter(Boolean).join(' · '))), h('span', {class: 'tm'}, localTime(job.created_at)));
    return h('ol', {class: 'stages', 'aria-label': L('처리 단계', 'Processing steps'), 'aria-live': 'polite'}, received, STAGES.map(([key]) => {
      const row = by[key];
      const doneRow = row && ['done', 'reused', 'not_run'].includes(row.status);
      const now = row && row.status === 'running';
      const failedRow = row && ['failed', 'timeout', 'interrupted'].includes(row.status);
      const cls = failedRow ? 'fail' : doneRow ? 'done' : now ? 'now' : 'todo';
      const note = row && row.provider ? [providerLabel(row.provider), now ? ` · ${L('글자를 보내는 중', 'sending text')}` : ''].join('') : null;
      return h('li', {class: cls, 'aria-current': now ? 'step' : null}, h('span', {class: 'mk'}, failedRow ? '✕' : doneRow ? '✓' : ''),
        h('span', null, h('span', {class: 'nm'}, stageLabel(key)), note ? [h('br'), h('span', {class: 'muted'}, note)] : null),
        h('span', {class: 'tm', id: now ? 'el-now' : null}, doneRow && row.finished_at && row.started_at ? clock(row.finished_at - row.started_at) : now && e ? clock(e.stage) : ''));
    }));
  }

  function sentTo() {
    const runs = state.detail ? state.detail.runs : [];
    const rows = runs.flatMap((r) => r.stages || []).filter((st) => st.provider && Array.isArray(st.sent_fields) && st.sent_fields.length);
    if (!rows.length) return L('없음', 'nothing');
    const fields = [...new Set(rows.flatMap((st) => st.sent_fields))];
    return `${[...new Set(rows.map((st) => providerLabel(st.provider)))].join(', ')} · ${fields.map((f) => L(FIELD_NAME[f] ? FIELD_NAME[f][0] : f, FIELD_NAME[f] ? FIELD_NAME[f][1] : f)).join(L('·', ', '))}`;
  }

  function render() {
    const job = pick();
    const view = job ? describe(job, {providers: state.providers, settings: state.settings}) : null;
    const group = view ? view.group : 'none';
    let body;
    let mood = say('ok', L('폰에서 5분 넘게 녹음하고 저장해 주세요. 도착하면 단계별로 보여 드릴게요.', 'Record something over 5 minutes on the phone and save it. You\'ll see each step here when it arrives.'),
      L('5분보다 짧은 녹음은 원래 건너뛰어요. 시험으로 짧게 했다면 ‘이 녹음 처리하기’를 누르면 돼요.', 'Recordings under 5 minutes are skipped by default. For a short test, press ‘Process this recording’.'));
    if (group === 'none') {
      body = h('section', {class: 'card', 'aria-live': 'polite'},
        h('div', {class: 'row'}, chip('run', '●', L('기다리는 중', 'Waiting')), h('b', {class: 'ink'}, L('아직 도착한 녹음이 없어요', 'Nothing has arrived yet'))),
        h('p', {class: 'small muted'}, L('받는 폴더를 1분마다 확인해요. 파일이 다 오고 1분 동안 크기가 그대로면 처리를 시작해요.', 'The inbox is checked every minute. Processing starts once a file has stopped changing for a minute.')),
        h('dl', {class: 'kv'}, h('dt', null, L('받는 폴더', 'Inbox')), h('dd', null, h('code', null, state.settings.inbox || '…'))));
    } else if (group === 'done') {
      mood = say('ok', L('첫 회의록 초안을 썼어요!', 'Your first draft minutes are ready!'), L('중요한 결정과 할 일은 근거를 확인해 주세요.', 'Check the evidence for key decisions and tasks.'), true);
      body = h('section', {class: 'card hero'},
        h('div', {class: 'card-head'}, h('h2', null, job.source_name), chip('line', '✎', L('초안', 'Draft'))),
        h('p', {class: 'small muted'}, [job.duration_sec ? dur(job.duration_sec) : null, state.detail && state.detail.runs.length ? L(`처리 ${dur(job.updated_at - state.detail.runs[state.detail.runs.length - 1].started_at)}`, `processed in ${dur(job.updated_at - state.detail.runs[state.detail.runs.length - 1].started_at)}`) : null].filter(Boolean).join(' · ')),
        h('dl', {class: 'kv'}, h('dt', null, L('저장한 곳', 'Saved to')), h('dd', null, h('code', null, job.note_path || '—')),
          h('dt', null, L('외부로 보낸 곳', 'Sent to')), h('dd', null, sentTo())),
        h('div', {class: 'actions'}, btn({kind: 'primary', href: `/notes/${encodeURIComponent(job.job_id)}`, label: L('회의록 보기', 'Open the minutes')})),
        h('p', {class: 'small muted'}, L('볼트를 폰과 동기화하고 있다면 폰의 Obsidian에서도 열려요.', 'If your vault syncs to your phone, it opens in Obsidian there too.')));
    } else if (group === 'skipped') {
      mood = say('worry', L('녹음이 도착했는데, 건너뛰었어요.', 'The recording arrived but was skipped.'));
      body = jobCard(job, view, actions, {mono: true});
    } else if (['running', 'queued', 'retry'].includes(group) || (job.status === 'running')) {
      mood = say('ok', L('새 녹음이 도착해서 받아 적고 있어요.', 'A new recording arrived; I\'m writing it up.'), L('남은 시간은 짐작하지 않고, 단계와 지나간 시간만 보여 드려요.', 'No time-left guesses — just the step and time elapsed.'));
      const e = elapsed();
      body = h('section', {class: 'card hero', 'aria-labelledby': 'tr-h'},
        h('div', {class: 'card-head'}, h('h2', {id: 'tr-h'}, job.source_name), view ? chip(view.chip.kind, view.chip.glyph, view.chip.label) : null),
        h('dl', {class: 'kv num'}, h('dt', null, L('지금 단계', 'Current step')), h('dd', null, job.stage ? [h('b', null, stageLabel(job.stage)), L(` · 11단계 중 ${STAGES.findIndex((s) => s[0] === job.stage) + 2}번째`, ` · step ${STAGES.findIndex((s) => s[0] === job.stage) + 2} of 11`)] : '—'),
          h('dt', null, L('전체 경과', 'Total elapsed')), h('dd', {id: 'el-total'}, e ? clock(e.total) : '—')),
        stageList(job), job.status !== 'running' ? problemBlock({what: view.what, why: view.why, codes: view.codes}) : null);
    } else {
      mood = say('worry', L('처리하지 못했어요.', 'It could not be processed.'));
      body = jobCard(job, view, actions, {mono: true});
    }
    replace(content, h('h1', null, L('6. 시험', '6. Test run')), mood, state.notice, body);
    footerBar(footer, {step: 6, next: false,
      finish: group === 'done' ? btn({kind: 'primary', href: '/home', label: L('설정 마치기', 'Finish setup')}) : btn({kind: 'ghost', href: '/home', label: L('시험은 나중에 하고 마치기', 'Skip the test and finish')})});
    syncEngineControls(content);
  }

  function tick() {
    const e = elapsed();
    const now = document.getElementById('el-now'), total = document.getElementById('el-total');
    if (e && now) now.textContent = clock(e.stage);
    if (e && total) total.textContent = clock(e.total);
  }

  onLang(render);
  subscribe((l) => {
    const sig = l.snapshot ? JSON.stringify([l.snapshot.jobs, l.snapshot.stage && l.snapshot.stage.stage]) : '';
    if (sig !== signature) {
      signature = sig;
      load();
    }
  });
  setInterval(tick, 1000);
  await load();
}

export async function mount(ctx) {
  return ctx.step === 5 ? step5(ctx) : step6(ctx);
}
