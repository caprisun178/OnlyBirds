// services/geocoding.js — thin validation layer over the geocoding DAO.
import { geocodingDAO } from '../Dao/geocoding.js';

const MIN_QUERY_LENGTH = 3;

export const geocodingService = {
  async search(query) {
    const trimmed = (query || '').trim();
    if (trimmed.length < MIN_QUERY_LENGTH) return [];
    return geocodingDAO.search(trimmed);
  },

  // Returns null if no address is known for that point — a click far from
  // any mapped place is still a valid pin, just without a readable name.
  async reverse(lat, lng) {
    return geocodingDAO.reverse(lat, lng);
  },
};
