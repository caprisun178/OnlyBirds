// dao/identify.js — raw calls to the describe & guess endpoints.
import { apiClient } from './apiClient.js';

export const identifyDAO = {
  describe: (text, hints) => apiClient.post('/identify/describe', { text, hints }),
  select: (identificationId, speciesCode) =>
    apiClient.post(`/identify/${identificationId}/select`, { species_code: speciesCode }),
};
