// services/quiz.js — thin layer over the quiz DAO + the shared region-picker
// and user-profile DAOs. No grading logic here: that's a simple equality
// check done in the Presenter (nothing is scored or persisted server-side —
// see docs/features/test-your-skill.md).
import { quizDAO } from '../Dao/quiz.js';
import { regionsDAO } from '../Dao/regions.js';
import { usersDAO } from '../Dao/users.js';

export const quizService = {
  async getQuestion(mode, { regionCode, family } = {}) {
    return quizDAO.getQuestion(mode, { regionCode, family });
  },

  async getFilters(regionCode) {
    return quizDAO.getFilters(regionCode);
  },

  async getAnotherPhoto(scientificName, commonName, excludePhotoUrl) {
    return quizDAO.getAnotherPhoto(scientificName, commonName, excludePhotoUrl);
  },

  // Same region-picker data Life List's cascading country/state/county
  // picker already uses — reused directly, not reimplemented.
  async getRegionOptions(parentCode, type) {
    return regionsDAO.getChildren(parentCode, type);
  },

  // The signed-in user's own `default_region` (e.g. "US-NC") — used to
  // default the quiz's region filter to wherever the user actually birds,
  // instead of always starting at "Anywhere." `usersDAO.getProfile()`
  // throws (not a silent null) if the user doesn't exist yet; the
  // Presenter treats that as "no default available" and falls back to
  // "world," same as before a profile existed at all.
  async getDefaultRegion(userId) {
    const profile = await usersDAO.getProfile(userId);
    return profile.default_region;
  },

  // There's no reverse "name for this code" lookup — a region code only
  // ever comes with a human-readable name as one entry in its *parent's*
  // children list (the same shape the picker itself fetches). Infers the
  // right parent/type from the code's own shape (0 dashes = country, 1 =
  // state/province, 2 = county) and reuses getRegionOptions() to find the
  // matching entry. Falls back to the raw code if anything about that
  // lookup fails — a readable label is a nicety, not worth blocking on.
  async resolveRegionLabel(regionCode) {
    if (!regionCode || regionCode === 'world') return 'Anywhere';
    try {
      const parts = regionCode.split('-');
      const type = parts.length === 1 ? 'country' : parts.length === 2 ? 'subnational1' : 'subnational2';
      const parent = parts.length === 1 ? 'world' : parts.slice(0, -1).join('-');
      const options = await regionsDAO.getChildren(parent, type);
      return options.find((o) => o.code === regionCode)?.name || regionCode;
    } catch (err) {
      return regionCode;
    }
  },
};
