// Presenters/LifeList.js — the Life List completion view.
//
//   import { mount } from './Presenters/LifeList.js';
//   mount(document.getElementById('app'), { userId: 'u1', region: 'US-NC' });
//
// No real auth/profile yet (user-profiles.md is still "Planned"), so
// `userId` and `region` default to placeholders here instead of pulling
// from a shared profile module — keeps this screen usable standalone.
// See docs/features/life-list.md.

import { lifeListService } from '../Services/lifeList.js';
import { pinsService } from '../Services/pins.js';
import { renderSpeciesCard } from '../Components/SpeciesCard.js';
import { renderMissingBird } from '../Components/MissingBird.js';
import { renderProgressBar } from '../Components/ProgressBar.js';
import { escapeHtml } from '../Components/htmlUtils.js';

// Default view shows only the top DEFAULT_LIMIT species (taxonomic order,
// i.e. eBird's own regional frequency ordering) rather than the whole
// checklist at once — a region can run 500-700+ species. "Show more" grows
// the visible slice by LOAD_INCREMENT at a time, up to the full checklist.
const DEFAULT_LIMIT = 50;
const LOAD_INCREMENT = 50;

export function mount(container, props = {}) {
  const userId = props.userId || 'u1';
  const { onNavigate } = props; // optional — omitted when this screen is previewed standalone

  const state = {
    loading: true,
    error: null,
    view: 'grid', // 'grid' | 'list'
    sort: 'taxonomic', // 'taxonomic' | 'recent' | 'alphabetical'
    limit: DEFAULT_LIMIT, // how many of the (already-filtered) species are visible; grows via "Show more"
    regionCode: props.region || 'US',
    regionLabel: props.regionLabel || props.region || 'United States',
    data: null, // { regionCode, total, seen, species }

    // Filters — seen/unseen, bird type (eBird family), and a name search
    // narrow the species list before it's sliced to `limit`. Region is
    // already a "filter" via the region picker below.
    seenFilter: 'all', // 'all' | 'seen' | 'unseen'
    typeFilter: '', // '' (all types) or a family_common_name
    searchQuery: '', // matched against common + scientific name, case-insensitive
    families: [], // distinct family_common_name values in the current checklist

    // Region picker: cascading country -> state/province -> county selects,
    // each level optional (eBird's region hierarchy: world -> country ->
    // subnational1 -> subnational2).
    pickerOpen: false,
    pickerLoading: false,
    countries: [],
    states: [],
    counties: [],
    pickerCountry: '',
    pickerState: '',
    pickerCounty: '',

    // Quick state filter — a one-click shortcut to a US state's checklist,
    // next to the other filters, instead of always going through "Change
    // region"'s country -> state picker. Loaded eagerly (unlike `states`
    // above, which only loads once the picker's country dropdown is used).
    quickStates: [],

    // Scientific names (lowercased) the user has pinned — see
    // Components/MissingBird.js's pin button. A Set, not the raw pin list,
    // since every lookup here is just "is this species pinned?".
    pinnedNames: new Set(),
    pinError: null,
  };

  render();
  loadChecklist();
  loadQuickStates();
  loadPins();

  async function loadChecklist() {
    state.loading = true;
    state.error = null;
    render();
    try {
      const data = await lifeListService.getChecklist(state.regionCode, userId);
      state.data = { ...data, species: lifeListService.sortSpecies(data.species, state.sort) };
      state.families = lifeListService.getFamilies(data.species);
      state.seenFilter = 'all';
      state.typeFilter = '';
      state.searchQuery = '';
      state.limit = DEFAULT_LIMIT;
    } catch (err) {
      state.error = err.message || 'Could not load the checklist for this region.';
      state.data = null;
    } finally {
      state.loading = false;
      render();
    }
  }

  function applySort(sort) {
    state.sort = sort;
    if (state.data) {
      state.data = { ...state.data, species: lifeListService.sortSpecies(state.data.species, sort) };
    }
    state.limit = DEFAULT_LIMIT;
    render();
  }

  function applyFilters({ seenFilter, typeFilter } = {}) {
    if (seenFilter !== undefined) state.seenFilter = seenFilter;
    if (typeFilter !== undefined) state.typeFilter = typeFilter;
    state.limit = DEFAULT_LIMIT;
    render();
  }

  // Search re-renders on every keystroke (live filtering), unlike the
  // dropdown filters above — a full `render()` would otherwise kick focus
  // out of the input after each character, since this presenter always
  // rebuilds the whole container from scratch. Preserving focus + cursor
  // position across that rebuild is simpler here than teaching this
  // presenter partial re-renders just for one field.
  function applySearch(query) {
    state.searchQuery = query;
    state.limit = DEFAULT_LIMIT;
    const input = container.querySelector('#species-search');
    const hadFocus = input && document.activeElement === input;
    const selectionStart = input?.selectionStart;
    const selectionEnd = input?.selectionEnd;
    render();
    if (hadFocus) {
      const newInput = container.querySelector('#species-search');
      newInput?.focus();
      newInput?.setSelectionRange(selectionStart, selectionEnd);
    }
  }

  // The sorted (seen-first by default) species list, narrowed by the
  // seen/unseen filter, bird-type filter, and name search. `limit` slices
  // this, not the raw data.
  function filteredSpecies() {
    const query = state.searchQuery.trim().toLowerCase();
    return state.data.species.filter((sp) => {
      if (state.seenFilter === 'seen' && !sp.seen) return false;
      if (state.seenFilter === 'unseen' && sp.seen) return false;
      if (state.typeFilter && sp.family_common_name !== state.typeFilter) return false;
      if (query && !sp.common_name.toLowerCase().includes(query) && !sp.scientific_name.toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
  }

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Life List</h1>
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.pinError ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.pinError)}</div>` : ''}
        ${state.loading ? renderLoading() : renderLoaded()}
      </div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]').addEventListener('click', () => onNavigate('home'));
    }
    wire();
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderLoaded() {
    if (!state.data) return '';
    return `
      ${renderHeader()}
      ${renderBody()}
    `;
  }

  // ---- Header: region, progress, region picker, view/sort controls ------

  function renderHeader() {
    return `
      <div class="ob-card ob-stack">
        <div class="ob-cluster" style="justify-content: space-between;">
          <div>
            <h2 style="margin-bottom:0;">${escapeHtml(state.regionLabel)}</h2>
            <p class="ob-text-muted ob-text-sm" style="margin:0;">${state.data.total} species on the checklist</p>
          </div>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="toggle-picker">Change region</button>
        </div>

        ${renderProgressBar(state.data.seen, state.data.total)}

        ${state.pickerOpen ? renderRegionPicker() : ''}

        <div class="ob-field">
          <label class="ob-label ob-visually-hidden" for="species-search">Search species</label>
          <input
            id="species-search"
            type="search"
            class="ob-input"
            placeholder="Search by common or scientific name…"
            value="${escapeHtml(state.searchQuery)}"
          />
        </div>

        <div class="ob-cluster" style="justify-content: space-between;">
          <div class="ob-cluster" role="group" aria-label="Grid or list view">
            <button type="button" class="ob-btn ob-btn--sm ${state.view === 'grid' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view="grid">Grid</button>
            <button type="button" class="ob-btn ob-btn--sm ${state.view === 'list' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view="list">List</button>
          </div>
          <div class="ob-cluster" style="align-items:center; gap: var(--ob-space-3);">
            <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
              <label class="ob-label" for="seen-filter">Show</label>
              <select id="seen-filter" class="ob-select" style="width:auto;">
                <option value="all" ${state.seenFilter === 'all' ? 'selected' : ''}>All</option>
                <option value="seen" ${state.seenFilter === 'seen' ? 'selected' : ''}>Seen</option>
                <option value="unseen" ${state.seenFilter === 'unseen' ? 'selected' : ''}>Unseen</option>
              </select>
            </div>
            <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
              <label class="ob-label" for="type-filter">Type</label>
              <select id="type-filter" class="ob-select" style="width:auto;">
                <option value="">All types</option>
                ${state.families.map((f) => `<option value="${escapeHtml(f)}" ${f === state.typeFilter ? 'selected' : ''}>${escapeHtml(f)}</option>`).join('')}
              </select>
            </div>
            <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
              <label class="ob-label" for="state-filter">State</label>
              <select id="state-filter" class="ob-select" style="width:auto;">
                ${!isKnownQuickRegion() ? '<option value="" disabled selected hidden>Custom region</option>' : ''}
                <option value="US" ${state.regionCode === 'US' ? 'selected' : ''}>Whole country</option>
                ${state.quickStates.map((s) => `<option value="${escapeHtml(s.code)}" ${s.code === state.regionCode ? 'selected' : ''}>${escapeHtml(s.name)}</option>`).join('')}
              </select>
            </div>
            <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
              <label class="ob-label" for="sort-select">Sort</label>
              <select id="sort-select" class="ob-select" style="width:auto;">
                <option value="taxonomic" ${state.sort === 'taxonomic' ? 'selected' : ''}>Taxonomic order</option>
                <option value="recent" ${state.sort === 'recent' ? 'selected' : ''}>Most recent</option>
                <option value="alphabetical" ${state.sort === 'alphabetical' ? 'selected' : ''}>Alphabetical</option>
              </select>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderRegionPicker() {
    return `
      <div class="ob-card ob-card--flat ob-stack" data-role="region-picker">
        <div class="ob-grid" style="--ob-grid-min: 180px;">
          <div class="ob-field">
            <label class="ob-label" for="picker-country">Country</label>
            <select id="picker-country" class="ob-select">
              <option value="">${state.pickerLoading && state.countries.length === 0 ? 'Loading…' : 'Select a country'}</option>
              ${state.countries.map((c) => `<option value="${escapeHtml(c.code)}" ${c.code === state.pickerCountry ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
            </select>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="picker-state">State / province</label>
            <select id="picker-state" class="ob-select" ${state.pickerCountry ? '' : 'disabled'}>
              <option value="">Whole country</option>
              ${state.states.map((s) => `<option value="${escapeHtml(s.code)}" ${s.code === state.pickerState ? 'selected' : ''}>${escapeHtml(s.name)}</option>`).join('')}
            </select>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="picker-county">County</label>
            <select id="picker-county" class="ob-select" ${state.pickerState ? '' : 'disabled'}>
              <option value="">Whole state</option>
              ${state.counties.map((c) => `<option value="${escapeHtml(c.code)}" ${c.code === state.pickerCounty ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join('')}
            </select>
          </div>
        </div>
        <button type="button" class="ob-btn ob-btn--primary ob-btn--sm" data-action="apply-region" style="align-self:flex-start;">View this region's checklist</button>
      </div>
    `;
  }

  // ---- Body: the completion grid/list + empty state ----------------------

  function renderBody() {
    const emptyState = state.data.seen === 0
      ? `<div class="ob-card ob-text-center">
           <p class="ob-card__body">You haven't logged any birds in ${escapeHtml(state.regionLabel)} yet.</p>
         </div>`
      : '';
    const matches = filteredSpecies();
    const noMatches = matches.length === 0
      ? `<div class="ob-card ob-text-center">
           <p class="ob-card__body">No species match the current filters.</p>
         </div>`
      : '';
    return `${emptyState}${noMatches}${renderSpeciesList(matches)}${renderLoadMore(matches)}`;
  }

  function renderSpeciesList(matches) {
    const visibleSpecies = matches.slice(0, state.limit);
    const cards = visibleSpecies
      .map((sp) => (sp.seen
        ? renderSpeciesCard(sp)
        : renderMissingBird(sp, { pinned: state.pinnedNames.has(sp.scientific_name.toLowerCase()) })))
      .join('');
    return state.view === 'grid'
      ? `<div class="ob-grid" style="--ob-grid-min: 220px;">${cards}</div>`
      : `<div class="ob-stack" style="--ob-stack-gap: var(--ob-space-2);">${cards}</div>`;
  }

  function renderLoadMore(matches) {
    const max = matches.length;
    if (max === 0) return '';
    const shown = Math.min(state.limit, max);
    return `
      <div class="ob-cluster" style="justify-content: center; flex-direction: column; align-items: center;">
        <span class="ob-text-muted ob-text-sm">Showing ${shown} of ${max} species</span>
        ${shown < max
          ? `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="show-more">Show ${Math.min(LOAD_INCREMENT, max - shown)} more</button>`
          : ''}
      </div>
    `;
  }

  // ---- Wiring -------------------------------------------------------------

  function wire() {
    const toggleBtn = container.querySelector('[data-action="toggle-picker"]');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        state.pickerOpen = !state.pickerOpen;
        render();
        if (state.pickerOpen && state.countries.length === 0) loadCountries();
      });
    }

    container.querySelectorAll('[data-view]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.view = btn.dataset.view;
        render();
      });
    });

    const sortSelect = container.querySelector('#sort-select');
    if (sortSelect) sortSelect.addEventListener('change', () => applySort(sortSelect.value));

    const searchInput = container.querySelector('#species-search');
    searchInput?.addEventListener('input', () => applySearch(searchInput.value));

    const seenFilterSelect = container.querySelector('#seen-filter');
    if (seenFilterSelect) {
      seenFilterSelect.addEventListener('change', () => applyFilters({ seenFilter: seenFilterSelect.value }));
    }

    const typeFilterSelect = container.querySelector('#type-filter');
    if (typeFilterSelect) {
      typeFilterSelect.addEventListener('change', () => applyFilters({ typeFilter: typeFilterSelect.value }));
    }

    const stateFilterSelect = container.querySelector('#state-filter');
    if (stateFilterSelect) {
      stateFilterSelect.addEventListener('change', () => {
        const code = stateFilterSelect.value;
        const label = code === 'US' ? 'United States' : state.quickStates.find((s) => s.code === code)?.name || code;
        changeRegion(code, label);
      });
    }

    const showMoreBtn = container.querySelector('[data-action="show-more"]');
    showMoreBtn?.addEventListener('click', () => {
      state.limit = Math.min(filteredSpecies().length, state.limit + LOAD_INCREMENT);
      render();
    });

    wireSpeciesCards();
    wireRegionPicker();
    wirePinButtons();
    wireMissingBirdProfileCards();
  }

  function wirePinButtons() {
    container.querySelectorAll('[data-action="toggle-pin"]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        // The whole MissingBird card is now its own click target (Bird
        // Info — see wireMissingBirdProfileCards() below); without this,
        // clicking "Pin" would bubble up and also open the profile page.
        e.stopPropagation();
        togglePin(btn.dataset.pinScientificName, btn.dataset.pinCommonName);
      });
    });
  }

  // MissingBird.js's whole card (not seen yet) opens the Bird Info page —
  // docs/features/bird-info.md §1, row 2. `data-profile-scientific-name` is
  // its own attribute, distinct from `data-scientific-name` (seen cards,
  // just below) and `data-pin-scientific-name` (the pin button inside this
  // same card) — see that component's own comment for why reusing either
  // of those names here would double-wire the click.
  function wireMissingBirdProfileCards() {
    if (!onNavigate) return;
    container.querySelectorAll('[data-profile-scientific-name]').forEach((el) => {
      const open = () => onNavigate('species-profile', {
        scientificName: el.dataset.profileScientificName,
        commonName: el.dataset.profileCommonName,
      });
      el.addEventListener('click', open);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    });
  }

  // Seen-species cards open that species' observation log. Missing-bird
  // placeholders aren't clickable here — they open the Bird Info page
  // instead (wireMissingBirdProfileCards() above).
  function wireSpeciesCards() {
    if (!onNavigate) return;
    container.querySelectorAll('[data-scientific-name]').forEach((el) => {
      const open = () => onNavigate('observation-log', {
        userId,
        scientificName: el.dataset.scientificName,
        commonName: el.dataset.commonName,
        // so "Back to life list" can return to the same region instead of
        // resetting to the default
        region: state.regionCode,
        regionLabel: state.regionLabel,
      });
      el.addEventListener('click', open);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    });
    wireSpeciesNameProfileLinks();
  }

  // The species name inside a seen card is its own, separate click target
  // (Bird Info — docs/features/bird-info.md §1, row 1) — `stopPropagation()`
  // so clicking the name doesn't *also* fire the whole card's
  // navigate-to-observation-log handler wired just above.
  function wireSpeciesNameProfileLinks() {
    if (!onNavigate) return;
    container.querySelectorAll('[data-action="view-profile"]').forEach((el) => {
      const open = (e) => {
        e.stopPropagation();
        onNavigate('species-profile', {
          scientificName: el.dataset.profileScientificName,
          commonName: el.dataset.profileCommonName,
        });
      };
      el.addEventListener('click', open);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open(e);
        }
      });
    });
  }

  async function loadQuickStates() {
    try {
      state.quickStates = await lifeListService.getRegionOptions('US', 'subnational1');
      render();
    } catch (err) {
      // Leave it empty — the quick filter just won't have state options.
    }
  }

  async function loadPins() {
    try {
      const pins = await pinsService.list(userId);
      state.pinnedNames = new Set(pins.map((p) => p.scientific_name.toLowerCase()));
      render();
    } catch (err) {
      // Leave it empty — pin buttons just show as unpinned until this loads.
    }
  }

  // Pinning/unpinning is a discrete click, not live-as-you-type, so a full
  // render() (same as every other button handler in this file) is fine —
  // no focus to preserve.
  async function togglePin(scientificName, commonName) {
    state.pinError = null;
    const key = scientificName.toLowerCase();
    try {
      if (state.pinnedNames.has(key)) {
        await pinsService.unpin(userId, scientificName);
        state.pinnedNames.delete(key);
      } else {
        await pinsService.pin(userId, { scientificName, commonName });
        state.pinnedNames.add(key);
      }
    } catch (err) {
      state.pinError = err.message || 'Could not update that pin. Try again in a moment.';
    }
    render();
  }

  function changeRegion(code, label) {
    state.regionCode = code;
    state.regionLabel = label;
    state.pickerOpen = false;
    loadChecklist();
  }

  // Whether the current region is one the quick state filter can represent
  // (whole US, or a fetched US state) — false for a county picked via
  // "Change region", or a non-US country, so the dropdown shows "Custom
  // region" instead of silently defaulting to the wrong option.
  function isKnownQuickRegion() {
    return state.regionCode === 'US' || state.quickStates.some((s) => s.code === state.regionCode);
  }

  async function loadCountries() {
    state.pickerLoading = true;
    render();
    try {
      state.countries = await lifeListService.getRegionOptions('world', 'country');
    } catch (err) {
      // Leave countries empty — the picker just shows no options to choose from.
    } finally {
      state.pickerLoading = false;
      render();
    }
  }

  function wireRegionPicker() {
    const countrySelect = container.querySelector('#picker-country');
    if (!countrySelect) return;

    countrySelect.addEventListener('change', async () => {
      state.pickerCountry = countrySelect.value;
      state.pickerState = '';
      state.pickerCounty = '';
      state.states = [];
      state.counties = [];
      render();
      if (!state.pickerCountry) return;
      try {
        state.states = await lifeListService.getRegionOptions(state.pickerCountry, 'subnational1');
      } catch (err) {
        // Some countries have no subnational1 breakdown in eBird — fine, no state options.
      }
      render();
    });

    const stateSelect = container.querySelector('#picker-state');
    stateSelect?.addEventListener('change', async () => {
      state.pickerState = stateSelect.value;
      state.pickerCounty = '';
      state.counties = [];
      render();
      if (!state.pickerState) return;
      try {
        state.counties = await lifeListService.getRegionOptions(state.pickerState, 'subnational2');
      } catch (err) {
        // Not every state has a county breakdown either — same deal.
      }
      render();
    });

    const countySelect = container.querySelector('#picker-county');
    countySelect?.addEventListener('change', () => {
      state.pickerCounty = countySelect.value;
    });

    const applyBtn = container.querySelector('[data-action="apply-region"]');
    applyBtn?.addEventListener('click', () => {
      const code = state.pickerCounty || state.pickerState || state.pickerCountry;
      if (!code) return;
      const label =
        state.counties.find((c) => c.code === code)?.name ||
        state.states.find((s) => s.code === code)?.name ||
        state.countries.find((c) => c.code === code)?.name ||
        code;
      changeRegion(code, label);
    });
  }
}
