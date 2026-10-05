// services/trip.js — thin defaults layer over the trip-planning DAO.
import { tripDAO } from '../Dao/trip.js';

export const tripService = {
  async plan({ lat, lng, radiusKm = 25, startDate, endDate, userId }) {
    if (!startDate || !endDate) throw new Error('Both a start and end date are required.');
    if (endDate < startDate) throw new Error('End date can’t be before the start date.');
    return tripDAO.plan({ lat, lng, radiusKm, startDate, endDate, userId });
  },
};
