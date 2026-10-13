// presenters/BulkImport.js — "Import several photos": pick many photos →
// each is identified in the browser-driven queue (Services/bulkImport.js) →
// review grid, one card per photo → log the ticked ones → summary + undo.
// See docs/features/bulk-import.md.
//
// Nothing is logged until the user reviews it: the model is good but not
// field-guide-grade, and 50 unchecked guesses would quietly pollute the
// life list.
//
// Layout: the top bar, the cards and the footer are template strings
// re-rendered from state, but the location map panel is a live Leaflet
// instance (same reason as AddObservation.js — re-creating it would reset
// its pan/zoom/pin), so it lives in its own element that's never rebuilt.
// Card edits are wired by event delegation on the cards container and only
// repaint the cards they affect.
import {
  MAX_PHOTOS,
  computeFlags,
  labelLocations,
  logAll,
  makeItems,
  newImportBatchId,
  scanAll,
  undoImport,
} from '../Services/bulkImport.js';
import { geocodingService } from '../Services/geocoding.js';
import { speciesService } from '../Services/species.js';
import { ACCEPT_ATTR, TYPES_HINT } from '../Services/uploads.js';
import { getCurrentUser } from '../testData/testProfile.js';
import { escapeHtml } from '../Components/CandidateList.js';
import { renderImportReviewCard, renderSpeciesResults, OTHER_SPECIES } from '../Components/ImportReviewCard.js';
import { mountLocationPicker } from '../Components/LocationPicker.js';

const SPECIES_SEARCH_DEBOUNCE_MS = 300;

function nowForDatetimeLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function mount(container, props = {}) {
  const userId = props.userId || getCurrentUser().id;
  const { onNavigate } = props; // optional — omitted when previewed standalone

  const state = {
    phase: 'pick', // 'pick' | 'scanning' | 'review' | 'saving' | 'done'
    items: [],
    skipped: 0,
    flags: new Map(),
    batchDefaultAt: nowForDatetimeLocal(),
    importBatchId: newImportBatchId(),
    saving: { done: 0, total: 0 },
    result: null, // { logged, failed, newSpecies, seenBefore }
    notice: null, // { tone, message }
  };
  const searches = new Map(); // item index -> { open, query, results, timer, requestId }

  // Map panel — see the header comment.
  let mapController = null;
  let locationTarget = null; // an item index, or 'missing' (every ready photo without a location)
  let pendingPin = null;
  // Where the map's marker currently sits. The map is reused between opens,
  // so a reopened panel already shows a pin — that pin has to count as the
  // current choice, or "Use this location" would sit disabled under a
  // visible pin (a real bug: set one card, then "set one location for the
  // rest" did nothing).
  let markerPin = null;

  container.innerHTML = `
    <div class="ob-container ob-stack">
      <div class="ob-cluster">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back">← Back to Add Observation</button>' : ''}
      </div>
      <h1>Import several photos</h1>
      <div data-role="notice"></div>
      <div data-role="top"></div>
      <div class="ob-card ob-stack" data-role="map-panel" hidden>
        <h2 class="ob-text-lg" data-role="map-title">Set location</h2>
        <div class="ob-cluster">
          <input class="ob-input" style="flex:1" data-role="map-search" placeholder="Search for an address or place" autocomplete="off" />
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="map-search">Search</button>
        </div>
        <div class="ob-stack" data-role="map-results" style="--ob-stack-gap: var(--ob-space-1);"></div>
        <div data-role="map" style="height: 320px; border-radius: var(--ob-radius-md); overflow: hidden;"></div>
        <p class="ob-hint" data-role="map-status">Search for a place, or click the map to drop a pin.</p>
        <div class="ob-cluster">
          <button type="button" class="ob-btn ob-btn--primary ob-btn--sm" data-action="map-apply" disabled>Use this location</button>
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="map-cancel">Cancel</button>
        </div>
        <p class="ob-hint">Map tiles &copy; <a href="https://www.esri.com" target="_blank" rel="noopener">Esri</a>. Address search data &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors.</p>
      </div>
      <div class="ob-grid" style="--ob-grid-min: 260px;" data-role="cards"></div>
      <div data-role="footer"></div>
    </div>
  `;
  const el = (role) => container.querySelector(`[data-role="${role}"]`);

  container.querySelector('[data-action="back"]')?.addEventListener('click', () => {
    mapController?.destroy();
    onNavigate('add-observation');
  });
  wireCards();
  wireMapPanel();
  renderAll();

  // ---- rendering ---------------------------------------------------------

  function renderAll() {
    renderNotice();
    renderTop();
    renderCards();
    renderFooter();
  }

  function renderNotice() {
    el('notice').innerHTML = state.notice
      ? `<div class="ob-alert ob-alert--${state.notice.tone}">${escapeHtml(state.notice.message)}</div>`
      : '';
  }

  function renderTop() {
    const top = el('top');
    if (state.phase === 'pick') {
      top.innerHTML = `
        <div class="ob-card ob-stack">
          <p>Pick up to <strong>${MAX_PHOTOS} photos</strong> from one outing. Each one gets a best-guess species, and
          its date and location are read from the photo when it has them. You review everything before
          anything is logged.</p>
          <input type="file" data-role="file-input" multiple accept="${ACCEPT_ATTR}" style="display:none;" />
          <button type="button" class="ob-btn ob-btn--primary" data-action="pick" style="align-self:flex-start;">Choose photos</button>
          <p class="ob-hint">${TYPES_HINT} Keep this tab open while the photos are identified.</p>
        </div>
      `;
      const input = top.querySelector('[data-role="file-input"]');
      top.querySelector('[data-action="pick"]').addEventListener('click', () => input.click());
      input.addEventListener('change', () => {
        if (input.files.length) startImport(input.files);
      });
      return;
    }

    const ready = state.items.filter((it) => it.status === 'ready').length;
    const failed = state.items.filter((it) => it.status === 'failed').length;
    const total = state.items.length;

    if (state.phase === 'scanning') {
      const finished = ready + failed;
      top.innerHTML = `
        <div class="ob-card ob-stack">
          <p><strong>Identified ${finished} of ${total}…</strong></p>
          <progress max="${total}" value="${finished}" style="width:100%;"></progress>
          ${finished === 0 ? '<p class="ob-hint">The first photo can take up to a minute while the bird model warms up.</p>' : ''}
          <p class="ob-hint">You can start reviewing cards as they finish.</p>
        </div>
      `;
      return;
    }

    if (state.phase === 'done') {
      const { logged, failed: failedItems, newSpecies } = state.result;
      top.innerHTML = `
        <div class="ob-card ob-stack ob-text-center">
          <h2>${logged} observation${logged === 1 ? '' : 's'} logged</h2>
          ${newSpecies.length
            ? `<span class="ob-tag ob-tag--success" style="align-self:center;">${newSpecies.length} new life list species!</span>`
            : '<span class="ob-tag ob-tag--info" style="align-self:center;">No new life list species this time</span>'}
          ${failedItems.length ? `<div class="ob-alert ob-alert--warning">${failedItems.length} couldn't be saved. Try again below.</div>` : ''}
          <div class="ob-cluster" style="justify-content:center;">
            ${onNavigate ? `
              <button type="button" class="ob-btn ob-btn--primary" data-action="view-observations">View my observations</button>
              <button type="button" class="ob-btn ob-btn--ghost" data-action="view-life-list">View life list</button>
            ` : ''}
            <button type="button" class="ob-btn ob-btn--ghost" data-action="start-over">Import more photos</button>
            ${logged ? '<button type="button" class="ob-btn ob-btn--subtle" data-action="undo">Undo this import</button>' : ''}
          </div>
        </div>
      `;
      top.querySelector('[data-action="view-observations"]')?.addEventListener('click', () => leave('observation-log', { userId }));
      top.querySelector('[data-action="view-life-list"]')?.addEventListener('click', () => leave('life-list'));
      top.querySelector('[data-action="start-over"]').addEventListener('click', startOver);
      top.querySelector('[data-action="undo"]')?.addEventListener('click', undo);
      return;
    }

    // review / saving
    const missing = missingLocationItems().length;
    top.innerHTML = `
      <div class="ob-card ob-stack">
        <p><strong>${ready} identified</strong>${failed ? `, ${failed} failed` : ''}${state.skipped ? `. Only the first ${MAX_PHOTOS} photos were imported; ${state.skipped} skipped` : ''}.
        Check each card, untick anything you don't want logged, then log them at the bottom.</p>
        <div class="ob-field">
          <label class="ob-label" for="batch-date">Date for photos without one</label>
          <input id="batch-date" type="datetime-local" class="ob-input" value="${escapeHtml(state.batchDefaultAt)}" style="max-width:260px;" />
        </div>
        ${missing ? `
          <button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="locate-missing" style="align-self:flex-start;">
            Set one location for the ${missing} photo${missing === 1 ? '' : 's'} without one
          </button>` : ''}
      </div>
    `;
    top.querySelector('#batch-date').addEventListener('change', (e) => {
      state.batchDefaultAt = e.target.value || nowForDatetimeLocal();
      state.items.filter((it) => !it.observedAt).forEach((it) => refreshCard(it.index));
      refreshFlags();
    });
    top.querySelector('[data-action="locate-missing"]')?.addEventListener('click', () => openMap('missing'));
  }

  function renderCards() {
    el('cards').innerHTML = state.items.map(cardHtml).join('');
  }

  function cardHtml(item) {
    const flags = state.flags.get(item.index) || {};
    return renderImportReviewCard(item, flags, searches.get(item.index), state.batchDefaultAt);
  }

  function refreshCard(index) {
    const card = el('cards').querySelector(`[data-index="${index}"]`);
    if (card) card.outerHTML = cardHtml(state.items[index]);
  }

  // Flags can change on other cards too (duplicates), so recompute all and
  // repaint only the cards whose flags actually changed.
  function refreshFlags() {
    const before = state.flags;
    state.flags = computeFlags(state.items);
    for (const [index, flags] of state.flags) {
      if (JSON.stringify(flags) !== JSON.stringify(before.get(index))) refreshCard(index);
    }
  }

  function renderFooter() {
    const footer = el('footer');
    if (state.phase === 'review' || state.phase === 'scanning') {
      const toLog = state.items.filter((it) => it.include && it.status === 'ready' && !it.loggedId).length;
      const scanning = state.phase === 'scanning';
      footer.innerHTML = `
        <div class="ob-card ob-stack" style="position:sticky;bottom:0;">
          <button type="button" class="ob-btn ob-btn--primary ob-btn--block" data-action="log" ${toLog && !scanning ? '' : 'disabled'}>
            ${scanning ? 'Waiting for every photo to be identified…' : `Log ${toLog} observation${toLog === 1 ? '' : 's'}`}
          </button>
        </div>
      `;
      footer.querySelector('[data-action="log"]').addEventListener('click', logChecked);
    } else if (state.phase === 'saving') {
      const { done, total } = state.saving;
      footer.innerHTML = `
        <div class="ob-card ob-stack">
          <p>Logging ${done} of ${total}…</p>
          <progress max="${total}" value="${done}" style="width:100%;"></progress>
        </div>
      `;
    } else if (state.phase === 'done' && state.result.failed.length) {
      footer.innerHTML = `
        <div class="ob-card"><button type="button" class="ob-btn ob-btn--primary ob-btn--block" data-action="retry-log">
          Try saving the ${state.result.failed.length} that failed
        </button></div>
      `;
      footer.querySelector('[data-action="retry-log"]').addEventListener('click', logChecked);
    } else {
      footer.innerHTML = '';
    }
  }

  // ---- flow --------------------------------------------------------------

  async function startImport(fileList) {
    const { items, skipped } = makeItems(fileList);
    Object.assign(state, { items, skipped, phase: 'scanning', notice: null });
    state.flags = computeFlags(items);
    renderAll();
    await scanAll(state.items, onItemChanged);
    state.phase = 'review';
    refreshFlags();
    renderTop();
    renderFooter();
    labelLocations(state.items, (it) => refreshCard(it.index)); // background; cards fill in as labels arrive
  }

  function onItemChanged(item) {
    refreshCard(item.index);
    if (item.status === 'ready' || item.status === 'failed') {
      refreshFlags();
      renderTop();
      renderFooter();
    }
  }

  async function retryItem(index) {
    const item = state.items[index];
    item.status = 'queued';
    const wasReview = state.phase === 'review';
    await scanAll([item], onItemChanged);
    if (wasReview) labelLocations([item], (it) => refreshCard(it.index));
  }

  async function logChecked() {
    closeMap();
    state.phase = 'saving';
    state.saving = { done: 0, total: state.items.filter((it) => it.include && it.status === 'ready' && !it.loggedId).length };
    renderFooter();
    try {
      state.result = await logAll(state.items, {
        userId,
        importBatchId: state.importBatchId,
        batchDefaultAt: state.batchDefaultAt,
        seenBefore: state.result?.seenBefore || null,
        onProgress: (done, total) => {
          state.saving = { done, total };
          renderFooter();
        },
      });
      state.phase = 'done';
      state.notice = null;
    } catch (err) {
      state.phase = 'review';
      state.notice = { tone: 'danger', message: err.message || 'Could not save these observations. Please try again.' };
    }
    renderAll();
  }

  async function undo() {
    const count = state.result.logged;
    if (!window.confirm(`Remove all ${count} observation${count === 1 ? '' : 's'} from this import? This can't be undone.`)) return;
    try {
      const { deleted } = await undoImport(userId, state.importBatchId);
      state.items.forEach((it) => { delete it.loggedId; });
      Object.assign(state, {
        phase: 'review',
        result: null,
        importBatchId: newImportBatchId(), // a re-log is a fresh import
        notice: { tone: 'success', message: `Import undone: ${deleted} observation${deleted === 1 ? '' : 's'} removed. Your photos are still here if you want to fix something and log again.` },
      });
    } catch (err) {
      state.notice = { tone: 'danger', message: err.message || 'Could not undo this import. Please try again.' };
    }
    renderAll();
  }

  function startOver() {
    state.items.forEach((it) => URL.revokeObjectURL(it.previewUrl));
    searches.clear();
    Object.assign(state, {
      phase: 'pick', items: [], skipped: 0, flags: new Map(), result: null, notice: null,
      batchDefaultAt: nowForDatetimeLocal(), importBatchId: newImportBatchId(),
    });
    closeMap();
    renderAll();
  }

  function leave(route, params) {
    mapController?.destroy();
    onNavigate(route, params);
  }

  // ---- card events (delegated) -------------------------------------------

  function wireCards() {
    const cards = el('cards');
    const itemFor = (target) => {
      const card = target.closest('[data-index]');
      return card ? state.items[Number(card.dataset.index)] : null;
    };

    cards.addEventListener('change', (e) => {
      const item = itemFor(e.target);
      if (!item) return;
      const field = e.target.dataset.field;
      if (field === 'include') {
        item.include = e.target.checked;
        refreshCard(item.index);
        renderFooter();
      } else if (field === 'species') {
        if (e.target.value === OTHER_SPECIES) {
          searches.set(item.index, { open: true, query: '', results: [], timer: null, requestId: 0 });
          refreshCard(item.index);
          el('cards').querySelector(`[data-index="${item.index}"] [data-field="speciesQuery"]`)?.focus();
          return;
        }
        const picked = item.candidates.find((c) => c.scientific_name === e.target.value);
        if (picked) {
          item.species = { commonName: picked.common_name, scientificName: picked.scientific_name };
          item.confidence = picked.confidence;
          item.userPicked = true;
        }
        searches.delete(item.index);
        refreshCard(item.index);
        refreshFlags();
      } else if (field === 'observedAt') {
        item.observedAt = e.target.value;
        item.dateFromPhoto = false;
        refreshCard(item.index);
        refreshFlags();
      } else if (field === 'sex' || field === 'lifeStage') {
        item[field] = e.target.value;
      }
    });

    cards.addEventListener('input', (e) => {
      const item = itemFor(e.target);
      if (!item) return;
      if (e.target.dataset.field === 'notes') {
        item.notes = e.target.value;
      } else if (e.target.dataset.field === 'speciesQuery') {
        scheduleSpeciesSearch(item.index, e.target.value);
      }
    });

    cards.addEventListener('click', (e) => {
      const button = e.target.closest('[data-action]');
      const item = button && itemFor(button);
      if (!item) return;
      const action = button.dataset.action;
      if (action === 'retry') {
        retryItem(item.index);
      } else if (action === 'set-location') {
        openMap(item.index);
      } else if (action === 'pick-species') {
        item.species = { commonName: button.dataset.commonName, scientificName: button.dataset.scientificName };
        item.confidence = null;
        item.userPicked = true;
        searches.delete(item.index);
        refreshCard(item.index);
        refreshFlags();
      }
    });
  }

  function scheduleSpeciesSearch(index, query) {
    const search = searches.get(index);
    if (!search) return;
    search.query = query;
    clearTimeout(search.timer);
    search.timer = setTimeout(async () => {
      const requestId = (search.requestId += 1);
      let results = [];
      try {
        results = await speciesService.search(query);
      } catch {
        results = [];
      }
      if (requestId !== search.requestId) return; // a newer search started
      search.results = results.slice(0, 8);
      const resultsEl = el('cards').querySelector(`[data-index="${index}"] [data-role="species-results"]`);
      if (resultsEl) resultsEl.innerHTML = renderSpeciesResults(search.results);
    }, SPECIES_SEARCH_DEBOUNCE_MS);
  }

  // ---- location map panel ------------------------------------------------

  function missingLocationItems() {
    return state.items.filter((it) => it.status === 'ready' && !it.loggedId && (it.lat == null || it.lng == null));
  }

  async function openMap(target) {
    locationTarget = target;
    pendingPin = null;
    const panel = el('map-panel');
    const item = typeof target === 'number' ? state.items[target] : null;
    el('map-title').textContent = item
      ? `Set location for ${item.file.name}`
      : `Set one location for ${missingLocationItems().length} photos without one`;
    el('map-status').textContent = 'Search for a place, or click the map to drop a pin.';
    panel.querySelector('[data-action="map-apply"]').disabled = true;
    panel.hidden = false;
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Start from this photo's own location if it has one, otherwise from
    // wherever the marker was last left.
    const start = item && item.lat != null ? [item.lat, item.lng]
      : markerPin ? [markerPin.lat, markerPin.lng] : undefined;
    if (!mapController) {
      try {
        mapController = await mountLocationPicker(el('map'), {
          initialLatLng: start,
          onPositionChange: (lat, lng) => setPendingPin(lat, lng),
        });
      } catch (err) {
        el('map').innerHTML = `<div class="ob-alert ob-alert--warning">${escapeHtml(err.message || 'Could not load the map.')}</div>`;
      }
    } else if (start) {
      mapController.setView(...start);
    }
    if (start) setPendingPin(...start);
  }

  function setPendingPin(lat, lng) {
    pendingPin = { lat, lng };
    markerPin = { lat, lng };
    el('map-status').textContent = `Pin at ${lat.toFixed(5)}, ${lng.toFixed(5)}. Click the map again to move it.`;
    el('map-panel').querySelector('[data-action="map-apply"]').disabled = false;
  }

  function closeMap() {
    el('map-panel').hidden = true;
    el('map-results').innerHTML = '';
    locationTarget = null;
    pendingPin = null;
  }

  function wireMapPanel() {
    const panel = el('map-panel');
    const searchInput = el('map-search');
    const resultsEl = el('map-results');

    async function runSearch() {
      const query = searchInput.value.trim();
      if (!query) return;
      resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">Searching…</p>';
      let results = [];
      try {
        results = await geocodingService.search(query);
      } catch {
        resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">Search failed. Try again in a moment.</p>';
        return;
      }
      if (!results.length) {
        resultsEl.innerHTML = '<p class="ob-text-muted ob-text-sm">No matches. Try a different search, or just click the map.</p>';
        return;
      }
      resultsEl.innerHTML = results.map((r, i) => `
        <button type="button" class="ob-btn ob-btn--ghost ob-btn--block ob-text-sm" style="justify-content:flex-start;" data-result-index="${i}">${escapeHtml(r.display_name)}</button>
      `).join('');
      resultsEl.querySelectorAll('[data-result-index]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const picked = results[Number(btn.dataset.resultIndex)];
          mapController?.setView(picked.lat, picked.lng);
          setPendingPin(picked.lat, picked.lng);
          resultsEl.innerHTML = '';
        });
      });
    }

    panel.querySelector('[data-action="map-search"]').addEventListener('click', runSearch);
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runSearch();
      }
    });
    panel.querySelector('[data-action="map-cancel"]').addEventListener('click', closeMap);
    panel.querySelector('[data-action="map-apply"]').addEventListener('click', () => {
      if (!pendingPin) return;
      const targets = locationTarget === 'missing' ? missingLocationItems() : [state.items[locationTarget]];
      for (const it of targets) {
        it.lat = pendingPin.lat;
        it.lng = pendingPin.lng;
        it.locationName = '';
        refreshCard(it.index);
      }
      closeMap();
      refreshFlags();
      renderTop();
      labelLocations(targets, (it) => refreshCard(it.index));
    });
  }
}
