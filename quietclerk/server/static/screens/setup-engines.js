// Setup step 4: summary engines, their order, what each may receive, local-only (design: docs/ui/wizard-4.html).
// Data: GET /api/providers, POST /api/providers/{name}/check (a synthetic test call, only inside the consent),
// GET/PUT /api/settings (providers.order, providers.consent, providers.allow_unverified, providers.local_only,
// providers.ollama.model). Every change is saved at once: this step has no save button.
import {h, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, put, post} from '../lib/api.js';
import {btn, chip, code, say, announce, problemBlock} from '../lib/ui.js';
import {providerLabel, LOGIN_COMMAND} from '../lib/jobs.js';
import {problemBanner} from '../lib/cards.js';
import {localTime} from '../lib/fmt.js';
import {footerBar} from './setup.js';
import {syncEngineControls} from '../lib/shell.js';

const FIELDS = [
  ['transcript', ['대화록', 'Transcript'], ['교정·분류·요약', 'correct, classify, summarize']],
  ['source_name', ['녹음 파일 이름', 'Recording file name'], ['분류', 'classify']],
  ['project_list', ['프로젝트 목록', 'Project list'], ['분류', 'classify']],
];
const VENDOR = {codex: 'OpenAI', claude: 'Anthropic'};

export async function mount({content, footer}) {
  const state = {providers: null, settings: null, tests: {}, notice: null, error: null};

  async function load() {
    try {
      state.providers = (await get('/api/providers')).items;
      state.settings = await get('/api/settings');
      state.error = null;
    } catch (error) {
      state.error = error;
    }
    render();
  }

  const s = (key) => state.settings.effective[key];
  const locked = (key) => state.settings.environment_keys.includes(key);

  async function save(changes) {
    state.notice = null;
    try {
      state.settings = await put('/api/settings', changes);
      announce(L('저장했어요.', 'Saved.'));
    } catch (error) {
      state.notice = problemBanner(error);
    }
    render();
  }

  function enable(name, on) {
    const order = s('providers.order').filter((n) => n !== name);
    const consent = {...s('providers.consent')};
    if (on) {
      order.push(name);
      consent[name] = consent[name] && consent[name].length ? consent[name] : FIELDS.map(([f]) => f);
    } else {
      delete consent[name];
    }
    return save({'providers.order': order, 'providers.consent': consent});
  }

  function move(name, by) {
    const order = [...s('providers.order')];
    const i = order.indexOf(name);
    order.splice(i, 1);
    order.splice(i + by, 0, name);
    return save({'providers.order': order});
  }

  function setField(name, field, on) {
    const current = new Set(s('providers.consent')[name] || []);
    if (on) current.add(field);
    else current.delete(field);
    const consent = {...s('providers.consent'), [name]: FIELDS.map(([f]) => f).filter((f) => current.has(f))};
    // Without the transcript nothing can be corrected or summarised, so the engine is not used.
    const order = consent[name].includes('transcript') ? s('providers.order') : s('providers.order').filter((n) => n !== name);
    if (!consent[name].includes('transcript')) delete consent[name];
    return save({'providers.consent': consent, 'providers.order': order});
  }

  async function allowUnverified(name, on) {
    const list = s('providers.allow_unverified').filter((n) => n !== name);
    if (on) list.push(name);
    const order = on ? s('providers.order') : s('providers.order').filter((n) => n !== name);
    return save({'providers.allow_unverified': list, 'providers.order': order});
  }

  async function test(name) {
    state.tests[name] = {busy: true};
    render();
    try {
      const result = await post(`/api/providers/${encodeURIComponent(name)}/check`);
      state.tests[name] = {...result, at: new Date()};
    } catch (error) {
      state.tests[name] = {ok: false, reason: String(error.status), at: new Date()};
    }
    render();
  }

  async function recheck() {
    try {
      state.providers = (await get('/api/providers')).items;
    } catch (error) {
      state.notice = problemBanner(error);
    }
    render();
  }

  const row = (term, ...detail) => [h('dt', null, term), h('dd', null, detail)];

  function card(p, index, count) {
    const name = p.name;
    const on = s('providers.order').includes(name);
    const unverified = p.tool_block === 'unverified';
    const allowed = s('providers.allow_unverified').includes(name);
    const usable = p.installed && p.tool_block !== 'unsupported' && (!unverified || allowed);
    const consent = s('providers.consent')[name] || [];
    const test_ = state.tests[name];
    const canTest = on && p.installed && p.logged_in !== false && consent.includes('transcript');
    const vendor = VENDOR[name];
    return h('li', {class: 'card tight'},
      h('div', {class: 'card-head'}, on ? code(String(index + 1)) : null, h('h3', null, providerLabel(name)), h('span', {class: 'small muted'}, p.version || ''), h('span', {class: 'spacer'}),
        h('label', {class: 'switch'}, h('input', {type: 'checkbox', role: 'switch', checked: on, disabled: !usable || locked('providers.order'), 'data-engine': usable ? '' : null,
          on: {change: (event) => enable(name, event.target.checked)}}), h('span', null, L('사용', 'Use'))),
        on ? h('div', {class: 'row nogap'},
          btn({small: true, engine: true, disabled: index === 0, icon: 'up', aria: L(`${providerLabel(name)} 위로`, `Move ${providerLabel(name)} up`), on: {click: () => move(name, -1)}}),
          btn({small: true, engine: true, disabled: index === count - 1, icon: 'down', aria: L(`${providerLabel(name)} 아래로`, `Move ${providerLabel(name)} down`), on: {click: () => move(name, 1)}})) : null),
      h('dl', {class: 'kv'},
        row(L('설치', 'Installed'), p.installed ? chip('ok', '✓', L('설치됨', 'Installed')) : chip('idle', '—', L('설치 안 됨', 'Not installed'))),
        name === 'ollama' ? null : row(L('로그인', 'Sign-in'),
          p.logged_in === true ? chip('ok', '✓', L('로그인됨', 'Signed in'))
            : p.logged_in === false ? [chip('err', '!', L('로그인 필요', 'Sign-in needed')), ' ',
              LOGIN_COMMAND[name] ? h('span', {class: 'small'}, L('터미널에서 ', 'Run '), h('code', null, LOGIN_COMMAND[name]), L('을 실행해 로그인한 뒤', ' in Terminal to sign in, then')) : null,
              btn({small: true, icon: 'refresh', engine: true, label: L('다시 확인', 'Check again'), on: {click: recheck}})]
              : chip('idle', '?', L('확인 못 함', 'Unknown'))),
        row(L('도구 차단', 'Tool block'), p.tool_block === 'verified'
          ? [chip('ok', '✓', L('확인됨', 'Verified')), ' ', h('span', {class: 'small muted'}, L('파일 읽기·명령 실행을 막은 채로만 불러요', 'Called only with file access and commands blocked'))]
          : p.tool_block === 'unsupported' ? [chip('err', '⊘', L('쓸 수 없음', 'Unavailable')), ' ', h('span', {class: 'small muted'}, p.reason || '')]
            : [chip('warn', '!', L('확인 전', 'Not verified')), ' ', h('span', {class: 'small muted'}, L('도구를 막았는지 아직 확인하지 못했어요. 쓰려면 아래에서 이 엔진만 예외로 허용해야 해요.', 'We have not confirmed tools are blocked. To use it you must allow this one engine as an exception below.'))]),
        row(L('실행 위치', 'Runs at'), p.endpoint_class === 'external' ? chip('warn', '↗', vendor ? L(`외부 (${vendor})`, `External (${vendor})`) : L('외부', 'External'))
          : p.endpoint_class === 'local' ? chip('ok', '✓', L('이 Mac', 'This Mac'))
            : [chip('idle', '?', L('확인 전', 'Not verified')), ' ', h('span', {class: 'small muted'}, L('이 Mac에서 도는지 아직 확인하지 못해 ‘로컬’로 치지 않아요', 'We can\'t yet confirm it runs on this Mac, so it doesn\'t count as local'))]),
        row(L('시험 호출', 'Test call'), test_ && test_.busy ? chip('run', '●', L('호출 중', 'Calling'))
          : test_ ? [test_.ok ? chip('ok', '✓', L(`성공 ${localTime(test_.at / 1000)}`, `Passed ${localTime(test_.at / 1000)}`)) : chip('err', '!', L(`실패 ${localTime(test_.at / 1000)}`, `Failed ${localTime(test_.at / 1000)}`)),
            test_.reason ? [' ', code(test_.reason)] : null, ' ']
            : null,
        btn({small: true, engine: canTest, disabled: !canTest, label: test_ && !test_.busy ? L('다시 시험', 'Test again') : L('시험 호출', 'Test call'), on: canTest ? {click: () => test(name)} : null}),
        canTest ? h('span', {class: 'small muted'}, name === 'ollama' ? L('가상의 한 문장만 보내요.', 'Sends one made-up sentence.') : L('가상의 한 문장만 보내요. 회의 내용은 가지 않아요.', 'Sends one made-up sentence. No meeting content.'))
          : h('span', {class: 'why'}, L('켜고 대화록을 보내도록 허용한 뒤, 로그인돼 있어야 해요.', 'Needs the engine on, the transcript allowed and a sign-in.')))),
      unverified && p.installed ? h('label', {class: 'check small'}, h('input', {type: 'checkbox', checked: allowed, 'data-engine': '', on: {change: (event) => allowUnverified(name, event.target.checked)}}),
        h('span', null, h('b', {class: 'ink'}, L('도구 차단이 확인되지 않은 엔진이지만 이것만 예외로 쓰기', 'Allow this unverified engine as an exception')), h('br'),
          h('span', {class: 'muted'}, L('대체 경로에는 들어가지 않고, 순서에 넣은 경우에만 써요.', 'It is not used as a fallback; only when you put it in the order.')))) : null,
      on ? h('fieldset', {class: 'stack fieldset-box'}, h('legend', null, L('이 엔진에 보낼 것', 'What this engine receives')),
        FIELDS.map(([field, [ko, en], [uko, uen]]) => h('label', {class: 'check small'},
          h('input', {type: 'checkbox', checked: consent.includes(field), 'data-engine': '', on: {change: (event) => setField(name, field, event.target.checked)}}),
          h('span', null, h('b', {class: 'ink'}, L(ko, en)), ' ', h('code', null, field), h('br'), h('span', {class: 'muted'}, L(`쓰는 단계: ${uko}`, `Used in: ${uen}`)))),
        ),
        h('p', {class: 'small muted'}, L('오디오는 보내지 않아요. 체크를 끄면 그 필드는 보내지 않고, 대화록을 끄면 이 엔진은 쓰지 않아요.', 'Audio is never sent. Unchecked fields aren\'t sent; without the transcript this engine isn\'t used.'))) : null,
      name === 'ollama' ? h('div', {class: 'row'}, h('label', {class: 'small', for: 'ollama-model'}, L('모델', 'Model')),
        h('input', {class: 'input mid', id: 'ollama-model', value: s('providers.ollama.model'), 'data-engine': '', placeholder: 'qwen3:8b',
          on: {change: (event) => save({'providers.ollama.model': event.target.value})}}),
        h('span', {class: 'small muted'}, L('설치된 모델 이름을 적어요. 품질·메모리는 아직 재 보지 않아 ‘실험적’이에요.', 'Type an installed model name. Quality and memory are not measured yet, so this is experimental.'))) : null);
  }

  function render() {
    if (!state.settings || !state.providers) {
      replace(content, h('h1', null, L('4. 요약 엔진', '4. Summary engine')), state.error ? problemBanner(state.error) : say('ok', L('설치된 요약 엔진을 찾는 중이에요…', 'Looking for installed summary engines…')));
      footerBar(footer, {step: 4, nextHref: '/setup/5', nextLabel: L('다음: 폰 연결', 'Next: connect phone')});
      return;
    }
    const order = s('providers.order');
    const sorted = [...state.providers].sort((a, b) => {
      const ia = order.indexOf(a.name), ib = order.indexOf(b.name);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    const usable = state.providers.some((p) => p.installed && p.tool_block === 'verified' && p.logged_in !== false);
    const lockedOnly = locked('providers.local_only');
    replace(content,
      h('h1', null, L('4. 요약 엔진', '4. Summary engine')),
      say('ok', L('받아 적은 글을 다듬고 요약할 엔진을 골라요.', 'Pick the engines that clean up and summarise the transcript.'), L('오디오는 어디에도 보내지 않아요. 고른 엔진에 글자만 가요.', 'Audio never leaves your devices. Only text goes to the engines you choose.')),
      state.notice,
      h('section', {class: 'card', 'aria-labelledby': 'lo-h'},
        h('div', {class: 'card-head'}, h('h2', {id: 'lo-h'}, L('로컬 전용 모드', 'Local-only mode')),
          h('label', {class: 'switch'}, h('input', {type: 'checkbox', role: 'switch', checked: !!s('providers.local_only'), disabled: lockedOnly, 'data-engine': lockedOnly ? null : '', 'aria-describedby': 'lo-help',
            on: {change: (event) => save({'providers.local_only': event.target.checked})}}), h('span', null, s('providers.local_only') ? L('켬', 'On') : L('끔', 'Off')))),
        h('p', {class: 'small', id: 'lo-help'}, L('켜면 이 Mac 밖으로 글자를 보내지 않아요. 외부 엔진으로 넘어가는 대체 경로도 막아요. 로컬로 확인된 엔진이 없으면, 켜는 순간 녹음이 요약 단계 앞에서 기다려요.', 'When on, no text leaves this Mac and fallback to external engines is blocked. If no engine is confirmed local, recordings wait before summarising once it is on.'), ' ', code('no_local_provider'),
          lockedOnly ? h('span', {class: 'small muted'}, L(' 환경 변수 QC_LOCAL_ONLY로 정해져 있어 바꿀 수 없어요.', ' Fixed by the environment variable QC_LOCAL_ONLY.')) : null)),
      h('section', {class: 'stack', 'aria-labelledby': 'pv-h'},
        h('div', {class: 'row'}, h('h2', {id: 'pv-h'}, L('요약 엔진과 순서', 'Engines and order')),
          h('span', {class: 'small muted'}, L('위에서부터 써요. 실패하면 다음 엔진으로 넘어가요(동의한 엔진만).', 'Used top to bottom. On failure the next one is tried (only engines you agreed to).'))),
        h('ol', {class: 'stack'}, sorted.map((p, i) => card(p, order.indexOf(p.name), order.length)),
          h('li', {class: 'card tight'}, h('div', {class: 'card-head'}, h('h3', null, 'Gemini CLI'), h('span', {class: 'spacer'}),
            h('label', {class: 'switch'}, h('input', {type: 'checkbox', role: 'switch', disabled: true}), h('span', null, L('사용', 'Use')))),
          h('dl', {class: 'kv'}, row(L('상태', 'Status'), chip('err', '⊘', L('쓸 수 없음', 'Unavailable')), ' ',
            h('span', {class: 'small muted'}, L('개인 구독 로그인을 Gemini 서버가 거절해 지원하지 않아요', 'Gemini\'s servers reject personal subscription sign-in, so it isn\'t supported')))))),
        usable ? null : h('article', {class: 'card alert tight'},
          h('div', {class: 'card-head'}, h('h3', null, L('쓸 수 있는 요약 엔진이 없어요', 'No usable summary engine')), chip('err', '!', L('없음', 'None'))),
          problemBlock({what: L('설치돼 있고 로그인된, 도구 차단이 확인된 엔진이 없어요.', 'No engine is installed, signed in and confirmed tool-safe.'),
            why: L('받아쓰기까지는 되지만 교정·요약을 할 엔진이 없어요.', 'Transcription works, but nothing can correct or summarise.'),
            how: L('하나를 설치하고 로그인한 뒤 다시 찾아 주세요.', 'Install and sign in to one, then search again.'), command: 'npm i -g @openai/codex && codex login',
            actions: [btn({small: true, icon: 'refresh', engine: true, label: L('다시 찾기', 'Search again'), on: {click: recheck}})], codes: ['no_verified_provider']}))),
      h('p', {class: 'small muted'}, L('Codex·Claude Code는 각 회사 서버에서 돌아요. 회사 정책이 외부 AI 사용을 막는다면 로컬 전용 모드를 쓰세요.', 'Codex and Claude Code run on their companies\' servers. If your company forbids external AI, use local-only mode.')));
    footerBar(footer, {step: 4, nextHref: '/setup/5', nextLabel: L('다음: 폰 연결', 'Next: connect phone')});
    syncEngineControls(content);
  }

  onLang(render);
  await load();
}
