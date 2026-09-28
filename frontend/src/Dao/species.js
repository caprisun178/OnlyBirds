// dao/species.js — raw API access only.
import { apiClient } from './apiClient.js';

export const speciesDAO = {
  search: (query) => apiClient.get(`/species/search?q=${encodeURIComponent(query)}`),
};
