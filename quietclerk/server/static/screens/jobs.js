// Jobs: fix what failed, is blocked, is waiting to retry or was skipped (design: docs/ui/jobs.html).
// Data: /api/jobs (all pages), /api/providers + /api/settings (reasons), POST /api/jobs/{id}/process|exclude|include,
// PUT /api/jobs/{id}/language. Not in the API yet: the list of files the engine refused (files.intake_status
// = rejected / waiting), so that section is shown as unavailable with the missing endpoint named.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get} from '../lib/api.js';
import {subscribe} from '../lib/live.js';
import {btn, chip, code, empty} from '../lib/ui.js';
import {describe, loadJobs} from '../lib/jobs.js';
import {jobCard, makeActions} from '../lib/cards.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';

const SECTIONS = [
  ['blocked', '막힘', 'Blocked', '사람이 손대야 풀려요', 'Needs you to act'],
  ['failed', '실패', 'Failed', '자동으로 다시 하지 않아요', 'Won\'t retry by itself'],
  ['retry', '재시도 대기', 'Retry pending', '정해진 시각에 다시 해요', 'Retries at a set time'],
  ['skipped', '건너뜀', 'Skipped', '정책상 처리하지 않은 녹음', 'Not processed by policy'],
];
const PAGE = 20;

export async function mount({content}) {
  setTitle('작업 · QuietClerk', 'Jobs · QuietClerk');
  const state = {jobs: [], providers: [], settings: {}, filter: 'all', notice: null, shown: {}};
  let signature = null;

  async function load() {
    const quiet = (promise) => promise.catch(() => null);
    const [jobs, providers, settings] = await Promise.all([quiet(loadJobs()), quiet(get('/api/providers')), quiet(get('/api/settings'))]);
    if (jobs) state.jobs = jobs;
    if (providers) state.providers = providers.items;
    if (settings) state.settings = settings.effective;
    render();
  }

  const actions = makeActions({after: load, notice: (node) => { state.notice = node; render(); }});

  function grouped() {
    const env = {providers: state.providers, settings: state.settings};
    const groups = Object.fromEntries(SECTIONS.map(([key]) => [key, []]));
    for (const job of state.jobs) {
      if (job.status === 'skipped' && !job.source_name) continue;   // deleted recordings keep only a fingerprint
      const view = describe(job, env);
      if (groups[view.group]) groups[view.group].push({job, view});
    }
    for (const list of Object.values(groups)) list.sort((a, b) => b.job.updated_at - a.job.updated_at);
    return groups;
  }

  function filters(groups, total) {
    const options = [['all', L(`전체 ${total}`, `All ${total}`)],
      ...SECTIONS.map(([key, ko, en]) => [key, L(`${ko} ${groups[key].length}`, `${en} ${groups[key].length}`)])];
    return h('div', {class: 'seg', role: 'radiogroup', 'aria-label': L('보기', 'Filter')},
      options.map(([key, label]) => h('label', null,
        h('input', {type: 'radio', name: 'filter', value: key, checked: state.filter === key, on: {change: () => { state.filter = key; render(); }}}),
        h('span', null, label))),
      h('label', null, h('input', {type: 'radio', name: 'filter', value: 'rejected', disabled: true}),
        h('span', null, L('받지 않은 파일 —', 'Not accepted —'))));
  }

  function explain() {
    const rows = [
      [L('이어서 처리', 'Resume'), L('끝난 단계 결과를 다시 쓰고 멈춘 곳부터 해요.', 'Reuses finished steps and continues where it stopped.')],
      [L('처음부터 다시', 'Redo from scratch'), L('언어 감지부터 다시 해요. 화자 분리는 입력이 같으면 다시 써요.', 'Restarts from language detection. Speaker separation is reused if unchanged.')],
      [L('요약만 다시', 'Re-summarize only'), L('분류·요약만 다시 하고 노트의 생성 구간만 바꿔요. 직접 고친 할 일·메모는 남아요.', 'Redoes classify and summary and replaces only the generated part of the note. Your task edits and notes stay.')],
      [L('언어 고정', 'Pin language'), L('이 녹음의 언어를 정하고 받아쓰기부터 다시 해요.', 'Sets this recording\'s language and redoes transcription.')],
      [L('제외', 'Exclude'), L('처리하지 않아요. 처리 중이면 지금 단계가 끝난 뒤 멈춰요.', 'Won\'t be processed. If running, stops after the current step.')],
    ];
    return h('details', {class: 'card tight'}, h('summary', {class: 'summary-strong'}, L('버튼이 하는 일', 'What each button does')),
      h('dl', {class: 'kv small top-gap'}, rows.flatMap(([term, text]) => [h('dt', null, h('b', null, term)), h('dd', null, text)])),
      h('p', {class: 'small muted'}, L('새 결과가 완성되기 전에는 기존 회의록을 지우지 않아요.', 'Existing minutes are kept until a new result is complete.')));
  }

  function section([key, ko, en, noteKo, noteEn], list) {
    if (!list.length || (state.filter !== 'all' && state.filter !== key)) return null;
    const limit = state.shown[key] || PAGE;
    return h('section', {class: 'stack', 'aria-labelledby': `h-${key}`},
      h('div', {class: 'row'}, h('h2', {id: `h-${key}`}, L(ko, en)), h('span', {class: 'small muted'}, L(noteKo, noteEn))),
      h('div', {class: 'grid g2 top'}, list.slice(0, limit).map(({job, view}) => jobCard(job, view, actions, {mono: true}))),
      list.length > limit ? btn({small: true, label: L(`${list.length - limit}개 더 보기`, `${list.length - limit} more`), on: {click: () => { state.shown[key] = limit + PAGE; render(); }}}) : null);
  }

  function rejectedFiles() {
    if (state.filter !== 'all') return null;
    return h('section', {class: 'list', 'aria-labelledby': 'rj-h'},
      h('div', {class: 'list-head'}, h('h2', {id: 'rj-h'}, L('받지 않은 파일', 'Files not accepted')),
        h('span', {class: 'muted small'}, L('작업이 아니라서 버튼으로 처리할 수 없어요', 'Not jobs, so no button can process them'))),
      h('div', {class: 'item full'}, h('div', {class: 'stack'},
        h('div', {class: 'row gap6'}, chip('idle', '—', L('아직 지원 안 함', 'Not supported yet')),
          code('GET /api/files')),
        h('p', {class: 'small'}, L('엔진이 받지 않은 파일(너무 큼 · 오디오가 아님 · 빈 파일 등)을 알려 주는 API가 아직 없어서 여기에 보일 수 없어요. 폰의 원본 녹음은 그대로 있고, 엔진은 받는 폴더의 파일을 옮기거나 지우지 않아요.',
          'There is no API yet that lists files the engine refused (too big, not audio, empty…), so they can\'t be shown here. Originals on the phone are untouched, and the engine never moves or deletes files in the inbox.')))));
  }

  function render() {
    const groups = grouped();
    const total = SECTIONS.reduce((sum, [key]) => sum + groups[key].length, 0);
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('작업', 'Jobs'))),
      state.notice,
      filters(groups, total), explain(),
      SECTIONS.map((def) => section(def, groups[def[0]])),
      total ? null : h('section', {class: 'card'}, empty({bubble: L('손볼 작업이 없어요.', 'Nothing needs fixing.'),
        text: L('실패하거나 건너뛴 녹음이 생기면 이유와 고치는 방법을 여기 모아 둘게요.', 'If a recording fails or is skipped, the reason and the fix will show up here.')})),
      rejectedFiles());
    syncEngineControls(content);
  }

  onLang(render);
  subscribe((l) => {
    const sig = l.snapshot ? JSON.stringify([l.snapshot.jobs]) : '';
    if (sig !== signature) {
      signature = sig;
      load();
    } else {
      syncEngineControls(content);
    }
  });
  await load();
}
