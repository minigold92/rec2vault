// Components named after the design mock (docs/ui/README.md §3): .chip, .code-tag, .btn, .banner,
// .problem (what / why / how / status), .say + .bubble (the character), .empty, .meter.
import {h, icon} from './dom.js';
import {L} from './i18n.js';

export const chip = (kind, glyph, label) =>
  h('span', {class: `chip ${kind}`}, glyph ? h('i', {'aria-hidden': 'true'}, glyph) : null, label);

export const code = (text) => h('span', {class: 'code-tag'}, text);

// A control that needs the engine is marked data-engine; the shell disables it while the engine is
// unreachable. A control the API cannot serve yet is rendered disabled with its reason (.why) beside it.
// `act` names what the button does (data-act): screens that re-render use it to put the keyboard focus back.
export function btn(o) {
  const cls = ['btn', o.kind || '', o.small ? 'sm' : ''].filter(Boolean).join(' ');
  const common = {class: cls, id: o.id, 'aria-label': o.aria, 'aria-describedby': o.describedby, 'data-act': o.act,
    'data-engine': o.engine ? '' : null, on: o.on};
  const kids = [o.icon ? icon(o.icon) : null, o.label];
  if (o.href && !o.disabled) return h('a', {...common, href: o.href}, ...kids);
  return h('button', {...common, type: o.type || 'button', disabled: o.disabled}, ...kids);
}

export function banner(kind, glyph, content, actions, role) {
  return h('div', {class: `banner ${kind}`, role: role || (kind === 'err' || kind === 'off' ? 'alert' : 'status')},
    h('span', {class: 'ic', 'aria-hidden': 'true'}, h('span', null, glyph)),
    h('div', null, content),
    actions && actions.length ? h('div', {class: 'actions'}, actions) : null);
}

export function problem(rows) {
  return h('dl', {class: 'problem'}, rows.flatMap(([term, definition, cls]) => [h('dt', null, term), h('dd', {class: cls}, definition)]));
}

// "What / Why / How / Status": a friendly sentence first, then the cause, then what to do, then the code.
export function problemBlock({what, why, how, command, actions, codes}) {
  const rows = [];
  if (what) rows.push([L('무엇이', 'What'), what]);
  if (why) rows.push([L('왜', 'Why'), why]);
  const commands = [].concat(command || []).map((text) => h('code', null, text));
  if (how || commands.length || (actions && actions.length)) {
    rows.push([L('어떻게', 'How'), [how ? h('span', null, how) : null, commands,
      actions && actions.length ? h('div', {class: 'actions'}, actions) : null], 'how']);
  }
  if (codes && codes.length) rows.push([L('상태', 'Status'), codes.map(code), 'row']);
  return problem(rows);
}

export const say = (mood, text, small, large) =>
  h('div', {class: 'say' + (large ? ' lg' : '')},
    h('img', {src: mood === 'worry' ? '/static/seogi-worry.svg' : '/static/seogi.svg', alt: ''}),
    h('p', {class: 'bubble'}, text, small ? h('small', null, small) : null));

export const empty = ({mood, bubble, text, actions, tight}) =>
  h('div', {class: tight ? 'empty tight' : 'empty'},
    h('img', {src: mood === 'worry' ? '/static/seogi-worry.svg' : '/static/seogi.svg', alt: ''}),
    h('p', {class: 'bubble'}, bubble),
    text ? h('p', {class: 'muted small'}, text) : null,
    actions && actions.length ? h('div', {class: 'actions'}, actions) : null);

export const meter = (value, kind, label) =>
  h('div', {class: 'meter' + (kind ? ' ' + kind : ''), role: 'progressbar', 'aria-label': label,
    'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(value * 100)},
  h('i', {vars: {'--v': Math.max(0, Math.min(1, value))}}));

export const topbar = (title, ...extra) => h('div', {class: 'topbar'}, h('h1', null, title), ...extra);

// Polite screen-reader announcement (the shell owns #live).
export function announce(text) {
  const region = document.getElementById('live');
  if (region) region.textContent = text;
}

export function apiProblem(error) {
  if (error.status === 0) return {what: L('엔진에 닿지 못했어요.', 'Could not reach the engine.'), code: 'engine_unreachable'};
  if (error.status === 401) return {what: L('로그인이 끝났어요.', 'Your session ended.'), code: '401'};
  if (error.status === 503) return {what: L('Syncthing 같은 연동 프로그램에 닿지 못했어요.', 'A local integration such as Syncthing is unavailable.'), code: '503'};
  const field = error.body && error.body.field ? ` {field: ${error.body.field}}` : '';
  return {what: L('요청을 받지 않았어요.', 'Request not accepted.'), code: `${error.status}${field}`};
}
