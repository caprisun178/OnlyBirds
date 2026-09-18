import { getStickerShelf } from '../Services/stickers.js';

function escapeHtml(value) {
  // Escape API-provided text before inserting it into the shelf markup.
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[character]));
}

function renderItem(sticker) {
  // Render one sticker card with its state and optional progress indicator.
  const progress = sticker.progress != null && sticker.target != null
    ? `<span>${sticker.progress} / ${sticker.target}</span>`
    : '';
  const image = sticker.image_url
    ? `<img src="${escapeHtml(sticker.image_url)}" alt="" loading="lazy" />`
    : `<span class="ob-sticker__placeholder" aria-hidden="true">✦</span>`;
  return `
    <article class="ob-sticker ${sticker.earned ? 'ob-sticker--earned' : 'ob-sticker--locked'}">
      <div class="ob-sticker__art">${image}</div>
      <div class="ob-sticker__body">
        <p class="ob-sticker__rarity">${escapeHtml(sticker.rarity)}</p>
        <h3>${escapeHtml(sticker.name)}</h3>
        <p>${escapeHtml(sticker.description)}</p>
        ${progress ? `<div class="ob-sticker__progress" aria-label="Progress">${progress}</div>` : ''}
      </div>
    </article>`;
}

export async function mount(container, { userId = 'u1' } = {}) {
  // Load a user's shelf and render its earned and locked sections.
  container.innerHTML = '<p class="ob-text-muted">Loading stickers...</p>';
  try {
    const shelf = await getStickerShelf(userId);
    container.innerHTML = `
      <header class="ob-sticker-header">
        <div>
          <p class="ob-eyebrow">Collection</p>
          <h1>Sticker shelf</h1>
          <p class="ob-text-muted">${shelf.earned.length} of ${shelf.total} earned</p>
        </div>
      </header>
      <section class="ob-sticker-section" aria-labelledby="earned-heading">
        <h2 id="earned-heading">Earned</h2>
        <div class="ob-sticker-grid">${shelf.earned.length ? shelf.earned.map(renderItem).join('') : '<p class="ob-text-muted">Your first sticker is waiting.</p>'}</div>
      </section>
      <section class="ob-sticker-section" aria-labelledby="locked-heading">
        <h2 id="locked-heading">Still to find</h2>
        <div class="ob-sticker-grid">${shelf.locked.map(renderItem).join('')}</div>
      </section>`;
  } catch (error) {
    container.innerHTML = `<p role="alert" class="ob-feedback ob-feedback--error">${escapeHtml(error.message)}</p>`;
  }
}