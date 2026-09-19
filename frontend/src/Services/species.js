// services/species.js — thin validation layer over the species search DAO.
import { speciesDAO } from '../Dao/species.js';

const MIN_QUERY_LENGTH = 2;

export const speciesService = {
  async search(query) {
    const trimmed = (query || '').trim();
    if (trimmed.length < MIN_QUERY_LENGTH) return [];
    return speciesDAO.search(trimmed);
  },
};
