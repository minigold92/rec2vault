// Speaker names, merges and line edits (contract §10.8 A/B): the requests, and the words for what the server refuses.
// Every write rewrites the minutes note on the engine, so writes go one at a time: a second one started while the
// first is still rewriting would meet 409 job_running for no real reason.
import {get, put, post, del, jobPath} from './api.js';
import {L} from './i18n.js';
import {apiProblem} from './ui.js';

let tail = Promise.resolve();
const queued = (task) => {
  const run = tail.then(task);
  tail = run.catch(() => {});
  return run;
};

const part = encodeURIComponent;
export const readSpeakers = (jobId) => get(jobPath(jobId, 'speakers'));
export const readLines = (jobId) => get(jobPath(jobId, 'transcript'));
export const nameSpeaker = (jobId, label, name, confirmed) =>
  queued(() => put(jobPath(jobId, `speakers/${part(label)}`), {name, confirmed}));
export const mergeSpeaker = (jobId, from, into) => queued(() => post(jobPath(jobId, 'speakers/merge'), {from, into}));
export const saveLine = (jobId, id, text) => queued(() => put(jobPath(jobId, `transcript/${part(id)}`), {text}));
export const restoreLine = (jobId, id) => queued(() => del(jobPath(jobId, `transcript/${part(id)}`)));

// 409 {"error": "override_conflict", "reason": ...}: why the server will not change this meeting now.
const WHY = {
  job_running: ['지금 이 회의를 처리하고 있어요. 끝난 뒤에 다시 해 주세요.', 'This meeting is being processed right now. Try again when it is done.'],
  processing_data_deleted: ['처리 데이터를 지워서 고칠 수 없어요.', 'The processing data was deleted, so this can\'t be changed.'],
  vault_migration: ['회의록 폴더의 노트를 아직 새 형식으로 옮기지 않았어요. 설정의 ‘이전 형식 노트 옮기기’를 먼저 해 주세요.', 'The notes in your vault have not been converted to the new format yet. Do ‘Convert old-format notes’ in Settings first.'],
  note_missing: ['볼트에서 이 회의록 노트를 찾지 못해 고칠 수 없어요.', 'The note for this meeting is not in your vault, so it can\'t be changed.'],
  job_changed: ['그새 회의가 바뀌었어요. 화면을 새로 고친 뒤 다시 해 주세요.', 'The meeting changed in the meantime. Reload this page and try again.'],
  artifact_unavailable: ['엔진이 보관한 결과를 읽지 못했어요.', 'The engine could not read its kept result.'],
  transcript_unavailable: ['이 회의의 대화록 결과가 아직 없어요.', 'This meeting has no transcript result yet.'],
  merge_cycle: ['이미 합쳐진 화자끼리는 서로 합칠 수 없어요.', 'Speakers that are already merged can\'t be merged into each other.'],
};
const has = (reason) => Object.prototype.hasOwnProperty.call(WHY, reason);
const short = (value, limit) => String(value).slice(0, limit);

// What to tell the user about a failed request: {text, code, running (the job is being processed), reason, reload}.
export function refusal(error) {
  const body = error && error.body && typeof error.body === 'object' ? error.body : null;
  if (error && error.status === 409 && body && body.error === 'override_conflict') {
    const reason = short(body.reason, 60);
    return {text: has(reason) ? L(...WHY[reason]) : L('요청을 받지 않았어요.', 'Request not accepted.'), code: `409 ${reason}`,
      running: reason === 'job_running', reason, reload: reason === 'job_changed'};
  }
  const problem = apiProblem(error || {status: 0});
  const detail = body && typeof body.error === 'string' && error.status === 400 ? ` ${short(body.error, 80)}` : '';
  return {text: problem.what, code: problem.code + detail, running: false, reason: null, reload: false};
}
