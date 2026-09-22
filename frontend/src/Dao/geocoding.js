// dao/geocoding.js — raw calls to our geocoding proxy.
import { apiClient } from './apiClient.js';

export const geocodingDAO = {
  search: (query) => apiClient.get(`/geocode/search?q=${encodeURIComponent(query)}`),
  reverse: (lat, lng) => apiClient.get(`/geocode/reverse?lat=${lat}&lng=${lng}`),
};
