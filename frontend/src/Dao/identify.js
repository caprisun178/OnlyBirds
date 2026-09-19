// dao/identify.js — raw calls to the describe & guess endpoints.
import { apiClient } from './apiClient.js';

export const identifyDAO = {
  describe: (text, hints, sense) => apiClient.post('/identify/describe', { text, hints, sense }),
  select: (identificationId, speciesCode) =>
    apiClient.post(`/identify/${identificationId}/select`, { species_code: speciesCode }),
};
