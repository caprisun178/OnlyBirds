function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  }[character]));
}

function formatAwardDate(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(date);
}

export function renderStickerCard(sticker) {
  const progress = sticker.progress == null
    ? ''
    : `<p class="ob-sticker__progress">${sticker.target == null
      ? `${sticker.progress} species found`
      : `${sticker.progress} of ${sticker.target}`}</p>`;
  const awardDate = formatAwardDate(sticker.awarded_at);
  const image = sticker.image_url
    ? `<img src="${escapeHtml(sticker.image_url)}" alt="" loading="lazy" />`
    : '<span class="ob-sticker__placeholder" aria-hidden="true">✦</span>';

  return `
    <article class="ob-sticker ${sticker.earned ? 'ob-sticker--earned' : 'ob-sticker--locked'}"
      aria-label="${escapeHtml(sticker.name)}, ${sticker.earned ? 'earned' : 'not yet earned'}">
      <div class="ob-sticker__art">${image}</div>
      <div class="ob-sticker__body">
        <p class="ob-sticker__rarity">${escapeHtml(sticker.rarity)}</p>
        <h3>${escapeHtml(sticker.name)}</h3>
        <p class="ob-sticker__state"><span class="ob-tag ${sticker.earned ? 'ob-tag--success' : 'ob-tag--info'}">
          ${sticker.earned ? 'Earned' : 'Not yet earned'}
        </span></p>
        <p class="ob-sticker__description">${escapeHtml(sticker.description || '')}</p>
        ${progress}
        ${awardDate ? `<p class="ob-sticker__date">Earned ${escapeHtml(awardDate)}</p>` : ''}
      </div>
    </article>`;
}
