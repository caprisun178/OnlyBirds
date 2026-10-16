// dao/quiz.js — raw calls to the Test Your Skill quiz endpoints.
import { apiClient } from './apiClient.js';

export const quizDAO = {
  getQuestion: (mode, { regionCode, family } = {}) => {
    const params = new URLSearchParams({ mode });
    if (regionCode) params.set('region_code', regionCode);
    if (family) params.set('family', family);
    return apiClient.get(`/quiz/question?${params.toString()}`);
  },

  // Distinct taxonomic families present in a region's checklist, each with
  // a species count — feeds the "type" filter dropdown. Region-picker
  // options themselves (country/state/county) reuse `Dao/regions.js`'s
  // `regionsDAO` directly — that's a generic, already-shared endpoint, not
  // quiz-specific, so it doesn't need its own wrapper here.
  getFilters: (regionCode) =>
    apiClient.get(`/quiz/filters?region_code=${encodeURIComponent(regionCode)}`),

  // "Try another photo" — same species, a different reference image.
  getAnotherPhoto: (scientificName, commonName, excludePhotoUrl) => {
    const params = new URLSearchParams({
      scientific_name: scientificName,
      common_name: commonName,
      exclude_photo_url: excludePhotoUrl,
    });
    return apiClient.get(`/quiz/another-photo?${params.toString()}`);
  },
};
