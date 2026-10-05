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

    loading: false,
    error: null,
    plan: null, // { hotspots, likely_species } once fetched
  };

  let searchDebounceTimer = null;
  let searchRequestId = 0;

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
    const startDate = container.querySelector('#trip-start-date')?.value;
    const endDate = container.querySelector('#trip-end-date')?.value;
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
    render();
    try {
      state.plan = await tripService.plan({
        lat: state.destination.lat,
        lng: state.destination.lng,
        radiusKm,
        startDate,
        endDate,
        userId,
      });
    } catch (err) {
      state.error = err.message || 'Could not plan this trip. Try again in a moment.';
    } finally {
      state.loading = false;
      render();
    }
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
          ${state.destination ? `<p class="ob-text-sm">📍 Planning around <strong>${escapeHtml(state.destination.label)}</strong></p>` : ''}

          <div class="ob-cluster" style="align-items: flex-end;">
            <div class="ob-field">
              <label class="ob-label" for="trip-start-date">Start date</label>
              <input id="trip-start-date" type="date" class="ob-input" />
            </div>
            <div class="ob-field">
              <label class="ob-label" for="trip-end-date">End date</label>
              <input id="trip-end-date" type="date" class="ob-input" />
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
          <h2 class="ob-card__title">📍 Suggested hotspots</h2>
          ${hotspots.length === 0
            ? '<p class="ob-text-muted ob-text-sm">No eBird hotspots found nearby — try a wider radius.</p>'
            : `
              <ol class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); margin: 0; padding: 0; list-style: none;">
                ${hotspots.slice(0, 10).map((h, i) => `
                  <li class="ob-cluster" style="justify-content: space-between; align-items: center; padding: var(--ob-space-2) var(--ob-space-3); background: var(--ob-color-surface-alt); border-radius: var(--ob-radius-sm);">
                    <span class="ob-text-sm">
                      <strong>${i + 1}.</strong>
                      <a href="https://ebird.org/hotspot/${escapeHtml(h.loc_id)}" target="_blank" rel="noopener">${escapeHtml(h.name)}</a>
                    </span>
                    <span class="ob-tag ob-tag--info">${h.species_all_time} species all-time</span>
                  </li>
                `).join('')}
              </ol>
            `}
        </section>

        <section class="ob-card">
          <h2 class="ob-card__title">🐦 Birds you're likely to see</h2>
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
                    ${sp.new_for_you ? '<span class="ob-tag ob-tag--success" style="margin-top: var(--ob-space-1); display: inline-block;">✨ New for you</span>' : ''}
                  </div>
                `).join('')}
              </div>
            `}
        </section>
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

    container.querySelector('[data-action="plan-trip"]')?.addEventListener('click', planTrip);
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
