// dao/bugReports.js — raw calls to the admin bug-backlog endpoints. See
// Presenters/BugBacklog.js. The "Report a problem" button's own submit call
// still goes through Dao/feedback.js — this is only the admin-side read/update.
import { apiClient } from './apiClient.js';

export const bugReportsDAO = {
  list: () => apiClient.get('/admin/bug-reports'),
  // `patch` is `{ status?, owner? }` — only whichever keys are present get
  // touched server-side (FastAPI's exclude_unset, see BugReportUpdate).
  update: (id, patch) => apiClient.patch(`/admin/bug-reports/${id}`, patch),
};
