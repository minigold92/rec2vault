// Small pure helpers of the minutes screen: what may be typed (as the server will judge it), which lines a search
// matches, speaker names inside prose, and the key rules of the line editor. No DOM here, so tests can call them directly.

// Unicode "other": control (newline, tab), format (zero-width, bidirectional), private use, unassigned. The server
// refuses all of them in names and lines (contract §10.8), so the screen says so before anything is sent.
const OTHER = /\p{C}/u;
export const size = (text) => Array.from(text).length;   // the server counts characters, not UTF-16 units

// {ok, text} for a name or a line as the server will take it (trimmed, 1..limit characters), else {ok: false, why, n}.
export function cleanText(raw, limit) {
  const text = String(raw ?? '').trim();
  if (!text) return {ok: false, why: 'empty'};
  if (OTHER.test(text)) return {ok: false, why: 'chars'};
  const n = size(text);
  return n > limit ? {ok: false, why: 'long', n} : {ok: true, text};
}

// Enter that only ends an IME composition (Korean, Japanese, Chinese) must not act. Chrome and Firefox mark that
// keydown with isComposing; Safari sends it after compositionend, with keyCode 229.
export const isComposing = (event) => !!(event.isComposing || event.keyCode === 229);

// Pasted or typed line breaks become one space: a line is one line.
export const oneLine = (text) => String(text).replace(/[\r\n\v\f\u0085\u2028\u2029]+/g, ' ');

// Lowercased letters of `text` without whitespace, each remembered with where it came from.
function fold(text) {
  let flat = '';
  const from = [];
  let at = 0;
  for (const ch of text) {
    if (ch.trim()) {
      for (const c of ch.toLowerCase()) {
        flat += c;
        for (let k = 0; k < c.length; k += 1) from.push([at, at + ch.length]);
      }
    }
    at += ch.length;
  }
  return {flat, from};
}

// [start, end) ranges of `query` in `text`, ignoring case and spacing: speech-to-text spacing is unreliable, so
// "책 마루" finds 책마루. A match never overlaps the one before it.
export function findRanges(text, query) {
  const needle = fold(String(query)).flat;
  if (!needle) return [];
  const {flat, from} = fold(String(text));
  const ranges = [];
  for (let at = flat.indexOf(needle); at !== -1; at = flat.indexOf(needle, at + needle.length)) {
    ranges.push([from[at][0], from[at + needle.length - 1][1]]);
  }
  return ranges;
}

// `text` cut into [{text, hit}] along the ranges (non-overlapping, ascending); hit pieces carry their index among the ranges.
export function cutAt(text, ranges) {
  const pieces = [];
  let at = 0;
  ranges.forEach(([start, end], index) => {
    if (start > at) pieces.push({text: text.slice(at, start), hit: false});
    pieces.push({text: text.slice(start, end), hit: true, index});
    at = end;
  });
  if (at < text.length) pieces.push({text: text.slice(at), hit: false});
  return pieces;
}

// Confirmed names in prose, by the note's rule (render.replace_speaker_names / particle_for): a speaker number such
// as S2 becomes the name when no letter or digit comes before it and no ASCII letter, digit or underscore after it.
// A Korean particle right after it is made to agree with the name ("S2는" -> "오지안은", "S2가" -> "오지안이").
const PAIRS = { '은': ['은', '는'], '는': ['은', '는'], '이': ['이', '가'], '가': ['이', '가'], '을': ['을', '를'],
  '를': ['을', '를'], '과': ['과', '와'], '와': ['과', '와'] };
export function particleFor(name, particle) {
  if (!particle) return '';
  const last = name.slice(-1);
  if (!(last >= '가' && last <= '힣')) return particle;
  const final = (last.charCodeAt(0) - 0xac00) % 28;
  if (particle === '으로' || particle === '로') return final === 0 || final === 8 ? '로' : '으로';
  return PAIRS[particle][final ? 0 : 1];
}
export function nameSpeakers(text, names) {
  if (!names || !names.size) return text;
  return String(text).replace(/(^|[^\p{L}\p{N}_])(S[1-9]\d*)(?![A-Za-z0-9_])((?:으로|은|는|이|가|을|를|과|와|로)(?![가-힣]))?/gu,
    (whole, before, label, particle) => (names.has(label)
      ? before + names.get(label) + particleFor(names.get(label), particle) : whole));
}
