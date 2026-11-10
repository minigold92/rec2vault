// Convert old-format notes (contract §7.5; design: docs/ui/migrate.html).
// Data: GET /api/notes/migration (read-only preview of the output vault, whether it is migrated, and how the last
// consented request ended) and POST /api/notes/migration {consent: true} (runs on the executor thread between
// jobs: 200 with the manifest, or 202 and this screen asks GET again). The mapping table, counts, conflicts and
// the before/after example all come from the preview; nothing here is sample data.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post} from '../lib/api.js';
import {subscribe} from '../lib/live.js';
import {btn, chip, code, banner, say, empty, meter, problemBlock, announce} from '../lib/ui.js';
import {loadJobs} from '../lib/jobs.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

// Why a conflict keeps a note from being converted (or why it is left as it is).
const CONFLICT = {
  custom_key: ['직접 만든 키', 'Your own key'], custom_value: ['표에 없는 값', 'Value not in the table'],
  key_collision: ['같은 이름으로 겹치는 키', 'Keys that collide'], invalid_date: ['날짜 형식이 맞지 않아요', 'Wrong date format'],
  identity_mismatch: ['작업 번호·해시가 엔진 기록과 달라요', 'Job ID or hash differs from the engine\'s record'],
  duplicate_job: ['같은 작업의 노트가 둘 이상이에요', 'More than one note for the same job'],
  job_missing: ['엔진이 모르는 작업의 노트예요', 'A note for a job the engine doesn\'t know'],
  invalid_frontmatter: ['머리말을 읽을 수 없어요', 'The properties block can\'t be read'],
  identity_missing: ['작업 번호가 없어요', 'No job ID'], invalid_identity: ['작업 번호 형식이 이상해요', 'The job ID looks wrong'],
};

// Why the migration request itself failed (NoteConflict reason codes from quietclerk.notes.migration).
const FAILURE = {
  migration_conflicts: [['직접 만든 값이나 겹치는 키처럼 자동으로 바꿀 수 없는 노트가 있어요.', 'Some notes can\'t be converted automatically (your own values, colliding keys…).'],
    ['아래 ‘막힘’ 항목을 고친 뒤 다시 시도해 주세요.', 'Fix the blocked items below, then try again.']],
  migration_new_candidates: [['옮기는 동안 이전 형식 노트가 새로 생겼어요.', 'A new old-format note appeared while converting.'],
    ['미리보기를 다시 확인하고 한 번 더 동의해 주세요.', 'Review the preview again and agree once more.']],
  migration_note_changed: [['옮기는 도중 노트가 바뀌었어요. 바뀐 노트는 덮어쓰지 않았어요.', 'A note changed while converting. The changed note was not overwritten.'],
    ['미리보기를 다시 확인한 뒤 이어서 옮겨요.', 'Review the preview again, then continue.']],
  migration_plan_changed: [['미리보기와 달라진 노트가 있어요.', 'A note no longer matches the preview.'], ['미리보기를 다시 확인한 뒤 이어서 옮겨요.', 'Review the preview again, then continue.']],
  migration_path_changed: [['노트 경로가 링크로 바뀌었거나 볼트 밖으로 나갔어요.', 'A note path became a link or left the vault.'], ['볼트 폴더를 확인해 주세요.', 'Check the vault folder.']],
  migration_backup_path_changed: [['백업 경로가 바뀌어 있어요. 덮어쓰지 않고 멈췄어요.', 'The backup path changed. It stopped instead of overwriting.'], ['백업 폴더를 확인해 주세요.', 'Check the backup folder.']],
  migration_backup_changed: [['백업 파일이 원래와 달라요. 덮어쓰지 않고 멈췄어요.', 'A backup file differs from the original. It stopped instead of overwriting.'], ['백업 폴더를 확인해 주세요.', 'Check the backup folder.']],
  migration_output_changed: [['회의록 폴더가 지난번 옮기기와 달라요.', 'The notes folder differs from the earlier conversion.'],
    ['설정에서 폴더를 원래대로 돌리거나 백업 폴더의 migration-*.json을 확인해 주세요.', 'Restore the folder in settings or check migration-*.json in the backup folder.']],
  backup_must_be_outside_vault: [['백업 폴더가 볼트 안에 있어요. 백업은 볼트 밖이어야 해요.', 'The backup folder is inside the vault. Backups must be outside it.'],
    ['데이터 폴더와 회의록 폴더가 서로 겹치지 않게 해 주세요.', 'Make sure the data folder and the notes folder don\'t overlap.']],
  engine_running: [['엔진이 처리 중이라 지금은 옮길 수 없어요.', 'The engine is busy, so it can\'t convert right now.'], ['잠시 뒤 다시 시도해 주세요.', 'Try again in a moment.']],
};

const fmtValue = (value) => JSON.stringify(value);

export async function mount({content}) {
  setTitle('이전 형식 노트 옮기기 · QuietClerk', 'Convert old-format notes · QuietClerk');
  const state = {data: null, error: null, consent: false, phase: 'preview', total: 0, converted: null, failure: null,
    pendingJobs: 0, manifest: null, showAll: false, loading: true};
  let timer = 0;

  const candidates = () => (state.data ? state.data.preview.entries.filter((entry) => !entry.skip) : []);
  const blocking = () => (state.data ? state.data.preview.conflicts.filter((c) => c.blocking) : []);
  const relative = (path) => (state.data && path.startsWith(state.data.preview.output + '/') ? path.slice(state.data.preview.output.length + 1) : path);

  async function refresh() {
    try {
      state.data = await get('/api/notes/migration');
      state.error = null;
    } catch (error) {
      state.error = error;
    }
    state.loading = false;
  }

  async function countBlockedJobs() {
    try {
      state.pendingJobs = (await loadJobs()).filter((job) => job.status === 'retry_wait' && job.blocked_reason === 'vault_migration').length;
    } catch (_) { /* the banner just stays general */ }
  }

  // After the first read, decide which phase the data implies (a request may already be running or have failed).
  function settle() {
    const d = state.data;
    if (!d) return;
    const task = d.task;
    if (task && task.state === 'running') state.phase = 'running';
    else if (task && task.state === 'failed') {
      state.phase = 'error';
      state.failure = task.reason;
    } else if (state.phase === 'running' && d.migrated && !candidates().length) state.phase = 'done';
    else if (state.phase === 'running' && task && task.state === 'done') state.phase = candidates().length ? 'preview' : 'done';
    else if (state.phase === 'preview' && !candidates().length && d.migrated && state.converted !== null) state.phase = 'done';
  }

  async function tick() {
    await refresh();
    settle();
    if (state.phase !== 'running') {
      clearInterval(timer);
      timer = 0;
    }
    render();
  }

  async function apply() {
    state.total = candidates().length;
    state.converted = state.total;
    state.phase = 'running';
    state.error = null;
    state.failure = null;
    render();
    try {
      const result = await post('/api/notes/migration', {consent: true});
      if (result && result.done) {
        state.manifest = result;
        await refresh();
        state.phase = 'done';
        announce(L('노트를 옮겼어요.', 'Notes converted.'));
      } else if (!timer) {
        timer = setInterval(tick, 2000);
      }
    } catch (error) {
      state.error = error;
      state.phase = 'error';
      state.failure = error.body && error.body.reason;
      await refresh();
    }
    render();
  }

  // ---- pieces
  const tile = (key, value, detail) => h('div', {class: 'tile'}, h('span', {class: 'k'}, key), h('span', {class: 'v'}, value), h('span', {class: 'd'}, detail));

  function renamed() {
    const seen = new Map();
    for (const entry of candidates()) {
      for (const row of entry.mapping || []) if (row.from_key && row.from_key !== row.to_key && !seen.has(row.from_key)) seen.set(row.from_key, row.to_key);
    }
    return [...seen];
  }

  function tiles() {
    const keys = renamed();
    const kept = state.data.preview.conflicts.filter((c) => !c.blocking).length;
    return h('section', {class: 'grid g4', 'aria-label': L('미리보기 요약', 'Preview summary')},
      tile(L('옮길 노트', 'Notes to convert'), L(`${candidates().length}개`, String(candidates().length)), L('이전 형식 · 구형(영문 job_id) 포함', 'Old format, incl. legacy job_id notes')),
      tile(L('바뀌는 속성', 'Properties renamed'), L(`${keys.length}종`, String(keys.length)), L('값 이름도 함께', 'Value names too')),
      tile(L('그대로 둘 것', 'Left unchanged'), L(`${kept}건`, String(kept)), L('직접 만든 키·값', 'Your own keys and values')),
      tile(L('백업', 'Backup'), L('볼트 밖', 'Outside vault'), h('code', null, `${state.data.preview.backup_root}/`)));
  }

  function mappingCard() {
    const keys = renamed();
    const values = state.data.preview.value_map;
    return h('section', {class: 'card', 'aria-labelledby': 'mp-h'},
      h('div', {class: 'card-head'}, h('h2', {id: 'mp-h'}, L('속성 대응표', 'Property mapping')), chip('line', '=', L('이 볼트의 노트에서 읽은 것', 'Read from the notes in this vault'))),
      h('div', {class: 'table-wrap'}, h('table', {class: 'table'},
        h('thead', null, h('tr', null, h('th', null, L('이전 키', 'Old key')), h('th', null, L('새 키', 'New key')), h('th', null, L('값 바꾸기', 'Value mapping')))),
        h('tbody', null, keys.map(([from, to]) => h('tr', null,
          h('td', {'data-k': L('이전 키', 'Old key')}, h('code', null, from)), h('td', {'data-k': L('새 키', 'New key')}, h('code', null, to)),
          h('td', {'data-k': L('값 바꾸기', 'Value mapping')}, values[to] ? Object.entries(values[to]).map(([a, b]) => `${a} → ${b}`).join(', ') : '—')))))),
      h('p', {class: 'small muted'}, L('표에 없는 키·값은 바꾸지 않고 아래 ‘그대로 둘 것’에 보여 드려요. Obsidian 보기 파일 회의록.base는 덮어쓰지 않고 새 보기 파일을 따로 만들어요.',
        'Keys and values not in the table are left alone and listed below. The Obsidian view file 회의록.base isn\'t overwritten; a new view file is created.')));
  }

  function examples() {
    const first = candidates()[0];
    if (!first || !first.mapping) return null;
    const before = first.mapping.filter((row) => row.from_key).slice(0, 8).map((row) => `${row.from_key}: ${fmtValue(row.from_value)}`).join('\n');
    const after = first.mapping.slice(0, 8).map((row) => `${row.to_key}: ${fmtValue(row.to_value)}`).join('\n');
    return h('section', {class: 'grid g2'},
      h('div', {class: 'card tight'}, h('h3', null, L('예 · 지금', 'Example · now')), h('pre', {class: 'pre'}, before)),
      h('div', {class: 'card tight'}, h('h3', null, L('옮긴 뒤', 'After')), h('pre', {class: 'pre'}, after)));
  }

  function conflictList() {
    const rows = [...state.data.preview.conflicts].sort((a, b) => Number(b.blocking) - Number(a.blocking));
    if (!rows.length) return null;
    const shown = state.showAll ? rows : rows.slice(0, 20);
    return h('section', {class: 'list', 'aria-labelledby': 'cf-h'},
      h('div', {class: 'list-head'}, h('h2', {id: 'cf-h'}, L('그대로 둘 것 · 막힌 것', 'Left unchanged · blocked')), h('span', {class: 'muted small'}, String(rows.length))),
      shown.map((c) => h('div', {class: 'item'},
        h('div', null, h('span', {class: 't mono'}, relative(c.path)),
          h('div', {class: 'meta'}, h('span', {class: 'wrap'}, CONFLICT[c.reason] ? L(CONFLICT[c.reason][0], CONFLICT[c.reason][1]) : c.reason, ' ',
            c.key !== undefined ? h('code', null, c.value !== undefined ? `${c.key}: ${typeof c.value === 'string' ? c.value : JSON.stringify(c.value)}` : String(c.key)) : null))),
        h('div', {class: 'side-r'}, c.blocking ? chip('err', '⊘', L('막힘', 'Blocked')) : chip('line', '=', L('그대로 둠', 'Kept as is')), code(c.reason)))),
      rows.length > shown.length ? h('div', {class: 'item full'}, btn({small: true, label: L(`${rows.length - shown.length}개 더 보기`, `${rows.length - shown.length} more`), on: {click: () => { state.showAll = true; render(); }}})) : null);
  }

  function consentCard() {
    const stop = blocking().length > 0;
    const why = stop ? L('막힘 항목이 있어서 옮길 수 없어요. 위 목록을 먼저 고쳐 주세요.', 'Blocked items stop the conversion. Fix the list above first.')
      : L('동의에 체크하면 켜져요.', 'Enabled once you tick the box.');
    return h('section', {class: 'card hero'},
      h('label', {class: 'check'}, h('input', {type: 'checkbox', checked: state.consent, disabled: stop, 'data-engine': stop ? null : '',
        on: {change: (event) => { state.consent = event.target.checked; render(); }}}),
      h('span', {class: 'ink'}, h('b', null, L('미리보기를 확인했어요.', 'I\'ve reviewed the preview.')), ' ',
        L(`백업을 만든 뒤 노트 ${candidates().length}개의 속성을 바꾸는 데 동의해요.`, `I agree to back up and then change properties in ${candidates().length} notes.`))),
      h('div', {class: 'row'},
        btn({kind: 'primary', engine: true, disabled: !state.consent || stop, describedby: 'mg-why', label: L('백업하고 옮기기', 'Back up and convert'), on: {click: apply}}),
        h('span', {class: 'why', id: 'mg-why'}, state.consent && !stop ? L('백업은 볼트 밖에 만들고, 노트 본문은 그대로 두고 맨 위 속성만 바꿔요.', 'The backup goes outside the vault; note bodies stay as they are and only the properties on top change.') : why),
        h('span', {class: 'spacer'}), btn({kind: 'ghost', href: '/settings', label: L('나중에 하기', 'Later')})));
  }

  function runningCard() {
    const left = candidates().length;
    const total = Math.max(state.total, left, 1);
    const done = total - left;
    return h('section', {class: 'card hero', 'aria-live': 'polite'},
      h('div', {class: 'card-head'}, h('h2', null, L('옮기는 중', 'Converting')), chip('run', '●', L('처리 중', 'Processing'))),
      meter(done / total, '', L('옮긴 노트', 'Notes converted')),
      h('p', {class: 'num ink'}, h('b', null, String(done)), ` / ${total} · `, L('백업 폴더', 'backup folder'), ': ', h('code', null, `${state.data ? state.data.preview.backup_root : ''}/`)),
      h('p', {class: 'small muted'}, L('엔진이 녹음을 처리 중이면 그 작업이 끝난 뒤에 옮기기를 시작해요. 중간에 멈춰도 다시 누르면 옮긴 다음 노트부터 이어서 해요.',
        'If the engine is processing a recording, the conversion starts after that job. If it stops, starting again continues from the next note.')));
  }

  function failureCard() {
    const reason = state.failure;
    const text = FAILURE[reason];
    const left = candidates().length;
    const done = state.total ? Math.max(0, state.total - left) : null;
    const generic = state.error && !state.failure;
    return h('article', {class: 'card alert tight'},
      h('div', {class: 'card-head'}, h('h3', null, L('옮기다가 멈췄어요', 'Conversion stopped')),
        done !== null && state.total ? chip('warn', '‖', `${done}/${state.total}`) : null),
      problemBlock({
        what: done ? L(`노트 ${done}개를 옮기고 멈췄어요. 옮긴 노트와 백업은 그대로 있어요.`, `Stopped after ${done} notes. Converted notes and the backup are intact.`)
          : L('노트를 바꾸지 않고 멈췄어요. 노트는 그대로예요.', 'Stopped without changing any note. Your notes are untouched.'),
        why: text ? L(text[0][0], text[0][1]) : generic ? L('엔진이 요청을 받지 못했어요.', 'The engine did not accept the request.') : L('원인은 아직 몰라요.', 'The cause is unknown.'),
        how: text ? L(text[1][0], text[1][1]) : L('다시 눌러 이어서 옮겨 볼 수 있어요.', 'You can press again to continue.'),
        actions: [btn({small: true, kind: 'primary', engine: true, disabled: blocking().length > 0, label: L('이어서 옮기기', 'Continue converting'), on: {click: apply}})],
        codes: [reason || (state.error ? String(state.error.status) : 'migration_interrupted')]}));
  }

  function doneCard() {
    const count = state.total || (state.manifest ? state.manifest.entries.filter((e) => e.state === 'done').length : 0);
    return h('section', {class: 'card'}, empty({
      bubble: count ? L(`노트 ${count}개를 옮겼어요.${state.pendingJobs ? ` 기다리던 새 회의록 ${state.pendingJobs}개도 곧 볼트에 넣어요.` : ''}`,
        `${count} notes converted.${state.pendingJobs ? ` The ${state.pendingJobs} waiting new note(s) go into your vault shortly.` : ''}`)
        : L('볼트의 회의록이 모두 새 형식이에요.', 'Every note in your vault already uses the new format.'),
      text: L(`백업은 ${state.manifest ? state.manifest.backup_dir : state.data.preview.backup_root}/에 있어요. 필요 없으면 직접 지워 주세요.`,
        `The backup is in ${state.manifest ? state.manifest.backup_dir : state.data.preview.backup_root}/. Delete it yourself when no longer needed.`),
      actions: [btn({href: '/notes', label: L('회의록 보기', 'View notes')})]}));
  }

  function stepper() {
    const at = state.phase === 'preview' ? 0 : 2;
    return h('ol', {class: 'stepper steps3'}, [['미리보기', 'Preview'], ['동의', 'Agree'], ['옮기기', 'Convert']].map(([ko, en], i) =>
      h('li', {class: state.phase === 'done' || i < at ? 'done' : i === at ? 'now' : ''}, h('span', {class: 'n'}, `${i + 1}/3`), h('span', {class: 's'}, L(ko, en)))));
  }

  function render() {
    const d = state.data;
    const pending = d && !d.migrated && candidates().length;
    let body;
    if (state.loading) {
      body = h('ul', {class: 'stages', 'aria-live': 'polite'}, h('li', {class: 'now'}, h('span', {class: 'mk'}), h('span', {class: 'nm'}, L('볼트의 노트를 읽는 중', 'Reading the notes in your vault')), h('span', {class: 'tm'}, '…')));
    } else if (!d) {
      const reason = state.error && state.error.body && state.error.body.reason;
      const text = FAILURE[reason];
      body = h('article', {class: 'card alert tight'}, h('div', {class: 'card-head'}, h('h3', null, L('미리보기를 만들 수 없어요', 'Couldn\'t build the preview'))),
        problemBlock({what: L('볼트의 노트를 읽지 못했어요. 아무것도 바꾸지 않았어요.', 'Couldn\'t read the notes in the vault. Nothing was changed.'),
          why: text ? L(text[0][0], text[0][1]) : L('원인은 아직 몰라요.', 'The cause is unknown.'), how: text ? L(text[1][0], text[1][1]) : null,
          actions: [btn({small: true, icon: 'refresh', engine: true, label: L('다시 시도', 'Try again'), on: {click: async () => { state.loading = true; render(); await refresh(); settle(); render(); }}})],
          codes: [reason || (state.error ? String(state.error.status) : 'engine_unreachable')]}));
    } else if (state.phase === 'running') {
      body = [candidates().length || state.total ? tiles() : null, runningCard()];
    } else if (state.phase === 'error') {
      body = [failureCard(), candidates().length ? [tiles(), conflictList()] : null];
    } else if (state.phase === 'done' || (!candidates().length && !blocking().length)) {
      body = doneCard();
    } else {
      body = [tiles(), mappingCard(), examples(), conflictList(), consentCard()];
    }
    replace(content,
      h('nav', {class: 'crumb', 'aria-label': L('위치', 'Breadcrumb')}, h('a', {href: '/settings'}, L('설정', 'Settings')), h('span', null, '›'), h('span', null, L('노트 옮기기', 'Convert notes'))),
      h('div', {class: 'topbar'}, h('h1', null, L('이전 형식 노트 옮기기', 'Convert old-format notes'))),
      pending || state.phase === 'running' || state.phase === 'error'
        ? banner('warn', '!', [h('b', null, L('옮기기 전까지는 볼트에 새 회의록을 쓰지 않아요.', 'New minutes aren\'t written to the vault until conversion.')),
          state.pendingJobs ? [' ', L(`새 회의록 ${state.pendingJobs}개가 따로 보관돼 있어요. 옮기고 나면 볼트에 넣어요.`, `${state.pendingJobs} new note(s) are kept aside and go into the vault after conversion.`)] : null], null, 'status') : null,
      state.phase === 'done' ? null : say('ok', L('노트 속성 이름을 한국어·영어 어디서나 같은 이름으로 바꿔요. 한국어 화면에서는 계속 한국어로 보여요.', 'Note properties get one language-neutral name. Korean screens still show them in Korean.'),
        L('바꾸기 전에 볼트 밖에 백업을 만들고, 동의한 뒤에만 시작해요.', 'A backup is made outside the vault first, and nothing starts until you agree.')),
      d ? stepper() : null, body);
    syncEngineControls(content);
  }

  onLang(render);
  subscribe(() => syncEngineControls(content));
  render();
  await Promise.all([refresh(), countBlockedJobs()]);
  settle();
  if (state.phase === 'running') timer = setInterval(tick, 2000);
  render();
}
