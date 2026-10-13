// dao/observationDAO.js
import { apiClient } from './apiClient.js';

export const observationDAO = {
  getAll: (userId) => apiClient.get(`/users/${userId}/observations`),
  create: (payload) => apiClient.post(`/observations`, payload),
  getById: (id) => apiClient.get(`/observations/${id}`),
  update: (id, payload) => apiClient.patch(`/observations/${id}`, payload),
  // Bulk import undo — deletes every observation tagged with that batch id.
  undoImport: (userId, importBatchId) => apiClient.delete(`/users/${userId}/imports/${encodeURIComponent(importBatchId)}`),
};