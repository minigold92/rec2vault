// Live engine state: /api/events (SSE) carries engine, paused, counts, current job and the job list
// signature; /api/status adds providers and phone sync, which the stream does not carry.
// Elapsed time is derived here from the snapshot (the server sends it once per change).
import {get, openSession} from './api.js';

export const live = {
  snapshot: null,       // last SSE 'state' payload
  status: null,         // last GET /api/status payload
  connected: false,
  failed: false,        // the stream broke (or never opened): engine unreachable
  lastEvent: null,      // Date of the last data from the engine
  receivedAt: 0,        // performance.now() when the snapshot arrived
  authLost: false,
};

const listeners = new Set();
let source = null;
let retry = null;
let delay = 2000;
let statusTimer = null;

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const emit = () => { for (const fn of listeners) fn(live); };

export function markAuthLost() {
  live.authLost = true;
  emit();
}

export async function refreshStatus() {
  try {
    live.status = await get('/api/status');
    live.lastEvent = new Date();
  } catch (error) {
    if (error.status === 0) live.failed = true;
  }
  emit();
  return live.status;
}

export function connect() {
  clearTimeout(retry);
  if (source) source.close();
  source = new EventSource('/api/events');
  source.onopen = () => {
    live.connected = true;
    live.failed = false;
    delay = 2000;
    emit();
  };
  source.addEventListener('state', (event) => {
    live.snapshot = JSON.parse(event.data);
    live.receivedAt = performance.now();
    live.lastEvent = new Date();
    live.connected = true;
    live.failed = false;
    emit();
  });
  source.onerror = () => {
    live.connected = false;
    live.failed = true;
    emit();
    // A refused stream (for example the session ended) is closed for good: check the session, then retry.
    if (source.readyState === EventSource.CLOSED) {
      retry = setTimeout(reconnect, delay);
      delay = Math.min(delay * 2, 30000);
    }
  };
  clearInterval(statusTimer);
  statusTimer = setInterval(refreshStatus, 30000);
}

export async function reconnect() {
  try {
    await openSession();
    live.authLost = false;
  } catch (error) {
    if (error.status === 401) {
      markAuthLost();
      return;
    }
  }
  connect();
}

// Seconds the current stage / the whole job have been running, extrapolated from the snapshot.
export function elapsed() {
  const s = live.snapshot;
  if (!s || s.elapsed_sec === null || s.elapsed_sec === undefined) return null;
  const now = s.elapsed_sec + (performance.now() - live.receivedAt) / 1000;
  const started = s.stage ? s.stage.started_at : (s.current_job && s.current_job.claimed_at);
  const claimed = s.current_job && s.current_job.claimed_at;
  return {stage: now, total: started && claimed ? now + (started - claimed) : now};
}
