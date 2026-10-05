// Components/MissingBird.js — presentational only. The greyed placeholder
// for a species in the region checklist the user hasn't logged yet.
import { escapeHtml } from './htmlUtils.js';

export function renderMissingBird(species) {
  return `
    <article class="ob-card ob-card--flat ob-text-center" style="opacity: 0.6;">
      <div aria-hidden="true" style="height:80px;border-radius:var(--ob-radius-sm);background:var(--ob-color-surface-alt);"></div>
      <h3 class="ob-card__title">${escapeHtml(species.common_name)}</h3>
      <p class="ob-card__body ob-text-sm"><em>${escapeHtml(species.scientific_name)}</em></p>
      <span class="ob-tag">Not seen yet</span>
    </article>
  `;
}
