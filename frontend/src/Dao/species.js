// dao/species.js — raw API access only.
import { apiClient } from './apiClient.js';

export const speciesDAO = {
  search: (query) => apiClient.get(`/species/search?q=${encodeURIComponent(query)}`),

  // `species` is `[{ scientific_name, common_name }, ...]`. Returns a
  // guaranteed-non-blank photo per entry (real or placeholder) — see
  // `app/services/species.py#get_stock_photos`.
  photos: (species) => apiClient.post('/species/photos', species),

  // The Bird Info page's full profile — see docs/features/bird-info.md.
  profile: (scientificName) =>
    apiClient.get(`/species/profile?scientific_name=${encodeURIComponent(scientificName)}`),
};
