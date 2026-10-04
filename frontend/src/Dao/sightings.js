// dao/sightings.js — raw call to the nearby-sightings endpoint.
import { apiClient } from './apiClient.js';

export const sightingsDAO = {
  nearby: ({ lat, lng, radiusKm, daysBack, source }) => {
    const params = new URLSearchParams({
      lat: String(lat),
      lng: String(lng),
      radius_km: String(radiusKm),
      days_back: String(daysBack),
      source,
    });
    return apiClient.get(`/sightings/nearby?${params.toString()}`);
  },
};
