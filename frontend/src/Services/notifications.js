// services/notifications.js — thin layer over the notifications DAO.
import { notificationsDAO } from '../Dao/notifications.js';

export const notificationsService = {
  async list(userId, unreadOnly = false) {
    return notificationsDAO.list(userId, unreadOnly);
  },

  async unreadCount(userId) {
    const unread = await notificationsDAO.list(userId, true);
    return unread.length;
  },

  async markRead(userId, ids) {
    const result = await notificationsDAO.markRead(userId, ids);
    return result.marked_read;
  },
};
