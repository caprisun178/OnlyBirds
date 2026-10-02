// services/sightings.js — thin defaults layer over the nearby-sightings DAO.
import { sightingsDAO } from '../Dao/sightings.js';

export const sightingsService = {
  async nearby({ lat, lng, radiusKm = 25, daysBack = 7, source = 'all' }) {
    return sightingsDAO.nearby({ lat, lng, radiusKm, daysBack, source });
  },
};
