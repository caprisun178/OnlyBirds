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

  hotspotSightings: ({ lat, lng, radiusKm, startDate, endDate, locId }) => {
    const params = new URLSearchParams({
      lat: String(lat),
      lng: String(lng),
      start_date: startDate,
      end_date: endDate,
    });
    if (radiusKm) params.set('radius_km', String(radiusKm));
    // Lets the backend also merge in eBird checklist data for this exact
    // hotspot (it accepts a hotspot's own locId in place of a region code —
    // see app/dao/ebird.py#get_historic_checklist). Omitted, results stay
    // iNaturalist-only.
    if (locId) params.set('loc_id', locId);
    return apiClient.get(`/trip/hotspot-sightings?${params.toString()}`);
  },
};
