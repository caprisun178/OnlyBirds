// Presenters/PlanATrip.js — standalone trip-planning screen.
//
//   import { mount } from './Presenters/PlanATrip.js';
//   mount(document.getElementById('app'), { userId: 'u1' });
//
// Deliberately its own screen, not folded into Explore Map's Trip Planning
// box — this answers "I'm going somewhere on specific dates, what should I
// expect and where should I go," a different question from Explore Map's
// "what's around here right now." See docs/features/plan-a-trip.md for the
// full scope and why it's separate.
//
// No live map here (unlike Explore Map/Add Observation), so this screen
// doesn't need any of their "preserve the Leaflet instance across renders"
// machinery — a plain full render() on every state change is fine, except
// for the destination search input, which needs the same targeted-update
// treatment Explore Map's place search uses so typing doesn't lose focus
// mid-word while a debounced fetch resolves.

import { geocodingService } from '../Services/geocoding.js';
import { tripService } from '../Services/trip.js';
import { mountSightingsMap } from '../Components/SightingsMap.js';
import { renderSightingDetail } from '../Components/SightingDetail.js';
import { escapeHtml } from '../Components/htmlUtils.js';

const SEARCH_DEBOUNCE_MS = 350;
const MIN_SEARCH_LENGTH = 3; // matches geocodingService's own no-op threshold
// Same km/mi pattern as Explore Map's radius filter — each unit gets its own
// native-feeling presets rather than a converted version of the other
// unit's. `nativeToKm()` converts to the canonical km value before it's ever
// sent to the backend; only the dropdown's own options/labels vary by unit.
const RADIUS_OPTIONS_BY_UNIT = {
  km: [10, 25, 50, 100],
  mi: [5, 10, 25, 50],
};
const RADIUS_DEFAULT_BY_UNIT = { km: 25, mi: 5 };
const MI_TO_KM = 1.60934;
// Matches the backend's default `radius_km` for `/trip/hotspot-sightings`
// (app/services/trip.py's `_HOTSPOT_SIGHTINGS_RADIUS_KM`) — kept in sync
// manually since it's also used here to draw the drill-down map's search
// circle and fit its initial zoom tightly to it (see wireHotspotMap()).
// Passed explicitly in the request too, rather than relying on the
// backend's own default, so the two can never silently drift apart.
const HOTSPOT_SIGHTINGS_RADIUS_KM = 2;

export function mount(container, props = {}) {
  const { onNavigate, userId = 'u1' } = props;

  const state = {
    destinationQuery: '',
    destinationResults: [],
    destinationSearching: false,
    destinationError: null,
    destinationFocused: false,
    destination: null, // { lat, lng, label } once a suggestion is picked

    distanceUnit: 'km', // 'km' | 'mi' — see RADIUS_OPTIONS_BY_UNIT's comment
    startDate: '',
    endDate: '',

    loading: false,
    error: null,
    plan: null, // { hotspots, likely_species } once fetched

    selectedHotspot: null, // the Hotspot a user tapped, or null — drives the drill-down map below the list
    hotspotSightings: [],
    hotspotSightingsLoading: false,
    hotspotSightingsError: null,
    selectedHotspotSighting: null, // a pin clicked on the drill-down map, shown in a small detail card

    enlargedPhotoUrl: null, // set while the click-to-enlarge lightbox is open — same pattern as ExploreMap.js
  };

  let searchDebounceTimer = null;
  let searchRequestId = 0;
  let mapController = null;
  let mapGeneration = 0; // guards against an in-flight mount resolving after a newer render already started remounting

  render();

  // ---- Destination search (debounced, targeted update) --------------------

  function scheduleDestinationSearch(query) {
    state.destinationQuery = query;
    state.destination = null; // typing again means the old pick no longer applies
    clearTimeout(searchDebounceTimer);
    if (query.trim().length < MIN_SEARCH_LENGTH) {
      searchRequestId += 1; // invalidate any in-flight fetch's result
      state.destinationResults = [];
      state.destinationError = null;
      state.destinationSearching = false;
      updateDestinationSuggestionsDom();
      return;
    }
    searchDebounceTimer = setTimeout(() => runDestinationSearch(query), SEARCH_DEBOUNCE_MS);
  }

  async function runDestinationSearch(query) {
    const trimmed = query.trim();
    if (!trimmed) return;
    const requestId = (searchRequestId += 1);
    state.destinationSearching = true;
    state.destinationError = null;
    updateDestinationSuggestionsDom();
    try {
      const results = await geocodingService.search(trimmed);
      if (requestId !== searchRequestId) return; // a newer search started since this one began
      state.destinationResults = results;
      if (results.length === 0) state.destinationError = 'No matches — try a different search.';
    } catch (err) {
      if (requestId !== searchRequestId) return;
      state.destinationError = 'Search failed. Try again in a moment.';
      state.destinationResults = [];
    } finally {
      if (requestId === searchRequestId) {
        state.destinationSearching = false;
        updateDestinationSuggestionsDom();
      }
    }
  }

  // Picking a suggestion is a click, not a keystroke — no focus to lose, so
  // a full render() (to update the submit button's disabled state, show the
  // picked label, etc.) is simplest here, unlike the live-typing path above.
  function selectDestination(result) {
    state.destination = { lat: result.lat, lng: result.lng, label: result.display_name };
    state.destinationQuery = result.display_name;
    state.destinationResults = [];
    state.plan = null; // a new destination invalidates whatever was planned for the old one
    render();
  }

  // ---- Planning -------------------------------------------------------------

  function nativeToKm(value, unit) {
    return unit === 'mi' ? Math.round(value * MI_TO_KM) : value;
  }

  function setDistanceUnit(unit) {
    if (unit === state.distanceUnit) return;
    state.distanceUnit = unit;
    render();
  }

  async function planTrip() {
    const radiusNative = Number(
      container.querySelector('#trip-radius')?.value || RADIUS_DEFAULT_BY_UNIT[state.distanceUnit]
    );
    const radiusKm = nativeToKm(radiusNative, state.distanceUnit);

    if (!state.destination) {
      state.error = 'Pick a destination from the suggestions first.';
      render();
      return;
    }

    state.loading = true;
    state.error = null;
    state.plan = null;
    closeHotspotMap({ skipRender: true }); // a new plan invalidates whatever hotspot was being drilled into
    render();
    try {
      state.plan = await tripService.plan({
        lat: state.destination.lat,
        lng: state.destination.lng,
        radiusKm,
        startDate: state.startDate,
        endDate: state.endDate,
        userId,
      });
    } catch (err) {
      state.error = err.message || 'Could not plan this trip. Try again in a moment.';
    } finally {
      state.loading = false;
      render();
    }
  }

  // ---- Hotspot drill-down map ------------------------------------------------

  async function selectHotspot(hotspot) {
    state.selectedHotspot = hotspot;
    state.hotspotSightings = [];
    state.hotspotSightingsError = null;
    state.hotspotSightingsLoading = true;
    state.selectedHotspotSighting = null;
    render();
    try {
      state.hotspotSightings = await tripService.hotspotSightings({
        lat: hotspot.lat,
        lng: hotspot.lng,
        radiusKm: HOTSPOT_SIGHTINGS_RADIUS_KM,
        startDate: state.startDate,
        endDate: state.endDate,
        locId: hotspot.loc_id,
      });
    } catch (err) {
      state.hotspotSightingsError = err.message || 'Could not load sightings for this hotspot.';
    } finally {
      state.hotspotSightingsLoading = false;
      render();
    }
  }

  function closeHotspotMap({ skipRender = false } = {}) {
    mapController?.destroy();
    mapController = null;
    state.selectedHotspot = null;
    state.hotspotSightings = [];
    state.hotspotSightingsError = null;
    state.selectedHotspotSighting = null;
    if (state.enlargedPhotoUrl) {
      state.enlargedPhotoUrl = null;
      document.removeEventListener('keydown', handleLightboxKeydown);
    }
    if (!skipRender) render();
  }

  function selectHotspotSighting(sighting) {
    state.selectedHotspotSighting = sighting;
    const panel = container.querySelector('[data-role="hotspot-sighting-detail"]');
    if (panel) {
      panel.innerHTML = renderSightingDetail(sighting);
      wireSightingDetailPhoto(panel);
    }
  }

  // Click-to-enlarge on the sighting-detail photo — the full-size image
  // doesn't fit at the detail card's fixed 240px-tall thumbnail crop, so
  // this opens it full-screen instead. Same lightbox pattern as
  // ExploreMap.js (its docstrings there cover the reasoning in full); kept
  // self-contained here rather than extracted into a shared component since
  // it's a handful of lines wired to this screen's own state either way.
  function wireSightingDetailPhoto(panel) {
    const photoEl = panel?.querySelector('[data-action="enlarge-photo"]');
    if (!photoEl) return;
    const open = () => enlargePhoto(photoEl.dataset.photoUrl);
    photoEl.addEventListener('click', open);
    photoEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
      }
    });
  }

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

  function wireHotspotMap() {
    const mapEl = container.querySelector('[data-role="hotspot-map"]');
    mapController?.destroy();
    mapController = null;
    if (!mapEl || !state.selectedHotspot) return;

    const generation = ++mapGeneration;
    const { lat, lng } = state.selectedHotspot;
    // Plain `initialLatLng` alone falls back to SightingsMap's generic
    // LOCATED_ZOOM (10) — built for "somewhere in this city," not a single
    // named hotspot, so it opened zoomed miles out with the pin barely
    // visible (reported live: a hotspot map that looked like a regional
    // overview). `searchArea` + `fitSearchArea` reuses the same "cover the
    // frame" zoom math ExploreMap's search-radius circle already relies on,
    // fit to this hotspot's actual (tight, 2km) search radius instead.
    mountSightingsMap(mapEl, {
      initialLatLng: [lat, lng],
      onSelectSighting: selectHotspotSighting,
      searchArea: { lat, lng, radiusKm: HOTSPOT_SIGHTINGS_RADIUS_KM },
      fitSearchArea: true,
    })
      .then((controller) => {
        if (generation !== mapGeneration) {
          controller.destroy(); // a newer render already started remounting — this one lost the race
          return;
        }
        mapController = controller;
        controller.setSightings(state.hotspotSightings);
      })
      .catch((err) => {
        mapEl.innerHTML = `<div class="ob-alert ob-alert--warning">${escapeHtml(err.message || 'Could not load the map.')}</div>`;
      });
  }

  // ---- Render ---------------------------------------------------------------

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Plan a trip</h1>
        <p class="ob-text-muted">Pick a destination and your travel dates — we'll suggest real eBird birding hotspots nearby, and which species to expect based on what was seen there around these same dates last year.</p>

        <div class="ob-card ob-stack">
          <div class="ob-field" style="position: relative;">
            <label class="ob-label" for="trip-destination">Destination</label>
            <input
              id="trip-destination"
              type="search"
              class="ob-input"
              autocomplete="off"
              placeholder="City, park, or address…"
              value="${escapeHtml(state.destinationQuery)}"
            />
            <div data-role="destination-suggestions">${renderDestinationSuggestions()}</div>
          </div>
          ${state.destination ? `<p class="ob-text-sm">Planning around <strong>${escapeHtml(state.destination.label)}</strong></p>` : ''}

          <div class="ob-cluster" style="align-items: flex-end;">
            <div class="ob-field">
              <label class="ob-label" for="trip-start-date">Start date</label>
              <input id="trip-start-date" type="date" class="ob-input" value="${escapeHtml(state.startDate)}" />
            </div>
            <div class="ob-field">
              <label class="ob-label" for="trip-end-date">End date</label>
              <input id="trip-end-date" type="date" class="ob-input" value="${escapeHtml(state.endDate)}" />
            </div>
            <div class="ob-field">
              <label class="ob-label" for="trip-radius">Radius</label>
              <div class="ob-cluster" style="--ob-cluster-gap: var(--ob-space-1);">
                <select id="trip-radius" class="ob-select">
                  ${RADIUS_OPTIONS_BY_UNIT[state.distanceUnit].map((r) => `<option value="${r}" ${r === RADIUS_DEFAULT_BY_UNIT[state.distanceUnit] ? 'selected' : ''}>${r} ${state.distanceUnit}</option>`).join('')}
                </select>
                <select id="trip-distance-unit" class="ob-select">
                  <option value="km" ${state.distanceUnit === 'km' ? 'selected' : ''}>km</option>
                  <option value="mi" ${state.distanceUnit === 'mi' ? 'selected' : ''}>mi</option>
                </select>
              </div>
            </div>
            <button type="button" class="ob-btn ob-btn--primary" data-action="plan-trip" ${state.loading ? 'disabled' : ''}>
              ${state.loading ? 'Planning…' : 'Plan my trip'}
            </button>
          </div>
        </div>

        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? '<p class="ob-text-muted ob-text-sm"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Gathering hotspots and likely species…</p>' : ''}
        ${state.plan ? renderResults() : ''}
      </div>
      <div data-role="lightbox">${renderLightboxContent()}</div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]')?.addEventListener('click', () => onNavigate('home'));
    }
    wire();
  }

  function renderDestinationSuggestions() {
    if (!state.destinationFocused) return '';
    if (state.destinationSearching) {
      return '<div class="ob-card ob-card--flat" style="position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: var(--ob-z-modal); padding: var(--ob-space-2); background: var(--ob-color-surface); box-shadow: var(--ob-shadow-md);"><p class="ob-text-muted ob-text-sm" style="margin:0;"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Searching…</p></div>';
    }
    if (state.destinationError) {
      return `<div class="ob-card ob-card--flat" style="position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: var(--ob-z-modal); padding: var(--ob-space-2); background: var(--ob-color-surface); box-shadow: var(--ob-shadow-md);"><p class="ob-text-muted ob-text-sm" style="margin:0;">${escapeHtml(state.destinationError)}</p></div>`;
    }
    if (state.destinationResults.length === 0) return '';
    return `
      <div
        class="ob-card ob-card--flat"
        style="position: absolute; top: 100%; left: 0; right: 0; margin-top: 4px; z-index: var(--ob-z-modal); max-height: 280px; overflow-y: auto; padding: var(--ob-space-1); background: var(--ob-color-surface); box-shadow: var(--ob-shadow-md);"
      >
        ${state.destinationResults.map((r, i) => `
          <button
            type="button"
            class="ob-btn ob-btn--ghost ob-btn--sm"
            data-destination-result="${i}"
            style="width: 100%; justify-content: flex-start; text-align: left;"
          >${escapeHtml(r.display_name)}</button>
        `).join('')}
      </div>
    `;
  }

  function updateDestinationSuggestionsDom() {
    const el = container.querySelector('[data-role="destination-suggestions"]');
    if (el) el.innerHTML = renderDestinationSuggestions();
    wireDestinationSuggestions();
  }

  function renderResults() {
    const { hotspots, likely_species: likelySpecies } = state.plan;
    return `
      <div class="ob-stack">
        <section class="ob-card">
          <h2 class="ob-card__title">Suggested hotspots</h2>
          ${hotspots.length === 0
            ? '<p class="ob-text-muted ob-text-sm">No eBird hotspots found nearby — try a wider radius.</p>'
            : `
              <p class="ob-text-muted ob-text-sm" style="margin: 0 0 var(--ob-space-2);">Tap a hotspot to see sightings there around these same dates last year.</p>
              <ol class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); margin: 0; padding: 0; list-style: none;">
                ${hotspots.slice(0, 10).map((h, i) => `
                  <li
                    class="ob-cluster"
                    data-hotspot-index="${i}"
                    role="button"
                    tabindex="0"
                    style="justify-content: space-between; align-items: center; padding: var(--ob-space-2) var(--ob-space-3); background: ${state.selectedHotspot?.loc_id === h.loc_id ? 'var(--ob-color-info-bg)' : 'var(--ob-color-surface-alt)'}; border-radius: var(--ob-radius-sm); cursor: pointer;"
                  >
                    <span class="ob-text-sm">
                      <strong>${i + 1}.</strong>
                      <a href="https://ebird.org/hotspot/${escapeHtml(h.loc_id)}" target="_blank" rel="noopener" data-stop-row-click>${escapeHtml(h.name)}</a>
                    </span>
                    <span class="ob-tag ob-tag--info">${h.species_all_time} species all-time</span>
                  </li>
                `).join('')}
              </ol>
            `}
          ${state.selectedHotspot ? renderHotspotDrillDown() : ''}
        </section>

        <section class="ob-card">
          <h2 class="ob-card__title">Birds you're likely to see</h2>
          <p class="ob-text-muted ob-text-sm">Based on iNaturalist sightings here around these same dates last year — one year of comparison, not a long-term average.</p>
          ${likelySpecies.length === 0
            ? '<p class="ob-text-muted ob-text-sm">No research-grade iNaturalist sightings found for this area and time of year.</p>'
            : `
              <div class="ob-grid" style="--ob-grid-min: 200px;">
                ${likelySpecies.map((sp) => `
                  <div class="ob-card ob-card--flat">
                    ${sp.photo_url
                      ? `<img src="${escapeHtml(sp.photo_url)}" alt="" style="width: 100%; height: 120px; object-fit: cover; border-radius: var(--ob-radius-sm); margin-bottom: var(--ob-space-2);" />`
                      : ''}
                    <div class="ob-card__title" style="font-size: 1rem;">${escapeHtml(sp.species?.common_name || 'Unknown species')}</div>
                    ${sp.species?.scientific_name ? `<p class="ob-text-sm" style="font-style: italic; margin: 0;">${escapeHtml(sp.species.scientific_name)}</p>` : ''}
                    <p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-1) 0 0;">${sp.observation_count} sighting${sp.observation_count === 1 ? '' : 's'} last year</p>
                    ${sp.new_for_you ? '<span class="ob-tag ob-tag--success" style="margin-top: var(--ob-space-1); display: inline-block;">New for you</span>' : ''}
                  </div>
                `).join('')}
              </div>
            `}
        </section>
      </div>
    `;
  }

  function renderHotspotDrillDown() {
    const hotspot = state.selectedHotspot;
    return `
      <div class="ob-card ob-card--flat" style="margin-top: var(--ob-space-3);">
        <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
          <h3 class="ob-card__title" style="margin: 0; font-size: 1rem;">Last year at ${escapeHtml(hotspot.name)}</h3>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="close-hotspot-map">Close</button>
        </div>
        ${state.hotspotSightingsError ? `<div class="ob-alert ob-alert--danger" style="margin-top: var(--ob-space-2);">${escapeHtml(state.hotspotSightingsError)}</div>` : ''}
        ${state.hotspotSightingsLoading
          ? '<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-2) 0 0;"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Loading last year’s sightings — checking eBird checklists day by day, this can take up to 30 seconds…</p>'
          : !state.hotspotSightingsError && state.hotspotSightings.length === 0
            ? '<p class="ob-text-muted ob-text-sm" style="margin: var(--ob-space-2) 0 0;">No eBird or iNaturalist sightings found here around these dates last year.</p>'
            : ''}
        <div data-role="hotspot-map" style="height: 320px; border-radius: var(--ob-radius-sm); overflow: hidden; margin-top: var(--ob-space-2);"></div>
        <div data-role="hotspot-sighting-detail" style="margin-top: var(--ob-space-2);">
          ${state.selectedHotspotSighting ? renderSightingDetail(state.selectedHotspotSighting) : ''}
        </div>
      </div>
    `;
  }

  // ---- Wiring -------------------------------------------------------------

  function wire() {
    const destinationInput = container.querySelector('#trip-destination');
    destinationInput?.addEventListener('input', () => scheduleDestinationSearch(destinationInput.value));
    destinationInput?.addEventListener('focus', () => {
      state.destinationFocused = true;
      updateDestinationSuggestionsDom();
    });
    destinationInput?.addEventListener('blur', () => {
      state.destinationFocused = false;
      updateDestinationSuggestionsDom();
    });
    destinationInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') destinationInput.blur();
    });

    wireDestinationSuggestions();

    const distanceUnitSelect = container.querySelector('#trip-distance-unit');
    distanceUnitSelect?.addEventListener('change', () => setDistanceUnit(distanceUnitSelect.value));

    const startDateInput = container.querySelector('#trip-start-date');
    const endDateInput = container.querySelector('#trip-end-date');
    startDateInput?.addEventListener('change', () => { state.startDate = startDateInput.value; });
    endDateInput?.addEventListener('change', () => { state.endDate = endDateInput.value; });

    container.querySelector('[data-action="plan-trip"]')?.addEventListener('click', planTrip);

    container.querySelectorAll('[data-hotspot-index]').forEach((row) => {
      const activate = (e) => {
        if (e.target.closest('[data-stop-row-click]')) return; // let the eBird link navigate on its own
        const hotspot = state.plan?.hotspots[Number(row.dataset.hotspotIndex)];
        if (hotspot) selectHotspot(hotspot);
      };
      row.addEventListener('click', activate);
      row.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          activate(e);
        }
      });
    });
    container.querySelector('[data-action="close-hotspot-map"]')?.addEventListener('click', () => closeHotspotMap());

    wireSightingDetailPhoto(container.querySelector('[data-role="hotspot-sighting-detail"]'));
    wireLightbox(container.querySelector('[data-role="lightbox"]'));

    wireHotspotMap();
  }

  function wireDestinationSuggestions() {
    container.querySelectorAll('[data-destination-result]').forEach((btn) => {
      // mousedown (not click) fires before the input's own blur, so the
      // suggestion is still in the DOM (not already hidden by blur) when
      // this runs — same autocomplete-dropdown trick Explore Map's species
      // filter uses.
      btn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const result = state.destinationResults[Number(btn.dataset.destinationResult)];
        if (result) selectDestination(result);
      });
    });
  }
}
