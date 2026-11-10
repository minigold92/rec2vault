// Older recordings: pick what is only on the phone, or was skipped, and process it (design: docs/ui/backlog.html).
// Data: GET /api/backlog (Syncthing need-list names + skipped jobs + inventory), POST /api/backlog/request,
// POST /api/jobs/{id}/process. The API gives names only (no size, no phone total: inventory is "partial"),
// so sizes and the total count are not shown.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, post, jobPath} from '../lib/api.js';
import {btn, chip, code, banner, say, empty, announce} from '../lib/ui.js';
import {describe} from '../lib/jobs.js';
import {conflictBanner, problemBanner} from '../lib/cards.js';
import {dur, shortDate, recordedFromName} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

export async function mount({content}) {
  setTitle('기존 녹음 · QuietClerk', 'Older recordings · QuietClerk');
  const state = {data: null, error: null, names: new Set(), jobs: new Set(), notice: null, busy: false, settings: {}};
  const barHost = h('div', {class: 'slot'});

  async function load() {
    try {
      state.data = await get('/api/backlog');
      state.error = null;
    } catch (error) {
      state.error = error;
    }
    try {
      state.settings = (await get('/api/settings')).effective;
    } catch (_) { /* reasons fall back to generic wording */ }
    render();
  }

  async function submit() {
    state.busy = true;
    state.notice = null;
    renderBar();
    let accepted = 0;
    const rejected = [];
    try {
      if (state.names.size) {
        await post('/api/backlog/request', {names: [...state.names]});
        accepted += state.names.size;
      }
      for (const id of state.jobs) {
        const job = state.data.skipped.find((j) => j.job_id === id);
        try {
          await post(jobPath(id, 'process'), {mode: 'auto'});
          accepted += 1;
        } catch (error) {
          if (error.status !== 409) throw error;
          rejected.push(job);
        }
      }
      state.names.clear();
      state.jobs.clear();
      state.notice = [
        accepted ? banner('info', 'i', [h('b', null, L(`${accepted}개를 요청했어요.`, `${accepted} requested.`)), ' ',
          L('받은 뒤 길이·형식을 확인하고 처리해요. 진행 상황은 홈에서 볼 수 있어요.', 'After fetching, length and format are checked, then they are processed. Follow progress on Home.')]) : null,
        rejected.map((job) => conflictBanner(job, {body: {status: job.status}}))];
      announce(L('요청을 보냈어요.', 'Request sent.'));
    } catch (error) {
      state.notice = problemBanner(error);
    }
    state.busy = false;
    await load();
  }

  const toggle = (set, value) => (event) => {
    if (event.target.checked) set.add(value);
    else set.delete(value);
    renderBar();
  };

  function phoneList() {
    const names = state.data.names;
    if (!names.length) return null;
    return h('section', {class: 'list', 'aria-labelledby': 'nr-h'},
      h('div', {class: 'list-head'}, h('h2', {id: 'nr-h'}, L('아직 받지 않은 녹음', 'Not fetched yet')),
        h('span', {class: 'muted small'}, L(`폰에만 있어요 · Syncthing이 알려 준 ${names.length}개`, `On the phone only · ${names.length} listed by Syncthing`)),
        h('label', {class: 'check small'}, h('input', {type: 'checkbox', 'data-engine': '', checked: names.every((name) => state.names.has(name)),
          on: {change: (event) => {
            for (const name of names) {
              if (event.target.checked) state.names.add(name);
              else state.names.delete(name);
            }
            for (const box of content.querySelectorAll('input[data-pick="name"]')) box.checked = event.target.checked;
            renderBar();
          }}}),
        h('span', null, L('모두 선택', 'Select all')))),
      names.map((name, index) => {
        const when = recordedFromName(name);
        return h('div', {class: 'item sel'},
          h('input', {type: 'checkbox', id: `n${index}`, 'data-engine': '', 'data-pick': 'name', class: 'check-lg', checked: state.names.has(name), on: {change: toggle(state.names, name)}}),
          h('div', null, h('label', {class: 't mono pointer', for: `n${index}`}, name), h('div', {class: 'meta'}, when ? h('span', null, shortDate(when)) : null)),
          h('div', {class: 'side-r'}, chip('line', '☐', L('폰에만 있음', 'Phone only'))));
      }),
      h('div', {class: 'item full'}, h('p', {class: 'small muted'},
        L('받기 전에는 녹음 길이를 알 수 없고, 크기와 폰의 전체 개수는 아직 알려 주지 않아요.', 'Length is unknown until a file is fetched, and sizes and the phone\'s total are not reported yet.'))));
  }

  function skippedList() {
    const rows = state.data.skipped.filter((job) => job.source_name);
    if (!rows.length) return null;
    return h('section', {class: 'list', 'aria-labelledby': 'sk2-h'},
      h('div', {class: 'list-head'}, h('h2', {id: 'sk2-h'}, L('받았지만 건너뛴 녹음', 'Fetched but skipped')),
        h('span', {class: 'muted small'}, L('고르면 원본을 다시 확인한 뒤 처리해요', 'Selecting re-checks the original, then processes it'))),
      rows.map((job) => {
        const view = describe(job, {settings: state.settings});
        const blocked = job.skip_reason === 'legacy_rejected';
        return h('div', {class: 'item sel'},
          h('input', {type: 'checkbox', id: `s-${job.job_id}`, 'data-engine': blocked ? null : '', class: 'check-lg', disabled: blocked,
            checked: state.jobs.has(job.job_id), on: {change: toggle(state.jobs, job.job_id)}}),
          h('div', null, h('label', {class: 't mono pointer', for: `s-${job.job_id}`}, job.source_name),
            h('div', {class: 'meta'}, h('span', null, shortDate(job.recorded_at)), job.duration_sec ? h('span', null, dur(job.duration_sec)) : null, blocked ? null : h('span', {class: 'wrap'}, view.why)),
            blocked ? h('div', {class: 'why'}, L('이전 버전에서 형식 오류로 거부된 파일이라 처리할 수 없어요.', 'Rejected by the previous version for a format error; can\'t be processed.')) : null),
          h('div', {class: 'side-r'}, chip('idle', '↷', L('건너뜀', 'Skipped')), code(job.skip_reason)));
      }));
  }

  function renderBar() {
    const n = state.names.size + state.jobs.size;
    replace(barHost, h('div', {class: 'card tight hero stickybar', role: 'region', 'aria-label': L('선택한 녹음', 'Selection')},
      h('div', {class: 'row'},
        h('b', {class: 'ink', 'aria-live': 'polite'}, n ? L(`${n}개 선택`, `${n} selected`) : L('고른 녹음이 없어요', 'Nothing selected')),
        h('span', {class: 'small muted'}, L('받은 뒤 길이·형식을 확인하고 처리해요', 'Length and format are checked after fetching')),
        h('span', {class: 'spacer'}),
        btn({small: true, engine: true, disabled: !n, label: L('선택 해제', 'Clear'), on: {click: () => {
          state.names.clear();
          state.jobs.clear();
          for (const box of content.querySelectorAll('input[type=checkbox]')) box.checked = false;
          renderBar();
        }}}),
        btn({small: true, kind: 'primary', engine: true, disabled: !n || state.busy, label: L('받아서 처리하기', 'Fetch and process'), on: {click: submit}})),
      n ? null : h('p', {class: 'why'}, L('위 목록에서 녹음을 고르면 켜져요.', 'Enabled once you pick a recording above.'))));
    syncEngineControls(barHost);
  }

  function render() {
    const data = state.data;
    const unavailable = state.error || (data && data.inventory === 'unavailable');
    const phone = data ? phoneList() : null;
    const skipped = data ? skippedList() : null;
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('기존 녹음', 'Older recordings'))),
      say('ok', L('폰에는 있지만 아직 처리하지 않은 녹음이에요. 필요한 것만 골라 주세요.', 'Recordings on your phone that haven\'t been processed. Pick only what you need.'),
        L('통화 녹음과 하위 폴더는 목록에 넣지 않아요.', 'Call recordings and subfolders are never listed.')),
      state.notice,
      unavailable ? banner('warn', '!', [h('b', null, L('폰 목록을 받지 못했어요.', 'Couldn\'t get the phone\'s list.')), ' ',
        state.error && state.error.status === 0 ? L('엔진에 닿지 못했어요.', 'Could not reach the engine.')
          : L('Syncthing이 켜져 있는지, 폰이 연결돼 있는지 봐 주세요. 이미 받은 녹음 중 건너뛴 것은 아래에서 고를 수 있어요.', 'Check that Syncthing is running and the phone is connected. You can still pick skipped recordings below.'),
        ' ', code(state.error ? `${state.error.status}` : 'inventory=unavailable')]) : null,
      phone, skipped,
      data && !phone && !skipped && !unavailable ? h('section', {class: 'card'}, empty({bubble: L('처리하지 않은 녹음이 없어요.', 'No unprocessed recordings.'),
        text: L('폰의 녹음은 모두 받아서 처리했거나 직접 제외했어요.', 'Everything on the phone has been processed or excluded.')})) : null,
      data && (phone || skipped) ? barHost : null);
    renderBar();
    syncEngineControls(content);
  }

  onLang(render);
  await load();
}
