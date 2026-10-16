// Services/recentLocations.js — "remember my favorite spots," the
// lightweight way: an automatic, per-browser cache of the last few distinct
// locations actually used to log an observation (not every map click —
// see AddObservation.js's wireFieldNotesSubmit, the only caller of
// `remember()`), surfaced as quick-select chips above the address search in
// the location picker. No backend, no login needed, no "manage your
// favorites" UI — localStorage only. If a real cross-device, user-curated
// favorites list is ever wanted, that's a bigger, separate feature (a new
// table + endpoints), not this.

const STORAGE_KEY = 'ob-recent-locations';
const MAX_RECENT = 5;

export const recentLocationsService = {
  // Most-recently-used first. Never throws — a private window, blocked
  // storage, or corrupted JSON all just mean "no recents," not a broken page.
  list() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  },

  remember({ lat, lng, locationName }) {
    if (lat == null || lng == null || !locationName) return; // nothing worth remembering
    try {
      const deduped = recentLocationsService.list().filter((loc) => loc.locationName !== locationName);
      const updated = [{ lat, lng, locationName }, ...deduped].slice(0, MAX_RECENT);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    } catch (err) {
      // Quota exceeded or storage blocked — remembering a recent spot is a
      // nicety, not something worth surfacing an error for.
    }
  },
};
