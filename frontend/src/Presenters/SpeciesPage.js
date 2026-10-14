// Presenters/SpeciesPage.js — the Bird Info page: a read-only reference
// page for one species (header, photo/audio, About/sex-differences/
// migration/habitat prose, seen status + pin toggle). See
// docs/features/bird-info.md.
//
//   import { mount } from './Presenters/SpeciesPage.js';
//   mount(container, { scientificName, commonName, onNavigate, userId });
//
// `commonName` is optional — several entry points (SightingDetail.js,
// PlanATrip.js's likely-species cards) already have it on hand and passing
// it through avoids a flash of "unknown species" before the profile loads;
// the profile fetch itself only ever needs `scientificName` (see
// app/routers/species.py's note on why that's the one field every entry
// point reliably has).
import { speciesService } from '../Services/species.js';
import { pinsService } from '../Services/pins.js';
import { lifeListService } from '../Services/lifeList.js';
import { escapeHtml } from '../Components/htmlUtils.js';

export function mount(container, props = {}) {
  const { scientificName, commonName: initialCommonName, onNavigate, userId = 'u1' } = props;

  const state = {
    loading: true,
    error: null,
    profile: null,
    seenAt: null, // ISO date string, or null if not seen
    pinned: false,
    pinError: null,
  };

  render();
  loadProfile();
  loadStatus();

  function render() {
    container.innerHTML = `
      <div class="ob-container ob-stack">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back" style="align-self:flex-start;">← Back</button>' : ''}
        ${state.loading ? renderLoading() : state.error ? renderError() : renderProfile()}
      </div>
    `;
    wire();
  }

  function renderLoading() {
    return '<div class="ob-card ob-text-center"><div class="ob-spinner" style="margin-inline:auto"></div></div>';
  }

  function renderError() {
    return `<div class="ob-alert ob-alert--danger">${escapeHtml(state.error)}</div>`;
  }

  function renderProfile() {
    const p = state.profile;
    return `
      <div class="ob-card ob-stack">
        <div class="ob-cluster" style="justify-content: space-between; align-items: flex-start;">
          <div>
            <h1 style="margin: 0;">${escapeHtml(p.commonName || initialCommonName || scientificName)}</h1>
            <p class="ob-text-muted" style="margin: 2px 0 0;"><em>${escapeHtml(scientificName)}</em>${p.family ? ` · ${escapeHtml(p.family)}` : ''}</p>
          </div>
          <span class="ob-tag ${state.seenAt ? 'ob-tag--success' : ''}">${state.seenAt ? `Seen — first on ${escapeHtml(formatDate(state.seenAt))}` : 'Not seen yet'}</span>
        </div>

        <img src="${escapeHtml(p.photoUrl)}" alt="${escapeHtml(p.commonName || scientificName)}" style="width:100%; max-height:360px; object-fit:cover; border-radius: var(--ob-radius-sm);" />
        ${p.photoAttribution ? `<p class="ob-text-muted ob-text-sm" style="margin:0;">${escapeHtml(p.photoAttribution)}</p>` : ''}

        ${p.audioUrl ? `<audio controls src="${escapeHtml(p.audioUrl)}" style="width:100%;"></audio>` : ''}
        ${p.audioUrl && p.audioAttribution ? `<p class="ob-text-muted ob-text-sm" style="margin:0;">${escapeHtml(p.audioAttribution)}</p>` : ''}

        <div class="ob-cluster">
          <button type="button" class="ob-btn ${state.pinned ? 'ob-btn--primary' : 'ob-btn--ghost'} ob-btn--sm" data-action="toggle-pin" aria-pressed="${state.pinned}">${state.pinned ? 'Pinned' : 'Pin this species'}</button>
        </div>
        ${state.pinError ? `<div class="ob-alert ob-alert--danger ob-text-sm">${escapeHtml(state.pinError)}</div>` : ''}

        ${renderTextBlock('About', p.about, p.aboutSourceUrl)}
        ${renderTextBlock('Male vs. female', p.sexDifferences)}
        ${renderTextBlock('Migration', p.migration)}
        ${renderTextBlock('Habitat', p.habitat)}
        ${!p.about && !p.sexDifferences && !p.migration && !p.habitat
          ? '<p class="ob-text-muted ob-text-sm">No Wikipedia article content found for this species yet.</p>'
          : ''}
      </div>
    `;
  }

  function renderTextBlock(label, text, sourceUrl) {
    if (!text) return '';
    return `
      <div>
        <h2 class="ob-card__title" style="font-size: 1.05rem;">${escapeHtml(label)}</h2>
        <p class="ob-card__body" style="white-space: pre-wrap;">${escapeHtml(text)}</p>
        ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" class="ob-text-sm">Wikipedia</a>` : ''}
      </div>
    `;
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return iso;
    }
  }

  function wire() {
    container.querySelector('[data-action="back"]')?.addEventListener('click', () => onNavigate?.('home'));
    container.querySelector('[data-action="toggle-pin"]')?.addEventListener('click', togglePin);
  }

  async function loadProfile() {
    state.loading = true;
    state.error = null;
    render();
    try {
      state.profile = await speciesService.getProfile(scientificName);
    } catch (err) {
      state.error = err.message || 'Could not load this species.';
    } finally {
      state.loading = false;
      render();
    }
  }

  // "Seen / not seen" and pin state are both derived from data this app
  // already has elsewhere (life_list_entries / pinned_birds — see
  // bird-info.md's "Where the data comes from" table) rather than carried
  // on the profile response itself, so both load independently of it and
  // re-render into the same card once each resolves.
  async function loadStatus() {
    try {
      const [lifeList, pins] = await Promise.all([
        lifeListService.getAll(userId),
        pinsService.list(userId),
      ]);
      const seenEntry = lifeList.find(
        (e) => e.species?.scientific_name?.toLowerCase() === scientificName.toLowerCase(),
      );
      state.seenAt = seenEntry?.first_observed_at || null;
      state.pinned = pins.some((p) => p.scientific_name.toLowerCase() === scientificName.toLowerCase());
      render();
    } catch (err) {
      // Leave seen/pinned at their defaults — the page still works without
      // this, same as other best-effort status badges in this app.
    }
  }

  async function togglePin() {
    state.pinError = null;
    try {
      if (state.pinned) {
        await pinsService.unpin(userId, scientificName);
        state.pinned = false;
      } else {
        await pinsService.pin(userId, {
          scientificName,
          commonName: state.profile?.commonName || initialCommonName,
        });
        state.pinned = true;
      }
    } catch (err) {
      state.pinError = err.message || 'Could not update the pin.';
    } finally {
      render();
    }
  }
}
