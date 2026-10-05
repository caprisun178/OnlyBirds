// dao/feedback.js — raw call to the beta "Report a problem" endpoint.
import { apiClient } from './apiClient.js';

export const feedbackDAO = {
  create: (report) => apiClient.post('/feedback', report),
};
