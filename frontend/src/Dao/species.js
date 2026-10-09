// dao/species.js — raw API access only.
import { apiClient } from './apiClient.js';

export const speciesDAO = {
  search: (query) => apiClient.get(`/species/search?q=${encodeURIComponent(query)}`),

  // `species` is `[{ scientific_name, common_name }, ...]`. Returns a
  // guaranteed-non-blank photo per entry (real or placeholder) — see
  // `app/services/species.py#get_stock_photos`.
  photos: (species) => apiClient.post('/species/photos', species),

  // The Bird Info page's full profile — see docs/features/bird-info.md.
  // `commonName`/`family` are optional overrides for a caller that already
  // has them (Test Your Skill's reveal, straight from the question's own
  // choices) and shouldn't depend on a taxonomy lookup that's often empty
  // for a species outside this app's own logged history.
  profile: (scientificName, { commonName, family } = {}) => {
    const params = new URLSearchParams({ scientific_name: scientificName });
    if (commonName) params.set('common_name', commonName);
    if (family) params.set('family', family);
    return apiClient.get(`/species/profile?${params.toString()}`);
  },
};
