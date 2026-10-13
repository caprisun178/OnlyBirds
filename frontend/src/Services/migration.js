// services/migration.js — business logic over the migration calendar DAO.
// See docs/features/migration-calendar.md.
import { migrationDAO } from '../Dao/migration.js';

const POLL_MS = 10000;
const STORAGE_KEY = 'ob-migration-location';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const PATTERN_LABELS = {
  passage: 'Passes through',
  summer: 'Summer visitor',
  winter: 'Winter visitor',
  resident: 'Year-round',
  irregular: 'Irregular',
};

// A location's first request starts a background build on the server and
// comes back `{ status: 'building' }`; keep asking every 10 s until real
// data arrives. `onBuilding()` fires on each building response so the
// screen can say so. `isCancelled()` lets the caller abandon the wait
// (e.g. the user picked a different location meanwhile).
async function untilReady(fetchOnce, { onBuilding, isCancelled }) {
  for (;;) {
    const result = await fetchOnce();
    if (result?.status !== 'building') return result;
    onBuilding?.();
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    if (isCancelled?.()) return null;
  }
}

export const migrationService = {
  getNow(lat, lng, { userId, week, onBuilding, isCancelled } = {}) {
    return untilReady(() => migrationDAO.getNow(lat, lng, { week, userId }), { onBuilding, isCancelled });
  },

  getCalendar(lat, lng, { onBuilding, isCancelled } = {}) {
    return untilReady(() => migrationDAO.getCalendar(lat, lng), { onBuilding, isCancelled });
  },

  // ISO week of the year, 1–52 (53 folded into 52, like the server's data).
  currentWeek(today = new Date()) {
    const d = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
    const day = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.min(52, Math.ceil(((d - yearStart) / 86400000 + 1) / 7));
  },

  // Month a 0-based week index mostly falls in ("May").
  monthOfWeek(index) {
    return MONTHS[Math.min(11, Math.floor((index * 7 + 3) / 30.44))];
  },

  // "Usually here: May, Sep–Oct" — a plain-language summary of a bar strip,
  // for screen readers and the "This week" rows.
  describeWeeks(weekly, threshold = 0.15) {
    const runs = [];
    let start = null;
    for (let i = 0; i <= weekly.length; i += 1) {
      const on = i < weekly.length && weekly[i] >= threshold;
      if (on && start === null) start = i;
      if (!on && start !== null) {
        runs.push([start, i - 1]);
        start = null;
      }
    }
    // Gaps of 1–2 weeks are noise (a quiet week in the data), not a real
    // absence: "Apr–Jun, Jul, Sep–Oct" should read "Apr–Jul, Sep–Oct".
    for (let k = runs.length - 1; k > 0; k -= 1) {
      if (runs[k][0] - runs[k - 1][1] <= 3) {
        runs[k - 1][1] = runs[k][1];
        runs.splice(k, 1);
      }
    }
    // A run touching both ends of the year is one winter run.
    if (runs.length > 1 && runs[0][0] === 0 && runs.at(-1)[1] === weekly.length - 1) {
      const last = runs.pop();
      runs[0] = [last[0], runs[0][1]];
    }
    if (!runs.length) return 'Rarely seen here';
    if (runs.length === 1 && runs[0][0] === 0 && runs[0][1] === weekly.length - 1) return 'Here all year';
    const label = ([a, b]) => {
      const from = this.monthOfWeek(a);
      const to = this.monthOfWeek(b);
      return from === to ? from : `${from}–${to}`;
    };
    return `Usually here: ${runs.map(label).join(', ')}`;
  },

  // Last location used on this screen — localStorage only, per browser.
  // Never throws (private windows / blocked storage just mean "none").
  loadLocation() {
    try {
      const loc = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      return loc && typeof loc.lat === 'number' && typeof loc.lng === 'number' ? loc : null;
    } catch {
      return null;
    }
  },

  saveLocation(loc) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
    } catch {
      // Remembering the spot is a convenience, not worth an error.
    }
  },
};
