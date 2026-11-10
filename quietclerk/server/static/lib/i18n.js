// One language is rendered at a time. Every visible string is written once as L('한국어', 'English')
// next to the code that shows it; switching the language re-renders the screen.
const listeners = new Set();
let lang = typeof document !== 'undefined' && document.documentElement.lang === 'en' ? 'en' : 'ko';

export const getLang = () => lang;
export const L = (ko, en) => (lang === 'ko' ? ko : en);
export const onLang = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export function setLang(next) {
  if (next !== 'ko' && next !== 'en') return;
  lang = next;
  if (typeof document !== 'undefined') document.documentElement.lang = next;
  for (const fn of listeners) fn(next);
}

// English count nouns: plural(3, 'recording') -> "3 recordings".
export const plural = (n, noun) => `${n} ${noun}${n === 1 ? '' : 's'}`;
