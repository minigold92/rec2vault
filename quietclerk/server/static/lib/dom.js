// Tiny DOM builder. Text always goes through text nodes; nothing here parses HTML, so transcript,
// title and engine text can never become markup. The CSP forbids inline style, hence `vars`
// (CSSOM custom properties) instead of `style`.
const SVG_NS = 'http://www.w3.org/2000/svg';
const LATE = ['value', 'checked', 'selected', 'indeterminate'];

function safeUrl(url) {
  const value = String(url);
  // Same-origin paths, in-page anchors and the Obsidian opener only.
  if (/^\/(?!\/)/.test(value) || value.startsWith('#') || value.startsWith('obsidian://open?')) return value;
  throw new Error('blocked url: ' + value);
}

function apply(el, props, late) {
  if (!props) return;
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.setAttribute('class', value);
    else if (key === 'on') for (const [type, fn] of Object.entries(value)) el.addEventListener(type, fn);
    else if (key === 'vars') for (const [name, v] of Object.entries(value)) el.style.setProperty(name, String(v));
    else if (key === 'ref') value(el);
    else if (key === 'style') throw new Error('inline style is blocked by the CSP; use a class or vars');
    else if (key.startsWith('on')) throw new Error('use the on: {} map for events');
    else if (key === 'href' || key === 'src') el.setAttribute(key, safeUrl(value));
    else if (LATE.includes(key)) late.push([key, value]);
    else if (key === 'disabled') { el.disabled = true; el.setAttribute('aria-disabled', 'true'); }
    else if (key === 'hidden' || key === 'open') el[key] = true;
    else el.setAttribute(key, value === true ? '' : String(value));
  }
}

export function append(el, kids) {
  for (const kid of kids) {
    if (kid === null || kid === undefined || kid === false) continue;
    if (Array.isArray(kid)) append(el, kid);
    else if (kid instanceof Node) el.append(kid);
    else el.append(document.createTextNode(String(kid)));
  }
  return el;
}

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  const late = [];
  apply(el, props, late);
  append(el, kids);
  for (const [key, value] of late) el[key] = value;
  return el;
}

export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, String(value));
  for (const kid of kids) if (kid) el.append(kid);
  return el;
}

// Line icons from the design mock (docs/ui), 24px grid.
const ICONS = {
  home: [['path', {d: 'M3 11 12 4l9 7'}], ['path', {d: 'M5 10v10h14V10'}], ['path', {d: 'M10 20v-6h4v6'}]],
  notes: [['rect', {x: 5, y: 3, width: 14, height: 18, rx: 2}], ['path', {d: 'M9 8h6M9 12h6M9 16h4'}]],
  jobs: [['path', {d: 'M4 6h16M4 12h16M4 18h10'}], ['circle', {cx: 19, cy: 18, r: 2}]],
  backlog: [['rect', {x: 7, y: 2.5, width: 10, height: 19, rx: 2.5}], ['path', {d: 'M10 6h4'}], ['path', {d: 'M12 10v6m-3-3 3 3 3-3'}]],
  settings: [['circle', {cx: 12, cy: 12, r: 3}], ['path', {d: 'M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1'}]],
  pause: [['path', {d: 'M9 5v14M15 5v14'}]],
  play: [['path', {d: 'M7 4l13 8-13 8z'}]],
  refresh: [['path', {d: 'M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5'}]],
  external: [['path', {d: 'M14 4h6v6M20 4l-9 9'}], ['path', {d: 'M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'}]],
  lock: [['rect', {x: 5, y: 11, width: 14, height: 10, rx: 2}], ['path', {d: 'M8 11V7a4 4 0 0 1 8 0v4'}]],
  up: [['path', {d: 'M12 19V5M6 11l6-6 6 6'}]],
  down: [['path', {d: 'M12 5v14M6 13l6 6 6-6'}]],
  copy: [['rect', {x: 8, y: 8, width: 12, height: 12, rx: 2}], ['path', {d: 'M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3'}]],
  x: [['path', {d: 'M6 6l12 12M18 6 6 18'}]],
  plus: [['path', {d: 'M12 5v14M5 12h14'}]],
};

export function icon(name) {
  return svg('svg', {width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'},
  ...ICONS[name].map(([tag, attrs]) => svg(tag, attrs)));
}

export function replace(parent, ...kids) {
  parent.replaceChildren();
  return append(parent, kids);
}
