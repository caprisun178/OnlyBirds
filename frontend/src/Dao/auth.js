// dao/auth.js — raw calls to the sign-in endpoints. No business logic.
// See docs/features/user-profiles.md#auth.
import { apiClient } from './apiClient.js';

export const authDAO = {
  // {google_client_id} — null while sign-in isn't configured on the server.
  getConfig: () => apiClient.get('/auth/config'),
  // Trade Google's ID token for our own session: {token, expires_at, name, profile}.
  signInWithGoogle: (credential) => apiClient.post('/auth/google', { credential }),
  me: () => apiClient.get('/auth/me'),
};
