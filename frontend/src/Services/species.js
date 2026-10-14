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

  // The Bird Info page's profile — see docs/features/bird-info.md.
  // common_name/family/about/sex_differences/migration/habitat are all
  // independently nullable server-side; left as-is (null, not defaulted to
  // '') so the Presenter can tell "not mentioned" apart from "empty string."
  async getProfile(scientificName) {
    const p = await speciesDAO.profile(scientificName);
    return {
      scientificName: p.scientific_name,
      commonName: p.common_name,
      family: p.family,
      photoUrl: p.photo_url,
      photoAttribution: p.photo_attribution,
      audioUrl: p.audio_url,
      audioAttribution: p.audio_attribution,
      about: p.about,
      aboutSourceUrl: p.about_source_url,
      sexDifferences: p.sex_differences,
      migration: p.migration,
      habitat: p.habitat,
    };
  },
};
