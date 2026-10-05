// Presenters/ExploreMap.js — the Explore Map screen (MVP scope).
//
//   import { mount } from './Presenters/ExploreMap.js';
//   mount(document.getElementById('app'), { userId: 'u1' });
//
// This is deliberately the small version of docs/features/explore-map.md:
// that page's full spec is viewport-driven fetch + pin clustering + a new
// `sighting_cache` table + `observations.geom` (PostGIS) + source dedupe —
// none of which exist yet, and building it is its own multi-session project.
// This screen instead reuses the existing `GET /sightings/nearby` (point +
// radius, already merges eBird + iNaturalist with graceful degradation) —
// no migration, no new backend endpoint. Swap in the bbox-driven version
// later without changing how this screen is reached (same route, same
// props) once that infrastructure lands.
//
// There's no `default_region`/profile location yet (user-profiles.md is
// still "Planned"), so centering the map needs its own answer here: try the
// browser's geolocation on mount (silently — same as
// `Components/LocationPicker.js`'s fallback), and offer a manual place
// search and an explicit "Use my location" button for when that's denied or
// wrong. See docs/features/explore-map.md.
//
// `embedded: true` (set by `Presenters/Home.js`, which mounts this directly
// below its own header instead of sending you to a separate route) drops
// the "← Back to home" button (meaningless nested inside Home itself) and
// renders the section title as an `<h2>` instead of an `<h1>`, since Home
// already has its own page-level `<h1>`. Still reachable standalone at the
// `explore-map` route with the full `<h1>` + back button.

import { sightingsService } from '../Services/sightings.js';
import { geocodingService } from '../Services/geocoding.js';
import { lifeListService } from '../Services/lifeList.js';
import { speciesService } from '../Services/species.js';
import { mountSightingsMap } from '../Components/SightingsMap.js';
import { renderSightingDetail } from '../Components/SightingDetail.js';
import { escapeHtml } from '../Components/htmlUtils.js';

const DAYS_BACK_OPTIONS = [7, 14, 30];
// Each unit offers its own clean, native-feeling set of radii (standard
// mile-radius presets, not an awkward unit conversion of the km ones — that
// used to show 6/16/31/62 mi, converted from 10/25/50/100 km). Picking an
// option converts it to km (MI_TO_KM) before it's ever sent to the backend
// — `state.radiusKm` is always the canonical value in both the API call and
// everywhere else in this file (the search-area circle, trip-planning
// subtitle, etc.); only the dropdown's own options/labels vary by unit.
const RADIUS_OPTIONS_BY_UNIT = {
  km: [10, 25, 50, 100],
  mi: [5, 10, 25, 50],
};
// Switching units resets to the new unit's own default rather than
// converting/approximating the old radius — simpler and more predictable
// than picking "the closest native option" to whatever was selected before.
const RADIUS_DEFAULT_BY_UNIT = { km: 25, mi: 5 };
const KM_TO_MI = 0.621371;
const MI_TO_KM = 1 / KM_TO_MI;
const TOP_AREAS_SHOWN = 5;
const SEARCH_DEBOUNCE_MS = 350;
const MIN_SEARCH_LENGTH = 3; // matches geocodingService's own no-op threshold (Services/geocoding.js)
const SPECIES_SUGGESTIONS_SHOWN = 8;

export function mount(container, props = {}) {
  // onNavigate optional — omitted when this screen is previewed standalone.
  // `userId` defaults the same way AddObservation/LifeList/ObservationList
  // do — this screen isn't behind real auth yet either.
  const { onNavigate, embedded = false, userId = 'u1' } = props;

  const state = {
    lat: null,
    lng: null,
    placeLabel: null,
    locating: false, // explicit "Use my location" in flight
    daysBack: 7,
    radiusKm: 25,
    distanceUnit: 'km', // 'km' | 'mi' — see RADIUS_OPTIONS_BY_UNIT's comment
    source: 'all', // 'all' | 'ebird' | 'inat' | 'manual'
    sightings: [],
    loading: false,
    error: null,

    speciesQuery: '', // free-text species-name filter, client-side over `sightings` — not reset on location/filter changes, since "find this bird" is a persistent intent while panning around
    speciesFilterFocused: false, // gates the suggestions dropdown's visibility — suppressed once the input loses focus, not just once the query is cleared
    mineOnly: false, // narrows to the logged-in user's own sightings (user_id match) — distinct from source: 'manual', which is every OnlyBirds user's logged sightings, not just this one

    searchQuery: '',
    searchResults: [],
    searching: false,
    searchError: null,

    selectedSighting: null, // shown in the docked detail panel; null hides it
    enlargedPhotoUrl: null, // set while the click-to-enlarge lightbox is open

    // Backs the "trip planning" region-summary box — the user's full life
    // list (every species they've ever logged, not scoped to one region;
    // there's no lat/lng -> eBird-region-code mapping to narrow it further),
    // fetched once per mount. Starts empty rather than null so "new for
    // you" math never has to null-check — `seenSpeciesLoaded` gates whether
    // that figure is shown at all, so an empty-but-not-yet-loaded set can't
    // be misread as "nothing you've seen before."
    seenSpecies: new Set(),
    seenSpeciesLoaded: false,

    // Both collapsible so the map can have the whole screen when neither is
    // needed — e.g. the detail panel after you've already noted what you
    // came for, or the trip-planning box once you've already picked a spot.
    tripPlanningCollapsed: false,
    detailPanelCollapsed: false,
  };

  // The live Leaflet instance lives outside `state` and survives across
  // renders where possible — see `wireMap()`.
  let mapController = null;
  let mapGeneration = 0; // guards against a stale remount resolving after a newer one started
  let locationJustChanged = false; // true for the one render right after setLocation() — jump there instead of preserving pan/zoom
  let radiusJustChanged = false; // true for the one render right after a radius filter change — the search-area circle's size changed, so re-fit to it instead of preserving pan/zoom
  let searchDebounceTimer = null;
  let searchRequestId = 0;
  let stockPhotoCache = new Map(); // scientific_name -> photo_url, persists for this mount's lifetime
  let pendingPhotoKeys = new Set(); // scientific names currently being fetched — avoids duplicate overlapping requests

  render();
  attemptSilentGeolocation();
  loadSeenSpecies();

  // ---- Data ---------------------------------------------------------------

  // Non-critical to the rest of the screen — a failure here just means the
  // region-summary box omits the "new for you" figure, so it's swallowed
  // rather than surfaced as a page-level error.
  function loadSeenSpecies() {
    lifeListService.getSeenScientificNames(userId)
      .then((names) => {
        state.seenSpecies = names;
        state.seenSpeciesLoaded = true;
        updateRegionSummaryDom();
      })
      .catch(() => {});
  }

  function attemptSilentGeolocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setLocation(pos.coords.latitude, pos.coords.longitude, 'Your location'),
      () => {}, // denied or timed out — the default map view still works, search still works
      { timeout: 4000 },
    );
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      state.error = 'This browser can’t share your location — search for a place instead.';
      render();
      return;
    }
    state.locating = true;
    state.error = null;
    render();
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        state.locating = false;
        setLocation(pos.coords.latitude, pos.coords.longitude, 'Your location');
      },
      () => {
        state.locating = false;
        state.error = 'Could not get your location — search for a place instead.';
        render();
      },
      { timeout: 8000 },
    );
  }

  function setLocation(lat, lng, label) {
    state.lat = lat;
    state.lng = lng;
    state.placeLabel = label;
    state.searchResults = [];
    state.searchQuery = '';
    state.selectedSighting = null; // the old selection won't be on the map near this new area
    locationJustChanged = true;
    render();
    loadSightings();
  }

  async function loadSightings() {
    if (state.lat == null || state.lng == null) return;
    state.loading = true;
    state.error = null;
    render();
    try {
      state.sightings = await sightingsService.nearby({
        lat: state.lat,
        lng: state.lng,
        radiusKm: state.radiusKm,
        daysBack: state.daysBack,
        source: state.source,
      });
    } catch (err) {
      state.error = err.message || 'Could not load sightings for this area.';
      state.sightings = [];
    } finally {
      state.loading = false;
      render();
      // Only clear these once this load cycle's *last* render() has fired
      // (and so wireMap() has read them) — see wireMap()'s comment for why
      // they can't just be reset inside wireMap() itself.
      locationJustChanged = false;
      radiusJustChanged = false;
    }
  }

  // `state.sightings` narrowed by the species-name filter — matches common
  // *or* scientific name, case-insensitive substring. Purely client-side
  // over what's already been fetched for this location/radius/source/days,
  // same as Life List's own search bar.
  function filteredSightings() {
    const query = state.speciesQuery.trim().toLowerCase();
    return state.sightings.filter((s) => {
      if (state.mineOnly && s.user_id !== userId) return false;
      if (!query) return true;
      const common = s.species?.common_name?.toLowerCase() || '';
      const sci = s.species?.scientific_name?.toLowerCase() || '';
      return common.includes(query) || sci.includes(query);
    });
  }

  function isOwnSighting(sighting) {
    return sighting.user_id === userId;
  }

  // `get_stock_photo()` on the backend always returns *a* URL — a real
  // Commons photo, or a generated placehold.co image with the species name
  // printed on it as a last resort so Life List cards are never blank. That
  // text-on-a-card placeholder reads fine at Life List's size, but shrunk
  // to this dropdown's 32px circle the text is illegible and looks exactly
  // like a broken/not-yet-loaded image (a real "still not loading" report —
  // it had actually finished loading, it just wasn't a real photo). Treated
  // as equivalent to "no photo" here so it falls back to the plain icon
  // instead, which reads unambiguously at any size.
  function isGeneratedPlaceholder(url) {
    return url.startsWith('https://placehold.co/');
  }

  // Distinct species (by scientific name, falling back to common name)
  // among `state.sightings` matching the typed text — feeds the species
  // filter's autocomplete dropdown. Each entry carries a representative
  // photo: the first matching sighting's own photo if it has one, else a
  // guaranteed real-or-placeholder stock photo from `stockPhotoCache`
  // (filled in by loadMissingStockPhotos() below) if one's already been
  // fetched — most eBird sightings carry neither, so without this most
  // rows would otherwise show no photo at all. Purely client-side over
  // what's already fetched, same as filteredSightings() itself.
  function speciesSuggestions(query) {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return [];
    const matches = new Map();
    for (const s of state.sightings) {
      const common = s.species?.common_name || '';
      const sci = s.species?.scientific_name || '';
      if (!common.toLowerCase().includes(trimmed) && !sci.toLowerCase().includes(trimmed)) continue;
      const key = sci || common;
      if (!key || matches.has(key)) continue;
      const photoUrl = s.photo_url || (sci ? stockPhotoCache.get(sci) : null) || null;
      matches.set(key, { commonName: common || 'Unknown species', scientificName: sci, photoUrl });
    }
    return [...matches.values()].slice(0, SPECIES_SUGGESTIONS_SHOWN);
  }

  // Fetches a stock photo for whichever currently-shown suggestions don't
  // have one yet — lazy (only the handful actually visible right now, not
  // every species ever seen) and deduped against `pendingPhotoKeys` so fast
  // typing can't fire overlapping requests for the same species twice.
  // Results land in `stockPhotoCache`, which persists for the rest of this
  // mount, so narrowing/widening the query never re-fetches one already
  // resolved.
  async function loadMissingStockPhotos(suggestions) {
    const missing = suggestions.filter(
      (sp) => !sp.photoUrl && sp.scientificName && !pendingPhotoKeys.has(sp.scientificName),
    );
    if (missing.length === 0) return;
    missing.forEach((sp) => pendingPhotoKeys.add(sp.scientificName));
    try {
      const photos = await speciesService.getStockPhotos(
        missing.map((sp) => ({ scientificName: sp.scientificName, commonName: sp.commonName })),
      );
      photos.forEach((url, sci) => stockPhotoCache.set(sci, url));
    } catch (err) {
      // Non-critical — the dropdown just keeps showing the fallback icon
      // for these, nothing to surface as a page-level error over — but log
      // it so a real failure (vs. "nothing to fetch") is still visible
      // somewhere instead of silently vanishing.
      console.error('Could not load species photos:', err);
    } finally {
      missing.forEach((sp) => pendingPhotoKeys.delete(sp.scientificName));
      updateSpeciesSuggestionsDom();
    }
  }

  // Typing a species name only ever changes which of the already-fetched
  // pins are shown — no new fetch, so this skips render() entirely and just
  // tells the live map to swap its markers (SightingsMap#setSightings()
  // doesn't remount the map, just the pin layer) plus patches the status
  // line's count directly. Going through a full render() here would both
  // remount the whole Leaflet map on every keystroke and fight the input's
  // own focus, same reasoning as everywhere else this file avoids it.
  function applySpeciesFilter(query) {
    state.speciesQuery = query;
    mapController?.setSightings(filteredSightings());
    updateStatusLineDom();
    updateRegionSummaryDom();
    updateSpeciesSuggestionsDom();
  }

  // Picking a suggestion sets the input to that species' exact common name
  // and applies it as the filter — same path as typing it out by hand,
  // just faster. Closes the dropdown afterward (there's nothing left to
  // suggest once the query matches exactly one species anyway).
  function selectSpeciesSuggestion(suggestion) {
    const input = container.querySelector('#species-filter');
    if (input) input.value = suggestion.commonName;
    state.speciesFilterFocused = false;
    applySpeciesFilter(suggestion.commonName);
  }

  // Same "targeted update, skip render()" reasoning as applySpeciesFilter() —
  // a checkbox toggle shouldn't remount the whole Leaflet map either.
  function toggleMineOnly(checked) {
    state.mineOnly = checked;
    mapController?.setSightings(filteredSightings());
    updateStatusLineDom();
    updateRegionSummaryDom();
  }

  // Trip-planning numbers for whatever's currently filtered in (species
  // text, days-back, radius, source) — same `filteredSightings()` the map
  // and status line already use, so this box always agrees with what's
  // actually on screen.
  function regionSummary() {
    const sightings = filteredSightings();

    const speciesSeenHere = new Map(); // scientific/common name -> isNew
    for (const s of sightings) {
      const sci = s.species?.scientific_name;
      const key = sci || s.species?.common_name || 'unknown';
      if (speciesSeenHere.has(key)) continue;
      // Without a scientific name there's nothing reliable to match against
      // the life list, so it's counted toward diversity but never claimed
      // as "new" — understating that figure beats a false positive.
      speciesSeenHere.set(key, sci ? !state.seenSpecies.has(sci) : false);
    }
    const newSpeciesCount = [...speciesSeenHere.values()].filter(Boolean).length;

    // Tracks each named area's sighting count alongside the lat/lng extent
    // of its sightings, so clicking a "top spot" (see renderRegionSummaryBody())
    // can zoom the map to exactly that area, not just its name.
    const areaStats = new Map();
    for (const s of sightings) {
      const name = s.location_name?.trim();
      if (!name) continue;
      const entry = areaStats.get(name) || { count: 0, minLat: Infinity, maxLat: -Infinity, minLng: Infinity, maxLng: -Infinity };
      entry.count += 1;
      if (s.lat != null && s.lng != null) {
        entry.minLat = Math.min(entry.minLat, s.lat);
        entry.maxLat = Math.max(entry.maxLat, s.lat);
        entry.minLng = Math.min(entry.minLng, s.lng);
        entry.maxLng = Math.max(entry.maxLng, s.lng);
      }
      areaStats.set(name, entry);
    }
    const topAreas = [...areaStats.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, TOP_AREAS_SHOWN)
      .map(([name, stats]) => ({
        name,
        count: stats.count,
        bounds: stats.minLat <= stats.maxLat ? [[stats.minLat, stats.minLng], [stats.maxLat, stats.maxLng]] : null,
      }));

    return { speciesCount: speciesSeenHere.size, newSpeciesCount, topAreas };
  }

  // Clicking a "top spot" in the trip-planning list — zooms the map to that
  // area and draws a rectangle around it (SightingsMap#focusArea()) so the
  // user can see exactly which pins it covers, same filters still applied.
  function focusOnArea(bounds) {
    mapController?.focusArea(bounds);
  }

  function applyFilters({ daysBack, radiusKm, source } = {}) {
    if (daysBack !== undefined) state.daysBack = daysBack;
    if (radiusKm !== undefined && radiusKm !== state.radiusKm) {
      state.radiusKm = radiusKm;
      radiusJustChanged = true;
    }
    if (source !== undefined) state.source = source;
    state.selectedSighting = null; // the selected pin might not match the new filters
    render();
    loadSightings();
  }

  // Switching units resets the radius to the new unit's own default (see
  // RADIUS_DEFAULT_BY_UNIT) rather than trying to convert/approximate the
  // old selection — e.g. mi's default is a plain 5, not whatever odd number
  // 25km would convert to. A deliberate, infrequent action, so a full
  // render() (same as any other filter change) is fine — no need for
  // applySpeciesFilter()'s targeted-update dance.
  function setDistanceUnit(unit) {
    if (unit === state.distanceUnit) return;
    state.distanceUnit = unit;
    const newRadiusKm = nativeToKm(RADIUS_DEFAULT_BY_UNIT[unit], unit);
    if (newRadiusKm !== state.radiusKm) {
      state.radiusKm = newRadiusKm;
      radiusJustChanged = true; // re-fit the search-area circle to the new default radius
    }
    render();
    loadSightings();
  }

  function nativeToKm(value, unit) {
    return unit === 'mi' ? Math.round(value * MI_TO_KM) : value;
  }

  function formatDistance(km) {
    if (state.distanceUnit === 'mi') return `${Math.round(km * KM_TO_MI)} mi`;
    return `${km} km`;
  }

  // Selecting a pin only ever touches the detail panel — never the map
  // itself — so this deliberately bypasses render()/wireMap() (see that
  // function's comment) and patches the panel's DOM directly, the same
  // "targeted update" pattern used elsewhere in this codebase (e.g.
  // AddObservation's photo-upload status) to avoid disrupting something
  // live for an unrelated state change. A full render() here would remount
  // the whole Leaflet map (tiles and all) just from clicking a pin.
  function selectSighting(sighting) {
    state.selectedSighting = sighting;
    updateDetailPanelDom();
  }

  function clearSelection() {
    state.selectedSighting = null;
    updateDetailPanelDom();
  }

  function toggleDetailPanel() {
    state.detailPanelCollapsed = !state.detailPanelCollapsed;
    updateDetailPanelDom();
  }

  function toggleTripPlanning() {
    state.tripPlanningCollapsed = !state.tripPlanningCollapsed;
    updateRegionSummaryDom();
  }

  // Click-to-enlarge on the detail panel's photo — same "targeted update,
  // skip render()" reasoning as selectSighting() above. The Escape listener
  // is only attached while the lightbox is actually open (not for the
  // Presenter's whole lifetime) so it can't accumulate across remounts —
  // this app's navigation tears down and remounts a fresh Presenter on every
  // route change, so anything attached to `document` instead of a DOM node
  // that gets discarded needs its own explicit cleanup.
  function enlargePhoto(url) {
    state.enlargedPhotoUrl = url;
    document.addEventListener('keydown', handleLightboxKeydown);
    updateLightboxDom();
  }

  function closeLightbox() {
    state.enlargedPhotoUrl = null;
    document.removeEventListener('keydown', handleLightboxKeydown);
    updateLightboxDom();
  }

  function handleLightboxKeydown(e) {
    if (e.key === 'Escape') closeLightbox();
  }

  // Live suggestions as you type, instead of requiring an explicit
  // "Search" click/Enter — debounced so it doesn't fire a request per
  // keystroke, and guarded by `searchRequestId` so a slower, earlier
  // response can't clobber a newer one if they resolve out of order.
  // `geocodingService.search()` already no-ops under 3 characters, so this
  // doesn't bother debouncing/fetching for a query that's going to come
  // back empty anyway.
  function scheduleSearch(query) {
    state.searchQuery = query;
    clearTimeout(searchDebounceTimer);
    if (query.trim().length < MIN_SEARCH_LENGTH) {
      searchRequestId += 1; // invalidate any in-flight fetch's result
      state.searchResults = [];
      state.searchError = null;
      state.searching = false;
      updateSearchSuggestionsDom();
      return;
    }
    searchDebounceTimer = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS);
  }

  // Patches just the suggestions dropdown, not the whole search bar — a
  // full render() on every keystroke's resolved fetch would steal focus
  // out of the input mid-type, same "targeted update" reasoning as
  // applySpeciesFilter() elsewhere in this file.
  async function runSearch(query) {
    const trimmed = query.trim();
    if (!trimmed) return;
    const requestId = (searchRequestId += 1);
    state.searching = true;
    state.searchError = null;
    updateSearchSuggestionsDom();
    try {
      const results = await geocodingService.search(trimmed);
      if (requestId !== searchRequestId) return; // a newer search started since this one began
      state.searchResults = results;
      if (state.searchResults.length === 0) state.searchError = 'No matches — try a different search.';
    } catch (err) {
      if (requestId !== searchRequestId) return;
      state.searchError = 'Search failed. Try again in a moment.';
      state.searchResults = [];
    } finally {
      if (requestId === searchRequestId) {
        state.searching = false;
        updateSearchSuggestionsDom();
      }
    }
  }

  // ---- Render ---------------------------------------------------------------

  function render() {
    const headingTag = embedded ? 'h2' : 'h1';
    // Standalone (its own route), this screen provides its own side
    // padding — a literal 0.5in, same as `Home.js` — deliberately no
    // `ob-container`, since a map wants the full viewport width, not a
    // narrow centered column. Embedded inside Home, Home's own wrapper
    // already pads the whole page (including this sub-container), so
    // adding it again here would double it up.
    container.innerHTML = `
      <div class="ob-stack" style="${embedded ? '' : 'padding-inline: 0.5in;'}">
        ${!embedded && onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <${headingTag}>Explore map</${headingTag}>
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${renderSearchBar()}
        ${renderFilters()}
        <div class="ob-cluster" style="align-items: flex-start; flex-wrap: wrap; gap: var(--ob-space-4);">
          <div class="ob-stack" style="flex: 2 1 320px; min-width: 280px;">
            <div data-role="sightings-map" style="height: 480px; border-radius: var(--ob-radius-md); overflow: hidden;"></div>
            <div data-role="status-line">${renderStatusLine()}</div>
          </div>
          <div
            class="ob-card"
            data-role="detail-panel"
            style="flex: 1 1 340px; max-width: 460px; ${detailPanelExpandedStyle()} position: sticky; top: var(--ob-space-4);"
          >${renderDetailPanelContent()}</div>
        </div>
        <div data-role="region-summary">${renderRegionSummary()}</div>
        <p class="ob-hint">Map tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>. Sightings from eBird, iNaturalist, and OnlyBirds users.</p>
        <div data-role="lightbox">${renderLightboxContent()}</div>
      </div>
    `;
    if (!embedded && onNavigate) {
      container.querySelector('[data-action="back-to-home"]')?.addEventListener('click', () => onNavigate('home'));
    }
    wire();
    wireSearchSuggestions();
    wireSpeciesSuggestions();
    wireMap();
    wireDetailPanel();
    wireRegionSummary();
    wireLightbox();
  }

  // The panel's fixed height + scroll only make sense expanded — collapsed,
  // it should shrink to just its header, same as the trip-planning card.
  function detailPanelExpandedStyle() {
    return state.detailPanelCollapsed ? '' : 'height: 560px; overflow-y: auto;';
  }

  function renderSearchBar() {
    return `
      <div class="ob-field">
        <label class="ob-label ob-visually-hidden" for="place-search">Search for a place</label>
        <div class="ob-cluster">
          <input id="place-search" type="search" class="ob-input" style="flex:1" autocomplete="off" placeholder="Search for a place…" value="${escapeHtml(state.searchQuery)}" />
          <button type="button" class="ob-btn ob-btn--ghost" data-action="use-my-location" ${state.locating ? 'disabled' : ''}>${state.locating ? 'Locating…' : 'Use my location'}</button>
        </div>
        <div data-role="search-suggestions">${renderSearchSuggestions()}</div>
      </div>
    `;
  }

  // Suggestions dropdown only — split out from renderSearchBar() so typing
  // can patch just this subtree (updateSearchSuggestionsDom()) without
  // touching the `<input>` itself and losing cursor focus mid-word.
  function renderSearchSuggestions() {
    if (state.searching) {
      return '<p class="ob-text-muted ob-text-sm"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Searching…</p>';
    }
    if (state.searchError) {
      return `<p class="ob-text-muted ob-text-sm">${escapeHtml(state.searchError)}</p>`;
    }
    if (state.searchResults.length === 0) return '';
    return `
      <div class="ob-stack" style="--ob-stack-gap: var(--ob-space-1);" data-role="search-results">
        ${state.searchResults.map((r, i) => `
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" style="justify-content:flex-start;" data-search-result="${i}">${escapeHtml(r.display_name)}</button>
        `).join('')}
      </div>
    `;
  }

  function updateSearchSuggestionsDom() {
    const el = container.querySelector('[data-role="search-suggestions"]');
    if (el) el.innerHTML = renderSearchSuggestions();
    wireSearchSuggestions();
  }

  function wireSearchSuggestions() {
    container.querySelectorAll('[data-search-result]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const result = state.searchResults[Number(btn.dataset.searchResult)];
        if (result) setLocation(result.lat, result.lng, result.display_name);
      });
    });
  }

  // Image-left/name-right autocomplete rows, shown only while the input is
  // focused and has a non-empty query with matches — a stray render() while
  // typing elsewhere (e.g. the map's own loading state) shouldn't leave this
  // dropdown lingering open.
  function renderSpeciesSuggestions() {
    if (!state.speciesFilterFocused) return '';
    const suggestions = speciesSuggestions(state.speciesQuery);
    if (suggestions.length === 0) return '';
    return `
      <div
        data-role="species-suggestions-list"
        class="ob-card ob-card--flat"
        style="position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: var(--ob-z-modal); max-height: 280px; overflow-y: auto; padding: var(--ob-space-1); background: var(--ob-color-surface); box-shadow: var(--ob-shadow-md);"
      >
        ${suggestions.map((sp, i) => `
          <button
            type="button"
            class="ob-btn ob-btn--ghost"
            data-species-suggestion="${i}"
            style="width: 100%; justify-content: flex-start; gap: var(--ob-space-2); padding: var(--ob-space-1) var(--ob-space-2);"
          >
            ${sp.photoUrl && !isGeneratedPlaceholder(sp.photoUrl)
              ? `<img src="${escapeHtml(sp.photoUrl)}" alt="" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; flex-shrink: 0;" />`
              : `<span style="display: inline-block; width: 32px; height: 32px; border-radius: 50%; background: var(--ob-color-surface-alt); flex-shrink: 0;"></span>`}
            <span style="text-align: left;">
              <div class="ob-text-sm">${escapeHtml(sp.commonName)}</div>
              ${sp.scientificName ? `<div class="ob-text-muted" style="font-style: italic; font-size: 0.85em;">${escapeHtml(sp.scientificName)}</div>` : ''}
            </span>
          </button>
        `).join('')}
      </div>
    `;
  }

  function updateSpeciesSuggestionsDom() {
    const el = container.querySelector('[data-role="species-suggestions"]');
    if (el) el.innerHTML = renderSpeciesSuggestions();
    wireSpeciesSuggestions();
    if (state.speciesFilterFocused) loadMissingStockPhotos(speciesSuggestions(state.speciesQuery));
  }

  function wireSpeciesSuggestions() {
    container.querySelectorAll('[data-species-suggestion]').forEach((btn) => {
      // mousedown (not click) fires before the input's blur event, so the
      // suggestion is still in the DOM (not already hidden by blur) when
      // this runs — the usual autocomplete-dropdown ordering gotcha.
      btn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const suggestions = speciesSuggestions(state.speciesQuery);
        const suggestion = suggestions[Number(btn.dataset.speciesSuggestion)];
        if (suggestion) selectSpeciesSuggestion(suggestion);
      });
    });
  }

  function renderFilters() {
    return `
      <div class="ob-cluster" style="align-items:center; gap: var(--ob-space-3);">
        <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
          <label class="ob-label" for="species-filter">Bird</label>
          <div style="position: relative; width: 280px;">
            <input
              id="species-filter"
              type="search"
              class="ob-input"
              style="width: 100%;"
              autocomplete="off"
              placeholder="Filter by species…"
              value="${escapeHtml(state.speciesQuery)}"
              ${state.lat == null ? 'disabled' : ''}
            />
            <div data-role="species-suggestions">${renderSpeciesSuggestions()}</div>
          </div>
        </div>
        <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
          <label class="ob-label" for="days-back-filter">Since</label>
          <select id="days-back-filter" class="ob-select" style="width:auto;" ${state.lat == null ? 'disabled' : ''}>
            ${DAYS_BACK_OPTIONS.map((d) => `<option value="${d}" ${d === state.daysBack ? 'selected' : ''}>Last ${d} days</option>`).join('')}
          </select>
        </div>
        <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
          <label class="ob-label" for="distance-unit-filter">Radius</label>
          <select id="distance-unit-filter" class="ob-select" style="width:auto;" aria-label="Distance unit">
            <option value="km" ${state.distanceUnit === 'km' ? 'selected' : ''}>km</option>
            <option value="mi" ${state.distanceUnit === 'mi' ? 'selected' : ''}>mi</option>
          </select>
          <select id="radius-filter" class="ob-select" style="width:auto;" ${state.lat == null ? 'disabled' : ''}>
            ${RADIUS_OPTIONS_BY_UNIT[state.distanceUnit].map((v) => `<option value="${v}" ${nativeToKm(v, state.distanceUnit) === state.radiusKm ? 'selected' : ''}>${v} ${state.distanceUnit}</option>`).join('')}
          </select>
        </div>
        <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
          <label class="ob-label" for="source-filter">Source</label>
          <select id="source-filter" class="ob-select" style="width:auto;" ${state.lat == null ? 'disabled' : ''}>
            <option value="all" ${state.source === 'all' ? 'selected' : ''}>All sources</option>
            <option value="manual" ${state.source === 'manual' ? 'selected' : ''}>OnlyBirds only</option>
            <option value="ebird" ${state.source === 'ebird' ? 'selected' : ''}>eBird only</option>
            <option value="inat" ${state.source === 'inat' ? 'selected' : ''}>iNaturalist only</option>
          </select>
        </div>
        <label class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
          <input id="mine-only-filter" type="checkbox" ${state.mineOnly ? 'checked' : ''} ${state.lat == null ? 'disabled' : ''} />
          Only my sightings
        </label>
      </div>
    `;
  }

  // Helps someone planning a trip decide where to actually go: how much is
  // around right now (within the current filters), how many of those
  // species would be new for them, and which named locations are turning up
  // the most sightings. Hidden until a location is picked (nothing to
  // summarize yet) and while the initial fetch for that location is still
  // in flight (totals would be misleadingly low/zero otherwise).
  function renderRegionSummary() {
    if (state.lat == null) return '';
    const collapsed = state.tripPlanningCollapsed;
    return `
      <div class="ob-card">
        <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
          <div>
            <h3 class="ob-card__title" style="margin: 0;">Trip planning</h3>
            <p class="ob-text-muted ob-text-sm" style="margin: 2px 0 0;">Based on the last ${state.daysBack} days within ${formatDistance(state.radiusKm)} of ${escapeHtml(state.placeLabel || 'this area')}</p>
          </div>
          <button
            type="button"
            class="ob-btn ob-btn--ghost ob-btn--sm"
            data-action="toggle-trip-planning"
            aria-expanded="${collapsed ? 'false' : 'true'}"
          >${collapsed ? 'Show' : 'Hide'}</button>
        </div>
        ${collapsed ? '' : renderRegionSummaryBody()}
      </div>
    `;
  }

  function renderRegionSummaryBody() {
    if (state.loading) {
      return `<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-3) 0 0;"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Gathering area info…</p>`;
    }
    const { speciesCount, newSpeciesCount, topAreas } = regionSummary();
    return `
      <div class="ob-cluster" style="gap: var(--ob-space-3); margin-top: var(--ob-space-3);">
        <div class="ob-card ob-card--flat" style="flex: 1 1 140px; text-align: center; padding: var(--ob-space-3); background: var(--ob-color-info-bg);">
          <div style="font-size: 2rem; line-height: 1; font-weight: 700; color: var(--ob-color-info-text);">${speciesCount}</div>
          <div class="ob-text-sm" style="margin-top: var(--ob-space-1);">species spotted</div>
        </div>
        ${state.seenSpeciesLoaded ? `
          <div class="ob-card ob-card--flat" style="flex: 1 1 140px; text-align: center; padding: var(--ob-space-3); background: var(--ob-color-success-bg);">
            <div style="font-size: 2rem; line-height: 1; font-weight: 700; color: var(--ob-color-success-text);">${newSpeciesCount}</div>
            <div class="ob-text-sm" style="margin-top: var(--ob-space-1);">new for you</div>
          </div>
        ` : ''}
      </div>
      <div style="margin-top: var(--ob-space-4);">
        <p class="ob-text-sm" style="margin: 0 0 var(--ob-space-2); font-weight: 600;">Top spots to check out</p>
        ${topAreas.length > 0 ? `
          <ol class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); margin: 0; padding: 0; list-style: none;">
            ${topAreas.map((a, i) => {
              // Bounds are plain numbers (no quotes/special chars from
              // JSON.stringify-ing an array of numbers), safe to drop
              // straight into the attribute without escaping.
              const focusAttrs = a.bounds
                ? ` data-action="focus-area" data-bounds="${JSON.stringify(a.bounds)}" role="button" tabindex="0"`
                : '';
              return `
                <li
                  class="ob-cluster"
                  style="justify-content: space-between; align-items: center; padding: var(--ob-space-2) var(--ob-space-3); background: var(--ob-color-surface-alt); border-radius: var(--ob-radius-sm); ${a.bounds ? 'cursor: pointer;' : ''}"${focusAttrs}
                >
                  <span class="ob-text-sm"><strong>${i + 1}.</strong> ${escapeHtml(a.name)}</span>
                  <span class="ob-tag ob-tag--info">${a.count} sighting${a.count === 1 ? '' : 's'}</span>
                </li>
              `;
            }).join('')}
          </ol>
          ${topAreas.some((a) => a.bounds) ? '<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-2) 0 0;">Click a spot to zoom in and see its sightings outlined on the map.</p>' : ''}
        ` : `<p class="ob-text-muted ob-text-sm" style="margin: 0;">None of these sightings have a specific location name yet.</p>`}
      </div>
    `;
  }

  // Same "targeted update, skip render()" reasoning as updateStatusLineDom().
  function updateRegionSummaryDom() {
    const el = container.querySelector('[data-role="region-summary"]');
    if (el) el.innerHTML = renderRegionSummary();
    wireRegionSummary();
  }

  function wireRegionSummary() {
    const el = container.querySelector('[data-role="region-summary"]');
    el?.querySelector('[data-action="toggle-trip-planning"]')?.addEventListener('click', toggleTripPlanning);

    el?.querySelectorAll('[data-action="focus-area"]').forEach((li) => {
      const focus = () => {
        try {
          focusOnArea(JSON.parse(li.dataset.bounds));
        } catch {
          // Malformed/missing bounds — nothing to zoom to, just ignore the click.
        }
      };
      li.addEventListener('click', focus);
      li.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          focus();
        }
      });
    });
  }

  function renderDetailPanelContent() {
    const collapsed = state.detailPanelCollapsed;
    return `
      <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
        <h3 class="ob-card__title" style="margin: 0;">Sighting details</h3>
        <button
          type="button"
          class="ob-btn ob-btn--ghost ob-btn--sm"
          data-action="toggle-detail-panel"
          aria-expanded="${collapsed ? 'false' : 'true'}"
        >${collapsed ? 'Show' : 'Hide'}</button>
      </div>
      ${collapsed ? '' : renderDetailPanelBody()}
    `;
  }

  function renderDetailPanelBody() {
    if (!state.selectedSighting) {
      return '<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-2) 0 0;">Select a sighting on the map to see its details here.</p>';
    }
    return `
      <div style="margin-top: var(--ob-space-2);">
        ${renderSightingDetail(state.selectedSighting)}
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="close-detail" style="margin-top: var(--ob-space-3);">Close</button>
      </div>
    `;
  }

  // Clicking anywhere in the dark backdrop closes it; clicking the image
  // itself doesn't (that click bubbles to this same element, but only the
  // backdrop's own data-action is wired to actually close — see
  // wireLightbox()'s `e.target === e.currentTarget` guard).
  //
  // The image sits on a white card, not directly on the dark backdrop — a
  // dark-toned bird (a Black Vulture, a crow) photographed against a dark
  // background would otherwise be nearly invisible against the 85%-opacity
  // black overlay itself. If the photo genuinely fails to load (wired in
  // wireLightbox()'s `error` listener below), that's shown as text instead
  // of silently leaving the same empty-looking backdrop.
  function renderLightboxContent() {
    if (!state.enlargedPhotoUrl) return '';
    return `
      <div
        data-action="close-lightbox"
        style="position:fixed; inset:0; background:rgba(0,0,0,0.85); display:flex; align-items:center; justify-content:center; z-index:var(--ob-z-modal); padding: var(--ob-space-6); cursor:zoom-out;"
      >
        <div style="background:#fff; padding: var(--ob-space-2); border-radius: var(--ob-radius-md); max-width:90vw; max-height:90vh; cursor:default;">
          <img
            data-role="lightbox-img"
            src="${escapeHtml(state.enlargedPhotoUrl)}"
            alt=""
            style="display:block; max-width:100%; max-height:calc(90vh - var(--ob-space-2) * 2); object-fit:contain; border-radius: calc(var(--ob-radius-md) - 2px);"
          />
          <p data-role="lightbox-error" class="ob-text-sm ob-text-muted" style="display:none; margin: var(--ob-space-2) 0 0; max-width:280px;">This photo couldn’t be loaded.</p>
        </div>
        <button
          type="button"
          class="ob-btn ob-btn--ghost ob-btn--sm"
          data-action="close-lightbox"
          style="position:fixed; top: var(--ob-space-5); right: var(--ob-space-5);"
        >Close</button>
      </div>
    `;
  }

  function renderStatusLine() {
    if (state.lat == null) {
      return '<p class="ob-text-muted ob-text-sm">Search for a place above, or allow location access, to see recent sightings nearby.</p>';
    }
    if (state.loading) {
      return `<p class="ob-text-muted ob-text-sm"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Loading sightings near ${escapeHtml(state.placeLabel || 'this area')}…</p>`;
    }
    const matches = filteredSightings();
    const filterNote = state.speciesQuery.trim() ? ` matching “${escapeHtml(state.speciesQuery.trim())}”` : '';
    const mineCount = matches.filter(isOwnSighting).length;
    return `
      <p class="ob-text-muted ob-text-sm">${matches.length} sighting${matches.length === 1 ? '' : 's'}${filterNote} near ${escapeHtml(state.placeLabel || 'this area')} in the last ${state.daysBack} days.</p>
      <p class="ob-text-muted ob-text-sm" style="margin-top: var(--ob-space-1);"><span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:var(--ob-color-success-text); margin-right: var(--ob-space-1); vertical-align:middle;"></span>${mineCount} ${mineCount === 1 ? 'is' : 'are'} yours.</p>
      <p class="ob-text-muted ob-text-sm" style="margin-top: var(--ob-space-1);"><span style="display:inline-block; width:14px; height:0; border-top: 2px dashed #3aa0ff; margin-right: var(--ob-space-1); vertical-align:middle;"></span>Dashed circle = your ${formatDistance(state.radiusKm)} search area.</p>
    `;
  }

  // Same "targeted update, skip render()" reasoning as applySpeciesFilter().
  function updateStatusLineDom() {
    const el = container.querySelector('[data-role="status-line"]');
    if (el) el.innerHTML = renderStatusLine();
  }

  // ---- Wiring -------------------------------------------------------------

  function wire() {
    // Live-as-you-type — applySpeciesFilter() deliberately never calls
    // render(), so there's no focus to lose here; this listener only ever
    // gets (re)attached on an actual full render (radius/days/source
    // changes, initial load), not on every keystroke. Same reasoning as the
    // place-search input below.
    const speciesInput = container.querySelector('#species-filter');
    speciesInput?.addEventListener('input', () => applySpeciesFilter(speciesInput.value));
    speciesInput?.addEventListener('focus', () => {
      state.speciesFilterFocused = true;
      updateSpeciesSuggestionsDom();
    });
    speciesInput?.addEventListener('blur', () => {
      state.speciesFilterFocused = false;
      updateSpeciesSuggestionsDom();
    });
    speciesInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') speciesInput.blur(); // triggers the blur listener above, closing the dropdown
    });

    // Live suggestions as you type (debounced — see scheduleSearch());
    // Enter bypasses the debounce and searches immediately, for anyone who
    // types fast and doesn't want to wait it out.
    const searchInput = container.querySelector('#place-search');
    searchInput?.addEventListener('input', () => scheduleSearch(searchInput.value));
    searchInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(searchDebounceTimer);
        runSearch(searchInput.value);
      }
    });

    container.querySelector('[data-action="use-my-location"]')?.addEventListener('click', useMyLocation);

    const daysBackSelect = container.querySelector('#days-back-filter');
    daysBackSelect?.addEventListener('change', () => applyFilters({ daysBack: Number(daysBackSelect.value) }));

    const radiusSelect = container.querySelector('#radius-filter');
    radiusSelect?.addEventListener('change', () => applyFilters({ radiusKm: nativeToKm(Number(radiusSelect.value), state.distanceUnit) }));

    const distanceUnitSelect = container.querySelector('#distance-unit-filter');
    distanceUnitSelect?.addEventListener('change', () => setDistanceUnit(distanceUnitSelect.value));

    const sourceSelect = container.querySelector('#source-filter');
    sourceSelect?.addEventListener('change', () => applyFilters({ source: sourceSelect.value }));

    const mineOnlyCheckbox = container.querySelector('#mine-only-filter');
    mineOnlyCheckbox?.addEventListener('change', () => toggleMineOnly(mineOnlyCheckbox.checked));
  }

  // The map is a live widget, not markup rebuilt from `state` — every
  // render() above fully replaces the DOM (including the map's own
  // container div), so the Leaflet instance has to remount each time. To
  // avoid snapping back to the searched location on every filter change,
  // this preserves whatever the user last panned/zoomed to (falling back to
  // `state.lat`/`lng` only when there's no prior view, e.g. the very first
  // mount, right after picking a new search result, or right after a radius
  // change — both of those re-fit to the search-area circle instead, since
  // the old pan/zoom would otherwise show the wrong boundary).
  //
  // `locationJustChanged`/`radiusJustChanged` are deliberately NOT reset
  // here, even though they're read here — setLocation()/applyFilters()/
  // setDistanceUnit() each call render() once (triggering this) and then
  // loadSightings() (which calls render() at least once more itself, for
  // its own loading spinner). Each of those is a *separate* remount, racing
  // on `mapGeneration` — only the last one actually survives on screen (an
  // earlier one notices it's stale once its mount promise resolves and
  // self-destructs). Clearing the flag in here, on the first of those
  // calls, meant the surviving *last* remount never saw it and silently
  // fell back to the plain fixed zoom — a real "I changed the radius and
  // the map didn't zoom at all" report. loadSightings()'s `finally` block
  // clears both flags instead, once its own last render() has already run.
  function wireMap() {
    const mapEl = container.querySelector('[data-role="sightings-map"]');
    if (!mapEl) return;

    const generation = ++mapGeneration;
    const jumpToSearchArea = locationJustChanged || radiusJustChanged;
    const priorView = jumpToSearchArea ? null : mapController?.getView?.();
    mapController?.destroy();
    mapController = null;

    const initialLatLng = priorView
      ? [priorView.lat, priorView.lng]
      : state.lat != null
        ? [state.lat, state.lng]
        : undefined;
    const searchArea = state.lat != null ? { lat: state.lat, lng: state.lng, radiusKm: state.radiusKm } : null;

    mountSightingsMap(mapEl, {
      initialLatLng,
      onSelectSighting: selectSighting,
      isOwnSighting,
      searchArea,
      fitSearchArea: jumpToSearchArea,
    })
      .then((controller) => {
        if (generation !== mapGeneration) {
          controller.destroy(); // a newer render already started remounting — this one lost the race
          return;
        }
        mapController = controller;
        if (priorView) controller.setView(priorView.lat, priorView.lng, priorView.zoom);
        controller.setSightings(filteredSightings());
      })
      .catch((err) => {
        mapEl.innerHTML = `<div class="ob-alert ob-alert--warning">${escapeHtml(err.message || 'Could not load the map.')}</div>`;
      });
  }

  // Patches the detail panel's content directly — see
  // selectSighting()/clearSelection() above for why this skips render(). The
  // panel itself is always visible (a fixed-size docked rail next to the
  // map, reserved whether or not anything's selected, so clicking a pin
  // doesn't shift the map's width around) — only its content changes here.
  function updateDetailPanelDom() {
    const panel = container.querySelector('[data-role="detail-panel"]');
    if (!panel) return;
    // Collapsed/expanded toggles the panel's own fixed height + scroll, not
    // just its content — see detailPanelExpandedStyle() in render().
    panel.style.height = state.detailPanelCollapsed ? '' : '560px';
    panel.style.overflowY = state.detailPanelCollapsed ? '' : 'auto';
    panel.innerHTML = renderDetailPanelContent();
    wireDetailPanel(panel);
  }

  function wireDetailPanel(panel) {
    const el = panel || container.querySelector('[data-role="detail-panel"]');
    el?.querySelector('[data-action="toggle-detail-panel"]')?.addEventListener('click', toggleDetailPanel);
    el?.querySelector('[data-action="close-detail"]')?.addEventListener('click', clearSelection);

    const photoEl = el?.querySelector('[data-action="enlarge-photo"]');
    if (photoEl) {
      const open = () => enlargePhoto(photoEl.dataset.photoUrl);
      photoEl.addEventListener('click', open);
      photoEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    }
  }

  // Same "targeted update, skip render()" reasoning as updateDetailPanelDom().
  function updateLightboxDom() {
    const el = container.querySelector('[data-role="lightbox"]');
    if (!el) return;
    el.innerHTML = renderLightboxContent();
    wireLightbox(el);
  }

  function wireLightbox(el) {
    const root = el || container.querySelector('[data-role="lightbox"]');
    root?.querySelectorAll('[data-action="close-lightbox"]').forEach((closeEl) => {
      closeEl.addEventListener('click', (e) => {
        // The backdrop itself and the image both live under this listener
        // (event bubbling) — only close for a click on the backdrop/button
        // directly, not one that bubbled up from clicking the image.
        if (e.target === e.currentTarget) closeLightbox();
      });
    });

    const img = root?.querySelector('[data-role="lightbox-img"]');
    img?.addEventListener('error', () => {
      img.style.display = 'none';
      const errorEl = root.querySelector('[data-role="lightbox-error"]');
      if (errorEl) errorEl.style.display = 'block';
    });
  }
}
