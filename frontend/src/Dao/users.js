// dao/users.js — raw calls to the user profile endpoints.
import { apiClient } from './apiClient.js';

export const usersDAO = {
  // By the external id (e.g. 'u1') — what every other `/users/{user_id}/...`
  // endpoint in this app already means by "user id." Distinct from
  // `GET /users/{username}` (the user-chosen display name), which needs a
  // username on hand to look up by; this doesn't.
  getProfile: (userId) => apiClient.get(`/users/by-id/${encodeURIComponent(userId)}`),
};
