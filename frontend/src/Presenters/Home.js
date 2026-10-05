// frontend/src/Presenters/Home.js
// The app's landing screen: a header with quick links (Life List, Add
// Observation, Login) and Explore Map embedded directly below it, so you
// can start filtering sightings the moment the app loads — no separate
// welcome page to click through first. No router yet, so navigation goes
// through an optional onNavigate callback (it just logs for now). Auth/
// login is separate in-progress work — the header's Login button has
// nowhere to go yet, so it hits the same "no screen yet" fallback every
// other not-yet-built route already does.
//
// Deliberately no `ob-container` here (unlike AddObservation/LifeList/
// ObservationList, which each opt into it on their own top-level element) —
// a map screen wants the full viewport width, not a narrow centered reading
// column with large empty margins on a wide screen. `#app` itself carries
// no side padding either (see preview.html), so this provides its own — a
// literal 0.5in (not a `--ob-space-*` token) so it stays exactly that
// regardless of any future change to the spacing scale.

import { mount as mountExploreMap } from './ExploreMap.js';

export function mount(container, props = {}) {
  const { onNavigate = (route) => console.log('navigate to:', route) } = props;

  container.innerHTML = `
    <div class="ob-stack" style="padding-inline: 0.5in;">
      <header class="ob-cluster" style="justify-content: space-between; align-items: center;">
        <h1 style="margin: 0;">Only Birds</h1>
        <nav class="ob-cluster" aria-label="Main">
          <button type="button" class="ob-btn ob-btn--ghost" data-route="life-list">Life List</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="add-observation">Add Observation</button>
          <button type="button" class="ob-btn ob-btn--ghost" data-route="plan-a-trip">Plan a Trip</button>
          <button type="button" class="ob-btn ob-btn--primary" data-route="login">Log in</button>
        </nav>
      </header>
      <div data-role="explore-map"></div>
    </div>
  `;

  container.querySelectorAll('[data-route]').forEach((el) => {
    el.addEventListener('click', () => onNavigate(el.dataset.route));
  });

  mountExploreMap(container.querySelector('[data-role="explore-map"]'), { ...props, onNavigate, embedded: true });
}
