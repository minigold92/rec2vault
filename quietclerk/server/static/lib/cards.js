// Job cards and the actions behind their buttons, shared by Home, Jobs and the minutes screen.
import {h} from './dom.js';
import {L} from './i18n.js';
import {get, put, post, jobPath} from './api.js';
import {banner, btn, chip, code, problemBlock, announce, apiProblem} from './ui.js';
import {runAction, jobName, fileNote} from './jobs.js';
import {dur, shortDate, shortEpoch} from './fmt.js';
import {openConversion} from './note-conversion.js';

export const statusWord = (status) => ({
  running: L('처리 중', 'processing'), queued: L('대기', 'queued'), retry_wait: L('다시 시도 대기', 'retry pending'),
  failed: L('실패', 'failed'), skipped: L('건너뜀', 'skipped'), done: L('완료', 'done'),
}[status] || String(status));

// A 409 means the job changed state before the request arrived: say so, with the current state.
export function conflictBanner(job, error) {
  const status = error.body && error.body.status;
  const name = job.source_name || job.job_id;
  return banner('err', '!', [
    h('b', null, L('요청을 받지 않았어요.', 'Request not accepted.')), ' ',
    L(`${name}는 그새 상태가 바뀌어 지금은 할 수 없어요. 지금 상태: ${statusWord(status)}.`,
      `${name} changed state in the meantime, so this isn't allowed now. Current state: ${statusWord(status)}.`),
    ' ', code(`409 status=${status}`),
  ]);
}

export function problemBanner(error) {
  const p = apiProblem(error);
  return banner('err', '!', [h('b', null, p.what), ' ', code(p.code)]);
}

// "Re-check sign-in": read the provider status again; if one enabled engine can work now, resume the jobs.
export async function recheckLogin(jobs) {
  const providers = (await get('/api/providers')).items;
  const settings = (await get('/api/settings')).effective;
  const order = settings['providers.order'] || [];
  if (!providers.some((p) => p.installed && p.logged_in !== false && order.includes(p.name))) {
    return {usable: false, banner: banner('warn', '!', [h('b', null, L('아직 로그인이 안 됐어요.', 'Still signed out.')), ' ',
      L('터미널에서 로그인한 뒤 다시 눌러 주세요.', 'Sign in in Terminal, then press this again.')])};
  }
  for (const job of jobs) {
    try {
      await runAction(job, 'resume');
    } catch (error) {
      if (error.status !== 409) throw error;   // changed state meanwhile: nothing to resume
    }
  }
  return {usable: true};
}

// Builds the click handlers. `after` reloads the screen's data; `notice(node|null)` shows/clears a banner.
export function makeActions({after, notice}) {
  const previews = new Set();
  const fail = (job, error) => notice(error.status === 409 ? conflictBanner(job, error) : problemBanner(error));
  return {
    async run(job, id) {
      if (id === 'convert-note') {
        if (previews.has(job.job_id)) return;
        previews.add(job.job_id);
        try { await openConversion(job, {notice, after}); }
        finally { previews.delete(job.job_id); }
        return;
      }
      notice(null);
      try {
        if (id === 'recheck') {
          const result = await recheckLogin([job]);
          if (!result.usable) {
            notice(result.banner);
            return;
          }
        } else {
          await runAction(job, id);
        }
        announce(L('요청을 보냈어요.', 'Request sent.'));
        await after();
      } catch (error) {
        fail(job, error);
      }
    },
    async pin(job, value) {
      notice(null);
      if (!value) return;
      try {
        await put(jobPath(job.job_id, 'language'), {override: value === 'auto' ? null : value});
        await post(jobPath(job.job_id, 'process'), {mode: 'from_transcribe'});
        announce(L('언어를 고정하고 받아쓰기부터 다시 시작했어요.', 'Language pinned; restarting from transcription.'));
        await after();
      } catch (error) {
        fail(job, error);
      }
    },
  };
}

export function languageSelect(job, handlers, {auto} = {}) {
  return h('label', {class: 'small row gap6'},
    h('span', null, L('언어 고정', 'Pin language')),
    h('select', {class: 'input compact', 'data-engine': '', on: {change: (event) => handlers.pin(job, event.target.value)},
      value: job.language_override || (auto ? 'auto' : '')},
    h('option', {value: auto ? 'auto' : ''}, auto ? L('자동', 'Auto') : L('고르기', 'Choose')),
    h('option', {value: 'ko'}, L('한국어', 'Korean')),
    h('option', {value: 'en'}, 'English')));
}

function control(job, action, handlers) {
  if (action.href) return btn({small: true, href: action.href, label: action.label});
  if (action.id === 'pin') return languageSelect(job, handlers);
  const button = btn({small: true, kind: action.kind, icon: action.icon, label: action.label, engine: !action.disabled,
    disabled: action.disabled, on: action.disabled ? null : {click: () => handlers.run(job, action.id)}});
  return action.why ? h('span', {class: 'row gap6'}, button, h('span', {class: 'why'}, action.why)) : button;
}

// Run history for a job that ran out of attempts, fetched when the user opens it.
function history(job) {
  const body = h('div', {class: 'history'});
  let loaded = false;
  const load = async (event) => {
    if (!event.target.open || loaded) return;
    loaded = true;
    try {
      const {runs} = await get(jobPath(job.job_id));
      const rows = runs.filter((run) => run.status !== 'running');
      const head = [['시도', 'Attempt'], ['시작', 'Started'], ['멈춘 단계', 'Stopped at'], ['결과', 'Result']];
      body.replaceChildren(h('div', {class: 'table-wrap top-gap'}, h('table', {class: 'table'},
        h('thead', null, h('tr', null, head.map(([ko, en]) => h('th', null, L(ko, en))))),
        h('tbody', null, rows.map((run, index) => {
          const stopped = (run.stages || []).find((stage) => ['failed', 'timeout', 'interrupted'].includes(stage.status));
          return h('tr', null,
            h('td', {'data-k': L('시도', 'Attempt')}, String(index + 1)),
            h('td', {'data-k': L('시작', 'Started')}, shortEpoch(run.started_at)),
            h('td', {'data-k': L('멈춘 단계', 'Stopped at')}, stopped ? stopped.stage : '—'),
            h('td', {'data-k': L('결과', 'Result')}, code(String(run.error || run.status).slice(0, 80))));
        })))));
    } catch (_) {
      body.replaceChildren(h('p', {class: 'muted top-gap'}, L('실행 기록을 받지 못했어요.', 'Couldn\'t load the run history.')));
    }
  };
  return h('details', {class: 'small', on: {toggle: load}}, h('summary', {class: 'summary-link'}, L('실행 기록', 'Run history')), body);
}

// One card per job: the name (the minutes' title when there is one, else the file name) with its state chip on the first
// line; date, length and, under a title, the file name on the second.
export function jobCard(job, view, handlers) {
  const when = [shortDate(job.recorded_at), job.duration_sec ? dur(job.duration_sec) : null].filter(Boolean).join(' · ');
  const file = fileNote(job);
  return h('article', {class: 'card tight'},
    h('div', {class: 'job-head'},
      h('div', {class: 'job-id'}, h('h3', null, jobName(job)),
        when || file ? h('p', {class: 'small muted job-meta'}, when, when && file ? ' · ' : null, file ? h('span', {class: 'mono'}, file) : null) : null),
      chip(view.chip.kind, view.chip.glyph, view.chip.label)),
    problemBlock({what: view.what, why: view.why, how: view.how, command: view.command,
      actions: view.actions.map((action) => control(job, action, handlers)), codes: view.codes}),
    view.history ? history(job) : null);
}
