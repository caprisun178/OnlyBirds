// dao/apiClient.js — raw transport to our FastAPI backend. No business logic.
const BASE_URL =
  (typeof process !== 'undefined' && process.env && process.env.API_BASE_URL) ||
  'http://localhost:8000';

async function request(method, path, body) {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(`${method} ${path} -> ${resp.status}`);
  }
  return resp.status === 204 ? null : resp.json();
}

export const apiClient = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body),
  put: (path, body) => request('PUT', path, body),
  delete: (path) => request('DELETE', path),
};
