// Presenters/TestYourSkill.js — the Test Your Skill quiz screen. See
// docs/features/test-your-skill.md.
//
//   import { mount } from './Presenters/TestYourSkill.js';
//   mount(document.getElementById('app'));
//
// Nothing here is sent to the backend except "give me a question" —
// grading, the running score, and the current question are all plain local
// state, gone on refresh. That's the whole feature, deliberately: see the
// feature page for why no persistence is a scope decision, not a cut corner.
//
// Filters (added after the original no-filter version): "region" (reuses
// Life List's exact cascading country -> state/province -> county picker
// pattern and the same shared `/regions` endpoint, not a reimplementation)
// and "type" (a taxonomic family — warblers, corvids, owls, ...). Region
// comes first, both in the UI and in load order, because it drives type:
// changing it reloads the family options to whatever's actually on that
// region's checklist (see loadFilters()). Defaults to the signed-in user's
// own `users.default_region` (e.g. "US-NC") rather than "Anywhere" — see
// loadDefaultRegion() — falling back to "Anywhere" only if no profile/region
// is set yet, which is the original "random, any and all birds" behavior:
// region_code="world" with no family filter, confirmed live to cover the
// full ~10,800-species eBird taxonomy.

import { quizService } from '../Services/quiz.js';
import { speciesService } from '../Services/species.js';
import { escapeHtml } from '../Components/htmlUtils.js';

export function mount(container, props = {}) {
  const { onNavigate, userId = 'u1' } = props;

  const state = {
    mode: 'photo', // 'photo' | 'audio'
    loading: true,
    error: null,
    question: null, // { mode, photo_url, audio_url, attribution, choices, correct_scientific_name, correct_family }
    selectedAnswer: null, // the scientific_name picked, or null before answering
    revealed: false,
    // Full species profile(s) for the reveal — always the correct species;
    // also the picked species when wrong, for the two-panel "here's what you
    // picked vs. what it actually was" comparison. Each slot is `null` until
    // its own fetch resolves (`incorrect` stays `null` forever on a correct
    // answer — a right answer only needs the one panel); the two load and
    // render independently, not gated behind each other.
    revealProfiles: { correct: null, incorrect: null },
    revealLoading: { correct: false, incorrect: false },
    // Cumulative across mode/filter changes and across "Next question" —
    // deliberately not reset by any of those, since this is "how good am I
    // at birds this session," not a separate tally per setting. Reset to
    // 0/0 only by leaving and coming back (a fresh mount), which matches
    // "nothing is persisted" by construction.
    score: 0,
    totalAnswered: 0,

    // "Try another photo" — same question, a different reference image.
    // Real report that motivated this: a Seaside Sparrow question showed a
    // range map instead of a bird. Available any time there's a photo
    // question (not just after revealing), since the whole point is letting
    // someone move past a bad image *before* they have to guess from it.
    photoSwapping: false,
    photoSwapNotice: null,

    // "Type" filter — a taxonomic family, or null for "Any type."
    regionCode: 'world',
    regionLabel: 'Anywhere',
    family: null,
    familyOptions: [], // [{name, count}, ...] for the current regionCode
    familyOptionsLoading: false,

    // Region picker — cascading country -> state/province -> county, same
    // shape as LifeList.js's own (not reimplemented logic, just mirrored
    // UI, since this screen doesn't share LifeList's component).
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
  // The region must be resolved *before* the first filters/question fetch
  // — otherwise both would fire against the "world" default and then have
  // to redo themselves the moment the user's real default region arrives,
  // a visible flash from "Anywhere" to wherever they actually are.
  loadDefaultRegion().then(() => {
    loadFilters();
    loadQuestion();
  });

  async function loadDefaultRegion() {
    try {
      const code = await quizService.getDefaultRegion(userId);
      if (code && code !== 'world') {
        state.regionCode = code;
        state.regionLabel = await quizService.resolveRegionLabel(code);
      }
    } catch (err) {
      // No profile yet, or the fetch failed — stay at "world"/"Anywhere."
      // Not worth a page-level error for a default that simply didn't load.
    }
  }

  async function loadQuestion() {
    state.loading = true;
    state.error = null;
    state.question = null;
    state.selectedAnswer = null;
    state.revealed = false;
    state.photoSwapNotice = null;
    state.revealProfiles = { correct: null, incorrect: null };
    state.revealLoading = { correct: false, incorrect: false };
    render();
    try {
      state.question = await quizService.getQuestion(state.mode, {
        regionCode: state.regionCode,
        family: state.family,
      });
    } catch (err) {
      state.error = err.message || 'No birds matched that combination — try a broader filter.';
    } finally {
      state.loading = false;
      render();
    }
  }

  async function loadFilters() {
    state.familyOptionsLoading = true;
    render();
    try {
      state.familyOptions = await quizService.getFilters(state.regionCode);
      // The previously-picked family might not exist in the new region's
      // checklist (e.g. switching from "Anywhere" to a region with no owls)
      // — drop back to "Any type" rather than silently querying for a
      // filter that can't match anything there.
      if (state.family && !state.familyOptions.some((f) => f.name === state.family)) {
        state.family = null;
      }
    } catch (err) {
      state.familyOptions = []; // the type dropdown just shows "Any type" only — not worth a page-level error for this
    } finally {
      state.familyOptionsLoading = false;
      render();
    }
  }

  function switchMode(mode) {
    if (mode === state.mode) return;
    state.mode = mode;
    loadQuestion();
  }

  function switchFamily(family) {
    const next = family || null;
    if (next === state.family) return;
    state.family = next;
    loadQuestion();
  }

  function selectAnswer(scientificName) {
    if (state.revealed || !state.question) return; // already answered this one, or nothing to answer yet
    state.selectedAnswer = scientificName;
    state.revealed = true;
    state.totalAnswered += 1;
    if (scientificName === state.question.correct_scientific_name) {
      state.score += 1;
    }
    render();
    loadRevealProfiles();
  }

  function loadRevealProfiles() {
    const q = state.question;
    const correctChoice = q.choices.find((c) => c.scientific_name === q.correct_scientific_name);
    const wasCorrect = state.selectedAnswer === q.correct_scientific_name;
    const pickedChoice = wasCorrect ? null : q.choices.find((c) => c.scientific_name === state.selectedAnswer);

    // Each panel fetches and renders independently rather than both waiting
    // on a shared Promise.all — a slow/rate-limited Wikipedia lookup for one
    // panel (worst case ~30s, see species.py#_get_or_fetch_content) would
    // otherwise block a panel whose own fetch already finished from showing
    // anything at all.
    state.revealProfiles = { correct: null, incorrect: null };
    state.revealLoading = { correct: true, incorrect: Boolean(pickedChoice) };
    render();

    loadOnePanel('correct', correctChoice.scientific_name, correctChoice.common_name);
    if (pickedChoice) loadOnePanel('incorrect', pickedChoice.scientific_name, pickedChoice.common_name);
  }

  async function loadOnePanel(slot, scientificName, commonName) {
    try {
      state.revealProfiles[slot] = await speciesService.getProfile(scientificName, { commonName });
    } catch (err) {
      state.revealProfiles[slot] = null; // the plain correct/incorrect line above still shows either way
    } finally {
      state.revealLoading[slot] = false;
      render();
    }
  }

  async function tryAnotherPhoto() {
    if (!state.question || state.mode !== 'photo' || state.photoSwapping) return;
    const q = state.question;
    const correctCommonName = q.choices.find((c) => c.scientific_name === q.correct_scientific_name)?.common_name || '';
    state.photoSwapping = true;
    state.photoSwapNotice = null;
    render();
    try {
      const result = await quizService.getAnotherPhoto(q.correct_scientific_name, correctCommonName, q.photo_url);
      if (result.changed) {
        q.photo_url = result.photo_url;
        q.attribution = result.attribution;
      } else {
        state.photoSwapNotice = 'No other photo of this species is available right now.';
      }
    } catch (err) {
      state.photoSwapNotice = 'Could not load another photo — try again in a moment.';
    } finally {
      state.photoSwapping = false;
      render();
    }
  }

  // ---- Region picker (mirrors LifeList.js's own cascading picker) --------

  function togglePicker() {
    state.pickerOpen = !state.pickerOpen;
    render();
    if (state.pickerOpen && state.countries.length === 0) loadCountries();
  }

  async function loadCountries() {
    state.pickerLoading = true;
    render();
    try {
      state.countries = await quizService.getRegionOptions('world', 'country');
    } catch (err) {
      // Leave countries empty — the picker just shows no options to choose from.
    } finally {
      state.pickerLoading = false;
      render();
    }
  }

  function changeRegion(code, label) {
    state.regionCode = code;
    state.regionLabel = label;
    state.pickerOpen = false;
    state.family = null; // the old family filter may not exist in the new region — see loadFilters()
    render();
    loadFilters();
    loadQuestion();
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
        state.states = await quizService.getRegionOptions(state.pickerCountry, 'subnational1');
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
        state.counties = await quizService.getRegionOptions(state.pickerState, 'subnational2');
      } catch (err) {
        // Not every state has a county breakdown either — same deal.
      }
      render();
    });

    const countySelect = container.querySelector('#picker-county');
    countySelect?.addEventListener('change', () => {
      state.pickerCounty = countySelect.value;
    });

    container.querySelector('[data-action="apply-region"]')?.addEventListener('click', () => {
      const code = state.pickerCounty || state.pickerState || state.pickerCountry;
      if (!code) return;
      const label =
        state.counties.find((c) => c.code === code)?.name ||
        state.states.find((s) => s.code === code)?.name ||
        state.countries.find((c) => c.code === code)?.name ||
        code;
      changeRegion(code, label);
    });

    container.querySelector('[data-action="reset-region"]')?.addEventListener('click', () => {
      changeRegion('world', 'Anywhere');
    });
  }

  // ---- Render ---------------------------------------------------------------

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back-to-home" style="align-self:flex-start;">← Back to home</button>' : ''}
        <h1>Test your skill</h1>
        <p class="ob-text-muted">Real photos and real recordings, pulled fresh each time — nothing about your score is saved, so play as many rounds as you like.</p>

        <div class="ob-card ob-stack">
          <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
            <div class="ob-cluster" role="group" aria-label="Quiz mode">
              <button type="button" class="ob-btn ob-btn--sm ${state.mode === 'photo' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-mode="photo">By sight</button>
              <button type="button" class="ob-btn ob-btn--sm ${state.mode === 'audio' ? 'ob-btn--primary' : 'ob-btn--ghost'}" data-mode="audio">By ear</button>
            </div>
            <p class="ob-text-sm" style="margin: 0;">${state.totalAnswered === 0 ? 'No questions answered yet' : `${state.score} / ${state.totalAnswered} correct`}</p>
          </div>

          <div class="ob-cluster" style="align-items: flex-end;">
            <div class="ob-field">
              <span class="ob-label">Region</span>
              <button type="button" class="ob-btn ob-btn--ghost" data-action="toggle-picker">${escapeHtml(state.regionLabel)} — change</button>
            </div>
            <div class="ob-field">
              <label class="ob-label" for="family-filter">Type</label>
              <select id="family-filter" class="ob-select" ${state.familyOptionsLoading ? 'disabled' : ''}>
                <option value="">Any type</option>
                ${state.familyOptions.map((f) => `<option value="${escapeHtml(f.name)}" ${f.name === state.family ? 'selected' : ''}>${escapeHtml(f.name)} (${f.count})</option>`).join('')}
              </select>
            </div>
          </div>

          ${state.pickerOpen ? renderRegionPicker() : ''}
        </div>

        ${state.error ? `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>` : ''}
        ${state.loading ? renderLoading() : state.question ? renderQuestion() : ''}
      </div>
    `;
    if (onNavigate) {
      container.querySelector('[data-action="back-to-home"]')?.addEventListener('click', () => onNavigate('home'));
    }
    container.querySelectorAll('[data-mode]').forEach((btn) => {
      btn.addEventListener('click', () => switchMode(btn.dataset.mode));
    });
    container.querySelector('#family-filter')?.addEventListener('change', (e) => switchFamily(e.target.value));
    container.querySelector('[data-action="toggle-picker"]')?.addEventListener('click', togglePicker);
    wireRegionPicker();
    wireQuestion();
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
        <div class="ob-cluster">
          <button type="button" class="ob-btn ob-btn--primary ob-btn--sm" data-action="apply-region">Use this region</button>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="reset-region">Reset to anywhere</button>
        </div>
      </div>
    `;
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderQuestion() {
    const q = state.question;
    return `
      <div class="ob-card ob-stack">
        ${q.mode === 'photo'
          ? `<img src="${escapeHtml(q.photo_url)}" alt="Guess this bird" style="display:block; width:100%; height:360px; object-fit:contain; background:var(--ob-color-surface-alt); border-radius:var(--ob-radius-md);" />`
          : `<div class="ob-text-center" style="padding: var(--ob-space-5) 0;"><audio controls src="${escapeHtml(q.audio_url)}" style="width:100%; max-width:360px;"></audio></div>`}

        ${q.mode === 'photo'
          ? `
            <div class="ob-cluster" style="align-items: center; gap: var(--ob-space-2);">
              <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="try-another-photo" ${state.photoSwapping ? 'disabled' : ''}>
                ${state.photoSwapping ? 'Loading another photo…' : 'Not a clear photo? Try another'}
              </button>
              ${state.photoSwapNotice ? `<span class="ob-text-sm ob-text-muted">${escapeHtml(state.photoSwapNotice)}</span>` : ''}
            </div>
          `
          : ''}

        <div class="ob-grid" style="--ob-grid-min: 160px;">
          ${q.choices.map((c) => renderChoice(c)).join('')}
        </div>

        ${state.revealed ? renderReveal() : ''}
      </div>
    `;
  }

  function renderReveal() {
    const q = state.question;
    const wasCorrect = state.selectedAnswer === q.correct_scientific_name;
    return `
      <div class="ob-stack" style="gap: var(--ob-space-3);">
        <div class="ob-cluster" style="justify-content: space-between; align-items: center;">
          <p class="ob-text-sm" style="margin: 0;">
            ${wasCorrect ? '<strong>Correct!</strong>' : '<strong>Not quite.</strong>'}
          </p>
          <button type="button" class="ob-btn ob-btn--primary ob-btn--sm" data-action="next-question">Next question</button>
        </div>
        ${renderRevealProfiles(wasCorrect)}
      </div>
    `;
  }

  // One full profile when the answer was right — nothing to compare against.
  // Two side-by-side panels when it was wrong: "Your answer" first, then
  // "Correct answer" (per the order this was asked for) — same full profile
  // shape either way, image + call included for both sight and ear quizzes,
  // not just whichever medium the question itself used, so a miss on either
  // mode gives the full picture to learn from. Each panel loads and renders
  // independently (see loadOnePanel()) — a slow panel never blocks one
  // that's already resolved from showing up.
  function renderRevealProfiles(wasCorrect) {
    if (wasCorrect) {
      return renderProfilePanel('correct', 'About this species');
    }
    return `
      <div class="ob-grid" style="--ob-grid-min: 260px;">
        ${renderProfilePanel('incorrect', 'Your answer')}
        ${renderProfilePanel('correct', 'Correct answer')}
      </div>
    `;
  }

  function renderProfilePanel(slot, headingLabel) {
    if (state.revealLoading[slot]) return renderLoading();
    const profile = state.revealProfiles[slot];
    if (!profile) return '';
    // Both the correct and incorrect choices for this question came from the
    // same regional checklist the quiz is currently filtered to (see
    // quiz.py's `_filtered_pool()`) — so "recorded in {region}" is true for
    // either panel's species whenever a specific region is active. Not shown
    // for "Anywhere" (region_code "world"): true of literally every species,
    // so it wouldn't tell anyone anything.
    const regionNote = state.regionCode !== 'world' ? state.regionLabel : null;
    return `
      <div class="ob-card ob-card--flat ob-stack" style="gap: var(--ob-space-2);">
        <p class="ob-text-sm ob-text-muted" style="margin: 0; text-transform: uppercase; letter-spacing: 0.03em;">${escapeHtml(headingLabel)}</p>
        <img src="${escapeHtml(profile.photoUrl)}" alt="${escapeHtml(profile.commonName)}" style="display:block; width:100%; height:180px; object-fit:cover; border-radius:var(--ob-radius-md); background:var(--ob-color-surface-alt);" />
        <div>
          <p style="margin: 0;"><strong>${escapeHtml(profile.commonName)}</strong> <em class="ob-text-muted">${escapeHtml(profile.scientificName)}</em></p>
          ${profile.family ? `<p class="ob-text-sm ob-text-muted" style="margin: 0;">${escapeHtml(profile.family)}</p>` : ''}
        </div>
        ${profile.sexDifferences ? `<p class="ob-text-sm" style="margin: 0;"><strong>Description:</strong> ${escapeHtml(profile.sexDifferences)}</p>` : ''}
        ${profile.habitat ? `<p class="ob-text-sm" style="margin: 0;"><strong>Habitat:</strong> ${escapeHtml(profile.habitat)}</p>` : ''}
        ${profile.migration ? `<p class="ob-text-sm" style="margin: 0;"><strong>Range:</strong> ${escapeHtml(profile.migration)}</p>` : ''}
        ${regionNote ? `<p class="ob-text-sm" style="margin: 0;"><strong>Recorded in:</strong> ${escapeHtml(regionNote)}</p>` : ''}
        ${profile.about ? `<p class="ob-text-sm" style="margin: 0;">${escapeHtml(profile.about)}</p>` : ''}
        ${profile.aboutSourceUrl ? `<a href="${escapeHtml(profile.aboutSourceUrl)}" target="_blank" rel="noopener noreferrer" class="ob-text-sm">Read more on Wikipedia</a>` : ''}
        ${profile.audioUrl
          ? `
            <div>
              <p class="ob-text-sm" style="margin: 0 0 4px;"><strong>Call:</strong></p>
              <audio controls src="${escapeHtml(profile.audioUrl)}" style="width: 100%;"></audio>
              ${profile.audioAttribution ? `<p class="ob-text-sm ob-text-muted" style="margin: 4px 0 0;">${escapeHtml(profile.audioAttribution)}</p>` : ''}
            </div>
          `
          : '<p class="ob-text-sm ob-text-muted" style="margin: 0;">No recording available for this species.</p>'}
        ${profile.photoAttribution ? `<p class="ob-text-sm ob-text-muted" style="margin: 0;">Photo: ${escapeHtml(profile.photoAttribution)}</p>` : ''}
      </div>
    `;
  }

  function renderChoice(choice) {
    const isSelected = state.selectedAnswer === choice.scientific_name;
    const isCorrect = choice.scientific_name === state.question.correct_scientific_name;

    // Reuses this app's existing success/danger tokens (same green as the
    // map's own-sighting pins, same red as the map's selected-pin marker
    // and error alerts) rather than inventing new right/wrong colors.
    let style = '';
    if (state.revealed && isCorrect) {
      style = 'background: var(--ob-color-success-bg); border-color: var(--ob-color-success-text);';
    } else if (state.revealed && isSelected && !isCorrect) {
      style = 'background: var(--ob-color-danger-bg); border-color: var(--ob-color-danger-text);';
    }

    return `
      <button
        type="button"
        class="ob-btn ${isSelected && !state.revealed ? 'ob-btn--primary' : 'ob-btn--ghost'}"
        data-choice="${escapeHtml(choice.scientific_name)}"
        style="${style}"
        ${state.revealed ? 'disabled' : ''}
      >${escapeHtml(choice.common_name)}</button>
    `;
  }

  function wireQuestion() {
    container.querySelectorAll('[data-choice]').forEach((btn) => {
      btn.addEventListener('click', () => selectAnswer(btn.dataset.choice));
    });
    container.querySelector('[data-action="next-question"]')?.addEventListener('click', loadQuestion);
    container.querySelector('[data-action="try-another-photo"]')?.addEventListener('click', tryAnotherPhoto);
  }
}
