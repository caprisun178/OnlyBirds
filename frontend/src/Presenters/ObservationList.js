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
  const { onNavigate, scientificName = null, commonName = null, region = null, regionLabel = null } = props;

  const state = {
    loading: true,
    error: null,
    observations: [],
    editingId: null, // id of the observation currently being edited, or null
    editValues: null,
    saving: false,
    saveError: null,
    photoUploadState: 'idle', // 'idle' | 'uploading' | 'done' | 'error'
    photoUploadError: null,
  };

  render();
  loadObservations();

  async function loadObservations() {
    state.loading = true;
    state.error = null;
    render();
    try {
      const all = await observationService.getSortedObservations(userId);
      state.observations = scientificName
        ? all.filter((obs) => obs.species?.scientific_name === scientificName)
        : all;
    } catch (err) {
      state.error = err.message || 'Could not load your observation log.';
      state.observations = [];
    } finally {
      state.loading = false;
      render();
    }
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
      const index = state.observations.findIndex((o) => o.id === observationId);
      if (index !== -1) state.observations[index] = updated;
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
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back" style="align-self:flex-start;">← Back to ${scientificName ? 'life list' : 'home'}</button>` : ''}
        <h1>${scientificName ? escapeHtml(commonName || scientificName) : 'My observations'}</h1>
        ${scientificName ? `<p class="ob-text-muted ob-text-sm" style="margin:0;"><em>${escapeHtml(scientificName)}</em></p>` : ''}
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : renderBody()}
      </div>
    `;
    if (onNavigate) {
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
    if (state.observations.length === 0) {
      const message = scientificName
        ? `You haven't logged any observations of ${escapeHtml(commonName || scientificName)} yet.`
        : "You haven't logged any observations yet.";
      return `<div class="ob-card ob-text-center"><p class="ob-card__body">${message}</p></div>`;
    }
    return `
      ${renderFirstObserved()}
      <div class="ob-stack">${state.observations.map(renderObservationCard).join('')}</div>
    `;
  }

  function renderFirstObserved() {
    const earliest = state.observations.reduce((min, obs) => (
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

  function renderObservationCard(obs) {
    if (state.editingId === obs.id) return renderEditForm(obs);

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
        const obs = state.observations.find((o) => o.id === btn.dataset.observationId);
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
  }
}

// `<input type="datetime-local">` wants local "YYYY-MM-DDTHH:mm", not an ISO
// string — same conversion AddObservation's field-notes step does in reverse.
function toDatetimeLocalValue(isoString) {
  const d = new Date(isoString);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
