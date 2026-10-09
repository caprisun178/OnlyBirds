// services/species.js — thin validation layer over the species search DAO.
import { speciesDAO } from '../Dao/species.js';

const MIN_QUERY_LENGTH = 2;

export const speciesService = {
  async search(query) {
    const trimmed = (query || '').trim();
    if (trimmed.length < MIN_QUERY_LENGTH) return [];
    return speciesDAO.search(trimmed);
  },

  // `species` is `[{ scientificName, commonName }, ...]` → a Map keyed by
  // scientific name, so callers can just `.get(sci)` instead of searching
  // an array. Species with no scientific name are silently dropped by the
  // backend (nothing to look up by), so they simply won't be in the map —
  // callers already treat a missing entry as "no photo" either way.
  async getStockPhotos(species) {
    if (species.length === 0) return new Map();
    const payload = species.map((s) => ({ scientific_name: s.scientificName, common_name: s.commonName }));
    const photos = await speciesDAO.photos(payload);
    return new Map(photos.map((p) => [p.scientific_name, p.photo_url]));
  },

  async getProfile(scientificName, commonName, family) {
    return speciesDAO.getProfile(scientificName, commonName, family);
  },
};
