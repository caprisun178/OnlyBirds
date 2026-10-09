// Dao/user.js — raw calls to the user profile endpoints. No business logic.
// See docs/features/user-profiles.md.

import { apiClient } from './apiClient.js';

export const userDao = {
  getByUsername: (username) => apiClient.get(`/users/${encodeURIComponent(username)}`),
  create: (payload) => apiClient.post('/users', payload),
  update: (userId, changes) => apiClient.patch(`/users/${encodeURIComponent(userId)}`, changes),
};
