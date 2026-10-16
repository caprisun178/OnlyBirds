import { getStickerShelf } from '../Services/stickers.js';
import { renderStickerCard } from '../Components/StickerCard.js';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[character]));
}

export async function mount(container, props = {}) {
  const { userId = 'u1', onNavigate } = props;
  const state = { shelf: null, rarity: 'all', status: 'all', error: null };

  function render() {
    if (state.error) {
      container.innerHTML = `
        <main class="ob-container ob-stack">
          ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm" data-action="back">← Back</button>' : ''}
          <div class="ob-alert ob-alert--danger" role="alert">
            <p>${escapeHtml(state.error)}</p>
            <button type="button" class="ob-btn ob-btn--subtle ob-btn--sm" data-action="retry">Try again</button>
          </div>
        </main>`;
      container.querySelector('[data-action="retry"]').addEventListener('click', load);
      wireBack();
      return;
    }

    if (!state.shelf) {
      container.innerHTML = '<p class="ob-text-muted" role="status">Loading your sticker shelf…</p>';
      return;
    }

    const stickers = [...state.shelf.earned, ...state.shelf.locked];
    const filtered = stickers.filter((sticker) =>
      (state.rarity === 'all' || sticker.rarity === state.rarity)
      && (state.status === 'all'
        || (state.status === 'earned' ? sticker.earned : !sticker.earned)));
    const earnedCount = state.shelf.earned.length;

    container.innerHTML = `
      <main class="ob-container ob-stack ob-sticker-page">
        ${onNavigate ? '<button type="button" class="ob-btn ob-btn--ghost ob-btn--sm ob-sticker-back" data-action="back">← Back</button>' : ''}
        <header class="ob-sticker-header">
          <div>
            <p class="ob-eyebrow">Collection</p>
            <h1>Sticker shelf</h1>
            <p class="ob-text-muted" aria-live="polite">${earnedCount} of ${state.shelf.total} earned</p>
          </div>
        </header>
        <section class="ob-sticker-controls ob-cluster" aria-label="Filter stickers">
          <label class="ob-field">
            <span class="ob-label">Collection</span>
            <select class="ob-select" data-filter="status">
              <option value="all" ${state.status === 'all' ? 'selected' : ''}>All stickers</option>
              <option value="earned" ${state.status === 'earned' ? 'selected' : ''}>Earned</option>
              <option value="locked" ${state.status === 'locked' ? 'selected' : ''}>Still to find</option>
            </select>
          </label>
          <label class="ob-field">
            <span class="ob-label">Rarity</span>
            <select class="ob-select" data-filter="rarity">
              <option value="all" ${state.rarity === 'all' ? 'selected' : ''}>All rarities</option>
              <option value="common" ${state.rarity === 'common' ? 'selected' : ''}>Common</option>
              <option value="uncommon" ${state.rarity === 'uncommon' ? 'selected' : ''}>Uncommon</option>
              <option value="rare" ${state.rarity === 'rare' ? 'selected' : ''}>Rare</option>
            </select>
          </label>
        </section>
        <p class="ob-text-muted ob-sticker-result-count" aria-live="polite">
          Showing ${filtered.length} of ${state.shelf.total} stickers
        </p>
        ${filtered.length
          ? `<div class="ob-sticker-grid">${filtered.map(renderStickerCard).join('')}</div>`
          : `<div class="ob-card ob-text-center ob-sticker-empty" role="status">
              <h2 class="ob-card__title">${stickers.length ? 'No stickers match these filters' : 'Your first sticker is waiting'}</h2>
              <p class="ob-card__body">${stickers.length
                ? 'Try changing the collection or rarity filter.'
                : 'Log a new bird sighting to start collecting.'}</p>
              ${onNavigate && !stickers.length
                ? '<button type="button" class="ob-btn ob-btn--primary" data-action="log-bird">Log a bird</button>'
                : ''}
            </div>`}
      </main>`;

    container.querySelectorAll('[data-filter]').forEach((select) => {
      select.addEventListener('change', () => {
        state[select.dataset.filter] = select.value;
        render();
      });
    });
    container.querySelector('[data-action="log-bird"]')?.addEventListener('click', () => {
      onNavigate('add-observation', { userId });
    });
    container.querySelectorAll('.ob-sticker__art img').forEach((image) => {
      image.addEventListener('error', () => {
        const placeholder = document.createElement('span');
        placeholder.className = 'ob-sticker__placeholder';
        placeholder.setAttribute('aria-hidden', 'true');
        placeholder.textContent = '✦';
        image.replaceWith(placeholder);
      }, { once: true });
    });
    wireBack();
  }

  function wireBack() {
    container.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      if (onNavigate) onNavigate('home');
    });
  }

  async function load() {
    state.error = null;
    state.shelf = null;
    render();
    try {
      state.shelf = await getStickerShelf(userId);
    } catch (error) {
      state.error = error instanceof Error ? error.message : 'Could not load your sticker shelf.';
    }
    render();
  }

  await load();
}