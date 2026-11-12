// One consent flow for Home, Jobs and Minutes. Untrusted note text is always a text node.
import {h} from './dom.js';
import {L} from './i18n.js';
import {get, post, jobPath} from './api.js';
import {banner, btn, code} from './ui.js';

const REASONS = {
  artifact_unavailable: ['최신 실행의 검증된 처리 결과가 없거나 손상됐어요. 이어서 처리로 결과를 만든 뒤 다시 확인해 주세요.', 'The latest run has missing or damaged verified results. Resume processing to produce them, then try again.'],
  artifact_inputs_mismatch: ['처리 결과들이 같은 입력으로 만들어지지 않았어요. 이어서 처리한 뒤 다시 확인해 주세요.', 'The results do not share the same inputs. Resume processing, then try again.'],
  artifact_invalid: ['보관된 처리 결과의 형식이 올바르지 않아요. 이어서 처리한 뒤 다시 확인해 주세요.', 'The kept results have an invalid shape. Resume processing, then try again.'],
  conversion_changed: ['미리보기 뒤 노트나 작업이 바뀌었어요. 다시 미리보기해 주세요.', 'The note or job changed after preview. Open a fresh preview.'],
  note_name_conflict: ['새 경로에 다른 파일이 있어 바꾸지 않았어요. 볼트에서 파일 이름을 확인해 주세요.', 'Another file occupies the new path. Check filenames in your vault.'],
  note_not_migrated: ['이 노트는 이전 형식에서 옮긴 노트가 아니거나 이미 교체됐어요.', 'This note was not migrated from the old format, or has already been converted.'],
  note_already_current: ['이미 새 형식인 노트라 교체하지 않았어요.', 'This note already has the new format and was not replaced.'],
  note_missing: ['볼트에서 이 작업의 노트를 찾지 못했어요. 노트 위치를 확인해 주세요.', 'The job’s note was not found in the vault. Check its location.'],
  vault_migration: ['먼저 설정에서 이전 형식 노트 옮기기를 마쳐 주세요.', 'First finish converting old-format note properties in Settings.'],
  job_running: ['처리 중이에요. 끝난 뒤 다시 확인해 주세요.', 'Processing is running. Try again when it finishes.'],
  job_not_ready: ['이 작업은 지금 교체할 수 있는 상태가 아니에요.', 'This job is not in a state that allows conversion.'],
  processing_data_deleted: ['처리 데이터가 삭제되어 교체할 수 없어요.', 'The processing data was deleted, so conversion is unavailable.'],
  backup_inside_vault: ['백업 위치가 볼트 안이거나 안전하지 않아요. 데이터 폴더와 볼트 위치를 확인해 주세요.', 'The backup location is inside the vault or unsafe. Check your data and vault folders.'],
};

export function conversionProblem(error) {
  const reason = String(error.body && (error.body.reason || error.body.status) || '');
  const pair = REASONS[reason.split(':')[0]];
  return banner('err', '!', [pair ? L(...pair) : L('노트를 교체하지 못했어요. 상태를 확인하고 다시 미리보기해 주세요.', 'Could not convert the note. Check its state and open a fresh preview.'), ' ', code(reason || `HTTP ${error.status || 0}`)]);
}

export async function openConversion(job, {notice, after}) {
  let preview;
  try {
    preview = await get(jobPath(job.job_id, 'convert-note'));
  } catch (error) {
    notice(conversionProblem(error));
    return;
  }
  let consent = false, applying = false;
  const apply = btn({small: true, kind: 'primary', engine: true, disabled: true,
    label: L('동의하고 새 형식으로 바꾸기', 'Consent and convert to new format'), on: {click: async () => {
      if (!consent || applying) return;
      applying = true;
      apply.disabled = true;
      checkbox.disabled = true;
      cancel.disabled = true;
      try {
        const result = await post(jobPath(job.job_id, 'convert-note'), {consent: true, preview_token: preview.preview_token});
        notice(banner('info', '✓', [h('b', null, L('새 형식으로 바꿨어요.', 'Converted to the new format.')), ' ',
          L('기존 본문은 메모 칸에, 교체 전 파일은 이 백업에 보관했어요:', 'The old body is under Notes; the original file is backed up here:'), ' ', h('span', {class: 'mono-sm'}, result.backup_path)],
        [btn({small: true, href: `/notes/${encodeURIComponent(job.job_id)}`, label: L('회의록 보기', 'View minutes')})]));
        await after();
      } catch (error) {
        notice(conversionProblem(error));
      }
    }}});
  const checkbox = h('input', {type: 'checkbox', on: {change: (event) => {
    consent = event.target.checked;
    apply.disabled = !consent || applying;
  }}});
  const cancel = btn({small: true, label: L('취소', 'Cancel'), on: {click: () => { if (!applying) notice(null); }}});
  notice(h('section', {class: 'card alert tight', 'aria-label': L('노트 교체 미리보기', 'Note conversion preview')},
    h('h2', null, L('새 형식으로 바꾸기', 'Convert to new format')),
    h('p', null, L('LLM을 다시 부르지 않아요. 교체 직전에 볼트 밖에 한 번 더 백업하고 사용자 속성은 유지해요. 기존 본문 전체는 메모 칸의 접힌 콜아웃에 안전한 글자로 보존해요.',
      'No LLM call. The note is backed up outside the vault immediately before replacement; your properties are kept. The whole old body is kept as inert text in a folded callout under Notes.')),
    h('dl', {class: 'kv'}, h('dt', null, L('현재 경로', 'Current path')), h('dd', {class: 'mono-sm'}, preview.current_path),
      h('dt', null, L('새 경로', 'New path')), h('dd', {class: 'mono-sm'}, preview.new_path)),
    h('details', {open: true}, h('summary', null, L('새 본문 요약', 'New body summary')), h('pre', {class: 'pre wrapany'}, preview.summary)),
    h('details', null, h('summary', null, L('메모로 옮길 기존 본문 전체', 'Whole old body to keep under Notes')), h('pre', {class: 'pre wrapany'}, preview.previous_body)),
    h('label', {class: 'check'}, checkbox, L('백업과 기존 본문 보존 방법을 확인했고 교체에 동의해요.', 'I reviewed the backup and body preservation and consent to replacement.')),
    h('div', {class: 'actions'}, apply, cancel)));
}
