// Services/profile.js — shapes the user profile for the screen.
// See docs/features/user-profiles.md.

import { usersDAO } from '../Dao/users.js';
import { getCurrentUserId } from './auth.js';

export const profileService = {
  async getCurrentProfile() {
    const userId = getCurrentUserId();
    try {
      return await usersDAO.getProfile(userId);
    } catch (err) {
      // No `users` row yet (they haven't logged an observation, which is what
      // creates one today) — create it. Placeholder until a sign-up flow exists.
      if (err.status === 404) {
        return usersDAO.create({ auth_provider_id: userId });
      }
      throw err;
    }
  },

  async updateDefaultRegion(userId, regionCode) {
    return usersDAO.update(userId, { default_region: regionCode });
  },

  async updateAvatar(userId, avatarUrl) {
    return usersDAO.update(userId, { avatar_url: avatarUrl });
  },
};
