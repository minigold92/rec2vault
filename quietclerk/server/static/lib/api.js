// JSON client for /api. The session cookie is HttpOnly; the CSRF token comes from GET /api/session
// on every page load (never from a stored copy that could belong to an old session). Every
// mutation carries X-CSRF-Token and a fresh Idempotency-Key; the browser adds Origin itself.
export class ApiError extends Error {
  constructor(status, body) {
    super(`HTTP ${status}`);
    this.status = status;   // 0 = the engine could not be reached
    this.body = body;       // parsed JSON error body, or null
  }
}

export const authEvents = new EventTarget();   // 'lost' when any call answers 401
let csrf = '';

function key() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
}

async function call(method, path, body) {
  const headers = {Accept: 'application/json'};
  const init = {method, headers, credentials: 'same-origin'};
  if (method !== 'GET') {
    headers['X-CSRF-Token'] = csrf;
    headers['Idempotency-Key'] = key();
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (_) {
    throw new ApiError(0, null);
  }
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('json') ? await response.json().catch(() => null) : null;
  if (response.status === 401) authEvents.dispatchEvent(new Event('lost'));
  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

export const get = (path) => call('GET', path);
export const post = (path, body) => call('POST', path, body);
export const put = (path, body) => call('PUT', path, body);
export const del = (path) => call('DELETE', path);

export async function openSession() {
  csrf = (await call('GET', '/api/session')).csrf_token;
}

export const jobPath = (id, action) => `/api/jobs/${encodeURIComponent(id)}${action ? '/' + action : ''}`;
