// dao/lifelist.js — raw API access only.
import { apiClient } from './apiClient';

export const lifeListDAO = {
  getAll: (userId) => apiClient.get(`/users/${userId}/life-list`),
};
