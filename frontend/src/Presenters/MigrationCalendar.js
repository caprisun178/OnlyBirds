// presenters/MigrationCalendar.js — "what birds should be passing through
// here right now, and when do the others show up?" See
// docs/features/migration-calendar.md.
//
// Pick a location (place search, "use my location", or a recent spot) →
// two tabs over the same per-area data:
//   This week — migrants arriving / at peak / leaving, with photos + pins.
//   Full year — every species as a 52-week bar strip, filterable.
// A location's first visit can take a few minutes while the server builds
// that area's calendar; Services/migration.js polls until it's ready.
import { migrationService, PATTERN_LABELS } from '../Services/migration.js';
import { geocodingService } from '../Services/geocoding.js';
import { lifeListService } from '../Services/lifeList.js';
import { pinsService } from '../Services/pins.js';
import { recentLocationsService } from '../Services/recentLocations.js';
import { getCurrentUser } from '../testData/testProfile.js';
import { escapeHtml } from '../Components/CandidateList.js';
import { renderBarStrip, renderMonthAxis } from '../Components/MigrationBarStrip.js';

const PATTERN_FILTERS = ['passage', 'summer', 'winter', 'resident', 'irregular'];
const NOW_SECTIONS = [
  ['arriving', 'Arriving', 'Numbers usually start rising around now.'],
  ['peak', 'Peak now', 'Usually at or near their highest numbers this week.'],
  ['leaving', 'Leaving', 'Usually thinning out — last chances for a while.'],
];

export function mount(container, props = {}) {
  const userId = props.userId || getCurrentUser().id;
  const { onNavigate } = props;
  const week = migrationService.currentWeek();

  const state = {
    location: migrationService.loadLocation(), // { lat, lng, label }
    tab: 'now', // 'now' | 'year'
    loading: false,
    building: false,
    error: null,
    now: null,
    calendar: null,
    patternFilter: new Set(['passage', 'summer', 'winter']),
    notOnLifeListOnly: false,
    seenNames: null, // Set of lowercased scientific names, loaded on demand
    pinnedNames: new Set(),
    pinError: null,
    query: '',
    searchResults: [],
    searching: false,
  };
  let requestId = 0; // a newer location/tab load cancels the older one's polling

  render();
  loadPins();
  if (state.location) load();

  // ---- data --------------------------------------------------------------

  async function load() {
    const id = (requestId += 1);
    const { lat, lng } = state.location;
    Object.assign(state, { loading: true, building: false, error: null });
    render();
    const options = {
      onBuilding: () => {
        if (id !== requestId) return;
        state.building = true;
        render();
      },
      isCancelled: () => id !== requestId,
    };
    try {
      if (state.tab === 'now') {
        const data = await migrationService.getNow(lat, lng, { userId, week, ...options });
        if (id !== requestId || !data) return;
        state.now = data;
      } else {
        const data = await migrationService.getCalendar(lat, lng, options);
        if (id !== requestId || !data) return;
        state.calendar = data;
      }
    } catch (err) {
      if (id !== requestId) return;
      state.error = err.message || 'Could not load the migration calendar. Try again in a moment.';
    }
    Object.assign(state, { loading: false, building: false });
    render();
  }

  async function loadPins() {
    try {
      const pins = await pinsService.list(userId);
      state.pinnedNames = new Set(pins.map((p) => p.scientific_name.toLowerCase()));
      render();
    } catch {
      // Pin buttons just show as unpinned until this loads.
    }
  }

  async function loadSeenNames() {
    if (state.seenNames) return;
    try {
      state.seenNames = new Set([...await lifeListService.getSeenScientificNames(userId)].map((n) => n.toLowerCase()));
    } catch {
      state.seenNames = new Set();
    }
  }

  function setLocation(loc) {
    state.location = loc;
    state.now = null;
    state.calendar = null;
    state.searchResults = [];
    migrationService.saveLocation(loc);
    load();
  }

  // ---- rendering ---------------------------------------------------------

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Migration calendar</h1>
        <p class="ob-text-muted">Which birds usually pass through an area, and when.</p>
        ${renderLocationPicker()}
        ${state.location ? renderTabs() : ''}
        ${state.pinError ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.pinError)}</div>` : ''}
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${renderContent()}
        ${state.location ? `
          <p class="ob-hint">Based on iNaturalist research-grade photo observations from all years, within about 40 km.
          Birds that are hard to photograph may look rarer than they are, and timing shifts with the weather each year,
          so this is typical timing, not a forecast.</p>` : ''}
      </div>
    `;
    wire();
  }

  function renderLocationPicker() {
    const recents = recentLocationsService.list();
    return `
      <div class="ob-card ob-stack" style="--ob-stack-gap: var(--ob-space-2);">
        ${state.location ? `<p><strong>${escapeHtml(state.location.label)}</strong></p>` : '<p>Choose a location to see its calendar.</p>'}
        <div class="ob-cluster">
          <input class="ob-input" style="flex:1;min-width:200px;" data-role="place-search" placeholder="Search for a town, park or address" autocomplete="off" value="${escapeHtml(state.query)}" />
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="search">Search</button>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="my-location">Use my location</button>
        </div>
        ${state.searching ? '<p class="ob-text-muted ob-text-sm">Searching…</p>' : ''}
        ${state.searchResults.map((r, i) => `
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--block ob-text-sm" style="justify-content:flex-start;" data-result-index="${i}">${escapeHtml(r.display_name)}</button>
        `).join('')}
        ${recents.length ? `
          <div class="ob-cluster ob-text-sm" style="align-items:center;">
            <span class="ob-text-muted">Recent:</span>
            ${recents.map((loc, i) => `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-recent-index="${i}">${escapeHtml(loc.locationName)}</button>`).join('')}
          </div>` : ''}
      </div>
    `;
  }

  function renderTabs() {
    const tab = (key, label) => `<button type="button" class="ob-btn ${state.tab === key ? 'ob-btn--primary' : 'ob-btn--ghost'}" role="tab" aria-selected="${state.tab === key}" data-tab="${key}">${label}</button>`;
    return `<div class="ob-cluster" role="tablist" aria-label="Migration calendar views">${tab('now', 'This week')}${tab('year', 'Full year')}</div>`;
  }

  function renderContent() {
    if (!state.location) return '';
    if (state.building) {
      return `
        <div class="ob-card ob-stack ob-text-center">
          <div class="ob-spinner" style="margin-inline:auto"></div>
          <p><strong>Building the calendar for this area.</strong></p>
          <p class="ob-text-muted">The first visit to an area gathers a full year of sightings, which takes a few minutes.
          It's saved afterwards, so it's instant for everyone nearby from then on. You can leave this page open.</p>
        </div>
      `;
    }
    if (state.loading) {
      return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
    }
    const data = state.tab === 'now' ? state.now : state.calendar;
    if (!data) return '';
    return `${renderQualityBanner(data)}${state.tab === 'now' ? renderNow(data) : renderYear(data)}`;
  }

  function renderQualityBanner(data) {
    if (data.data_quality === 'insufficient') {
      return '<div class="ob-alert ob-alert--warning">There are too few bird sightings around here to build a reliable calendar. Try a nearby town or city.</div>';
    }
    if (data.data_quality === 'limited') {
      return '<div class="ob-alert ob-alert--warning">Not much data here yet, so this calendar may be incomplete.</div>';
    }
    return data.refreshing ? '<p class="ob-hint">Updating this calendar with newer sightings in the background.</p>' : '';
  }

  function renderNow(data) {
    if (data.data_quality === 'insufficient') return '';
    const any = data.arriving.length + data.peak.length + data.leaving.length;
    if (!any) return '<div class="ob-card"><p>No migrants are usually moving through here this week.</p></div>';
    return NOW_SECTIONS.map(([key, title, hint]) => (data[key].length ? `
      <section class="ob-stack" style="--ob-stack-gap: var(--ob-space-2);">
        <h2>${title} <span class="ob-text-muted ob-text-sm">(${data[key].length})</span></h2>
        <p class="ob-hint">${hint}</p>
        <div class="ob-grid" style="--ob-grid-min: 280px;">${data[key].map(renderNowCard).join('')}</div>
      </section>` : '')).join('');
  }

  function renderNowCard(sp) {
    const name = sp.common_name || sp.scientific_name;
    const pinned = state.pinnedNames.has(sp.scientific_name.toLowerCase());
    const summary = migrationService.describeWeeks(sp.weekly);
    return `
      <div class="ob-card ob-stack" style="--ob-stack-gap: var(--ob-space-2);">
        <div class="ob-cluster" style="align-items:center;flex-wrap:nowrap;">
          ${sp.photo_url ? `<img src="${escapeHtml(sp.photo_url)}" alt="" loading="lazy" style="width:64px;height:64px;object-fit:cover;border-radius:var(--ob-radius-md);flex:none;" />` : ''}
          <div class="ob-stack" style="--ob-stack-gap: 2px;min-width:0;">
            <button type="button" class="ob-btn ob-btn--subtle ob-btn--sm" style="justify-content:flex-start;padding:0;" data-profile="${escapeHtml(sp.scientific_name)}" data-profile-name="${escapeHtml(name)}"><strong>${escapeHtml(name)}</strong></button>
            <span class="ob-text-sm ob-text-muted">${PATTERN_LABELS[sp.pattern]} · ${escapeHtml(summary)}</span>
            ${sp.on_life_list === false ? '<span class="ob-tag ob-tag--success" style="align-self:flex-start;">New for you</span>' : ''}
          </div>
        </div>
        ${renderBarStrip(sp.weekly, { currentWeek: week, label: summary })}
        ${renderMonthAxis()}
        ${sp.on_life_list ? '' : `
          <button type="button" class="ob-btn ob-btn--sm ${pinned ? 'ob-btn--primary' : 'ob-btn--ghost'}" style="align-self:flex-start;"
                  data-action="toggle-pin" data-pin-scientific-name="${escapeHtml(sp.scientific_name)}" data-pin-common-name="${escapeHtml(name)}">
            ${pinned ? 'Pinned — you’ll hear when it’s reported' : 'Pin it: tell me when one’s reported'}
          </button>`}
      </div>
    `;
  }

  function renderYear(data) {
    if (data.data_quality === 'insufficient') return '';
    const rows = data.species.filter((sp) => state.patternFilter.has(sp.pattern)
      && (!state.notOnLifeListOnly || !state.seenNames?.has(sp.scientific_name.toLowerCase())));
    return `
      <div class="ob-card ob-stack">
        <div class="ob-cluster ob-text-sm" style="align-items:center;">
          ${PATTERN_FILTERS.map((p) => `
            <label class="ob-cluster" style="align-items:center;gap:4px;">
              <input type="checkbox" data-pattern="${p}" ${state.patternFilter.has(p) ? 'checked' : ''} /> ${PATTERN_LABELS[p]}
            </label>`).join('')}
          <label class="ob-cluster" style="align-items:center;gap:4px;margin-left:auto;">
            <input type="checkbox" data-role="not-seen" ${state.notOnLifeListOnly ? 'checked' : ''} /> Not on my life list
          </label>
        </div>
        <p class="ob-text-sm ob-text-muted">${rows.length} species. The outlined column is this week.</p>
        <div style="display:grid;grid-template-columns:minmax(140px,220px) 1fr;gap:6px 12px;align-items:center;">
          <span></span>${renderMonthAxis()}
          ${rows.map((sp) => {
            const name = sp.common_name || sp.scientific_name;
            const summary = migrationService.describeWeeks(sp.weekly);
            return `
              <button type="button" class="ob-btn ob-btn--subtle ob-btn--sm ob-text-sm" style="justify-content:flex-start;padding:0;text-align:left;" title="${escapeHtml(`${PATTERN_LABELS[sp.pattern]} · ${summary}`)}"
                      data-profile="${escapeHtml(sp.scientific_name)}" data-profile-name="${escapeHtml(name)}">${escapeHtml(name)}</button>
              ${renderBarStrip(sp.weekly, { currentWeek: week, label: `${name}: ${summary}` })}`;
          }).join('')}
        </div>
      </div>
    `;
  }

  // ---- events --------------------------------------------------------------

  function wire() {
    container.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      requestId += 1; // stop any polling
      onNavigate('home');
    });

    const searchInput = container.querySelector('[data-role="place-search"]');
    const runSearch = async () => {
      const q = searchInput.value.trim();
      state.query = searchInput.value;
      if (!q) return;
      state.searching = true;
      render();
      try {
        state.searchResults = await geocodingService.search(q);
        if (!state.searchResults.length) state.error = 'No places found. Try a different search.';
        else state.error = null;
      } catch {
        state.error = 'Place search failed. Try again in a moment.';
      }
      state.searching = false;
      render();
    };
    container.querySelector('[data-action="search"]').addEventListener('click', runSearch);
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runSearch();
      }
    });
    container.querySelectorAll('[data-result-index]').forEach((btn) => btn.addEventListener('click', () => {
      const r = state.searchResults[Number(btn.dataset.resultIndex)];
      setLocation({ lat: r.lat, lng: r.lng, label: r.display_name });
    }));
    container.querySelectorAll('[data-recent-index]').forEach((btn) => btn.addEventListener('click', () => {
      const loc = recentLocationsService.list()[Number(btn.dataset.recentIndex)];
      if (loc) setLocation({ lat: loc.lat, lng: loc.lng, label: loc.locationName });
    }));
    container.querySelector('[data-action="my-location"]').addEventListener('click', () => {
      if (!navigator.geolocation) {
        state.error = 'Your browser can’t share your location. Search for a place instead.';
        render();
        return;
      }
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const { latitude: lat, longitude: lng } = pos.coords;
          let label = 'My location';
          try {
            label = (await geocodingService.reverse(lat, lng))?.display_name || label;
          } catch {
            // A coordinate-only label is fine.
          }
          setLocation({ lat, lng, label });
        },
        () => {
          state.error = 'Couldn’t get your location. Search for a place instead.';
          render();
        },
        { timeout: 10000 },
      );
    });

    container.querySelectorAll('[data-tab]').forEach((btn) => btn.addEventListener('click', () => {
      if (state.tab === btn.dataset.tab) return;
      state.tab = btn.dataset.tab;
      if ((state.tab === 'now' && !state.now) || (state.tab === 'year' && !state.calendar)) load();
      else render();
    }));

    container.querySelectorAll('[data-pattern]').forEach((box) => box.addEventListener('change', () => {
      if (box.checked) state.patternFilter.add(box.dataset.pattern);
      else state.patternFilter.delete(box.dataset.pattern);
      render();
    }));
    container.querySelector('[data-role="not-seen"]')?.addEventListener('change', async (e) => {
      state.notOnLifeListOnly = e.target.checked;
      if (state.notOnLifeListOnly) await loadSeenNames();
      render();
    });

    container.querySelectorAll('[data-profile]').forEach((btn) => btn.addEventListener('click', () => {
      if (!onNavigate) return;
      requestId += 1;
      onNavigate('species-profile', { scientificName: btn.dataset.profile, commonName: btn.dataset.profileName });
    }));

    container.querySelectorAll('[data-action="toggle-pin"]').forEach((btn) => btn.addEventListener('click', async () => {
      const sci = btn.dataset.pinScientificName;
      const key = sci.toLowerCase();
      state.pinError = null;
      try {
        if (state.pinnedNames.has(key)) {
          await pinsService.unpin(userId, sci);
          state.pinnedNames.delete(key);
        } else {
          await pinsService.pin(userId, { scientificName: sci, commonName: btn.dataset.pinCommonName });
          state.pinnedNames.add(key);
        }
      } catch (err) {
        state.pinError = err.message || 'Could not update that pin. Try again in a moment.';
      }
      render();
    }));
  }
}
