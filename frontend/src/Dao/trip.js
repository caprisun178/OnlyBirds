// dao/trip.js — raw call to the trip-planning endpoint.
import { apiClient } from './apiClient.js';

export const tripDAO = {
  plan: ({ lat, lng, radiusKm, startDate, endDate, userId }) => {
    const params = new URLSearchParams({
      lat: String(lat),
      lng: String(lng),
      radius_km: String(radiusKm),
      start_date: startDate,
      end_date: endDate,
    });
    if (userId) params.set('user_id', userId);
    return apiClient.get(`/trip/plan?${params.toString()}`);
  },
};
