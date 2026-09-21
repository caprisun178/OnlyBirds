// frontend/src/Components/HomeCard.js
// Presentational only: no state, and no imports from Dao/ or Services/.

// Returns a string of markup;the Presenter decides where it goes.

export function renderHomeCard({ title, body, route, buttonLabel, tag }) {
  return `
    <article class="ob-card ob-card--interactive">
      <h3 class="ob-card__title">${title}</h3>
      ${tag ? `<span class="ob-tag ob-tag--info">${tag}</span>` : ''}
      <p class="ob-card__body ob-text-sm">${body}</p>
      <button class="ob-btn ob-btn--subtle ob-btn--sm" type="button" data-route="${route}">
        ${buttonLabel}
      </button>
    </article>
  `;
}