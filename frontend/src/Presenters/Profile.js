// Presenters/Profile.js — the signed-in user's own profile: avatar, life
// list total, sticker count, and an editable default region.
// See docs/features/user-profiles.md.
//
//  import { mount } from './Presenters/Profile.js';
//    mount(document.getElementById('app'), { onNavigate });

import { profileService } from '../Services/profile.js';
import { lifeListService } from '../Services/lifeList.js';
import { renderAvatar } from '../Components/Avatar.js';
import { renderRegionPicker } from '../Components/RegionPicker.js';
import { escapeHtml } from '../Components/htmlUtils.js';

export function mount(container, props = {}) {
  const { onNavigate = (route) => console.log('navigate to:', route) } = props;

  const state = {
    loading: true,
    error: null,
    profile: null, // { id, username, avatar_url, default_region, life_list_total, sticker_count }
    saving: false,

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
  load();

  async function load() {
    state.loading = true;
    state.error = null;
    render();
    try {
      state.profile = await profileService.getCurrentProfile();
    } catch (err) {
      state.error = err.message || 'Could not load your profile.';
    } finally {
      state.loading = false;
      render();
    }
  }

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        <h1>Your profile</h1>
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
    if (!state.profile) return '';
    const { username, avatar_url, default_region, life_list_total, sticker_count } = state.profile;

    return `
      <div class="ob-card ob-stack">
        <div class="ob-cluster">
          ${renderAvatar({ username, avatarUrl: avatar_url, size: 'lg' })}
          <div>
            <h2 style="margin-bottom:0;">${escapeHtml(username || 'Unnamed birder')}</h2>
            <p class="ob-text-muted ob-text-sm" style="margin:0;">Default region: ${escapeHtml(default_region)}</p>
          </div>
        </div>

        <div class="ob-cluster">
          <span class="ob-tag ob-tag--info">Life list: ${life_list_total}</span>
          <span class="ob-tag ob-tag--info">Stickers: ${sticker_count}</span>
        </div>

        <div>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="toggle-picker">
            Change default region
          </button>
        </div>

        ${state.pickerOpen ? renderPickerSection() : ''}
      </div>

      <div class="ob-cluster">
        <button type="button" class="ob-btn ob-btn--subtle ob-btn--sm" data-action="go-life-list">
          Open life list
        </button>
        <button type="button" class="ob-btn ob-btn--subtle ob-btn--sm" data-action="go-stickers">
          View stickers
        </button>
      </div>
    `;
  }

  function renderPickerSection() {
    return `
      <div class="ob-card ob-card--flat ob-stack">
        ${renderRegionPicker({
          countries: state.countries,
          states: state.states,
          counties: state.counties,
          pickerCountry: state.pickerCountry,
          pickerState: state.pickerState,
          pickerCounty: state.pickerCounty,
          loading: state.pickerLoading,
        })}
        <button
          type="button"
          class="ob-btn ob-btn--primary ob-btn--sm"
          data-action="save-region"
          style="align-self:flex-start;"
          ${state.saving ? 'disabled' : ''}
        >
          ${state.saving ? 'Saving…' : 'Save region'}
        </button>
      </div>
    `;
  }

  // ---- Wiring ---------------------------------------

  function wire() {
    container.querySelector('[data-action="toggle-picker"]')?.addEventListener('click', () => {
      state.pickerOpen = !state.pickerOpen;
      render();
      if (state.pickerOpen && state.countries.length === 0) loadCountries();
    });

    container.querySelector('[data-action="go-life-list"]')?.addEventListener('click', () => onNavigate('life-list'));
    container.querySelector('[data-action="go-stickers"]')?.addEventListener('click', () => onNavigate('stickers'));

    wireRegionPicker();
  }

  async function loadCountries() {
    state.pickerLoading = true;
    render();
    try {
      state.countries = await lifeListService.getRegionOptions('world', 'country');
    } catch (err) {
      // Leave countries empty — the picker just shows no options.
    } finally {
      state.pickerLoading = false;
      render();
    }
  }

  function wireRegionPicker() {
    const countrySelect = container.querySelector('[data-role="region-country"]');
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
        // Some countries have no subnational1 breakdown — fine, no options.
      }
      render();
    });

    const stateSelect = container.querySelector('[data-role="region-state"]');
    stateSelect?.addEventListener('change', async () => {
      state.pickerState = stateSelect.value;
      state.pickerCounty = '';
      state.counties = [];
      render();
      if (!state.pickerState) return;
      try {
        state.counties = await lifeListService.getRegionOptions(state.pickerState, 'subnational2');
      } catch (err) {
        // Not every state has a county breakdown — same deal.
      }
      render();
    });

    const countySelect = container.querySelector('[data-role="region-county"]');
    countySelect?.addEventListener('change', () => {
      state.pickerCounty = countySelect.value;
    });

    const saveBtn = container.querySelector('[data-action="save-region"]');
    saveBtn?.addEventListener('click', async () => {
      const code = state.pickerCounty || state.pickerState || state.pickerCountry;
      if (!code) return;
      state.saving = true;
      render();
      try {
        state.profile = await profileService.updateDefaultRegion(state.profile.id, code);
        state.pickerOpen = false;
      } catch (err) {
        state.error = err.message || 'Could not save your region.';
      } finally {
        state.saving = false;
        render();
      }
    });
  }
}