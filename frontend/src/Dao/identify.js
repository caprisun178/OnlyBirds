// dao/identify.js — raw calls to the describe & guess / photo endpoints.
import { apiClient, BASE_URL } from './apiClient.js';

export const identifyDAO = {
  // `regional` is `{ lat, lng, observed_at }`, already snake_cased by
  // Services/identify.js (same convention as Services/observations.js) —
  // all optional, undefined keys just don't go in the request body. Lets
  // the backend reorder candidates toward what's actually been recorded in
  // that region/day instead of ranking on text/visual similarity alone
  // (see docs/features/bird-id.md §7).
  describe: (text, hints, sense, regional) =>
    apiClient.post('/identify/describe', { text, hints, sense, ...regional }),
  select: (identificationId, speciesCode) =>
    apiClient.post(`/identify/${identificationId}/select`, { species_code: speciesCode }),

  // Doesn't go through apiClient.js's `request()` — that always sends
  // JSON, this needs multipart/form-data (same reasoning as Dao/uploads.js,
  // and same fix: reuse apiClient's BASE_URL rather than redeclaring it).
  async identifyPhoto(file, regional) {
    const formData = new FormData();
    formData.append('file', file);
    if (regional?.lat != null) formData.append('lat', regional.lat);
    if (regional?.lng != null) formData.append('lng', regional.lng);
    if (regional?.observed_at) formData.append('observed_at', regional.observed_at);
    const resp = await fetch(`${BASE_URL}/identify/photo`, {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.detail || `Identify failed (${resp.status})`);
    }
    return resp.json();
  },
};
