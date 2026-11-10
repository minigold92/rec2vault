// Settings: contract §3.3 keys with their effective value, file value and lock (design: docs/ui/settings.html).
// Data: GET/PUT /api/settings (flat dotted keys; one invalid key rejects the whole save), GET /api/providers,
// POST /api/logout, GET /api/notes/migration (how many old-format notes are left). Not in the API yet: the
// list of deleted recordings and restoring them, so that is shown as unavailable with the endpoint named.
import {h, icon, replace} from '../lib/dom.js';
import {L, onLang} from '../lib/i18n.js';
import {get, put, post} from '../lib/api.js';
import {btn, chip, code, banner, announce} from '../lib/ui.js';
import {providerLabel} from '../lib/jobs.js';
import {problemBanner} from '../lib/cards.js';
import {setTitle, syncEngineControls, langSwitch} from '../lib/shell.js';

const ENV = {root: 'QC_ROOT', inbox: 'QC_INBOX', output: 'QC_OUTPUT', since: 'QC_SINCE', min_duration_sec: 'QC_MIN_DURATION_SEC',
  stable_sec: 'QC_STABLE_SEC', 'language.mode': 'QC_LANGUAGE', 'providers.local_only': 'QC_LOCAL_ONLY', 'server.port': 'QC_PORT'};
const APPLY = {
  rec: () => L('다음 녹음부터 적용', 'Applies from the next recording'),
  scan: () => L('다음 확인부터 적용', 'Applies from the next scan'),
  clean: () => L('다음 정리부터 적용', 'Applies at next cleanup'),
  restart: () => L('엔진 다시 시작 후 적용', 'Applies after engine restart'),
  now: () => L('바로 적용', 'Applies now'),
};
const FIELD_NAMES = {transcript: ['대화록', 'transcript'], source_name: ['파일 이름', 'file name'], project_list: ['프로젝트 목록', 'project list']};

export async function mount({content}) {
  setTitle('설정 · QuietClerk', 'Settings · QuietClerk');
  const state = {server: null, providers: [], draft: {}, errors: {}, notice: null, loadError: null, migration: null};
  const barHost = h('div', {class: 'slot'});

  async function load() {
    try {
      state.server = await get('/api/settings');
      state.loadError = null;
    } catch (error) {
      state.loadError = error;
    }
    try {
      state.providers = (await get('/api/providers')).items;
    } catch (_) { /* provider rows say "unknown" */ }
    try {
      state.migration = await get('/api/notes/migration');
    } catch (_) { /* the card just links to the conversion screen */ }
    render();
    if (location.hash) {
      const target = document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView();
    }
  }

  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const effective = (key) => state.server.effective[key];
  const value = (key) => (key in state.draft ? state.draft[key] : effective(key));
  const isLocked = (key) => state.server.environment_keys.includes(key) || key === 'root' || key === 'inbox';
  const changed = () => Object.keys(state.draft).filter((key) => !same(state.draft[key], effective(key)));

  function setDraft(key, next) {
    if (same(next, effective(key))) delete state.draft[key];
    else state.draft[key] = next;
    delete state.errors[key];
    renderBar();
  }

  const show = (v) => (typeof v === 'string' ? v : JSON.stringify(v));

  function lockNote(key) {
    const env = ENV[key];
    const file = state.server.file[key];
    return h('p', {class: 'small note'}, icon('lock'), h('span', null, env
      ? L(`환경 변수 ${env}로 정해져 있어 여기서 바꿀 수 없어요. 지금 값 ${show(effective(key))} · 파일 값 ${file === undefined ? '없음' : show(file)}.`,
        `Set by the environment variable ${env}, so it can't be changed here. In effect: ${show(effective(key))} · file value: ${file === undefined ? 'none' : show(file)}.`)
      : key === 'root' ? L('여기서 바꿀 수 없어요. 옮기려면 유지보수 명령 quietclerk을 써요.', 'Can\'t be changed here. Use the quietclerk maintenance command to move it.')
        : L('실행 중에는 바꿀 수 없어요.', 'Can\'t be changed while running.')));
  }

  const tags = (key, apply, extra) => h('div', {class: 'tags'},
    apply === 'now' ? chip('ok', '✓', APPLY.now()) : apply === 'restart' ? chip('warn', '↻', APPLY.restart()) : chip('line', '↻', APPLY[apply]()),
    code(extra || key));

  const lockChip = () => chip('lock', '⊘', L('잠김', 'Locked'));

  function field({id, key, label, help, control, apply, locked, extra}) {
    const error = state.errors[key];
    return h('div', {class: 'field' + (locked ? ' locked' : ''), 'data-key': key},
      h('div', {class: 'lab'}, h('label', {for: id}, label), help ? h('span', {class: 'help'}, help) : null),
      h('div', {class: 'ctl'}, control, locked ? lockNote(key) : null,
        error ? h('p', {class: 'err-text', id: `${id}-err`}, error, ' ', code(`400 ${key}`)) : null,
        apply ? tags(key, apply, extra) : (extra ? h('div', {class: 'tags'}, code(extra)) : null)));
  }

  function textField(key, id, label, help, apply, cls) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('input', {class: `input ${cls || ''}`, id, value: String(value(key) ?? ''), disabled: locked,
      'aria-invalid': state.errors[key] ? 'true' : null, 'aria-describedby': state.errors[key] ? `${id}-err` : null, 'data-engine': locked ? null : '',
      on: {input: (event) => setDraft(key, event.target.value)}})});
  }

  function numberField(key, id, label, help, apply, unit, cls) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('div', {class: 'row'},
      h('input', {class: `input ${cls || 'narrow'}`, id, inputmode: 'numeric', value: String(value(key) ?? ''), disabled: locked,
        'aria-invalid': state.errors[key] ? 'true' : null, 'aria-describedby': state.errors[key] ? `${id}-err` : null, 'data-engine': locked ? null : '',
        on: {input: (event) => setDraft(key, /^\d+$/.test(event.target.value.trim()) ? Number(event.target.value.trim()) : event.target.value)}}),
      unit ? h('span', {class: 'small'}, unit) : null, locked ? lockChip() : null)});
  }

  function segField(key, id, label, help, apply, options) {
    const locked = isLocked(key);
    return field({id, key, label, help, apply, locked, control: h('div', {class: 'seg', role: 'radiogroup', 'aria-labelledby': `${id}-l`},
      options.map(([v, text], index) => h('label', null,
        h('input', {type: 'radio', name: key, id: index ? null : id, value: v, checked: value(key) === v, disabled: locked, 'data-engine': locked ? null : '',
          on: {change: () => setDraft(key, v)}}), h('span', null, text))))});
  }

  function switchField(key, id, label, help, apply) {
    const locked = isLocked(key);
    const on = !!value(key);
    const text = h('span', null, on ? L('켬', 'On') : L('끔', 'Off'));
    return field({id, key, label, help, apply, locked, control: h('label', {class: 'switch'},
      h('input', {type: 'checkbox', role: 'switch', id, checked: on, disabled: locked, 'data-engine': locked ? null : '',
        on: {change: (event) => { setDraft(key, event.target.checked); text.textContent = event.target.checked ? L('켬', 'On') : L('끔', 'Off'); }}}), text)});
  }

  // ---- providers: the order list (enabling and consent live in setup step 4)
  const providersHost = h('div', {class: 'slot'});
  function providerRows() {
    const order = value('providers.order') || [];
    const consent = value('providers.consent') || {};
    const by = Object.fromEntries(state.providers.map((p) => [p.name, p]));
    const known = state.providers.map((p) => p.name);
    const rows = [...order, ...known.filter((name) => !order.includes(name))];
    const status = (name) => {
      const p = by[name];
      if (!p) return [chip('idle', '?', L('확인 못 함', 'Unknown'))];
      const out = [];
      if (!p.installed) out.push(chip('idle', '—', L('설치 안 됨', 'Not installed')));
      else if (p.logged_in === false) out.push(chip('err', '!', L('로그인 필요', 'Sign-in needed')));
      else if (p.tool_block === 'verified') out.push(chip('ok', '✓', L('사용 가능', 'Ready')));
      else out.push(chip('warn', '!', p.tool_block === 'unsupported' ? L('쓸 수 없음', 'Unavailable') : L('확인 전', 'Unverified')));
      if (p.endpoint_class === 'external') out.push(chip('warn', '↗', L('외부', 'External')));
      else if (p.endpoint_class === 'local') out.push(chip('ok', '✓', L('이 Mac', 'This Mac')));
      else out.push(chip('idle', '?', L('로컬 확인 전', 'Local not verified')));
      return out;
    };
    const move = (name, by_) => {
      const next = [...order];
      const i = next.indexOf(name);
      next.splice(i, 1);
      next.splice(i + by_, 0, name);
      setDraft('providers.order', next);
      renderProviders();
    };
    const items = rows.map((name) => {
      const index = order.indexOf(name);
      const on = index >= 0;
      return h('li', {class: 'row provider-row' + (on ? '' : ' off')},
        on ? code(String(index + 1)) : null, h('b', null, providerLabel(name)), status(name),
        on ? h('span', {class: 'small muted'}, L(`보낼 것: ${(consent[name] || []).map((f) => (FIELD_NAMES[f] ? FIELD_NAMES[f][0] : f)).join('·') || '없음'}`,
          `Sends: ${(consent[name] || []).map((f) => (FIELD_NAMES[f] ? FIELD_NAMES[f][1] : f)).join(', ') || 'nothing'}`))
          : h('span', {class: 'small muted'}, L('꺼짐 · 순서에 없음', 'Off · not in order')),
        h('span', {class: 'spacer'}),
        btn({small: true, kind: 'ghost', href: '/setup/4', label: on ? L('동의 바꾸기', 'Edit consent') : L('켜기', 'Turn on')}),
        on ? [btn({small: true, engine: true, disabled: index === 0, icon: 'up', aria: L(`${providerLabel(name)} 위로`, `Move ${providerLabel(name)} up`), on: {click: () => move(name, -1)}}),
          btn({small: true, engine: true, disabled: index === order.length - 1, icon: 'down', aria: L(`${providerLabel(name)} 아래로`, `Move ${providerLabel(name)} down`), on: {click: () => move(name, 1)}})] : null);
    });
    items.push(h('li', {class: 'row provider-row off'}, h('b', null, 'Gemini CLI'), chip('err', '⊘', L('쓸 수 없음', 'Unavailable')),
      h('span', {class: 'small muted'}, L('개인 구독 로그인을 서버가 거절해요', 'Server rejects personal subscription sign-in'))));
    return h('ol', {class: 'stack tight', id: 'f-order'}, items);
  }

  function renderProviders() {
    replace(providersHost, providerRows());
    syncEngineControls(providersHost);
  }

  // ---- sections
  function section(id, title, ...body) {
    return h('section', {class: 'card', id, 'aria-labelledby': `${id}-h`}, h('div', {class: 'card-head'}, h('h2', {id: `${id}-h`}, title)), h('div', null, body));
  }

  function sections() {
    return [
      section('s-out', L('회의록', 'Notes'),
        field({id: 'f-out', key: 'output', label: L('회의록 폴더', 'Notes folder'), help: L('볼트 안의 폴더', 'A folder in your vault'), apply: 'rec', locked: isLocked('output'),
          control: h('div', {class: 'row'}, h('input', {class: 'input grow', id: 'f-out', value: String(value('output') ?? ''), disabled: isLocked('output'), 'data-engine': isLocked('output') ? null : '',
            'aria-invalid': state.errors.output ? 'true' : null, on: {input: (event) => setDraft('output', event.target.value)}}),
          h('span', {class: 'row gap6'}, btn({small: true, disabled: true, label: L('바꾸기', 'Change')}),
            h('span', {class: 'why'}, L('폴더 선택 창은 Mac 앱에서만 열려요', 'The folder picker opens only in the Mac app'))))}),
        segField('notes.output_language', 'f-ol', L('회의록 언어', 'Minutes language'), L('대화록 언어와 다르게 쓸 수 있어요', 'Can differ from the spoken language'), 'rec',
          [['same', L('녹음과 같게', 'Same as recording')], ['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]])),
      section('s-rec', L('처리할 녹음', 'Recordings to process'),
        textField('since', 'f-since', L('이 시각 이후 녹음만', 'Only recordings after'), L('그 전 녹음은 ‘기존 녹음’에서 골라요', 'Earlier ones are under ‘Older recordings’'), 'scan', 'mid'),
        numberField('min_duration_sec', 'f-min', L('최소 길이', 'Minimum length'), L('이보다 짧으면 건너뛰어요', 'Shorter recordings are skipped'), 'scan', L('초', 'seconds')),
        numberField('stable_sec', 'f-stable', L('도착 확인 시간', 'Arrival settle time'), L('파일 크기가 이만큼 그대로면 다 왔다고 봐요', 'A file is complete once its size holds this long'), 'scan', L('초', 'seconds'))),
      section('s-lang', L('언어', 'Language'),
        segField('language.mode', 'f-lm', L('녹음 언어', 'Recording language'), L('고정하면 언어 감지를 건너뛰어요', 'Pinning skips language detection'), 'rec',
          [['auto', L('자동 감지', 'Auto-detect')], ['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]]),
        segField('language.default', 'f-ld', L('애매할 때 쓸 언어', 'Fallback language'), L('자동 감지가 한쪽으로 정해지지 않을 때', 'Used when detection is inconclusive'), 'rec',
          [['ko', L('한국어', 'Korean')], ['en', L('영어', 'English')]]),
        field({id: 'f-ui', key: 'ui.language', label: L('화면 언어', 'Display language'), help: L('이 화면에만 적용돼요', 'Affects this screen only'), apply: 'now', control: h('div', {id: 'f-ui'}, langSwitch())})),
      section('providers', L('요약 엔진', 'Summary engines'),
        switchField('providers.local_only', 'f-lo', L('로컬 전용 모드', 'Local-only mode'),
          L('켜면 이 Mac 밖으로 글자를 보내지 않고, 외부로 넘어가는 대체도 막아요. 로컬로 확인된 엔진이 없으면 요약 단계에서 기다리게 돼요.', 'When on, no text leaves this Mac and external fallback is blocked. If no engine is verified local, jobs wait at summarising.'), 'rec'),
        field({id: 'f-order', key: 'providers.order', label: L('순서와 보낼 것', 'Order and data sent'), help: L('위에서부터 쓰고, 실패하면 다음으로 넘어가요. 동의한 엔진만 써요.', 'Used top to bottom; on failure the next is tried. Only engines you agreed to are used.'),
          apply: 'rec', extra: 'providers.order · providers.consent', control: providersHost}),
        textField('providers.ollama.model', 'f-om', L('Ollama 모델', 'Ollama model'), L('설치된 모델 이름을 적어요. 모델 목록을 받는 API는 아직 없어요.', 'Type an installed model name. There is no API yet that lists models.'), 'rec', 'mid'),
        segField('providers.codex.effort', 'f-ce', L('Codex 생각 정도', 'Codex reasoning effort'), L('높일수록 느려요', 'Higher is slower'), 'rec',
          [['low', L('낮음', 'Low')], ['medium', L('보통', 'Medium')], ['high', L('높음', 'High')]]),
        segField('providers.codex.speed', 'f-cs', L('Codex 속도', 'Codex speed'), L('빠르게는 약 1.5배 빠르지만 구독 사용량을 2.5배 써요', 'Fast is about 1.5x quicker but uses 2.5x of your plan limits'), 'rec',
          [['standard', L('보통', 'Standard')], ['fast', L('빠르게', 'Fast')]])),
      section('retention', L('저장과 삭제', 'Storage & deletion'),
        field({id: 'f-root', key: 'root', label: L('데이터 폴더', 'Data folder'), help: L('엔진의 모든 파일이 여기 있어요', 'All engine files live here'), locked: true, extra: 'root',
          control: h('div', {class: 'row'}, h('input', {class: 'input mid', id: 'f-root', value: String(effective('root')), disabled: true}), lockChip())}),
        field({id: 'f-inbox', key: 'inbox', label: L('받는 폴더', 'Inbox'), help: L('Syncthing이 녹음을 넣는 곳 · 엔진은 읽기만 해요', 'Where Syncthing drops recordings · read-only for the engine'), locked: true, extra: 'inbox',
          control: h('div', {class: 'row'}, h('input', {class: 'input mid', id: 'f-inbox', value: String(effective('inbox')), disabled: true}), lockChip())}),
        numberField('retention.wav_days', 'f-wav', L('변환한 음성 보관', 'Keep converted audio'), L('회의록을 쓰고 며칠 뒤 지울지', 'Days after the note is written'), 'clean', L('일', 'days')),
        retentionTable()),
      section('s-ui', L('화면과 연결', 'Screen & access'),
        numberField('server.port', 'f-port', L('화면 주소 포트', 'Screen port'), null, 'restart', `127.0.0.1:${effective('server.port')}`, 'narrow'),
        state.server.restart_required ? banner('info', 'i', L('포트를 바꿨어요. 엔진을 다시 시작하면 새 주소로 열려요.', 'The port was changed. After the engine restarts it opens at the new address.')) : null,
        field({id: 'f-remote', key: 'remote', label: L('다른 기기에서 접속', 'Access from other devices'), help: L('지금 버전은 이 Mac에서만 열려요.', 'This version opens only on this Mac.'),
          control: chip('idle', '—', L('꺼짐 · 설정 없음', 'Off · no setting'))}),
        field({id: 'f-out2', key: 'logout', label: L('이 브라우저에서 로그아웃', 'Sign out of this browser'), help: L('다시 열려면 터미널에서 quietclerk open을 실행해요.', 'Run quietclerk open in Terminal to come back.'),
          control: btn({small: true, engine: true, label: L('로그아웃', 'Sign out'), on: {click: logout}})})),
      section('consent', L('녹음 동의와 회사 정책', 'Recording consent & company policy'),
        h('div', {class: 'stack small ink'},
          h('p', null, L('녹음 전에 함께 있는 사람에게 알리고 동의를 받아 주세요. 녹음에 대한 법은 나라와 상황마다 달라요. QuietClerk는 녹음이 허용되는지 판단하지 않아요.', 'Tell everyone present and get their consent before recording. Recording laws differ by country and situation. QuietClerk doesn\'t judge whether a recording is allowed.')),
          h('p', null, L('회사 회의라면 회사 정책을 먼저 확인해 주세요. 외부 AI 사용을 막는 회사라면 로컬 전용 모드를 켜세요. 이 설정은 녹음을 보내기 전에 적용돼요.', 'For work meetings, check your company\'s policy first. If external AI is not allowed, turn on local-only mode. It applies before anything is sent.')),
          h('p', null, L('오디오는 내 폰과 이 Mac 사이에서만 오가요. 외부 요약 엔진에는 위에서 동의한 글자만 가요.', 'Audio moves only between your phone and this Mac. External engines receive only the text fields you agreed to above.')),
          h('p', {class: 'muted'}, L('처음 설정할 때 본 안내와 같은 내용이에요.', 'Same notice as during setup.')))),
      h('section', {class: 'card tight', 'aria-labelledby': 'mg-h'},
        h('div', {class: 'card-head'}, h('h2', {id: 'mg-h'}, L('이전 형식 노트 옮기기', 'Convert old-format notes')), migrationChip()),
        h('p', {class: 'small'}, L('볼트에 한국어 속성을 쓰는 이전 형식 노트가 있으면, 옮기기 전까지 새 회의록을 볼트에 넣지 않아요.', 'If your vault has notes with the old Korean properties, new minutes are not written to it until they are converted.')),
        h('div', {class: 'actions'}, btn({small: true, href: '/migrate', label: L('미리보기', 'Preview')}))),
    ];
  }

  // The conversion card's state comes from the real preview: notes left, nothing to do, or unknown.
  function migrationChip() {
    const m = state.migration;
    if (!m) return chip('idle', '?', L('확인 못 함', 'Unknown'));
    const left = m.preview.entries.filter((entry) => !entry.skip).length;
    if (left) return chip('warn', '!', L(`${left}개 남음`, `${left} left`));
    return m.migrated ? chip('ok', '✓', L('옮김', 'Converted')) : chip('line', '=', L('옮길 노트 없음', 'Nothing to convert'));
  }

  function retentionTable() {
    const days = value('retention.wav_days');
    const rows = [
      [L('원본 사본', 'Recording copy'), 'archive/', L('지울 때까지', 'Until you delete it')],
      [L('변환한 음성(WAV)', 'Converted audio (WAV)'), 'work/', L(`회의록을 쓰고 ${days}일`, `${days} days after the note`)],
      [L('중간 결과(대화록 등)', 'Working files (transcripts etc.)'), 'work/', L('새 회의록이 성공하면 이전 것 정리', 'Older ones cleaned after a new success')],
      [L('로그', 'Logs'), 'logs/', L('14일 · 작업 번호만, 회의 내용은 안 남겨요', '14 days · job IDs only, no meeting content')],
      [L('DB 백업', 'Database backups'), 'state.sqlite3.bak-*', L('최근 3개', 'Latest 3')],
      [L('노트 옮기기 백업', 'Note conversion backup'), 'note-backups/', L('지울 때까지', 'Until you delete it')],
      [L('회의록 노트', 'Notes'), null, L('내 것 · 엔진은 지우지 않아요', 'Yours · the engine never deletes them')],
    ];
    return [
      h('h3', {class: 'mt4'}, L('무엇을 얼마나 두나요', 'What\'s kept and for how long')),
      h('div', {class: 'table-wrap'}, h('table', {class: 'table'},
        h('thead', null, h('tr', null, h('th', null, L('데이터', 'Data')), h('th', null, L('어디에', 'Where')), h('th', null, L('얼마나', 'Kept')))),
        h('tbody', null, rows.map(([what, where, kept]) => h('tr', null, h('td', {'data-k': L('데이터', 'Data')}, what),
          h('td', {'data-k': L('어디에', 'Where')}, where ? h('code', null, where) : L('볼트', 'Vault')), h('td', {'data-k': L('얼마나', 'Kept')}, kept)))))),
      h('div', {class: 'grid g2 mt4'},
        h('div', {class: 'card tight'}, h('h3', null, L('‘처리 데이터 삭제’가 지우는 것', 'What ‘Delete processing data’ removes')), h('ul', {class: 'sec small'},
          h('li', null, L('원본 사본과 중간 결과', 'The recording copy and working files')),
          h('li', null, L('대화 관련 기록, 할 일·필드 소유 기록', 'Transcript-related records and note ownership data')),
          h('li', null, L('같은 파일이 다시 와도 처리하지 않도록 지문(해시)만 남겨요', 'A fingerprint (hash) so the same file isn\'t processed again')))),
        h('div', {class: 'card tight'}, h('h3', null, L('지우지 못하는 것', 'What it can\'t remove')), h('ul', {class: 'sec small'},
          h('li', null, L('폰의 원본 녹음과 받는 폴더의 파일', 'The original on the phone and the file in the inbox')),
          h('li', null, L('볼트의 회의록 노트 (직접 지워 주세요)', 'The note in your vault (delete it yourself)')),
          h('li', null, L('외부 요약 엔진(Codex 등) 쪽에 남은 기록 — 각 서비스 정책을 따라요', 'Anything kept by external engines (Codex etc.) — their policies apply'))))),
      h('p', {class: 'small mt3'}, L('녹음마다 회의록 보기나 작업 화면에서 지워요. 처리 중이면 지금 단계를 마친 뒤 지워요.', 'Delete per recording from the note or Jobs screen. If it\'s running, deletion waits for the current step.')),
      h('div', {class: 'list mt3'},
        h('div', {class: 'list-head'}, h('h3', null, L('지운 녹음', 'Deleted recordings')), chip('idle', '—', L('아직 지원 안 함', 'Not supported yet')),
          code('GET /api/tombstones')),
        h('div', {class: 'item'}, h('div', null, h('p', {class: 'small muted'}, L('지운 녹음 목록과 복원 API가 아직 없어요.', 'There is no API yet to list deleted recordings or restore them.'))),
          h('div', {class: 'side-r'}, h('span', {class: 'row gap6'}, btn({small: true, disabled: true, label: L('복원', 'Restore')}),
            h('span', {class: 'why'}, L('복원 API가 없어요', 'No restore API')))))),
    ];
  }

  async function logout() {
    try {
      await post('/api/logout');
    } catch (_) { /* leaving anyway */ }
    location.replace('/');
  }

  // ---- save bar
  function renderBar() {
    const keys = changed();
    replace(barHost, h('div', {class: 'card tight hero stickybar'},
      h('div', {class: 'row'},
        h('b', {class: 'ink', 'aria-live': 'polite'}, keys.length ? L(`바꾼 항목 ${keys.length}개`, `${keys.length} change${keys.length === 1 ? '' : 's'}`) : L('바꾼 항목이 없어요', 'No changes')),
        h('span', {class: 'small muted'}, L('처리 중인 녹음은 시작할 때의 설정으로 끝까지 가요.', 'A recording already in progress finishes with the settings it started with.')),
        h('span', {class: 'spacer'}),
        btn({small: true, engine: true, disabled: !keys.length, label: L('되돌리기', 'Revert'), on: {click: () => { state.draft = {}; state.errors = {}; state.notice = null; render(); }}}),
        btn({small: true, kind: 'primary', engine: true, disabled: !keys.length, label: L('저장', 'Save'), on: {click: save}})),
      h('p', {class: 'small muted'}, L('저장하면 settings.toml을 통째로 다시 써요. 파일에 직접 단 주석은 남지 않아요.', 'Saving rewrites settings.toml entirely; comments you added are not kept.'))));
    syncEngineControls(barHost);
  }

  async function save() {
    const keys = changed();
    state.errors = {};
    state.notice = null;
    const body = {};
    for (const key of keys) {
      const v = state.draft[key];
      if (['min_duration_sec', 'stable_sec', 'retention.wav_days', 'server.port'].includes(key) && typeof v !== 'number') {
        state.errors[key] = L('숫자로 적어 주세요.', 'Enter a whole number.');
      } else if (key === 'since' && !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(String(v))) {
        state.errors[key] = L('형식이 맞지 않아요. 예: 2026-11-09 23:00', 'Wrong format. Example: 2026-11-09 23:00');
      } else {
        body[key] = v;
      }
    }
    if (Object.keys(state.errors).length) {
      state.notice = banner('err', '!', [h('b', null, L('저장하지 못했어요.', 'Not saved.')), ' ',
        L(`빨간 항목 ${Object.keys(state.errors).length}개를 고쳐 주세요. 나머지는 아직 바뀌지 않았어요.`, `Fix the ${Object.keys(state.errors).length} item(s) in red. Nothing else has changed yet.`)]);
      render();
      return;
    }
    try {
      state.server = await put('/api/settings', body);
      state.draft = {};
      state.notice = banner('info', '✓', [h('b', null, L('저장했어요.', 'Saved.'))]);
      announce(L('저장했어요.', 'Saved.'));
    } catch (error) {
      const field = error.body && error.body.field;
      if ((error.status === 400 || error.status === 409) && field) {
        state.errors[field] = error.status === 409 ? L('환경 변수로 정해져 있어 바꿀 수 없어요.', 'Fixed by an environment variable; it can\'t be changed.')
          : field === 'since' ? L('형식이 맞지 않아요. 예: 2026-11-09 23:00', 'Wrong format. Example: 2026-11-09 23:00') : String(error.body.error);
        state.notice = banner('err', '!', [h('b', null, L('저장하지 못했어요.', 'Not saved.')), ' ',
          L('빨간 항목 1개를 고쳐 주세요. 나머지는 아직 바뀌지 않았어요.', 'Fix the 1 item in red. Nothing else has changed yet.'), ' ', code(`${error.status} {field: ${field}}`)]);
      } else {
        state.notice = problemBanner(error);
      }
    }
    render();
  }

  function render() {
    if (!state.server) {
      replace(content, h('div', {class: 'topbar'}, h('h1', null, L('설정', 'Settings'))), state.loadError ? problemBanner(state.loadError) : null);
      return;
    }
    const keep = document.activeElement && document.activeElement.id;
    replace(content,
      h('div', {class: 'topbar'}, h('h1', null, L('설정', 'Settings'))),
      state.notice,
      h('nav', {class: 'row', 'aria-label': L('설정 구역', 'Settings sections')}, [
        ['s-out', L('회의록', 'Notes')], ['s-rec', L('처리할 녹음', 'Recordings')], ['s-lang', L('언어', 'Language')], ['providers', L('요약 엔진', 'Summary engines')],
        ['retention', L('저장·삭제', 'Storage & deletion')], ['s-ui', L('화면', 'Screen')], ['consent', L('녹음 동의', 'Recording consent')]]
        .map(([id, text]) => h('a', {class: 'chip line', href: `#${id}`}, text))),
      sections(), barHost);
    renderProviders();
    renderBar();
    syncEngineControls(content);
    if (keep && document.getElementById(keep)) document.getElementById(keep).focus();
  }

  onLang(render);
  await load();
}
