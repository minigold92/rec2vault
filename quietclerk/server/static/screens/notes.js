// Minutes list: find a recording's minutes (design: docs/ui/notes.html).
// Data: /api/jobs (jobs that have a note). Not in the API yet: note titles, types, languages and the
// draft/reviewed state (proposal: GET /api/notes), so rows are named by the recording and the type and
// language filters are shown off with their reason.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {subscribe} from '../lib/live.js';
import {btn, chip, code, banner, empty} from '../lib/ui.js';
import {loadJobs} from '../lib/jobs.js';
import {dur, shortDate} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

const reasonsOf = (job) => {
  try {
    const list = JSON.parse(job.review_reasons || '[]');
    return Array.isArray(list) ? list : [];
  } catch (_) {
    return [];
  }
};

export async function mount({content}) {
  setTitle('회의록 · QuietClerk', 'Notes · QuietClerk');
  const state = {jobs: [], query: '', onlyReview: false};
  let signature = null;

  async function load() {
    try {
      state.jobs = await loadJobs();
    } catch (_) { /* keep the last list */ }
    render();
  }

  function visible() {
    const query = state.query.trim().toLowerCase();
    return state.jobs
      .filter((job) => job.note_path)
      .filter((job) => !query || String(job.source_name).toLowerCase().includes(query))
      .filter((job) => !state.onlyReview || reasonsOf(job).length)
      .sort((a, b) => String(b.recorded_at).localeCompare(String(a.recorded_at)));
  }

  function filters() {
    return h('form', {class: 'row', role: 'search', 'aria-label': L('회의록 찾기', 'Find notes'), on: {submit: (event) => event.preventDefault()}},
      h('label', {class: 'sr-only', for: 'q'}, L('녹음 이름으로 찾기', 'Search recording names')),
      h('input', {class: 'input mid', id: 'q', type: 'search', value: state.query, placeholder: L('녹음 이름으로 찾기', 'Search recording names'),
        on: {input: (event) => { state.query = event.target.value; renderList(); }}}),
      h('label', {class: 'sr-only', for: 'ft'}, L('유형', 'Type')),
      h('select', {class: 'input compact', id: 'ft', disabled: true, 'aria-describedby': 'nf-why'}, h('option', null, L('모든 유형', 'All types'))),
      h('label', {class: 'sr-only', for: 'fl'}, L('언어', 'Language')),
      h('select', {class: 'input compact', id: 'fl', disabled: true, 'aria-describedby': 'nf-why'}, h('option', null, L('모든 언어', 'All languages'))),
      h('label', {class: 'check small'},
        h('input', {type: 'checkbox', checked: state.onlyReview, on: {change: (event) => { state.onlyReview = event.target.checked; renderList(); }}}),
        h('span', null, L('확인 필요만', 'Needs review only'))),
      h('span', {class: 'why', id: 'nf-why'}, L('유형·언어·제목은 노트 목록 API(GET /api/notes)가 생기면 쓸 수 있어요.', 'Type, language and title need the notes API (GET /api/notes).')));
  }

  const listHost = h('div', {class: 'slot'});

  function renderList() {
    const rows = visible();
    replace(listHost, h('section', {class: 'list', 'aria-labelledby': 'nl-h'},
      h('div', {class: 'list-head'}, h('h2', {id: 'nl-h'}, L('엔진이 쓴 회의록', 'Minutes written by the engine')), h('span', {class: 'muted'}, L(`${rows.length}개`, String(rows.length)))),
      rows.length ? rows.map((job) => {
        const reasons = reasonsOf(job);
        return h('div', {class: 'item'},
          h('div', null, h('a', {class: 't', href: `/notes/${encodeURIComponent(job.job_id)}`}, job.source_name),
            h('div', {class: 'meta'}, h('span', null, shortDate(job.recorded_at)), job.duration_sec ? h('span', null, dur(job.duration_sec)) : null,
              job.status !== 'done' ? h('span', null, L('다시 만드는 중', 'Being redone')) : null)),
          h('div', {class: 'side-r'}, reasons.length ? chip('warn', '!', L(`확인 필요 ${reasons.length}`, `${reasons.length} to check`)) : null));
      }) : h('div', {class: 'item full'}, h('p', {class: 'small muted'}, L('조건에 맞는 회의록이 없어요.', 'No minutes match.')))));
    syncEngineControls(listHost);
  }

  function render() {
    const total = state.jobs.filter((job) => job.note_path).length;
    const pending = state.jobs.filter((job) => job.status === 'retry_wait' && job.blocked_reason === 'vault_migration').length;
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('회의록', 'Notes'))),
      h('p', {class: 'promise'}, L('회의록은 초안이에요. 중요한 결정과 할 일은 근거를 확인해 주세요.', 'Minutes are drafts. Check the evidence before relying on decisions and tasks.')),
      pending ? banner('warn', '!', [h('b', null, L(`새 회의록 ${pending}개를 아직 볼트에 넣지 않았어요.`, `${pending} new note(s) aren't in your vault yet.`)), ' ',
        L('볼트에 이전 형식 노트가 있어서, 새 형식으로 옮긴 뒤에 넣어요.', 'Your vault still has old-format notes; new notes go in after conversion.'), ' ', code('blocked_reason=vault_migration')],
      [btn({small: true, href: '/migrate', label: L('노트 옮기기', 'Convert notes')})]) : null,
      total ? [filters(), listHost] : h('section', {class: 'card'}, empty({bubble: L('아직 쓴 회의록이 없어요.', 'No minutes yet.'),
        text: L('폰에서 5분 넘게 녹음하고 저장하면, 받아 적어서 여기와 볼트에 초안을 둘게요.', 'Record over 5 minutes on your phone and save it; a draft will appear here and in your vault.'),
        actions: [btn({href: '/home', label: L('진행 상황 보기', 'See progress')}), btn({href: '/backlog', label: L('폰에 있던 녹음 고르기', 'Pick older recordings')})]})));
    if (total) renderList();
    syncEngineControls(content);
  }

  onLang(render);
  subscribe((l) => {
    const sig = l.snapshot ? JSON.stringify(l.snapshot.jobs) : '';
    if (sig !== signature) {
      signature = sig;
      load();
    }
  });
  await load();
}
