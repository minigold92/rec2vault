// Home: what is happening now, what needs a look, and today's minutes (design: docs/ui/home.html).
// Data: /api/status (providers, phone), /api/events (engine, current job), /api/jobs (with each minutes' title), /api/settings,
// /api/setup/checks (free disk space). Not in the API yet: note languages. Today's minutes are listed by title, with the
// recording name beside it.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post} from '../lib/api.js';
import {live, subscribe, refreshStatus, elapsed} from '../lib/live.js';
import {btn, chip, say, empty, problemBlock, announce} from '../lib/ui.js';
import {describe, loadJobs, STAGES, stageLabel, providerLabel, jobName, fileNote, LOGIN_COMMAND} from '../lib/jobs.js';
import {jobCard, makeActions, problemBanner, recheckLogin} from '../lib/cards.js';
import {dur, clock, localTime, sameLocalDay, gigabytes, monthDayTime} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

const LOW_DISK = 2 * 1024 ** 3;

export async function mount({content}) {
  setTitle('홈 · QuietClerk', 'Home · QuietClerk');
  const state = {jobs: [], settings: {}, checks: null, notice: null};
  let signature = null;

  const quiet = (promise) => promise.catch(() => null);
  async function load() {
    const [jobs, settings, checks] = await Promise.all([quiet(loadJobs()), quiet(get('/api/settings')), quiet(get('/api/setup/checks'))]);
    if (jobs) state.jobs = jobs;
    if (settings) state.settings = settings.effective;
    if (checks) state.checks = checks;
    render();
  }

  const actions = makeActions({
    after: async () => { await refreshStatus(); await load(); },
    notice: (node) => { state.notice = node; render(); },
  });

  const tile = (key, value, detail) =>
    h('div', {class: 'tile'}, h('span', {class: 'k'}, key), h('span', {class: 'v'}, value), h('span', {class: 'd'}, detail));

  function view() {
    const snapshot = live.snapshot, status = live.status;
    const providers = status ? status.providers : [];
    return {
      snapshot, status, providers,
      engine: (snapshot && snapshot.engine) || (status && status.engine) || 'ready',
      paused: snapshot ? snapshot.paused : !!(status && status.paused),
      current: (snapshot && snapshot.current_job) || (status && status.current_job) || null,
      counts: (snapshot && snapshot.counts) || (status && status.counts) || {},
      env: {providers, settings: state.settings},
    };
  }

  function usableProviders(v) {
    const s = state.settings;
    const order = s['providers.order'] || [], consent = s['providers.consent'] || {}, allowed = s['providers.allow_unverified'] || [];
    const by = Object.fromEntries(v.providers.map((p) => [p.name, p]));
    const enabled = order.filter((name) => consent[name] && by[name]);
    const usable = enabled.filter((name) => {
      const p = by[name];
      return p.installed && p.logged_in !== false && p.tool_block !== 'unsupported'
        && (p.tool_block === 'verified' || allowed.includes(name)) && (!s['providers.local_only'] || p.endpoint_class === 'local');
    });
    return {enabled, usable, by};
  }

  function tiles(v) {
    const jobs = state.jobs;
    const doneToday = jobs.filter((j) => j.status === 'done' && sameLocalDay(j.updated_at)).length;
    const lastReceived = jobs.reduce((latest, j) => Math.max(latest, j.created_at || 0), 0);
    const when = live.lastEvent ? localTime(live.lastEvent.getTime() / 1000) : '—';
    const queued = v.counts.queued || 0;
    const sync = v.status && v.status.sync ? v.status.sync.state : null;
    const {enabled, usable} = usableProviders(v);
    const free = state.checks ? state.checks.disk_free_bytes : null;

    let engine;
    if (live.failed) engine = tile(L('엔진', 'Engine'), chip('err', '!', L('연결 끊김', 'Unreachable')), L(`아래는 ${when}에 받은 정보예요`, `Below is as of ${when}`));
    else if (v.engine === 'disk_low') engine = tile(L('엔진', 'Engine'), L('멈춤 · 공간 부족', 'Stopped · low disk'), L(`대기 ${queued}`, `${queued} queued`));
    else if (v.paused) engine = tile(L('엔진', 'Engine'), L('일시정지', 'Paused'), L('받기는 계속 · 새 처리 멈춤', 'Still receiving · no new processing'));
    else engine = tile(L('엔진', 'Engine'), L('켜짐', 'On'), L(`오늘 처리 ${doneToday} · 대기 ${queued}`, `${doneToday} done today · ${queued} queued`));

    let phone;
    if (sync === 'connected') {
      phone = tile(L('폰', 'Phone'), chip('ok', '✓', L('연결됨', 'Connected')),
        lastReceived ? L(`마지막 받은 녹음 ${localTime(lastReceived)}`, `last recording ${localTime(lastReceived)}`) : L('아직 받은 녹음 없음', 'nothing received yet'));
    } else if (sync === 'awaiting_acceptance') {
      phone = tile(L('폰', 'Phone'), chip('warn', '!', L('수락 대기', 'Waiting')), h('a', {href: '/setup/5'}, L('폰에서 폴더 수락을 마쳐 주세요', 'Finish accepting the folder on the phone')));
    } else if (sync === 'not_shared') {
      phone = tile(L('폰', 'Phone'), chip('idle', '—', L('연결 안 됨', 'Not connected')), h('a', {href: '/setup/5'}, L('폰 연결 설정으로', 'Set up the phone')));
    } else {
      phone = tile(L('폰', 'Phone'), chip('idle', '?', L('확인 못 함', 'Unknown')), L('Syncthing 상태를 읽지 못했어요', 'Couldn\'t read the Syncthing state'));
    }

    let engines;
    if (!v.providers.length) engines = tile(L('요약 엔진', 'Summary engine'), '…', L('확인 중', 'Checking'));
    else if (usable.length) {
      engines = tile(L('요약 엔진', 'Summary engine'), providerLabel(usable[0]),
        enabled[0] !== usable[0]
          ? L(`${providerLabel(enabled[0])} 로그인 필요 → 다음 순서로 처리 중`, `${providerLabel(enabled[0])} needs sign-in → using the next one`)
          : L(`순서: ${enabled.map(providerLabel).join(' → ')}`, `Order: ${enabled.map(providerLabel).join(' → ')}`));
    } else if (!enabled.length) {
      engines = tile(L('요약 엔진', 'Summary engine'), chip('idle', '—', L('정하지 않음', 'None chosen')), h('a', {href: '/settings#providers'}, L('요약 엔진 설정', 'Engine settings')));
    } else {
      engines = tile(L('요약 엔진', 'Summary engine'), chip('err', '!', L('쓸 수 없음', 'Unavailable')),
        L(`${enabled.map(providerLabel).join('·')} 모두 쓸 수 없어요`, `${enabled.map(providerLabel).join(', ')} all unusable`));
    }

    let disk;
    if (free === null) disk = tile(L('저장 공간', 'Disk'), '—', L('확인하지 못했어요', 'Couldn\'t check'));
    else if (free < LOW_DISK) disk = tile(L('저장 공간', 'Disk'), chip('err', '!', L(`${gigabytes(free)} 남음`, `${gigabytes(free)} left`)), L('2GB 아래라 처리를 멈췄어요', 'Below 2 GB, processing stopped'));
    else disk = tile(L('저장 공간', 'Disk'), L(`여유 ${gigabytes(free)}`, `${gigabytes(free)} free`), L('2GB 아래면 처리를 멈춰요', 'Processing stops below 2 GB'));
    return h('section', {class: 'grid g4', 'aria-label': L('상태 요약', 'Status overview')}, engine, phone, engines, disk);
  }

  function bubble(v) {
    const jobs = state.jobs;
    const received = jobs.filter((j) => sameLocalDay(j.created_at)).length;
    const written = jobs.filter((j) => j.status === 'done' && sameLocalDay(j.updated_at)).length;
    if (v.engine === 'disk_low') {
      return say('worry', L('공간이 모자라서 잠깐 손을 멈췄어요.', 'I\'ve stopped for now — the disk is almost full.'), L('아래에서 무엇이, 왜 멈췄는지 보세요.', 'See below for what stopped and why.'));
    }
    const running = v.current ? 1 : 0;
    const ko = received || written
      ? `오늘 녹음 ${received}개를 받아 회의록 초안 ${written}개를 썼어요.${running ? ' 하나는 지금 받아 적고 있어요.' : ''}`
      : '오늘은 받은 녹음이 아직 없어요.';
    const en = received || written
      ? `${received} recording${received === 1 ? '' : 's'} today: ${written} draft${written === 1 ? '' : 's'} written${running ? ', 1 in progress' : ''}.`
      : 'No recordings today yet.';
    return say('ok', L(ko, en), L('중요한 결정과 할 일은 근거를 확인해 주세요.', 'Check the evidence for key decisions and tasks.'));
  }

  function hero(v) {
    const job = v.current;
    const jobs = state.jobs;
    if (!job) {
      const next = jobs.filter((j) => j.status === 'queued').sort((a, b) => a.created_at - b.created_at)[0];
      return h('section', {class: 'card', 'aria-labelledby': 'now-h'},
        h('div', {class: 'card-head'}, h('h2', {id: 'now-h'}, L('지금 처리 중', 'Processing now')), chip('idle', '…', L('대기', 'Idle'))),
        h('p', null, v.paused ? L('일시정지 중이라 새 녹음은 기다려요.', 'Paused, so new recordings wait.') : L('처리할 녹음을 기다리고 있어요. 받는 폴더는 1분마다 확인해요.', 'Waiting for a recording. The inbox is checked every minute.')),
        next ? h('p', {class: 'small muted'}, L(`다음 차례: ${next.source_name}`, `Next: ${next.source_name}`)) : null);
    }
    const key = (v.snapshot && v.snapshot.stage && v.snapshot.stage.stage) || job.stage;
    const index = STAGES.findIndex((stage) => stage[0] === key);
    const fixed = job.language_override || (state.settings['language.mode'] !== 'auto' ? state.settings['language.mode'] : null);
    const language = fixed ? L(`언어 고정 ${fixed === 'ko' ? '한국어' : '영어'}`, `language pinned: ${fixed === 'ko' ? 'Korean' : 'English'}`) : L('언어 자동 감지', 'language auto');
    const next = jobs.filter((j) => j.status === 'queued').sort((a, b) => a.created_at - b.created_at)[0];
    const progress = v.snapshot && v.snapshot.last_progress;
    const known = jobs.find((j) => j.job_id === job.job_id) || job;   // the list knows the title of a job that is being redone
    const file = fileNote(known);
    // One emphasised card per screen: the stop notice takes it from this one.
    return h('section', {class: 'card' + (v.engine === 'disk_low' ? '' : ' hero'), 'aria-labelledby': 'now-h'},
      h('div', {class: 'card-head'}, h('h2', {id: 'now-h'}, L('지금 처리 중', 'Processing now')), chip('run', '●', L('처리 중', 'Processing'))),
      h('div', {class: 'stack'},
        h('div', null, h('div', {class: 'job-title'}, jobName(known)),
          h('div', {class: 'muted small'}, [L(`녹음 ${monthDayTime(job.recorded_at)}`, `Recorded ${monthDayTime(job.recorded_at)}`), job.duration_sec ? dur(job.duration_sec) : null, language].filter(Boolean).join(' · '),
            file ? [' · ', h('span', {class: 'mono'}, file)] : null)),
        h('div', {class: 'dots', 'aria-hidden': 'true'}, STAGES.map((stage, i) => h('span', {class: i < index ? 'done' : i === index ? 'now' : '', title: L(stage[1], stage[2])}))),
        h('p', {class: 'ink', 'aria-live': 'polite'}, key ? [h('b', null, stageLabel(key)), L(` · ${STAGES.length}단계 중 ${index + 1}번째`, ` · step ${index + 1} of ${STAGES.length}`)] : L('시작하는 중', 'Starting')),
        h('dl', {class: 'kv num'},
          h('dt', null, L('이 단계 경과', 'This step')), h('dd', {id: 'el-stage'}, '—'),
          h('dt', null, L('전체 경과', 'Total elapsed')), h('dd', {id: 'el-total'}, '—'),
          h('dt', null, L('마지막 진척', 'Last progress')), h('dd', null, typeof progress === 'number' ? `${Math.round(progress * 100)}%` : '—')),
        h('p', {class: 'small muted'}, L('남은 시간은 짐작하지 않아요. 단계와 지나간 시간만 보여 드려요.', 'No time-left guesses — only the stage and time elapsed.'))),
      h('div', {class: 'row'},
        btn({small: true, href: '/jobs', label: L('작업 자세히', 'Job details')}),
        btn({small: true, kind: 'danger', engine: true, label: L('이 녹음 제외', 'Exclude this recording'), on: {click: () => actions.run(job, 'exclude')}}),
        h('span', {class: 'spacer'}),
        next ? h('span', {class: 'small muted'}, L(`다음 차례: ${next.source_name}`, `Next: ${next.source_name}`)) : null),
      v.paused ? h('p', {class: 'small muted'}, L('일시정지해도 지금 작업은 끝까지 처리해요.', 'Pausing lets the current job finish.')) : null);
  }

  function diskCard(v) {
    const free = state.checks ? state.checks.disk_free_bytes : null;
    return h('section', {class: 'card alert', 'aria-labelledby': 'stop-h'},
      h('div', {class: 'card-head'}, h('h2', {id: 'stop-h'}, L('처리를 멈췄어요', 'Processing stopped')), chip('warn', '!', L('막힘 · 공간 부족', 'Blocked · low disk'))),
      problemBlock({
        what: L(`새 녹음 받기와 처리를 모두 멈췄어요. 녹음 ${v.counts.queued || 0}개가 기다려요.`, `Receiving and processing are both on hold. ${v.counts.queued || 0} recording(s) are waiting.`),
        why: free === null ? L('Mac의 여유 공간이 2GB보다 적어요. 중간 파일을 쓰다 실패할 수 있어 멈춰요.', 'The Mac has under 2 GB free. Writing working files can fail, so processing waits.')
          : L(`Mac의 여유 공간이 ${gigabytes(free)}예요. 2GB보다 적으면 중간 파일을 쓰다 실패할 수 있어 멈춰요.`, `The Mac has ${gigabytes(free)} free. Below 2 GB, writing working files can fail, so processing waits.`),
        how: L('공간을 2GB 넘게 비우면 자동으로 다시 시작해요. 이 화면에서 따로 누를 건 없어요.', 'Free more than 2 GB and it resumes on its own. Nothing to press here.'),
        actions: [btn({small: true, href: '/settings#retention', label: L('보존 설정 보기', 'Retention settings')})],
        codes: ['blocked_reason=disk_low']}));
  }

  function authCard(blocked, v) {
    const {by} = usableProviders(v);
    const names = (state.settings['providers.order'] || []).filter((n) => by[n] && by[n].logged_in === false);
    const label = names.map(providerLabel).join(', ');
    return h('article', {class: 'card tight'},
      h('div', {class: 'job-head'}, h('h3', null, L('요약 엔진에 로그인이 필요해요', 'Summary engines need sign-in')), chip('warn', '!', L('막힘 · 로그인', 'Blocked · sign-in'))),
      problemBlock({
        what: L(`녹음 ${blocked.length}개가 교정 단계 앞에서 기다려요. 받아쓰기까지는 끝났어요.`, `${blocked.length} recording(s) are waiting before the Correct step. Transcription is done.`),
        why: label ? L(`켜 둔 요약 엔진(${label})이 모두 로그인이 풀렸어요.`, `Every enabled summary engine (${label}) is signed out.`) : L('켜 둔 요약 엔진이 모두 로그인이 풀렸어요.', 'Every enabled summary engine is signed out.'),
        how: L('하나라도 로그인하면 이어서 처리해요. 시간이 지나도 저절로 풀리지 않아요.', 'Sign in to either one and processing resumes. It will not clear on its own.'),
        command: names.map((n) => LOGIN_COMMAND[n]).filter(Boolean),
        actions: [btn({small: true, icon: 'refresh', engine: true, label: L('다시 확인', 'Check again'), on: {click: () => recheck(blocked)}}),
          btn({small: true, href: '/settings#providers', label: L('요약 엔진 설정', 'Summary engine settings')})],
        codes: ['retry_wait', 'blocked_reason=auth']}));
  }

  function migrationCard(blocked) {
    return h('article', {class: 'card tight'},
      h('div', {class: 'job-head'}, h('h3', null, L('노트 옮기기가 필요해요', 'Note conversion needed')), chip('warn', '!', L('막힘 · 노트 이행', 'Blocked · note conversion'))),
      problemBlock({
        what: L(`새 회의록 ${blocked.length}개를 만들었지만 볼트에 아직 넣지 않았어요.`, `${blocked.length} new note(s) are written but not in your vault yet.`),
        why: L('볼트에 이전 형식 노트가 있어서, 새 형식으로 옮기기 전에는 볼트에 쓰지 않아요. 시도 횟수는 쓰지 않았어요.',
          'The vault still has old-format notes; nothing is written to it until they are converted. No attempt was used.'),
        how: L('노트 옮기기를 마치면 이어서 처리해요.', 'Once the note conversion is done, it continues.'),
        actions: [btn({small: true, kind: 'primary', href: '/migrate', label: L('노트 옮기기', 'Convert notes')})],
        codes: ['retry_wait', 'blocked_reason=vault_migration']}));
  }

  function providerCard(name, v) {
    const {usable} = usableProviders(v);
    const next = usable.find((n) => n !== name);
    return h('article', {class: 'card tight'},
      h('div', {class: 'job-head'}, h('h3', null, L(`${providerLabel(name)} 로그인이 끊겼어요`, `${providerLabel(name)} is signed out`)), chip('warn', '!', L('로그인 필요', 'Login needed'))),
      problemBlock({
        what: next ? L(`${providerLabel(name)}로는 요약할 수 없어요. 대신 순서상 다음인 ${providerLabel(next)}로 처리해요.`, `${providerLabel(name)} can't summarise. The next provider in your order, ${providerLabel(next)}, is used instead.`)
          : L(`${providerLabel(name)}로는 요약할 수 없어요.`, `${providerLabel(name)} can't summarise.`),
        why: L(`${providerLabel(name)}에 로그인되어 있지 않아요. 인증이 만료됐을 수 있어요.`, `${providerLabel(name)} is not signed in. The sign-in may have expired.`),
        how: L('터미널에서 아래 명령을 실행해 로그인한 뒤 확인을 눌러 주세요.', 'Run this in Terminal to sign in, then press Check.'),
        command: LOGIN_COMMAND[name],
        actions: [btn({small: true, icon: 'refresh', engine: true, label: L('다시 확인', 'Check again'), on: {click: () => refreshStatus()}})],
        codes: ['logged_in=false']}));
  }

  async function recheck(blocked) {
    state.notice = null;
    try {
      const result = await recheckLogin(blocked);
      if (!result.usable) state.notice = result.banner;
      announce(L('다시 확인했어요.', 'Checked again.'));
      await refreshStatus();
      await load();
    } catch (error) {
      state.notice = problemBanner(error);
      render();
    }
  }

  function attention(v) {
    const jobs = state.jobs;
    const cards = [];
    const blockedAuth = jobs.filter((j) => j.status === 'retry_wait' && j.blocked_reason === 'auth');
    const blockedMigration = jobs.filter((j) => j.status === 'retry_wait' && j.blocked_reason === 'vault_migration');
    const {enabled, by} = usableProviders(v);
    const signedOut = enabled.filter((n) => by[n].logged_in === false);
    if (blockedMigration.length) cards.push(migrationCard(blockedMigration));
    if (blockedAuth.length) cards.push(authCard(blockedAuth, v));
    else for (const name of signedOut) cards.push(providerCard(name, v));
    const recent = Date.now() / 1000 - 86400;
    const rank = {failed: 0, retry: 1, blocked: 1, skipped: 2};
    const rows = jobs
      .filter((j) => !(j.status === 'retry_wait' && ['auth', 'disk_low', 'vault_migration'].includes(j.blocked_reason)))
      .map((job) => ({job, d: describe(job, v.env)}))
      .filter(({job, d}) => ['failed', 'retry', 'blocked'].includes(d.group)
        || (d.group === 'skipped' && ['too_short', 'no_speech'].includes(job.skip_reason) && job.created_at > recent))
      .sort((a, b) => (rank[a.d.group] - rank[b.d.group]) || (b.job.updated_at - a.job.updated_at));
    const total = cards.length + rows.length;
    for (const {job, d} of rows.slice(0, Math.max(0, 5 - cards.length))) cards.push(jobCard(job, d, actions));
    if (!cards.length) return null;
    return h('section', {class: 'stack', 'aria-labelledby': 'att-h'},
      h('h2', {id: 'att-h'}, L('확인해 주세요', 'Needs a look'), ' ', h('span', {class: 'muted'}, String(total))),
      cards,
      total > cards.length ? btn({small: true, href: '/jobs', label: L(`작업에서 ${total - cards.length}개 더 보기`, `${total - cards.length} more in Jobs`)}) : null);
  }

  function today() {
    const done = state.jobs.filter((j) => j.status === 'done' && j.note_path && sameLocalDay(j.updated_at)).sort((a, b) => b.updated_at - a.updated_at);
    return h('section', {class: 'list', 'aria-labelledby': 'today-h'},
      h('div', {class: 'list-head counted'}, h('h2', {id: 'today-h'}, L('오늘 쓴 회의록', 'Minutes drafted today')), h('span', {class: 'count'}, String(done.length)),
        h('span', {class: 'spacer'}), btn({kind: 'ghost', small: true, href: '/notes', label: L('전체 보기', 'View all')})),
      done.length ? done.map((job) => {
        const reasons = parseReasons(job);
        const file = fileNote(job);
        return h('div', {class: 'item'},
          h('div', null, h('a', {class: 't', href: `/notes/${encodeURIComponent(job.job_id)}`}, jobName(job)),
            h('div', {class: 'meta'}, h('span', null, localTime(job.updated_at)), job.duration_sec ? h('span', null, dur(job.duration_sec)) : null,
              file ? h('span', {class: 'file mono'}, file) : null)),
          h('div', {class: 'side-r'}, reasons.length ? chip('warn', '!', L(`확인 필요 ${reasons.length}`, `${reasons.length} to check`)) : null));
      }) : h('div', {class: 'item full'}, h('p', {class: 'small muted'}, L('오늘 쓴 회의록이 아직 없어요.', 'No minutes written today yet.'))));
  }

  function parseReasons(job) {
    try {
      const list = JSON.parse(job.review_reasons || '[]');
      return Array.isArray(list) ? list : [];
    } catch (_) {
      return [];
    }
  }

  function toggle(v) {
    return v.paused
      ? btn({kind: 'primary', icon: 'play', engine: true, label: L('다시 시작', 'Resume'), on: {click: () => send('/api/resume')}})
      : btn({icon: 'pause', engine: true, label: L('일시정지', 'Pause'), on: {click: () => send('/api/pause')}});
  }

  async function send(path) {
    state.notice = null;
    try {
      await post(path);
      announce(path.endsWith('resume') ? L('다시 시작했어요.', 'Resumed.') : L('일시정지했어요.', 'Paused.'));
    } catch (error) {
      state.notice = problemBanner(error);
      render();
    }
  }

  function render() {
    const v = view();
    const first = !state.jobs.length;
    const pausedBanner = v.paused ? h('div', {class: 'banner warn', role: 'status'},
      h('span', {class: 'ic', 'aria-hidden': 'true'}, h('span', null, '‖')),
      h('div', null, h('b', null, L('처리를 잠시 멈췄어요.', 'Processing is paused.')), ' ', L('새 녹음은 계속 받아 두고, 다시 시작하면 차례대로 처리해요.', 'New recordings still arrive and wait; they\'re processed in order when you resume.')),
      h('div', {class: 'actions'}, btn({small: true, icon: 'play', engine: true, label: L('다시 시작', 'Resume'), on: {click: () => send('/api/resume')}}))) : null;
    const att = first ? h('section', {class: 'card tight'}, h('h2', null, L('처음이라면', 'Getting started')),
      h('p', {class: 'small'}, L('시험 녹음을 하나 해 보세요. 받기 → 받아쓰기 → 요약 → 노트 쓰기까지 이 화면에서 따라갈 수 있어요.', 'Try a test recording. You can follow it here from arrival to transcription, summary and note.'))) : attention(v);
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('홈', 'Home')), toggle(v)),
      pausedBanner, state.notice,
      first ? null : bubble(v),
      tiles(v),
      h('div', {class: 'hg'},
        h('div', {class: 'a-now stack gap5'},
          v.engine === 'disk_low' ? diskCard(v) : null,
          first ? h('section', {class: 'card'}, empty({bubble: L('아직 받은 녹음이 없어요.', 'No recordings yet.'),
            text: L('폰 녹음 앱에서 녹음을 저장하면 Syncthing이 이 Mac으로 옮겨 와요. 도착하면 여기서 단계별로 보여 드릴게요. 5분보다 짧은 녹음은 건너뛰어요.',
              'Save a recording in your phone\'s recorder app and Syncthing copies it to this Mac. Once it arrives you\'ll see each step here. Recordings under 5 minutes are skipped.'),
            actions: [btn({href: '/setup/5', label: L('폰 연결 확인', 'Check phone connection')}), btn({href: '/backlog', label: L('폰에 있던 녹음 보기', 'See older recordings')})]}))
            : (v.engine === 'disk_low' && !v.current ? null : hero(v))),
        h('div', {class: 'a-att stack gap4'}, att),
        h('div', {class: 'a-today'}, first ? null : today())));
    syncEngineControls(content);
    tick();
  }

  function tick() {
    const e = elapsed();
    const stage = document.getElementById('el-stage'), total = document.getElementById('el-total');
    if (e && stage && total) {
      stage.textContent = clock(e.stage);
      total.textContent = clock(e.total);
    }
  }

  onLang(render);
  subscribe((l) => {
    const sig = l.snapshot ? JSON.stringify([l.snapshot.engine, l.snapshot.paused, l.snapshot.jobs]) : '';
    if (sig !== signature) {
      signature = sig;
      load();
    } else {
      render();
    }
  });
  setInterval(tick, 1000);
  await load();
}
