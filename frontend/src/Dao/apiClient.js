// dao/apiClient.js — raw transport to our FastAPI backend. No business logic.
//
// No build step means no env-var injection (`process` doesn't exist in a
// browser — that check below never actually fires there; it's just a no-op
// escape hatch for anything that *does* run this under Node, e.g. a future
// test). So the deployed API URL is picked by runtime hostname instead:
// localhost gets the local backend, anything else (GitHub Pages, Vercel,
// Netlify, ...) gets the Render dev backend. Swap the ONRENDER_URL for a
// second hardcoded prod URL once a prod frontend deploy exists.
const ONRENDER_URL = 'https://onlybirds-dev.onrender.com';
const IS_LOCAL =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

export const BASE_URL =
  (typeof process !== 'undefined' && process.env && process.env.API_BASE_URL) ||
  (IS_LOCAL ? 'http://localhost:8000' : ONRENDER_URL);

// Session token from sign-in (Services/auth.js sets it; null = signed out).
// Kept here rather than read from Services/auth.js so this Dao doesn't
// import upward into the Services layer.
let authToken = null;
let onUnauthorized = () => {};

export function setAuthToken(token) {
  authToken = token || null;
}

// Called when a request made *with* a token comes back 401 — the session
// expired or was revoked. Services/auth.js uses it to sign the user out.
export function setOnUnauthorized(handler) {
  onUnauthorized = handler;
}

export function authHeaders() {
  return authToken ? { Authorization: `Bearer ${authToken}` } : {};
}

export function handleUnauthorized(status) {
  if (status === 401 && authToken) onUnauthorized();
}

async function request(method, path, body) {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    handleUnauthorized(resp.status);
    const err = new Error(`${method} ${path} -> ${resp.status}`);
    err.status = resp.status; // lets callers branch on e.g. 404 without parsing the message
    throw err;
  }
  return resp.status === 204 ? null : resp.json();
}

export const apiClient = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  patch: (path, body) => request('PATCH', path, body),
  delete: (path) => request('DELETE', path),
  assetUrl: (path) => new URL(path, BASE_URL).toString(),
};
