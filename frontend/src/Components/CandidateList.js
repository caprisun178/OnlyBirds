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
          ${renderConfidence(c.confidence)}
          ${c.photo_attribution ? `<p class="ob-text-muted ob-text-sm">Photo: ${escapeHtml(c.photo_attribution)}</p>` : ''}
          ${sense === 'sound' ? renderAudio(c) : ''}
          ${c.species_code === selectedCode ? '<span class="ob-tag ob-tag--success">Selected</span>' : ''}
        </div>
      `).join('')}
    </div>
  `;
}

// A visible confidence number lets a user spot a low-confidence (or just
// generically unconvincing) pick instead of trusting the top card by
// default — matters most for photo-ID results, which can be confidently
// wrong rather than just uncertain when the real species isn't one the
// classifier model knows at all (see docs/features/bird-id.md).
function renderConfidence(confidence) {
  if (confidence == null) return '';
  const pct = Math.round(confidence * 100);
  const tone = pct >= 50 ? 'success' : pct >= 20 ? 'warning' : 'danger';
  return `<span class="ob-tag ob-tag--${tone}">${pct}% match</span>`;
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
