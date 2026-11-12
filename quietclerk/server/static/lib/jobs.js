// Job state -> screen wording (contract §2.1 states, README §6 table). One place decides the
// chip, the "what / why / how" sentences, the buttons and the status codes, so Home, Jobs and the
// setup test show the same thing for the same job.
import {L} from './i18n.js';
import {get, post, jobPath} from './api.js';
import {dur, localTime} from './fmt.js';

export const STAGES = [
  ['convert', '변환', 'Convert'], ['diarize', '화자 분리', 'Speakers'], ['detect_language', '언어 감지', 'Language'],
  ['transcribe', '받아쓰기', 'Transcribe'], ['second_pass', '보조 받아쓰기', 'Second pass'], ['turns', '발언 묶기', 'Turns'],
  ['correct', '교정', 'Correct'], ['classify', '분류', 'Classify'], ['summarize', '요약', 'Summarize'],
  ['note', '노트 쓰기', 'Publish'],
];

export function stageLabel(key) {
  const row = STAGES.find((stage) => stage[0] === key);
  return row ? L(row[1], row[2]) : String(key || '');
}

export const PROVIDER_NAME = {codex: 'Codex CLI', claude: 'Claude Code', ollama: 'Ollama', gemini: 'Gemini CLI', omp: 'omp'};
export const LOGIN_COMMAND = {codex: 'codex login', claude: 'claude'};
export const providerLabel = (name) => PROVIDER_NAME[name] || name;

// Every page of the job list (ascending job id), so the newest recordings are included.
export async function loadJobs() {
  const items = [];
  let cursor = '';
  for (let page = 0; page < 25; page += 1) {
    const result = await get(`/api/jobs?limit=200${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}`);
    items.push(...result.items);
    if (!result.next_cursor) break;
    cursor = result.next_cursor;
  }
  return items;
}

export const isBlocked = (job) => job.status === 'retry_wait' && !!job.blocked_reason;

const act = {
  resume: () => ({id: 'resume', label: L('이어서 처리', 'Resume'), kind: 'primary'}),
  redo: () => ({id: 'from_transcribe', label: L('처음부터 다시', 'Redo from scratch')}),
  resummarize: (primary) => ({id: 'resummarize', label: L('요약만 다시', 'Re-summarize only'), kind: primary ? 'primary' : ''}),
  retry: () => ({id: 'retry', label: L('지금 다시 시도', 'Retry now')}),
  exclude: () => ({id: 'exclude', label: L('제외', 'Exclude'), kind: 'danger'}),
  include: () => ({id: 'include', label: L('제외 해제', 'Include again')}),
  process: () => ({id: 'process', label: L('이 녹음 처리하기', 'Process this recording'), kind: 'primary'}),
  recheck: () => ({id: 'recheck', label: L('로그인 다시 확인', 'Re-check sign-in'), kind: 'primary', icon: 'refresh'}),
  pin: () => ({id: 'pin'}),
  link: (href, label) => ({href, label}),
};

const codeText = (text) => String(text || '').slice(0, 80);

// env: {providers: /api/providers items, settings: effective settings}
export function describe(job, env = {}) {
  const settings = env.settings || {};
  const length = job.duration_sec ? dur(job.duration_sec) : null;
  const signedOut = (env.providers || []).filter((p) => p.logged_in === false && (settings['providers.order'] || []).includes(p.name));
  if (job.legacy && job.note_path && ['done', 'failed', 'retry_wait'].includes(job.status)) {
    return blocked({...job, blocked_reason: 'note_update_blocked'}, signedOut, {codes: [], actions: []});
  }
  const base = {codes: [], actions: [act.exclude()]};
  switch (job.status) {
    case 'running':
      return {group: 'running', chip: {kind: 'run', glyph: '●', label: L('처리 중', 'Processing')}, codes: [], actions: [act.exclude()]};
    case 'queued':
      return {group: 'queued', chip: {kind: 'idle', glyph: '…', label: L('대기', 'Queued')},
        what: L('다음 차례를 기다려요.', 'Waiting for its turn.'), codes: ['queued'], actions: [act.exclude()]};
    case 'done':
      return {group: 'done', chip: {kind: 'ok', glyph: '✓', label: L('완료', 'Done')}, codes: [], actions: []};
    case 'retry_wait':
      return job.blocked_reason ? blocked(job, signedOut, base) : waiting(job, base);
    case 'failed':
      return failed(job, base, settings);
    case 'skipped':
      return skipped(job, settings, length);
    default:
      return {group: 'other', chip: {kind: 'idle', glyph: '?', label: job.status}, codes: [job.status], actions: []};
  }
}

function blocked(job, signedOut, base) {
  const names = signedOut.map((p) => providerLabel(p.name));
  const codes = ['retry_wait', `blocked_reason=${job.blocked_reason}`];
  const holding = L('교정·요약 단계 앞에서 기다려요. 받아쓰기까지는 끝났어요.', 'Waiting before Correct and Summarize. Transcription is done.');
  switch (job.blocked_reason) {
    case 'note_update_blocked':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('동의 대기 · 노트 교체', 'Awaiting consent · replace note')}, codes,
        what: L('새 결과는 보관했지만 이전 형식 노트를 덮어쓰지 않았어요.', 'The new result was kept; the old-format note was not overwritten.'),
        why: L('이전 본문과 직접 쓴 메모를 지키기 위해 멈췄어요. 자동 재시도하지 않고 시도 횟수도 쓰지 않아요.',
          'Stopped to protect the old body and your notes. No automatic retry and no attempt used.'),
        how: L('미리보기를 확인하고 새 형식으로 바꿔 주세요. 기존 본문 전체는 메모 칸에 보존해요.',
          'Review the preview, then convert to the new format. The whole old body is kept under Notes.'),
        actions: [{id: 'convert-note', label: L('새 형식으로 바꾸기', 'Convert to new format'), kind: 'primary'}, act.exclude()]};
    case 'note_conflict':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 노트 충돌', 'Blocked · note conflict')}, codes,
        what: L('볼트의 노트를 덮어쓰지 않고 멈췄어요.', 'Stopped without overwriting the vault note.'),
        why: L('노트의 식별·본문 경계·파일 변경을 안전하게 확인할 수 없어요. 자동 재시도하지 않아요.',
          'The note identity, body boundaries or file changes could not be checked safely. It will not retry automatically.'),
        how: L('볼트의 중복 노트와 본문 경계를 확인한 뒤 이어서 처리해 주세요.', 'Check duplicate notes and body boundaries in the vault, then resume.'),
        actions: [act.resume(), act.exclude()]};
    case 'auth':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 로그인', 'Blocked · sign-in')}, codes, what: holding,
        why: names.length
          ? L(`켜 둔 요약 엔진(${names.join(', ')})이 모두 로그인이 풀렸어요. 시간이 지나도 저절로 풀리지 않아요.`,
            `All enabled engines (${names.join(', ')}) are signed out. This won't clear by itself.`)
          : L('켜 둔 요약 엔진이 모두 로그인이 풀렸어요. 시간이 지나도 저절로 풀리지 않아요.', 'All enabled engines are signed out. This won\'t clear by itself.'),
        how: L('터미널에서 하나라도 로그인하면 이어서 처리해요.', 'Sign in to either in Terminal and it resumes.'),
        command: signedOut.map((p) => LOGIN_COMMAND[p.name]).filter(Boolean), actions: [act.recheck(), act.exclude()]};
    case 'no_local_provider':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 로컬 엔진 없음', 'Blocked · no local engine')}, codes,
        what: L('교정 단계 앞에서 기다려요.', 'Waiting before Correct.'),
        why: L('로컬 전용 모드라 이 Mac에서 도는 엔진만 쓸 수 있는데, 로컬로 확인된 엔진이 없어요. Ollama는 아직 ‘확인 전’이에요.',
          'Local-only mode allows only engines confirmed to run on this Mac, and none are. Ollama is still unverified.'),
        how: L('로컬 전용을 끄고 외부 엔진을 허용하거나, 로컬 엔진 확인을 기다려요.', 'Turn off local-only to allow external engines, or wait for a verified local engine.'),
        actions: [act.link('/settings#providers', L('요약 엔진 설정', 'Engine settings')), act.exclude()]};
    case 'no_verified_provider':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 쓸 엔진 없음', 'Blocked · no usable engine')}, codes,
        what: holding,
        why: L('동의하고 켜 둔, 도구 차단이 확인된 요약 엔진이 없어요.', 'No enabled engine with confirmed tool blocking and your consent.'),
        how: L('요약 엔진을 설치하고 로그인한 뒤 설정에서 순서에 넣어 주세요.', 'Install and sign in to an engine, then add it to the order in settings.'),
        actions: [act.link('/settings#providers', L('요약 엔진 설정', 'Engine settings')), act.exclude()]};
    case 'disk_low':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 공간 부족', 'Blocked · low disk')}, codes,
        what: L('처리를 멈췄어요.', 'Processing is on hold.'),
        why: L('Mac의 여유 공간이 2GB보다 적어요. 중간 파일을 쓰다 실패할 수 있어 멈춰요.', 'The Mac has under 2 GB free. Writing working files could fail, so processing waits.'),
        how: L('공간을 2GB 넘게 비우면 자동으로 다시 시작해요.', 'Free more than 2 GB and it resumes on its own.'),
        actions: [act.link('/settings#retention', L('보존 설정 보기', 'Retention settings')), act.exclude()]};
    case 'vault_migration':
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘 · 노트 이행', 'Blocked · note conversion')}, codes,
        what: L('새 회의록은 만들었지만 볼트에 아직 넣지 않았어요.', 'The new minutes are written but not in your vault yet.'),
        why: L('볼트에 이전 형식 노트가 있어서, 새 형식으로 옮기기 전에는 볼트에 쓰지 않아요. 시도 횟수는 쓰지 않았어요.',
          'The vault still has old-format notes; nothing is written to it until they are converted. No attempt was used.'),
        how: L('노트 옮기기를 마치면 이어서 처리해요.', 'Once the note conversion is done, it continues.'),
        actions: [act.link('/migrate', L('노트 옮기기', 'Convert notes')), act.exclude()]};
    default:
      return {...base, group: 'blocked', chip: {kind: 'warn', glyph: '!', label: L('막힘', 'Blocked')}, codes, what: L('처리를 멈췄어요.', 'Processing is on hold.'),
        why: L('원인은 아직 몰라요.', 'The cause is unknown.'), actions: [act.exclude()]};
  }
}

function waiting(job, base) {
  const error = String(job.last_error || '');
  const stageKey = error.startsWith('timeout:') ? error.slice(8) : null;
  const next = job.next_attempt_at ? localTime(job.next_attempt_at) : null;
  const tries = Math.min(3, (job.attempts || 0) + 1);
  let what;
  let why;
  if (error === 'interrupted') {
    what = L(`엔진이 중간에 멈춰서 ${next || '곧'} 다시 시도해요.`, `The engine stopped midway; retrying ${next ? 'at ' + next : 'soon'}.`);
    why = L('엔진이 다시 시작되면서 처리 중이던 단계가 끊겼어요. 시도 횟수는 늘리지 않았어요.', 'The engine restarted while this step was running. The attempt count was not increased.');
  } else {
    what = stageKey
      ? L(`${stageLabel(stageKey)} 단계에서 실패해 ${next || '곧'} 다시 시도해요 (3번 중 ${tries}번째).`,
        `${stageLabel(stageKey)} failed; retrying ${next ? 'at ' + next : 'soon'} (attempt ${tries} of 3).`)
      : L(`처리에 실패해 ${next || '곧'} 다시 시도해요 (3번 중 ${tries}번째).`, `Processing failed; retrying ${next ? 'at ' + next : 'soon'} (attempt ${tries} of 3).`);
    why = stageKey && STAGES.some((s) => s[0] === stageKey)
      ? L(`${stageLabel(stageKey)} 단계가 제한 시간을 넘겼어요.`, `The ${stageLabel(stageKey)} step exceeded its time limit.`)
      : L('원인은 아직 몰라요.', 'The cause is unknown.');
  }
  const actions = [act.retry(), act.exclude()];
  return {...base, group: 'retry', chip: {kind: 'warn', glyph: '◷', label: L('다시 시도 대기', 'Retry pending')}, what, why, codes: ['retry_wait', codeText(error)].filter(Boolean), actions};
}

function failed(job, base, settings) {
  const error = String(job.last_error || '');
  const chip = {kind: 'err', glyph: '✕', label: L('실패', 'Failed')};
  const codes = ['failed', codeText(error)].filter(Boolean);
  switch (error) {
    case 'max_attempts':
      return {...base, group: 'failed', chip, codes, what: L('3번 시도했지만 모두 끝내지 못했어요.', 'All 3 attempts failed to finish.'),
        why: L('원인은 아래 실행 기록에서 볼 수 있어요. 정확한 원인은 아직 몰라요.', 'The run history below shows where each attempt stopped. The exact cause is unknown.'),
        how: L('이어서 처리하면 끝난 단계(변환·화자 분리·언어 감지)는 다시 쓰고 멈춘 곳부터 해요.', 'Resume reuses finished steps (convert, speakers, language) and continues where it stopped.'),
        actions: [act.resume(), act.redo(), act.exclude()], history: true};
    case 'unsupported_language':
      return {...base, group: 'failed', chip, codes, what: L('처리를 멈췄어요.', 'Processing stopped.'),
        why: L('말의 대부분이 한국어·영어가 아닌 언어로 들렸어요. 지원하는 언어는 한국어와 영어예요.', 'Most speech sounded like a language other than Korean or English, which are the supported languages.'),
        how: L('실제로 한국어나 영어 회의라면 언어를 고정하고 다시 처리해요. 받아쓰기부터 다시 해요.', 'If it really is Korean or English, pin the language and reprocess. It restarts from transcription.'),
        actions: [act.pin(), act.exclude()]};
    case 'tool_use_detected':
      return {...base, group: 'failed', chip: {...chip, label: L('실패 · 보안', 'Failed · security')}, codes,
        what: L('요약 중에 바로 멈췄어요. 노트는 바꾸지 않았어요.', 'Stopped at once during summarising. No note was changed.'),
        why: L('요약 엔진이 파일 읽기나 명령 실행을 하려 했어요. 막아 둔 동작이라 즉시 중단하고 기록했어요. 대화록 속 문장이 지시처럼 읽혔을 수 있어요.',
          'The engine tried to read files or run a command. That is blocked, so the run stopped and was logged. A sentence in the transcript may have read like an instruction.'),
        how: L('요약만 다시 하면 같은 순서로 다시 시도해요. 이 경우엔 다음 엔진으로 넘기지 않아요. 반복되면 이 엔진을 끄거나 녹음을 제외해 주세요.',
          'Re-summarize tries again in the same order; this error never falls through to the next engine. If it repeats, turn this engine off or exclude the recording.'),
        actions: [act.resummarize(false), act.exclude()]};
    case 'context_too_long':
      return {...base, group: 'failed', chip, codes, what: L('요약하지 못했어요. 대화록은 있어요.', 'Couldn\'t summarise. The transcript exists.'),
        why: L('대화록이 켜 둔 모든 요약 엔진의 입력 한도보다 길어요.', 'The transcript exceeds the input limit of every enabled engine.'),
        how: L('엔진 설정을 바꾼 뒤 요약만 다시 할 수 있어요.', 'Change engine settings, then re-summarize.'),
        actions: [act.resummarize(false), act.link('/settings#providers', L('요약 엔진 설정', 'Engine settings'))]};
    case 'interrupted_repeatedly':
      return {...base, group: 'failed', chip, codes, what: L('엔진이 처리 도중 여러 번 멈췄어요.', 'The engine stopped midway several times.'),
        why: L('같은 녹음을 처리하다 엔진이 3번 다시 시작됐어요. 원인은 아직 몰라요.', 'The engine restarted 3 times while processing this recording. The cause is unknown.'),
        how: L('이어서 처리하면 끝난 단계는 다시 쓰고 멈춘 곳부터 해요.', 'Resume reuses finished steps and continues where it stopped.'),
        actions: [act.resume(), act.exclude()]};
    case 'audio_decode':
      return {...base, group: 'failed', chip, codes, what: L('녹음을 읽지 못했어요.', 'Couldn\'t read the recording.'),
        why: L('변환한 소리의 길이가 파일에 적힌 길이와 다르거나, 디코드가 안 돼요.', 'The decoded length differs from the length in the file, or it could not be decoded.'),
        how: L('폰의 원본이 온전한지 확인해 주세요. 이 오류는 다시 처리해도 같아요.', 'Check that the original on the phone is intact. Reprocessing gives the same error.'),
        actions: [act.exclude()]};
    case 'note_conflict':
      return {...base, group: 'failed', chip, codes, what: L('볼트에 노트를 쓰지 않았어요.', 'Nothing was written to the vault.'),
        why: L('볼트의 노트가 엔진이 마지막으로 본 내용과 달라서, 덮어쓰지 않고 멈췄어요.', 'The note in the vault differs from what the engine last saw, so it stopped instead of overwriting.'),
        how: L('볼트의 노트를 확인한 뒤 요약만 다시 해 주세요.', 'Check the note in the vault, then re-summarize.'),
        actions: [act.resummarize(false), act.exclude()]};
    default:
      if (error.startsWith('ModelMissing')) {
        return {...base, group: 'failed', chip, codes, what: L('받아쓰기 모델이 없어요.', 'A transcription model is missing.'),
          why: L('필요한 모델을 이 Mac에서 찾지 못했어요.', 'A required model was not found on this Mac.'),
          how: L('설정 2단계에서 모델을 받은 뒤 이어서 처리해요.', 'Download the models in setup step 2, then resume.'),
          actions: [act.link('/setup/2', L('모델 받기', 'Download models')), act.resume(), act.exclude()]};
      }
      return {...base, group: 'failed', chip, codes, what: L('처리를 멈췄어요.', 'Processing stopped.'),
        why: L('원인은 아직 몰라요.', 'The cause is unknown.'), how: L('이어서 처리하거나 처음부터 다시 해 볼 수 있어요.', 'You can resume or redo from scratch.'),
        actions: [act.resume(), act.redo(), act.exclude()]};
  }
}

function skipped(job, settings, length) {
  const chip = {kind: 'idle', glyph: '↷', label: L('건너뜀', 'Skipped')};
  const code = `skipped:${job.skip_reason}`;
  const notProcessed = L('처리하지 않았어요.', 'Not processed.');
  switch (job.skip_reason) {
    case 'too_short': {
      const min = settings.min_duration_sec;
      return {group: 'skipped', chip, codes: [code], what: notProcessed,
        why: length && min !== undefined ? L(`${length}라 최소 길이(${dur(min)})보다 짧아요.`, `It is ${length}, under the ${dur(min)} minimum.`)
          : L('최소 길이보다 짧아요.', 'Shorter than the minimum length.'),
        actions: [act.process()]};
    }
    case 'no_speech':
      return {group: 'skipped', chip, codes: [code], what: L('받아 적을 말소리가 없었어요.', 'No speech to transcribe.'),
        why: L('녹음 전체에서 말하는 구간을 찾지 못했어요. 주머니 속 녹음일 수 있어요.', 'No speech segments were found anywhere. It may be a pocket recording.'),
        actions: [act.process()]};
    case 'before_cutoff':
      return {group: 'skipped', chip, codes: [code], what: notProcessed,
        why: settings.since ? L(`설치 시각(${settings.since}) 전에 녹음된 파일이에요.`, `Recorded before the start time (${settings.since}).`)
          : L('설치 시각 전에 녹음된 파일이에요.', 'Recorded before the start time.'),
        actions: [act.process()]};
    case 'user_excluded':
      return {group: 'skipped', chip, codes: [code], what: L('처리하지 않도록 직접 제외했어요.', 'You excluded this recording.'),
        why: L('사용자 요청', 'Your request'), actions: [act.include()]};
    case 'legacy_rejected':
      return {group: 'skipped', chip, codes: [code], what: notProcessed,
        why: L('이전 버전에서 형식 오류 등으로 거부된 파일이라 처리할 수 없어요.', 'Rejected by the previous version (for example a format error); it can\'t be processed.'),
        actions: [{...act.process(), kind: '', disabled: true, why: L('이전 버전이 거부한 파일은 처리할 수 없어요', 'Files rejected by the previous version cannot be processed')}]};
    default:
      return {group: 'skipped', chip, codes: [code], what: notProcessed, why: L('원인은 아직 몰라요.', 'The cause is unknown.'), actions: [act.include()]};
  }
}

// Run a button action against the API. Throws ApiError (409 carries the current status).
export async function runAction(job, id, argument) {
  const id_ = job.job_id;
  switch (id) {
    case 'resume': return post(jobPath(id_, 'process'), {mode: 'resume'});
    case 'from_transcribe': return post(jobPath(id_, 'process'), {mode: 'from_transcribe'});
    case 'resummarize': return post(jobPath(id_, 'process'), {mode: 'resummarize'});
    case 'retry':
    case 'process': return post(jobPath(id_, 'process'), {mode: 'auto'});
    case 'exclude': return post(jobPath(id_, 'exclude'));
    case 'include': return post(jobPath(id_, 'include'));
    default: throw new Error('unknown action ' + id + String(argument || ''));
  }
}
