// dao/observationDAO.js
import { apiClient } from './apiClient.js';

export const observationDAO = {
  // `scientificName` scopes this to one species server-side, instead of
  // always shipping a user's entire observation history — see
  // `app/routers/observations.py`'s own note.
  getAll: (userId, scientificName) => {
    const params = scientificName ? `?scientific_name=${encodeURIComponent(scientificName)}` : '';
    return apiClient.get(`/users/${userId}/observations${params}`);
  },
  create: (payload) => apiClient.post(`/observations`, payload),
  getById: (id) => apiClient.get(`/observations/${id}`),
  update: (id, payload) => apiClient.patch(`/observations/${id}`, payload),
};