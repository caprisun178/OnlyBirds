// services/pins.js — thin validation/defaults layer over the pins DAO.
import { pinsDAO } from '../Dao/pins.js';

export const pinsService = {
  async list(userId) {
    return pinsDAO.list(userId);
  },

  async pin(userId, { scientificName, commonName, region }) {
    if (!scientificName) throw new Error('A species is required to pin it.');
    try {
      return await pinsDAO.create(userId, { scientificName, commonName, region });
    } catch (err) {
      // apiClient's error is just "`METHOD path -> status`" — no body — so
      // the 409 ("already on your life list — nothing to chase", see
      // app/routers/pins.py) is detected by status code rather than message text.
      if (String(err.message).includes('-> 409')) {
        throw new Error('Already on your life list — nothing to chase.');
      }
      throw err;
    }
  },

  async updateRegion(userId, scientificName, region) {
    if (!region) throw new Error('A region is required.');
    return pinsDAO.updateRegion(userId, scientificName, region);
  },

  async unpin(userId, scientificName) {
    return pinsDAO.remove(userId, scientificName);
  },
};
