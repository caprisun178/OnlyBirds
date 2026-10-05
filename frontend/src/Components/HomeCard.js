// frontend/src/Components/HomeCard.js
// Presentational only: no state, and no imports from Dao/ or Services/.

export function renderHomeCard({ emoji, title, body, route, buttonLabel, tag, tagVariant = 'info' }) {
  return `
    <article class="ob-card ob-card--interactive">
      <h3 class="ob-card__title">
        ${emoji ? `<span aria-hidden="true">${emoji}</span> ` : ''}${title}
      </h3>
      ${tag ? `<span class="ob-tag ob-tag--${tagVariant}">${tag}</span>` : ''}
      <p class="ob-card__body ob-text-sm">${body}</p>
      <button class="ob-btn ob-btn--subtle ob-btn--sm" type="button" data-route="${route}">
        ${buttonLabel}
      </button>
      
    </article>
  `;
}