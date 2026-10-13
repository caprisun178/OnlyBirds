// components/ImportReviewCard.js — one photo's card on the bulk import
// review screen (Presenters/BulkImport.js). Presentational only: returns
// markup; the presenter wires events by delegation using `data-index` and
// `data-field` / `data-action`. See docs/features/bulk-import.md §1.
import { escapeHtml } from './CandidateList.js';

const OTHER_SPECIES = '__search__';

// `flags`: { noLocation, lowConfidence, possibleDuplicate } from
// Services/bulkImport.js#computeFlags(). `search`: { open, query, results }
// for this card's "Other species…" search, owned by the presenter.
export function renderImportReviewCard(item, flags, search, batchDefaultAt) {
  const i = item.index;
  // HEIC previews only render in Safari; the stored copy is always a JPEG.
  const imgSrc = item.photoUrl || item.previewUrl;
  return `
    <div class="ob-card ob-stack" data-index="${i}" style="--ob-stack-gap: var(--ob-space-2); ${item.include ? '' : 'opacity:0.65;'}">
      <img src="${escapeHtml(imgSrc)}" alt="${escapeHtml(item.file.name)}" loading="lazy"
           style="width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:var(--ob-radius-md);background:var(--ob-color-surface-2, #eee);"
           onerror="this.style.visibility='hidden'" />
      ${renderBody(item, flags, search, batchDefaultAt)}
    </div>
  `;
}

function renderBody(item, flags, search, batchDefaultAt) {
  if (item.status === 'queued' || item.status === 'identifying') {
    return `<p class="ob-hint">${item.status === 'queued' ? 'Waiting…' : '<span class="ob-spinner" style="width:1em;height:1em;vertical-align:middle;margin-right:6px;"></span>Identifying…'}</p>`;
  }
  if (item.status === 'failed') {
    return `
      <div class="ob-alert ob-alert--warning ob-text-sm">${escapeHtml(item.error)}</div>
      <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="retry">Try again</button>
    `;
  }
  if (item.loggedId) {
    return `<span class="ob-tag ob-tag--success">Logged: ${escapeHtml(item.species.commonName)}</span>`;
  }

  const sci = item.species?.scientificName;
  const options = item.candidates.map((c) => `
    <option value="${escapeHtml(c.scientific_name)}" ${c.scientific_name === sci ? 'selected' : ''}>
      ${escapeHtml(c.common_name)} (${Math.round(c.confidence * 100)}%)
    </option>`).join('');
  const isCustom = sci && !item.candidates.some((c) => c.scientific_name === sci);

  return `
    <label class="ob-cluster ob-text-sm" style="align-items:center;">
      <input type="checkbox" data-field="include" ${item.include ? 'checked' : ''} />
      Log this one
    </label>
    <div class="ob-cluster ob-text-sm">
      ${flags.lowConfidence ? '<span class="ob-tag ob-tag--warning">Low confidence — check the species</span>' : ''}
      ${flags.possibleDuplicate ? '<span class="ob-tag ob-tag--info">Possible duplicate</span>' : ''}
      ${flags.noLocation ? '<span class="ob-tag ob-tag--warning">No location</span>' : ''}
    </div>
    <div class="ob-field">
      <label class="ob-label">Species</label>
      <select class="ob-select" data-field="species">
        ${isCustom ? `<option value="${escapeHtml(sci)}" selected>${escapeHtml(item.species.commonName)}</option>` : ''}
        ${options}
        <option value="${OTHER_SPECIES}">Other species…</option>
      </select>
      ${search?.open ? renderSpeciesSearch(search) : ''}
    </div>
    <div class="ob-field">
      <label class="ob-label">Date &amp; time</label>
      <input type="datetime-local" class="ob-input" data-field="observedAt" value="${escapeHtml(item.observedAt || batchDefaultAt)}" />
      <p class="ob-hint">${item.dateFromPhoto ? 'From the photo.' : item.observedAt ? 'Edited.' : 'The photo had no date, so this uses the date at the top.'}</p>
    </div>
    <div class="ob-field">
      <label class="ob-label">Location</label>
      <p class="ob-text-sm">${item.lat != null
        ? escapeHtml(item.locationName || `${item.lat.toFixed(4)}, ${item.lng.toFixed(4)}`)
        : '<span class="ob-text-muted">Not set</span>'}</p>
      <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="set-location" style="align-self:flex-start;">
        ${item.lat != null ? 'Change location' : 'Set location'}
      </button>
    </div>
    <details>
      <summary class="ob-text-sm">More details (optional)</summary>
      <div class="ob-stack" style="--ob-stack-gap: var(--ob-space-2); margin-top: var(--ob-space-2);">
        <select class="ob-select" data-field="sex" aria-label="Male / female">
          <option value="">Male / female: not sure</option>
          ${['male', 'female', 'unknown'].map((v) => `<option value="${v}" ${item.sex === v ? 'selected' : ''}>${v[0].toUpperCase()}${v.slice(1)}</option>`).join('')}
        </select>
        <select class="ob-select" data-field="lifeStage" aria-label="Life stage">
          <option value="">Life stage: not sure</option>
          ${['adult', 'juvenile', 'fledgling', 'unknown'].map((v) => `<option value="${v}" ${item.lifeStage === v ? 'selected' : ''}>${v[0].toUpperCase()}${v.slice(1)}</option>`).join('')}
        </select>
        <textarea class="ob-textarea" data-field="notes" placeholder="Notes">${escapeHtml(item.notes)}</textarea>
      </div>
    </details>
  `;
}

function renderSpeciesSearch(search) {
  return `
    <div class="ob-stack" style="--ob-stack-gap: var(--ob-space-1); margin-top: var(--ob-space-1);">
      <input class="ob-input" data-field="speciesQuery" placeholder="Search by name" value="${escapeHtml(search.query)}" autocomplete="off" />
      <div class="ob-stack" data-role="species-results" style="--ob-stack-gap: var(--ob-space-1);">${renderSpeciesResults(search.results)}</div>
    </div>
  `;
}

// Separate so the presenter can patch just the results while the user is
// still typing in the search box (a full card re-render would drop focus).
export function renderSpeciesResults(results) {
  return results.map((s) => `
    <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm ob-text-sm" style="justify-content:flex-start;"
            data-action="pick-species" data-scientific-name="${escapeHtml(s.scientific_name || '')}" data-common-name="${escapeHtml(s.common_name || s.scientific_name || '')}">
      ${escapeHtml(s.common_name || s.scientific_name)} <span class="ob-text-muted">(${escapeHtml(s.scientific_name || '')})</span>
    </button>`).join('');
}

export { OTHER_SPECIES };
