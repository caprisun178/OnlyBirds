// dao/identify.js — raw calls to the describe & guess / photo endpoints.
import { apiClient, BASE_URL } from './apiClient.js';

export const identifyDAO = {
  describe: (text, hints, sense) => apiClient.post('/identify/describe', { text, hints, sense }),
  select: (identificationId, speciesCode) =>
    apiClient.post(`/identify/${identificationId}/select`, { species_code: speciesCode }),

  // Doesn't go through apiClient.js's `request()` — that always sends
  // JSON, this needs multipart/form-data (same reasoning as Dao/uploads.js,
  // and same fix: reuse apiClient's BASE_URL rather than redeclaring it).
  async identifyPhoto(file) {
    const formData = new FormData();
    formData.append('file', file);
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
