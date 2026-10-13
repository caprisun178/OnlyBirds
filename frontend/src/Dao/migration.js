// dao/migration.js — raw calls to the migration calendar endpoints.
// Both return `{ status: "building", cell_id }` (HTTP 202) while a location's
// calendar is being built for the first time — see Services/migration.js.
import { apiClient } from './apiClient.js';

function query(params) {
  return new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString();
}

export const migrationDAO = {
  getCalendar: (lat, lng) => apiClient.get(`/migration/calendar?${query({ lat, lng })}`),
  getNow: (lat, lng, { week, userId } = {}) => apiClient.get(`/migration/now?${query({ lat, lng, week, user_id: userId })}`),
};
