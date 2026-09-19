// Components/CandidateList.js — presentational only; no Dao/Service imports.
// Renders the "which one did you see/heard?" grid. The Presenter wires up
// clicks (and Enter/Space, since this can't be a real <button> — see below)
// via the `data-species-code` attribute.
//
// The card is a div with role="button", not an actual <button>: HTML doesn't
// allow interactive content (an <audio controls> player, shown in "heard it"
// mode) to nest inside a real button — browsers silently break the button
// open when you try, which breaks the whole card's click handling. The
// Presenter must wire both `click` and a `keydown` (Enter/Space) listener to
// keep it keyboard-accessible.

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

export function renderCandidateList(candidates, selectedCode, sense = 'sight') {
  return `
    <div class="ob-grid" data-role="candidate-grid">
      ${candidates.map((c) => `
        <div
          class="ob-card ob-card--interactive ob-text-center"
          data-species-code="${escapeHtml(c.species_code)}"
          role="button"
          tabindex="0"
          aria-pressed="${c.species_code === selectedCode}"
        >
          <img src="${escapeHtml(c.photo_url)}" alt="${escapeHtml(c.common_name)}" />
          <h3 class="ob-card__title">${escapeHtml(c.common_name)}</h3>
          <p class="ob-card__body ob-text-sm"><em>${escapeHtml(c.scientific_name)}</em></p>
          ${c.photo_attribution ? `<p class="ob-text-muted ob-text-sm">Photo: ${escapeHtml(c.photo_attribution)}</p>` : ''}
          ${sense === 'sound' ? renderAudio(c) : ''}
          ${c.species_code === selectedCode ? '<span class="ob-tag ob-tag--success">Selected</span>' : ''}
        </div>
      `).join('')}
    </div>
  `;
}

function renderAudio(candidate) {
  if (!candidate.audio_url) {
    return '<p class="ob-hint">No recording available</p>';
  }
  return `
    <audio controls src="${escapeHtml(candidate.audio_url)}" style="width:100%;margin-top:var(--ob-space-2);"></audio>
    ${candidate.audio_attribution ? `<p class="ob-text-muted ob-text-sm">Audio: ${escapeHtml(candidate.audio_attribution)}</p>` : ''}
  `;
}
