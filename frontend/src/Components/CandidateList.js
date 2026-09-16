// Components/CandidateList.js — presentational only; no Dao/Service imports.
// Renders the "which one did you see?" grid. The Presenter wires up clicks
// via the `data-species-code` attribute.

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

export function renderCandidateList(candidates, selectedCode) {
  return `
    <div class="ob-grid" data-role="candidate-grid">
      ${candidates.map((c) => `
        <button
          type="button"
          class="ob-card ob-card--interactive ob-text-center"
          data-species-code="${escapeHtml(c.species_code)}"
          aria-pressed="${c.species_code === selectedCode}"
        >
          <img src="${escapeHtml(c.photo_url)}" alt="${escapeHtml(c.common_name)}" />
          <h3 class="ob-card__title">${escapeHtml(c.common_name)}</h3>
          <p class="ob-card__body ob-text-sm"><em>${escapeHtml(c.scientific_name)}</em></p>
          ${c.species_code === selectedCode ? '<span class="ob-tag ob-tag--success">Selected</span>' : ''}
        </button>
      `).join('')}
    </div>
  `;
}
