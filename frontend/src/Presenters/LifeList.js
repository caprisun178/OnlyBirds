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
import { renderSpeciesCard } from '../Components/SpeciesCard.js';
import { renderMissingBird } from '../Components/MissingBird.js';
import { renderProgressBar } from '../Components/ProgressBar.js';
import { escapeHtml } from '../Components/htmlUtils.js';

const PAGE_SIZE = 60;

export function mount(container, props = {}) {
  const userId = props.userId || 'u1';

  const state = {
    loading: true,
    error: null,
    view: 'grid', // 'grid' | 'list'
    sort: 'taxonomic', // 'taxonomic' | 'recent' | 'alphabetical'
    page: 1, // a region's checklist can run 500+ species; paginated client-side since we already have it all in hand
    regionCode: props.region || 'US',
    regionLabel: props.regionLabel || props.region || 'United States',
    data: null, // { regionCode, total, seen, species }

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
  };

  render();
  loadChecklist();

  async function loadChecklist() {
    state.loading = true;
    state.error = null;
    render();
    try {
      const data = await lifeListService.getChecklist(state.regionCode, userId);
      state.data = { ...data, species: lifeListService.sortSpecies(data.species, state.sort) };
      state.page = 1;
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
    state.page = 1;
    render();
  }

  function render() {
    container.innerHTML = `
      <div class="ob-stack">
        <h1>Life List</h1>
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : renderLoaded()}
      </div>
    `;
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

        <div class="ob-cluster" style="justify-content: space-between;">
          <div class="ob-cluster" role="group" aria-label="Grid or list view">
            <button type="button" class="ob-btn ob-btn--sm ${state.view === 'grid' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view="grid">Grid</button>
            <button type="button" class="ob-btn ob-btn--sm ${state.view === 'list' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view="list">List</button>
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
    return `${emptyState}${renderSpeciesList()}${renderPagination()}`;
  }

  function pageCount() {
    return Math.max(1, Math.ceil(state.data.species.length / PAGE_SIZE));
  }

  function renderSpeciesList() {
    const start = (state.page - 1) * PAGE_SIZE;
    const pageSpecies = state.data.species.slice(start, start + PAGE_SIZE);
    const cards = pageSpecies
      .map((sp) => (sp.seen ? renderSpeciesCard(sp) : renderMissingBird(sp)))
      .join('');
    return state.view === 'grid'
      ? `<div class="ob-grid" style="--ob-grid-min: 220px;">${cards}</div>`
      : `<div class="ob-stack" style="--ob-stack-gap: var(--ob-space-2);">${cards}</div>`;
  }

  function renderPagination() {
    const total = pageCount();
    if (total <= 1) return '';
    return `
      <div class="ob-cluster" style="justify-content: center;">
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="prev-page" ${state.page <= 1 ? 'disabled' : ''}>Previous</button>
        <span class="ob-text-muted ob-text-sm">Page ${state.page} of ${total}</span>
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="next-page" ${state.page >= total ? 'disabled' : ''}>Next</button>
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

    const prevBtn = container.querySelector('[data-action="prev-page"]');
    prevBtn?.addEventListener('click', () => {
      state.page = Math.max(1, state.page - 1);
      render();
    });
    const nextBtn = container.querySelector('[data-action="next-page"]');
    nextBtn?.addEventListener('click', () => {
      state.page = Math.min(pageCount(), state.page + 1);
      render();
    });

    wireRegionPicker();
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
      state.regionCode = code;
      state.regionLabel =
        state.counties.find((c) => c.code === code)?.name ||
        state.states.find((s) => s.code === code)?.name ||
        state.countries.find((c) => c.code === code)?.name ||
        code;
      state.pickerOpen = false;
      loadChecklist();
    });
  }
}
