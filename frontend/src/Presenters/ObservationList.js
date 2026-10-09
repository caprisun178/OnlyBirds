// Presenters/ObservationList.js — a user's own observation log. Opened
// standalone (all of a user's observations) or scoped to one species (a
// Life List "seen" card's click target — see Presenters/LifeList.js).
// Observations are editable in place (backend: PATCH /observations/{id}).
//
//   import { mount } from './Presenters/ObservationList.js';
//   mount(document.getElementById('app'), { userId: 'u1' });
//   // or, scoped to a species:
//   mount(document.getElementById('app'), {
//     userId: 'u1', scientificName: 'Turdus migratorius', commonName: 'American Robin',
//   });
//
// `embedded: true` (set by `Presenters/LifeList.js`, which mounts this in
// its own "Observations" tab) drops the "← Back" button and outer padding
// and renders the heading as an `<h2>` instead of `<h1>` — same convention
// as `ExploreMap.js`'s `embedded` prop, see that file's comment for why.
//
// Unscoped (no `scientificName`) view also offers list/card display modes
// and date-range + species filters — scoped (single-species) view skips
// the species filter since it's redundant there, but still gets list/card.
//
// See docs/features/life-list.md.

import { observationService } from '../Services/observations.js';
import { uploadsService } from '../Services/uploads.js';
import { escapeHtml } from '../Components/htmlUtils.js';

const SEX_OPTIONS = [
  ['', 'Not specified'],
  ['male', 'Male'],
  ['female', 'Female'],
  ['unknown', 'Unknown'],
];
const LIFE_STAGE_OPTIONS = [
  ['', 'Not specified'],
  ['adult', 'Adult'],
  ['juvenile', 'Juvenile'],
  ['fledgling', 'Fledgling'],
  ['unknown', 'Unknown'],
];
const DETECTION_OPTIONS = [
  ['', 'Not specified'],
  ['sight', 'Saw it'],
  ['sound', 'Heard it'],
];

export function mount(container, props = {}) {
  const userId = props.userId || 'u1';
  // onNavigate optional — screen previewed standalone. region/regionLabel
  // are just carried through from the Life List card that opened this
  // screen, so "back" can return to the same region instead of resetting.
  const { onNavigate, embedded = false, scientificName = null, commonName = null, region = null, regionLabel = null } = props;

  const state = {
    loading: true,
    error: null,
    allObservations: [], // full fetched list (already species-scoped via props, if any) — filters below narrow a view of this, not re-fetch
    editingId: null, // id of the observation currently being edited, or null
    editValues: null,
    saving: false,
    saveError: null,
    photoUploadState: 'idle', // 'idle' | 'uploading' | 'done' | 'error'
    photoUploadError: null,

    viewMode: 'list', // 'list' | 'card'
    dateFrom: '', // 'YYYY-MM-DD', inclusive
    dateTo: '', // 'YYYY-MM-DD', inclusive
    speciesFilter: '', // '' = all; otherwise a species.common_name — only shown when unscoped (see renderFilterBar)
  };

  render();
  loadObservations();

  async function loadObservations() {
    state.loading = true;
    state.error = null;
    render();
    try {
      // Scoped server-side now (not fetch-everything-then-filter) — see
      // `app/routers/observations.py`'s own note on why that mattered once
      // a user's history gets large.
      state.allObservations = await observationService.getSortedObservations(userId, scientificName);
    } catch (err) {
      state.error = err.message || 'Could not load your observation log.';
      state.allObservations = [];
    } finally {
      state.loading = false;
      render();
    }
  }

  // Distinct species present in the (already species-scoped-via-props)
  // fetched list, for the species filter dropdown — this is "what this
  // user has actually observed," not the full taxonomy, so it's always a
  // short, relevant list regardless of how large the real checklist is.
  function speciesOptions() {
    const seen = new Map();
    for (const obs of state.allObservations) {
      const name = obs.species?.common_name;
      if (name && !seen.has(name)) seen.set(name, obs.species.scientific_name);
    }
    return [...seen.entries()].sort(([a], [b]) => a.localeCompare(b));
  }

  // The date-range + species filters applied on top of `allObservations` —
  // client-side, same reasoning as Life List's own filters: the backend
  // returns the full list with no query params to narrow it (see
  // `GET /users/{user_id}/observations`), and a user's own observation
  // count is small enough that filtering in the browser is simpler than
  // adding query-param support for what's likely a short list either way.
  function visibleObservations() {
    return state.allObservations.filter((obs) => {
      if (state.dateFrom && obs.observed_at.slice(0, 10) < state.dateFrom) return false;
      if (state.dateTo && obs.observed_at.slice(0, 10) > state.dateTo) return false;
      if (state.speciesFilter && obs.species?.common_name !== state.speciesFilter) return false;
      return true;
    });
  }

  // ---- Editing --------------------------------------------------------

  function startEdit(obs) {
    state.editingId = obs.id;
    state.saveError = null;
    state.photoUploadState = 'idle';
    state.photoUploadError = null;
    state.editValues = {
      observedAt: toDatetimeLocalValue(obs.observed_at),
      locationName: obs.location_name || '',
      notes: obs.notes || '',
      sex: obs.sex || '',
      lifeStage: obs.life_stage || '',
      detectionType: obs.detection_type || '',
      photoUrl: obs.photo_url || null, // the URL that will actually be saved
      photoPreviewUrl: obs.photo_url || null, // what's shown — swaps to a local preview while a new file uploads
    };
    render();
  }

  function cancelEdit() {
    state.editingId = null;
    state.editValues = null;
    state.saveError = null;
    state.photoUploadState = 'idle';
    state.photoUploadError = null;
    render();
  }

  async function saveEdit(observationId, form) {
    const fieldNotes = {
      observedAt: new Date(form.querySelector('#edit-observed-at').value).toISOString(),
      locationName: form.querySelector('#edit-location').value.trim(),
      notes: form.querySelector('#edit-notes').value.trim(),
      sex: form.querySelector('#edit-sex').value,
      lifeStage: form.querySelector('#edit-life-stage').value,
      detectionType: form.querySelector('#edit-detection').value,
      photoUrl: state.editValues.photoUrl,
    };

    state.saving = true;
    state.saveError = null;
    render();
    try {
      const updated = await observationService.updateObservation(observationId, fieldNotes);
      const index = state.allObservations.findIndex((o) => o.id === observationId);
      if (index !== -1) state.allObservations[index] = updated;
      state.editingId = null;
      state.editValues = null;
    } catch (err) {
      state.saveError = err.message || 'Could not save your changes. Please try again.';
    } finally {
      state.saving = false;
      render();
    }
  }

  // Targeted DOM updates (not a full render()) while a photo uploads, same
  // reasoning as AddObservation's field-notes step: a full re-render would
  // wipe out whatever the user's mid-typing in the notes field etc.
  function wireEditPhotoInput(form) {
    const photoInput = form.querySelector('#edit-photo');
    if (!photoInput) return;
    photoInput.addEventListener('change', async () => {
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = () => {
        state.editValues.photoPreviewUrl = reader.result;
        updateEditPhotoStatusDom(form);
      };
      reader.readAsDataURL(file);

      state.photoUploadState = 'uploading';
      state.photoUploadError = null;
      updateEditPhotoStatusDom(form);
      updateEditSubmitButtonDom(form);
      try {
        state.editValues.photoUrl = await uploadsService.uploadPhoto(file);
        state.photoUploadState = 'done';
      } catch (err) {
        state.photoUploadState = 'error';
        state.photoUploadError = `${err.message} Your existing photo was kept.`;
        state.editValues.photoPreviewUrl = state.editValues.photoUrl; // revert the preview
      }
      updateEditPhotoStatusDom(form);
      updateEditSubmitButtonDom(form);
    });
  }

  function renderEditPhotoStatusHtml() {
    const v = state.editValues;
    return `
      ${v.photoPreviewUrl ? `<img src="${escapeHtml(v.photoPreviewUrl)}" alt="" style="max-width:220px;border-radius:var(--ob-radius-md);" />` : ''}
      ${state.photoUploadState === 'uploading' ? '<p class="ob-hint">Uploading photo…</p>' : ''}
      ${state.photoUploadState === 'error' ? `<div class="ob-alert ob-alert--warning">${escapeHtml(state.photoUploadError)}</div>` : ''}
    `;
  }

  function updateEditPhotoStatusDom(form) {
    const el = form.querySelector('[data-role="edit-photo-status"]');
    if (el) el.innerHTML = renderEditPhotoStatusHtml();
  }

  function updateEditSubmitButtonDom(form) {
    const btn = form.querySelector('[data-role="edit-submit-btn"]');
    if (!btn) return;
    const uploading = state.photoUploadState === 'uploading';
    btn.disabled = uploading;
    btn.textContent = uploading ? 'Uploading photo…' : 'Save';
  }

  // ---- Render -----------------------------------------------------------

  function render() {
    const headingTag = embedded ? 'h2' : 'h1';
    container.innerHTML = `
      <div class="ob-stack${embedded ? '' : ' ob-container'}">
        ${!embedded && onNavigate ? `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back" style="align-self:flex-start;">← Back to ${scientificName ? 'life list' : 'home'}</button>` : ''}
        <${headingTag}>${scientificName ? escapeHtml(commonName || scientificName) : 'My observations'}</${headingTag}>
        ${scientificName ? `<p class="ob-text-muted ob-text-sm" style="margin:0;"><em>${escapeHtml(scientificName)}</em></p>` : ''}
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : renderBody()}
      </div>
    `;
    if (!embedded && onNavigate) {
      container.querySelector('[data-action="back"]').addEventListener('click', () => {
        onNavigate(scientificName ? 'life-list' : 'home', scientificName ? { region, regionLabel } : undefined);
      });
    }
    wire();
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderBody() {
    if (state.allObservations.length === 0) {
      const message = scientificName
        ? `You haven't logged any observations of ${escapeHtml(commonName || scientificName)} yet.`
        : "You haven't logged any observations yet.";
      return `<div class="ob-card ob-text-center"><p class="ob-card__body">${message}</p></div>`;
    }
    const visible = visibleObservations();
    const noMatches = visible.length === 0
      ? '<div class="ob-card ob-text-center"><p class="ob-card__body">No observations match the current filters.</p></div>'
      : '';
    return `
      ${renderFirstObserved()}
      ${renderFilterBar()}
      ${noMatches}
      ${visible.length > 0
        ? (state.viewMode === 'card'
            ? `<div class="ob-grid" style="--ob-grid-min: 220px;">${visible.map(renderObservationCard).join('')}</div>`
            : `<div class="ob-stack">${visible.map(renderObservationCard).join('')}</div>`)
        : ''}
    `;
  }

  // View mode (list/card), plus date-range + species filters. The species
  // dropdown only makes sense unscoped — a per-species view (opened from a
  // Life List card) is already filtered to one species by definition.
  function renderFilterBar() {
    const options = speciesOptions();
    return `
      <div class="ob-card ob-card--flat ob-cluster" style="justify-content: space-between; align-items: flex-end;" data-role="filter-bar">
        <div class="ob-cluster" role="group" aria-label="List or card view">
          <button type="button" class="ob-btn ob-btn--sm ${state.viewMode === 'list' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view-mode="list">List</button>
          <button type="button" class="ob-btn ob-btn--sm ${state.viewMode === 'card' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-view-mode="card">Card</button>
        </div>
        <div class="ob-cluster" style="align-items:flex-end; gap: var(--ob-space-3);">
          <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
            <label class="ob-label" for="date-from">From</label>
            <input id="date-from" type="date" class="ob-input" style="width:auto;" value="${escapeHtml(state.dateFrom)}" />
          </div>
          <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
            <label class="ob-label" for="date-to">To</label>
            <input id="date-to" type="date" class="ob-input" style="width:auto;" value="${escapeHtml(state.dateTo)}" />
          </div>
          ${!scientificName ? `
            <div class="ob-field" style="flex-direction:row; align-items:center; gap: var(--ob-space-2);">
              <label class="ob-label" for="species-filter">Species</label>
              <select id="species-filter" class="ob-select" style="width:auto;">
                <option value="">All species</option>
                ${options.map(([name]) => `<option value="${escapeHtml(name)}" ${name === state.speciesFilter ? 'selected' : ''}>${escapeHtml(name)}</option>`).join('')}
              </select>
            </div>
          ` : ''}
          ${(state.dateFrom || state.dateTo || state.speciesFilter)
            ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="clear-filters">Clear filters</button>'
            : ''}
        </div>
      </div>
    `;
  }

  function renderFirstObserved() {
    const earliest = state.allObservations.reduce((min, obs) => (
      new Date(obs.observed_at) < new Date(min.observed_at) ? obs : min
    ));
    const dateLabel = new Date(earliest.observed_at).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    });
    const speciesLabel = scientificName ? '' : `${escapeHtml(earliest.species?.common_name || 'Unknown species')} — `;
    const whereLabel = earliest.location_name ? ` at ${escapeHtml(earliest.location_name)}` : '';
    return `
      <div class="ob-alert ob-alert--success">
        <strong>First observed:</strong> ${speciesLabel}${escapeHtml(dateLabel)}${whereLabel}
      </div>
    `;
  }

  // Dispatches by view mode — an observation being edited always gets the
  // full-width edit form regardless of mode (a wide form crammed into a
  // grid cell would be unusable, so it spans every column in card mode).
  function renderObservationCard(obs) {
    if (state.editingId === obs.id) {
      return state.viewMode === 'card'
        ? `<div style="grid-column: 1 / -1;">${renderEditForm(obs)}</div>`
        : renderEditForm(obs);
    }
    return state.viewMode === 'card' ? renderObservationCardCompact(obs) : renderObservationRow(obs);
  }

  function renderObservationRow(obs) {
    const dateLabel = obs.observed_at
      ? new Date(obs.observed_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
      : 'Unknown date';
    const detectionPrefix = obs.detection_type === 'sound' ? 'Heard — ' : '';
    const tags = [obs.sex, obs.life_stage].filter((v) => v && v !== 'unknown');

    return `
      <article class="ob-card ob-cluster" style="align-items:flex-start; flex-wrap:nowrap; gap: var(--ob-space-3);">
        ${obs.photo_url
          ? `<img src="${escapeHtml(obs.photo_url)}" alt="" style="width:96px;height:96px;object-fit:cover;border-radius:var(--ob-radius-md);flex-shrink:0;" />`
          : ''}
        <div class="ob-stack" style="flex:1;">
          ${scientificName ? '' : `<h3 class="ob-card__title">${escapeHtml(obs.species?.common_name || 'Unknown species')}</h3>`}
          <p class="ob-card__body ob-text-sm">${detectionPrefix}${escapeHtml(dateLabel)} — ${escapeHtml(obs.location_name || 'location not set')}</p>
          ${obs.notes ? `<p class="ob-text-sm">${escapeHtml(obs.notes)}</p>` : ''}
          <div class="ob-cluster">
            ${tags.map((t) => `<span class="ob-tag">${escapeHtml(t)}</span>`).join('')}
            <span class="ob-tag ob-tag--info">${escapeHtml(obs.source)}</span>
          </div>
        </div>
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="edit" data-observation-id="${escapeHtml(obs.id)}" style="flex-shrink:0;">Edit</button>
      </article>
    `;
  }

  // Compact grid card — photo prominent, details stacked below, same data
  // as the list row just laid out for a multi-column grid instead of a
  // full-width row.
  function renderObservationCardCompact(obs) {
    const dateLabel = obs.observed_at
      ? new Date(obs.observed_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
      : 'Unknown date';
    const detectionPrefix = obs.detection_type === 'sound' ? 'Heard — ' : '';
    const tags = [obs.sex, obs.life_stage].filter((v) => v && v !== 'unknown');

    return `
      <article class="ob-card ob-stack">
        ${obs.photo_url
          ? `<img src="${escapeHtml(obs.photo_url)}" alt="" style="width:100%;height:140px;object-fit:cover;border-radius:var(--ob-radius-md);" />`
          : ''}
        ${scientificName ? '' : `<h3 class="ob-card__title" style="margin:0;">${escapeHtml(obs.species?.common_name || 'Unknown species')}</h3>`}
        <p class="ob-card__body ob-text-sm" style="margin:0;">${detectionPrefix}${escapeHtml(dateLabel)}</p>
        <p class="ob-text-muted ob-text-sm" style="margin:0;">${escapeHtml(obs.location_name || 'location not set')}</p>
        ${obs.notes ? `<p class="ob-text-sm" style="margin:0;">${escapeHtml(obs.notes)}</p>` : ''}
        <div class="ob-cluster">
          ${tags.map((t) => `<span class="ob-tag">${escapeHtml(t)}</span>`).join('')}
          <span class="ob-tag ob-tag--info">${escapeHtml(obs.source)}</span>
        </div>
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="edit" data-observation-id="${escapeHtml(obs.id)}" style="align-self:flex-start;">Edit</button>
      </article>
    `;
  }

  function renderEditForm(obs) {
    const v = state.editValues;
    const options = (opts, selected) => opts
      .map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`)
      .join('');

    return `
      <article class="ob-card">
        <form class="ob-stack" data-role="edit-form" data-observation-id="${escapeHtml(obs.id)}">
          <div class="ob-field">
            <label class="ob-label" for="edit-observed-at">Date seen</label>
            <input id="edit-observed-at" type="datetime-local" class="ob-input" value="${escapeHtml(v.observedAt)}" required />
          </div>
          <div class="ob-field">
            <label class="ob-label" for="edit-location">Location</label>
            <input id="edit-location" type="text" class="ob-input" value="${escapeHtml(v.locationName)}" />
          </div>
          <div class="ob-grid" style="--ob-grid-min: 140px;">
            <div class="ob-field">
              <label class="ob-label" for="edit-sex">Male / female</label>
              <select id="edit-sex" class="ob-select">${options(SEX_OPTIONS, v.sex)}</select>
            </div>
            <div class="ob-field">
              <label class="ob-label" for="edit-life-stage">Life stage</label>
              <select id="edit-life-stage" class="ob-select">${options(LIFE_STAGE_OPTIONS, v.lifeStage)}</select>
            </div>
            <div class="ob-field">
              <label class="ob-label" for="edit-detection">Sight or sound</label>
              <select id="edit-detection" class="ob-select">${options(DETECTION_OPTIONS, v.detectionType)}</select>
            </div>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="edit-photo">Photo</label>
            <input id="edit-photo" type="file" accept="image/*" class="ob-input" />
            <div data-role="edit-photo-status">${renderEditPhotoStatusHtml()}</div>
            <p class="ob-hint">JPEG, PNG, WebP, or GIF, up to 8 MB.</p>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="edit-notes">Notes</label>
            <textarea id="edit-notes" class="ob-textarea">${escapeHtml(v.notes)}</textarea>
          </div>
          ${state.saveError ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.saveError)}</div>` : ''}
          <div class="ob-cluster">
            <button type="submit" class="ob-btn ob-btn--primary ob-btn--sm" data-role="edit-submit-btn" ${state.saving || state.photoUploadState === 'uploading' ? 'disabled' : ''}>${state.saving ? 'Saving…' : state.photoUploadState === 'uploading' ? 'Uploading photo…' : 'Save'}</button>
            <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="cancel-edit" ${state.saving ? 'disabled' : ''}>Cancel</button>
          </div>
        </form>
      </article>
    `;
  }

  // ---- Wiring -------------------------------------------------------------

  function wire() {
    container.querySelectorAll('[data-action="edit"]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const obs = state.allObservations.find((o) => o.id === btn.dataset.observationId);
        if (obs) startEdit(obs);
      });
    });

    const form = container.querySelector('[data-role="edit-form"]');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (state.photoUploadState === 'uploading') return; // shouldn't happen — submit button is disabled — but belt and suspenders
        saveEdit(form.dataset.observationId, form);
      });
      form.querySelector('[data-action="cancel-edit"]')?.addEventListener('click', () => cancelEdit());
      wireEditPhotoInput(form);
    }

    wireFilterBar();
  }

  function wireFilterBar() {
    container.querySelectorAll('[data-view-mode]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.viewMode = btn.dataset.viewMode;
        render();
      });
    });

    const dateFrom = container.querySelector('#date-from');
    dateFrom?.addEventListener('change', () => {
      state.dateFrom = dateFrom.value;
      render();
    });

    const dateTo = container.querySelector('#date-to');
    dateTo?.addEventListener('change', () => {
      state.dateTo = dateTo.value;
      render();
    });

    const speciesFilter = container.querySelector('#species-filter');
    speciesFilter?.addEventListener('change', () => {
      state.speciesFilter = speciesFilter.value;
      render();
    });

    container.querySelector('[data-action="clear-filters"]')?.addEventListener('click', () => {
      state.dateFrom = '';
      state.dateTo = '';
      state.speciesFilter = '';
      render();
    });
  }
}

// `<input type="datetime-local">` wants local "YYYY-MM-DDTHH:mm", not an ISO
// string — same conversion AddObservation's field-notes step does in reverse.
function toDatetimeLocalValue(isoString) {
  const d = new Date(isoString);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
