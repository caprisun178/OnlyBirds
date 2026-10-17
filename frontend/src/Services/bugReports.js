// Services/bugReports.js — thin pass-through for the admin bug-backlog
// screen; no client-side shaping needed beyond what the DAO already returns.
import { bugReportsDAO } from '../Dao/bugReports.js';

export const bugReportsService = {
  list: () => bugReportsDAO.list(),
  update: (id, patch) => bugReportsDAO.update(id, patch),
};
