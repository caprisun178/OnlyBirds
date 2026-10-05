// dao/pins.js — raw calls to the Pinned Birds endpoints.
import { apiClient } from './apiClient.js';

export const pinsDAO = {
  list: (userId) => apiClient.get(`/users/${encodeURIComponent(userId)}/pins`),

  create: (userId, { scientificName, commonName, region }) => {
    const body = { scientific_name: scientificName };
    if (commonName) body.common_name = commonName;
    if (region) body.region = region;
    return apiClient.post(`/users/${encodeURIComponent(userId)}/pins`, body);
  },

  updateRegion: (userId, scientificName, region) =>
    apiClient.patch(
      `/users/${encodeURIComponent(userId)}/pins/${encodeURIComponent(scientificName)}`,
      { region }
    ),

  remove: (userId, scientificName) =>
    apiClient.delete(`/users/${encodeURIComponent(userId)}/pins/${encodeURIComponent(scientificName)}`),
};
