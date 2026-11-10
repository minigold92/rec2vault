// App frame shared by every screen: left menu + engine box + language switch (wide), top bar + tab bar
// (narrow), the engine-offline banner, and the setup wizard frame. The shell owns everything outside
// the screen's own content, and re-renders itself when the language or the engine state changes.
import {h, icon, replace} from './dom.js';
import {L, getLang, setLang, onLang} from './i18n.js';
import {put, get} from './api.js';
import {live, subscribe, reconnect} from './live.js';
import {banner, btn, chip, code} from './ui.js';
import {localTime} from './fmt.js';
import {isBlocked} from './jobs.js';

const NAV = [
  ['home', '/home', 'home', '홈', 'Home'],
  ['notes', '/notes', 'notes', '회의록', 'Notes'],
  ['jobs', '/jobs', 'jobs', '작업', 'Jobs'],
  ['backlog', '/backlog', 'backlog', '기존 녹음', 'Older recordings'],
  ['settings', '/settings', 'settings', '설정', 'Settings'],
];
const WIZARD = [['환경 점검', 'Check Mac'], ['모델 받기', 'Models'], ['회의록 위치', 'Notes folder'],
  ['요약 엔진', 'Summary engine'], ['폰 연결', 'Phone'], ['시험', 'Test run']];
// Screens that live under a menu entry.
const PARENT = {note: 'notes', migrate: 'settings'};

let title = ['QuietClerk', 'QuietClerk'];
let badge = 0, badgeKey = '';

export function setTitle(ko, en) {
  title = [ko, en];
  document.title = L(ko, en);
}

export async function changeLanguage(next) {
  setLang(next);
  try {
    await put('/api/settings', {'ui.language': next});
  } catch (_) { /* the screen already switched; the setting is saved next time */ }
}

export const langSwitch = () =>
  h('div', {class: 'langsw', role: 'group', 'aria-label': L('화면 언어', 'Display language')},
    ['ko', 'en'].map((lang) => h('button', {type: 'button', 'data-lang': lang, 'aria-pressed': String(getLang() === lang),
      on: {click: () => changeLanguage(lang)}}, lang === 'ko' ? '한국어' : 'English')));

const brand = (full) =>
  h('a', {class: 'brand', href: '/home'}, h('img', {src: '/static/seogi.svg', alt: ''}),
    h('span', null, h('b', null, 'QuietClerk'), full ? h('span', null, L('맥서기', 'Meeting minutes on your Mac')) : null));

export function syncEngineControls(root = document) {
  for (const el of root.querySelectorAll('[data-engine]')) {
    if (live.failed) {
      if (!el.disabled) {
        el.dataset.offline = '1';
        el.disabled = true;
        el.setAttribute('aria-disabled', 'true');
      }
    } else if (el.dataset.offline) {
      delete el.dataset.offline;
      el.disabled = false;
      el.removeAttribute('aria-disabled');
    }
  }
}

function engineBox() {
  const snapshot = live.snapshot;
  let state;
  if (live.failed) state = L('엔진 연결 끊김', 'Engine unreachable');
  else if (!snapshot) state = L('엔진 확인 중', 'Checking the engine');
  else if (snapshot.paused) state = L('엔진 켜짐 · 일시정지', 'Engine on · paused');
  else state = L('엔진 켜짐', 'Engine on');
  return h('div', {class: 'engine', 'aria-live': 'polite'}, h('b', null, state), h('span', {class: 'muted'}, location.host));
}

function navLinks(current, withCount) {
  return NAV.map(([key, href, ic, ko, en]) =>
    h('a', {href, 'aria-current': key === current ? 'page' : null}, icon(ic), L(ko, en),
      withCount && key === 'jobs' && badge ? h('span', {class: 'count'}, String(badge)) : null));
}

export function offlineBanner() {
  const last = live.lastEvent;
  return banner('off', '!', [
    h('b', null, L('엔진과 연결이 끊겼어요.', 'Lost connection to the engine.')), ' ',
    last
      ? L(`마지막으로 받은 화면(${localTime(last.getTime() / 1000)})을 보여 드려요. 다시 연결되면 버튼이 켜져요.`,
        `Showing the last screen received (${localTime(last.getTime() / 1000)}). Buttons come back when it reconnects.`)
      : L('아직 받은 화면이 없어요. 다시 연결되면 보여 드려요.', 'Nothing received yet. It will show up once connected.'),
    h('div', {class: 'small'},
      L('Mac을 다시 켰다면 로그인해야 엔진이 돌아요. 그래도 안 되면 터미널에서 ', 'If the Mac restarted, the engine runs only after you log in. If it still fails, run '),
      h('code', null, 'quietclerk status'), L(' 를 실행해 보세요.', ' in Terminal.'), ' ', code('engine_unreachable')),
  ], [btn({small: true, label: L('다시 연결', 'Reconnect'), on: {click: reconnect}})], 'alert');
}

function authBanner() {
  return banner('err', '!', [
    h('b', null, L('로그인이 끝났어요.', 'Your session ended.')), ' ',
    L('터미널에서 ', 'Run '), h('code', null, 'quietclerk open'), L('을 실행하면 다시 열려요.', ' in Terminal to open it again.'), ' ', code('401'),
  ], [btn({small: true, label: L('다시 확인', 'Check again'), on: {click: reconnect}})]);
}

function topNotices() {
  if (live.authLost) return authBanner();
  return live.failed ? offlineBanner() : null;
}

async function refreshBadge() {
  const counts = (live.snapshot && live.snapshot.counts) || {};
  const key = `${counts.failed || 0}:${counts.retry_wait || 0}:${(live.snapshot && live.snapshot.jobs || []).length}`;
  if (key === badgeKey) return;
  badgeKey = key;
  let blocked = 0;
  if (counts.retry_wait) {
    try {
      blocked = (await get('/api/jobs?status=retry_wait&limit=200')).items.filter(isBlocked).length;
    } catch (_) { return; }
  }
  badge = (counts.failed || 0) + blocked;
}

// Builds the frame and returns {content, footer}: the screen fills `content` (and `footer` in the wizard).
// `content` and the notice slot are display:contents, so their children lay out as the frame's own.
export function mountShell(screen, {wizardStep} = {}) {
  const root = document.getElementById('app');
  const slots = {};
  const content = h('div', {class: 'slot'});
  const noticeSlot = h('div', {class: 'slot'});
  const announcer = h('div', {id: 'live', class: 'sr-only', 'aria-live': 'polite'});
  const skip = h('a', {class: 'skip', href: '#main'});
  const main = h('main', {class: wizardStep ? 'stack gap5' : 'main', id: 'main', tabindex: '-1'});
  let footer = null;

  if (wizardStep) {
    footer = h('footer', {class: 'wiz-foot'});
    slots.head = h('header', {class: 'wiz-top'});
    slots.stepper = h('ol', {class: 'stepper'});
    main.append(noticeSlot, content);
    replace(root, skip, h('div', {class: 'wiz'}, slots.head, slots.stepper, main, footer), announcer);
  } else {
    slots.side = h('aside', {class: 'side'});
    slots.mobile = h('header', {class: 'mobile-top'});
    slots.tab = h('nav', {class: 'tabbar'});
    main.append(h('div', {class: 'wrap'}, noticeSlot, content));
    replace(root, skip, h('div', {class: 'app'}, slots.side, h('div', null, slots.mobile, main)), slots.tab, announcer);
  }

  const current = PARENT[screen] || screen;
  const chrome = () => {
    skip.textContent = L('본문으로 건너뛰기', 'Skip to content');
    document.title = L(title[0], title[1]);
    if (wizardStep) {
      replace(slots.head, brand(true), langSwitch());
      slots.stepper.setAttribute('aria-label', L('설정 단계', 'Setup steps'));
      replace(slots.stepper, WIZARD.map(([ko, en], index) => {
        const n = index + 1;
        return h('li', {class: n < wizardStep ? 'done' : n === wizardStep ? 'now' : '', 'aria-current': n === wizardStep ? 'step' : null},
          h('span', {class: 'n'}, `${n}/6`), h('span', {class: 's'}, L(ko, en)),
          h('span', {class: 'sr-only'}, n === wizardStep ? L('지금', 'current') : ''));
      }));
    } else {
      slots.side.setAttribute('aria-label', L('주 메뉴', 'Main menu'));
      slots.tab.setAttribute('aria-label', L('주 메뉴', 'Main menu'));
      replace(slots.side, brand(true), h('nav', {class: 'nav'}, navLinks(current, true)),
        h('div', {class: 'side-foot'}, engineBox(), langSwitch()));
      replace(slots.mobile, brand(false),
        live.failed ? chip('err', '!', L('엔진 끊김', 'Offline'))
          : live.snapshot && live.snapshot.paused ? chip('warn', '‖', L('일시정지', 'Paused')) : null,
        langSwitch());
      replace(slots.tab, navLinks(current, false));
    }
    replace(noticeSlot, topNotices());
    syncEngineControls(root);
  };
  chrome();
  onLang(chrome);
  subscribe(async () => {
    await refreshBadge();
    chrome();
  });
  return {content, footer, main};
}
