// dao/stickers.js — raw sticker API access only.
import { apiClient } from './apiClient.js';

export const stickersDAO = {
  // Fetch the catalog of every sticker the application supports.
  getCatalog: () => apiClient.get('/stickers'),
  // Fetch one user's earned and locked sticker shelf.
  getForUser: (userId) => apiClient.get(`/users/${encodeURIComponent(userId)}/stickers`),
  // Sticker art is served by the API rather than the static frontend host.
  assetUrl: (path) => apiClient.assetUrl(path),
};