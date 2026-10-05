// dao/uploads.js — raw call to the photo upload endpoint.
// Doesn't go through apiClient.js's `request()` helper because that always
// sends JSON; this needs multipart/form-data instead. Still reuses its
// BASE_URL rather than redeclaring it — a second copy of that localhost-vs-
// deployed switch previously drifted to a localhost-only hardcode, so photo
// uploads silently tried to reach a backend that doesn't exist on any
// deployed frontend (raw "Failed to fetch", no HTTP status to show).
import { BASE_URL } from './apiClient.js';

export const uploadsDAO = {
  async uploadPhoto(file) {
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(`${BASE_URL}/uploads/photo`, {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.detail || `Upload failed (${resp.status})`);
    }
    return resp.json();
  },
};
