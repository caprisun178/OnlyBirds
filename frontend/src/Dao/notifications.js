// dao/notifications.js — raw calls to the notification feed endpoints.
import { apiClient } from './apiClient.js';

export const notificationsDAO = {
  list: (userId, unreadOnly = false) => {
    const qs = unreadOnly ? '?unread=true' : '';
    return apiClient.get(`/users/${encodeURIComponent(userId)}/notifications${qs}`);
  },

  markRead: (userId, ids) =>
    apiClient.post(`/users/${encodeURIComponent(userId)}/notifications/read`, ids ? { ids } : {}),
};
