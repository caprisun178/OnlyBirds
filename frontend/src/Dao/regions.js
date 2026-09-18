// dao/regions.js — raw calls to the region picker + checklist endpoints.
import { apiClient } from './apiClient.js';

export const regionsDAO = {
  getChildren: (parentCode, type) =>
    apiClient.get(`/regions?parent=${encodeURIComponent(parentCode)}&type=${encodeURIComponent(type)}`),

  getChecklist: (regionCode, userId) => {
    const query = userId ? `?user_id=${encodeURIComponent(userId)}` : '';
    return apiClient.get(`/regions/${encodeURIComponent(regionCode)}/checklist${query}`);
  },
};
