// Components/SpeciesCard.js — presentational only. A species the user has
// already logged: their photo (if any — falling back to a Commons stock
// photo server-side, see life-list.md), common/scientific name, first-seen
// date. Clickable — the Presenter wires the click/keydown to open that
// species' observation log — so it's a `role="button"` div rather than a
// real `<button>`, same reasoning as `Components/CandidateList.js`.
import { escapeHtml } from './htmlUtils.js';

export function renderSpeciesCard(species) {
  const dateLabel = species.first_observed_at
    ? new Date(species.first_observed_at).toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
      })
    : null;

  return `
    <article
      class="ob-card ob-card--interactive"
      data-scientific-name="${escapeHtml(species.scientific_name)}"
      data-common-name="${escapeHtml(species.common_name)}"
      role="button"
      tabindex="0"
    >
      ${species.photo_url
        ? `<img src="${escapeHtml(species.photo_url)}" alt="${escapeHtml(species.common_name)}" style="width:100%;height:160px;object-fit:cover;border-radius:var(--ob-radius-md);margin-bottom:var(--ob-space-3);" />`
        : ''}
      <h3 class="ob-card__title">${escapeHtml(species.common_name)}</h3>
      <p class="ob-card__body ob-text-sm"><em>${escapeHtml(species.scientific_name)}</em></p>
      ${species.photo_attribution ? `<p class="ob-text-muted ob-text-sm">Photo: ${escapeHtml(species.photo_attribution)}</p>` : ''}
      <span class="ob-tag ob-tag--success">${dateLabel ? `Seen — ${escapeHtml(dateLabel)}` : 'Seen'}</span>
    </article>
  `;
}
