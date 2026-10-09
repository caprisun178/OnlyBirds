// Presenters/AddObservation.js — the Add Observation wizard.
//
// Order (per the current build): describe (when/where + sight-or-sound +
// upload a photo or describe it) -> identify (pick from suggested matches)
// -> confirm (when/where editable again, sex, life stage, photo, notes) ->
// submit. See docs/features/add-observation.md.
//
// When/where lives in the describe step, not a step of its own, so the
// backend can use it to reorder identify candidates toward what's actually
// been recorded in that region/day (Services/identify.js's `location` param
// — see docs/features/bird-id.md §7) before the bird is even confirmed. It
// shows up again, editable, in the confirm step in case it needs correcting
// before the final submit — both steps read/write the same
// `state.fieldNotes` fields, so nothing typed in one is lost in the other.
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
import { recentLocationsService } from '../Services/recentLocations.js';
import { getCurrentUser } from '../testData/testProfile.js';
import { renderCandidateList, escapeHtml } from '../Components/CandidateList.js';
import { mountLocationPicker } from '../Components/LocationPicker.js';

// After this many unsuccessful identify attempts (a wrong named-target pick,
// or "None of these match") in one wizard session, nudge toward Test Your
// Skill — see renderSkillSuggestion() below.
const FAILED_ATTEMPTS_BEFORE_SKILL_SUGGESTION = 3;

const STEP = {
  DESCRIBE: 'describe',
  CANDIDATES: 'candidates',
  MANUAL_SEARCH: 'manualSearch',
  FIELD_NOTES: 'fieldNotes',
  DONE: 'done',
};

const SEARCH_DEBOUNCE_MS = 350;
const MIN_SEARCH_LENGTH = 3; // matches geocodingService's own no-op threshold (Services/geocoding.js)

function nowForDatetimeLocal() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function mount(container, props = {}) {
  const userId = props.userId || getCurrentUser().id;
  const { onNavigate } = props; // optional — omitted when this screen is previewed standalone

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
    method: null, // 'describe' | 'photo' — which flow produced `candidates`; photo gets its own caution banner below
    failedAttempts: 0, // wrong named-target picks + "None of these match" clicks this session — see renderSkillSuggestion()

    manualQuery: '',
    manualResults: [],

    confirmedSpecies: null, // { commonName, scientificName }

    fieldNotes: {
      observedAt: nowForDatetimeLocal(),
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
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Add an observation</h1>
        ${renderStepper()}
        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${renderStep()}
      </div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]').addEventListener('click', () => {
        mapController?.destroy();
        mapController = null;
        onNavigate('home');
      });
    }
    wireStep();
  }

  function renderStepper() {
    const labels = [
      [STEP.DESCRIBE, 'Describe'],
      [STEP.CANDIDATES, 'Identify'],
      [STEP.FIELD_NOTES, 'Confirm'],
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

  // `observedAt` truncated to a plain date — eBird's regional checklist is
  // per calendar day, and the datetime-local value carries minutes the
  // backend has no use for (see Services/identify.js's `toRegional()`).
  function currentLocation() {
    const { lat, lng, observedAt } = state.fieldNotes;
    return { lat, lng, observedAt: observedAt ? observedAt.slice(0, 10) : undefined };
  }

  // ---- Step 1: describe (when/where + sight-or-sound + photo or text) ---
  // When/where lives here, not its own step, so it's known before
  // identification (the backend uses it to reorder candidates toward
  // what's regionally plausible — docs/features/bird-id.md §7). It's
  // editable again in Confirm (step 3) in case it needs correcting later —
  // both steps read/write the same `state.fieldNotes` fields.

  function renderDescribeStep() {
    const fn = state.fieldNotes;
    return `
      <form class="ob-card ob-stack" data-form="describe">
        <div class="ob-field">
          <label class="ob-label" for="observed-at">Date &amp; time</label>
          <input id="observed-at" type="datetime-local" class="ob-input" value="${escapeHtml(fn.observedAt)}" required />
        </div>
        <div class="ob-field">
          <label class="ob-label" for="address-search">Location (optional)</label>
          ${renderRecentLocationChips()}
          <input id="address-search" class="ob-input" autocomplete="off" placeholder="Search for an address or place" />
          <div data-role="address-results" class="ob-stack" style="--ob-stack-gap: var(--ob-space-1);"></div>
          <div data-role="location-map" style="height: 320px; border-radius: var(--ob-radius-md); overflow: hidden;"></div>
          <p class="ob-hint" data-role="pin-status">${renderPinStatusText(fn)}</p>
          <input id="location-name" class="ob-input" placeholder='Label for this sighting, e.g. "Discovery Park, Seattle"' value="${escapeHtml(fn.locationName)}" />
          <p class="ob-hint">Map tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>. Address search data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors. Knowing roughly where and when helps narrow the next step's match suggestions to birds actually recorded in your area around this time of year.</p>
        </div>
        <div class="ob-field">
          <label class="ob-label">Did you see it or hear it?</label>
          <div class="ob-cluster" role="radiogroup" aria-label="Did you see it or hear it?">
            <button type="button" class="ob-btn ob-btn--sm ${state.sense === 'sight' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-sense="sight" role="radio" aria-checked="${state.sense === 'sight'}">I saw it</button>
            <button type="button" class="ob-btn ob-btn--sm ${state.sense === 'sound' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-sense="sound" role="radio" aria-checked="${state.sense === 'sound'}">I heard it</button>
          </div>
        </div>
        <div class="ob-field">
          <label class="ob-label">Or upload a photo</label>
          <input type="file" id="identify-photo-input" accept="image/jpeg,image/png,image/webp,image/gif" style="display:none;" />
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="upload-photo" style="align-self:flex-start;">Upload a photo</button>
          <p class="ob-hint">Skips straight to picking a match — only covers common North American species, so an uncommon or regional bird may come back as a confident-looking but wrong match.</p>
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

    wireLocationPicker(form);

    form.querySelectorAll('[data-sense]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.sense = btn.dataset.sense;
        state.descriptionText = form.querySelector('#description').value; // preserve what they'd typed
        captureWhenWhereInputs(form); // same reason — a full re-render follows
        render();
      });
    });

    const photoInput = form.querySelector('#identify-photo-input');
    form.querySelector('[data-action="upload-photo"]')?.addEventListener('click', () => photoInput.click());
    photoInput.addEventListener('change', async () => {
      const file = photoInput.files[0];
      if (!file) return;

      captureWhenWhereInputs(form);
      state.error = null;
      state.loading = true;
      render();
      try {
        const response = await identifyService.identifyPhoto(file, currentLocation());
        state.identificationId = response.identification_id;
        state.candidates = response.candidates;
        state.method = 'photo';
        state.sense = 'sight'; // a photo is always "sight" — the candidates step's audio UI only shows for 'sound'
        state.selectedCode = null;
        state.feedback = null;
        mapController?.destroy();
        mapController = null;
        state.step = STEP.CANDIDATES;
        // The photo used to identify the bird is a reasonable default for
        // the observation's own photo too — upload it now, in the
        // background, so it's already attached by the time Confirm renders
        // instead of asking for the same file twice. Not awaited: the
        // wizard has already moved on to Identify by the time this settles.
        uploadIdentifyPhotoForObservation(file);
      } catch (err) {
        state.error = err.message || 'Could not identify that photo. Try again or describe it instead.';
      } finally {
        state.loading = false;
        render();
      }
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      captureWhenWhereInputs(form);
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
        const response = await identifyService.describe(state.descriptionText, state.hints, state.sense, currentLocation());
        state.identificationId = response.identification_id;
        state.candidates = response.candidates;
        state.method = 'describe';
        state.selectedCode = null;
        state.feedback = null;
        mapController?.destroy();
        mapController = null;
        state.step = STEP.CANDIDATES;
      } catch (err) {
        state.error = err.message || 'Could not get suggestions. Try describing it differently.';
      } finally {
        state.loading = false;
        render();
      }
    });
  }

  // Carries the photo used to identify the bird over to Confirm's own photo
  // field — same upload pipeline wirePhotoInput() uses, just triggered from
  // here instead of a direct file-input change. Fire-and-forget from the
  // caller's point of view; patches Confirm's photo status in place if the
  // user's already there by the time this resolves (same reasoning as
  // wirePhotoInput — a full render() would blow away anything else they're
  // mid-typing on that step). The user can still remove it
  // (wirePhotoRemoveButton) if they'd rather attach a different photo.
  async function uploadIdentifyPhotoForObservation(file) {
    const reader = new FileReader();
    reader.onload = () => {
      state.fieldNotes.photoDataUrl = reader.result;
      refreshConfirmPhotoStatus();
    };
    reader.readAsDataURL(file);

    state.photoUploadState = 'uploading';
    state.photoUploadError = null;
    refreshConfirmPhotoStatus();
    try {
      state.fieldNotes.photoUrl = await uploadsService.uploadPhoto(file);
      state.photoUploadState = 'done';
    } catch (err) {
      state.photoUploadState = 'error';
      state.photoUploadError = `${err.message} You can still log this sighting without a photo.`;
    }
    refreshConfirmPhotoStatus();
  }

  // Only Confirm's own photo-status subtree exists to patch while the user
  // is actually on that step — on any other step (Identify, most likely,
  // since this runs right after a photo identify) there's nothing to patch
  // and nothing to lose by not re-rendering; the carried-over photo is
  // already in `state.fieldNotes` and will render normally whenever Confirm
  // is actually reached.
  function refreshConfirmPhotoStatus() {
    const form = container.querySelector('[data-form="field-notes"]');
    if (!form) return;
    updatePhotoStatusDom(form);
    updateSubmitButtonDom(form);
  }

  // Reads the describe step's date/location inputs into state.fieldNotes —
  // same reasoning as captureFieldNotesInputs below: called right before
  // anything that might re-render or navigate away, so typed values survive.
  function captureWhenWhereInputs(form) {
    state.fieldNotes.observedAt = form.querySelector('#observed-at').value;
    state.fieldNotes.locationName = form.querySelector('#location-name').value;
  }

  // ---- Step 2: identify (pick from suggested matches) --------------------

  function renderCandidatesStep() {
    return `
      <div class="ob-stack">
        <div class="ob-card ob-card--flat">
          <p class="ob-card__body">${state.sense === 'sound' ? 'Which one did you hear?' : 'Which one did you see?'}</p>
        </div>
        ${state.feedback ? `<div class="ob-alert ob-alert--${state.feedback.tone}">${escapeHtml(state.feedback.message)}</div>` : ''}
        ${state.method === 'photo' ? `
          <div class="ob-alert ob-alert--warning">
            Photo matches only cover common North American species — if your
            bird isn't one of them, these can look confident and still be
            wrong. If none of these actually match, use "None of these
            match" below rather than picking the closest-looking one.
          </div>
        ` : ''}
        ${renderCandidateList(state.candidates, state.selectedCode, state.sense)}
        <div class="ob-cluster">
          <button type="button" class="ob-btn ob-btn--ghost" data-action="back-to-describe">Start over</button>
          <button type="button" class="ob-btn ob-btn--subtle" data-action="none-match">None of these match</button>
        </div>
        ${renderSkillSuggestion()}
      </div>
    `;
  }

  // After a few unsuccessful tries in one session (a wrong named-target
  // pick, or "None of these match" — see where state.failedAttempts is
  // incremented, below), nudge toward Test Your Skill rather than letting
  // someone just keep guessing. Shown here and on the manual-search
  // fallback, since either can be where a losing streak actually lands.
  function renderSkillSuggestion() {
    if (state.failedAttempts < FAILED_ATTEMPTS_BEFORE_SKILL_SUGGESTION) return '';
    return `
      <div class="ob-alert ob-alert--info">
        Having trouble identifying this one? Practicing with
        ${onNavigate
          ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="try-test-your-skill" style="margin:0 var(--ob-space-1);">Test Your Skill</button>'
          : ' Test Your Skill '}
        can help you get faster at spotting the differences between similar species.
      </div>
    `;
  }

  function wireSkillSuggestion() {
    container.querySelector('[data-action="try-test-your-skill"]')?.addEventListener('click', () => {
      onNavigate('test-your-skill');
    });
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
    if (backBtn) {
      // Deliberately does NOT reset failedAttempts — "Start over" means a
      // new description/photo, not a new bird, so a losing streak across
      // re-attempts should still add up to the skill suggestion rather than
      // resetting every time someone tries rephrasing their description.
      backBtn.addEventListener('click', () => { state.step = STEP.DESCRIBE; state.feedback = null; render(); });
    }

    const noneBtn = container.querySelector('[data-action="none-match"]');
    if (noneBtn) noneBtn.addEventListener('click', () => handleNoneMatch());

    wireSkillSuggestion();
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
        state.failedAttempts = 0;
      } else if (result.outcome === 'incorrect') {
        state.confirmedSpecies = null;
        state.feedback = {
          tone: 'warning',
          message: `That's actually a ${result.chosen_species.common_name} — ${lookAgainHint}, or search for something else.`,
        };
        state.failedAttempts += 1;
      } else {
        // unconfirmed: no known target, so trust the pick.
        state.confirmedSpecies = {
          commonName: result.chosen_species.common_name,
          scientificName: result.chosen_species.scientific_name,
        };
        state.feedback = { tone: 'info', message: `Got it — logging this as a ${result.chosen_species.common_name}.` };
        state.step = STEP.FIELD_NOTES;
        state.failedAttempts = 0;
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
    state.failedAttempts += 1;
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
        ${renderSkillSuggestion()}
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
        state.failedAttempts = 0;
        render();
      });
    });

    const backBtn = container.querySelector('[data-action="back-to-candidates"]');
    if (backBtn) backBtn.addEventListener('click', () => { state.step = STEP.CANDIDATES; render(); });

    wireSkillSuggestion();
  }

  // ---- Step 3: confirm (when/where again, sex, life stage, photo, notes) -

  function renderFieldNotesStep() {
    const fn = state.fieldNotes;
    return `
      <form class="ob-card ob-stack" data-form="field-notes">
        <div class="ob-alert ob-alert--success">
          Confirmed: ${escapeHtml(state.confirmedSpecies.commonName)}
          <span class="ob-tag" style="margin-left: var(--ob-space-2);">${state.sense === 'sound' ? 'Heard' : 'Seen'}</span>
        </div>

        <div class="ob-field">
          <label class="ob-label" for="observed-at">Date &amp; time</label>
          <input id="observed-at" type="datetime-local" class="ob-input" value="${escapeHtml(fn.observedAt)}" required />
        </div>

        <div class="ob-field">
          <label class="ob-label" for="address-search">Location</label>
          ${renderRecentLocationChips()}
          <input id="address-search" class="ob-input" autocomplete="off" placeholder="Search for an address or place" />
          <div data-role="address-results" class="ob-stack" style="--ob-stack-gap: var(--ob-space-1);"></div>
          <div data-role="location-map" style="height: 320px; border-radius: var(--ob-radius-md); overflow: hidden;"></div>
          <p class="ob-hint" data-role="pin-status">${renderPinStatusText(fn)}</p>
          <input id="location-name" class="ob-input" placeholder='Label for this sighting, e.g. "Discovery Park, Seattle"' value="${escapeHtml(fn.locationName)}" />
          <p class="ob-hint">Map tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>. Address search data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors.</p>
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
      ${fn.photoDataUrl ? `
        <div class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); align-items:flex-start;">
          <img src="${fn.photoDataUrl}" alt="Uploaded preview" style="max-width:220px;border-radius:var(--ob-radius-md);" />
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="remove-photo">Remove photo</button>
        </div>
      ` : ''}
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
    wirePhotoRemoveButton(form);
    wireFieldNotesSubmit(form);
  }

  // ---- Location: address search + click-to-drop-pin map -----------------

  // "Remember my favorite spots" — the last few distinct locations actually
  // used to log an observation (recentLocationsService.remember(), called
  // on successful submit below), offered as quick-select chips. Shown on
  // both Describe and Confirm, since both render this same location block.
  function renderRecentLocationChips() {
    const recents = recentLocationsService.list();
    if (recents.length === 0) return '';
    return `
      <div class="ob-cluster ob-text-sm" data-role="recent-locations" style="align-items:center;">
        <span class="ob-text-muted">Recent:</span>
        ${recents.map((loc, i) => `<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-recent-index="${i}">${escapeHtml(loc.locationName)}</button>`).join('')}
      </div>
    `;
  }

  function wireRecentLocations(form) {
    form.querySelectorAll('[data-recent-index]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const loc = recentLocationsService.list()[Number(btn.dataset.recentIndex)];
        if (!loc) return;
        const nameInput = form.querySelector('#location-name');
        // Clear first so handleMapPositionChange's "don't clobber what they
        // typed" guard (below) doesn't block filling in the recent spot's
        // label — clicking a recent chip is exactly the explicit intent
        // that guard is meant to defer to.
        if (nameInput) nameInput.value = '';
        mapController?.setView(loc.lat, loc.lng);
        handleMapPositionChange(form, loc.lat, loc.lng, loc.locationName);
      });
    });
  }

  async function wireLocationPicker(form) {
    const mapEl = form.querySelector('[data-role="location-map"]');
    const fn = state.fieldNotes;

    wireRecentLocations(form);

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
    // Debounced live suggestions as you type (same reasoning/pattern as
    // Explore Map's place search — ExploreMap.js#scheduleSearch()); Enter
    // bypasses the debounce. `searchRequestId` guards against an earlier,
    // slower response clobbering a newer one if they resolve out of order.
    let searchDebounceTimer = null;
    let searchRequestId = 0;

    async function runAddressSearch() {
      const query = searchInput.value.trim();
      if (!query) {
        resultsEl.innerHTML = '';
        return;
      }
      const requestId = (searchRequestId += 1);
      resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm"><span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Searching…</p>';
      let results;
      try {
        results = await geocodingService.search(query);
      } catch (err) {
        if (requestId !== searchRequestId) return;
        resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">Search failed. Try again in a moment.</p>';
        return;
      }
      if (requestId !== searchRequestId) return; // a newer search started since this one began
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

    searchInput.addEventListener('input', () => {
      clearTimeout(searchDebounceTimer);
      if (searchInput.value.trim().length < MIN_SEARCH_LENGTH) {
        searchRequestId += 1; // invalidate any in-flight fetch's result
        resultsEl.innerHTML = '';
        return;
      }
      searchDebounceTimer = setTimeout(runAddressSearch, SEARCH_DEBOUNCE_MS);
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        clearTimeout(searchDebounceTimer);
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
    wirePhotoRemoveButton(form); // the subtree above was just replaced — its "Remove photo" button needs rewiring
  }

  // Lets the user clear a selected/attached photo instead of being stuck
  // with it until final submit — covers both a photo picked directly on
  // this step and one carried over from the identify step's upload (see
  // uploadIdentifyPhotoForObservation() below), since both just populate
  // the same fieldNotes.photoDataUrl/photoUrl this button clears.
  function wirePhotoRemoveButton(form) {
    form.querySelector('[data-action="remove-photo"]')?.addEventListener('click', () => {
      state.fieldNotes.photoDataUrl = null;
      state.fieldNotes.photoUrl = null;
      state.photoUploadState = 'idle';
      state.photoUploadError = null;
      const photoInput = form.querySelector('#photo');
      if (photoInput) photoInput.value = ''; // so re-picking the same file still fires a change event
      updatePhotoStatusDom(form);
      updateSubmitButtonDom(form);
    });
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
        recentLocationsService.remember({
          lat: state.fieldNotes.lat,
          lng: state.fieldNotes.lng,
          locationName: state.fieldNotes.locationName,
        });
        state.step = STEP.DONE;
      } catch (err) {
        state.error = err.message || 'Could not save this observation. Please try again.';
      } finally {
        state.loading = false;
        render(); // if we're still on confirm (submit failed), the map remounts at the saved lat/lng
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
          ${escapeHtml(observation.species.common_name)} — ${escapeHtml(observation.location_name || 'location not set')}
        </p>
        ${isNewSpecies
          ? '<span class="ob-tag ob-tag--success">New life list species!</span>'
          : '<span class="ob-tag ob-tag--info">Already on your life list</span>'}
        <div class="ob-cluster" style="justify-content:center;">
          <button type="button" class="ob-btn ob-btn--primary" data-action="log-another">Log another sighting</button>
          ${onNavigate ? `
            <button type="button" class="ob-btn ob-btn--ghost" data-action="view-life-list">View life list</button>
            <button type="button" class="ob-btn ob-btn--ghost" data-action="view-observations">View my observations</button>
          ` : ''}
        </div>
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
          method: null,
          failedAttempts: 0,
          manualQuery: '',
          manualResults: [],
          confirmedSpecies: null,
          fieldNotes: {
            observedAt: nowForDatetimeLocal(), locationName: '', lat: null, lng: null, sex: '', lifeStage: '', notes: '',
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

    container.querySelector('[data-action="view-life-list"]')?.addEventListener('click', () => {
      onNavigate('life-list');
    });
    container.querySelector('[data-action="view-observations"]')?.addEventListener('click', () => {
      onNavigate('observation-log', { userId });
    });
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
