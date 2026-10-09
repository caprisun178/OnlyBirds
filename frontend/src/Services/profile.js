// Services/profile.js — shapes the user profile for the screen.
// See docs/features/user-profiles.md.

import { userDao } from '../Dao/user.js';
import { getCurrentUserId } from './auth.js';

// Placeholder until the sign-up flow exists: ensures a `users` row exists for
// this id/username, the same way logging an observation does today.
async function ensureUser(userId) {
  return userDao.create({ auth_provider_id: userId });
}

export const profileService = {
  async getCurrentProfile() {
    const userId = getCurrentUserId();
    try {
      return await userDao.getByUsername(userId);
    } catch (err) {
      // Not created yet (404) — create it, using the id as a placeholder
      // username until the user picks a real one.
      if (String(err.message).includes('404')) {
        return ensureUser(userId);
    }
      throw err;
    }
  },

  async updateDefaultRegion(userId, regionCode) {
    return userDao.update(userId, { default_region: regionCode });
  },

  async updateAvatar(userId, avatarUrl) {
    return userDao.update(userId, { avatar_url: avatarUrl });
  },
};