// dao/observationDAO.js
import { apiClient } from './apiClient.js';

export const observationDAO = {
  getAll: (userId) => apiClient.get(`/users/${userId}/observations`),
  create: (payload) => apiClient.post(`/observations`, payload),
  getById: (id) => apiClient.get(`/observations/${id}`),
};