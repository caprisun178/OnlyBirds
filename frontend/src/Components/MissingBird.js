// Components/MissingBird.js — presentational only. The greyed placeholder
// for a species in the region checklist the user hasn't logged yet.
//
// Also where Pinned Birds' pin toggle lives (docs/features/pinned-birds.md):
// only a not-yet-observed species can be pinned — pinning an already-logged
// one is rejected server-side ("nothing to chase") — which this card is the
// one place that's always true for, so the button lives here rather than on
// SpeciesCard.js (already-seen birds). `pinned` is passed in by the
// Presenter (it owns the fetched pin list, not this component); the pin
// button's click is a `data-action="toggle-pin"` + `data-pin-scientific-name`/
// `data-pin-common-name` pair for the Presenter to wire.
//
// Deliberately NOT `data-scientific-name`/`data-common-name` — those are
// SpeciesCard.js's own attributes, which LifeList.js's wireSpeciesCards()
// selects on to wire a click-to-open-observation-log handler. Reusing that
// exact attribute name here meant this button not only got its own
// toggle-pin click handler, it *also* matched wireSpeciesCards()'s selector
// and got a second, unwanted "navigate away" handler attached to the same
// element — stopPropagation() in the pin handler doesn't help, since that
// only stops bubbling to ancestors, not a second listener on the same
// element (a real "unpin sends me to Add Observation" bug). Separate
// attribute names make the two wiring passes mutually exclusive by
// construction, instead of relying on each Presenter's selector being
// careful not to overlap.
import { escapeHtml } from './htmlUtils.js';

export function renderMissingBird(species, { pinned = false } = {}) {
  // The dimming (opacity: 0.6) is scoped to this inner wrapper, not the
  // whole <article> — CSS opacity composites every descendant regardless of
  // their own opacity value, so a pin button inside a 0.6-opacity article
  // would still render dimmed (and read as disabled) no matter what opacity
  // *it* declared. The button sits outside that wrapper instead, at full
  // strength, so "not seen yet" still reads as de-emphasized while "pin
  // this" stays a clear, fully-visible action.
  //
  // The whole card now opens the Bird Info page (docs/features/bird-info.md
  // §1, row 2) — `data-profile-scientific-name`, a third attribute name
  // distinct from both `data-scientific-name` (SpeciesCard.js's seen-card
  // click target) and `data-pin-scientific-name` (the pin button below), on
  // purpose: reusing either of those exact names on a second, differently-
  // wired element is the exact bug this app already shipped and fixed once
  // (see this file's own history / bird-info.md's note on it) — two
  // listeners firing off one click because they happened to share a
  // selector, not because anyone meant to wire two handlers to one click.
  return `
    <article
      class="ob-card ob-card--flat ob-text-center"
      style="cursor:pointer;"
      data-profile-scientific-name="${escapeHtml(species.scientific_name)}"
      data-profile-common-name="${escapeHtml(species.common_name)}"
      role="button"
      tabindex="0"
    >
      <div style="opacity: 0.6;">
        <div aria-hidden="true" style="height:80px;border-radius:var(--ob-radius-sm);background:var(--ob-color-surface-alt);"></div>
        <h3 class="ob-card__title">${escapeHtml(species.common_name)}</h3>
        <p class="ob-card__body ob-text-sm"><em>${escapeHtml(species.scientific_name)}</em></p>
        <span class="ob-tag">Not seen yet</span>
      </div>
      <button
        type="button"
        class="ob-btn ob-btn--sm ${pinned ? 'ob-btn--primary' : 'ob-btn--ghost'}"
        style="margin-top: var(--ob-space-2);"
        data-action="toggle-pin"
        data-pin-scientific-name="${escapeHtml(species.scientific_name)}"
        data-pin-common-name="${escapeHtml(species.common_name)}"
        data-pinned="${pinned}"
        aria-pressed="${pinned}"
      >${pinned ? 'Pinned' : 'Pin'}</button>
    </article>
  `;
}
