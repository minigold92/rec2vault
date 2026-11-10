// Formatting helpers. Server times are epoch seconds; recording times come from the job id
// (YYYYMMDD-HHMMSS, the recorder's local clock) and are never reinterpreted through a time zone.
import {L} from './i18n.js';

const pad = (n) => String(n).padStart(2, '0');

export function dur(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const hours = Math.floor(total / 3600), minutes = Math.floor(total % 3600 / 60), secs = total % 60;
  if (hours) return L(`${hours}시간 ${minutes}분`, `${hours} h ${minutes} min`);
  if (minutes) return secs ? L(`${minutes}분 ${secs}초`, `${minutes} min ${secs} s`) : L(`${minutes}분`, `${minutes} min`);
  return L(`${secs}초`, `${secs} s`);
}

// Running clock, m:ss or h:mm:ss.
export function clock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  return hours ? `${hours}:${pad(Math.floor(total % 3600 / 60))}:${pad(total % 60)}` : `${Math.floor(total / 60)}:${pad(total % 60)}`;
}

// Evidence time, mm:ss (h:mm:ss from one hour), same rule as the note renderer.
export function stamp(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(total / 3600);
  return hours ? `${hours}:${pad(Math.floor(total % 3600 / 60))}:${pad(total % 60)}` : `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
}

export function parseRecorded(value) {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(String(value || ''));
  return match ? {y: +match[1], mo: +match[2], d: +match[3], h: +match[4], mi: +match[5]} : null;
}

const WEEKDAY = {ko: ['일', '월', '화', '수', '목', '금', '토'], en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']};
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "11-10 10:00" (list rows), "11월 10일 10:00" is not needed anywhere else.
export function shortDate(recorded) {
  const t = parseRecorded(recorded);
  return t ? `${pad(t.mo)}-${pad(t.d)} ${pad(t.h)}:${pad(t.mi)}` : '';
}

export function monthDayTime(recorded) {
  const t = parseRecorded(recorded);
  if (!t) return '';
  return L(`${t.mo}월 ${t.d}일 ${pad(t.h)}:${pad(t.mi)}`, `${MONTH[t.mo - 1]} ${t.d}, ${pad(t.h)}:${pad(t.mi)}`);
}

export function fullDate(recorded) {
  const t = parseRecorded(recorded);
  if (!t) return '';
  const weekday = new Date(t.y, t.mo - 1, t.d).getDay();
  return L(`${t.y}년 ${t.mo}월 ${t.d}일 (${WEEKDAY.ko[weekday]}) ${pad(t.h)}:${pad(t.mi)}`,
    `${WEEKDAY.en[weekday]}, ${MONTH[t.mo - 1]} ${t.d} ${t.y}, ${pad(t.h)}:${pad(t.mi)}`);
}

export function localTime(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function sameLocalDay(epochSeconds, now = new Date()) {
  const a = new Date(epochSeconds * 1000);
  return a.getFullYear() === now.getFullYear() && a.getMonth() === now.getMonth() && a.getDate() === now.getDate();
}

export function gigabytes(bytes) {
  const value = Math.round(bytes / 1024 ** 3 * 10) / 10;
  const text = value >= 100 ? String(Math.round(value)) : String(value);
  return L(`${text}GB`, `${text} GB`);
}

// "11-09 21:04" from epoch seconds (the engine's own clock, shown in local time).
export function shortEpoch(epochSeconds) {
  const date = new Date(epochSeconds * 1000);
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// Recorder file name -> recording time: "음성 261110_100000.m4a" -> "20261110-100000".
export function recordedFromName(name) {
  const match = /(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(String(name || ''));
  return match ? `20${match[1]}${match[2]}${match[3]}-${match[4]}${match[5]}${match[6]}` : null;
}
