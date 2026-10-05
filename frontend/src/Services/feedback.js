// services/feedback.js — attaches the context a bug report needs (which
// screen, what URL, whose session, which browser) so the reporter only ever
// has to type what went wrong.
import { feedbackDAO } from '../Dao/feedback.js';

export const feedbackService = {
  async sendReport({ message, screen, userId }) {
    return feedbackDAO.create({
      message,
      screen,
      user_id: userId,
      url: typeof window !== 'undefined' ? window.location.href : undefined,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    });
  },
};
