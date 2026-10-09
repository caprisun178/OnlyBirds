// dao/species.js — raw API access only.
import { apiClient } from './apiClient.js';

export const speciesDAO = {
  search: (query) => apiClient.get(`/species/search?q=${encodeURIComponent(query)}`),

  // `species` is `[{ scientific_name, common_name }, ...]`. Returns a
  // guaranteed-non-blank photo per entry (real or placeholder) — see
  // `app/services/species.py#get_stock_photos`.
  photos: (species) => apiClient.post('/species/photos', species),

  // Full profile bundle (photo, audio, About text, habitat) — see
  // `app/services/species.py#get_profile`. First real caller: Test Your
  // Skill's post-answer reveal.
  getProfile: (scientificName, commonName, family) => {
    const params = new URLSearchParams({ scientific_name: scientificName, common_name: commonName });
    if (family) params.set('family', family);
    return apiClient.get(`/species/profile?${params.toString()}`);
  },
};
