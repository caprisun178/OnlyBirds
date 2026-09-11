// dao/lifelist.js — raw API access only.
import { apiClient } from './apiClient.js';

export const lifeListDAO = {
  getAll: (userId) => apiClient.get(`/users/${userId}/life-list`),
};
