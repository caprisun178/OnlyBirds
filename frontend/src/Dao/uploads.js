// dao/uploads.js — raw call to the photo upload endpoint.
// Separate from apiClient.js because that helper always sends JSON;
// this needs multipart/form-data instead.
const BASE_URL =
  (typeof process !== 'undefined' && process.env && process.env.API_BASE_URL) ||
  'http://localhost:8000';

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
