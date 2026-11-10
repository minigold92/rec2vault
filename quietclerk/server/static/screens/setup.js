// Setup wizard (design: docs/ui/wizard-1..6.html). Steps 1-3 live here; 4 in setup-engines.js, 5-6 in setup-phone.js.
// Step 1: GET /api/setup/checks. Step 2: no models API yet (GET /api/setup/models, POST .../download are missing),
// so it shows the terminal command and keeps "Next" open. Step 3: GET /api/setup/vaults + PUT /api/settings output.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, put} from '../lib/api.js';
import {btn, chip, code, banner, say, announce} from '../lib/ui.js';
import {gigabytes} from '../lib/fmt.js';
import {setTitle, syncEngineControls} from '../lib/shell.js';
import {subscribe} from '../lib/live.js';

export const TITLES = [
  ['설정 1/6 · 환경 점검', 'Setup 1/6 · Check Mac'], ['설정 2/6 · 모델 받기', 'Setup 2/6 · Models'], ['설정 3/6 · 회의록 위치', 'Setup 3/6 · Notes folder'],
  ['설정 4/6 · 요약 엔진', 'Setup 4/6 · Summary engine'], ['설정 5/6 · 폰 연결', 'Setup 5/6 · Phone'], ['설정 6/6 · 시험', 'Setup 6/6 · Test run'],
];

// Footer: back link, spacer, optional ghost link, next control (link or button), reason line.
export function footerBar(footer, {step, next, nextHref, nextOn, nextDisabled, nextLabel, why, later, finish}) {
  const back = step > 1 ? btn({href: `/setup/${step - 1}`, label: L('이전', 'Back')}) : null;
  const forward = nextHref && !nextDisabled
    ? btn({kind: 'primary', href: nextHref, label: nextLabel})
    : btn({kind: 'primary', engine: !nextDisabled && !!nextOn, disabled: nextDisabled, describedby: why ? `why-${step}` : null, label: nextLabel,
      on: !nextDisabled && nextOn ? {click: nextOn} : null});
  replace(footer, back, h('span', {class: 'spacer'}), later, finish || null, next === false ? null : forward,
    why ? h('p', {class: 'why', id: `why-${step}`}, why) : null);
  syncEngineControls(footer);
}

const tile = (cls, mark, name, text, value) => h('li', {class: cls},
  h('span', {class: 'mk'}, mark), h('span', null, h('span', {class: 'nm'}, name), h('br'), h('span', {class: 'muted'}, text)),
  h('span', {class: 'tm stage-time'}, value));

// ---- step 1
async function step1({content, footer}) {
  const state = {checks: null, error: null, loading: true};
  async function check() {
    state.loading = true;
    render();
    try {
      state.checks = await get('/api/setup/checks');
      state.error = null;
    } catch (error) {
      state.error = error;
    }
    state.loading = false;
    render();
  }

  function rows() {
    const c = state.checks;
    if (state.loading || !c) {
      const wait = [L('칩', 'Chip'), L('메모리', 'Memory'), L('저장 공간', 'Disk'), 'ffmpeg', 'uv'];
      return wait.map((name, i) => tile(i === 0 ? 'now' : 'todo', i === 0 ? '' : '', name, i === 0 ? '…' : L('기다리는 중', 'Waiting'), i === 0 ? L('확인 중', 'Checking') : '—'));
    }
    const out = [];
    out.push(c.supported
      ? tile('done', '✓', L('칩', 'Chip'), L('Apple Silicon이라 받아쓰기 모델(MLX)을 돌릴 수 있어요.', 'Apple Silicon can run the transcription models (MLX).'), c.chip)
      : tile('fail', '✕', L('칩', 'Chip'), L('받아쓰기 모델(MLX)은 Apple Silicon에서만 돌아요. 이 Mac에서는 처리할 수 없어요.', 'The transcription models (MLX) run only on Apple Silicon. This Mac can\'t process recordings.'), c.chip));
    out.push(c.memory_bytes
      ? tile('done', '✓', L('메모리', 'Memory'), L('확인했어요. 로컬 요약(Ollama)은 품질·메모리를 아직 재 보지 않아 ‘실험적’으로 표시해요.', 'Noted. Local summaries (Ollama) are marked experimental: quality and memory aren\'t measured yet.'), gigabytes(c.memory_bytes))
      : tile('todo', '', L('메모리', 'Memory'), L('메모리 크기를 읽지 못했어요.', 'Couldn\'t read the memory size.'), '—'));
    const enough = c.disk_free_bytes >= 7.2 * 1024 ** 3;
    out.push(enough
      ? tile('done', '✓', L('저장 공간', 'Disk'), L('모델 약 5.2GB와 작업 공간이 들어가요. 2GB 아래로 내려가면 처리를 멈춰요.', 'Fits the models (about 5.2 GB) and working files. Processing stops below 2 GB free.'), L(`여유 ${gigabytes(c.disk_free_bytes)}`, `${gigabytes(c.disk_free_bytes)} free`))
      : tile('fail', '✕', L('저장 공간', 'Disk'), L('모델 약 5.2GB를 받고도 2GB가 남아야 해요. 공간을 비운 뒤 다시 점검해 주세요.', 'You need room for the models (about 5.2 GB) plus 2 GB left. Free up space, then check again.'), L(`여유 ${gigabytes(c.disk_free_bytes)}`, `${gigabytes(c.disk_free_bytes)} free`)));
    for (const [name, tool, why] of [['ffmpeg', c.ffmpeg, L('녹음을 변환하는 데 필요해요.', 'Needed to convert recordings.')], ['uv', c.uv, L('파이썬 환경을 만드는 데 필요해요.', 'Needed to create the Python environment.')]]) {
      out.push(tool.installed
        ? tile('done', '✓', name, L('설치돼 있어요.', 'Installed.'), L('설치됨', 'Installed'))
        : h('li', {class: 'fail'}, h('span', {class: 'mk'}, '✕'), h('span', null, h('span', {class: 'nm'}, name), h('br'),
          h('span', {class: 'muted'}, why, ' ', L('터미널에서 ', 'Install it in Terminal with '), h('code', null, tool.remedy), L('로 설치한 뒤 다시 점검해 주세요.', ', then check again.'))),
        h('span', {class: 'tm stage-time'}, L('없음', 'Missing'))));
    }
    return out;
  }

  function render() {
    const c = state.checks;
    const failing = c ? [!c.supported, c.disk_free_bytes < 7.2 * 1024 ** 3, !c.ffmpeg.installed, !c.uv.installed].filter(Boolean).length : 0;
    replace(content,
      h('h1', null, L('1. 환경 점검', '1. Check Mac')),
      say('ok', L('먼저 이 Mac이 받아쓰기를 돌릴 수 있는지 볼게요. 누를 건 없어요.', 'First, a quick check that this Mac can run transcription. Nothing to press.')),
      h('ul', {class: 'stages', 'aria-label': L('점검 결과', 'Check results'), 'aria-live': 'polite'}, rows()),
      state.error ? banner('err', '!', [h('b', null, L('점검하지 못했어요.', 'Couldn\'t run the checks.')), ' ', code(state.error.status ? String(state.error.status) : 'engine_unreachable')],
        [btn({small: true, icon: 'refresh', engine: true, label: L('다시 점검', 'Check again'), on: {click: check}})]) : null,
      failing ? banner('err', '!', [h('b', null, L('이 Mac에서는 아직 시작할 수 없어요.', 'This Mac can\'t start yet.')), ' ',
        L(`빨간 항목 ${failing}개를 해결해야 해요. ffmpeg·uv는 설치하면 되지만, Intel Mac은 지원하지 않아요.`, `Fix the ${failing} red item(s). ffmpeg and uv can be installed; Intel Macs aren't supported.`), ' ', code('env_check_failed')],
      [btn({small: true, icon: 'refresh', engine: true, label: L('다시 점검', 'Check again'), on: {click: check}})]) : null);
    footerBar(footer, {step: 1, nextHref: '/setup/2', nextLabel: L('다음: 모델 받기', 'Next: download models'), nextDisabled: state.loading || !c || failing > 0,
      why: failing ? L('빨간 항목을 해결하면 다음으로 갈 수 있어요.', 'Fix the red items to continue.') : null});
    syncEngineControls(content);
  }

  onLang(render);
  await check();
}

// ---- step 2
async function step2({content, footer}) {
  const command = 'python -m quietclerk.models prefetch';
  function render() {
    replace(content,
      h('h1', null, L('2. 모델 받기', '2. Models')),
      say('ok', L('받아쓰기 모델 4개, 약 5.2GB를 받아요. 한 번 받아 두면 처리할 때 인터넷이 필요 없어요.', 'Four transcription models, about 5.2 GB. Once downloaded, processing works offline.'),
        L('끊겨도 받은 데까지는 남아 있어서 이어받을 수 있어요.', 'If the download drops, it resumes from where it stopped.')),
      h('section', {class: 'list', 'aria-labelledby': 'mh'},
        h('div', {class: 'list-head'}, h('h2', {id: 'mh'}, L('모델', 'Models')), chip('idle', '—', L('아직 지원 안 함', 'Not supported yet'))),
        h('div', {class: 'item full'}, h('div', {class: 'stack'},
          h('p', {class: 'small'}, L('모델 목록과 받는 진행을 알려 주는 API가 아직 없어서, 여기서는 받기를 시작하거나 진행을 볼 수 없어요. 지금은 터미널에서 받아요:',
            'There is no API yet that lists the models or reports download progress, so this screen can\'t start a download or show progress. For now download in Terminal:'),),
          h('div', {class: 'row'}, h('code', {class: 'grow'}, command),
            btn({small: true, icon: 'copy', label: L('복사', 'Copy'), on: {click: async () => {
              try { await navigator.clipboard.writeText(command); announce(L('복사했어요', 'Copied')); } catch (_) { /* clipboard blocked */ }
            }}})),
          h('div', {class: 'row'}, code('GET /api/setup/models'), code('POST /api/setup/models/download'))))),
      h('div', {class: 'row'}, btn({kind: 'primary', disabled: true, describedby: 'dl-why', label: L('받기 시작', 'Start download')}),
        h('span', {class: 'small muted', id: 'dl-why'}, L('받기 API가 생기면 켜져요. Hugging Face에서 받고, 녹음은 보내지 않아요.', 'Turns on once the download API exists. Downloads from Hugging Face; no recordings are sent.'))),
      h('p', {class: 'small muted'}, L('남은 시간은 회선마다 달라 짐작하지 않아요. 받은 비율만 보여 드려요.', 'Time left depends on your connection, so we show only the share downloaded.')));
    footerBar(footer, {step: 2, nextHref: '/setup/3', nextLabel: L('다음: 회의록 위치', 'Next: notes folder'),
      why: L('모델이 받아졌는지 화면에서 확인할 수 없어서, 이 단계는 확인하지 않고 넘어가요.', 'The screen can\'t check whether the models are downloaded, so this step is not verified.')});
    syncEngineControls(content);
  }
  onLang(render);
  render();
}

// ---- step 3
async function step3({content, footer}) {
  const state = {vaults: [], settings: null, choice: 'other', other: '', sub: '회의록', error: null, loaded: false};
  const trim = (path) => path.replace(/\/+$/, '');
  const join = (base, sub) => (sub.trim() ? `${trim(base)}/${sub.trim().replace(/^\/+|\/+$/g, '')}` : base);

  async function load() {
    try {
      state.vaults = (await get('/api/setup/vaults')).items;
    } catch (_) { /* no candidates: a plain folder works */ }
    try {
      state.settings = await get('/api/settings');
    } catch (error) {
      state.error = error;
    }
    const output = state.settings ? state.settings.effective.output : '';
    const index = state.vaults.findIndex((v) => v.exists && (output === v.path || output.startsWith(trim(v.path) + '/')));
    if (index >= 0) {
      state.choice = index;
      state.sub = output.slice(trim(state.vaults[index].path).length + 1) || '';
    } else {
      state.choice = 'other';
      state.other = output;
      state.sub = '';
    }
    state.loaded = true;
    render();
  }

  const base = () => (state.choice === 'other' ? state.other : (state.vaults[state.choice] || {}).path || '');
  const target = () => join(base(), state.sub);
  const locked = () => !!state.settings && state.settings.environment_keys.includes('output');

  async function next() {
    state.error = null;
    if (!locked() && state.settings && target() !== state.settings.effective.output) {
      try {
        state.settings = await put('/api/settings', {output: target()});
      } catch (error) {
        state.error = error;
        render();
        return;
      }
    }
    location.assign('/setup/4');
  }

  function render() {
    if (!state.loaded) return;
    const error = state.error;
    const names = state.vaults;
    replace(content,
      h('h1', null, L('3. 회의록 위치', '3. Notes folder')),
      say('ok', names.length ? L('회의록을 어디에 둘까요? Obsidian에 등록된 볼트를 찾아 봤어요.', 'Where should the minutes go? Here are the Obsidian vaults on this Mac.')
        : L('Obsidian 볼트를 찾지 못했어요.', 'No Obsidian vaults found.'),
      names.length ? null : L('Obsidian 없이도 돼요. 회의록은 마크다운 파일이라 아무 폴더에나 둘 수 있어요.', 'That\'s fine. Minutes are Markdown files, so any folder works.')),
      h('fieldset', {class: 'stack fieldset-plain'}, h('legend', {class: 'sr-only'}, L('볼트 고르기', 'Choose a vault')),
        names.map((vault, index) => h('label', {class: 'option'},
          h('input', {type: 'radio', name: 'vault', checked: state.choice === index, disabled: !vault.exists || locked(), 'data-engine': vault.exists ? '' : null,
            on: {change: () => { state.choice = index; render(); }}}),
          h('span', {class: 'grow'}, h('b', null, vault.path.split('/').filter(Boolean).pop() || vault.path), h('span', {class: 'help mono-sm'}, vault.path),
            h('span', {class: 'help'}, vault.exists ? L('Obsidian에 등록된 볼트', 'Registered in Obsidian') : L('이 폴더를 찾을 수 없어요', 'This folder can\'t be found'))))),
        h('label', {class: 'option'},
          h('input', {type: 'radio', name: 'vault', checked: state.choice === 'other', disabled: locked(), 'data-engine': '', on: {change: () => { state.choice = 'other'; render(); }}}),
          h('span', {class: 'grow'}, h('b', null, L('다른 폴더', 'Another folder')), h('span', {class: 'help'}, L('Obsidian 없이 마크다운 폴더로 써도 돼요.', 'A plain Markdown folder works too.')),
            state.choice === 'other' ? h('input', {class: 'input', id: 'other', value: state.other, disabled: locked(), 'aria-label': L('폴더 경로', 'Folder path'), placeholder: '~/Notes',
              'data-engine': '', on: {input: (event) => { state.other = event.target.value; preview(); }}}) : null))),
      h('div', {class: 'field'},
        h('div', {class: 'lab'}, h('label', {for: 'sub'}, L('볼트 안 폴더', 'Folder inside the vault')), h('span', {class: 'help'}, L('없으면 만들어요.', 'Created if missing.'))),
        h('div', {class: 'ctl'},
          h('input', {class: 'input', id: 'sub', value: state.sub, disabled: locked(), 'aria-invalid': error ? 'true' : null, 'aria-describedby': error ? 'sub-err sub-prev' : 'sub-prev', 'data-engine': '',
            on: {input: (event) => { state.sub = event.target.value; preview(); }}}),
          error ? h('p', {class: 'err-text', id: 'sub-err'}, error.status === 400 ? L('이 폴더로 정할 수 없어요: ', 'Can\'t use this folder: ') + String((error.body && error.body.error) || '') : L('저장하지 못했어요.', 'Not saved.'), ' ', code(`${error.status} output`)) : null,
          locked() ? h('p', {class: 'small muted'}, L('환경 변수 QC_OUTPUT으로 정해져 있어 여기서 바꿀 수 없어요.', 'Fixed by the environment variable QC_OUTPUT, so it can\'t be changed here.')) : null,
          h('p', {class: 'small muted', id: 'sub-prev'}, L('예: ', 'e.g. '), h('code', {id: 'preview'}, `${target() || '…'}/2026-11-10_제목_1000.md`)))),
      h('p', {class: 'small muted'}, L('폴더 선택 창은 Mac 앱에서만 열려요. 브라우저에서는 위 후보를 고르거나 경로를 직접 적어 주세요.', 'The folder picker opens only in the Mac app. In a browser, pick a candidate above or type a path.')),
      banner('info', 'i', [h('b', null, L('이전 형식 회의록이 볼트에 있는지는 노트 옮기기 화면에서 확인해요.', 'Whether the vault has old-format notes is checked on the convert screen.')), ' ',
        L('옮기기 전까지는 볼트에 새 회의록을 쓰지 않고 따로 보관해요.', 'Until they\'re converted, new minutes are kept aside instead of written to the vault.')],
      [btn({small: true, href: '/migrate', label: L('미리보기', 'Preview')})]));
    footerBar(footer, {step: 3, nextOn: next, nextDisabled: !base().trim(), nextLabel: L('다음: 요약 엔진', 'Next: summary engine'),
      why: base().trim() ? null : L('폴더를 고르거나 경로를 적으면 다음으로 갈 수 있어요.', 'Pick a folder or type a path to continue.')});
    syncEngineControls(content);
  }

  function preview() {
    const el = document.getElementById('preview');
    if (el) el.textContent = `${target() || '…'}/2026-11-10_제목_1000.md`;
    footerBar(footer, {step: 3, nextOn: next, nextDisabled: !base().trim(), nextLabel: L('다음: 요약 엔진', 'Next: summary engine'),
      why: base().trim() ? null : L('폴더를 고르거나 경로를 적으면 다음으로 갈 수 있어요.', 'Pick a folder or type a path to continue.')});
  }

  onLang(render);
  subscribe(() => syncEngineControls(content));
  await load();
}

export async function mount(ctx) {
  const {step} = ctx;
  setTitle(...TITLES[step - 1].map((text) => `${text} · QuietClerk`));
  if (step === 1) return step1(ctx);
  if (step === 2) return step2(ctx);
  if (step === 3) return step3(ctx);
  if (step === 4) return (await import('./setup-engines.js')).mount(ctx);
  return (await import('./setup-phone.js')).mount(ctx);
}
