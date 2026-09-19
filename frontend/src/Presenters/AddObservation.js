// Presenters/AddObservation.js — the Add Observation wizard.
//
// Order (per the current build): describe the bird -> pick which of 6 photos
// matches what you saw -> confirm -> field notes (date, location, sex, life
// stage, photo, notes) -> submit. See docs/features/add-observation.md.
//
//   import { mount } from './Presenters/AddObservation.js';
//   mount(document.getElementById('app'), { userId: 'u1' });
//
// If no `userId` prop is given, falls back to the test profile
// (testData/testProfile.js) so this screen works before real auth/profile
// (user-profiles.md) exists.

import { identifyService } from '../Services/identify.js';
import { speciesService } from '../Services/species.js';
import { observationService } from '../Services/observations.js';
import { uploadsService } from '../Services/uploads.js';
import { geocodingService } from '../Services/geocoding.js';
import { getCurrentUser } from '../testData/testProfile.js';
import { renderCandidateList, escapeHtml } from '../Components/CandidateList.js';
import { mountLocationPicker } from '../Components/LocationPicker.js';

const STEP = {
  DESCRIBE: 'describe',
  CANDIDATES: 'candidates',
  MANUAL_SEARCH: 'manualSearch',
  FIELD_NOTES: 'fieldNotes',
  DONE: 'done',
};

export function mount(container, props = {}) {
  const userId = props.userId || getCurrentUser().id;

  // The map is a live widget, not markup rebuilt from `state` — it lives
  // outside state and is only ever touched by the field-notes wiring below.
  let mapController = null;
  // Bumped on every pin move; a reverse-geocode response only gets applied
  // if it's still the most recent one requested, so a slower response from
  // an earlier click can't overwrite a faster one from a later click.
  let positionRequestId = 0;

  const state = {
    step: STEP.DESCRIBE,
    loading: false,
    error: null,

    descriptionText: '',
    hints: { size: '', color: '', habitat: '' },
    sense: 'sight', // 'sight' ("I saw it") | 'sound' ("I heard it") — decides whether candidates get an audio player

    identificationId: null,
    candidates: [],
    selectedCode: null,
    feedback: null, // { tone: 'success'|'warning'|'info', message }

    manualQuery: '',
    manualResults: [],

    confirmedSpecies: null, // { commonName, scientificName }

    fieldNotes: {
      observedAt: '',
      locationName: '',
      lat: null,
      lng: null,
      sex: '',
      lifeStage: '',
      notes: '',
      photoDataUrl: null, // local preview only, never sent to the API
      photoUrl: null, // set once the upload to object storage succeeds
    },
    photoUploadState: 'idle', // 'idle' | 'uploading' | 'done' | 'error'
    photoUploadError: null,

    result: null, // { observation, isNewSpecies }
  };

  render();

  function render() {
    container.innerHTML = `
      <div class="ob-stack">
        <h1>Add an observation</h1>
        ${renderStepper()}
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${renderStep()}
      </div>
    `;
    wireStep();
  }

  function renderStepper() {
    const labels = [
      [STEP.DESCRIBE, 'Describe'],
      [STEP.CANDIDATES, 'Pick a match'],
      [STEP.FIELD_NOTES, 'Field notes'],
      [STEP.DONE, 'Done'],
    ];
    const activeIndex = labels.findIndex(([key]) => key === state.step);
    return `
      <div class="ob-cluster ob-text-sm">
        ${labels.map(([key, label], i) => `
          <span class="ob-tag ${i === activeIndex ? 'ob-tag--info' : i < activeIndex ? 'ob-tag--success' : ''}">${i + 1}. ${label}</span>
        `).join('')}
      </div>
    `;
  }

  function renderStep() {
    if (state.loading) {
      return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
    }
    switch (state.step) {
      case STEP.DESCRIBE:
        return renderDescribeStep();
      case STEP.CANDIDATES:
        return renderCandidatesStep();
      case STEP.MANUAL_SEARCH:
        return renderManualSearchStep();
      case STEP.FIELD_NOTES:
        return renderFieldNotesStep();
      case STEP.DONE:
        return renderDoneStep();
      default:
        return '';
    }
  }

  // ---- Step 1: describe -----------------------------------------------

  function renderDescribeStep() {
    return `
      <form class="ob-card ob-stack" data-form="describe">
        <div class="ob-field">
          <label class="ob-label">Did you see it or hear it?</label>
          <div class="ob-cluster" role="radiogroup" aria-label="Did you see it or hear it?">
            <button type="button" class="ob-btn ob-btn--sm ${state.sense === 'sight' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-sense="sight" role="radio" aria-checked="${state.sense === 'sight'}">👀 I saw it</button>
            <button type="button" class="ob-btn ob-btn--sm ${state.sense === 'sound' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-sense="sound" role="radio" aria-checked="${state.sense === 'sound'}">🔊 I heard it</button>
          </div>
        </div>
        <div class="ob-field">
          <label class="ob-label" for="description">${state.sense === 'sound' ? 'What did you hear?' : 'What did you see?'}</label>
          <textarea id="description" class="ob-textarea" placeholder="${state.sense === 'sound'
            ? "e.g. a loud harsh call from a tree near the water, or straight up 'a blue jay'"
            : "e.g. a small brown streaky bird with a thin beak near the reeds, or straight up 'a blue jay'"}">${escapeHtml(state.descriptionText)}</textarea>
          <p class="ob-hint">${state.sense === 'sound'
            ? "Be as specific as you can — an exact name works too. We'll show you recordings to confirm either way."
            : "Be as specific as you can — an exact name works too. We'll show you photos to confirm either way."}</p>
        </div>
        <div class="ob-grid" style="--ob-grid-min: 160px;">
          <div class="ob-field">
            <label class="ob-label" for="hint-size">Size (optional)</label>
            <select id="hint-size" class="ob-select">
              <option value="">Not sure</option>
              <option value="small">Small</option>
              <option value="medium">Medium</option>
              <option value="large">Large</option>
            </select>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="hint-color">Main color (optional)</label>
            <input id="hint-color" class="ob-input" placeholder="e.g. blue, brown, yellow" value="${escapeHtml(state.hints.color)}" />
          </div>
          <div class="ob-field">
            <label class="ob-label" for="hint-habitat">Habitat (optional)</label>
            <input id="hint-habitat" class="ob-input" placeholder="e.g. backyard, wetland" value="${escapeHtml(state.hints.habitat)}" />
          </div>
        </div>
        <button type="submit" class="ob-btn ob-btn--primary ob-btn--block">Show me possible matches</button>
      </form>
    `;
  }

  function wireDescribeStep() {
    const form = container.querySelector('[data-form="describe"]');
    if (!form) return;

    form.querySelectorAll('[data-sense]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.sense = btn.dataset.sense;
        state.descriptionText = form.querySelector('#description').value; // preserve what they'd typed
        render();
      });
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      state.descriptionText = form.querySelector('#description').value;
      state.hints = {
        size: form.querySelector('#hint-size').value,
        color: form.querySelector('#hint-color').value,
        habitat: form.querySelector('#hint-habitat').value,
      };

      state.error = null;
      state.loading = true;
      render();
      try {
        const response = await identifyService.describe(state.descriptionText, state.hints, state.sense);
        state.identificationId = response.identification_id;
        state.candidates = response.candidates;
        state.selectedCode = null;
        state.feedback = null;
        state.step = STEP.CANDIDATES;
      } catch (err) {
        state.error = err.message || 'Could not get suggestions. Try describing it differently.';
      } finally {
        state.loading = false;
        render();
      }
    });
  }

  // ---- Step 2: candidates ----------------------------------------------

  function renderCandidatesStep() {
    return `
      <div class="ob-stack">
        <div class="ob-card ob-card--flat">
          <p class="ob-card__body">${state.sense === 'sound' ? 'Which one did you hear?' : 'Which one did you see?'}</p>
        </div>
        ${state.feedback ? `<div class="ob-alert ob-alert--${state.feedback.tone}">${escapeHtml(state.feedback.message)}</div>` : ''}
        ${renderCandidateList(state.candidates, state.selectedCode, state.sense)}
        <div class="ob-cluster">
          <button type="button" class="ob-btn ob-btn--ghost" data-action="back-to-describe">Start over</button>
          <button type="button" class="ob-btn ob-btn--subtle" data-action="none-match">None of these match</button>
        </div>
      </div>
    `;
  }

  function wireCandidatesStep() {
    const grid = container.querySelector('[data-role="candidate-grid"]');
    if (grid) {
      // Cards are div[role="button"], not real <button>s — an <audio controls>
      // player can't legally nest inside a real button (see CandidateList.js) —
      // so clicks and Enter/Space both need wiring by hand here.
      grid.querySelectorAll('[data-species-code]').forEach((card) => {
        card.addEventListener('click', () => handleCandidatePick(card.dataset.speciesCode));
        card.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleCandidatePick(card.dataset.speciesCode);
          }
        });
      });
      // Interacting with a candidate's audio player shouldn't also select the card.
      grid.querySelectorAll('audio').forEach((audioEl) => {
        audioEl.addEventListener('click', (e) => e.stopPropagation());
        audioEl.addEventListener('keydown', (e) => e.stopPropagation());
      });
    }
    const backBtn = container.querySelector('[data-action="back-to-describe"]');
    if (backBtn) backBtn.addEventListener('click', () => { state.step = STEP.DESCRIBE; state.feedback = null; render(); });

    const noneBtn = container.querySelector('[data-action="none-match"]');
    if (noneBtn) noneBtn.addEventListener('click', () => handleNoneMatch());
  }

  async function handleCandidatePick(speciesCode) {
    state.selectedCode = speciesCode;
    state.error = null;
    state.loading = true;
    render();
    try {
      const result = await identifyService.selectCandidate(state.identificationId, speciesCode);
      const lookAgainHint = state.sense === 'sound' ? 'take another listen' : 'take another look at the photos';
      if (result.outcome === 'correct') {
        state.confirmedSpecies = {
          commonName: result.chosen_species.common_name,
          scientificName: result.chosen_species.scientific_name,
        };
        state.feedback = { tone: 'success', message: `That's a ${result.chosen_species.common_name}! Adding it to your notes.` };
        state.step = STEP.FIELD_NOTES;
      } else if (result.outcome === 'incorrect') {
        state.confirmedSpecies = null;
        state.feedback = {
          tone: 'warning',
          message: `That's actually a ${result.chosen_species.common_name} — ${lookAgainHint}, or search for something else.`,
        };
      } else {
        // unconfirmed: no known target, so trust the pick.
        state.confirmedSpecies = {
          commonName: result.chosen_species.common_name,
          scientificName: result.chosen_species.scientific_name,
        };
        state.feedback = { tone: 'info', message: `Got it — logging this as a ${result.chosen_species.common_name}.` };
        state.step = STEP.FIELD_NOTES;
      }
    } catch (err) {
      state.error = err.message || 'Could not record your pick. Please try again.';
      state.selectedCode = null;
    } finally {
      state.loading = false;
      render();
    }
  }

  async function handleNoneMatch() {
    state.error = null;
    state.loading = true;
    render();
    try {
      await identifyService.selectCandidate(state.identificationId, null);
    } catch (err) {
      // Non-fatal — the manual search fallback still works even if this fails.
    } finally {
      state.loading = false;
      state.step = STEP.MANUAL_SEARCH;
      render();
    }
  }

  // ---- Manual fallback search -------------------------------------------

  function renderManualSearchStep() {
    return `
      <div class="ob-card ob-stack">
        <form class="ob-cluster" data-form="manual-search">
          <input class="ob-input" style="flex:1" placeholder="Search by name" value="${escapeHtml(state.manualQuery)}" data-field="manual-query" />
          <button type="submit" class="ob-btn ob-btn--primary">Search</button>
        </form>
        <div class="ob-stack" data-role="manual-results">
          ${state.manualResults.length === 0
            ? '<p class="ob-text-muted ob-text-sm">Search for the species you saw.</p>'
            : state.manualResults.map((s) => `
              <button type="button" class="ob-btn ob-btn--ghost ob-btn--block" data-common-name="${escapeHtml(s.common_name || '')}" data-scientific-name="${escapeHtml(s.scientific_name || '')}">
                ${escapeHtml(s.common_name || s.scientific_name)} <span class="ob-text-muted">(${escapeHtml(s.scientific_name || '')})</span>
              </button>
            `).join('')}
        </div>
        <button type="button" class="ob-btn ob-btn--subtle" data-action="back-to-candidates">Back to photos</button>
      </div>
    `;
  }

  function wireManualSearchStep() {
    const form = container.querySelector('[data-form="manual-search"]');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        state.manualQuery = form.querySelector('[data-field="manual-query"]').value;
        state.error = null;
        state.loading = true;
        render();
        try {
          state.manualResults = await speciesService.search(state.manualQuery);
        } catch (err) {
          state.error = 'Search failed. Try again in a moment.';
          state.manualResults = [];
        } finally {
          state.loading = false;
          render();
        }
      });
    }

    container.querySelectorAll('[data-common-name]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.confirmedSpecies = {
          commonName: btn.dataset.commonName || btn.dataset.scientificName,
          scientificName: btn.dataset.scientificName,
        };
        state.step = STEP.FIELD_NOTES;
        render();
      });
    });

    const backBtn = container.querySelector('[data-action="back-to-candidates"]');
    if (backBtn) backBtn.addEventListener('click', () => { state.step = STEP.CANDIDATES; render(); });
  }

  // ---- Step 3: field notes ----------------------------------------------

  function renderFieldNotesStep() {
    const fn = state.fieldNotes;
    return `
      <form class="ob-card ob-stack" data-form="field-notes">
        <div class="ob-alert ob-alert--success">
          Confirmed: ${escapeHtml(state.confirmedSpecies.commonName)}
          <span class="ob-tag" style="margin-left: var(--ob-space-2);">${state.sense === 'sound' ? '🔊 Heard' : '👀 Seen'}</span>
        </div>

        <div class="ob-field">
          <label class="ob-label" for="observed-at">Date &amp; time</label>
          <input id="observed-at" type="datetime-local" class="ob-input" value="${escapeHtml(fn.observedAt)}" required />
        </div>

        <div class="ob-field">
          <label class="ob-label" for="address-search">Location</label>
          <div class="ob-cluster">
            <input id="address-search" class="ob-input" style="flex:1" placeholder="Search for an address or place" />
            <button type="button" class="ob-btn ob-btn--ghost" data-action="search-address">Search</button>
          </div>
          <div data-role="address-results" class="ob-stack" style="--ob-stack-gap: var(--ob-space-1);"></div>
          <div data-role="location-map" style="height: 320px; border-radius: var(--ob-radius-md); overflow: hidden;"></div>
          <p class="ob-hint" data-role="pin-status">${renderPinStatusText(fn)}</p>
          <input id="location-name" class="ob-input" placeholder='Label for this sighting, e.g. "Discovery Park, Seattle"' value="${escapeHtml(fn.locationName)}" />
          <p class="ob-hint">Map and address search data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors.</p>
        </div>

        <div class="ob-grid" style="--ob-grid-min: 220px;">
          <div class="ob-field">
            <label class="ob-label" for="sex">Male / female</label>
            <select id="sex" class="ob-select">
              <option value="">Not sure</option>
              <option value="male" ${fn.sex === 'male' ? 'selected' : ''}>Male</option>
              <option value="female" ${fn.sex === 'female' ? 'selected' : ''}>Female</option>
              <option value="unknown" ${fn.sex === 'unknown' ? 'selected' : ''}>Unknown</option>
            </select>
          </div>
          <div class="ob-field">
            <label class="ob-label" for="life-stage">Life stage</label>
            <select id="life-stage" class="ob-select">
              <option value="">Not sure</option>
              <option value="adult" ${fn.lifeStage === 'adult' ? 'selected' : ''}>Adult</option>
              <option value="juvenile" ${fn.lifeStage === 'juvenile' ? 'selected' : ''}>Juvenile</option>
              <option value="fledgling" ${fn.lifeStage === 'fledgling' ? 'selected' : ''}>Fledgling</option>
              <option value="unknown" ${fn.lifeStage === 'unknown' ? 'selected' : ''}>Unknown</option>
            </select>
          </div>
        </div>

        <div class="ob-field">
          <label class="ob-label" for="photo">Photo (optional)</label>
          <input id="photo" type="file" accept="image/*" class="ob-input" />
          <div data-role="photo-status">${renderPhotoStatusHtml()}</div>
          <p class="ob-hint">JPEG, PNG, WebP, or GIF, up to 8 MB.</p>
        </div>

        <div class="ob-field">
          <label class="ob-label" for="notes">Notes</label>
          <textarea id="notes" class="ob-textarea" placeholder="What was it doing? Anything else memorable?">${escapeHtml(fn.notes)}</textarea>
        </div>

        <button type="submit" class="ob-btn ob-btn--primary ob-btn--block" data-role="submit-btn" ${state.photoUploadState === 'uploading' ? 'disabled' : ''}>
          ${state.photoUploadState === 'uploading' ? 'Uploading photo…' : 'Log this observation'}
        </button>
      </form>
    `;
  }

  function renderPinStatusText(fn) {
    return fn.lat != null && fn.lng != null
      ? `Pin dropped at ${fn.lat.toFixed(5)}, ${fn.lng.toFixed(5)} — click the map again to move it.`
      : 'Search for a place above, or click the map to drop a pin for exactly where you saw it.';
  }

  function renderPhotoStatusHtml() {
    const fn = state.fieldNotes;
    return `
      ${fn.photoDataUrl ? `<img src="${fn.photoDataUrl}" alt="Uploaded preview" style="max-width:220px;border-radius:var(--ob-radius-md);" />` : ''}
      ${state.photoUploadState === 'uploading' ? '<p class="ob-hint">Uploading photo…</p>' : ''}
      ${state.photoUploadState === 'error' ? `<div class="ob-alert ob-alert--warning">${escapeHtml(state.photoUploadError)}</div>` : ''}
    `;
  }

  // Reads the form's current values into state.fieldNotes. Called before any
  // full re-render triggered mid-edit (e.g. submitting) so that rebuilding
  // the form's HTML from state doesn't blank out fields the user already
  // typed into. lat/lng aren't form inputs — the map keeps those in state
  // directly via handleMapPositionChange, below.
  function captureFieldNotesInputs(form) {
    state.fieldNotes.observedAt = form.querySelector('#observed-at').value;
    state.fieldNotes.locationName = form.querySelector('#location-name').value;
    state.fieldNotes.sex = form.querySelector('#sex').value;
    state.fieldNotes.lifeStage = form.querySelector('#life-stage').value;
    state.fieldNotes.notes = form.querySelector('#notes').value;
  }

  function wireFieldNotesStep() {
    const form = container.querySelector('[data-form="field-notes"]');
    if (!form) return;

    wireLocationPicker(form);
    wirePhotoInput(form);
    wireFieldNotesSubmit(form);
  }

  // ---- Location: address search + click-to-drop-pin map -----------------

  async function wireLocationPicker(form) {
    const mapEl = form.querySelector('[data-role="location-map"]');
    const fn = state.fieldNotes;

    mapController?.destroy();
    mapController = null;
    try {
      mapController = await mountLocationPicker(mapEl, {
        initialLatLng: fn.lat != null && fn.lng != null ? [fn.lat, fn.lng] : undefined,
        onPositionChange: (lat, lng) => handleMapPositionChange(form, lat, lng),
      });
    } catch (err) {
      mapEl.innerHTML = `<div class="ob-alert ob-alert--warning">${escapeHtml(err.message || 'Could not load the map.')}</div>`;
    }

    const searchInput = form.querySelector('#address-search');
    const resultsEl = form.querySelector('[data-role="address-results"]');

    async function runAddressSearch() {
      const query = searchInput.value.trim();
      if (!query) return;
      resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">Searching…</p>';
      let results;
      try {
        results = await geocodingService.search(query);
      } catch (err) {
        resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">Search failed. Try again in a moment.</p>';
        return;
      }
      if (results.length === 0) {
        resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">No matches — try a different search, or just click the map.</p>';
        return;
      }
      resultsEl.innerHTML = results.map((r, i) => `
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--block ob-text-sm" style="justify-content:flex-start;" data-result-index="${i}">${escapeHtml(r.display_name)}</button>
      `).join('');
      resultsEl.querySelectorAll('[data-result-index]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const picked = results[Number(btn.dataset.resultIndex)];
          mapController?.setView(picked.lat, picked.lng);
          handleMapPositionChange(form, picked.lat, picked.lng, picked.display_name);
          resultsEl.innerHTML = '';
          searchInput.value = '';
        });
      });
    }

    form.querySelector('[data-action="search-address"]').addEventListener('click', runAddressSearch);
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runAddressSearch();
      }
    });
  }

  async function handleMapPositionChange(form, lat, lng, knownDisplayName) {
    const requestId = ++positionRequestId;

    state.fieldNotes.lat = lat;
    state.fieldNotes.lng = lng;
    const pinStatusEl = form.querySelector('[data-role="pin-status"]');
    if (pinStatusEl) pinStatusEl.textContent = renderPinStatusText(state.fieldNotes);

    const locationNameInput = form.querySelector('#location-name');
    if (!locationNameInput || locationNameInput.value.trim()) return; // don't clobber what they typed

    if (knownDisplayName) {
      locationNameInput.value = knownDisplayName;
      state.fieldNotes.locationName = knownDisplayName;
      return;
    }
    try {
      const place = await geocodingService.reverse(lat, lng);
      // A later click may have started (and even finished) its own
      // reverse-geocode while this one was in flight — if so, this response
      // is stale and must not overwrite the newer one.
      if (requestId !== positionRequestId) return;
      if (place && !locationNameInput.value.trim()) {
        locationNameInput.value = place.display_name;
        state.fieldNotes.locationName = place.display_name;
      }
    } catch (err) {
      // Non-fatal — the pin is still saved even without a readable label.
    }
  }

  // ---- Photo upload (targeted DOM updates so the map above never gets
  // torn down by a full re-render while the user is still on this step) ---

  function wirePhotoInput(form) {
    const photoInput = form.querySelector('#photo');
    photoInput.addEventListener('change', async () => {
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = () => {
        state.fieldNotes.photoDataUrl = reader.result;
        updatePhotoStatusDom(form);
      };
      reader.readAsDataURL(file);

      state.photoUploadState = 'uploading';
      state.photoUploadError = null;
      state.fieldNotes.photoUrl = null;
      updatePhotoStatusDom(form);
      updateSubmitButtonDom(form);
      try {
        state.fieldNotes.photoUrl = await uploadsService.uploadPhoto(file);
        state.photoUploadState = 'done';
      } catch (err) {
        state.photoUploadState = 'error';
        state.photoUploadError = `${err.message} You can still log this sighting without a photo.`;
      }
      updatePhotoStatusDom(form);
      updateSubmitButtonDom(form);
    });
  }

  function updatePhotoStatusDom(form) {
    const el = form.querySelector('[data-role="photo-status"]');
    if (el) el.innerHTML = renderPhotoStatusHtml();
  }

  function updateSubmitButtonDom(form) {
    const btn = form.querySelector('[data-role="submit-btn"]');
    if (!btn) return;
    const uploading = state.photoUploadState === 'uploading';
    btn.disabled = uploading;
    btn.textContent = uploading ? 'Uploading photo…' : 'Log this observation';
  }

  function wireFieldNotesSubmit(form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      captureFieldNotesInputs(form);
      mapController?.destroy();
      mapController = null;

      state.error = null;
      state.loading = true;
      render();
      try {
        state.result = await observationService.createFromWizard(userId, {
          species: state.confirmedSpecies,
          identificationId: state.identificationId,
          sense: state.sense,
          fieldNotes: {
            observedAt: state.fieldNotes.observedAt
              ? new Date(state.fieldNotes.observedAt).toISOString()
              : new Date().toISOString(),
            locationName: state.fieldNotes.locationName,
            lat: state.fieldNotes.lat,
            lng: state.fieldNotes.lng,
            photoUrl: state.fieldNotes.photoUrl,
            sex: state.fieldNotes.sex,
            lifeStage: state.fieldNotes.lifeStage,
            notes: state.fieldNotes.notes,
          },
        });
        state.step = STEP.DONE;
      } catch (err) {
        state.error = err.message || 'Could not save this observation. Please try again.';
      } finally {
        state.loading = false;
        render(); // if we're still on field notes (submit failed), the map remounts at the saved lat/lng
      }
    });
  }

  // ---- Step 4: done ------------------------------------------------------

  function renderDoneStep() {
    const { observation, isNewSpecies } = state.result;
    return `
      <div class="ob-card ob-stack ob-text-center">
        <h2>Observation logged!</h2>
        <p class="ob-card__body">
          ${observation.detection_type === 'sound' ? '🔊' : '👀'} ${escapeHtml(observation.species.common_name)} — ${escapeHtml(observation.location_name || 'location not set')}
        </p>
        ${isNewSpecies
          ? '<span class="ob-tag ob-tag--success">New life list species! (life list page coming soon)</span>'
          : '<span class="ob-tag ob-tag--info">Already on your life list</span>'}
        <button type="button" class="ob-btn ob-btn--primary" data-action="log-another">Log another sighting</button>
      </div>
    `;
  }

  function wireDoneStep() {
    const btn = container.querySelector('[data-action="log-another"]');
    if (btn) {
      btn.addEventListener('click', () => {
        mapController?.destroy();
        mapController = null;
        Object.assign(state, {
          step: STEP.DESCRIBE,
          descriptionText: '',
          hints: { size: '', color: '', habitat: '' },
          sense: 'sight',
          identificationId: null,
          candidates: [],
          selectedCode: null,
          feedback: null,
          manualQuery: '',
          manualResults: [],
          confirmedSpecies: null,
          fieldNotes: {
            observedAt: '', locationName: '', lat: null, lng: null, sex: '', lifeStage: '', notes: '',
            photoDataUrl: null, photoUrl: null,
          },
          photoUploadState: 'idle',
          photoUploadError: null,
          result: null,
          error: null,
        });
        render();
      });
    }
  }

  function wireStep() {
    switch (state.step) {
      case STEP.DESCRIBE:
        return wireDescribeStep();
      case STEP.CANDIDATES:
        return wireCandidatesStep();
      case STEP.MANUAL_SEARCH:
        return wireManualSearchStep();
      case STEP.FIELD_NOTES:
        return wireFieldNotesStep();
      case STEP.DONE:
        return wireDoneStep();
      default:
        return undefined;
    }
  }
}
