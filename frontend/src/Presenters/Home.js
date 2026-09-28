// frontend/src/Presenters/Home.js
// The app's landing screen — no separate marketing page, this is the first
// thing shown. A welcome, a main call to action, and cards that lead to the
// other screens. No router yet, so navigation goes through an optional
// onNavigate callback (it just logs for now). Auth/login is separate
// in-progress work, not wired in here.

import { renderHomeCard } from '../Components/HomeCard.js';

// Keep tags in sync with docs/features/overview.md. .
const FEATURES = [
  {
    emoji: '📋',
    title: 'Life list',
    body: "Your region's full checklist, your finds filled in, a bar creeping toward 100%.",
    route: 'life-list',
    buttonLabel: 'Open life list',
    tag: 'Building now',
    tagVariant: 'progress',
  },
  {
    emoji: '✨',
    title: 'Stickers',
    body: 'A hundred species. Collect them on your profile!',
    route: 'stickers',
    buttonLabel: 'View stickers',
    tag: 'Coming soon',
  },
  {
    emoji: '🗺️',
    title: 'Explore map',
    body: "Drift around the map and see what's been spotted near you.",
    route: 'explore-map',
    buttonLabel: 'Open map',
    tag: 'Coming soon',
  },
  {
    emoji: '📌',
    title: 'Pinned birds',
    body: "Mark the ones you want. We'll nudge you when someone reports it in your area.",
    route: 'pinned-birds',
    buttonLabel: 'See pinned birds',
    tag: 'Coming soon',
  },
  {
    emoji: '🔊',
    title: 'Bird guide',
    body: 'Look up any species for its calls, range, migration and photos.',
    route: 'bird-info',
    buttonLabel: 'Browse the guide',
    tag: 'Coming soon',
  },
];

export function mount(container, props = {}) {
  const { onNavigate = (route) => console.log('navigate to:', route) } = props;

  container.innerHTML = `
    <div class="ob-container ob-stack">
      <header class="ob-stack">
        <p class="ob-text-muted ob-text-sm">🐦 spot it, log it, collect it!</p>
        <h1>Welcome to Only Birds 🐤</h1>
        <p class="ob-text-muted">
          Spot a bird, pop it on your list, and earn stickers along the way.
        </p>
      </header>

      <div class="ob-cluster">
        <button class="ob-btn ob-btn--primary ob-btn--lg" type="button" data-route="add-observation">
          Describe a bird
        </button>
        <button class="ob-btn ob-btn--ghost ob-btn--lg" type="button" data-route="life-list">
          See my life list
        </button>
      </div>

      <section class="ob-card ob-stack" aria-labelledby="how-title">
        <h2 id="how-title" class="ob-card__title">A logbook and a treasure map</h2>
        <p class="ob-card__body">
          Keep a diary of what you've seen, and see the whole checklist for your
          region with your birds coloured in.
        </p>
      </section>

      <section class="ob-stack" aria-labelledby="features-title">
        <h2 id="features-title">Stuff you can do 🎉</h2>
        <div class="ob-grid">
          ${FEATURES.map((feature) => renderHomeCard(feature)).join('')}
        </div>
      </section>

      <section class="ob-card ob-text-center ob-stack" aria-labelledby="closing-title">
        <h2 id="closing-title" class="ob-card__title">Ready to start collecting? 🐣</h2>
        <div>
          <button class="ob-btn ob-btn--primary" type="button" data-route="add-observation">
            Describe a bird
          </button>
        </div>
      </section>
    </div>
  `;

  container.querySelectorAll('[data-route]').forEach((el) => {
    el.addEventListener('click', () => onNavigate(el.dataset.route));
  });
}